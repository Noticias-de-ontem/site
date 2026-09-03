import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta

import instaloader
import requests

from archive_storage import (
    block_id_for_month_day,
    block_path,
    ensure_lang_dir,
    load_all_shortcodes,
    load_block,
    save_block,
)


HISTORICAL_BACKFILL_MODE = True
OLDEST_YEAR = 2010
CONSECUTIVE_EXISTING_LIMIT = 15
BLOCK_RETRY_MINUTES = int(os.environ.get("SCRAPER_BLOCK_RETRY_MINUTES", "90"))
FLUSH_EVERY_NEW_POSTS = int(os.environ.get("SCRAPER_FLUSH_EVERY_NEW_POSTS", "250"))
PROFILE_POSTS_BEFORE_COOLDOWN = int(os.environ.get("SCRAPER_PROFILE_POSTS_BEFORE_COOLDOWN", "25000"))
PROFILE_COOLDOWN_MINUTES = int(os.environ.get("SCRAPER_PROFILE_COOLDOWN_MINUTES", "60"))
PROGRESS_STATE_FILE = "scraper_progress.json"
RESUME_DIR = "scraper_resume"

PROFILES = {
    "pt": [
        "publico.pt",
        "sicnoticias",
        "cnnportugal",
        "rtpnoticias",
        "correiodamanhaoficial",
        "observador",
        "24sapo",
        "epahsaiu",
        "4gnewspt",
        "renascenca",
        "jornalexpresso",
        "hojenomundomilitar",
        "revista_nit",
        "revistaoriana",
    ],
    "en": [
        "nytimes",
        "cnn",
        "bbcnews",
        "aljazeeraenglish",
        "guardian",
        "buzzfeed",
        "buzzfeednews",
        "insidertech",
        "hojenomundomilitar",
        "politicoeurope",
        "insider",
        "deuxmoi",
    ],
}

LIGHTWEIGHT_PROFILES = {
    "epahsaiu",
    "revista_nit",
    "buzzfeed",
    "buzzfeednews",
    "insider",
    "insidertech",
    "deuxmoi",
}

ROUNDUP_PATTERNS = [
    r"\besta semana\b",
    r"\bthis week\b",
    r"\bfotos que marcam\b",
    r"\bphotos? of the day\b",
    r"\bphotos? that (mark|defined)\b",
    r"\bselecionadas? pela\b",
    r"\bna .* escolhemos\b",
    r"\bveja algumas dessas imagens\b",
    r"\bwhat happened this week\b",
    r"\bweek in review\b",
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
    r"\bsubscribe\b",
]

PROMO_PATTERNS = [
    r"\bc[oó]digo\b",
    r"\bcoupon\b",
    r"\bdesconto\b",
    r"\bpromo\b",
    r"\bapp\b",
    r"\bdownload\b",
    r"\bclube fashion\b",
]

MEME_PATTERNS = [
    r"\bmeme\b",
    r"\bviral\b",
    r"\bqual [ée] o vosso\b",
    r"\bwho else\b",
    r"\b😂\b",
    r"\b😭\b",
]

BLOCK_PATTERNS = [
    "429",
    "too many requests",
    "feedback required",
    "feedback_required",
    "checkpoint required",
    "challenge required",
    "please wait a few minutes",
    "try again later",
    "temporarily blocked",
]


class InstagramTemporaryBlock(Exception):
    pass


class ScheduledCooldown(Exception):
    pass


class DayBlockBuffer:
    def __init__(self, lang):
        self.lang = lang
        self._cache = {}

    def _get_block_id(self, date_str):
        month = int(date_str[5:7])
        day = int(date_str[8:10])
        return block_id_for_month_day(month, day)

    def add(self, post):
        block_id = self._get_block_id(post["date"])
        if block_id not in self._cache:
            self._cache[block_id] = load_block(self.lang, block_id)
        self._cache[block_id].append(post)

    def flush_all(self):
        for block_id, posts in self._cache.items():
            save_block(self.lang, block_id, posts)
            print(f"  [{self.lang}] Guardado {block_path(self.lang, block_id)} ({len(posts)} posts neste bloco)")
        self._cache.clear()

    def dirty_blocks(self):
        return list(self._cache.keys())


def now_local():
    return datetime.now().astimezone()


def format_local(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def load_progress_state():
    if not os.path.exists(PROGRESS_STATE_FILE):
        return {}
    with open(PROGRESS_STATE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_progress_state(state):
    with open(PROGRESS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clear_progress_state():
    save_progress_state(
        {
            "status": "idle",
            "updated_at": now_local().isoformat(),
        }
    )


def sanitize_profile_name(profile_name):
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", profile_name)


def resume_state_path(lang, profile_name, magic):
    safe_profile = sanitize_profile_name(profile_name)
    return os.path.join(RESUME_DIR, lang, f"{safe_profile}_{magic}.json")


def load_resume_iterator(_context, path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return instaloader.FrozenNodeIterator(**json.load(f))


def save_resume_iterator(frozen_iterator, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(frozen_iterator._asdict(), f, ensure_ascii=False, indent=2)


def build_running_state(lang, profile_name, last_post=None, status="running", blocked_at=None, resume_after=None, note=""):
    state = {
        "status": status,
        "lang": lang,
        "profile": profile_name,
        "updated_at": now_local().isoformat(),
        "note": note,
    }

    if last_post:
        state["last_shortcode"] = last_post.get("shortcodes", [""])[0]
        state["last_post_date"] = last_post.get("date", "")

    if blocked_at is not None:
        state["blocked_at"] = blocked_at.isoformat()
        state["blocked_at_readable"] = format_local(blocked_at)

    if resume_after is not None:
        state["resume_after"] = resume_after.isoformat()
        state["resume_after_readable"] = format_local(resume_after)

    return state


def maybe_wait_for_saved_block():
    state = load_progress_state()
    if state.get("status") not in {"blocked", "cooldown"}:
        return state

    resume_after_raw = state.get("resume_after")
    if not resume_after_raw:
        return state

    try:
        resume_after = datetime.fromisoformat(resume_after_raw)
    except ValueError:
        return state

    remaining_seconds = (resume_after - now_local()).total_seconds()
    if remaining_seconds > 0:
        print("\n" + "=" * 60)
        print("BLOQUEIO ANTERIOR DETETADO")
        print(f"Pausou em: {state.get('blocked_at_readable', state.get('blocked_at', 'desconhecido'))}")
        print(f"Retoma prevista: {state.get('resume_after_readable', resume_after_raw)}")
        print(f"A aguardar {int(remaining_seconds // 60)} minuto(s) antes de voltar a tentar...")
        print("=" * 60 + "\n")
        time.sleep(remaining_seconds)

    return state


def ordered_languages(progress_state):
    blocked_lang = progress_state.get("lang")
    if blocked_lang in PROFILES:
        return [blocked_lang] + [lang for lang in PROFILES if lang != blocked_lang]
    return list(PROFILES.keys())


def ordered_profiles(lang, profiles, progress_state):
    if progress_state.get("lang") != lang:
        return profiles

    blocked_profile = progress_state.get("profile")
    if blocked_profile not in profiles:
        return profiles

    start_idx = profiles.index(blocked_profile)
    return profiles[start_idx:]


def is_instagram_block_error(error):
    message = str(error).casefold()
    return any(pattern in message for pattern in BLOCK_PATTERNS)


def normalize_caption(text):
    return " ".join((text or "").split())


def count_hashtags(text):
    return len(re.findall(r"(?<!\w)#\w+", text))


def has_any_pattern(text, patterns):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def detect_content_flags(caption, media_count, profile_name):
    clean_caption = normalize_caption(caption)
    lowered = clean_caption.casefold()
    flags = []

    if media_count > 1:
        flags.append("carousel")
    if not clean_caption:
        flags.append("empty_caption")
    if len(clean_caption) < 120:
        flags.append("short_caption")
    if count_hashtags(clean_caption) >= 5:
        flags.append("hashtag_heavy")
    if has_any_pattern(lowered, ROUNDUP_PATTERNS):
        flags.append("roundup_caption")
    if re.search(r"\b(esta semana|this week|week in review)\b", lowered, flags=re.IGNORECASE):
        flags.append("weekly_recap")
    if has_any_pattern(lowered, CTA_PATTERNS):
        flags.append("call_to_action")
    if has_any_pattern(lowered, PROMO_PATTERNS):
        flags.append("promo_caption")
    if profile_name in LIGHTWEIGHT_PROFILES or has_any_pattern(clean_caption, MEME_PATTERNS):
        flags.append("internet_culture_signal")
    if media_count > 1 and len(clean_caption) < 260:
        flags.append("carousel_low_context")

    return sorted(set(flags))


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


def extract_media_metadata(post):
    primary_image_url = post.url
    video_url = post.video_url if post.is_video else None
    slide_urls = []
    slide_video_urls = []
    media_type = "video" if post.is_video else "image"
    media_count = getattr(post, "mediacount", 1) or 1

    if getattr(post, "typename", "") == "GraphSidecar":
        media_type = "carousel"
        try:
            for node in post.get_sidecar_nodes():
                slide_urls.append(node.display_url)
                slide_video_urls.append(node.video_url if node.is_video else "")
            if slide_urls:
                primary_image_url = slide_urls[0]
            if slide_video_urls and slide_video_urls[0]:
                video_url = slide_video_urls[0]
        except Exception:
            slide_urls = [post.url]
            slide_video_urls = [video_url or ""]
    else:
        slide_urls = [post.url]
        slide_video_urls = [video_url or ""]

    return {
        "media_type": media_type,
        "media_count": max(media_count, len(slide_urls) or 1),
        "is_video": bool(post.is_video),
        "primary_image_url": primary_image_url,
        "video_url": video_url or "",
        "slide_urls": slide_urls,
        "slide_video_urls": slide_video_urls,
    }


def translate_caption_if_needed(caption, lang, profile_name):
    if lang != "en" or profile_name != "geopoliticahoje" or not caption:
        return caption

    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "pt",
                "tl": "en",
                "dt": "t",
                "q": caption[:1500],
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        segments = payload[0] if isinstance(payload, list) and payload else []
        translated = "".join(
            segment[0]
            for segment in segments
            if isinstance(segment, list) and segment and isinstance(segment[0], str)
        )
        if not translated:
            raise ValueError("resposta de tradução sem texto")
        return translated
    except Exception as exc:
        print(f"  Erro ao traduzir: {exc}")
        return caption


def build_post_record(post, lang, profile_name):
    caption = translate_caption_if_needed(post.caption or "", lang, profile_name)
    caption = normalize_caption(caption)
    media = extract_media_metadata(post)
    flags = detect_content_flags(caption, media["media_count"], profile_name)

    needs_enrichment = (
        media["media_count"] > 1
        or "roundup_caption" in flags
        or "weekly_recap" in flags
        or "carousel_low_context" in flags
        or "call_to_action" in flags
        or "promo_caption" in flags
        or "empty_caption" in flags
    )

    return {
        "shortcodes": [post.shortcode],
        "date": post.date_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "global_context": caption,
        "raw_caption": caption,
        "image_url": media["primary_image_url"],
        "source_platform": "instagram",
        "source_profile": profile_name,
        "source_url": f"https://www.instagram.com/p/{post.shortcode}/",
        "media_type": media["media_type"],
        "media_count": media["media_count"],
        "is_video": media["is_video"],
        "video_url": media["video_url"],
        "slide_urls": media["slide_urls"],
        "slide_video_urls": media["slide_video_urls"],
        "content_flags": flags,
        "content_mode": infer_content_mode(flags, media["media_type"]),
        "needs_enrichment": needs_enrichment,
        "enrichment_status": "pending" if needs_enrichment else "not_needed",
    }


def init_instaloader():
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
        try:
            print(f"A carregar sessão guardada a partir de {session_file}...")
            insta_user = os.environ.get("INSTA_USERNAME", "imported_session")
            loader.load_session_from_file(insta_user, session_file)
            print("Sessão carregada com sucesso.")

            username_logado = loader.test_login()
            if not username_logado:
                raise RuntimeError("A sessão expirou ou foi invalidada pelo Instagram.")
            print(f"Sessão validada! Ligado como: {username_logado}")
            return loader
        except Exception as exc:
            print(f"Erro ao carregar a sessão: {exc}")
            print("A continuar de forma anónima (poderá sofrer bloqueios).")
            return loader

    insta_user = os.environ.get("INSTA_USERNAME")
    insta_pass = os.environ.get("INSTA_PASSWORD")
    if insta_user and insta_pass:
        try:
            print(f"A iniciar sessão direta com: {insta_user}...")
            loader.login(insta_user, insta_pass)
            print("Sessão iniciada com sucesso.")
            return loader
        except Exception as exc:
            print(f"Erro ao iniciar sessão direta: {exc}")
            if "checkpoint required" in str(exc).casefold():
                print("Corre 'python create_session.py' no teu computador local.")
            print("A continuar de forma anónima.")

    print("Aviso: sessão não configurada. A extração anónima tem alta probabilidade de falhar.")
    return loader


def wait_and_retry_after_block(lang, profile_name, buffer, existing_shortcodes, last_post):
    return pause_before_retry(
        lang=lang,
        profile_name=profile_name,
        buffer=buffer,
        existing_shortcodes=existing_shortcodes,
        last_post=last_post,
        reason_status="blocked",
        reason_label="O INSTAGRAM BLOQUEOU TEMPORARIAMENTE A CONTA / SESSÃO",
        note="Instagram bloqueou temporariamente a conta/sessão. O scraper vai retomar sozinho.",
        wait_minutes=BLOCK_RETRY_MINUTES,
    )


def pause_before_retry(lang, profile_name, buffer, existing_shortcodes, last_post, reason_status, reason_label, note, wait_minutes):
    blocked_at = now_local()
    resume_after = blocked_at + timedelta(minutes=wait_minutes)
    save_progress_state(
        build_running_state(
            lang,
            profile_name,
            last_post=last_post,
            status=reason_status,
            blocked_at=blocked_at,
            resume_after=resume_after,
            note=note,
        )
    )

    print("\n" + "=" * 60)
    print(reason_label)
    print(f"Parou em: {format_local(blocked_at)}")
    print(f"Vai retomar em: {format_local(resume_after)}")
    print("A guardar progresso antes da pausa...")
    print("=" * 60 + "\n")

    if buffer.dirty_blocks():
        buffer.flush_all()

    wait_seconds = max(0, (resume_after - now_local()).total_seconds())
    time.sleep(wait_seconds)

    print(f"[{lang}] A retomar automaticamente o perfil '{profile_name}'.")
    return load_all_shortcodes(lang)


def scrape_profiles():
    progress_state = maybe_wait_for_saved_block()
    loader = init_instaloader()
    summary = {"success": [], "failed": []}

    for lang in ordered_languages(progress_state):
        profiles = ordered_profiles(lang, PROFILES[lang], progress_state)
        ensure_lang_dir(lang)

        print(f"\n[{lang}] A indexar shortcodes existentes...")
        existing_shortcodes = load_all_shortcodes(lang)
        print(f"[{lang}] {len(existing_shortcodes)} shortcodes únicos já na base de dados.")

        buffer = DayBlockBuffer(lang)
        interrupted = False

        try:
            for profile_name in profiles:
                print(f"\n[{lang}] A extrair perfil: {profile_name}")
                profile_new_count = 0
                consecutive_existing_count = 0
                last_post_record = None

                while True:
                    try:
                        profile = instaloader.Profile.from_username(loader.context, profile_name)
                        post_iterator = profile.get_posts()
                        processed_since_resume = 0

                        with instaloader.resumable_iteration(
                            context=loader.context,
                            iterator=post_iterator,
                            load=load_resume_iterator,
                            save=save_resume_iterator,
                            format_path=lambda magic: resume_state_path(lang, profile_name, magic),
                            check_bbd=False,
                        ) as (is_resuming, start_index):
                            if is_resuming:
                                print(f"  A retomar cursor guardado do perfil '{profile_name}' no índice {start_index}.")

                            for post in post_iterator:
                                processed_since_resume += 1

                                if post.date_utc.year < OLDEST_YEAR:
                                    print(f"  Atingido o ano {post.date_utc.year}. A parar.")
                                    break

                                if post.shortcode in existing_shortcodes:
                                    consecutive_existing_count += 1
                                    sys.stdout.write(
                                        f"\r  [A verificar] Já existe: {post.date_utc.strftime('%Y-%m-%d')} "
                                        f"({consecutive_existing_count}/{CONSECUTIVE_EXISTING_LIMIT} saltados) "
                                    )
                                    sys.stdout.flush()

                                    if not HISTORICAL_BACKFILL_MODE and consecutive_existing_count >= CONSECUTIVE_EXISTING_LIMIT:
                                        print("\n  [Concluído] 15 posts consecutivos existentes. Sincronizado.")
                                        break

                                    if PROFILE_POSTS_BEFORE_COOLDOWN > 0 and processed_since_resume >= PROFILE_POSTS_BEFORE_COOLDOWN:
                                        raise ScheduledCooldown("Limite de posts desta sessão atingido para prevenção de bloqueio.")
                                    continue

                                if consecutive_existing_count > 0:
                                    print("")
                                consecutive_existing_count = 0

                                post_data = build_post_record(post, lang, profile_name)
                                last_post_record = post_data

                                buffer.add(post_data)
                                existing_shortcodes.add(post.shortcode)
                                profile_new_count += 1

                                save_progress_state(
                                    build_running_state(
                                        lang,
                                        profile_name,
                                        last_post=last_post_record,
                                        status="running",
                                        note="Extração em curso.",
                                    )
                                )

                                sys.stdout.write(
                                    f"\r  Extraído: {post.shortcode} | {post.date_utc.strftime('%Y-%m-%d')} "
                                    f"| {profile_name} (novos: {profile_new_count})   "
                                )
                                sys.stdout.flush()

                                if FLUSH_EVERY_NEW_POSTS > 0 and profile_new_count % FLUSH_EVERY_NEW_POSTS == 0:
                                    print("\n  A guardar checkpoint intermédio...")
                                    buffer.flush_all()

                                if PROFILE_POSTS_BEFORE_COOLDOWN > 0 and processed_since_resume >= PROFILE_POSTS_BEFORE_COOLDOWN:
                                    raise ScheduledCooldown("Limite de posts desta sessão atingido para prevenção de bloqueio.")

                                time.sleep(random.uniform(1.0, 3.0))

                        print("")
                        print(f"  [{lang}] Perfil '{profile_name}' concluído ({profile_new_count} novos). A guardar no disco...")
                        buffer.flush_all()
                        save_progress_state(
                            build_running_state(
                                lang,
                                profile_name,
                                last_post=last_post_record,
                                status="completed_profile",
                                note="Perfil concluído com sucesso.",
                            )
                        )
                        summary["success"].append(f"{profile_name} ({lang})")
                        break

                    except KeyboardInterrupt:
                        raise

                    except ScheduledCooldown:
                        existing_shortcodes = pause_before_retry(
                            lang=lang,
                            profile_name=profile_name,
                            buffer=buffer,
                            existing_shortcodes=existing_shortcodes,
                            last_post=last_post_record,
                            reason_status="cooldown",
                            reason_label="PAUSA PREVENTIVA PARA EVITAR BLOQUEIO DO INSTAGRAM",
                            note="Pausa preventiva por volume elevado de posts processados no mesmo perfil.",
                            wait_minutes=PROFILE_COOLDOWN_MINUTES,
                        )
                        continue

                    except Exception as exc:
                        if is_instagram_block_error(exc):
                            print(f"\n[Aviso] Instaloader bloqueado ao extrair perfil '{profile_name}'. A tentar Instagrapi Mobile API...")
                            try:
                                from instagram_mobile_fallback import get_fallback_client, InstagrapiPostWrapper
                                cl = get_fallback_client()
                                if cl:
                                    user_id = cl.user_id_from_username(profile_name)

                                    amount_to_fetch = 250 if HISTORICAL_BACKFILL_MODE else 50
                                    print(f"  [Fallback] A obter {amount_to_fetch} posts via Instagrapi...")
                                    medias = cl.user_medias(user_id, amount=amount_to_fetch)
                                    
                                    fallback_new_count = 0
                                    for media in medias:
                                        wrapped_post = InstagrapiPostWrapper(media)
                                        
                                        if wrapped_post.date_utc.year < OLDEST_YEAR:
                                            continue
                                            
                                        if wrapped_post.shortcode in existing_shortcodes:
                                            continue
                                            
                                        post_data = build_post_record(wrapped_post, lang, profile_name)
                                        last_post_record = post_data
                                        
                                        buffer.add(post_data)
                                        existing_shortcodes.add(wrapped_post.shortcode)
                                        profile_new_count += 1
                                        fallback_new_count += 1
                                        
                                        sys.stdout.write(
                                            f"\r  [Instagrapi] Extraído: {wrapped_post.shortcode} | {wrapped_post.date_utc.strftime('%Y-%m-%d')} "
                                            f"| {profile_name} (novos: {profile_new_count})   "
                                        )
                                        sys.stdout.flush()
                                        
                                        if FLUSH_EVERY_NEW_POSTS > 0 and profile_new_count % FLUSH_EVERY_NEW_POSTS == 0:
                                            buffer.flush_all()
                                            
                                    print(f"\n  [Instagrapi] Concluído fallback para '{profile_name}'. Adicionados {fallback_new_count} posts.")
                                    buffer.flush_all()
                                    save_progress_state(
                                        build_running_state(
                                            lang,
                                            profile_name,
                                            last_post=last_post_record,
                                            status="completed_profile",
                                            note="Perfil concluído via fallback Instagrapi.",
                                        )
                                    )
                                    summary["success"].append(f"{profile_name} ({lang})")
                                    break
                            except Exception as fallback_exc:
                                print(f"  [Erro] Falha também no fallback do Instagrapi: {fallback_exc}")
                                
                            existing_shortcodes = wait_and_retry_after_block(
                                lang,
                                profile_name,
                                buffer,
                                existing_shortcodes,
                                last_post_record,
                            )
                            consecutive_existing_count = 0
                            continue

                        print(f"\n  Erro ao extrair {profile_name}: {exc}")
                        summary["failed"].append(f"{profile_name} ({lang}): {exc}")
                        if buffer.dirty_blocks():
                            buffer.flush_all()
                        break

        except KeyboardInterrupt:
            interrupted = True
            print("\n\n" + "=" * 60)
            print("EXTRAÇÃO PAUSADA MANUALMENTE (CTRL+C)")
            blocks_dirty = buffer.dirty_blocks()
            if blocks_dirty:
                print(f"A guardar dados ({len(blocks_dirty)} blocos modificados)...")
                buffer.flush_all()
                print("Dados guardados com segurança.")
            else:
                print("Sem dados novos por guardar.")
            print("=" * 60 + "\n")
            sys.exit(0)

        if not interrupted:
            buffer.flush_all()
            print(f"[{lang}] Extração concluída para os perfis planeados.")

    clear_progress_state()

    print("\n--- RELATÓRIO FINAL ---")
    print(f"Sucesso ({len(summary['success'])}):")
    for item in summary["success"]:
        print(f"  - {item}")
    print(f"\nFalha ({len(summary['failed'])}):")
    for item in summary["failed"]:
        print(f"  - {item}")
    print("-----------------------")


if __name__ == "__main__":
    scrape_profiles()
