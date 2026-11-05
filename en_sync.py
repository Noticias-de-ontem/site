"""Sincronização automática de paridade PT -> EN e validação de URLs de notícias."""

import json
import re
import shutil
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from nvidia_client import NvidiaKeyPool, load_nvidia_api_keys
from social_networks import (
    normalize_networks,
    social_link_cta,
    translate_category_to_en,
)

ROOT = Path(__file__).resolve().parent

_ASSET_EXT_RE = re.compile(
    r"\.(?:jpe?g|png|gif|webp|svg|bmp|ico|tiff?|mp4|mp3|wav|ogg|webm|pdf|txt|csv|xml|json|rss|atom|css|js|woff2?|ttf|eot|zip|rar|gz)(?:[?#]|$)",
    re.IGNORECASE,
)
_WAYBACK_ASSET_MOD_RE = re.compile(r"/wayback/\d{8,14}(?:im_|js_|cs_|oe_|fw_)/", re.IGNORECASE)
_BLOCKED_ARTICLE_HOSTS = (
    "instagram.com",
    "facebook.com",
    "fb.com",
    "twitter.com",
    "x.com",
    "t.co",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "ibb.co",
    "imgbb.com",
    "fbcdn.net",
    "cdninstagram.com",
    "openverse.org",
    "flickr.com",
    "staticflickr.com",
    "unsplash.com",
    "pexels.com",
    "pixabay.com",
    "news.google.",
    "google.com",
    "google.pt",
    "news.ycombinator.com",
    "linguateca.pt",
    "goodreads.com",
    "wsws.org",
)
_BLOCKED_URL_PATTERNS = (
    "/wp-json/",
    "/xmlrpc.php",
    "/feed/",
    "/feeds/",
    "updates_rss",
    "submitlink?",
    "/search?",
    "?s=",
    "/wiki/file:",
    "/wiki/ficheiro:",
    "/wiki/categoria:",
    "/wiki/category:",
    "/stockimages/",
)


def extract_inner_url(url):
    text = str(url or "").strip()
    match = re.search(r"arquivo\.pt/(?:wayback|noFrame/replay)/\d{8,14}[a-z_]*/(https?://.+)$", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return text


def is_valid_article_url(url):
    """Valida se um URL aponta para uma página HTML de notícia (e nunca imagem/asset/pesquisa)."""
    text = str(url or "").strip()
    if not text or not text.startswith(("http://", "https://")):
        return False
    if _WAYBACK_ASSET_MOD_RE.search(text):
        return False
    inner = extract_inner_url(text)
    lower_inner = inner.lower()
    if _ASSET_EXT_RE.search(lower_inner):
        return False
    for pattern in _BLOCKED_URL_PATTERNS:
        if pattern in lower_inner:
            return False
    parsed = urlparse(inner)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host.startswith(("static.", "cdn.", "img.", "images.", "media.", "assets.", "thumbs.")):
        return False
    for blocked in _BLOCKED_ARTICLE_HOSTS:
        if blocked.endswith("."):
            if blocked in host:
                return False
        elif host == blocked or host.endswith(f".{blocked}"):
            return False
    path = (parsed.path or "").strip("/")
    # Rejeitar homepages puras sem slug/caminho de artigo ou páginas de tag genéricas
    if not path:
        return False
    if re.match(r"^(?:tag|tags|topico|topicos|autor|author|categoria|category)(?:/|$)", path, flags=re.IGNORECASE):
        return False
    return True


def strip_caption_metadata(value):
    """Remove aviso histórico, CTAs (PT e EN) e hashtags, preservando os parágrafos narrativos."""
    text = str(value or "")
    patterns = [
        r"Este post apenas tem o objetivo de relembrar acontecimentos passados da hist[oó]ria,? nunca representando acontecimentos atuais\.?:?",
        r"Esta not[ií]cia [eé] de \d{4}\.?",
        r"This post is intended solely to recall past events in history,? never representing current events\.?:?",
        r"This (?:story|news) is from \d{4}\.?",
        r"🔗?\s*L[eê] a not[ií]cia completa (?:no link (?:da bio|na descri[cç][aã]o do perfil|do sobre do perfil|do perfil)|no site no sobre do perfil)\.?:?",
        r"🔗?\s*L[eê] mais no link da bio\.?:?",
        r"🔗?\s*Read the full story (?:via|at|on) (?:the link in (?:our )?(?:bio(?:/about section)?|profile(?: description)?)|the website in (?:our |the )?profile'?s About section)\.?:?",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"#\w+", "", text)
    paragraphs = [re.sub(r"[ \t]+", " ", chunk).strip() for chunk in re.split(r"\n\s*\n", text)]
    paragraphs = [p for p in paragraphs if p]
    return "\n\n".join(paragraphs).strip()


def format_platform_caption(caption, year, category, platform="instagram", lang="pt"):
    """Formata a legenda padrão com o aviso histórico e o CTA específico de cada rede e idioma."""
    narrative = strip_caption_metadata(caption)
    year_str = str(year or "").strip()
    cta = social_link_cta(platform=platform, lang=lang)

    if str(lang or "pt").strip().lower() == "pt":
        folded = unicodedata.normalize("NFKD", str(category or "")).encode("ASCII", "ignore").decode("utf-8")
        cat_tag = re.sub(r"[^a-zA-Z0-9]", "", folded).capitalize()
        if not cat_tag or cat_tag.lower() in ("atualidade", "noticia", "noticias"):
            cat_tag = "Portugal"
        elif cat_tag.lower() == "mundial":
            cat_tag = "Mundo"
        alert = (
            "Este post apenas tem o objetivo de relembrar acontecimentos passados da história "
            f"nunca representando acontecimentos atuais. Esta notícia é de {year_str}."
        )
        hashtags = f"#NoticiasDeOntem #ArquivoPT #{cat_tag}"
    else:
        en_cat = translate_category_to_en(category)
        cat_tag = re.sub(r"[^a-zA-Z0-9]", "", en_cat).capitalize() or "History"
        if cat_tag.lower() == "news":
            cat_tag = "Portugal"
        alert = (
            "This post is intended solely to recall past events in history, "
            f"never representing current events. This story is from {year_str}."
        )
        hashtags = f"#YesterdaysNews #ArquivoPT #{cat_tag}"

    if narrative:
        return f"{narrative}\n\n{alert}\n\n{cta}\n\n{hashtags}"
    return f"{alert}\n\n{cta}\n\n{hashtags}"


def _pick_en_highlight(title_en, en_candidate=""):
    title_clean = str(title_en or "").strip()
    cand = str(en_candidate or "").strip()
    if cand and cand.lower() in title_clean.lower() and len(cand.split()) <= 3:
        return cand
    words = title_clean.split()
    stopwords = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from", "and", "or", "as", "is"}
    meaningful = []
    for w in words:
        clean_w = re.sub(r"[^\w]", "", w).lower()
        if clean_w and clean_w not in stopwords:
            meaningful.append(w)
            if len(meaningful) >= 2:
                break
        elif meaningful:
            break
    if meaningful:
        return " ".join(meaningful)
    return words[0] if words else ""


def _resolve_local_background(pt_entry, pt_opt):
    candidates = [
        pt_opt.get("local_background_path") or "",
        pt_entry.get("manual_background_url") or "",
    ]
    for raw in candidates:
        val = str(raw or "").strip()
        if not val or val.startswith(("http://", "https://")):
            continue
        norm = val.replace("\\", "/")
        direct = Path(norm)
        if direct.is_file():
            return str(direct)
        rel = ROOT / norm
        if rel.is_file():
            return str(rel)
        if "images/" in norm:
            sub = ROOT / norm[norm.index("images/") :]
            if sub.is_file():
                return str(sub)
    return ""


def ensure_option_en_fields(option, pool=None, need_caption_en=False):
    """Garante que uma opção PT tem title_en, summary_en, body_en e justification_en completos."""
    if not isinstance(option, dict) or not option.get("title"):
        return False
    pool = pool or NvidiaKeyPool(load_nvidia_api_keys())
    relevance = option.get("relevance") if isinstance(option.get("relevance"), dict) else {}

    has_title_en = bool(str(option.get("title_en") or "").strip())
    has_summary_en = bool(str(option.get("summary_en") or "").strip())
    has_body_en = len(str(option.get("body_en") or "").split()) >= 120
    has_just_en = bool(str(relevance.get("justification_en") or "").strip())
    has_caption_en = bool(str(option.get("caption_narrative_en") or "").strip())

    if has_title_en and has_summary_en and has_body_en and (has_just_en or not relevance.get("justification")) and (not need_caption_en or has_caption_en):
        return False

    if not pool.has_keys():
        return False

    level = relevance.get("level") or 4
    word_target = {1: "500-700", 2: "500-700", 3: "350-450", 4: "220-320", 5: "180-240"}.get(level, "220-320")
    pt_body = str(option.get("body") or "").strip()
    pt_caption = strip_caption_metadata(option.get("caption_instagram") or option.get("caption") or "")
    pt_just = str(relevance.get("justification") or "").strip()

    prompt = f"""Translate and adapt this historical Portuguese news item into natural, idiomatic United States English (journalistic tone, factual, never literal word-for-word translation).
Pretend the social caption is published on the day it happened (never say "on this day" or "years ago", integrate the year {option.get("year")} naturally inside the narrative).
Never invent facts, quotes, or numbers not supported by the Portuguese text.

Year: {option.get("year")}
Category: {option.get("category")}
Portuguese Headline: {option.get("title")}
Portuguese Subtitle/Overlay: {option.get("overlay_description") or option.get("summary")}
Portuguese Social Caption Narrative: {pt_caption}
Portuguese Relevance Justification: {pt_just}
Portuguese Article Body:
{pt_body or pt_caption}

Return ONLY valid JSON with these exact keys:
{{
  "title_en": "Sharp, natural US English headline (max 12 words, no year at the end unless essential)",
  "highlight_en": "1 key word that appears verbatim inside title_en (or empty string)",
  "summary_en": "Natural US English subtitle/overlay sentence (10-18 words, no hashtags, no CTA)",
  "caption_narrative_en": "Engaging 2-4 sentence social media summary in US English weaving in the year {option.get('year')} naturally (no disclaimer, no CTA, no hashtags)",
  "justification_en": "1-2 short sentences in US English translating/adapting the relevance justification (max 28 words)",
  "body_en": "Complete factual journalistic article in US English ({word_target} words, minimum 180 words, separated into 3-5 paragraphs with \\n\\n)"
}}"""

    changed = False
    for attempt in range(3):
        try:
            raw = pool.chat_json(prompt, timeout=180)
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                continue
            if not has_title_en and data.get("title_en"):
                option["title_en"] = str(data["title_en"]).strip()
                changed = True
            if data.get("highlight_en") and not option.get("highlight_text_en"):
                option["highlight_text_en"] = _pick_en_highlight(option.get("title_en"), data.get("highlight_en"))
            if not has_summary_en and data.get("summary_en"):
                option["summary_en"] = str(data["summary_en"]).strip()
                changed = True
            if data.get("caption_narrative_en"):
                option["caption_narrative_en"] = str(data["caption_narrative_en"]).strip()
                changed = True
            if data.get("justification_en") and isinstance(relevance, dict):
                relevance["justification_en"] = str(data["justification_en"]).strip()
                option["relevance"] = relevance
                changed = True
            body_en = str(data.get("body_en") or "").strip()
            min_words = 120 if attempt < 2 else 80
            if not has_body_en and len(body_en.split()) >= min_words:
                option["body_en"] = body_en
                changed = True
            if option.get("title_en") and option.get("summary_en") and len(str(option.get("body_en") or "").split()) >= min_words:
                break
        except Exception as exc:
            print(f"[en_sync] Tradução IA falhou (tentativa {attempt + 1}/3) para '{option.get('title', '')[:50]}': {exc}")
            pool.rotate()
    return changed


def sync_approved_pt_to_en(
    pending_posts,
    pool=None,
    render_images=True,
    mirror_dir=None,
    site_origin="https://www.noticiasdeontem.pt",
):
    """Garante que todo post PT aprovado tem um par EN aprovado completo e com imagem espelhada."""
    if not isinstance(pending_posts, list):
        return 0

    pool = pool or NvidiaKeyPool(load_nvidia_api_keys())
    mirror_path = Path(mirror_dir) if mirror_dir else (ROOT / "site" / "images" / "approved")
    by_id = {str(p.get("id") or ""): p for p in pending_posts if isinstance(p, dict) and p.get("id")}
    synced_count = 0

    pt_approved = [
        p for p in list(pending_posts)
        if isinstance(p, dict)
        and str(p.get("lang") or "pt").strip().lower() == "pt"
        and str(p.get("status") or "").strip().lower() == "approved"
    ]

    for pt_entry in pt_approved:
        date_str = str(pt_entry.get("date") or "").strip()
        slot = pt_entry.get("slot", 1)
        if not date_str:
            continue
        options = pt_entry.get("options") or []
        sel_idx = int(pt_entry.get("selected_option", 0) or 0)
        if not options or sel_idx < 0 or sel_idx >= len(options):
            continue
        pt_opt = options[sel_idx]

        # Normalizar CTAs PT nas opções aprovadas
        pt_year = pt_opt.get("year", "")
        pt_cat = pt_opt.get("category", "ATUALIDADE")
        pt_opt["caption_instagram"] = format_platform_caption(
            pt_opt.get("caption_instagram") or pt_opt.get("caption") or "",
            pt_year,
            pt_cat,
            platform="instagram",
            lang="pt",
        )
        pt_opt["caption_facebook"] = format_platform_caption(
            pt_opt.get("caption_facebook") or pt_opt.get("caption") or "",
            pt_year,
            pt_cat,
            platform="facebook",
            lang="pt",
        )
        pt_opt["caption"] = pt_opt["caption_instagram"]

        # Garantir tradução EN completa
        ensure_option_en_fields(pt_opt, pool=pool, need_caption_en=True)

        title_en = str(pt_opt.get("title_en") or "").strip()
        summary_en = str(pt_opt.get("summary_en") or "").strip()
        if not title_en or not summary_en:
            print(f"[en_sync] AVISO: {pt_entry.get('id')} sem title_en/summary_en; a saltar criação de par EN para não publicar texto PT.")
            continue

        en_id = f"en_{date_str}_{slot}"
        existing_en = by_id.get(en_id)
        if existing_en and str(existing_en.get("status") or "").strip().lower() == "published":
            continue

        existing_en_opt = {}
        if existing_en and (existing_en.get("options") or []):
            en_sel = int(existing_en.get("selected_option", 0) or 0)
            if 0 <= en_sel < len(existing_en["options"]):
                existing_en_opt = existing_en["options"][en_sel] or {}

        en_category = translate_category_to_en(pt_cat)
        pt_networks = pt_opt.get("networks")
        en_networks = normalize_networks(
            pt_networks,
            en_category,
            (pt_opt.get("relevance") or {}).get("level"),
        )
        # Se PT tem facebook, EN tem obrigatoriamente facebook (paridade total)
        if isinstance(pt_networks, list):
            for net in pt_networks:
                if net in ("instagram", "facebook") and net not in en_networks:
                    en_networks.append(net)

        narrative_en = (
            str(pt_opt.get("caption_narrative_en") or "").strip()
            or strip_caption_metadata(existing_en_opt.get("caption_instagram") or existing_en_opt.get("caption") or "")
            or summary_en
        )
        caption_ig_en = format_platform_caption(narrative_en, pt_year, en_category, platform="instagram", lang="en")
        caption_fb_en = format_platform_caption(narrative_en, pt_year, en_category, platform="facebook", lang="en")

        highlight_en = _pick_en_highlight(
            title_en,
            pt_opt.get("highlight_text_en") or existing_en_opt.get("highlight_text") or "",
        )
        local_bg = _resolve_local_background(pt_entry, pt_opt)
        manual_bg_source = (
            local_bg
            or str(pt_entry.get("manual_background_url") or "").strip()
            or (existing_en.get("manual_background_url") if existing_en else "")
            or ""
        )
        layout_pref = (
            str(pt_entry.get("layout_override") or "").strip()
            or (str(existing_en.get("layout_override") or "").strip() if existing_en else "")
            or str(pt_opt.get("layout_preference") or "template_1").strip()
        )
        breaking = bool(pt_opt.get("breaking_candidate", False)) or layout_pref == "breaking"

        en_relevance = json.loads(json.dumps(pt_opt.get("relevance") or {}))
        if en_relevance.get("justification_en"):
            en_relevance["justification"] = en_relevance["justification_en"]

        article_url = str(pt_opt.get("article_url") or existing_en_opt.get("article_url") or "").strip()
        if article_url and not is_valid_article_url(article_url):
            article_url = ""

        en_image_url = str(existing_en_opt.get("image_url") or "").strip()
        en_local_image_path = str(existing_en_opt.get("local_image_path") or "").strip()
        en_mirror_file = mirror_path / f"{en_id}.jpg"
        expected_mirror_url = f"{site_origin}/images/approved/{en_id}.jpg"

        needs_render = render_images and (
            not en_mirror_file.is_file()
            or en_image_url != expected_mirror_url
            or existing_en_opt.get("title") != title_en
            or existing_en_opt.get("overlay_description") != summary_en
            or existing_en_opt.get("category") != en_category
        )

        if needs_render:
            mirror_path.mkdir(parents=True, exist_ok=True)
            review_en_dir = ROOT / "images" / "review" / "en"
            review_en_dir.mkdir(parents=True, exist_ok=True)
            temp_render_file = review_en_dir / f"{en_id}.jpg"
            try:
                from PIL import Image
                from post_templates import TARGET_SIZE, create_image_with_text, fit_and_crop

                bg_image = None
                if local_bg and Path(local_bg).is_file():
                    with Image.open(local_bg) as raw_bg:
                        bg_image = fit_and_crop(raw_bg.convert("RGBA"), TARGET_SIZE)

                render_details = create_image_with_text(
                    en_category,
                    title_en,
                    "en",
                    output_path=str(temp_render_file),
                    description_to_draw=summary_en,
                    highlight_text=highlight_en,
                    layout_name=layout_pref if layout_pref != "auto" else "auto",
                    layout_preference=str(pt_opt.get("layout_preference") or "template_1"),
                    breaking_candidate=breaking,
                    background_query=str(pt_opt.get("image_theme") or title_en),
                    background_image=bg_image,
                    manual_background_url="" if bg_image is not None else manual_bg_source,
                    return_details=True,
                    year=pt_year,
                    relevance_level=en_relevance.get("level"),
                )
                if temp_render_file.is_file() and temp_render_file.stat().st_size > 1024:
                    shutil.copyfile(temp_render_file, en_mirror_file)
                    en_image_url = expected_mirror_url
                    en_local_image_path = f"site/images/approved/{en_id}.jpg"
                    extra_bg = ROOT / "images" / "backgrounds" / f"{en_id}-fundo.jpg"
                    if local_bg and extra_bg.is_file() and Path(local_bg).resolve() != extra_bg.resolve():
                        extra_bg.unlink(missing_ok=True)
                    elif isinstance(render_details, dict) and render_details.get("background_local_path") and not local_bg:
                        local_bg = str(render_details["background_local_path"]).replace("\\", "/")
            except Exception as exc:
                print(f"[en_sync] ERRO ao renderizar capa EN {en_id}: {exc}")

        en_opt = {
            "category": en_category,
            "title": title_en,
            "title_en": title_en,
            "highlight_text": highlight_en,
            "overlay_description": summary_en,
            "caption": caption_ig_en,
            "caption_instagram": caption_ig_en,
            "caption_facebook": caption_fb_en,
            "year": str(pt_year),
            "summary": summary_en,
            "summary_en": summary_en,
            "body": str(pt_opt.get("body_en") or ""),
            "body_en": str(pt_opt.get("body_en") or ""),
            "image_theme": str(pt_opt.get("image_theme") or title_en),
            "layout_preference": layout_pref if layout_pref != "breaking" else str(pt_opt.get("layout_preference") or "template_1"),
            "breaking_candidate": breaking,
            "networks": en_networks,
            "relevance": en_relevance,
            "article_url": article_url,
            "source_profile": str(pt_opt.get("source_profile") or pt_entry.get("source_profile") or ""),
            "source_platform": str(pt_opt.get("source_platform") or ""),
            "image_url": en_image_url,
            "image_delete_url": "",
            "local_image_path": en_local_image_path,
            "background_source_url": str(pt_opt.get("background_source_url") or ""),
            "local_background_path": str(local_bg).replace("\\", "/") if local_bg else "",
        }

        new_en_entry = {
            "id": en_id,
            "date": date_str,
            "slot": slot,
            "lang": "en",
            "selected_option": 0,
            # Quando a capa EN já foi renderizada e espelhada em site/images/approved/,
            # limpamos layout_override e manual_background_url para o publisher usar
            # diretamente a imagem espelhada sem depender do ImgBB na hora de publicar.
            "layout_override": "" if en_image_url == expected_mirror_url else layout_pref,
            "theme_suggestion": "",
            "manual_background_url": "" if en_image_url == expected_mirror_url else manual_bg_source,
            "review_action": "",
            "review_note": f"Synced from {pt_entry.get('id')}",
            "status": "approved",
            "generated_month": pt_entry.get("generated_month") or date_str[:7],
            "source_profile": str(pt_entry.get("source_profile") or pt_opt.get("source_profile") or ""),
            "external_suggestions": [],
            "options": [en_opt],
        }
        if existing_en:
            for keep_key in ("instagram_id", "instagram_url", "instagram_story_id", "facebook_id", "facebook_url", "facebook_story_id", "published_at"):
                if existing_en.get(keep_key):
                    new_en_entry[keep_key] = existing_en[keep_key]
            idx_in_list = pending_posts.index(existing_en)
            pending_posts[idx_in_list] = new_en_entry
        else:
            pending_posts.append(new_en_entry)
        by_id[en_id] = new_en_entry
        synced_count += 1
        print(f"[en_sync] Sincronizado {en_id} <- {pt_entry.get('id')} (networks={en_networks}, img={bool(en_image_url)})")

    return synced_count
