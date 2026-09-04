import json
import os
import random
import re
import shutil
import unicodedata
import gzip
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import requests

from archive_storage import (
    block_id_for_month_day,
    load_block,
    load_posts_for_date,
    save_block,
)
from imgbb_registry import register_imgbb_upload
from nvidia_client import DEFAULT_NVIDIA_MODEL, NvidiaKeyPool, load_nvidia_api_keys
from post_templates import create_image_with_text as render_post_image
from http_cache import cached_get


IG_CREDENTIALS = {
    "pt": {
        "token": os.environ.get("IG_ACCESS_TOKEN_PT") or os.environ.get("IG_ACCESS_TOKEN"),
        "user_id": os.environ.get("IG_USER_ID_PT") or os.environ.get("IG_USER_ID"),
    },
    "en": {
        "token": os.environ.get("IG_ACCESS_TOKEN_EN") or os.environ.get("IG_ACCESS_TOKEN"),
        "user_id": os.environ.get("IG_USER_ID_EN") or os.environ.get("IG_USER_ID"),
    },
}


api_keys = load_nvidia_api_keys()
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL)
nvidia_pool = NvidiaKeyPool(api_keys)
if nvidia_pool.has_keys():
    nvidia_pool.current_index = random.randint(0, len(api_keys) - 1)

def get_current_key_info():
    return nvidia_pool.get_current_key_info()

def save_key_status_to_file():
    nvidia_pool.save_key_status_to_file()


save_key_status_to_file()

def rotate_nvidia_client():
    return nvidia_pool.rotate()


def copy_image_reference_to_path(image_url, output_path, timeout=10):
    if not image_url:
        return False
    if re.match(r"^https?://", image_url, flags=re.IGNORECASE):
        img_response = requests.get(image_url, timeout=timeout)
        if img_response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(img_response.content)
            return True
        return False

    local_path = image_url.replace("/", os.sep)
    if os.path.exists(local_path):
        shutil.copyfile(local_path, output_path)
        return True
    return False

MAX_NVIDIA_INPUT_ITEMS = int(os.environ.get("PUBLISHER_NVIDIA_MAX_INPUT_ITEMS", "8"))
ARQUIVO_AI_MAX_CANDIDATES = int(os.environ.get("ARQUIVO_AI_MAX_CANDIDATES", "300"))
ARQUIVO_TEXTSEARCH_TIMEOUT = int(os.environ.get("ARQUIVO_TEXTSEARCH_TIMEOUT", "90"))
ARQUIVO_TEXTSEARCH_MAX_FAILURES_PER_YEAR = int(os.environ.get("ARQUIVO_TEXTSEARCH_MAX_FAILURES_PER_YEAR", "999"))
ARQUIVO_TEXTSEARCH_GLOBAL_FAILURE_LIMIT = int(os.environ.get("ARQUIVO_TEXTSEARCH_GLOBAL_FAILURE_LIMIT", "9999"))
ARQUIVO_HOMEPAGE_TIMEOUT = int(os.environ.get("ARQUIVO_HOMEPAGE_TIMEOUT", "60"))
ARQUIVO_HOMEPAGE_MAX_FAILURES_PER_YEAR = int(os.environ.get("ARQUIVO_HOMEPAGE_MAX_FAILURES_PER_YEAR", "999"))
ARQUIVO_HOMEPAGE_GLOBAL_FAILURE_LIMIT = int(os.environ.get("ARQUIVO_HOMEPAGE_GLOBAL_FAILURE_LIMIT", "9999"))
ARQUIVO_DEGRADED_MIN_CANDIDATES = int(os.environ.get("ARQUIVO_DEGRADED_MIN_CANDIDATES", "999999"))
ARQUIVO_CDXJ_DIR = os.environ.get("ARQUIVO_CDXJ_DIR", "arquivo_cdxj")
MAX_NVIDIA_CONTEXT_CHARS = int(os.environ.get("PUBLISHER_NVIDIA_MAX_CONTEXT_CHARS", "320"))
NVIDIA_DISABLED = False
NVIDIA_ERROR_MARKERS = ("429", "503", "401", "403", "resource_exhausted", "unavailable", "quota exceeded", "rate limit", "invalid", "unauthorized", "forbidden")
CTA_PATTERNS = [
    r"\blink na bio\b",
    r"\bna bio\b",
    r"\bread more\b",
    r"\bsee more\b",
    r"\bsaiba mais\b",
    r"\bveja mais\b",
    r"\bacompanhe\b",
    r"\bstories\b",
    r"\bswipe\b",
    r"\barraste\b",
]
NVIDIA_HINT_KEYWORDS = [
    "meme",
    "viral",
    "celebr",
    "cantor",
    "atriz",
    "actor",
    "futebol",
    "football",
    "sport",
    "desporto",
    "polit",
    "elei",
    "govern",
    "partido",
    "voto",
    "lei",
    "aprovad",
    "reforma",
    "psd",
    "ps",
    "cds",
    "coliga",
    "famos",
    "bizarro",
    "curioso",
    "insólit",
    "polemic",
    "tesla",
    "spacex",
    "iphone",
    "apple",
    "google",
    "beyonc",
    "rihanna",
    "swift",
    "kardashian",
    "gaga",
    "ronaldo",
    "messi",
    "festival",
    "music",
    "cultura",
    "internet",
    "met gala",
]


def normalize_text(value, uppercase=False):
    if value is None:
        value = ""
    normalized = unicodedata.normalize("NFC", str(value)).strip()
    return normalized.upper() if uppercase else normalized


def compact_text(value, limit=MAX_NVIDIA_CONTEXT_CHARS):
    text = re.sub(r"\s+", " ", normalize_text(value)).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


def strip_publicity_text(value):
    text = re.sub(r"\s+", " ", normalize_text(value)).strip()
    if not text:
        return ""
    text = re.sub(r"#\w+", "", text)
    for pattern in CTA_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" -:;,.!")


def score_news_item(item):
    text = normalize_text(build_editorial_context(item)).lower()
    score = 0
    for keyword in NVIDIA_HINT_KEYWORDS:
        if keyword in text:
            score += 1
    if len(text) < 180:
        score += 1
    return score


def select_nvidia_news_items(news_items, max_total=MAX_NVIDIA_INPUT_ITEMS):
    ranked = sorted(
        news_items,
        key=lambda item: (score_news_item(item), item.get("date", "")),
        reverse=True,
    )
    return ranked[:max_total]


def fold_for_search(value):
    text = unicodedata.normalize("NFKD", normalize_text(value))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def score_arquivo_candidate(item):
    text = fold_for_search(
        " ".join(
            [
                item.get("title", ""),
                item.get("snippet", ""),
                item.get("url", ""),
                item.get("domain", ""),
            ]
        )
    )
    domain = normalize_text(item.get("domain", "")).lower()
    score = 0

    magazine_domains = {
        "caras.pt", "flash.pt", "tv7dias.pt", "holofote.pt", "selfie.iol.pt",
        "lux.iol.pt", "nit.pt", "timeout.pt", "blitz.pt", "mag.sapo.pt",
        "activa.pt", "maxima.pt", "exameinformatica.pt",
    }
    strong_terms = [
        "ronaldo", "messi", "mourinho", "madonna", "britney", "beyonce",
        "rihanna", "lady gaga", "swift", "festival", "eurovisao", "cinema",
        "televisao", "famos", "celebr", "ator", "atriz", "cantor", "musica",
        "internet", "tecnologia", "iphone", "google", "apple", "facebook",
        "youtube", "instagram", "viral", "curioso", "bizarro", "insolito",
    ]
    civic_terms = [
        "eleicoes", "governo", "primeiro-ministro", "presidente", "partido",
        "ps ", "psd", "cds", "lei", "referendo", "parlamento", "ministro",
    ]
    weak_terms = [
        "agenda", "programacao", "horoscopo", "meteorologia", "farmacias",
        "transito", "obituario", "classificados", "opiniao",
        "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
        "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
        "primark", "outlet", "catalogo", "catálogo",
    ]

    if domain in magazine_domains:
        score += 4
    for term in strong_terms:
        if term in text:
            score += 4
    for term in civic_terms:
        if term in text:
            score += 3
    for term in weak_terms:
        if term in text:
            score -= 6
    if re.search(r"\b[A-Z][\w-]+(?:\s+[A-Z][\w-]+){1,3}\b", normalize_text(item.get("title", ""))):
        score += 2
    if "/tag/" in text or "/autor/" in text or "/opiniao/" in text:
        score -= 8
    return score


def select_arquivo_candidate_pool(candidate_articles, max_total=ARQUIVO_AI_MAX_CANDIDATES):
    indexed = list(enumerate(candidate_articles))
    if len(indexed) <= max_total:
        return indexed

    ranked = sorted(
        indexed,
        key=lambda pair: (
            score_arquivo_candidate(pair[1]),
            str(pair[1].get("timestamp", "")),
            str(pair[1].get("title", "")),
        ),
        reverse=True,
    )

    selected = []
    selected_indexes = set()

    def add(pair):
        idx, _item = pair
        if idx in selected_indexes or len(selected) >= max_total:
            return
        selected.append(pair)
        selected_indexes.add(idx)

    for pair in ranked[: max(40, max_total // 3)]:
        add(pair)

    best_by_year = {}
    best_by_domain = {}
    for pair in ranked:
        _idx, item = pair
        year = str(item.get("year") or item.get("timestamp") or "")[:4] or "0000"
        domain = normalize_text(item.get("domain", "")).lower()
        best_by_year.setdefault(year, pair)
        if domain:
            best_by_domain.setdefault(domain, pair)

    for pair in sorted(best_by_year.values(), key=lambda p: score_arquivo_candidate(p[1]), reverse=True):
        add(pair)
    for pair in sorted(best_by_domain.values(), key=lambda p: score_arquivo_candidate(p[1]), reverse=True):
        add(pair)
    for pair in ranked:
        add(pair)

    return selected


def select_arquivo_fallback_indexes(candidate_articles, max_total=5):
    return [idx for idx, _item in select_arquivo_candidate_pool(candidate_articles, max_total=max_total)]


STATIC_URL_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".mp3", ".avi", ".mov", ".pdf",
    ".zip", ".rar", ".xml", ".json", ".rss",
)


def arquivo_cdxj_paths_for_day(year, month, day):
    root = Path(ARQUIVO_CDXJ_DIR)
    if not root.exists():
        return []

    date_compact = f"{year}{month:02d}{day:02d}"
    date_dash = f"{year}-{month:02d}-{day:02d}"
    month_day = f"{month:02d}-{day:02d}"
    suffixes = ("cdxj", "cdxj.gz", "jsonl", "jsonl.gz", "ndjson", "ndjson.gz")
    bases = [
        root / date_compact,
        root / date_dash,
        root / str(year) / date_compact,
        root / str(year) / date_dash,
        root / str(year) / month_day,
        root / str(year) / f"{month:02d}" / f"{day:02d}",
        root / month_day / str(year),
        root / str(year),
    ]

    paths = []
    for base in bases:
        for suffix in suffixes:
            path = Path(f"{base}.{suffix}")
            if path.exists() and path not in paths:
                paths.append(path)
    return paths


def iter_cdxj_records(path):
    opener = gzip.open if str(path).lower().endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                timestamp = ""
                payload = None
                if line.startswith("{"):
                    payload = line
                else:
                    parts = line.split(maxsplit=2)
                    if len(parts) >= 3:
                        timestamp = parts[1]
                        payload = parts[2]
                if not payload:
                    continue
                try:
                    record = json.loads(payload)
                except Exception:
                    continue
                if timestamp and not record.get("timestamp") and not record.get("tstamp"):
                    record["_cdxj_timestamp"] = timestamp
                yield record
    except Exception as exc:
        print(f"[Arquivo.pt][CDXJ] Erro ao ler {path}: {exc}")


def title_from_url(url):
    parsed = urlparse(url)
    path = unquote(parsed.path or "").strip("/")
    slug = path.split("/")[-1] if path else parsed.netloc
    slug = re.sub(r"\.[a-z0-9]{2,6}$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip(" -_/")
    if not slug or len(slug) < 8:
        return f"Pagina arquivada em {parsed.netloc}".strip()
    return slug[:1].upper() + slug[1:]


def source_domain_for_url(url, sources):
    path = url.lower()
    for source in sources:
        if source["domain"] in path:
            return source["domain"]
    return ""


def is_probable_article_url(url):
    path = urlparse(url).path.lower()
    if not path or path == "/":
        return False
    if any(path.endswith(ext) for ext in STATIC_URL_EXTENSIONS):
        return False
    exclude = [
        "/opiniao/", "/editorial/", "/tag/", "/tags/", "/autor/", "/author/",
        "/comentarios/", "/page/", "/feed/", "/wp-json/", "/wp-admin/",
        "/comments/", "/blogs/", "/opinion/", "/pesquisa", "/search",
        "/login", "/logout", "/newsletter", "/passatempos/",
    ]
    if any(x in path for x in exclude):
        return False
    include = [
        "/noticia", "/noticias/", "/article/", "/politica/", "/economia/",
        "/desporto/", "/sociedade/", "/cultura/", "/local/", "/insolito/",
        "/gente/", "/bizarro/", "/curioso/", "/famosos/", "/vida/",
        "/champions/", "/mundial/", "/euro/", "/espetaculo/",
        "/entertainment/", "/showbiz/", "/sport/", "/lifestyle/", "/odd/",
        "/weird/", "/bizarre/", "/pais/", "/mundo/", "/musica/", "/cinema/",
        "/televisao/", "/tecnologia/",
    ]
    return (
        path.endswith(".html")
        or ".asp" in path
        or "/jornal/noticia/" in path
        or "/shownews.asp" in path
        or re.search(r"/20\d{2}/\d{1,2}/\d{1,2}/", path)
        or any(x in path for x in include)
    )


def load_arquivo_cdxj_candidates_for_day(year, month, day, sources, seen_urls):
    date_compact = f"{year}{month:02d}{day:02d}"
    paths = arquivo_cdxj_paths_for_day(year, month, day)
    if not paths:
        return []

    candidates = []
    local_seen = set()
    for path in paths:
        for record in iter_cdxj_records(path):
            timestamp = str(
                record.get("timestamp")
                or record.get("tstamp")
                or record.get("date")
                or record.get("_cdxj_timestamp")
                or ""
            )
            timestamp = re.sub(r"\D", "", timestamp)
            if timestamp and not timestamp.startswith(date_compact):
                continue
            if not timestamp:
                timestamp = f"{date_compact}120000"
            if len(timestamp) == 8:
                timestamp = f"{timestamp}120000"
            if len(timestamp) < 14:
                continue

            status = str(record.get("status") or record.get("statuscode") or record.get("statusCode") or "")
            if status and status not in {"200", "-"}:
                continue
            mime = str(record.get("mime") or record.get("mimeType") or record.get("mimetype") or "").lower()
            if mime and "html" not in mime and "text/plain" not in mime:
                continue

            url = str(
                record.get("url")
                or record.get("originalURL")
                or record.get("original")
                or record.get("url_original")
                or ""
            ).strip()
            if not url.startswith(("http://", "https://")):
                continue
            if url in seen_urls or url in local_seen:
                continue
            domain = source_domain_for_url(url, sources)
            if not domain:
                continue
            if not is_probable_article_url(url):
                continue

            title = normalize_text(record.get("title") or record.get("metadata", {}).get("title") or "")
            if not title or len(title) < 8:
                title = title_from_url(url)

            candidates.append(
                {
                    "url": url,
                    "title": f"[{year}] {title}",
                    "snippet": normalize_text(record.get("snippet") or record.get("text") or title),
                    "timestamp": timestamp[:14],
                    "domain": domain,
                    "year": year,
                }
            )
            local_seen.add(url)

    return candidates


def infer_category_from_text(text, lang):
    normalized = normalize_text(text).lower()
    category_rules = [
        ("DESPORTO" if lang == "pt" else "SPORTS", ["futebol", "football", "sport", "desporto", "ronaldo", "messi"]),
        ("POLITICA" if lang == "pt" else "POLITICS", ["polit", "elei", "govern", "parliament", "presid", "prime minister"]),
        ("CRIME", ["polici", "crime", "morte", "death", "attack", "ataque", "investig", "assass"]),
        ("TECNOLOGIA" if lang == "pt" else "TECHNOLOGY", ["tech", "tecnolog", "iphone", "apple", "google", "spacex", "tesla", "app"]),
        ("ENTRETENIMENTO" if lang == "pt" else "ENTERTAINMENT", ["meme", "viral", "celebr", "cantor", "atriz", "actor", "music", "festival", "gaga", "rihanna", "swift", "kardashian", "beyonc"]),
        ("CULTURA" if lang == "pt" else "CULTURE", ["cultura", "book", "livr", "art", "museum", "teatro"]),
        ("MUNDO" if lang == "pt" else "WORLD", ["war", "guerra", "ukraine", "ucrani", "russia", "israel", "palestin", "world"]),
    ]
    for category, keywords in category_rules:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "ATUALIDADE" if lang == "pt" else "NEWS"


def build_fallback_title(text, lang):
    cleaned = strip_publicity_text(text)
    if not cleaned:
        return "Atualidade" if lang == "pt" else "News"
    words = cleaned.split()
    if len(words) > 12:
        cleaned = " ".join(words[:12])
    return compact_text(cleaned, limit=84)


def build_fallback_publication(news_items, lang):
    if not news_items:
        return None, None, None, None, None, None, None, None, None

    selected_item = select_nvidia_news_items(news_items, max_total=1)[0]
    source_text = selected_item.get("global_context") or selected_item.get("caption") or selected_item.get("raw_caption") or ""
    cleaned_text = strip_publicity_text(source_text) or normalize_text(source_text)
    title = build_fallback_title(cleaned_text, lang)
    caption = compact_text(cleaned_text or title, limit=600)
    category = infer_category_from_text(cleaned_text or title, lang)
    overlay_description = compact_text(title, limit=120)
    image_theme = title

    return (
        category,
        title,
        caption,
        selected_item.get("date", ""),
        "",
        overlay_description,
        image_theme,
        "template_1",
        False,
    )


def build_editorial_context(item):
    primary_context = normalize_text(
        item.get("enriched_context")
        or item.get("global_context")
        or item.get("caption")
        or item.get("raw_caption")
        or ""
    )
    source_profile = normalize_text(item.get("source_profile", ""))
    content_mode = normalize_text(item.get("content_mode", ""))
    media_count = int(item.get("media_count") or 1)
    flags = [str(flag) for flag in item.get("content_flags", []) if str(flag)]

    parts = []
    if source_profile:
        parts.append(f"Source profile: {source_profile}")
    if content_mode:
        parts.append(f"Content mode: {content_mode}")
    if media_count > 1:
        parts.append(f"Media count: {media_count}")
    if flags:
        parts.append(f"Signals: {', '.join(flags)}")
    parts.append("Metadata richness warning: Do not treat richer metadata as evidence that this story is better.")
    if primary_context:
        parts.append(f"Context: {primary_context}")

    return "\n".join(parts).strip()


def filter_headlines_with_ai(candidate_articles, lang):
    global nvidia_pool
    if not nvidia_pool.has_keys():
        return select_arquivo_fallback_indexes(candidate_articles)

    print(f"[{lang}] A filtrar {len(candidate_articles)} cabeçalhos usando a NVIDIA...")


    candidate_pool = select_arquivo_candidate_pool(candidate_articles)
    print(f"[{lang}][Arquivo.pt] Pool editorial para IA: {len(candidate_pool)} de {len(candidate_articles)} candidatos.")

    headlines_text = ""
    for prompt_idx, (_original_idx, art) in enumerate(candidate_pool):
        headlines_text += f"{prompt_idx}: {art['title']} (Fonte: {art['domain']})\n"

    prompt = f"""You are an expert social media editor and journalist managing a high-engagement Instagram page dedicated to nostalgic look-backs, historical ironies, and curious news.
Look at the following list of news headlines from this day in the past. Your task is to select up to 5 index numbers of headlines that align with our global editorial philosophy:

GLOBAL EDITORIAL PHILOSOPHY:
1. NOSTALGIA & RECOGNITION: The headline MUST refer to personalities, brands, organizations, political parties, or concepts that are still highly famous, active, or widely recognized by the general public TODAY (e.g. major political parties like PS/PSD, globally famous athletes/celebrities, or active major politicians).
   * PRIORITIZE: Global pandemics, finals of major international sports competitions, general election victories of major political parties, opening of high-profile judicial investigations against political leaders, landmark controversial laws, and major cultural/technological milestones that remain widely discussed today.
   * TITLE-ONLY OFFICE HOOK: If a past political/social scandal or law is highly interesting/controversial but the person involved is NO LONGER widely famous or popular today, we CAN still select it. The post will refer to them ONLY by their official title/office instead of their name, creating a hook where it looks like the current title-holder did it!
2. HISTORICAL IRONIES & POLITICAL/SOCIAL MILESTONES: Choose major milestones that shaped the political or social landscape, or controversial laws and election results that remain highly discussable, ironic, or interesting when looked back at from a modern perspective.
3. CURIOUS & BIZARRE NEWS: Select human-interest stories, funny occurrences, local oddities, or bizarre happenings that are universally amusing, strange, or relatable. Avoid obscure historical records or dry trivia.
4. STRICT EXCLUSIONS:
   - Absolutely NO routine administrative bureaucracy (minor ministerial meetings, budget statistics, normal policy updates).
   - Absolutely NO minor sports transactions (loans, transfers, or line-ups of ordinary players/coaches who are no longer relevant today).
   - Absolutely NO heavy, tragic, or depressing stories (deaths, fatal accidents, violence, kidnappings, crimes, abuse).

Return a JSON object with exactly this key:
selected_indexes (a list of integers representing the chosen indexes, maximum 5 items)

Headlines list:
{headlines_text}"""

    try:
        response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL)
        save_key_status_to_file()
        payload = json.loads(response_text or "{}")
        indexes = payload.get("selected_indexes", [])
        selected = []
        for x in indexes:
            if not str(x).isdigit():
                continue
            prompt_idx = int(x)
            if 0 <= prompt_idx < len(candidate_pool):
                selected.append(candidate_pool[prompt_idx][0])
        return selected
    except Exception as e:
        print(f"[{lang}] Erro na filtragem de cabecalhos: {e}")
    return select_arquivo_fallback_indexes(candidate_articles)


def get_today_news_from_arquivo(lang, month, day):
    import requests
    import json
    import re
    import time
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    import random

    if lang == "pt":
        sources = [
            {"domain": "publico.pt", "url": "http://www.publico.pt/"},
            {"domain": "expresso.pt", "url": "http://www.expresso.pt/"},
            {"domain": "cmjornal.pt", "url": "http://www.cmjornal.pt/"},
            {"domain": "sabado.pt", "url": "http://www.sabado.pt/"},
            {"domain": "rtp.pt", "url": "http://www.rtp.pt/noticias/"},
            {"domain": "observador.pt", "url": "https://observador.pt/"},
            {"domain": "jn.pt", "url": "https://www.jn.pt/"},
            {"domain": "dn.pt", "url": "https://www.dn.pt/"},
            {"domain": "sicnoticias.pt", "url": "https://sicnoticias.pt/"},
            {"domain": "noticiasaominuto.com", "url": "https://www.noticiasaominuto.com/"},
            {"domain": "record.pt", "url": "https://www.record.pt/"},
            {"domain": "ojogo.pt", "url": "https://www.ojogo.pt/"},
            {"domain": "abola.pt", "url": "https://www.abola.pt/"},
            {"domain": "caras.pt", "url": "https://caras.pt/"},
            {"domain": "flash.pt", "url": "https://www.flash.pt/"},
            {"domain": "tv7dias.pt", "url": "https://www.tv7dias.pt/"},
            {"domain": "holofote.pt", "url": "https://www.holofote.pt/"},
            {"domain": "selfie.iol.pt", "url": "https://selfie.iol.pt/"},
            {"domain": "lux.iol.pt", "url": "https://lux.iol.pt/"},
            {"domain": "nit.pt", "url": "https://www.nit.pt/"},
            {"domain": "timeout.pt", "url": "https://www.timeout.pt/"},
            {"domain": "blitz.pt", "url": "https://blitz.pt/"},
            {"domain": "mag.sapo.pt", "url": "https://mag.sapo.pt/"},
            {"domain": "visao.pt", "url": "https://visao.pt/"},
            {"domain": "exameinformatica.pt", "url": "https://www.exameinformatica.pt/"},
            {"domain": "activa.pt", "url": "https://activa.pt/"},
            {"domain": "maxima.pt", "url": "https://www.maxima.pt/"},
        ]
    else:
        sources = []

    years = list(range(1996, 2026))
    candidate_articles = []
    search_terms = [
        term.strip()
        for term in os.environ.get(
            "ARQUIVO_SEARCH_TERMS",
            "Portugal,noticia,futebol,cultura,politica,economia,famosos,celebridades,musica,cinema,televisao,moda,tecnologia,desporto",
        ).split(",")
        if term.strip()
    ]
    textsearch_global_failures = 0
    textsearch_disabled = False
    homepage_global_failures = 0
    homepage_disabled = False

    for year in years:
        print(f"[{lang}][Arquivo.pt] A pesquisar no ano {year} para o dia {month:02d}-{day:02d}...")
        
        all_extracted = []
        date_str = f"{year}{month:02d}{day:02d}"
        textsearch_url = "https://arquivo.pt/textsearch"

        seen_urls = {item["url"] for item in candidate_articles}

        year_textsearch_failures = 0
        cdxj_candidates = load_arquivo_cdxj_candidates_for_day(year, month, day, sources, seen_urls)
        if cdxj_candidates:
            all_extracted.extend(cdxj_candidates)
            seen_urls.update(item["url"] for item in cdxj_candidates)
            print(f"[{lang}][Arquivo.pt][CDXJ] Ano {year}: {len(cdxj_candidates)} candidatos lidos do indice local.")
        elif textsearch_disabled:
            print(f"[{lang}][Arquivo.pt] Textsearch desativado neste run apos demasiados timeouts. A usar homepage/capas no ano {year}.")
        else:
            for term in search_terms:
                before_term_count = len(all_extracted)
                params = {
                    "q": term,
                    "from": f"{date_str}000000",
                    "to": f"{date_str}235959",
                    "itemsPerPage": 50
                }
                try:
                    res = cached_get(textsearch_url, params=params, timeout=ARQUIVO_TEXTSEARCH_TIMEOUT)
                except Exception as exc:
                    year_textsearch_failures += 1
                    textsearch_global_failures += 1
                    print(f"[{lang}][Arquivo.pt] Falha no termo '{term}' no ano {year}: {exc}")
                    if textsearch_global_failures >= ARQUIVO_TEXTSEARCH_GLOBAL_FAILURE_LIMIT:
                        textsearch_disabled = True
                        print(f"[{lang}][Arquivo.pt] Textsearch com demasiadas falhas neste run; a usar homepage/capas nos anos seguintes.")
                        break
                    if year_textsearch_failures >= ARQUIVO_TEXTSEARCH_MAX_FAILURES_PER_YEAR:
                        print(f"[{lang}][Arquivo.pt] Textsearch lento no ano {year}; a saltar restantes termos e tentar homepage/capas.")
                        break
                    continue

                if res.status_code != 200:
                    if res.status_code >= 500:
                        year_textsearch_failures += 1
                        textsearch_global_failures += 1
                        if textsearch_global_failures >= ARQUIVO_TEXTSEARCH_GLOBAL_FAILURE_LIMIT:
                            textsearch_disabled = True
                            print(f"[{lang}][Arquivo.pt] Textsearch com demasiados erros neste run; a usar homepage/capas nos anos seguintes.")
                            break
                        if year_textsearch_failures >= ARQUIVO_TEXTSEARCH_MAX_FAILURES_PER_YEAR:
                            print(f"[{lang}][Arquivo.pt] Textsearch devolveu erros no ano {year}; a tentar homepage/capas.")
                            break
                    continue

                data = json.loads(res.text)
                response_items = data.get("responseItems") or data.get("response_items") or []

                for item in response_items:
                    title = item.get("title", "").strip()
                    url = item.get("originalURL", "").strip()
                    timestamp = item.get("tstamp", "").strip()

                    if not title or len(title) < 15:
                        continue

                    title_lower = title.lower()
                    heavy_words = [
                        "morre", "morto", "morte", "rapto", "raptado", "abuso", "abusa", "viola", 
                        "violada", "violador", "assassina", "homicídio", "crime", "suicídio", 
                        "tragédia", "pedofilia", "guerra", "falece", "falecimento", "assassina",
                        "dies", "died", "death", "kidnap", "kidnapped", "abuse", "rape", "murder", 
                        "murdered", "homicide", "suicide", "tragedy", "pedophilia", "war", "fatal"
                    ]
                    if any(w in title_lower for w in heavy_words):
                        continue

                    path = url.lower()
                    exclude = [
                        "/opiniao/", "/editorial/", "/tag/",
                        "/autor/", "/comentarios/", "/page/", "/feed/", "/wp-json/",
                        "/wp-admin/", "/comments/", "/blogs/", "/opinion/"
                    ]
                    if any(x in path for x in exclude):
                        continue

                    include = [
                        "/politica/", "/economia/", "/desporto/", "/sociedade/", "/cultura/", "/local/", "/insolito/",
                        "/gente/", "/bizarro/", "/curioso/", "/famosos/", "/vida/",
                        "/champions/", "/mundial/", "/euro/", "/espetaculo/", "/entertainment/",
                        "/showbiz/", "/sport/", "/lifestyle/", "/odd/", "/weird/", "/bizarre/",
                        "/noticias/", "/pais/", "/mundo/"
                    ]

                    is_article = (
                        "/noticia/" in path
                        or "/article/" in path
                        or path.endswith(".html")
                        or any(x in path for x in include)
                        or ".asp" in path
                        or "/jornal/noticia/" in path
                        or "/shownews.asp" in path
                    )

                    if is_article:
                        matched_domain = None
                        for source in sources:
                            if source["domain"] in path:
                                matched_domain = source["domain"]
                                break
                        if not matched_domain:
                            continue

                        if url not in seen_urls:
                            all_extracted.append({
                                "url": url,
                                "title": f"[{year}] {title}",
                                "snippet": item.get("snippet", "") or item.get("text", ""),
                                "timestamp": timestamp,
                                "domain": matched_domain,
                                "year": year
                            })
                            seen_urls.add(url)
                if len(all_extracted) > before_term_count:
                    pass

        if not all_extracted and homepage_disabled:
            print(f"[{lang}][Arquivo.pt] Homepage/capas desativadas neste run apos demasiados timeouts. A saltar ano {year}.")

        if not all_extracted and not homepage_disabled:
            year_homepage_failures = 0
            for src in sources:
                if year_homepage_failures >= ARQUIVO_HOMEPAGE_MAX_FAILURES_PER_YEAR:
                    print(f"[{lang}][Arquivo.pt] Homepages lentas no ano {year}; a saltar restantes fontes deste ano.")
                    break
                if (
                    homepage_global_failures >= ARQUIVO_HOMEPAGE_GLOBAL_FAILURE_LIMIT
                    and len(candidate_articles) >= ARQUIVO_DEGRADED_MIN_CANDIDATES
                ):
                    homepage_disabled = True
                    print(f"[{lang}][Arquivo.pt] Homepages/capas com demasiadas falhas. A usar os candidatos ja recolhidos.")
                    break
                homepage_replay_url = f"https://arquivo.pt/noFrame/replay/{date_str}120000/{src['url']}"
                try:
                    home_res = cached_get(homepage_replay_url, timeout=ARQUIVO_HOMEPAGE_TIMEOUT)
                except Exception as exc:
                    year_homepage_failures += 1
                    homepage_global_failures += 1
                    print(f"[{lang}][Arquivo.pt] Falha homepage {src['domain']} no ano {year}: {exc}")
                    continue
                if home_res.status_code != 200:
                    if home_res.status_code >= 500:
                        year_homepage_failures += 1
                        homepage_global_failures += 1
                    continue

                soup = BeautifulSoup(home_res.content, "html.parser")
                for anchor in soup.find_all("a"):
                    title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
                    href = (anchor.get("href") or "").strip()
                    if not href or len(title) < 18:
                        continue

                    timestamp = date_str + "120000"
                    replay_match = re.search(r"/replay/(\d{14})/(https?://.+)$", href)
                    if replay_match:
                        timestamp = replay_match.group(1)
                        url = replay_match.group(2)
                    else:
                        url = urljoin(src["url"], href)

                    path = url.lower()
                    if src["domain"] not in path:
                        continue
                    if url in seen_urls:
                        continue

                    title_lower = title.lower()
                    heavy_words = [
                        "morre", "morto", "morte", "rapto", "raptado", "abuso", "abusa", "viola",
                        "violada", "violador", "assassina", "homicídio", "crime", "suicídio",
                        "tragédia", "pedofilia", "guerra", "falece", "falecimento",
                        "dies", "died", "death", "kidnap", "kidnapped", "abuse", "rape", "murder",
                        "murdered", "homicide", "suicide", "tragedy", "pedophilia", "war", "fatal"
                    ]
                    if any(w in title_lower for w in heavy_words):
                        continue

                    exclude = [
                        "/opiniao/", "/editorial/", "/tag/", "/autor/", "/comentarios/",
                        "/page/", "/feed/", "/wp-json/", "/wp-admin/", "/comments/",
                        "/blogs/", "/opinion/"
                    ]
                    if any(x in path for x in exclude):
                        continue

                    include = [
                        "/politica/", "/economia/", "/desporto/", "/sociedade/", "/cultura/",
                        "/local/", "/insolito/", "/gente/", "/bizarro/", "/curioso/",
                        "/famosos/", "/vida/", "/champions/", "/mundial/", "/euro/",
                        "/espetaculo/", "/entertainment/", "/showbiz/", "/sport/",
                        "/lifestyle/", "/odd/", "/weird/", "/bizarre/", "/noticias/",
                        "/pais/", "/mundo/"
                    ]
                    is_article = (
                        "/noticia/" in path
                        or "/article/" in path
                        or path.endswith(".html")
                        or any(x in path for x in include)
                        or ".asp" in path
                        or "/jornal/noticia/" in path
                        or "/shownews.asp" in path
                    )
                    if not is_article:
                        continue

                    all_extracted.append({
                        "url": url,
                        "title": f"[{year}] {title}",
                        "snippet": title,
                        "timestamp": timestamp,
                        "domain": src["domain"],
                        "year": year
                    })
                    seen_urls.add(url)

        if all_extracted:
            candidate_articles.extend(all_extracted)
            print(f"[{lang}][Arquivo.pt] Ano {year}: Obtidos {len(all_extracted)} links candidatos. Seguindo para o proximo ano...")

        if (
            textsearch_disabled
            and homepage_disabled
            and len(candidate_articles) >= ARQUIVO_DEGRADED_MIN_CANDIDATES
        ):
            print(f"[{lang}][Arquivo.pt] Modo degradado: encontrados {len(candidate_articles)} candidatos. A parar recolha deste dia para evitar timeouts.")
            break

    if not candidate_articles:
        return []

    print(f"[{lang}][Arquivo.pt] Encontrados {len(candidate_articles)} candidatos no total de todos os anos. A selecionar com a IA...")

    selected_indices = filter_headlines_with_ai(candidate_articles, lang)
    if not selected_indices:
        selected_indices = select_arquivo_fallback_indexes(candidate_articles)

    matching_news = []
    for idx in selected_indices:
        if idx >= len(candidate_articles):
            continue
        art = candidate_articles[idx]

        replay_url = f"https://arquivo.pt/noFrame/replay/{art['timestamp']}/{art['url']}"
        print(f"[{lang}][Arquivo.pt] A descarregar corpo do artigo ({art['year']}): {replay_url}...")
        body_text = ""
        page_title = ""
        try:
            art_res = cached_get(replay_url, timeout=ARQUIVO_HOMEPAGE_TIMEOUT)
            if art_res.status_code == 200:
                art_soup = BeautifulSoup(art_res.content, "html.parser")

                for s in art_soup(["script", "style", "nav", "footer", "header", "aside"]):
                    s.decompose()

                heading = art_soup.find(["h1", "h2"])
                title_tag = art_soup.find("title")
                page_title = normalize_text(
                    (heading.get_text(" ", strip=True) if heading else "")
                    or (title_tag.get_text(" ", strip=True) if title_tag else "")
                )
                page_title = re.sub(r"\s+[-|].*$", "", page_title).strip()
                paragraphs = [p.get_text().strip() for p in art_soup.find_all("p") if len(p.get_text().strip()) > 30]
                body_text = " ".join(paragraphs[:8])
        except Exception as e:
            pass

        article_title = art["title"].replace(f"[{art['year']}] ", "")
        if page_title and len(page_title) >= 12 and "arquivo.pt" not in page_title.lower():
            article_title = page_title
        fallback_context = " ".join(
            value.strip()
            for value in [
                article_title,
                str(art.get("snippet", "") or ""),
            ]
            if value and value.strip()
        )
        context = body_text if len(body_text) > 100 else fallback_context
        if len(context) > 30:
            matching_news.append({
                "url": art["url"],
                "source_url": replay_url,
                "date": f"{art['year']}-{month:02d}-{day:02d} 12:00:00",
                "title": article_title,
                "global_context": context,
                "source_profile": art["domain"],
                "published": False
            })

    return matching_news


def get_today_news(lang):
    today = datetime.now()


    try:
        arquivo_news = get_today_news_from_arquivo(lang, today.month, today.day)
        if arquivo_news:
            print(f"[{lang}] Obtidos {len(arquivo_news)} artigos com sucesso do Arquivo.pt.")
            return arquivo_news
    except Exception as e:
        print(f"[{lang}] Falha ao buscar no Arquivo.pt ({e}). A usar base de dados local como fallback...")


    posts = load_posts_for_date(lang, today.month, today.day)

    matching = []
    for item in posts:
        if item.get("published", False):
            continue
        try:
            item_date = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
            if item_date.day == today.day and item_date.year < today.year:
                matching.append(item)
        except ValueError:
            continue
    return matching


def get_event_historical_news(lang, search_keywords):
    from archive_storage import load_all_posts
    try:
        all_posts = load_all_posts(lang)
    except Exception as e:
        print(f"Erro ao carregar todos os posts do arquivo: {e}")
        return []
        
    matching = []
    for item in all_posts:
        if item.get("published", False):
            continue

        texts = []
        for key in ["global_context", "raw_caption", "title", "ai_summary"]:
            if item.get(key):
                texts.append(str(item[key]))
        options = item.get("options", [])
        if options and isinstance(options, list):
            for opt in options:
                if opt.get("title"):
                    texts.append(str(opt["title"]))
                if opt.get("summary"):
                    texts.append(str(opt["summary"]))
        
        full_text = " ".join(texts).lower()
        
        matched = False
        for kw in search_keywords:
            if kw.lower() in full_text:
                matched = True
                break
        if matched:
            matching.append(item)
            
    return matching


def mark_items_as_published(lang, items_to_mark):
    if not items_to_mark:
        return

    by_block = {}
    for item in items_to_mark:
        month = int(item["date"][5:7])
        day = int(item["date"][8:10])
        block_id = block_id_for_month_day(month, day)
        by_block.setdefault(block_id, []).append(item)

    for block_id, daily_items in by_block.items():
        shortcodes_to_mark = set()
        for daily_item in daily_items:
            shortcodes_to_mark.update(daily_item.get("shortcodes", []))

        posts = load_block(lang, block_id)
        for post in posts:
            if shortcodes_to_mark.intersection(set(post.get("shortcodes", []))):
                post["published"] = True
        save_block(lang, block_id, posts)

    print(f"[{lang}] Noticia(s) marcadas como 'published'.")


def process_daily_news_with_ai(news_items, lang, custom_prompt_instructions=None):
    global NVIDIA_DISABLED

    if not news_items:
        return None, None, None, None, None, None, None, None, None

    if NVIDIA_DISABLED or not nvidia_pool.has_keys():
        return build_fallback_publication(news_items, lang)

    selected_news_items = select_nvidia_news_items(news_items)
    if not selected_news_items:
        return build_fallback_publication(news_items, lang)

    if len(selected_news_items) < len(news_items):
        print(f"[{lang}] A reduzir o input para {len(selected_news_items)} de {len(news_items)} publicacoes antes de chamar a IA...")

    print(f"[{lang}] A enviar {len(selected_news_items)} publicacoes para a NVIDIA ({NVIDIA_MODEL})...")
    context_list = ""

    for idx, item in enumerate(selected_news_items):
        text = compact_text(build_editorial_context(item))
        context_list += f"\n--- PUBLICACAO {idx + 1} ---\n{text}\n"

    if custom_prompt_instructions:
        prompt = f"""You are an expert news editor and social media manager managing a high-engagement Instagram page dedicated to nostalgic look-backs, historical ironies, and curious news.
Look at the following raw news publications from exactly this day/event in the past. Your task is to:
1. Identify the most relevant story that aligns with our GLOBAL EDITORIAL PHILOSOPHY:
   - NOSTALGIA & RECOGNITION: The story MUST refer to personalities, brands, organizations, political parties, or concepts that are still highly famous, active, or widely recognized by the general public TODAY (e.g., major political parties like PS/PSD, globally famous athletes or celebrities, active major politicians).
     * PRIORITIZE: Global pandemics, finals of major international sports competitions, general election victories of major political parties, opening of high-profile judicial investigations against political leaders, landmark controversial laws, and major cultural/technological milestones that remain widely discussed today.
     * TITLE-ONLY OFFICE HOOK: If a past political/social scandal or law is highly interesting/controversial but the person involved is NO LONGER widely famous or popular today, refer to them ONLY by their official title/office instead of their name, creating a hook where it looks like the current title-holder did it!
   - HISTORICAL IRONIES & POLITICAL/SOCIAL MILESTONES: Choose major milestones that shaped the political or social landscape, or controversial laws and election results that remain highly discussable, ironic, or interesting when looked back at from a modern perspective.
   - CURIOUS & BIZARRE NEWS: Select human-interest stories, funny occurrences, local oddities, or bizarre happenings that are universally amusing, strange, or relatable. Avoid obscure historical records or dry trivia.
   - STRICT EXCLUSIONS: Absolutely NO routine administrative bureaucracy, NO minor sports transactions (loans, transfers, or line-ups of ordinary players/coaches who are no longer relevant today), and absolutely NO heavy, tragic, or depressing stories (deaths, fatal accidents, violence, kidnappings, crimes, abuse).
   - ENDURING VALUE: Routine institutional birthdays, age-count announcements, congratulatory ceremonies, and publicity-led anniversaries are low-value. Only choose anniversary coverage when it contains a substantive event that remains worth reading without the anniversary number.
2. Determine a short category in uppercase (max 2 words, category should be related to the event, e.g. "MUNDIAL", "FESTIVAL", "CHAMPIONS").
3. Write a short, punchy title for the image overlay. (Use the TITLE-ONLY OFFICE HOOK if applicable).
4. Choose highlight_text as either an empty string or 1 to 3 words from the title. Prefer just 1 word. Only choose highlight_text when it improves the design and editorial emphasis.
5. Write overlay_description as a short sentence for the image overlay, ideally 8 to 16 words, with no hashtags and no call to action.
6. Write image_theme as a short visual search query, ideally 2 to 5 words, that would help find a fitting background image.
7. Choose layout_preference from: "template_1", "template_2", "template_3", "template_4".
8. Set breaking_candidate to true or false.
9. Write the post caption based on the following instructions:
   {custom_prompt_instructions}
   Write a well-written, engaging post for social media in {lang.upper()}. (Use the TITLE-ONLY OFFICE HOOK if applicable).
10. Remove any calls to action and original hashtags.

Write your response in Portuguese.
Return a JSON object with exactly these keys:
category, title, highlight_text, overlay_description, image_theme, layout_preference, breaking_candidate, caption

News Items:
{context_list}"""
    elif lang == "pt":
        prompt = f"""You are an expert news editor and journalist managing a high-engagement Instagram page dedicated to nostalgic look-backs, historical ironies, and curious news.
Look at the following raw news publications from exactly this day in the past. Your task is to:
1. Identify the single story that best aligns with our GLOBAL EDITORIAL PHILOSOPHY:
   - NOSTALGIA & RECOGNITION: The story MUST refer to personalities, brands, organizations, political parties, or concepts that are still highly famous, active, or widely recognized by the general public TODAY (e.g., major political parties like PS/PSD, globally famous athletes or celebrities, active major politicians).
     * PRIORITIZE: Global pandemics, finals of major international sports competitions, general election victories of major political parties, opening of high-profile judicial investigations against political leaders, landmark controversial laws, and major cultural/technological milestones that remain widely discussed today.
     * TITLE-ONLY OFFICE HOOK: If a past political/social scandal or law is highly interesting/controversial but the person involved is NO LONGER widely famous or popular today, refer to them ONLY by their official title/office instead of their name, creating a hook where it looks like the current title-holder did it!
   - HISTORICAL IRONIES & POLITICAL/SOCIAL MILESTONES: Choose major milestones that shaped the political or social landscape, or controversial laws and election results that remain highly discussable, ironic, or interesting when looked back at from a modern perspective.
   - CURIOUS & BIZARRE NEWS: Select human-interest stories, funny occurrences, local oddities, or bizarre happenings that are universally amusing, strange, or relatable. Avoid obscure historical records or dry trivia.
   - STRICT EXCLUSIONS: Absolutely NO routine administrative bureaucracy, NO minor sports transactions (loans, transfers, or line-ups of ordinary players/coaches who are no longer relevant today), and absolutely NO heavy, tragic, or depressing stories (deaths, fatal accidents, violence, kidnappings, crimes, abuse).
   - ENDURING VALUE: Routine institutional birthdays, age-count announcements, congratulatory ceremonies, and publicity-led anniversaries are low-value. Only choose anniversary coverage when it contains a substantive event that remains worth reading without the anniversary number.
2. Determine a short category in uppercase (max 2 words, examples: "ATUALIDADE", "POLITICA", "MUNDO", "DESPORTO", "ECONOMIA", "CIENCIA", "TECNOLOGIA", "CULTURA").
3. Write a short, punchy title for the image overlay. (Use the TITLE-ONLY OFFICE HOOK if applicable).
4. Choose highlight_text as either an empty string or 1 to 3 words that already appear exactly in the title. Prefer just 1 word. Only choose highlight_text when it improves the design and editorial emphasis.
5. Write overlay_description as a short sentence for the image overlay, ideally 8 to 16 words, with no hashtags and no call to action.
6. Write image_theme as a short visual search query, ideally 2 to 5 words, that would help find a fitting background image.
7. If this is not breaking news, choose layout_preference from: "template_1", "template_2", "template_3", "template_4".
   - template_1: strongest default for longer titles and text placed lower left with description
   - template_2: cleaner centered composition near the top half
   - template_3: photo-led composition with centered lower title
   - template_4: same as template_1 but cleaner, with no shadow, only when the text area can stay simple
8. Set breaking_candidate to true only if this clearly deserves the special breaking layout. Otherwise false.
9. Rewrite the story of that specific event into an expanded, well-written mini-summary for the post caption. You must completely use your own words (to avoid copyright issues). (Use the TITLE-ONLY OFFICE HOOK if applicable).
10. Write like a strong social editor, not a formal newspaper archive. It can feel lively and culturally aware, focusing on nostalgia and recognition, while staying accurate.
11. Pretend you are publishing this news ON THE VERY DAY IT HAPPENED. NEVER say things like "hoje faz X anos", "neste dia", or "noticia antiga".
12. VERY IMPORTANT: Remove any calls to action such as 'link na bio', 'lê mais', 'subscreve', and remove original hashtags.

Write your response in Portuguese.
Return a JSON object with exactly these keys:
category, title, highlight_text, overlay_description, image_theme, layout_preference, breaking_candidate, caption

News Items:
{context_list}"""
    else:
        prompt = f"""You are an expert news editor and journalist managing a high-engagement Instagram page dedicated to nostalgic look-backs, historical ironies, and curious news.
Look at the following raw news publications from exactly this day in the past. Your task is to:
1. Identify the single story that best aligns with our GLOBAL EDITORIAL PHILOSOPHY:
   - NOSTALGIA & RECOGNITION: The story MUST refer to personalities, brands, organizations, political parties, or concepts that are still highly famous, active, or widely recognized by the general public TODAY (e.g., major political parties like PS/PSD, globally famous athletes or celebrities, active major politicians).
     * PRIORITIZE: Global pandemics, finals of major international sports competitions, general election victories of major political parties, opening of high-profile judicial investigations against political leaders, landmark controversial laws, and major cultural/technological milestones that remain widely discussed today.
     * TITLE-ONLY OFFICE HOOK: If a past political/social scandal or law is highly interesting/controversial but the person involved is NO LONGER widely famous or popular today, refer to them ONLY by their official title/office instead of their name, creating a hook where it looks like the current title-holder did it!
   - HISTORICAL IRONIES & POLITICAL/SOCIAL MILESTONES: Choose major milestones that shaped the political or social landscape, or controversial laws and election results that remain highly discussable, ironic, or interesting when looked back at from a modern perspective.
   - CURIOUS & BIZARRE NEWS: Select human-interest stories, funny occurrences, local oddities, or bizarre happenings that are universally amusing, strange, or relatable. Avoid obscure historical records or dry trivia.
   - STRICT EXCLUSIONS: Absolutely NO routine administrative bureaucracy, NO minor sports transactions (loans, transfers, or line-ups of ordinary players/coaches who are no longer relevant today), and absolutely NO heavy, tragic, or depressing stories (deaths, fatal accidents, violence, kidnappings, crimes, abuse).
   - ENDURING VALUE: Routine institutional birthdays, age-count announcements, congratulatory ceremonies, and publicity-led anniversaries are low-value. Only choose anniversary coverage when it contains a substantive event that remains worth reading without the anniversary number.
2. Determine a short category in uppercase (max 2 words, examples: "NEWS", "POLITICS", "WORLD", "SPORTS", "ECONOMY", "SCIENCE", "TECHNOLOGY", "CULTURE").
3. Write a short, punchy title for the image overlay. (Use the TITLE-ONLY OFFICE HOOK if applicable).
4. Choose highlight_text as either an empty string or 1 to 3 words that already appear exactly in the title. Prefer just 1 word. Only choose highlight_text when it improves the design and editorial emphasis.
5. Write overlay_description as a short sentence for the image overlay, ideally 8 to 16 words, with no hashtags and no call to action.
6. Write image_theme as a short visual search query, ideally 2 to 5 words, that would help find a fitting background image.
7. If this is not breaking news, choose layout_preference from: "template_1", "template_2", "template_3", "template_4".
   - template_1: strongest default for longer titles and text placed lower left with description
   - template_2: cleaner centered composition near the top half
   - template_3: photo-led composition with centered lower title
   - template_4: same as template_1 but cleaner, with no shadow, only when the text area can stay simple
8. Set breaking_candidate to true only if this clearly deserves the special breaking layout. Otherwise false.
9. Rewrite the story of that specific event into an expanded, well-written mini-summary for the post caption. You must completely use your own words (to avoid copyright issues). (Use the TITLE-ONLY OFFICE HOOK if applicable).
10. Write like a strong social editor, not a formal newspaper archive. It can feel lively and culturally aware, focusing on nostalgia and recognition, while staying accurate.
11. Pretend you are publishing this news ON THE VERY DAY IT HAPPENED. NEVER say things like "X years ago today", "on this day", or "old news".
12. VERY IMPORTANT: Remove any calls to action and original hashtags.

Write your response in English.
Return a JSON object with exactly these keys:
category, title, highlight_text, overlay_description, image_theme, layout_preference, breaking_candidate, caption

News Items:
{context_list}"""

    max_retries = 3
    for attempt in range(max_retries):
        if not nvidia_pool.has_keys():
            break
        try:
            response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL)
            save_key_status_to_file()
            payload = json.loads(response_text or "{}")
            category = normalize_text(payload.get("category", "ATUALIDADE" if lang == "pt" else "NEWS"), uppercase=True)
            title = normalize_text(payload.get("title", ""))
            highlight_text = normalize_text(payload.get("highlight_text", ""))
            overlay_description = normalize_text(payload.get("overlay_description", ""))
            image_theme = normalize_text(payload.get("image_theme", ""))
            layout_preference = str(payload.get("layout_preference", "template_1")).strip().lower().replace("-", "_")
            breaking_candidate = bool(payload.get("breaking_candidate", False))
            new_caption = normalize_text(payload.get("caption", ""))

            if not title or not new_caption:
                return None, None, None, None, None, None, None, None, None

            return (
                category,
                title,
                new_caption,
                selected_news_items[0]["date"],
                highlight_text,
                overlay_description,
                image_theme,
                layout_preference,
                breaking_candidate,
            )
        except Exception as e:
            err_msg = str(e).lower()
            is_quota = "429" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "quota" in err_msg
            if is_quota:
                if ("day" in err_msg or "daily" in err_msg) and "minute" not in err_msg:
                    print(f"\n[{lang}][NVIDIA] {get_current_key_info()} atingiu limite de API. A rodar...")
                    nvidia_pool.mark_current_exhausted()
                if rotate_nvidia_client():
                    continue
            print(f"[{lang}][NVIDIA] Erro na publicacao (tentativa {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                if any(marker in str(e).lower() for marker in NVIDIA_ERROR_MARKERS):
                    NVIDIA_DISABLED = True
                    print(f"[{lang}] NVIDIA indisponivel na publicacao: {e}")
                return build_fallback_publication(selected_news_items, lang)
    return build_fallback_publication(selected_news_items, lang)


def is_within_posting_hours(lang):
    try:
        tz_name = "Europe/Lisbon" 
        local_hour = datetime.now(ZoneInfo(tz_name)).hour
        return 8 <= local_hour <= 22
    except Exception:
        return True


def load_publish_state(filepath="publish_state.json"):
    default = {
        "pt": {"date": "", "morning_posted": False, "afternoon_posted": False, "last_post_time": None},
        "en": {"date": "", "morning_posted": False, "afternoon_posted": False, "last_post_time": None},
    }
    if not os.path.exists(filepath):
        return default
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_publish_state(state, filepath="publish_state.json"):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)


def get_approved_post(lang, slot_idx, date_str, filepath="pending_posts.json"):
    if not os.path.exists(filepath):
        return None, []
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            pending_posts = json.load(f)
        except json.JSONDecodeError:
            return None, []
    target_id = f"{lang}_{date_str}_{slot_idx}"
    for post in pending_posts:
        if (
            post.get("id") == target_id
            and post.get("status") == "approved"
            and not post.get("review_action")
        ):
            return post, pending_posts
    return None, pending_posts


def create_image_with_text(
    category_to_draw,
    title_to_draw,
    lang,
    template_path="template.jpg",
    overlay_path="overlay.png",
    output_path="output.jpg",
    description_to_draw="",
    highlight_text="",
    layout_name="auto",
    layout_preference="",
    breaking_candidate=False,
    background_query="",
    manual_background_url="",
):
    result = render_post_image(
        category_to_draw,
        title_to_draw,
        lang,
        template_path=template_path,
        overlay_path=overlay_path,
        output_path=output_path,
        description_to_draw=description_to_draw,
        highlight_text=highlight_text,
        layout_name=layout_name,
        layout_preference=layout_preference,
        breaking_candidate=breaking_candidate,
        background_query=background_query,
        manual_background_url=manual_background_url,
    )
    print(f"[{lang}] Imagem guardada: {output_path}")
    return result


def publish_to_instagram(image_url, caption, lang):
    token = IG_CREDENTIALS.get(lang, {}).get("token")
    user_id = IG_CREDENTIALS.get(lang, {}).get("user_id")
    if not token or not user_id:
        print(f"[{lang}] Credenciais Instagram nao configuradas.")
        return {"success": False}
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{user_id}/media",
            data={"image_url": image_url, "caption": caption, "access_token": token},
        )
        res_data = res.json()
        if "id" not in res_data:
            print("Erro Media Container:", res_data)
            return False
        pub = requests.post(
            f"https://graph.facebook.com/v25.0/{user_id}/media_publish",
            data={"creation_id": res_data["id"], "access_token": token},
        )
        pub_data = pub.json()
        if "id" in pub_data:
            instagram_id = pub_data["id"]
            permalink = ""
            try:
                details = requests.get(
                    f"https://graph.facebook.com/v25.0/{instagram_id}",
                    params={"fields": "permalink", "access_token": token},
                    timeout=20,
                )
                details_data = details.json()
                permalink = details_data.get("permalink", "")
            except Exception as details_exc:
                print(f"[{lang}] Publicado, mas nao foi possivel obter permalink: {details_exc}")
            print(f"[{lang}] Publicado! Post ID: {instagram_id}")
            return {"success": True, "id": instagram_id, "permalink": permalink}
        print("Erro ao publicar:", pub_data)
        return {"success": False}
    except Exception as e:
        print(f"[{lang}] Excecao API: {e}")
        return {"success": False}


def main():
    state = load_publish_state()

    for lang in ["pt"]:
        tz_name = "Europe/Lisbon" 
        tz = ZoneInfo(tz_name)
        local_now = datetime.now(tz)
        local_hour = local_now.hour
        local_date_str = local_now.strftime("%Y-%m-%d")

        if state.setdefault(lang, {}).get("date") != local_date_str:
            state[lang] = {
                "date": local_date_str,
                "morning_posted": False,
                "afternoon_posted": False,
                "last_post_time": state[lang].get("last_post_time"),
            }
            save_publish_state(state)

        if not is_within_posting_hours(lang):
            print(f"[{lang}] Fora do horario permitido (08h-22h local). A saltar.")
            continue

        if 8 <= local_hour < 14:
            current_slot, slot_idx, hours_left = "morning", 1, 13 - local_hour
        else:
            current_slot, slot_idx, hours_left = "afternoon", 2, 21 - local_hour

        if state[lang].get(f"{current_slot}_posted", False):
            print(f"[{lang}] Ja publicado na janela '{current_slot}'.")
            continue

        last_post_str = state[lang].get("last_post_time")
        if last_post_str:
            time_diff = (local_now - datetime.fromisoformat(last_post_str)).total_seconds() / 3600
            if time_diff < 4.0:
                print(f"[{lang}] Minimo de 4h nao cumprido ({time_diff:.1f}h). A saltar.")
                continue

        if hours_left > 0 and random.random() > 1.0 / max(hours_left, 1):
            print(f"[{lang}] Decisao aleatoria: Adiamento.")
            continue

        print(f"[{lang}] A publicar no slot '{current_slot}'...")

        output_image_path = f"post_{lang}.jpg"
        final_caption = ""
        historical_news_of_chosen_day = []
        is_event_mode = False
        event = None

        approved_entry, pending_posts = get_approved_post(lang, slot_idx, local_date_str)
        used_approved_post = False

        if approved_entry:
            sel_idx = approved_entry.get("selected_option", 0)
            options = approved_entry.get("options", [])
            if options and sel_idx < len(options):
                option = options[sel_idx]
                final_caption = normalize_text(option.get("caption", ""))
                year = option.get("year")
                if year:
                    for item in get_today_news(lang):
                        if item["date"].startswith(year):
                            historical_news_of_chosen_day.append(item)

                layout_override = str(approved_entry.get("layout_override", "")).strip().lower().replace("-", "_")
                theme_suggestion = normalize_text(approved_entry.get("theme_suggestion", ""))
                manual_background_url = normalize_text(approved_entry.get("manual_background_url", ""))
                needs_rerender = bool(layout_override or theme_suggestion or manual_background_url or not option.get("image_url"))

                if needs_rerender:
                    try:
                        create_image_with_text(
                            normalize_text(option.get("category", "ATUALIDADE" if lang == "pt" else "NEWS"), uppercase=True),
                            normalize_text(option.get("title", "")),
                            lang,
                            output_path=output_image_path,
                            description_to_draw=normalize_text(option.get("overlay_description", "")),
                            highlight_text=normalize_text(option.get("highlight_text", "")),
                            layout_name=layout_override or "auto",
                            layout_preference=option.get("layout_preference", "template_1"),
                            breaking_candidate=bool(option.get("breaking_candidate", False)),
                            background_query=normalize_text(theme_suggestion or option.get("image_theme", "") or option.get("title", "")),
                            manual_background_url=manual_background_url,
                            year=year,
                        )
                        used_approved_post = True
                    except Exception as e:
                        print(f"[{lang}] Erro ao re-renderizar post aprovado: {e}.")
                        img_url = option.get("image_url")
                        if img_url:
                            try:
                                if copy_image_reference_to_path(img_url, output_image_path):
                                    used_approved_post = True
                                    print(f"[{lang}] Fallback para preview já aprovada após falha de re-render.")
                            except Exception as fallback_exc:
                                print(f"[{lang}] Também falhou o fallback da preview aprovada: {fallback_exc}.")
                else:
                    img_url = option.get("image_url")
                    try:
                        if copy_image_reference_to_path(img_url, output_image_path):
                            used_approved_post = True
                    except Exception as e:
                        print(f"[{lang}] Erro imagem pre-aprovada: {e}. Fallback Live AI.")

        if not used_approved_post:

            calendar_path = "flexible_events_calendar.json"
            if os.path.exists(calendar_path):
                try:
                    with open(calendar_path, "r", encoding="utf-8") as f:
                        calendar_events = json.load(f)
                    for ev in calendar_events:
                        if ev.get("date") == local_date_str:
                            if current_slot in ev.get("slots", []):
                                if lang in ev.get("langs", ["pt", "en"]):
                                    event_posted_key = f"event_{ev['id']}_posted"
                                    if not state[lang].get(event_posted_key, False):
                                        event = ev
                                        break
                except Exception as ev_err:
                    print(f"[{lang}] Erro ao ler calendario de eventos flexiveis: {ev_err}")

            custom_instructions = None
            matching_news = []
            if event:
                print(f"[{lang}] Evento flexivel detetado para hoje: {event['name']}!")
                matching_news = get_event_historical_news(lang, event.get("search_keywords", []))
                if matching_news:
                    is_event_mode = True
                    custom_instructions = event.get("prompt_instructions")
                    print(f"[{lang}] Encontrados {len(matching_news)} artigos historicos relacionados.")
                else:
                    print(f"[{lang}] Nenhum artigo historico encontrado para o evento. Usando fluxo diario normal.")

            if not is_event_mode:
                matching_news = get_today_news(lang)
                if not matching_news:
                    print(f"[{lang}] Sem noticias para hoje.")
                    continue

            news_by_year = {}
            for item in matching_news:
                year = item["date"][:4]
                news_by_year.setdefault(year, []).append(item)

            chosen_year = random.choice(list(news_by_year.keys()))
            historical_news_of_chosen_day = news_by_year[chosen_year]
            print(f"[{lang}] {len(historical_news_of_chosen_day)} publicacoes do ano {chosen_year}...")

            (
                category,
                short_title,
                rewritten_caption,
                actual_date,
                highlight_text,
                overlay_description,
                image_theme,
                layout_preference,
                breaking_candidate,
            ) = process_daily_news_with_ai(historical_news_of_chosen_day, lang, custom_prompt_instructions=custom_instructions)
            del actual_date

            if not short_title or not rewritten_caption:
                print(f"[{lang}] IA falhou. Publicacao cancelada.")
                continue

            create_image_with_text(
                category,
                short_title,
                lang,
                output_path=output_image_path,
                description_to_draw=overlay_description,
                highlight_text=highlight_text,
                layout_preference=layout_preference,
                breaking_candidate=breaking_candidate,
                background_query=normalize_text(image_theme or short_title),
                year=chosen_year,
            )
            hashtags = "#Noticias #Atualidade #Jornalismo" if lang == "pt" else ""
            final_caption = normalize_text(f"{rewritten_caption}\n\n{hashtags}")

        imgbb_api_key = os.environ.get("IMGBB_API_KEY")
        if imgbb_api_key:
            try:
                with open(output_image_path, "rb") as img_file:
                    imgbb_res = requests.post(
                        "https://api.imgbb.com/1/upload",
                        data={"key": imgbb_api_key},
                        files={"image": img_file},
                    )
                imgbb_data = imgbb_res.json()

                if imgbb_data.get("success"):
                    upload_data = imgbb_data.get("data", {})
                    public_image_url = upload_data["url"]
                    delete_url = upload_data.get("delete_url", "")
                    publish_result = publish_to_instagram(public_image_url, final_caption, lang)
                    success = bool(publish_result.get("success")) if isinstance(publish_result, dict) else bool(publish_result)

                    if success:
                        instagram_id = publish_result.get("id", "") if isinstance(publish_result, dict) else ""
                        instagram_url = publish_result.get("permalink", "") if isinstance(publish_result, dict) else ""
                        register_imgbb_upload(
                            {
                                "kind": "published_post",
                                "lang": lang,
                                "date": local_date_str,
                                "slot": current_slot,
                                "post_id": approved_entry.get("id", "") if approved_entry else "",
                                "image_url": public_image_url,
                                "delete_url": delete_url,
                                "instagram_id": instagram_id,
                                "instagram_url": instagram_url,
                                "published_at": datetime.now().isoformat(),
                            }
                        )
                        mark_items_as_published(lang, historical_news_of_chosen_day)

                        if is_event_mode and event:
                            state[lang][f"event_{event['id']}_posted"] = True

                        if used_approved_post and approved_entry:
                            approved_entry["status"] = "published"
                            approved_entry["instagram_id"] = instagram_id
                            approved_entry["instagram_url"] = instagram_url
                            approved_entry["published_at"] = datetime.now().isoformat()
                            with open("pending_posts.json", "w", encoding="utf-8") as pf:
                                json.dump(pending_posts, pf, ensure_ascii=False, indent=4)

                        state[lang][f"{current_slot}_posted"] = True
                        state[lang]["last_post_time"] = local_now.isoformat()
                        save_publish_state(state)
                else:
                    print(f"[{lang}] Erro IMGBB: {imgbb_data}")
            except Exception as e:
                print(f"[{lang}] Excecao IMGBB: {e}")
        else:
            print(f"[{lang}] IMGBB_API_KEY nao configurado. Imagem guardada localmente.")


if __name__ == "__main__":
    main()
