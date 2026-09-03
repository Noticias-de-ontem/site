import ast
import hashlib
import html
import json
import os
import re
import shutil
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
SITE_DIR = ROOT / "site"
DATA_DIR = SITE_DIR / "data"
ASSETS_DIR = SITE_DIR / "assets"
POST_ASSETS_DIR = ASSETS_DIR / "posts"
BANNER_ASSETS_DIR = ASSETS_DIR / "banners"
PENDING_POSTS_FILE = ROOT / "pending_posts.json"
IMGBB_UPLOADS_FILE = ROOT / "imgbb_uploads.json"
ARQUIVO_CDXJ_DIR = ROOT / "arquivo_cdxj"
ARQUIVO_CDXJ_STATE_FILE = ROOT / "arquivo_cdxj_state.json"
SOCIAL_METRICS_FILE = ROOT / "social_metrics.json"
CDXJ_BUILDER_FILE = ROOT / "build_arquivo_cdxj_index.py"
INSTAGRAM_SCRAPER_FILE = ROOT / "scraper.py"
ICON_SOURCE = ROOT / "images" / "noticias_de_ontem_icon.png"
ICON_ASSET = "icon.png"
DEFAULT_PUBLIC_URL = "https://luisflmaximo.github.io/Noticias-de-ontem-pt"
ARQUIVO_BLUE = (0, 84, 139)
ARQUIVO_BLUE_DARK = (0, 62, 103)
ARQUIVO_BLUE_LIGHT = (38, 126, 190)
WHITE = (255, 255, 255)
SOURCE_CREATED_YEARS = {
    "publico.pt": 1990,
    "expresso.pt": 1973,
    "cmjornal.pt": 1979,
    "sabado.pt": 2004,
    "rtp.pt": 1957,
    "observador.pt": 2014,
    "jn.pt": 1888,
    "dn.pt": 1864,
    "sicnoticias.pt": 2001,
    "noticiasaominuto.com": 2012,
    "record.pt": 1949,
    "ojogo.pt": 1985,
    "abola.pt": 1945,
    "caras.pt": 1995,
    "flash.pt": 2003,
    "tv7dias.pt": 1987,
    "holofote.pt": 1937,
    "selfie.iol.pt": 2017,
    "lux.iol.pt": 2001,
    "nit.pt": 2014,
    "timeout.pt": 2007,
    "blitz.pt": 1984,
    "mag.sapo.pt": 2016,
    "visao.pt": 1993,
    "exameinformatica.pt": 1995,
    "activa.pt": 1991,
    "maxima.pt": 1988,
}


def public_site_url():
    configured = clean_text(os.environ.get("SITE_PUBLIC_URL"))
    if configured:
        return configured
    space_id = clean_text(os.environ.get("HF_SPACE_ID"))
    if "/" in space_id:
        return f"https://{space_id.replace('/', '-')}.hf.space"
    return DEFAULT_PUBLIC_URL


def static_site_only():
    return str(os.environ.get("SITE_STATIC_ONLY", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def absolute_site_url(path=""):
    return f"{public_site_url().rstrip('/')}/{str(path or '').lstrip('/')}"


def seo_block(
    title,
    description,
    canonical_path,
    structured_data,
    image_path=f"assets/{ICON_ASSET}",
    index=True,
    og_type="website",
):
    canonical = absolute_site_url(canonical_path)
    image = absolute_site_url(image_path)
    robots = (
        "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"
        if index
        else "noindex,follow"
    )
    title_html = html.escape(clean_text(title), quote=True)
    description_html = html.escape(clean_text(description), quote=True)
    canonical_html = html.escape(canonical, quote=True)
    image_html = html.escape(image, quote=True)
    structured_json = json.dumps(structured_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return "\n".join(
        [
            "    <!-- SEO:START -->",
            f"    <title>{title_html}</title>",
            f'    <meta name="description" content="{description_html}">',
            f'    <meta name="robots" content="{robots}">',
            '    <meta name="author" content="Notícias de Ontem">',
            '    <meta name="theme-color" content="#0b567c">',
            f'    <link rel="canonical" href="{canonical_html}">',
            '    <meta property="og:site_name" content="Notícias de Ontem">',
            f'    <meta property="og:type" content="{html.escape(og_type, quote=True)}">',
            '    <meta property="og:locale" content="pt_PT">',
            f'    <meta property="og:title" content="{title_html}">',
            f'    <meta property="og:description" content="{description_html}">',
            f'    <meta property="og:url" content="{canonical_html}">',
            f'    <meta property="og:image" content="{image_html}">',
            f'    <meta property="og:image:alt" content="{title_html}">',
            '    <meta name="twitter:card" content="summary_large_image">',
            f'    <meta name="twitter:title" content="{title_html}">',
            f'    <meta name="twitter:description" content="{description_html}">',
            f'    <meta name="twitter:image" content="{image_html}">',
            f'    <script type="application/ld+json" id="structured-data">{structured_json}</script>',
            "    <!-- SEO:END -->",
        ]
    )


def with_seo(html_text, block):
    return re.sub(
        r"\s*<!-- SEO:START -->.*?<!-- SEO:END -->",
        f"\n{block}",
        html_text,
        count=1,
        flags=re.DOTALL,
    )

# The Arquivo.pt site filter matches host names, not every subdomain of a
# publication. Query both the bare and www hosts, plus the few historical
# hosts that are part of the same publication, so older results are not lost.
SOURCE_SEARCH_HOST_ALIASES = {
    "publico.pt": [
        "www.publico.pt",
        "publico.pt",
        "economia.publico.pt",
        "fugas.publico.pt",
        "jornal.publico.pt",
        "lifestyle.publico.pt",
        "blogues.publico.pt",
        "desporto.publico.pt",
        "p3.publico.pt",
        "imobiliario.publico.pt",
        "lazer.publico.pt",
        "ipsilon.publico.pt",
        "inimigo.publico.pt",
        "cinecartaz.publico.pt",
        "m.publico.pt",
    ],
    "expresso.pt": [
        "www.expresso.pt",
        "expresso.pt",
        "expresso.sapo.pt",
        "economia.expresso.pt",
    ],
    "sicnoticias.pt": ["www.sicnoticias.pt", "sicnoticias.pt", "sicnoticias.sapo.pt"],
    "rtp.pt": ["www.rtp.pt", "rtp.pt", "ww1.rtp.pt", "www0.rtp.pt", "tv3.rtp.pt"],
    "dn.pt": ["www.dn.pt", "dn.pt", "150anos.dn.pt", "medialab.dn.pt"],
    "jn.pt": ["www.jn.pt", "jn.pt", "running.jn.pt"],
    "ojogo.pt": ["www.ojogo.pt", "ojogo.pt", "nonstop.ojogo.pt"],
    "abola.pt": ["www.abola.pt", "abola.pt", "m.abola.pt"],
    "caras.pt": ["www.caras.pt", "caras.pt", "caras.sapo.pt"],
}


def source_search_hosts(domain):
    aliases = SOURCE_SEARCH_HOST_ALIASES.get(domain)
    if aliases:
        return aliases
    return [f"www.{domain}", domain]


def filtered_cdxj_latest_date(default_date):
    latest = ""
    if ARQUIVO_CDXJ_DIR.exists():
        for path in ARQUIVO_CDXJ_DIR.glob("*/*.cdxj"):
            match = re.match(r"^(\d{4})$", path.parent.name)
            day_match = re.match(r"^(\d{2})-(\d{2})\.cdxj$", path.name)
            if not match or not day_match:
                continue
            candidate = f"{match.group(1)}-{day_match.group(1)}-{day_match.group(2)}"
            latest = max(latest, candidate)
    return min(latest or default_date, default_date)

NEWS_SOURCE_BRANDS = {
    "publico.pt": "publico",
    "expresso.pt": "expresso",
    "cmjornal.pt": "correio-da-manha",
    "sabado.pt": "sabado",
    "rtp.pt": "rtp",
    "observador.pt": "observador",
    "jn.pt": "jornal-de-noticias",
    "dn.pt": "diario-de-noticias",
    "sicnoticias.pt": "sic-noticias",
    "noticiasaominuto.com": "noticias-ao-minuto",
    "record.pt": "record",
    "ojogo.pt": "o-jogo",
    "abola.pt": "a-bola",
    "caras.pt": "caras",
    "flash.pt": "flash",
    "tv7dias.pt": "tv-7-dias",
    "holofote.pt": "holofote",
    "selfie.iol.pt": "selfie",
    "lux.iol.pt": "lux",
    "nit.pt": "nit",
    "timeout.pt": "time-out",
    "blitz.pt": "blitz",
    "mag.sapo.pt": "sapo-mag",
    "visao.pt": "visao",
    "exameinformatica.pt": "exame-informatica",
    "activa.pt": "activa",
    "maxima.pt": "maxima",
}

INSTAGRAM_SOURCE_BRANDS = {
    "publico.pt": "publico",
    "sicnoticias": "sic-noticias",
    "cnnportugal": "cnn-portugal",
    "rtpnoticias": "rtp",
    "correiodamanhaoficial": "correio-da-manha",
    "observador": "observador",
    "24sapo": "sapo-24",
    "epahsaiu": "epah-saiu",
    "4gnewspt": "4gnews",
    "renascenca": "renascenca",
    "jornalexpresso": "expresso",
    "hojenomundomilitar": "hoje-no-mundo-militar",
    "revista_nit": "nit",
    "revistaoriana": "revista-oriana",
}


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, payload):
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_python_literal(path, variable_name, default):
    """Read a simple list/dict constant without importing modules with side effects."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return default
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == variable_name for target in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (TypeError, ValueError):
                return default
    return default


def non_negative_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def refresh_instagram_metrics(metrics):
    networks = metrics.setdefault("networks", {})
    instagram = networks.setdefault("instagram", {"followers": 0})
    manual_followers = os.environ.get("INSTAGRAM_FOLLOWERS")
    if manual_followers not in (None, ""):
        instagram["followers"] = non_negative_int(manual_followers)
        instagram["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return True

    token = os.environ.get("IG_ACCESS_TOKEN_PT") or os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID_PT") or os.environ.get("IG_USER_ID")
    if not token or not user_id:
        return False

    try:
        response = requests.get(
            f"https://graph.facebook.com/v25.0/{user_id}",
            params={"fields": "followers_count,username", "access_token": token},
            timeout=(8, 20),
        )
        response.raise_for_status()
        payload = response.json()
        if "followers_count" not in payload:
            return False
        instagram["followers"] = non_negative_int(payload.get("followers_count"))
        username = clean_text(payload.get("username"))
        if username:
            instagram["username"] = username
            instagram["profile_url"] = f"https://www.instagram.com/{username}/"
        instagram["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return True
    except (requests.RequestException, ValueError) as exc:
        print(f"[site] Nao foi possivel atualizar seguidores do Instagram: {type(exc).__name__}")
        return False


def build_project_metrics(items):
    state = load_json(ARQUIVO_CDXJ_STATE_FILE, {})
    processed = state.get("processed", {}) if isinstance(state, dict) else {}
    entries = [value for value in processed.values() if isinstance(value, dict)] if isinstance(processed, dict) else []

    indexed_news = sum(non_negative_int(entry.get("written")) for entry in entries)
    indexed_news = max(indexed_news, len(items))
    start_years = [non_negative_int(entry.get("start_year")) for entry in entries]
    end_years = [non_negative_int(entry.get("end_year")) for entry in entries]
    start_years = [year for year in start_years if year]
    end_years = [year for year in end_years if year]

    item_years = [
        non_negative_int(item.get("original_year"))
        for item in items
        if non_negative_int(item.get("original_year"))
    ]
    coverage_start = min(start_years or item_years or [1996])
    coverage_end = max(end_years or item_years or [datetime.now().year])

    news_domains = load_python_literal(CDXJ_BUILDER_FILE, "NEWS_DOMAINS", [])
    instagram_profiles = load_python_literal(INSTAGRAM_SCRAPER_FILE, "PROFILES", {})
    pt_profiles = instagram_profiles.get("pt", []) if isinstance(instagram_profiles, dict) else []
    news_brands = {NEWS_SOURCE_BRANDS.get(domain, domain) for domain in news_domains}
    instagram_brands = {INSTAGRAM_SOURCE_BRANDS.get(profile, profile) for profile in pt_profiles}
    unique_sources = news_brands | instagram_brands

    social_metrics = load_json(SOCIAL_METRICS_FILE, {"networks": {"instagram": {"followers": 0}}})
    if not isinstance(social_metrics, dict):
        social_metrics = {"networks": {"instagram": {"followers": 0}}}
    social_metrics_changed = refresh_instagram_metrics(social_metrics)
    networks = social_metrics.get("networks", {})
    if not isinstance(networks, dict):
        networks = {}
    social_followers = sum(
        non_negative_int(details.get("followers"))
        for details in networks.values()
        if isinstance(details, dict)
    )

    publication_history = social_metrics.setdefault("publications", {})
    if not isinstance(publication_history, dict):
        publication_history = {}
        social_metrics["publications"] = publication_history
    known_post_ids = {
        clean_text(post_id)
        for post_id in publication_history.get("post_ids", [])
        if clean_text(post_id)
    }
    current_published_ids = {
        clean_text(item.get("id"))
        for item in items
        if item.get("status") == "published" and clean_text(item.get("id"))
    }
    merged_post_ids = known_post_ids | current_published_ids
    previous_publication_count = non_negative_int(publication_history.get("count"))
    published_posts = max(previous_publication_count, len(merged_post_ids), len(current_published_ids))
    if merged_post_ids != known_post_ids or published_posts != previous_publication_count:
        publication_history["post_ids"] = sorted(merged_post_ids)
        publication_history["count"] = published_posts
        publication_history["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        social_metrics_changed = True
    if social_metrics_changed:
        save_json(SOCIAL_METRICS_FILE, social_metrics)

    return {
        "news_covered": indexed_news,
        "coverage_start_year": coverage_start,
        "coverage_end_year": coverage_end,
        "news_sources": len(set(news_domains)) if isinstance(news_domains, list) else 0,
        "instagram_sources": len(set(pt_profiles)) if isinstance(pt_profiles, list) else 0,
        "unique_sources": len(unique_sources),
        "published_posts": published_posts,
        "social_followers": social_followers,
        "social_networks": len(networks),
        "news_source_domains": sorted(set(news_domains)) if isinstance(news_domains, list) else [],
    }


def clean_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if any(marker in text for marker in ("Ã", "Â", "â€", "â€œ", "â€\u009d")):
        try:
            repaired = text.encode("cp1252").decode("utf-8")
            text = re.sub(r"\s+", " ", repaired).strip()
        except Exception:
            pass
    return text


def strip_hashtags(value):
    text = re.sub(r"#\w+", "", str(value or ""))
    return clean_text(text)


def slugify(value):
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9\-_\s]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text[:90] or "post"


def news_page_id(item):
    identity = clean_text(
        item.get("original_url")
        or item.get("source_url")
        or item.get("instagram_url")
        or item.get("id")
        or f"{item.get('date', '')}|{item.get('title', '')}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"noticia-{digest}"


def arquivo_screenshot_url(source_url):
    source_url = clean_text(source_url)
    if not source_url or "arquivo.pt/" not in source_url:
        return ""
    return f"https://arquivo.pt/screenshot/?url={quote(source_url, safe='')}"


def has_enduring_editorial_value(item):
    text = clean_text(f"{item.get('title', '')} {item.get('summary', '')}").lower()
    anniversary_patterns = [
        r"\bparab[eé]ns\b",
        r"\b(?:celebra|celebram|comemora|comemoram|assinala|assinalam)\b.{0,90}\b\d{1,3}\s+anos\b",
        r"\b\d{1,3}[.ºoª\s]*(?:anivers[aá]rio|anos de exist[eê]ncia)\b",
    ]
    if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in anniversary_patterns):
        return True
    substantive_markers = (
        "inaugura", "lança", "lanca", "estreia", "concerto", "exposição", "exposicao",
        "vence", "recorde", "descoberta", "eleição", "eleicao", "acordo", "lei", "reforma",
        "investigação", "investigacao", "campeonato", "festival", "filme", "álbum", "album",
    )
    return any(marker in text for marker in substantive_markers)


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POST_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    BANNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def copy_site_image(source_path, fallback_name):
    if not source_path:
        return ""
    normalized = str(source_path).replace("/", os.sep)
    path = ROOT / normalized
    if not path.exists():
        return source_path if source_path.startswith(("http://", "https://")) else ""
    target_name = f"{slugify(Path(fallback_name).stem)}{path.suffix.lower() or '.jpg'}"
    target = POST_ASSETS_DIR / target_name
    shutil.copyfile(path, target)
    return f"assets/posts/{target.name}"


def local_source_path(source_path):
    if not source_path:
        return None
    normalized = str(source_path).replace("/", os.sep)
    path = ROOT / normalized
    return path if path.exists() else None


def load_font(weight="regular", size=48):
    file_name = "Montserrat-Bold.ttf" if weight == "bold" else "Montserrat-Regular.ttf"
    path = ROOT / "images" / "montserrat" / file_name
    try:
        return ImageFont.truetype(str(path), size=size)
    except Exception:
        return ImageFont.load_default()


def cover_image(image, size, focus_y=0.5):
    image = image.convert("RGB")
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.LANCZOS)
    left = max((resized.width - target_w) // 2, 0)
    max_top = max(resized.height - target_h, 0)
    top = int(max_top * min(max(float(focus_y), 0.0), 1.0))
    return resized.crop((left, top, left + target_w, top + target_h))


def draw_wrapped_text(draw, xy, text, font, fill, max_width, line_gap=8, max_lines=4):
    words = clean_text(text).split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
        lines[-1] = lines[-1].rstrip(" .") + "..."

    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((0, 0), line, font=font)[3] + line_gap
    return y


def create_banner_image(source_path, fallback_name, title, category, year):
    del title, category, year
    source = source_path if source_path and source_path.exists() else ICON_SOURCE
    if not source.exists():
        return ""

    target = BANNER_ASSETS_DIR / f"{slugify(fallback_name)}-banner.jpg"
    canvas_w, canvas_h = 1600, 700
    try:
        source_image = Image.open(source)
        image_area = cover_image(source_image, (canvas_w, canvas_h), focus_y=0.7)
    except Exception:
        return ""

    softened = image_area.filter(ImageFilter.GaussianBlur(radius=7.5))
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 65, 106, 54))
    canvas = Image.alpha_composite(softened.convert("RGBA"), overlay).convert("RGB")
    canvas.save(target, quality=88, optimize=True)
    return f"assets/banners/{target.name}"


def selected_option(post):
    options = post.get("options") if isinstance(post.get("options"), list) else []
    if not options:
        return {}
    try:
        idx = int(post.get("selected_option", 0) or 0)
    except Exception:
        idx = 0
    if idx < 0 or idx >= len(options):
        idx = 0
    return options[idx] if isinstance(options[idx], dict) else {}


def build_registry_lookup(records):
    by_post_id = {}
    for record in records:
        post_id = clean_text(record.get("post_id"))
        if post_id:
            by_post_id[post_id] = record
    return by_post_id


def post_to_site_item(post, registry_by_post_id):
    option = selected_option(post)
    if not option:
        return None

    post_id = clean_text(post.get("id"))
    registry_record = registry_by_post_id.get(post_id, {})
    title = clean_text(option.get("title"))
    if not title:
        return None

    summary = strip_hashtags(option.get("summary") or option.get("caption") or option.get("overlay_description"))
    image_path = clean_text(option.get("local_image_path"))
    source_local_image = local_source_path(image_path)
    image = copy_site_image(image_path, f"{post.get('date', '')}-{post.get('slot', '')}-{title}")
    if not image:
        image = clean_text(option.get("image_url") or registry_record.get("image_url"))

    status = clean_text(post.get("status") or "pending").lower()
    original_year = clean_text(option.get("year"))
    publish_date = clean_text(post.get("date"))
    category = clean_text(option.get("category") or "Atualidade")
    banner_image = create_banner_image(
        source_local_image,
        f"{publish_date}-{post.get('slot', '')}-{title}",
        title,
        category,
        original_year,
    )
    source_url = clean_text(
        option.get("background_source_url")
        or option.get("source_url")
        or post.get("source_url")
    )
    instagram_url = clean_text(
        post.get("instagram_url")
        or option.get("instagram_url")
        or registry_record.get("instagram_url")
        or registry_record.get("permalink")
    )
    instagram_id = clean_text(post.get("instagram_id") or registry_record.get("instagram_id"))
    item = {
        "id": post_id,
        "lang": clean_text(post.get("lang") or "pt"),
        "date": publish_date,
        "slot": post.get("slot", 0),
        "status": status,
        "category": category,
        "title": title,
        "title_en": clean_text(option.get("title_en")),
        "summary": summary,
        "summary_en": clean_text(option.get("summary_en")),
        "original_year": original_year,
        "image": image,
        "banner_image": banner_image,
        "source_url": source_url,
        "source_profile": clean_text(post.get("source_profile") or option.get("source_profile")),
        "instagram_url": instagram_url,
        "instagram_id": instagram_id,
        "archive_credit": "Arquivo.pt",
    }
    item["page_id"] = news_page_id(item)
    item["detail_image"] = image or arquivo_screenshot_url(source_url)
    return item


def build_calendar_payload(items):
    dates = sorted({item.get("date") for item in items if item.get("date")})
    years = sorted({int(date[:4]) for date in dates if re.match(r"^\d{4}-\d{2}-\d{2}$", date)})
    return {
        "post_dates": dates,
        "post_years": years,
        "recommendations_by_day": {},
        "recommendations_mode": "static_posts_only" if static_site_only() else "dynamic_api",
        "target_total_per_day": 25,
        "top_instagram_posts": 4,
    }


def build_payload():
    ensure_dirs()
    if ICON_SOURCE.exists():
        shutil.copyfile(ICON_SOURCE, ASSETS_DIR / ICON_ASSET)

    pending_posts = load_json(PENDING_POSTS_FILE, [])
    registry = load_json(IMGBB_UPLOADS_FILE, [])
    registry_by_post_id = build_registry_lookup(registry if isinstance(registry, list) else [])

    items = []
    for post in pending_posts if isinstance(pending_posts, list) else []:
        item = post_to_site_item(post, registry_by_post_id)
        if item:
            items.append(item)

    items.sort(key=lambda item: (item.get("date", ""), int(item.get("slot") or 0)), reverse=True)
    published = [item for item in items if item.get("status") == "published"]
    approved = [item for item in items if item.get("status") == "approved"]
    editorial_items = [item for item in items if has_enduring_editorial_value(item)]
    editorial_published = [item for item in published if has_enduring_editorial_value(item)]
    editorial_approved = [item for item in approved if has_enduring_editorial_value(item)]
    public_items = editorial_published or editorial_approved or editorial_items or published or approved or items
    featured = public_items[0] if public_items else None
    metrics = build_project_metrics(items)
    today = datetime.now().date()
    coverage_end_date = f"{metrics['coverage_end_year']}-12-31"
    cdxj_state = load_json(ARQUIVO_CDXJ_STATE_FILE, {})
    domain_coverage = cdxj_state.get("domain_coverage", {}) if isinstance(cdxj_state, dict) else {}
    coverage_latest_dates = [
        clean_text(details.get("latest_date"))
        for details in domain_coverage.values()
        if isinstance(details, dict) and clean_text(details.get("latest_date"))
    ]
    coverage_first_dates = [
        clean_text(details.get("first_date"))
        for details in domain_coverage.values()
        if isinstance(details, dict) and clean_text(details.get("first_date"))
    ]
    provisional_max_topic_date = filtered_cdxj_latest_date(min(today.isoformat(), coverage_end_date))
    max_topic_date = min(
        today.isoformat(),
        coverage_end_date,
        max(coverage_latest_dates) if coverage_latest_dates else provisional_max_topic_date,
    )
    min_topic_date = min(coverage_first_dates) if coverage_first_dates else f"{metrics['coverage_start_year']}-01-01"
    metrics["coverage_start_year"] = int(min_topic_date[:4])
    metrics["coverage_end_year"] = int(max_topic_date[:4])
    if domain_coverage:
        covered_domains = sorted(domain for domain in domain_coverage if domain in NEWS_SOURCE_BRANDS or domain in metrics["news_source_domains"])
        instagram_profiles = load_python_literal(INSTAGRAM_SCRAPER_FILE, "PROFILES", {})
        pt_profiles = instagram_profiles.get("pt", []) if isinstance(instagram_profiles, dict) else []
        covered_brands = {NEWS_SOURCE_BRANDS.get(domain, domain) for domain in covered_domains}
        instagram_brands = {INSTAGRAM_SOURCE_BRANDS.get(profile, profile) for profile in pt_profiles}
        metrics["news_source_domains"] = covered_domains
        metrics["news_sources"] = len(covered_domains)
        metrics["unique_sources"] = len(covered_brands | instagram_brands)
    source_metadata = {
        domain: {
            "created_year": SOURCE_CREATED_YEARS.get(domain, metrics["coverage_start_year"]),
            "analysis_start": max(
                f"{max(metrics['coverage_start_year'], SOURCE_CREATED_YEARS.get(domain, metrics['coverage_start_year']))}-01-01",
                clean_text((domain_coverage.get(domain) or {}).get("first_date")) or "0000-01-01",
            ),
            "analysis_end": min(
                max_topic_date,
                clean_text((domain_coverage.get(domain) or {}).get("latest_date")) or max_topic_date,
            ),
            "first_capture_date": clean_text((domain_coverage.get(domain) or {}).get("first_date")),
            "latest_capture_date": clean_text((domain_coverage.get(domain) or {}).get("latest_date")) or max_topic_date,
            "search_hosts": source_search_hosts(domain),
        }
        for domain in metrics["news_source_domains"]
    }

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "default_lang": "pt",
        "source_credit": "Dados recolhidos e contextualizados a partir do Arquivo.pt.",
        "instagram_profile_url": os.environ.get("INSTAGRAM_PROFILE_URL", "https://www.instagram.com/"),
        "featured": featured,
        "carousel": public_items[:8],
        "latest": published[:12] if published else public_items[:12],
        "all": items,
        "calendar": build_calendar_payload(items),
        "metrics": metrics,
        "topic_search": {
            "start_year": metrics["coverage_start_year"],
            "end_year": metrics["coverage_end_year"],
            "min_date": min_topic_date,
            "max_date": max_topic_date,
            "sources": metrics["news_source_domains"],
            "source_metadata": source_metadata,
            "coverage_updated_at": clean_text(cdxj_state.get("coverage_updated_at")) if isinstance(cdxj_state, dict) else "",
            "coverage_basis": "cdxj_domain" if domain_coverage else "cdxj_files",
            "coverage_precise": bool(domain_coverage),
        },
        "api_base_url": "" if static_site_only() else clean_text(os.environ.get("SITE_API_BASE_URL")),
        "runtime_mode": "static" if static_site_only() else "dynamic_fallback",
        "github_url": "https://github.com/luisflmaximo/Noticias-de-ontem-pt",
        "has_published_posts": bool(published),
    }


def route_structured_data(route, title, description):
    page_type = {
        "inicio": "WebSite",
        "calendario": "CollectionPage",
        "temas": "SearchResultsPage",
        "documentacao": "WebPage",
    }.get(route, "WebPage")
    return {
        "@context": "https://schema.org",
        "@type": page_type,
        "name": title,
        "description": description,
        "url": absolute_site_url(f"{route}/"),
        "inLanguage": "pt-PT",
        "isPartOf": {
            "@type": "WebSite",
            "name": "Notícias de Ontem",
            "url": absolute_site_url(),
        },
        "isBasedOn": "https://arquivo.pt/",
    }


def story_title(item):
    title = clean_text(item.get("title")) or "Notícia preservada"
    year = clean_text(item.get("original_year"))
    if year and not re.search(rf"\b{re.escape(year)}\b", title):
        return f"{title} em {year}"
    return title


def story_structured_data(item, canonical, image):
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": story_title(item),
        "description": clean_text(item.get("summary")),
        "url": canonical,
        "mainEntityOfPage": canonical,
        "image": [image],
        "datePublished": clean_text(item.get("date")),
        "dateModified": datetime.now(timezone.utc).date().isoformat(),
        "articleSection": clean_text(item.get("category")),
        "inLanguage": "pt-PT",
        "author": {"@type": "Organization", "name": "Notícias de Ontem"},
        "publisher": {
            "@type": "Organization",
            "name": "Notícias de Ontem",
            "url": absolute_site_url(),
            "logo": {
                "@type": "ImageObject",
                "url": absolute_site_url(f"assets/{ICON_ASSET}"),
            },
        },
        "isBasedOn": clean_text(item.get("source_url")) or "https://arquivo.pt/",
    }
    return {key: value for key, value in payload.items() if value}


def write_route_pages(payload):
    index_path = SITE_DIR / "index.html"
    if not index_path.exists():
        return
    source_html = index_path.read_text(encoding="utf-8")
    route_shell = (
        source_html
        .replace(f'href="assets/{ICON_ASSET}"', f'href="../assets/{ICON_ASSET}"')
        .replace(f'src="assets/{ICON_ASSET}"', f'src="../assets/{ICON_ASSET}"')
        .replace('href="styles.css?v=20260718i"', 'href="../styles.css?v=20260718i"')
        .replace('src="app.js?v=20260718i"', 'src="../app.js?v=20260718i"')
        .replace('href="inicio/"', 'href="../inicio/"')
        .replace('href="calendário/"', 'href="../calendario/"')
        .replace('href="temas/"', 'href="../temas/"')
        .replace('href="documentação/"', 'href="../documentacao/"')
    )
    route_metadata = {
        "inicio": (
            "Notícias de Ontem | Memória da imprensa portuguesa",
            "Explore notícias preservadas pelo Arquivo.pt, compare diferentes anos e descubra a memória da imprensa portuguesa em cada dia.",
            "inicio",
        ),
        "calendario": (
            "Calendário de notícias históricas | Notícias de Ontem",
            "Escolha uma data e descubra notícias de diferentes anos preservadas pelo Arquivo.pt.",
            "calendario",
        ),
        "temas": (
            "Evolução de temas na imprensa portuguesa | Notícias de Ontem",
            "Analise a evolução de até quatro temas na imprensa portuguesa preservada e filtre os resultados por jornal e período.",
            "temas",
        ),
        "documentacao": (
            "Como funciona o projeto | Notícias de Ontem",
            "Conheça as fontes, a cobertura e o método usado pelo Notícias de Ontem para selecionar conteúdos preservados pelo Arquivo.pt.",
            "documentacao",
        ),
        "noticia": (
            "Notícia preservada | Notícias de Ontem",
            "Consulte uma notícia histórica, a sua imagem, contexto e ligação verificável ao Arquivo.pt.",
            "noticia",
        ),
    }
    home_title, home_description, home_canonical_path = route_metadata["inicio"]
    source_html = with_seo(
        source_html,
        seo_block(
            home_title,
            home_description,
            f"{home_canonical_path}/",
            route_structured_data(home_canonical_path, home_title, home_description),
        ),
    )
    index_path.write_text(source_html, encoding="utf-8")
    aliases = {
        "calendário": "calendario",
        "documentação": "documentacao",
    }
    for route in ["inicio", "calendário", "documentação", "temas", "noticia", "calendario", "documentacao"]:
        canonical_route = aliases.get(route, route)
        title, description, canonical_path = route_metadata[canonical_route]
        structured = route_structured_data(canonical_path, title, description)
        route_html = with_seo(
            route_shell,
            seo_block(
                title,
                description,
                f"{canonical_path}/",
                structured,
                index=canonical_route != "noticia",
            ),
        )
        route_dir = SITE_DIR / route
        route_dir.mkdir(parents=True, exist_ok=True)
        (route_dir / "index.html").write_text(route_html, encoding="utf-8")

    news_root = SITE_DIR / "noticia"
    for child in news_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)

    indexed_story_urls = []
    nested_shell = (
        source_html
        .replace(f'href="assets/{ICON_ASSET}"', f'href="../../assets/{ICON_ASSET}"')
        .replace(f'src="assets/{ICON_ASSET}"', f'src="../../assets/{ICON_ASSET}"')
        .replace('href="styles.css?v=20260718i"', 'href="../../styles.css?v=20260718i"')
        .replace('src="app.js?v=20260718i"', 'src="../../app.js?v=20260718i"')
        .replace('href="inicio/"', 'href="../../inicio/"')
        .replace('href="calendário/"', 'href="../../calendario/"')
        .replace('href="temas/"', 'href="../../temas/"')
        .replace('href="documentação/"', 'href="../../documentacao/"')
    )
    for item in payload.get("all", []):
        page_id = clean_text(item.get("page_id"))
        if not page_id or not re.fullmatch(r"[a-z0-9-]+", page_id):
            continue
        title = story_title(item)
        description = clean_text(item.get("summary")) or f"Consulte {title} e a fonte preservada no Arquivo.pt."
        canonical_path = f"noticia/{page_id}/"
        image_path = clean_text(item.get("detail_image") or item.get("image") or item.get("banner_image")) or f"assets/{ICON_ASSET}"
        canonical = absolute_site_url(canonical_path)
        image = absolute_site_url(image_path)
        should_index = clean_text(item.get("status")).lower() == "published"
        story_html = with_seo(
            nested_shell,
            seo_block(
                f"{title} | Notícias de Ontem",
                description,
                canonical_path,
                story_structured_data(item, canonical, image),
                image_path=image_path,
                index=should_index,
                og_type="article",
            ),
        )
        story_dir = news_root / page_id
        story_dir.mkdir(parents=True, exist_ok=True)
        (story_dir / "index.html").write_text(story_html, encoding="utf-8")
        if should_index:
            indexed_story_urls.append(canonical)

    generated_date = clean_text(payload.get("generated_at"))[:10] or datetime.now(timezone.utc).date().isoformat()
    sitemap_urls = [
        absolute_site_url("inicio/"),
        absolute_site_url("calendario/"),
        absolute_site_url("temas/"),
        absolute_site_url("documentacao/"),
        *indexed_story_urls,
    ]
    sitemap_entries = "\n".join(
        f"  <url><loc>{html.escape(url)}</loc><lastmod>{generated_date}</lastmod></url>"
        for url in sitemap_urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{sitemap_entries}\n"
        "</urlset>\n"
    )
    (SITE_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    robots = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /*?id=",
            f"Sitemap: {absolute_site_url('sitemap.xml')}",
            "",
        ]
    )
    (SITE_DIR / "robots.txt").write_text(robots, encoding="utf-8")


def main():
    payload = build_payload()
    with (DATA_DIR / "news.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    write_route_pages(payload)
    print(f"Site data written to {DATA_DIR / 'news.json'}")


if __name__ == "__main__":
    main()
