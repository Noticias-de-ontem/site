"""
Ferramenta local para enriquecer posts já guardados no arquivo.

O que faz:
- revê posts antigos guardados em `pt/*.json` e `en/*.json`
- detecta carrosséis, captions fracas, recaps, promo e outros casos problemáticos
- vai buscar metadados frescos ao Instagram por shortcode (só quando necessário)
- opcionalmente usa Gemini para escrever contexto mais útil para o gerador de posts

Notas práticas:
- foi pensada para correr localmente
- a chave Gemini é opcional; sem ela o script pode correr em modo metadata-only
- o progresso fica guardado em `enrich_saved_posts_state.json`
- podes parar graciosamente com Ctrl+C ou criando um ficheiro de stop
- quando o Instagram bloqueia, o ficheiro atual é guardado IMEDIATAMENTE antes da espera
- o delay entre pedidos ao Instagram evita bloqueios precoces

Exemplos:
  python enrich_saved_posts.py --lang pt --metadata-only
  python enrich_saved_posts.py --lang pt --limit 100
  python enrich_saved_posts.py --lang en --gemini-api-key AQUI_A_TUA_CHAVE
  python enrich_saved_posts.py --lang pt --request-delay 2.0 --jitter 1.5
"""

import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from io import BytesIO

import instaloader
import requests
from PIL import Image
from nvidia_client import load_nvidia_api_keys, NvidiaKeyPool

from archive_storage import LANG_DIRS, block_path, iter_block_ids_for_month


STATE_FILE = "enrich_saved_posts_state.json"
DEFAULT_STOP_FILE = "enrich_saved_posts.stop"
DEFAULT_MAX_CAROUSEL_IMAGES = int(os.environ.get("ENRICH_MAX_CAROUSEL_IMAGES", "10"))
DEFAULT_REQUEST_DELAY = float(os.environ.get("ENRICH_REQUEST_DELAY", "2.0"))
DEFAULT_JITTER = float(os.environ.get("ENRICH_JITTER", "1.0"))
DEFAULT_SAVE_EVERY = int(os.environ.get("ENRICH_SAVE_EVERY", "5"))
LOCAL_NVIDIA_KEY_FILE = "nvidia_api_key.local.txt"
NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"



BLOCK_BACKOFF_MINUTES = [5, 15, 30, 60, 90, 90]
_block_count = 0


LOCAL_NVIDIA_API_KEY = ""

NVIDIA_API_KEY = ""
nvidia_pool = None

ROUNDUP_PATTERNS = [
    r"\besta semana\b",
    r"\bthis week\b",
    r"\bfotos que marcam\b",
    r"\bphotos? of the day\b",
    r"\bphotos? that (mark|defined)\b",
    r"\bweek in review\b",
    r"\bveja algumas dessas imagens\b",
    r"\bna .* escolhemos\b",
]

CTA_PATTERNS = [
    r"\blink na bio\b",
    r"\bna bio\b",
    r"\bread more\b",
    r"\bsee more\b",
    r"\bsaiba mais\b",
    r"\bveja mais\b",
    r"\bacompanhe\b",
    r"\binsta stories\b",
    r"\bstories\b",
    r"\bswipe\b",
    r"\barraste\b",
    r"\bsegue\b",
]

PROMO_PATTERNS = [
    r"\bc[oó]digo\b",
    r"\bcoupon\b",
    r"\bdesconto\b",
    r"\bpromo\b",
    r"\bapp\b",
    r"\bdownload\b",
    r"\bclubefashion\b",
]

MEME_PATTERNS = [
    r"\bmeme\b",
    r"\bviral\b",
    r"\bqual [ée] o vosso\b",
    r"\bwho else\b",
    r"😂",
    r"😭",
]

BLOCK_PATTERNS = [
    "429",
    "too many requests",
    "feedback required",
    "feedback_required",
    "checkpoint required",
    "checkpoint_required",
    "challenge required",
    "challenge_required",
    "please wait a few minutes",
    "try again later",
    "temporarily blocked",
]


def normalize_text(value, uppercase=False):
    if value is None:
        value = ""
    normalized = unicodedata.normalize("NFC", str(value)).strip()
    return normalized.upper() if uppercase else normalized


def read_local_nvidia_key_file():
    if not os.path.exists(LOCAL_NVIDIA_KEY_FILE):
        return ""
    with open(LOCAL_NVIDIA_KEY_FILE, "r", encoding="utf-8") as f:
        return normalize_text(f.read())


def resolve_nvidia_api_key(cli_value=""):
    return normalize_text(
        cli_value
        or LOCAL_NVIDIA_API_KEY
        or os.environ.get("NVIDIA_API_KEY", "")
        or read_local_nvidia_key_file()
    )


def configure_nvidia_client(cli_value=""):
    global NVIDIA_API_KEY
    global nvidia_pool

    NVIDIA_API_KEY = resolve_nvidia_api_key(cli_value)
    if NVIDIA_API_KEY:
        nvidia_pool = NvidiaKeyPool([NVIDIA_API_KEY])
    else:

        from nvidia_client import load_nvidia_api_keys
        keys = load_nvidia_api_keys()
        nvidia_pool = NvidiaKeyPool(keys) if keys else None
    return nvidia_pool


def now_local():
    return datetime.now().astimezone()


def format_local(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path, data):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def count_hashtags(text):
    return len(re.findall(r"(?<!\w)#\w+", text))


def has_any_pattern(text, patterns):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def detect_content_flags(post):
    caption = normalize_text(post.get("raw_caption") or post.get("global_context") or post.get("caption") or "")
    media_count = int(post.get("media_count") or 1)
    source_profile = normalize_text(post.get("source_profile", ""))
    flags = set(str(flag) for flag in post.get("content_flags", []) if str(flag))

    lowered = caption.casefold()
    if media_count > 1:
        flags.add("carousel")
    if not caption:
        flags.add("empty_caption")
    if len(caption) < 120:
        flags.add("short_caption")
    if count_hashtags(caption) >= 5:
        flags.add("hashtag_heavy")
    if has_any_pattern(lowered, ROUNDUP_PATTERNS):
        flags.add("roundup_caption")
    if re.search(r"\b(esta semana|this week|week in review)\b", lowered, flags=re.IGNORECASE):
        flags.add("weekly_recap")
    if has_any_pattern(lowered, CTA_PATTERNS):
        flags.add("call_to_action")
    if has_any_pattern(lowered, PROMO_PATTERNS):
        flags.add("promo_caption")
    if has_any_pattern(caption, MEME_PATTERNS):
        flags.add("internet_culture_signal")
    if media_count > 1 and len(caption) < 260:
        flags.add("carousel_low_context")
    if source_profile and source_profile in {"epahsaiu", "revista_nit", "buzzfeed", "buzzfeednews", "insider", "deuxmoi"}:
        flags.add("internet_culture_signal")
    if not post.get("media_type"):
        flags.add("missing_media_metadata")
    if not post.get("source_profile"):
        flags.add("missing_source_profile")

    return sorted(flags)


def infer_content_mode(flags, media_type):
    flag_set = set(flags)
    if "weekly_recap" in flag_set:
        return "weekly_recap"
    if "roundup_caption" in flag_set and "carousel" in flag_set:
        return "carousel_roundup"
    if "promo_caption" in flag_set:
        return "promo"
    if "internet_culture_signal" in flag_set:
        return "internet_culture"
    if media_type == "carousel":
        return "carousel"
    if media_type == "video":
        return "video"
    return "single_story"


def needs_enrichment(post, flags):
    flag_set = set(flags)
    if post.get("enrichment_status") == "done":
        return False
    if "missing_media_metadata" in flag_set or "missing_source_profile" in flag_set:
        return True
    if "carousel" in flag_set or "carousel_low_context" in flag_set:
        return True
    if "roundup_caption" in flag_set or "weekly_recap" in flag_set:
        return True
    if "call_to_action" in flag_set or "promo_caption" in flag_set:
        return True
    if "empty_caption" in flag_set:
        return True
    return False


def post_needs_instagram_fetch(post):
    """
    Verifica se o post precisa realmente de ir buscar dados ao Instagram.
    Se já tiver todos os campos críticos preenchidos, poupa o pedido à API.
    """
    if not post.get("media_type"):
        return True
    if not post.get("source_profile"):
        return True
    if not post.get("image_url"):
        return True

    if post.get("media_type") == "carousel" and not post.get("slide_urls"):
        return True
    return False


def init_instaloader():
    print("A inicializar Instaloader...")
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_video_thumbnails=False,
        download_videos=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )

    session_file = "instaloader.session"
    if os.path.exists(session_file):
        insta_user = os.environ.get("INSTA_USERNAME", "imported_session")
        print(f"A carregar sessão guardada de {session_file}...")
        loader.load_session_from_file(insta_user, session_file)
        print("Sessão carregada. A avançar para os blocos de arquivo...")
        return loader

    insta_user = os.environ.get("INSTA_USERNAME")
    insta_pass = os.environ.get("INSTA_PASSWORD")
    if insta_user and insta_pass:
        print(f"A iniciar sessão direta com {insta_user}...")
        loader.login(insta_user, insta_pass)
        print("Sessão iniciada com sucesso.")
    else:
        print("Sem sessão local nem credenciais diretas. Vai continuar no modo disponível.")

    return loader


def is_instagram_block_error(error):
    message = str(error).casefold()
    return any(pattern in message for pattern in BLOCK_PATTERNS)


def wait_after_block(on_emergency_save=None):
    """
    Espera com backoff exponencial após bloqueio Instagram.
    Chama on_emergency_save() ANTES de esperar para preservar o progresso.
    """
    global _block_count
    wait_minutes = BLOCK_BACKOFF_MINUTES[min(_block_count, len(BLOCK_BACKOFF_MINUTES) - 1)]
    _block_count += 1

    jitter_seconds = random.uniform(0, wait_minutes * 0.1 * 60)
    total_seconds = wait_minutes * 60 + jitter_seconds

    blocked_at = now_local()
    resume_after = blocked_at + timedelta(seconds=total_seconds)
    print("\n" + "=" * 60)
    print(f"BLOQUEIO TEMPORÁRIO: tentativa {_block_count}")
    print(f"Parou em: {format_local(blocked_at)}")
    print(f"Vai retomar em: {format_local(resume_after)} ({wait_minutes} min + jitter)")
    print("=" * 60)


    if on_emergency_save:
        on_emergency_save()

    print("A aguardar retoma automática... (Ctrl+C para sair agora; o progresso está guardado)")
    time.sleep(max(0, (resume_after - now_local()).total_seconds()))


def reset_block_count():
    """Reseta o contador de bloqueios após um fetch bem-sucedido."""
    global _block_count
    _block_count = 0


def extract_media_metadata(post, fetch_video_urls=False):
    primary_image_url = post.url
    video_url = post.video_url if post.is_video and fetch_video_urls else ""
    slide_urls = []
    slide_video_urls = []
    media_type = "video" if post.is_video else "image"
    media_count = getattr(post, "mediacount", 1) or 1

    if getattr(post, "typename", "") == "GraphSidecar":
        media_type = "carousel"
        for node in post.get_sidecar_nodes():
            slide_urls.append(node.display_url)
            slide_video_urls.append(node.video_url if node.is_video and fetch_video_urls else "")
        if slide_urls:
            primary_image_url = slide_urls[0]
        if slide_video_urls and slide_video_urls[0]:
            video_url = slide_video_urls[0]
    else:
        slide_urls = [post.url]
        slide_video_urls = [video_url or ""]

    return {
        "image_url": primary_image_url,
        "source_url": f"https://www.instagram.com/p/{post.shortcode}/",
        "media_type": media_type,
        "media_count": max(media_count, len(slide_urls) or 1),
        "is_video": bool(post.is_video),
        "video_url": video_url,
        "slide_urls": slide_urls,
        "slide_video_urls": slide_video_urls,
        "raw_caption": normalize_text(post.caption or ""),
        "source_profile": normalize_text(post.owner_username or ""),
    }


def hydrate_post_from_instagram(
    loader,
    post,
    fetch_video_urls=False,
    request_delay=DEFAULT_REQUEST_DELAY,
    jitter=DEFAULT_JITTER,
    on_block=None,
):
    """
    Vai buscar metadados ao Instagram para um post.
    - request_delay: pausa (segundos) antes de cada pedido para evitar bloqueios.
    - jitter: variação aleatória adicional ao delay.
    - on_block: callback chamado IMEDIATAMENTE quando se deteta um bloqueio,
                antes de qualquer espera, para guardar o ficheiro atual.
    """
    shortcode_list = post.get("shortcodes") or []
    if not shortcode_list:
        return post

    shortcode = shortcode_list[0]
    while True:
        try:

            if request_delay > 0:
                sleep_time = request_delay + random.uniform(0, jitter)
                time.sleep(sleep_time)

            live_post = instaloader.Post.from_shortcode(loader.context, shortcode)
            metadata = extract_media_metadata(live_post, fetch_video_urls=fetch_video_urls)
            post.update(metadata)
            if metadata.get("raw_caption") and not post.get("global_context"):
                post["global_context"] = metadata["raw_caption"]
            reset_block_count()
            return post
        except Exception as exc:
            if is_instagram_block_error(exc):
                print(f"\n[Aviso] Instaloader bloqueado para o shortcode {shortcode}. A tentar Instagrapi Mobile API...")
                try:
                    from instagram_mobile_fallback import get_fallback_client, InstagrapiPostWrapper
                    cl = get_fallback_client()
                    if cl:
                        media_pk = cl.media_pk_from_code(shortcode)
                        media = cl.media_info(media_pk)
                        live_post = InstagrapiPostWrapper(media)
                        metadata = extract_media_metadata(live_post, fetch_video_urls=fetch_video_urls)
                        post.update(metadata)
                        if metadata.get("raw_caption") and not post.get("global_context"):
                            post["global_context"] = metadata["raw_caption"]
                        print(f"  [Sucesso] Metadados recuperados com sucesso via Instagrapi!")
                        reset_block_count()
                        return post
                except Exception as fallback_exc:
                    print(f"  [Erro] Falha também no Instagrapi: {fallback_exc}")

                wait_after_block(on_emergency_save=on_block)
                continue
            raise


def download_images(urls, limit):
    images = []
    for index, url in enumerate(urls[:limit]):
        if not url:
            continue
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            images.append(
                {
                    "slide_number": index + 1,
                    "url": url,
                    "image": Image.open(BytesIO(response.content)).convert("RGB"),
                }
            )
        except Exception:
            continue
    return images


def enrich_with_ai(post, lang, max_carousel_images=DEFAULT_MAX_CAROUSEL_IMAGES):
    if not nvidia_pool or not nvidia_pool.has_keys():
        return None

    caption = normalize_text(post.get("raw_caption") or post.get("global_context") or "")
    source_profile = normalize_text(post.get("source_profile", ""))
    media_count = int(post.get("media_count") or 1)
    flags = ", ".join(post.get("content_flags", []))
    slide_urls = post.get("slide_urls") or []
    if not slide_urls and post.get("image_url"):
        slide_urls = [post["image_url"]]



    slide_url_lines = "\n".join(
        f"- slide {index + 1}: {url}" for index, url in enumerate(slide_urls[:max_carousel_images])
    )

    prompt = f"""
You are enriching archived social posts so a future content generator understands what this post was really about, even when the original caption is weak, generic, promotional, or part of a carousel.

Language required for the output: {lang.upper()}

Source profile: {source_profile}
Media count: {media_count}
Known flags: {flags}
Original caption:
{caption}

Slide image URLs:
{slide_url_lines}

Return a JSON object with exactly these keys:
- content_mode: one of "single_story", "carousel_roundup", "weekly_recap", "internet_culture", "meme", "promo", "photo_roundup", "institutional_news", "feature", "unclear"
- enriched_context: 1 to 3 short paragraphs, with the real useful context for future post generation. Remove hashtags and calls to action.
- summary: one sentence
- topic_keywords: array with up to 6 short strings
- virality_signals: array with up to 5 short strings
- carousel_items: array, one object per image/slide, preserving the slide order. Each object must have slide_number, description, visible_text, and news_value. (Since you cannot view the images, you can leave description, visible_text, and news_value empty, or guess/extract from caption context if mentioned).
- should_skip: true only if this is essentially unusable promo or too empty to recover
"""

    try:
        response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL)
        payload = json.loads(response_text or "{}")
    except Exception as exc:
        print(f"[{lang}] Erro ao chamar Nvidia em enrich_with_ai: {exc}")
        return None

    if not isinstance(payload, dict):
        return None

    payload["content_mode"] = normalize_text(payload.get("content_mode", ""))
    payload["enriched_context"] = normalize_text(payload.get("enriched_context", ""))
    payload["summary"] = normalize_text(payload.get("summary", ""))
    payload["topic_keywords"] = [normalize_text(item) for item in payload.get("topic_keywords", []) if normalize_text(item)]
    payload["virality_signals"] = [normalize_text(item) for item in payload.get("virality_signals", []) if normalize_text(item)]
    carousel_items = []
    

    raw_carousel = payload.get("carousel_items") or []
    for idx, slide_url in enumerate(slide_urls[:max_carousel_images]):
        slide_num = idx + 1
        item = {}

        if isinstance(raw_carousel, list):
            for r_item in raw_carousel:
                if isinstance(r_item, dict) and int(r_item.get("slide_number") or 0) == slide_num:
                    item = r_item
                    break
        
        carousel_items.append(
            {
                "slide_number": slide_num,
                "description": normalize_text(item.get("description", "")),
                "visible_text": normalize_text(item.get("visible_text", "")),
                "news_value": normalize_text(item.get("news_value", "")),
            }
        )
    payload["carousel_items"] = carousel_items
    payload["carousel_items_analyzed"] = len(carousel_items)
    payload["should_skip"] = bool(payload.get("should_skip", False))
    return payload


def target_files(args):
    langs = [args.lang] if args.lang else sorted(LANG_DIRS.keys())
    files = []
    for lang in langs:
        lang_dir = LANG_DIRS.get(lang)
        if not os.path.exists(lang_dir):
            continue
        if args.month:
            candidate_paths = [
                block_path(lang, block_id)
                for block_id in iter_block_ids_for_month(args.month)
            ]
        else:
            candidate_paths = [
                os.path.join(lang_dir, fname)
                for fname in sorted(os.listdir(lang_dir))
                if fname.endswith(".json")
            ]
        for path in candidate_paths:
            if os.path.exists(path):
                files.append((lang, os.path.basename(path)[:-5], path))
    return files


def load_state():
    return load_json(STATE_FILE, {})


def save_state(state):
    save_json(STATE_FILE, state)


def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def stop_requested(stop_file):
    return bool(stop_file) and os.path.exists(stop_file)


def should_resume_from(state, file_path, post_index):
    if not state:
        return True
    if state.get("status") not in {"running", "paused_keyboard_interrupt", "paused_stop_file", "paused_limit"}:
        return True
    state_path = state.get("file_path")
    if not state_path:
        return True
    state_index = int(state.get("post_index", 0))
    if file_path < state_path:
        return False
    if file_path > state_path:
        return True
    return post_index >= state_index


def print_block_progress(lang, block_id, index, total_posts, post, stage):
    shortcode = ""
    shortcodes = post.get("shortcodes") or []
    if shortcodes:
        shortcode = shortcodes[0]
    date_str = normalize_text(post.get("date", ""))
    message = f"[{lang}][bloco {block_id}] {stage} {index + 1}/{total_posts}"
    if date_str:
        message += f" - {date_str}"
    if shortcode:
        message += f" - {shortcode}"
    print(message)


def save_file_checkpoint_if_due(file_path, posts, lang, block_id, changed_in_file, save_every):
    interval = max(1, int(save_every or DEFAULT_SAVE_EVERY))
    if changed_in_file <= 0 or changed_in_file % interval != 0:
        return False
    save_json(file_path, posts)
    print(f"[{lang}][bloco {block_id}] Checkpoint guardado - posts alterados neste ficheiro: {changed_in_file}")
    return True


def clear_instagram_block_error(post):
    status = normalize_text(post.get("enrichment_status", ""))
    if status not in {"metadata_error", "ai_error"}:
        return False
    if not is_instagram_block_error(post.get("enrichment_error", "")):
        return False
    post.pop("enrichment_status", None)
    post.pop("enrichment_error", None)
    post.pop("enriched_at", None)
    post["needs_enrichment"] = True
    return True


def repair_instagram_block_errors(files):
    earliest = None
    repaired_total = 0
    for lang, block_id, file_path in files:
        posts = load_json(file_path, [])
        repaired_in_file = 0
        for index, post in enumerate(posts):
            if clear_instagram_block_error(post):
                repaired_in_file += 1
                if earliest is None:
                    earliest = {
                        "lang": lang,
                        "block_id": block_id,
                        "file_path": file_path,
                        "post_index": index,
                    }
        if repaired_in_file:
            save_json(file_path, posts)
            repaired_total += repaired_in_file
            print(f"[{lang}][bloco {block_id}] Reparados {repaired_in_file} erros de bloqueio Instagram.")
    return earliest, repaired_total


def main():
    parser = argparse.ArgumentParser(description="Enriquece posts guardados com metadados e contexto útil.")
    parser.add_argument("--lang", choices=["pt", "en"], help="Processa só um idioma.")
    parser.add_argument("--month", help="Processa só um mês MM.")
    parser.add_argument("--limit", type=int, default=0, help="Limite máximo de posts enriquecidos nesta execução.")
    parser.add_argument("--metadata-only", action="store_true", help="Só atualiza metadados/flags, sem NVIDIA.")
    parser.add_argument("--reanalyze", action="store_true", help="Reprocessa mesmo posts já marcados como done.")
    parser.add_argument("--no-resume", action="store_true", help="Ignora o ficheiro de estado e começa do início.")
    parser.add_argument("--nvidia-api-key", help="Chave NVIDIA opcional para uso local.")
    parser.add_argument("--max-carousel-images", type=int, default=DEFAULT_MAX_CAROUSEL_IMAGES, help="Máximo de imagens por carrossel enviadas ao NVIDIA.")
    parser.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help=f"Guarda o ficheiro a cada N posts alterados. Padrão: {DEFAULT_SAVE_EVERY}.")
    parser.add_argument("--fetch-video-urls", action="store_true", help="Também tenta guardar URLs diretos de vídeo. Mais lento e mais propenso a 429.")
    parser.add_argument("--stop-file", default=DEFAULT_STOP_FILE, help="Se este ficheiro existir, o script pára graciosamente no próximo checkpoint.")
    parser.add_argument("--request-delay", type=float, default=DEFAULT_REQUEST_DELAY, help=f"Delay em segundos entre pedidos ao Instagram. Padrão: {DEFAULT_REQUEST_DELAY}.")
    parser.add_argument("--jitter", type=float, default=DEFAULT_JITTER, help=f"Variação aleatória adicional ao delay (0 a N segundos). Padrão: {DEFAULT_JITTER}.")
    parser.add_argument("--force-instagram", action="store_true", help="Força o fetch ao Instagram mesmo para posts que já têm todos os metadados.")
    args = parser.parse_args()

    configure_nvidia_client(args.nvidia_api_key)

    print("=== ENRICH SAVED POSTS ===")
    print(f"Modelo NVIDIA: {NVIDIA_MODEL}")
    print(f"Estado guardado em: {STATE_FILE}")
    print(f"Stop file: {args.stop_file}")
    print(f"Delay entre pedidos Instagram: {args.request_delay}s + jitter 0-{args.jitter}s")
    print(f"Skip inteligente: {'DESATIVADO (--force-instagram)' if args.force_instagram else 'ATIVO (poupa pedidos desnecessários)'}")
    if nvidia_pool and nvidia_pool.has_keys():
        print("NVIDIA: ativo")
    else:
        print("NVIDIA: inativo (metadados locais/Instagram continuam disponíveis)")
        if not args.metadata_only:
            print("Erro: para enriquecer com IA define NVIDIA_API_KEY ou usa --nvidia-api-key.")
            print("Para atualizar apenas metadados/flags, corre explicitamente com --metadata-only.")
            return
    if args.metadata_only:
        print("Modo: metadata-only")
    print(f"Imagens por carrossel para IA: {args.max_carousel_images}")
    print(f"Checkpoint de ficheiro: a cada {max(1, args.save_every)} post(s) alterado(s)")
    print(f"URLs diretos de vídeo: {'ativos' if args.fetch_video_urls else 'inativos'}")
    print("Podes parar com Ctrl+C ou criando o stop file indicado acima.")

    files = target_files(args)
    if not files:
        print("Nenhum ficheiro alvo encontrado.")
        return

    print(f"Ficheiros/blocos alvo encontrados: {len(files)}")
    for lang, block_id, file_path in files:
        print(f"  - [{lang}] bloco {block_id}: {file_path}")

    state = {} if args.no_resume else load_state()
    repaired_state, repaired_total = repair_instagram_block_errors(files)
    if repaired_total:
        print(f"Reparação inicial: {repaired_total} posts voltaram à fila por erro de bloqueio Instagram.")
    if repaired_state and not args.no_resume and not should_resume_from(state, repaired_state["file_path"], repaired_state["post_index"]):
        state = {
            "status": "running",
            "lang": repaired_state["lang"],
            "block_id": repaired_state["block_id"],
            "file_path": repaired_state["file_path"],
            "post_index": repaired_state["post_index"],
            "updated_at": now_local().isoformat(),
            "note": "Retoma ajustada para repetir posts marcados indevidamente durante bloqueio Instagram.",
        }
        save_state(state)
        print(f"Retoma ajustada para {state['file_path']} no post {state['post_index']}.")

    loader = init_instaloader()
    if state:
        print(f"Retoma encontrada: {state}")

    enriched_count = 0
    audited_count = 0
    instagram_skipped = 0
    active_lang = ""
    active_block_id = ""
    active_file_path = ""
    active_post_index = 0
    active_next_post_index = 0
    active_posts = None
    active_changed = False

    try:
        for lang, block_id, file_path in files:
            posts = load_json(file_path, [])
            changed = False
            changed_in_file = 0
            active_lang = lang
            active_block_id = block_id
            active_file_path = file_path
            active_post_index = 0
            active_next_post_index = 0
            active_posts = posts
            active_changed = False
            total_posts = len(posts)

            print(f"\n[{lang}][bloco {block_id}] A abrir {file_path} ({total_posts} posts no ficheiro)")

            for index, post in enumerate(posts):
                if stop_requested(args.stop_file):
                    save_state(
                        {
                            "status": "paused_stop_file",
                            "lang": lang,
                            "block_id": block_id,
                            "file_path": file_path,
                            "post_index": index,
                            "updated_at": now_local().isoformat(),
                            "note": f"Stop file detetado em {args.stop_file}.",
                        }
                    )
                    if changed:
                        save_json(file_path, posts)
                        print(f"[{lang}] Atualizado {file_path}")
                    print(f"Stop file detetado: {args.stop_file}. A parar graciosamente.")
                    return

                if not should_resume_from(state, file_path, index):
                    continue

                if args.month and str(post.get("date", ""))[5:7] != args.month:
                    continue

                active_lang = lang
                active_block_id = block_id
                active_file_path = file_path
                active_post_index = index
                active_next_post_index = index

                if index == 0 or (index + 1) % 50 == 0:
                    print_block_progress(lang, block_id, index, total_posts, post, "A analisar")

                save_state(
                    {
                        "status": "running",
                        "lang": lang,
                        "block_id": block_id,
                        "file_path": file_path,
                        "post_index": index,
                        "updated_at": now_local().isoformat(),
                    }
                )

                if "raw_caption" not in post:
                    post["raw_caption"] = normalize_text(post.get("global_context") or post.get("caption") or "")

                flags = detect_content_flags(post)
                post["content_flags"] = flags
                post["content_mode"] = normalize_text(post.get("content_mode") or infer_content_mode(flags, post.get("media_type", "")))
                post["needs_enrichment"] = needs_enrichment(post, flags)
                audited_count += 1

                is_carousel = (post.get("media_type") == "carousel") or ("carousel" in flags)
                needs_carousel_items = is_carousel and not post.get("carousel_items")

                if post.get("enrichment_status") == "done" and not args.reanalyze and not needs_carousel_items:
                    continue

                if not post["needs_enrichment"] and post.get("media_type") and post.get("source_profile"):
                    post["enrichment_status"] = "not_needed"
                    continue


                needs_fetch = args.force_instagram or post_needs_instagram_fetch(post)
                if not needs_fetch:
                    instagram_skipped += 1
                    if index % 200 == 0 and instagram_skipped > 0:
                        print(f"[{lang}][bloco {block_id}] {instagram_skipped} pedidos Instagram poupados até agora (skip inteligente)")
                else:

                    def make_emergency_save(fp, ps, l, bid, idx):
                        def _save():
                            save_json(fp, ps)
                            save_state({
                                "status": "paused_block_wait",
                                "lang": l,
                                "block_id": bid,
                                "file_path": fp,
                                "post_index": idx,
                                "updated_at": now_local().isoformat(),
                                "note": "Guardado automaticamente durante bloqueio Instagram.",
                            })
                            print(f"[{l}][bloco {bid}] ⚠️  Guardado de emergência antes da espera: {fp}")
                        return _save

                    try:
                        post = hydrate_post_from_instagram(
                            loader,
                            post,
                            fetch_video_urls=args.fetch_video_urls,
                            request_delay=args.request_delay,
                            jitter=args.jitter,
                            on_block=make_emergency_save(file_path, posts, lang, block_id, index),
                        )
                    except Exception as exc:
                        print_block_progress(lang, block_id, index, total_posts, post, "Erro metadados")
                        print(f"  Motivo: {normalize_text(str(exc))[:300]}")
                        post["enrichment_status"] = "metadata_error"
                        post["enrichment_error"] = normalize_text(str(exc))
                        changed = True
                        active_changed = True
                        changed_in_file += 1
                        active_next_post_index = index + 1
                        if save_file_checkpoint_if_due(file_path, posts, lang, block_id, changed_in_file, args.save_every):
                            active_changed = False
                        continue

                    flags = detect_content_flags(post)
                    post["content_flags"] = flags
                    post["content_mode"] = normalize_text(post.get("content_mode") or infer_content_mode(flags, post.get("media_type", "")))
                    post["needs_enrichment"] = needs_enrichment(post, flags)
                    is_carousel = (post.get("media_type") == "carousel") or ("carousel" in flags)
                    needs_carousel_items = is_carousel and not post.get("carousel_items")

                if not args.metadata_only and (post["needs_enrichment"] or needs_carousel_items):
                    try:
                        print_block_progress(lang, block_id, index, total_posts, post, "A enriquecer")
                        ai_payload = enrich_with_ai(post, lang, args.max_carousel_images)
                        if ai_payload:
                            post["ai_summary"] = ai_payload["summary"]
                            post["topic_keywords"] = ai_payload["topic_keywords"]
                            post["virality_signals"] = ai_payload["virality_signals"]
                            post["content_mode"] = ai_payload["content_mode"] or post["content_mode"]
                            post["should_skip"] = ai_payload["should_skip"]
                            post["carousel_items"] = ai_payload["carousel_items"]
                            post["carousel_items_analyzed"] = ai_payload["carousel_items_analyzed"]
                            if ai_payload["enriched_context"]:
                                post["global_context"] = ai_payload["enriched_context"]
                                post["enriched_context"] = ai_payload["enriched_context"]
                            post["enrichment_status"] = "done"
                        else:
                            post["enrichment_status"] = "metadata_only"
                    except Exception as exc:
                        print_block_progress(lang, block_id, index, total_posts, post, "Erro IA")
                        print(f"  Motivo: {normalize_text(str(exc))[:300]}")
                        post["enrichment_status"] = "ai_error"
                        post["enrichment_error"] = normalize_text(str(exc))
                else:
                    post["enrichment_status"] = "metadata_only" if post["needs_enrichment"] else "not_needed"

                post["enriched_at"] = now_local().isoformat()
                enriched_count += 1
                changed = True
                active_changed = True
                changed_in_file += 1
                active_next_post_index = index + 1
                if save_file_checkpoint_if_due(file_path, posts, lang, block_id, changed_in_file, args.save_every):
                    active_changed = False

                if args.limit and enriched_count >= args.limit:
                    break

            if changed:
                save_json(file_path, posts)
                print(f"[{lang}][bloco {block_id}] Atualizado {file_path} · posts alterados neste ficheiro: {changed_in_file}")
                active_changed = False
            else:
                print(f"[{lang}][bloco {block_id}] Sem alterações neste ficheiro.")

            if args.limit and enriched_count >= args.limit:
                break

    except KeyboardInterrupt:
        if active_changed and active_posts is not None and active_file_path:
            save_json(active_file_path, active_posts)
            print(f"\n[{active_lang}] Checkpoint guardado antes de sair: {active_file_path}")
        save_state(
            {
                "status": "paused_keyboard_interrupt",
                "lang": active_lang,
                "block_id": active_block_id,
                "file_path": active_file_path,
                "post_index": active_next_post_index,
                "updated_at": now_local().isoformat(),
                "note": "Execução interrompida manualmente com Ctrl+C.",
            }
        )
        print("\nInterrompido manualmente. O progresso ficou guardado para retoma.")
        print(f"Pedidos Instagram poupados por skip inteligente: {instagram_skipped}")
        return

    if not args.limit or enriched_count < args.limit:
        clear_state()
    else:
        save_state(
            {
                "status": "paused_limit",
                "lang": active_lang,
                "block_id": active_block_id,
                "file_path": active_file_path,
                "post_index": active_next_post_index,
                "updated_at": now_local().isoformat(),
                "note": "Execução interrompida por limite manual.",
            }
        )

    print(
        f"Concluído. Posts auditados: {audited_count}. "
        f"Posts efetivamente enriquecidos/atualizados nesta execução: {enriched_count}. "
        f"Pedidos Instagram poupados por skip inteligente: {instagram_skipped}."
    )


if __name__ == "__main__":
    main()
