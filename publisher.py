import json
import os
import random
import re
import shutil
import sys
import unicodedata
import gzip
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import requests

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

    news_domains = {
        "publico.pt", "dn.pt", "jn.pt", "observador.pt", "sicnoticias.pt",
        "rtp.pt", "expresso.pt", "noticiasaominuto.com", "abola.pt",
        "record.pt", "ojogo.pt",
    }
    magazine_domains = {
        "caras.pt", "flash.pt", "tv7dias.pt", "holofote.pt", "selfie.iol.pt",
        "lux.iol.pt", "nit.pt", "timeout.pt", "blitz.pt", "mag.sapo.pt",
        "activa.pt", "maxima.pt", "exameinformatica.pt",
    }
    weak_terms = [
        "agenda", "programacao", "horoscopo", "meteorologia", "farmacias",
        "transito", "obituario", "classificados", "opiniao", "artigo de opiniao",
        "cronica", "saldos", "promocao", "promoção", "desconto", "descontos",
        "liquidacao", "liquidação", "loja", "lojas", "compras", "shopping",
        "outlet", "catalogo", "catálogo", "festival", "concerto", "cinema",
        "filme", "serie", "album", "cancao", "oscar", "globo de ouro",
        "famosos", "celebridades", "locais habituais", "nas bancas", "debate",
        "duelo", "entrevista", "comentario", "sondagem", "intencao de voto",
        "convencao", "secretariado", "sair das listas", "apura-se", "apurado",
        "meias-finais", "quartos-de-final", "oitavos-de-final", "terceiro lugar",
        "fase de grupos", "gemeos", "filhos", "gravida", "casamento", "ferias",
        "podcast", "video-opiniao", "galeria", "fotos da semana",
        # Rotina administrativa, burocracia menor e notas processuais recorrentes
        "renova estado de emergencia", "renovacao do estado de emergencia",
        "tabela taxas", "taxas de entrega", "mefedrona", "adia extincao",
        "adia por seis meses", "evita encerramento do governo", "orcamento parcial",
        "orcamento provisorio", "revogacao de decretos", "edificios mais eficientes",
        "alimentacao saudavel nas escolas", "derrame de petroleo", "inspecao do sef",
    ]

    if domain in news_domains:
        score += 4
    elif domain in magazine_domains:
        score -= 6

    for term in weak_terms:
        if term in text:
            score -= 6

    title_clean = normalize_text(item.get("title", ""))
    words = title_clean.split()
    if 5 <= len(words) <= 18:
        score += 2
    if re.search(r"\b[A-Z][\w-]+(?:\s+[A-Z][\w-]+){1,3}\b", title_clean):
        score += 2
    if "/tag/" in text or "/autor/" in text or "/opiniao/" in text:
        score -= 8

    # Prioritize major domestic/national news sections over routine sub-feeds
    if any(p in text for p in ["/pais/", "/nacional/", "/sociedade/", "/politica/"]):
        score += 6
    elif any(p in text for p in ["/economia/", "/mundo/"]):
        score += 3
    if "/lusa/" in text or "/comunicados/" in text or "/fugas." in text or "/cinecartaz." in text:
        score -= 8
    if any(p in text for p in ["estudo conclui", "cientistas estudam", "investigadores de", "laboratorio pioneiro"]):
        score -= 6
    if any(p in text for p in ["esqueleto", "ossadas", "tumulo", "túmulo", "fossil", "fóssil", "arqueolog", "milenares", "adega"]):
        score -= 10
    if any(p in text for p in ["venezuela", "maduro", "peru", "bolivia", "guatemala", "nicaragua"]):
        score -= 4

    # Structural impact keywords: executive decisions, emergencies, collective measures, major trials
    structural_terms = [
        "governo", "estado", "supremo", "tribunal", "parlamento", "lei", "decreto", "decreta",
        "aprova", "encerra", "encerramento", "fecha", "fecho", "suspende", "suspensao",
        "escola", "escolas", "aulas", "ensino", "universidade", "universidades",
        "alerta", "emergencia", "emergência", "quarentena", "confinamento", "saude publica", "saúde pública",
        "hospitais", "pandemia", "condena", "prisao", "prisão", "fraude",
        "acordo", "tratado", "soberania", "fronteira", "fronteiras", "europa", "uniao europeia"
    ]
    for st in structural_terms:
        if st in text:
            score += 4
    return score


def select_arquivo_candidate_pool(candidate_articles, max_total=ARQUIVO_AI_MAX_CANDIDATES):
    indexed = list(enumerate(candidate_articles))
    if len(indexed) <= max_total:
        return indexed

    # Group by year first so 2000-2017 get equal representation alongside 2018-2025
    by_year = {}
    for pair in indexed:
        _idx, item = pair
        year = str(item.get("year") or item.get("timestamp") or "")[:4] or "0000"
        by_year.setdefault(year, []).append(pair)

    for year, items in by_year.items():
        items.sort(
            key=lambda pair: (
                score_arquivo_candidate(pair[1]),
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

    # Round-robin across all available years (oldest and newest interleaved)
    sorted_years = sorted(by_year.keys())
    max_rounds = max((len(v) for v in by_year.values()), default=0)
    for r in range(max_rounds):
        if len(selected) >= max_total:
            break
        for y in sorted_years:
            if r < len(by_year[y]):
                add(by_year[y][r])

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


_CDXJ_SKIP_MARKERS = (
    "/tag/", "/tags/", "/opiniao/", "/opinion/", "/autor/", "/author/",
    "/feed/", "/wp-json/", "/wp-admin/", "/comments/", "/comentarios/",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js",
    ".woff", ".mp4", ".mp3", ".pdf", ".xml", ".json", ".rss",
    '"status": "30', '"status": "40', '"status": "50',
    '"mime": "image/', '"mime": "application/javascript', '"mime": "text/css',
)


def iter_cdxj_records(path):
    opener = gzip.open if str(path).lower().endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line or line[0] == "#":
                    continue
                line_low = line.lower()
                if any(m in line_low for m in _CDXJ_SKIP_MARKERS):
                    continue
                line = line.strip()
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
    segments = [seg for seg in path.split("/") if seg and not seg.isdigit()]
    slug = segments[-1] if segments else ""
    slug = re.sub(r"\.[a-z0-9]{2,6}$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"^(?:19|20)\d{2}[-_/]\d{1,2}[-_/]\d{1,2}[-_/]*", "", slug)
    slug = re.sub(r"[-_/]+(?:v?\d{5,}|\d{1,2})$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip(" -_/")
    alpha_words = [w for w in slug.split() if re.search(r"[a-zA-ZÀ-ÿ]{3,}", w)]
    if not slug or len(slug) < 14 or len(alpha_words) < 3:
        return ""
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
    local_seen_titles = set()
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

            # Reject non-news subdomains and foreign portals
            url_low = url.lower()
            if any(bad in url_low for bad in [
                "fugas.publico.pt", "cinecartaz.publico.pt", "blogues.publico.pt",
                "comunique.publico.pt", "acervo.publico.pt", "fazemosbem.jn.pt",
                "noticiasaominuto.com.br", ".dgrdn.pt", "/opiniao/", "/editorial/",
                "/horoscopo", "/classificados", "/newsletter", "/passatempos/"
            ]):
                continue

            # Enforce year coherence: if URL contains an explicit year segment, it must match current year
            m_year_seg = re.search(r"/(19\d\d|20\d\d)[-_/]", url)
            if m_year_seg and int(m_year_seg.group(1)) != int(year):
                continue

            title = normalize_text(record.get("title") or record.get("metadata", {}).get("title") or "")
            if not title or len(title) < 8:
                title = title_from_url(url)
            if not title or "pagina arquivada em" in title.lower():
                continue

            norm_title_key = re.sub(r"[^a-z0-9]+", "", title.lower())
            if len(norm_title_key) >= 12 and norm_title_key in local_seen_titles:
                continue
            local_seen_titles.add(norm_title_key)
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

    if len(candidates) > 35:
        candidates.sort(key=score_arquivo_candidate, reverse=True)
        # Keep top candidates while preserving domain diversity
        diverse = []
        domain_counts = {}
        for c in candidates:
            d = c.get("domain", "")
            if domain_counts.get(d, 0) >= 6:
                continue
            diverse.append(c)
            domain_counts[d] = domain_counts.get(d, 0) + 1
            if len(diverse) >= 30:
                break
        candidates = diverse

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
        return None, None, None, None, None, None, None, None, None, None, None, None, None

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
        ["instagram"],
        caption,
        caption,
        caption,
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


def filter_headlines_with_ai(candidate_articles, lang, max_items=15):
    global nvidia_pool
    if not nvidia_pool.has_keys():
        return select_arquivo_fallback_indexes(candidate_articles, max_total=max_items)

    print(f"[{lang}] A filtrar {len(candidate_articles)} cabeçalhos usando a NVIDIA...")


    candidate_pool = select_arquivo_candidate_pool(candidate_articles)
    print(f"[{lang}][Arquivo.pt] Pool editorial para IA: {len(candidate_pool)} de {len(candidate_articles)} candidatos.")

    headlines_text = ""
    for prompt_idx, (_original_idx, art) in enumerate(candidate_pool):
        headlines_text += f"{prompt_idx}: {art['title']} (Fonte: {art['domain']})\n"

    prompt = f"""You are the editorial director selecting archival news headlines from this calendar day across different years.
Your task is to select up to {max_items} distinct index numbers of headlines (covering diverse years and topics) strictly following these objective editorial standards:

1. FACTUAL IMPORTANCE & COLLECTIVE SCALE (HIGHEST PRIORITY):
   - Prioritize events of broad collective scale that directly alter, restrict, or condition daily life, public services, education, health, institutional functioning, or free movement of the population and nation.
   - ABSOLUTE TOP PRIORITY: official executive decisions, declarations of emergency or alert states, nationwide suspensions or closures of public facilities/schools/universities/services, major judicial sentences of national significance, landmark international treaties or conflicts.
   - GEOGRAPHICAL & CIVIL FOCUS: For this Portuguese-language publication, prioritize national-scope events (Portugal/EU) and major global geopolitical milestones. STRICTLY REJECT remote domestic news of third countries (e.g. municipal/local health decrees in Liberia, smog in Beijing, provincial decrees in Latin America/Asia/Africa) whenever Portuguese or European events exist.
   - STRICTLY DOWNGRADE/REJECT: minor sectoral curiosities, incremental scientific studies without immediate civil consequence, instrument calibrations, archaeological discoveries (fossils, bones, ancient tombs/cellars), celebrity leisure, routine administrative notices.

2. TEMPORAL PLAUSIBILITY (NO ANACHRONISMS WHEN READ TODAY):
   - When the archival year is not shown, the headline should read like a factual event happening today.
   - INSTITUTIONAL ROLE PRINCIPLE: If a past formal action was carried out by someone who no longer holds that office today, the headline must be framed around the institutional office/entity rather than the former officeholder's personal name.
   - Exclude stories centered on personal statements, candidacies, or political maneuvers by retired, inactive, or detained individuals whose situation today contradicts the news.

3. STRICT NEGATIVE EXCLUSIONS:
   - REJECT declarative noise: personal opinions, mutual verbal accusations, praise, warnings, hypothetical musings, or demands for clarification between public figures.
   - REJECT routine administrative/procedural items: periodic decree renewals (e.g. routine 15-day renewals of states of emergency), procedural deadline extensions (e.g. postponing agency extinctions by six months), minor platform/delivery fee caps, technical drug schedule updates, foreign government budget shutdown avoidance votes, routine EU directives (building energy efficiency, fruit/milk distribution in schools), administrative revocation of obsolete laws, or remote minor local environmental incidents.
   - REJECT internal organic politics: party conventions, leadership races, list dispute dramas, or electoral polling projections.
   - REJECT personal/family life of celebrities or public figures.
   - REJECT entertainment, cinema, music awards, concerts, festivals, commercial promotions, and tragic deaths/funerals.
   - In tournament sports, reject preliminary or intermediate stages (qualifications, quarter-finals, semi-finals, third-place matches); only final championship title victories are eligible.

4. THEMATIC CADENCE & SATURATION LIMITS:
   - Strictly avoid topic saturation: At least 3 days of interval between news of the same macro-theme (e.g. Covid-19/pandemia, repeated judicial cases, recurring disputes).
   - Maximum 8 stories on the same macro-theme per 30-day window. Even during high-intensity years (like 2020-2021 with the pandemic), do not oversaturate the feed with repetitive pandemic news; diversify into other historical milestones of the era.
   - Maximize chronological diversity across all available years (from 1996 to 2025). Do not cluster around a single year or a single theme.
   - Do not select multiple headlines about the same entity or topic on the same day.

Return a JSON object with exactly this key:
selected_indexes (a list of integers representing the chosen indexes, maximum {max_items} items)

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
                orig_idx = candidate_pool[prompt_idx][0]
                if orig_idx not in selected:
                    selected.append(orig_idx)
        # Guarantee historical year diversity (2000-2019) alongside recent years
        pre2020_selected = [
            idx for idx in selected
            if str(candidate_articles[idx].get("year", "9999"))[:4] < "2020"
        ]
        if len(pre2020_selected) < 6:
            for orig_idx, art in candidate_pool:
                if str(art.get("year", "9999"))[:4] < "2020" and orig_idx not in selected:
                    selected.append(orig_idx)
                    pre2020_selected.append(orig_idx)
                    if len(pre2020_selected) >= 6:
                        break
        if len(selected) < min(12, max_items):
            for fallback_idx in select_arquivo_fallback_indexes(candidate_articles, max_total=max_items):
                if fallback_idx not in selected:
                    selected.append(fallback_idx)
                if len(selected) >= max_items:
                    break
        return selected[:max_items]
    except Exception as e:
        print(f"[{lang}] Erro na filtragem de cabecalhos: {e}")
    return select_arquivo_fallback_indexes(candidate_articles, max_total=max_items)


def get_today_news_from_arquivo(lang, month, day, max_items=15):
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

    # Filtro opcional por fontes (popular_site.py --jornal / ARQUIVO_SOURCE_DOMAINS).
    _domain_filter = [item.strip().lower() for item in os.environ.get("ARQUIVO_SOURCE_DOMAINS", "").split(",") if item.strip()]
    if _domain_filter:
        sources = [source for source in sources if str(source.get("domain", "")).lower() in _domain_filter]

    # Intervalo de anos configurável (ARQUIVO_SEARCH_YEAR_START/END) para
    # acelerar runs locais e permitir foco em épocas com índice pesquisável.
    year_start = int(os.environ.get("ARQUIVO_SEARCH_YEAR_START", "1996"))
    year_end = int(os.environ.get("ARQUIVO_SEARCH_YEAR_END", "2026"))
    years = list(range(year_start, year_end))
    candidate_articles = []
    seen_urls = set()

    # 1. Passagem rápida pelo índice CDXJ local (D:\arquivo_cdxj)
    for year in years:
        cdxj_candidates = load_arquivo_cdxj_candidates_for_day(year, month, day, sources, seen_urls)
        if cdxj_candidates:
            candidate_articles.extend(cdxj_candidates)
            seen_urls.update(item["url"] for item in cdxj_candidates)
            print(f"[{lang}][Arquivo.pt][CDXJ] Ano {year}: {len(cdxj_candidates)} candidatos lidos do indice local.")

    # 2. Só recorrer a pesquisa online (textsearch/homepages) se o índice local não tiver candidatos suficientes
    if len(candidate_articles) < 100:
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
            year_textsearch_failures = 0

            if textsearch_disabled:
                print(f"[{lang}][Arquivo.pt] Textsearch desativado neste run apos demasiados timeouts. A usar homepage/capas no ano {year}.")
            else:
                for term in search_terms:
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
                            break
                        if year_textsearch_failures >= ARQUIVO_TEXTSEARCH_MAX_FAILURES_PER_YEAR:
                            break
                        continue

                    if res.status_code != 200:
                        if res.status_code >= 500:
                            year_textsearch_failures += 1
                            textsearch_global_failures += 1
                            if textsearch_global_failures >= ARQUIVO_TEXTSEARCH_GLOBAL_FAILURE_LIMIT:
                                textsearch_disabled = True
                                break
                            if year_textsearch_failures >= ARQUIVO_TEXTSEARCH_MAX_FAILURES_PER_YEAR:
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
                            "tragédia", "pedofilia", "falece", "falecimento", "assassina",
                            "dies", "died", "death", "kidnap", "kidnapped", "abuse", "rape", "murder", 
                            "murdered", "homicide", "suicide", "tragedy", "pedophilia", "fatal"
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

            if not all_extracted and not homepage_disabled:
                year_homepage_failures = 0
                for src in sources:
                    if year_homepage_failures >= ARQUIVO_HOMEPAGE_MAX_FAILURES_PER_YEAR:
                        break
                    if (
                        homepage_global_failures >= ARQUIVO_HOMEPAGE_GLOBAL_FAILURE_LIMIT
                        and len(candidate_articles) >= ARQUIVO_DEGRADED_MIN_CANDIDATES
                    ):
                        homepage_disabled = True
                        break
                    homepage_replay_url = f"https://arquivo.pt/noFrame/replay/{date_str}120000/{src['url']}"
                    try:
                        home_res = cached_get(homepage_replay_url, timeout=ARQUIVO_HOMEPAGE_TIMEOUT)
                    except Exception:
                        year_homepage_failures += 1
                        homepage_global_failures += 1
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
                        if src["domain"] not in path or url in seen_urls:
                            continue

                        title_lower = title.lower()
                        heavy_words = [
                            "morre", "morto", "morte", "rapto", "raptado", "abuso", "abusa", "viola",
                            "violada", "violador", "assassina", "homicídio", "crime", "suicídio",
                            "tragédia", "pedofilia", "falece", "falecimento",
                            "dies", "died", "death", "kidnap", "kidnapped", "abuse", "rape", "murder",
                            "murdered", "homicide", "suicide", "tragedy", "pedophilia", "fatal"
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
                break

    if not candidate_articles:
        return []

    print(f"[{lang}][Arquivo.pt] Encontrados {len(candidate_articles)} candidatos no total de todos os anos. A selecionar com a IA...")

    selected_indices = filter_headlines_with_ai(candidate_articles, lang, max_items=max_items)
    if not selected_indices:
        selected_indices = select_arquivo_fallback_indexes(candidate_articles, max_total=max_items)

    boilerplate_markers = (
        "obrigado por subscrever",
        "primeira newsletter",
        "subscreva a newsletter",
        "receba as principais notícias",
        "utilizamos cookies",
        "política de privacidade",
        "erro 404",
        "página não encontrada",
        "arquivo.pt",
    )

    from concurrent.futures import ThreadPoolExecutor

    def _fetch_one_selected(idx):
        if idx >= len(candidate_articles):
            return None
        art = candidate_articles[idx]
        replay_url = f"https://arquivo.pt/noFrame/replay/{art['timestamp']}/{art['url']}"
        wayback_url = f"https://arquivo.pt/wayback/{art['timestamp']}/{art['url']}"
        body_text = ""
        page_title = ""
        try:
            art_res = cached_get(replay_url, timeout=6)
            if art_res.status_code == 200:
                art_soup = BeautifulSoup(art_res.content, "html.parser")

                for s in art_soup(["script", "style", "nav", "footer", "header", "aside"]):
                    s.decompose()

                for tag_name in ("h1", "title", "h2"):
                    for candidate_tag in art_soup.find_all(tag_name):
                        candidate_text = normalize_text(candidate_tag.get_text(" ", strip=True))
                        candidate_text = re.sub(r"\s+[-|].*$", "", candidate_text).strip()
                        if (
                            len(candidate_text) >= 15
                            and not any(m in candidate_text.lower() for m in boilerplate_markers)
                        ):
                            page_title = candidate_text
                            break
                    if page_title:
                        break

                paragraphs = [
                    p.get_text(" ", strip=True)
                    for p in art_soup.find_all("p")
                    if len(p.get_text(" ", strip=True)) > 30
                    and not any(m in p.get_text(" ", strip=True).lower() for m in boilerplate_markers)
                ]
                body_text = " ".join(paragraphs[:8])

                # Extrair ano real de publicacao original a partir dos metadados HTML
                # (evita atribuir o ano do crawl do Arquivo.pt a uma noticia de ano anterior)
                real_year = None
                for meta_prop in [
                    "article:published_time", "article:modified_time", "datePublished",
                    "pubdate", "publishdate", "dc.date", "sailthru.date", "parsely-pub-date"
                ]:
                    m_tag = art_soup.find("meta", attrs={"property": re.compile(meta_prop, re.I)}) or art_soup.find(
                        "meta", attrs={"name": re.compile(meta_prop, re.I)}
                    )
                    if m_tag and m_tag.get("content"):
                        m_val = m_tag.get("content").strip()
                        m_match = re.search(r"(19\d\d|20\d\d)", m_val)
                        if m_match:
                            real_year = int(m_match.group(1))
                            break
                if not real_year:
                    t_tag = art_soup.find("time")
                    if t_tag:
                        t_val = t_tag.get("datetime") or t_tag.get_text()
                        m_match = re.search(r"(19\d\d|20\d\d)", t_val)
                        if m_match:
                            real_year = int(m_match.group(1))
                if real_year and 1990 <= real_year <= 2026:
                    art["year"] = real_year
        except Exception:
            pass

        article_title = art["title"].replace(f"[{art['year']}] ", "")
        if page_title and len(page_title) >= 12 and not any(m in page_title.lower() for m in boilerplate_markers):
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
            return {
                "url": art["url"],
                "source_url": wayback_url,
                "date": f"{art['year']}-{month:02d}-{day:02d} 12:00:00",
                "title": article_title,
                "global_context": context,
                "source_profile": art["domain"],
                "domain": art["domain"],
                "source_platform": "arquivo.pt",
                "published": False,
            }
        return None

    matching_news = []
    with ThreadPoolExecutor(max_workers=6) as pool_exec:
        for item in pool_exec.map(_fetch_one_selected, selected_indices):
            if item:
                matching_news.append(item)

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
        return None, None, None, None, None, None, None, None, None, None, None, None, None

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
9. Add "networks": a JSON array choosing which of our social networks this story fits: "instagram", "facebook", "x".
   - Instagram: visual, nostalgic, desporto, cultura, estrelas, curiosidades.
   - Facebook: política, sociedade, economia, marcos nacionais, discussão geral (público maduro 35-65+).
   - X: política, economia, ciência, tecnologia, mundial, debate atualizado (público instruído).
   - Most stories belong to ONE network. Use two only when the story genuinely fits both audiences. Use all three only for historic landmark / major event stories (level 1-2).
10. Rewrite the story of that specific event into an expanded, well-written mini-summary for the post caption. You must completely use your own words (to avoid copyright issues). (Use the TITLE-ONLY OFFICE HOOK if applicable).
11. Write like a strong social editor, not a formal newspaper archive. It can feel lively and culturally aware, focusing on nostalgia and recognition, while staying accurate.
12. Pretend you are publishing this news ON THE VERY DAY IT HAPPENED. NEVER say things like "hoje faz X anos", "neste dia", or "noticia antiga".
13. VERY IMPORTANT: Remove any calls to action such as 'link na bio', 'lê mais', 'subscreve', and remove original hashtags.
14. PLATFORM-SPECIFIC CAPTIONS:
- Do NOT start the caption with the year (e.g. NEVER start with "Em 2015," or "No ano de 2021,"). Integrate the year naturally inside or towards the end of the narrative phrase (e.g. "A Assembleia da República viveu um momento inédito na democracia em 2021: ...").
- Standard disclaimer MUST follow: "Este post apenas tem o objetivo de relembrar acontecimentos passados da história nunca representando acontecimentos atuais. Esta notícia é de [ANO]."
- For "caption_instagram": include link phrase "🔗 Lê a notícia completa no link da bio." and hashtags "#NoticiasDeOntem #ArquivoPT #[Category]" (e.g. #Politica, #Mundo, #Sociedade). NEVER use #atualidade.
- For "caption_facebook": include link phrase "🔗 Lê a notícia completa no link do sobre do perfil." and hashtags "#NoticiasDeOntem #ArquivoPT #[Category]". NEVER use #atualidade.

Write your response in Portuguese.
Return a JSON object with exactly these keys:
category, title, highlight_text, overlay_description, image_theme, layout_preference, breaking_candidate, networks, caption_instagram, caption_facebook, caption_x

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
9. Add "networks": a JSON array choosing which of our social networks this story fits: "instagram", "facebook", "x".
   - Instagram: visual, nostalgic, sports, culture, celebrities, curiosities.
   - Facebook: politics, society, economy, national milestones, general discussion (mature audience 35-65+).
   - X: politics, economy, science, technology, world news, real-time debate (informed audience).
   - Most stories belong to ONE network. Use two only when the story genuinely fits both audiences. Use all three only for historic landmark / major event stories (level 1-2).
10. Rewrite the story of that specific event into an expanded, well-written mini-summary for the post caption. You must completely use your own words (to avoid copyright issues). (Use the TITLE-ONLY OFFICE HOOK if applicable).
11. Write like a strong social editor, not a formal newspaper archive. It can feel lively and culturally aware, focusing on nostalgia and recognition, while staying accurate.
12. Pretend you are publishing this news ON THE VERY DAY IT HAPPENED. NEVER say things like "X years ago today", "on this day", or "old news".
13. VERY IMPORTANT: Remove any calls to action and original hashtags.
14. PLATFORM-SPECIFIC CAPTIONS: Write "caption_instagram" (visual, engaging, nostalgic tone with emojis), "caption_facebook" (discussion-oriented, invites comments), and "caption_x" (short, under 280 chars, punchy, current-events style). Each should be adapted to its platform's audience while covering the same story.

Write your response in English.
Return a JSON object with exactly these keys:
category, title, highlight_text, overlay_description, image_theme, layout_preference, breaking_candidate, networks, caption_instagram, caption_facebook, caption_x

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
            networks = payload.get("networks", ["instagram"])
            if not isinstance(networks, list):
                networks = ["instagram"]
            networks = [str(n).strip().lower() for n in networks if str(n).strip().lower() in ("instagram", "facebook", "x")]
            if not networks:
                networks = ["instagram"]
            caption_instagram = normalize_text(payload.get("caption_instagram", "") or payload.get("caption", ""))
            caption_facebook = normalize_text(payload.get("caption_facebook", "") or payload.get("caption", ""))
            caption_x = normalize_text(payload.get("caption_x", "") or payload.get("caption", ""))
            new_caption = normalize_text(payload.get("caption", ""))

            if not title or not new_caption:
                return None, None, None, None, None, None, None, None, None, None, None, None, None

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
                networks,
                caption_instagram,
                caption_facebook,
                caption_x,
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
        "pt": {
            "date": "",
            "instagram": {"morning_posted": False, "evening_posted": False, "morning_story_posted": False, "evening_story_posted": False, "last_post_time": None},
            "facebook": {"morning_posted": False, "evening_posted": False, "morning_story_posted": False, "evening_story_posted": False, "last_post_time": None},
        },
        "en": {
            "date": "",
            "instagram": {"morning_posted": False, "evening_posted": False, "morning_story_posted": False, "evening_story_posted": False, "last_post_time": None},
            "facebook": {"morning_posted": False, "evening_posted": False, "morning_story_posted": False, "evening_story_posted": False, "last_post_time": None},
        },
    }
    if not os.path.exists(filepath):
        return default
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            state = json.load(f)
        except json.JSONDecodeError:
            return default
    # Migrate old flat state to per-platform structure
    for lang in ("pt", "en"):
        if lang not in state:
            state[lang] = default[lang]
            continue
        lang_state = state[lang]
        if "date" not in lang_state:
            lang_state["date"] = ""
        if "instagram" not in lang_state:
            lang_state["instagram"] = {
                "morning_posted": bool(lang_state.get("morning_posted", False)),
                "evening_posted": bool(lang_state.get("afternoon_posted", False)),
                "last_post_time": lang_state.get("last_post_time"),
            }
        if "facebook" not in lang_state:
            lang_state["facebook"] = {
                "morning_posted": bool(lang_state.get("morning_posted", False)),
                "evening_posted": bool(lang_state.get("afternoon_posted", False)),
                "last_post_time": lang_state.get("last_post_time"),
            }
    for lang in ("pt", "en"):
        for pname in ("instagram", "facebook"):
            pstate = state.get(lang, {}).get(pname, {})
            if isinstance(pstate, dict):
                pstate.setdefault("morning_story_posted", False)
                pstate.setdefault("evening_story_posted", False)
    return state


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
        # Um post aprovado que ja foi publicado numa rede mas falhou noutra
        # fica com status "published" e sem URL nessa rede: tem de voltar a
        # ser devolvido para a rede em falta voltar a tenta-lo, em vez de
        # cair no caminho da IA, que geraria um post diferente.
        status_ok = post.get("status") == "approved" or (
            post.get("status") == "published"
            and (not post.get("instagram_url") or not post.get("facebook_url")
                 or not post.get("instagram_story_id") or not post.get("facebook_story_id"))
        )
        if (
            post.get("id") == target_id
            and status_ok
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
    year=None,
    relevance_level=None,
    **kwargs,
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
        year=year,
        relevance_level=relevance_level,
        **kwargs,
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
            timeout=60,
        )
        res_data = res.json()
        if "id" not in res_data:
            print("Erro Media Container:", res_data)
            return False
        # O Instagram pode demorar a processar a imagem: o primeiro
        # media_publish falha muitas vezes com 9007 "Media ID is not
        # available". Foi o que aconteceu na run das 20:58 de 27 out
        # (Instagram falhou, Facebook publicou). Voltar a tentar com
        # espera, em vez de marcar logo a publicacao como falhada.
        pub_data = {}
        for _attempt in range(6):
            pub = requests.post(
                f"https://graph.facebook.com/v25.0/{user_id}/media_publish",
                data={"creation_id": res_data["id"], "access_token": token},
                timeout=60,
            )
            pub_data = pub.json()
            if "id" in pub_data:
                break
            err = pub_data.get("error", {}) if isinstance(pub_data, dict) else {}
            if err.get("code") == 9007 or "not available" in str(err.get("message", "")).lower():
                print(f"[{lang}] Instagram ainda a processar a imagem, a voltar a tentar publicar...")
                import time as _time
                _time.sleep(20)
                continue
            break
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


def publish_instagram_story(image_url, lang):
    """Publica a mesma imagem como Story do Instagram (24h, sem legenda).

    Fluxo Graph API igual ao do feed, mas com media_type=STORIES e sem
    caption (o Instagram ignora legenda em Stories). Best-effort: devolve
    o id da story ou False, nunca levanta excecao, para uma falha na
    story nao transformar um post do feed ja publicado num falhado.
    """
    token = IG_CREDENTIALS.get(lang, {}).get("token")
    user_id = IG_CREDENTIALS.get(lang, {}).get("user_id")
    if not token or not user_id:
        print(f"[{lang}] Story Instagram: credenciais nao configuradas.")
        return False
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{user_id}/media",
            data={"image_url": image_url, "media_type": "STORIES", "access_token": token},
            timeout=60,
        )
        res_data = res.json()
        if "id" not in res_data:
            print(f"[{lang}] Story Instagram: erro no container:", res_data)
            return False
        pub_data = {}
        for _attempt in range(3):
            pub = requests.post(
                f"https://graph.facebook.com/v25.0/{user_id}/media_publish",
                data={"creation_id": res_data["id"], "access_token": token},
                timeout=60,
            )
            pub_data = pub.json()
            if "id" in pub_data:
                break
            err = pub_data.get("error", {}) if isinstance(pub_data, dict) else {}
            if err.get("code") == 9007 or "not available" in str(err.get("message", "")).lower():
                print(f"[{lang}] Story Instagram ainda a processar, a voltar a tentar...")
                import time as _time
                _time.sleep(10)
                continue
            break
        if "id" in pub_data:
            print(f"[{lang}] Story Instagram publicada! ID: {pub_data['id']}")
            return pub_data["id"]
        print(f"[{lang}] Story Instagram: erro ao publicar:", pub_data)
        return False
    except Exception as e:
        print(f"[{lang}] Story Instagram: excecao API: {e}")
        return False


def main():
    state = load_publish_state()

    for lang in ["pt"]:
        tz_name = "Europe/Lisbon"
        tz = ZoneInfo(tz_name)
        local_now = datetime.now(tz)
        local_hour = local_now.hour
        local_date_str = local_now.strftime("%Y-%m-%d")

        # Reset state per day with new per-platform structure
        lang_state = state.setdefault(lang, {})
        if lang_state.get("date") != local_date_str:
            lang_state.clear()
            lang_state.update({
                "date": local_date_str,
                "instagram": {"morning_posted": False, "evening_posted": False, "morning_story_posted": False, "evening_story_posted": False, "last_post_time": None},
                "facebook": {"morning_posted": False, "evening_posted": False, "morning_story_posted": False, "evening_story_posted": False, "last_post_time": None},
            })
            save_publish_state(state)

        if not is_within_posting_hours(lang):
            print(f"[{lang}] Fora do horario permitido (08h-22h local). A saltar.")
            continue

        # Determine which platforms have a posting window now
        platforms_to_post = []

        # Todas as redes: janela 1 = 8-14h, janela 2 = 17-22h
        for pname in ("instagram", "facebook"):
            pstate = lang_state.get(pname, {})
            morning_pending = not pstate.get("morning_posted", False) or not pstate.get("morning_story_posted", False)
            evening_pending = not pstate.get("evening_posted", False) or not pstate.get("evening_story_posted", False)
            if 8 <= local_hour < 14 and morning_pending:
                platforms_to_post.append((pname, "morning", 1))
            elif 17 <= local_hour < 22 and evening_pending:
                platforms_to_post.append((pname, "evening", 2))

        if not platforms_to_post:
            print(f"[{lang}] Nenhuma rede com janela de publicacao agora.")
            continue

        # Random delay (opcional, nao e obrigatorio publicar).
        # Excecao: a ultima run de cada janela publica sempre, sem sorteio.
        # Janela da manha 8-14h -> ultima hora 13; janela da tarde 17-22h -> ultima hora 21.
        last_hour_of_window = 13 if local_hour < 14 else 21
        hours_left = 22 - local_hour
        if local_hour != last_hour_of_window and hours_left > 0 and random.random() > 1.0 / max(hours_left, 1):
            print(f"[{lang}] Decisao aleatoria: Adiamento.")
            continue

        print(f"[{lang}] Plataformas a publicar agora: {[p[0] for p in platforms_to_post]}")

        output_image_path = f"post_{lang}.jpg"
        historical_news_of_chosen_day = []
        used_approved_post = False
        approved_entry = None
        pending_posts = []
        option = None
        networks = ["instagram"]
        caption_instagram = ""
        caption_facebook = ""
        category = "ATUALIDADE"
        short_title = ""
        overlay_description = ""
        image_theme = ""
        layout_preference = "template_1"
        breaking_candidate = False
        chosen_year = ""

        # Try to get an approved post for the first available platform slot
        approved_entry_found = False
        for pname, pslot, pidx in platforms_to_post:
            approved_entry, pending_posts = get_approved_post(lang, pidx, local_date_str)
            if approved_entry:
                approved_entry_found = True
                option = None
                sel_idx = approved_entry.get("selected_option", 0)
                options = approved_entry.get("options", [])
                if options and sel_idx < len(options):
                    option = options[sel_idx]
                    networks = option.get("networks", ["instagram"])
                    if not isinstance(networks, list):
                        networks = ["instagram"]
                    caption_instagram = normalize_text(option.get("caption_instagram", "") or option.get("caption", ""))
                    caption_facebook = normalize_text(option.get("caption_facebook", "") or option.get("caption", ""))
                    caption_x = normalize_text(option.get("caption_x", "") or option.get("caption", ""))
                    year = option.get("year")
                    # Post aprovado ja traz tudo (legenda, titulo, ano, imagem):
                    # nao ir buscar candidatos ao Arquivo aqui. O get_today_news
                    # e lento no runner (sem indice local, pesquisas online) e
                    # so servia para marcar itens como publicados, o que nao e
                    # preciso no caminho do post aprovado.

                    category = normalize_text(option.get("category", "ATUALIDADE" if lang == "pt" else "NEWS"), uppercase=True)
                    short_title = normalize_text(option.get("title", ""))
                    overlay_description = normalize_text(option.get("overlay_description", ""))
                    image_theme = normalize_text(option.get("image_theme", "") or option.get("title", ""))
                    layout_preference = str(option.get("layout_preference", "template_1")).strip().lower().replace("-", "_")
                    breaking_candidate = bool(option.get("breaking_candidate", False))
                    chosen_year = str(year) if year else ""

                    layout_override = str(approved_entry.get("layout_override", "")).strip().lower().replace("-", "_")
                    theme_suggestion = normalize_text(approved_entry.get("theme_suggestion", ""))
                    manual_background_url = normalize_text(approved_entry.get("manual_background_url", ""))
                    needs_rerender = bool(layout_override or theme_suggestion or manual_background_url or not option.get("image_url"))

                    if needs_rerender:
                        try:
                            create_image_with_text(
                                category,
                                short_title,
                                lang,
                                output_path=output_image_path,
                                description_to_draw=overlay_description,
                                highlight_text=normalize_text(option.get("highlight_text", "")),
                                layout_name=layout_override or "auto",
                                layout_preference=option.get("layout_preference", "template_1"),
                                breaking_candidate=breaking_candidate,
                                background_query=normalize_text(theme_suggestion or option.get("image_theme", "") or option.get("title", "")),
                                manual_background_url=manual_background_url,
                                year=year,
                                relevance_level=(option.get("relevance") or {}).get("level"),
                            )
                            used_approved_post = True
                        except Exception as e:
                            print(f"[{lang}] Erro ao re-renderizar post aprovado: {e}.")
                            img_url = option.get("image_url")
                            if img_url:
                                try:
                                    if copy_image_reference_to_path(img_url, output_image_path):
                                        used_approved_post = True
                                        print(f"[{lang}] Fallback para preview ja aprovada apos falha de re-render.")
                                except Exception as fallback_exc:
                                    print(f"[{lang}] Tambem falhou o fallback da preview aprovada: {fallback_exc}.")
                    else:
                        img_url = option.get("image_url")
                        try:
                            if copy_image_reference_to_path(img_url, output_image_path):
                                used_approved_post = True
                        except Exception as e:
                            print(f"[{lang}] Erro imagem pre-aprovada: {e}. Fallback Live AI.")
                break
                break

        if approved_entry_found and not used_approved_post:
            # Post aprovado existe mas a imagem nao ficou pronta (download
            # da preview falhou ou re-render falhou): abortar em vez de cair
            # no caminho da IA, que publicaria um post diferente do aprovado.
            print(f"[{lang}] ERRO: post aprovado sem imagem utilizavel. A abortar publicacao (sem fallback para IA).")
            continue

        if not used_approved_post:
            # Sem post aprovado utilizavel para este slot: abortar sem
            # fallback para IA. A aprovacao manual e obrigatoria e o
            # caminho da IA listava candidatos de todos os anos no
            # Arquivo.pt (lento, e publicaria um post nao aprovado).
            # As funcoes get_today_news / process_daily_news_with_ai
            # continuam no ficheiro, mas ja nao sao chamadas daqui.
            print(f"[{lang}] ERRO: sem post aprovado utilizavel para este slot. A abortar sem fallback para IA (sem listagem de candidatos).")
            continue

        # Upload image to ImgBB (once, shared across platforms)
        imgbb_api_key = os.environ.get("IMGBB_API_KEY")
        public_image_url = None
        delete_url = ""

        if not os.path.exists(output_image_path):
            print(f"[{lang}] Imagem nao encontrada em {output_image_path}. A saltar todas as redes.")
            continue

        if imgbb_api_key:
            try:
                with open(output_image_path, "rb") as img_file:
                    imgbb_res = requests.post(
                        "https://api.imgbb.com/1/upload",
                        data={"key": imgbb_api_key},
                        files={"image": img_file},
                        timeout=60,
                    )
                imgbb_data = imgbb_res.json()
                if imgbb_data.get("success"):
                    upload_data = imgbb_data.get("data", {})
                    public_image_url = upload_data["url"]
                    delete_url = upload_data.get("delete_url", "")
                else:
                    print(f"[{lang}] Erro IMGBB: {imgbb_data}")
            except Exception as e:
                print(f"[{lang}] Excecao IMGBB: {e}")
        else:
            print(f"[{lang}] IMGBB_API_KEY nao configurado. Imagem guardada localmente.")

        if not public_image_url:
            print(f"[{lang}] Nao foi possivel obter URL publica da imagem. A saltar todas as redes.")
            continue

        # Publish to each platform that has a window now and is in the post's networks
        for pname, pslot, pidx in platforms_to_post:
            if pname not in networks:
                print(f"[{lang}] {pname}: Nao esta nas networks desta noticia ({networks}).")
                continue

            pstate = lang_state[pname]
            feed_done = bool(approved_entry and approved_entry.get(f"{pname}_url")) or bool(pstate.get(f"{pslot}_posted", False))
            story_done = bool(approved_entry and approved_entry.get(f"{pname}_story_id")) or bool(pstate.get(f"{pslot}_story_posted", False))

            if feed_done and story_done:
                continue

            if feed_done and not story_done:
                # Retry apenas da story: o feed NAO volta a ser publicado.
                story_result = False
                if pname == "instagram":
                    story_result = publish_instagram_story(public_image_url, lang)
                elif pname == "facebook":
                    story_result = publish_facebook_story(public_image_url)
                if story_result:
                    if approved_entry:
                        approved_entry[f"{pname}_story_id"] = str(story_result)
                        with open("pending_posts.json", "w", encoding="utf-8") as pf:
                            json.dump(pending_posts, pf, ensure_ascii=False, indent=4)
                    pstate[f"{pslot}_story_posted"] = True
                    save_publish_state(state)
                    print(f"[{lang}] {pname}: Story retentada com sucesso (feed nao republicado).")
                else:
                    print(f"[{lang}] {pname}: Story continua a falhar; sera retentada na proxima run, sem republicar o feed.")
                continue

            # Select platform-specific caption
            if pname == "instagram":
                final_caption = caption_instagram or short_title
            elif pname == "facebook":
                final_caption = caption_facebook or short_title
            final_caption = normalize_text(final_caption)

            # Publish to the platform
            publish_success = False
            publish_result = {}

            if pname == "instagram":
                publish_result = publish_to_instagram(public_image_url, final_caption, lang)
                publish_success = bool(publish_result.get("success")) if isinstance(publish_result, dict) else bool(publish_result)
            elif pname == "facebook":
                publish_result = publish_to_facebook(final_caption, public_image_url)
                publish_success = publish_result is not None

            if publish_success:
                post_id_str = publish_result.get("id", "") if isinstance(publish_result, dict) else ""
                post_url_str = publish_result.get("permalink", "") if isinstance(publish_result, dict) else str(publish_result) if publish_result else ""

                register_imgbb_upload({
                    "kind": "published_post",
                    "lang": lang,
                    "date": local_date_str,
                    "slot": pslot,
                    "platform": pname,
                    "post_id": approved_entry.get("id", "") if approved_entry else "",
                    "image_url": public_image_url,
                    "delete_url": delete_url,
                    "platform_post_id": post_id_str,
                    "platform_post_url": post_url_str,
                    "published_at": datetime.now().isoformat(),
                })

                mark_items_as_published(lang, historical_news_of_chosen_day)

                if approved_entry:
                    approved_entry["status"] = "published"
                    approved_entry[f"{pname}_id"] = post_id_str
                    approved_entry[f"{pname}_url"] = post_url_str
                    approved_entry["published_at"] = datetime.now().isoformat()
                    with open("pending_posts.json", "w", encoding="utf-8") as pf:
                        json.dump(pending_posts, pf, ensure_ascii=False, indent=4)

                # Story da mesma imagem, best-effort: uma falha aqui nao
                # desfaz o post do feed nem impede a run de continuar.
                # Se a story ja foi registada, nao volta a publicar.
                if approved_entry and not approved_entry.get(f"{pname}_story_id"):
                    story_result = False
                    if pname == "instagram":
                        story_result = publish_instagram_story(public_image_url, lang)
                    elif pname == "facebook":
                        story_result = publish_facebook_story(public_image_url)
                    if story_result:
                        approved_entry[f"{pname}_story_id"] = str(story_result)
                        pstate[f"{pslot}_story_posted"] = True
                        with open("pending_posts.json", "w", encoding="utf-8") as pf:
                            json.dump(pending_posts, pf, ensure_ascii=False, indent=4)
                    else:
                        print(f"[{lang}] {pname}: Story falhou (feed continua publicado; sera retentada so a story na proxima run).")

                # Update per-platform state
                pstate = lang_state[pname]
                pstate[f"{pslot}_posted"] = True
                pstate["last_post_time"] = local_now.isoformat()
                save_publish_state(state)

                print(f"[{lang}] {pname}: Publicado com sucesso!")
            else:
                print(f"[{lang}] {pname}: Falha na publicacao.")


def publish_to_facebook(message, image_url):
    """Publica uma foto no Facebook Page via Graph API. Requer FB_PAGE_ID + FB_PAGE_ACCESS_TOKEN."""
    page_id = os.environ.get("FB_PAGE_ID", "")
    page_token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
    if not page_id or not page_token:
        return None
    import requests as _r
    try:
        res = _r.post(
            f"https://graph.facebook.com/v25.0/{page_id}/photos",
            data={"url": image_url, "caption": message, "access_token": page_token},
            timeout=60,
        )
        data = res.json()
        post_id = data.get("id")
        if post_id:
            return f"https://www.facebook.com/{post_id}"
        print("Erro Facebook:", data)
    except Exception as exc:
        print("Erro Facebook:", exc)
    return None

def publish_facebook_story(image_url):
    """Publica a mesma imagem como Story da Pagina do Facebook (24h).

    Dois passos Graph API: primeiro upload da foto como nao publicada,
    depois POST /{page-id}/photo_stories com o photo_id. Best-effort:
    devolve o post_id ou True/False, nunca levanta excecao, para uma
    falha na story nao transformar um post do feed ja publicado num
    falhado. Requer FB_PAGE_ID + FB_PAGE_ACCESS_TOKEN, os mesmos do feed.
    """
    page_id = os.environ.get("FB_PAGE_ID", "")
    page_token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
    if not page_id or not page_token:
        print("Story Facebook: credenciais nao configuradas.")
        return False
    import requests as _r
    try:
        up = _r.post(
            f"https://graph.facebook.com/v25.0/{page_id}/photos",
            data={"url": image_url, "published": "false", "access_token": page_token},
            timeout=60,
        )
        up_data = up.json()
        photo_id = up_data.get("id")
        if not photo_id:
            print("Story Facebook: erro no upload nao publicado:", up_data)
            return False
        res = _r.post(
            f"https://graph.facebook.com/v25.0/{page_id}/photo_stories",
            data={"photo_id": photo_id, "access_token": page_token},
            timeout=60,
        )
        data = res.json()
        if data.get("success"):
            print(f"Story Facebook publicada! Post ID: {data.get('post_id')}")
            return data.get("post_id") or True
        print("Story Facebook: erro ao publicar:", data)
        return False
    except Exception as exc:
        print("Story Facebook: excecao API:", exc)
        return False


if __name__ == "__main__":
    main()
