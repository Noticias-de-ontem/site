import calendar
import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

import requests

from archive_storage import load_posts_for_date
from imgbb_registry import register_imgbb_upload
from nvidia_client import DEFAULT_NVIDIA_MODEL, NvidiaKeyPool, load_nvidia_api_keys
from post_templates import create_image_with_text as render_post_image, is_volatile_image_url


PENDING_POSTS_FILE = "pending_posts.json"
REVIEW_HTML_FILES = {
    "pt": "review_pt.html",
    "en": "review_en.html",
}
PREGENERATION_STATE_FILE = "pregeneration_state.json"

import random

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

GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY")
PREGENERATOR_SOURCE_MODE = os.environ.get("PREGENERATOR_SOURCE_MODE", "arquivo-first")
MAX_NVIDIA_INPUT_ITEMS = int(os.environ.get("PREGENERATOR_NVIDIA_MAX_INPUT_ITEMS", "80"))
MAX_NVIDIA_CONTEXT_CHARS = int(os.environ.get("PREGENERATOR_NVIDIA_MAX_CONTEXT_CHARS", "320"))
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
    r"\bclick\b",
    r"\btap\b",
    r"\blink in bio\b",
]
NVIDIA_HINT_KEYWORDS = [
    "meme",
    "viral",
    "celebrity",
    "celebridade",
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
    "polici",
    "crime",
    "morte",
    "death",
    "war",
    "guerra",
    "attack",
    "ataque",
    "protest",
    "manifest",
    "ukraine",
    "ucrani",
    "russia",
    "israel",
    "palestin",
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
    "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
    "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
    "primark", "outlet", "catalogo", "catálogo"
]
STRONG_TOPIC_KEYWORDS = [
    "ronaldo", "messi", "mourinho", "sporting", "benfica", "porto", "seleção", "selecao",
    "mundial", "euro", "champions", "festival", "concerto", "cinema", "filme", "série",
    "serie", "música", "musica", "cantor", "atriz", "ator", "actor", "beyonc", "swift",
    "madonna", "lady gaga", "tecnologia", "iphone", "apple", "google", "spacex", "tesla",
    "internet", "viral", "meme", "curioso", "insólito", "insolito", "bizarro", "recorde",
    "estreia", "primeiro", "histórico", "historico", "vitória", "vitoria", "campeão",
    "campeao", "oscar", "televisão", "televisao"
]
WEAK_TOPIC_KEYWORDS = [
    "segundo a ap", "durante a reunião", "reunião pública", "executivo municipal",
    "orçamento", "orcamento", "relatório", "relatorio", "plano nacional",
    "secretário de estado", "secretario de estado", "comunicado",
    "conferência de imprensa", "conferencia de imprensa", "fonte oficial",
    "ministério", "ministerio", "processo administrativo"
]

WEAK_TOPIC_KEYWORDS.extend([
    "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
    "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
    "primark", "outlet", "catalogo", "catálogo",
])
COMMERCIAL_TOPIC_KEYWORDS = [
    "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
    "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
    "primark", "outlet", "catalogo", "catálogo",
]
LOW_VALUE_ANNIVERSARY_PATTERNS = [
    r"\bparab[eé]ns\b",
    r"\b(?:celebra|celebram|comemora|comemoram|assinala|assinalam)\b.{0,90}\b\d{1,3}\s+anos\b",
    r"\b\d{1,3}[.ºoª\s]*(?:anivers[aá]rio|anos de exist[eê]ncia)\b",
    r"\bfaz\s+\d{1,3}\s+anos\b",
]
SUBSTANTIVE_ANNIVERSARY_MARKERS = [
    "inaugura", "lança", "lanca", "estreia", "concerto", "exposição", "exposicao",
    "vence", "recorde", "descoberta", "eleição", "eleicao", "acordo", "lei", "reforma",
    "investigação", "investigacao", "campeonato", "festival", "filme", "álbum", "album",
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


def is_low_value_anniversary(item):
    text = normalize_text(
        item.get("enriched_context")
        or item.get("global_context")
        or item.get("caption")
        or item.get("raw_caption")
        or item.get("title")
        or ""
    ).lower()
    if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in LOW_VALUE_ANNIVERSARY_PATTERNS):
        return False
    return not any(marker in text for marker in SUBSTANTIVE_ANNIVERSARY_MARKERS)


def score_nvidia_candidate(item):
    text = normalize_text(build_editorial_context(item)).lower()
    score = 0
    for keyword in NVIDIA_HINT_KEYWORDS:
        if keyword in text:
            score += 1
    for keyword in STRONG_TOPIC_KEYWORDS:
        if keyword in text:
            score += 3
    for keyword in WEAK_TOPIC_KEYWORDS:
        if keyword in text:
            score -= 3
    for keyword in COMMERCIAL_TOPIC_KEYWORDS:
        if keyword in text:
            score -= 8
    if is_low_value_anniversary(item):
        score -= 20
    if re.search(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+){1,3}\b", build_editorial_context(item)):
        score += 2
    if 80 <= len(text) <= 900:
        score += 1
    if len(text) > 1600:
        score -= 2
    return score


def select_nvidia_candidates(news_items, max_total=MAX_NVIDIA_INPUT_ITEMS, max_per_year=2):
    grouped = {}
    for item in news_items:
        year = str(item.get("date", ""))[:4] or "0000"
        grouped.setdefault(year, []).append(item)

    selected = []
    years = sorted(grouped.keys(), reverse=True)
    # First pass: one strong item per year keeps July-like month runs from being dominated
    # by only the latest archived posts.
    for year in years:
        year_items = sorted(
            grouped[year],
            key=lambda item: (score_nvidia_candidate(item), item.get("date", "")),
            reverse=True,
        )
        if year_items:
            selected.append(year_items[0])
        if len(selected) >= max_total:
            break

    if len(selected) < max_total and max_per_year > 1:
        selected_ids = {id(item) for item in selected}
        remaining = []
        for year in years:
            year_items = sorted(
                grouped[year],
                key=lambda item: (score_nvidia_candidate(item), item.get("date", "")),
                reverse=True,
            )
            remaining.extend(item for item in year_items[1:max_per_year] if id(item) not in selected_ids)
        remaining.sort(key=lambda item: (score_nvidia_candidate(item), item.get("date", "")), reverse=True)
        selected.extend(remaining[: max_total - len(selected)])

    return selected[:max_total]


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


def build_fallback_options(news_items, lang, limit=5):
    fallback_items = select_nvidia_candidates(news_items, max_total=limit)
    if not fallback_items:
        fallback_items = list(news_items[:limit])

    options = []
    for item in fallback_items:
        source_text = item.get("global_context") or item.get("caption") or item.get("raw_caption") or ""
        cleaned_text = strip_publicity_text(source_text) or normalize_text(source_text)
        title = build_fallback_title(cleaned_text, lang)
        caption = compact_text(cleaned_text or title, limit=600)
        options.append(
            {
                "year": normalize_text(item.get("date", "")[:4]),
                "category": infer_category_from_text(cleaned_text or title, lang),
                "title": title,
                "highlight_text": "",
                "overlay_description": compact_text(title, limit=120),
                "image_theme": title,
                "layout_preference": "template_1",
                "breaking_candidate": False,
                "caption": caption,
                "summary": compact_text(cleaned_text or title, limit=180),
            }
        )
    return options


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


def get_historical_news_for_date(date_obj, lang):
    posts = load_posts_for_date(lang, date_obj.month, date_obj.day)

    matching = []
    heavy_words = [
        "morre", "morto", "morte", "rapto", "raptado", "abuso", "abusa", "viola", 
        "violada", "violador", "assassina", "homicídio", "crime", "suicídio", 
        "tragédia", "pedofilia", "guerra", "falece", "falecimento", "assassina",
        "dies", "died", "death", "kidnap", "kidnapped", "abuse", "rape", "murder", 
        "murdered", "homicide", "suicide", "tragedy", "pedophilia", "war", "fatal"
    ]
    for item in posts:
        if item.get("published", False):
            continue
        try:
            item_date = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
            if item_date.day == date_obj.day and item_date.year < date_obj.year:
                caption_val = item.get("caption") or item.get("global_context") or item.get("title") or ""
                if isinstance(caption_val, list):
                    caption_val = " ".join([str(x) for x in caption_val])
                elif not isinstance(caption_val, str):
                    caption_val = str(caption_val)
                caption_lower = caption_val.lower()
                if any(w in caption_lower for w in heavy_words):
                    continue
                if is_low_value_anniversary(item):
                    continue
                matching.append(item)
        except ValueError:
            continue
    return matching


def load_json(filepath, default=None):
    if default is None:
        default = []
    if not os.path.exists(filepath):
        return default
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


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
    exclude_background_urls=None,
    return_details=False,
    year=None,
):
    return render_post_image(
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
        google_cse_api_key=GOOGLE_CSE_API_KEY,
        google_cse_id=GOOGLE_CSE_ID,
        manual_background_url=manual_background_url,
        exclude_background_urls=exclude_background_urls,
        return_details=return_details,
        year=year,
    )


def upload_to_imgbb(filepath, lang, metadata=None):
    if not IMGBB_API_KEY:
        return {}
    try:
        with open(filepath, "rb") as img_file:
            res = requests.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_API_KEY},
                files={"image": img_file},
                timeout=30,
            )
        data = res.json()
        if data.get("success"):
            upload_data = data.get("data", {})
            image_url = upload_data.get("url", "")
            delete_url = upload_data.get("delete_url", "")
            register_imgbb_upload(
                {
                    **(metadata or {}),
                    "image_url": image_url,
                    "delete_url": delete_url,
                    "kind": (metadata or {}).get("kind") or "review_preview",
                }
            )
            return {"url": image_url, "delete_url": delete_url}
        print(f"[{lang}] Upload IMGBB falhou: {data}")
        return {}
    except Exception as e:
        print(f"[{lang}] Excecao IMGBB: {e}")
        return {}


def safe_filename_part(value, fallback="preview"):
    text = normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or fallback


def review_image_path(lang, date_str, option, index):
    year = safe_filename_part(option.get("year") or "preview")
    title = safe_filename_part(option.get("title") or option.get("image_theme") or "preview")
    directory = os.path.join("images", "review", lang)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{date_str}_{index + 1:02d}_{year}_{title}.jpg")


def rank_all_stories_for_day(news_items, lang, feedback_note=""):
    global NVIDIA_DISABLED

    if NVIDIA_DISABLED or not nvidia_pool.has_keys() or not news_items:
        return build_fallback_options(news_items, lang)

    filtered_items = select_nvidia_candidates(news_items, max_total=MAX_NVIDIA_INPUT_ITEMS, max_per_year=3)

    payload_items = [
        {
            "idx": i,
            "year": item.get("date", "")[:4],
            "context": build_editorial_context(item),
        }
        for i, item in enumerate(filtered_items)
    ]

    normalized_feedback = normalize_text(feedback_note)

    prompt = f"""
    You are an expert social editor for a 'Delayed News' project.
    I will provide you with a filtered list of raw news captions from previous years that happened exactly on today's day and month.

    Language required for the output: {lang.upper()}

    CRITICAL RULES:
    1. CATEGORY LANGUAGE:
       - Since the language is {lang.upper()}, you MUST output the "category" field STRICTLY in Portuguese!
       - Use categories like: POLÍTICA, DESPORTO, CULTURA, SOCIEDADE, CIÊNCIA, NACIONAL, MUNDIAL, ESTRELA, CURIOSO. Never output English categories like "SPORTS" or "SOCIETY".
    2. NO DATES IN OVERLAY DESCRIPTION:
       - The "overlay_description" field will be drawn directly onto the Instagram post image. It MUST NOT contain any dates, years, months, or days (e.g., absolutely NO 'em 2005', 'em 1974', 'em Julho', 'no dia 1', etc.). Keep it strictly timeless.
    3. NO DEATHS:
       - Do NOT select, write options about, or mention any stories involving deaths, passings, murders, suicides, violent tragedies, or funerals. Focus on sports, culture, light stories, positive or neutral historical milestones.
    4. HISTORICAL ACCURACY (PORTUGAL):
       - The dictatorship in Portugal (Estado Novo) lasted from 1933 until the Carnation Revolution on April 25, 1974. Never refer to 1960 or any other year as the end of the dictatorship.
    5. ENDURING EDITORIAL VALUE:
       - A story must remain interesting after removing any anniversary number, ceremonial wording, or congratulatory framing.
       - Treat routine institutional birthdays, age-count announcements, commemorative greetings, and publicity-led anniversaries as low-value material.
       - Anniversary coverage is only strong when it reports a substantive event with lasting public relevance, such as a major launch, victory, reform, discovery, performance, exhibition, or cultural milestone.

    YOUR TASK:
    1. Read all the provided historical news items.
    2. Group similar stories to find distinct events.
    3. Rank the distinct events by viral potential and recognizability today, not by formal institutional importance.
    4. Prefer stories that a Portuguese Instagram audience can understand immediately: famous people, sport, pop culture, technology, internet moments, curious public-life ironies, or major social milestones.
    5. Penalize routine bureaucracy, municipal meeting notes, generic agency copy, budget/process updates, minor appointments, ceremonial anniversaries, and stories whose hook depends on knowing an obscure name.
    6. Return a JSON object with an "options" array containing exactly 10 distinct, non-repeating objects (ordered from highest viral potential to lowest).
    7. The first 5 options will be used for Slot 1 of the day, and the remaining 5 options will be used for Slot 2. Ensure the two slot groups do not overlap in theme, year, public figure, or framing.

    Format:
    {{
      "options": [
        {{
          "year": "YYYY",
          "category": "ONE WORD CATEGORY IN PORTUGUESE (e.g., POLÍTICA, DESPORTO, CULTURA, SOCIEDADE)",
          "title": "A short, punchy headline summarizing the event",
          "highlight_text": "Either an empty string or 1 to 3 words that appear exactly in the title. Prefer just 1 word.",
          "overlay_description": "A short sentence for the image overlay. NO hashtags, NO call to action, and absolutely NO dates or years.",
          "image_theme": "A short visual search query, ideally 2 to 5 words, for the background image.",
          "layout_preference": "One of template_1, template_2, template_3. Only used when breaking_candidate is false.",
          "breaking_candidate": false,
          "caption": "A concise paragraph for Instagram. No hashtags. It can feel lively and socially native when appropriate.",
          "summary": "A 1-sentence internal summary for editorial review focused on why this could work well as a post."
        }}
      ]
    }}

    Layout guidance:
    - template_1: strongest default for longer titles and lower-left text with description
    - template_2: cleaner centered composition near the top half
    - template_3: photo-led composition with centered lower title
    - breaking_candidate is the main editorial decision: use true only when the post should become the special breaking layout, otherwise false and choose among the normal templates

    Editorial review feedback from the human reviewer:
    {normalized_feedback or "No extra feedback provided."}

    RAW DATA:
    {json.dumps(payload_items, ensure_ascii=False)}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        if not nvidia_pool.has_keys():
            break
        try:
            response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL)
            save_key_status_to_file()
            payload = json.loads(response_text or "{}")
            if isinstance(payload, dict):
                options = payload.get("options", [])
            else:
                options = payload if isinstance(payload, list) else []
            if isinstance(options, list):
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    option["year"] = normalize_text(option.get("year", ""))
                    option["category"] = normalize_text(option.get("category", ""), uppercase=True)
                    option["title"] = normalize_text(option.get("title", ""))
                    option["highlight_text"] = normalize_text(option.get("highlight_text", ""))
                    option["overlay_description"] = normalize_text(option.get("overlay_description", ""))
                    option["image_theme"] = normalize_text(option.get("image_theme", ""))
                    option["caption"] = normalize_text(option.get("caption", ""))
                    option["summary"] = normalize_text(option.get("summary", ""))
            return options if isinstance(options, list) and options else []
        except Exception as e:
            err_msg = str(e).lower()
            is_quota = "429" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "quota" in err_msg
            if is_quota:
                if ("day" in err_msg or "daily" in err_msg) and "minute" not in err_msg:
                    print(f"\n[NVIDIA] {get_current_key_info()} atingiu limite de API na pre-geracao. A rodar...")
                    nvidia_pool.mark_current_exhausted()
                if rotate_nvidia_client():
                    continue
            print(f"[NVIDIA] Erro na pre-geracao (tentativa {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                if any(marker in str(e).lower() for marker in NVIDIA_ERROR_MARKERS):
                    NVIDIA_DISABLED = True
                    print(f"[{lang}] NVIDIA indisponivel na pre-geracao: {e}")
                return build_fallback_options(news_items, lang)
    return build_fallback_options(news_items, lang)


def generate_external_day_suggestions(date_obj, lang, existing_options=None):
    global NVIDIA_DISABLED

    if NVIDIA_DISABLED or not nvidia_pool.has_keys():
        return []

    existing_options = existing_options or []
    existing_titles = [
        normalize_text(option.get("title", ""))
        for option in existing_options
        if isinstance(option, dict) and normalize_text(option.get("title", ""))
    ]
    audience_guidance = (
        "Focus primarily on events or cultural moments from Portugal, Portuguese public life, Portuguese media, Portuguese sport, "
        "or stories with especially strong resonance for a Portuguese audience."
        if lang == "pt"
        else "Focus primarily on world events, globally recognisable stories, internet culture, celebrity moments, major sport, "
        "and internationally relevant events rather than country-specific niche items."
    )
    output_language = "Portuguese" if lang == "pt" else "English"

    prompt = f"""
    You are helping a delayed-news editor find 3 extra historical post ideas for a specific calendar day.

    Calendar day:
    - day: {date_obj.day}
    - month: {date_obj.month}

    Language for the output: {output_language}

    CRITICAL RULES:
    1. STRICT CALENDAR DATE MATCHING:
       - You MUST only suggest events that actually happened on this exact day: {date_obj.day} of {date_obj.strftime('%B')}.
       - Do NOT suggest events from other dates. For example, if today is in July, do NOT suggest the Carnation Revolution (which happened on April 25th), do NOT suggest Christmas, and do NOT suggest any other off-season events.
    2. CATEGORY LANGUAGE:
       - Since the language is {lang.upper()}, the "category" field MUST be in Portuguese!
       - Use categories like: POLÍTICA, DESPORTO, CULTURA, SOCIEDADE, CIÊNCIA, NACIONAL, MUNDIAL, ESTRELA, CURIOSO. Never use English words.
    3. NO DEATHS:
       - Do NOT suggest any events about deaths, passings, murders, violence, or violent tragedies.
    4. HISTORICAL ACCURACY (PORTUGAL):
       - The dictatorship in Portugal (Estado Novo) lasted from 1933 until the Carnation Revolution on April 25, 1974. Never refer to 1960 or any other year as the end of the dictatorship.
    5. ENDURING EDITORIAL VALUE:
       - Prefer events that remain meaningful without relying on an anniversary number, institutional greeting, or ceremonial publicity.
       - Anniversary coverage is only suitable when it contains a substantive event or lasting cultural, social, scientific, sporting, or political consequence.

    Audience guidance:
    {audience_guidance}

    Existing archive-backed titles already available in the local database:
    {json.dumps(existing_titles, ensure_ascii=False)}

    Task:
    1. Suggest exactly 3 historical events, moments, or culturally important stories tied exactly to this calendar day and month.
    2. These suggestions should be independent from the local archive and can come from your own general knowledge base.
    3. Prefer high-confidence, recognisable events rather than obscure ones.
    4. Try not to duplicate the existing archive-backed titles above.
    5. Mix seriousness and virality well when possible.

    Return strict JSON as an object with a "suggestions" array containing exactly 3 objects:
    {{
      "suggestions": [
        {{
          "year": "YYYY",
          "category": "SHORT CATEGORY IN PORTUGUESE (e.g., CULTURA, DESPORTO)",
          "title": "Short headline idea",
          "summary": "1 sentence on why this matters or could work well as a post"
        }}
      ]
    }}
    """

    max_retries = 3
    for attempt in range(max_retries):
        if not nvidia_pool.has_keys():
            break
        try:
            response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL)
            save_key_status_to_file()
            payload = json.loads(response_text or "{}")
            if isinstance(payload, dict):
                payload = payload.get("suggestions", [])
            elif not isinstance(payload, list):
                payload = []
            if not isinstance(payload, list):
                return []

            suggestions = []
            for item in payload[:3]:
                if not isinstance(item, dict):
                    continue
                suggestions.append(
                    {
                        "year": normalize_text(item.get("year", "")),
                        "category": normalize_text(item.get("category", ""), uppercase=True),
                        "title": normalize_text(item.get("title", "")),
                        "summary": normalize_text(item.get("summary", "")),
                    }
                )
            return suggestions
        except Exception as exc:
            err_msg = str(exc).lower()
            is_quota = "429" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "quota" in err_msg
            if is_quota:
                if ("day" in err_msg or "daily" in err_msg) and "minute" not in err_msg:
                    print(f"\n[NVIDIA] {get_current_key_info()} atingiu limite de API nas sugestoes. A rodar...")
                    nvidia_pool.mark_current_exhausted()
                if rotate_nvidia_client():
                    continue
            print(f"[NVIDIA] Erro nas sugestoes (tentativa {attempt + 1}/{max_retries}): {exc}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                if any(marker in str(exc).lower() for marker in NVIDIA_ERROR_MARKERS):
                    NVIDIA_DISABLED = True
                    print(f"[{lang}] NVIDIA indisponivel nas sugestoes externas: {exc}")
                return []
    return []


def month_key(date_obj):
    return date_obj.strftime("%Y-%m")


def parse_month_key(value):
    return datetime.strptime(f"{value}-01", "%Y-%m-%d").date()


def add_one_month(date_obj):
    year = date_obj.year + (1 if date_obj.month == 12 else 0)
    month = 1 if date_obj.month == 12 else date_obj.month + 1
    return datetime(year, month, 1).date()


def end_of_month(date_obj):
    return datetime(date_obj.year, date_obj.month, calendar.monthrange(date_obj.year, date_obj.month)[1]).date()


def sort_pending_posts(posts):
    posts.sort(key=lambda item: (item.get("date", ""), 0 if item.get("lang") == "pt" else 1, int(item.get("slot", 1))))


def normalize_pending_post(post):
    post["layout_override"] = str(post.get("layout_override", "")).strip().lower().replace("-", "_")
    post["theme_suggestion"] = normalize_text(post.get("theme_suggestion", ""))
    review_action = str(post.get("review_action", "")).strip().lower()
    post["review_action"] = review_action if review_action in {"regenerate", "refresh_image"} else ""
    post["review_note"] = normalize_text(post.get("review_note", ""))
    post["manual_background_url"] = normalize_text(post.get("manual_background_url", ""))
    post["status"] = str(post.get("status", "pending")).strip().lower() or "pending"
    post["generated_month"] = str(post.get("generated_month") or str(post.get("date", ""))[:7]).strip()
    post["selected_option"] = int(post.get("selected_option", 0) or 0)
    external_suggestions = []
    for suggestion in post.get("external_suggestions", []) or []:
        if not isinstance(suggestion, dict):
            continue
        external_suggestions.append(
            {
                "year": normalize_text(suggestion.get("year", "")),
                "category": normalize_text(suggestion.get("category", ""), uppercase=True),
                "title": normalize_text(suggestion.get("title", "")),
                "summary": normalize_text(suggestion.get("summary", "")),
            }
        )
    post["external_suggestions"] = external_suggestions
    options = []
    for option in post.get("options", []) or []:
        if not isinstance(option, dict):
            continue
        normalized_option = dict(option)
        normalized_option["year"] = normalize_text(normalized_option.get("year", ""))
        normalized_option["category"] = normalize_text(normalized_option.get("category", ""), uppercase=True)
        normalized_option["title"] = normalize_text(normalized_option.get("title", ""))
        normalized_option["highlight_text"] = normalize_text(normalized_option.get("highlight_text", ""))
        normalized_option["overlay_description"] = normalize_text(normalized_option.get("overlay_description", ""))
        normalized_option["image_theme"] = normalize_text(normalized_option.get("image_theme", ""))
        normalized_option["caption"] = normalize_text(normalized_option.get("caption", ""))
        normalized_option["summary"] = normalize_text(normalized_option.get("summary", ""))
        normalized_option["layout_preference"] = str(normalized_option.get("layout_preference", "template_1")).strip().lower().replace("-", "_")
        normalized_option["breaking_candidate"] = bool(normalized_option.get("breaking_candidate", False))
        normalized_option["background_source_url"] = normalize_text(normalized_option.get("background_source_url", ""))
        normalized_option["local_image_path"] = normalize_text(normalized_option.get("local_image_path", ""))
        normalized_option["image_delete_url"] = normalize_text(normalized_option.get("image_delete_url", ""))
        options.append(normalized_option)
    post["options"] = options
    if post["selected_option"] >= len(options):
        post["selected_option"] = 0
    return post


def load_pregeneration_state():
    return load_json(PREGENERATION_STATE_FILE, {})


def save_pregeneration_state(state):
    save_json(PREGENERATION_STATE_FILE, state)


def latest_month_in_pending(pending_posts, lang_filter=""):
    latest = None
    for post in pending_posts:
        if lang_filter and post.get("lang") != lang_filter:
            continue
        try:
            post_date = datetime.strptime(post["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        candidate = post_date.replace(day=1)
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def determine_next_target_month(pending_posts, state, lang_filter=""):
    state_for_lang = state.get(lang_filter, {}) if lang_filter else state
    last_generated_month = normalize_text(state_for_lang.get("last_generated_month", ""))
    base_month = None

    if last_generated_month:
        try:
            base_month = parse_month_key(last_generated_month)
        except ValueError:
            base_month = None

    if base_month is None:
        base_month = latest_month_in_pending(pending_posts, lang_filter=lang_filter)

    if base_month is None:
        base_month = datetime.now().date().replace(day=1)

    return add_one_month(base_month)


def determine_focus_month(pending_posts, fallback_month=""):
    regenerate_posts = [post for post in pending_posts if post.get("review_action") == "regenerate"]
    if regenerate_posts:
        return sorted({post.get("date", "")[:7] for post in regenerate_posts if post.get("date")})[0]

    pending_posts_open = [
        post for post in pending_posts
        if post.get("status", "pending") not in {"approved", "published", "skip"}
    ]
    if pending_posts_open:
        return sorted({post.get("date", "")[:7] for post in pending_posts_open if post.get("date")})[0]

    return fallback_month


def match_option_to_article(option, articles):
    if not articles:
        return None
    opt_year = option.get("year", "")
    opt_title = (option.get("title") or "").lower()
    
    same_year_articles = [art for art in articles if str(art.get("date", ""))[:4] == opt_year]
    if not same_year_articles:
        return None
        
    if len(same_year_articles) == 1:
        return same_year_articles[0]
        
    best_match = same_year_articles[0]
    max_matches = -1
    for art in same_year_articles:
        art_title = (art.get("title") or "").lower()
        art_context = (art.get("global_context") or "").lower()
        words = [w for w in opt_title.split() if len(w) > 3]
        matches = sum(1 for w in words if w in art_title or w in art_context)
        if matches > max_matches:
            max_matches = matches
            best_match = art
            
    return best_match


def append_review_hashtags(caption, lang):
    caption = normalize_text(caption)
    hashtags = "#Noticias #Atualidade #Jornalismo" if lang == "pt" else "#News #BreakingNews #CurrentEvents"
    return caption if hashtags in caption else normalize_text(f"{caption}\n\n{hashtags}")


def prepare_options_for_review(
    options_list,
    lang,
    date_str,
    manual_background_url="",
    force_new_background=False,
    matching_news=None,
    selected_option_index=0,
    render_all=False,
):
    prepared_options = []
    try:
        selected_option_index = int(selected_option_index or 0)
    except Exception:
        selected_option_index = 0

    for option_index, opt in enumerate(options_list):
        option = dict(opt)
        should_render_image = render_all or option_index == selected_option_index
        matched_background_url = ""
        if should_render_image and matching_news:
            matched = match_option_to_article(option, matching_news)
            if matched:
                option["background_source_url"] = matched.get("source_url") or matched.get("url") or ""
                candidate_background_url = normalize_text(matched.get("image_url", ""))
                if candidate_background_url and not is_volatile_image_url(candidate_background_url):
                    matched_background_url = candidate_background_url
                elif candidate_background_url:
                    print(f"[{lang}] Imagem do artigo ignorada: URL temporario do Instagram/Facebook CDN.")

        if should_render_image:
            stable_img_path = review_image_path(lang, date_str, option, option_index)
            current_background_source = normalize_text(option.get("background_source_url", ""))
            effective_manual_background_url = manual_background_url or ("" if force_new_background else matched_background_url)
            render_details = create_image_with_text(
                option.get("category"),
                option.get("title"),
                lang,
                output_path=stable_img_path,
                description_to_draw=option.get("overlay_description", ""),
                highlight_text=option.get("highlight_text", ""),
                layout_preference=option.get("layout_preference", "template_1"),
                breaking_candidate=bool(option.get("breaking_candidate", False)),
                background_query=option.get("image_theme", "") or option.get("title", ""),
                manual_background_url=effective_manual_background_url,
                exclude_background_urls=[current_background_source] if force_new_background and current_background_source and not manual_background_url else [],
                return_details=True,
                year=option.get("year"),
            )
            imgbb_upload = upload_to_imgbb(
                stable_img_path,
                lang,
                metadata={
                    "kind": "review_preview",
                    "lang": lang,
                    "date": date_str,
                    "option_index": option_index,
                    "title": option.get("title", ""),
                    "year": option.get("year", ""),
                },
            )
            imgbb_url = imgbb_upload.get("url", "")
            local_review_url = stable_img_path.replace(os.sep, "/")
            option["image_url"] = imgbb_url or local_review_url
            option["image_delete_url"] = imgbb_upload.get("delete_url", "")
            option["local_image_path"] = local_review_url
            background_src = ""
            if isinstance(render_details, dict):
                background_src = render_details.get("background_source_url", "")
            option["background_source_url"] = normalize_text(background_src)
        else:
            option["image_url"] = ""
            option["image_delete_url"] = ""
            option["local_image_path"] = ""
            option["background_source_url"] = ""

        option["image_theme"] = normalize_text(option.get("image_theme", ""))
        option["layout_preference"] = str(option.get("layout_preference", "template_1")).strip().lower().replace("-", "_")
        option["breaking_candidate"] = bool(option.get("breaking_candidate", False))
        option["caption"] = append_review_hashtags(option.get("caption", ""), lang)
        prepared_options.append(option)
    return prepared_options


def clone_options(options_list):
    return json.loads(json.dumps(options_list, ensure_ascii=False))


def refresh_marked_post_images(pending_posts):
    targets = [post for post in pending_posts if post.get("review_action") == "refresh_image"]
    if not targets:
        return False, False, ""

    changed = False
    focus_month = determine_focus_month(targets, fallback_month="")

    for post in targets:
        lang = post.get("lang", "pt")
        date_str = post.get("date", "")
        manual_background_url = post.get("manual_background_url", "")

        if not post.get("options"):
            continue

        print(f"[{lang}] A atualizar apenas a imagem de fundo em {post.get('id', '')}.")
        prepared_options = prepare_options_for_review(
            post.get("options", []),
            lang,
            date_str,
            manual_background_url=manual_background_url,
            force_new_background=not bool(manual_background_url),
            selected_option_index=post.get("selected_option", 0),
        )
        post["options"] = clone_options(prepared_options)
        if post["selected_option"] >= len(post["options"]):
            post["selected_option"] = 0
        post["status"] = "pending"
        post["review_action"] = ""
        post["last_image_refresh_at"] = datetime.now().isoformat()
        changed = True

    return True, changed, focus_month


def tag_source_origin(items, origin):
    tagged = []
    for item in items or []:
        clone = dict(item)
        clone["source_origin"] = clone.get("source_origin") or origin
        tagged.append(clone)
    return tagged


def get_news_with_arquivo_first(date_obj, lang):
    arquivo_news = []
    try:
        from publisher import get_today_news_from_arquivo
        print(f"[{lang}][Arquivo.pt] A procurar notícias do dia no Arquivo.pt...")
        arquivo_news = get_today_news_from_arquivo(lang, date_obj.month, date_obj.day)
        if arquivo_news:
            print(f"[{lang}][Arquivo.pt] Obtidos {len(arquivo_news)} artigos com sucesso do Arquivo.pt.")
            return tag_source_origin(arquivo_news, "arquivo.pt")
        else:
            print(f"[{lang}][Arquivo.pt] Sem resultados ao buscar no Arquivo.pt. A usar dados locais como fallback...")
    except Exception as e:
        print(f"[{lang}][Arquivo.pt] Erro ao aceder ao Arquivo.pt ({e}). A usar dados locais como fallback...")

    return tag_source_origin(get_historical_news_for_date(date_obj, lang), "local_fallback")


def normalize_source_mode(value):
    mode = normalize_text(value or PREGENERATOR_SOURCE_MODE).lower().replace("_", "-")
    aliases = {
        "arquivo": "arquivo-first",
        "arquivo-only": "arquivo-only",
        "full": "arquivo-first",
        "fast": "local",
        "local-only": "local",
        "localfirst": "local-first",
        "arquivofirst": "arquivo-first",
    }
    return aliases.get(mode, mode if mode in {"local", "local-first", "arquivo-first", "arquivo-only"} else "arquivo-first")


def get_news_for_generation(date_obj, lang, source_mode=""):
    mode = normalize_source_mode(source_mode)

    if mode in {"local", "local-first"}:
        local_news = get_historical_news_for_date(date_obj, lang)
        if local_news:
            print(f"[{lang}][Local] Obtidas {len(local_news)} noticias locais.")
            return tag_source_origin(local_news, "local")
        if mode == "local":
            print(f"[{lang}][Local] Sem noticias locais para este dia.")
            return []
        print(f"[{lang}][Local] Sem noticias locais. A tentar Arquivo.pt...")

    if mode == "arquivo-only":
        try:
            from publisher import get_today_news_from_arquivo
            print(f"[{lang}][Arquivo.pt] A procurar noticias do dia no Arquivo.pt...")
            return tag_source_origin(get_today_news_from_arquivo(lang, date_obj.month, date_obj.day), "arquivo.pt")
        except Exception as exc:
            print(f"[{lang}][Arquivo.pt] Erro ao aceder ao Arquivo.pt ({exc}).")
            return []

    return get_news_with_arquivo_first(date_obj, lang)


def regenerate_marked_posts(pending_posts):
    targets = [post for post in pending_posts if post.get("review_action") == "regenerate"]
    if not targets:
        return False, False, ""

    target_groups = {}
    for post in targets:
        key = (post.get("lang", "pt"), post.get("date", ""))
        target_groups.setdefault(key, []).append(post)

    print(f"A regenerar {len(targets)} post(s) marcados para refresh seletivo...")
    changed = False

    for (lang, date_str), grouped_targets in target_groups.items():
        try:
            post_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            print(f"[{lang}] Data invalida em {date_str}.")
            continue

        matching_news = get_news_for_generation(post_date, lang)
        if not matching_news:
            print(f"[{lang}] Sem noticias historicas para regenerar {date_str}.")
            continue

        feedback_note = "\n".join(
            note for note in [post.get("review_note", "") for post in grouped_targets] if note
        )
        manual_background_url = next(
            (normalize_text(post.get("manual_background_url", "")) for post in grouped_targets if normalize_text(post.get("manual_background_url", ""))),
            "",
        )
        siblings = [
            post for post in pending_posts
            if post.get("lang", "pt") == lang and post.get("date", "") == date_str
        ]

        print(f"[{lang}] A regenerar {date_str} com {len(matching_news)} noticias.")
        options_list = rank_all_stories_for_day(
            matching_news,
            lang,
            feedback_note=feedback_note,
        )
        if not options_list:
            print(f"[{lang}] Falha da IA em {date_str}.")
            continue

        external_suggestions = generate_external_day_suggestions(post_date, lang, options_list)
        slot1_base_options = options_list[:5]
        slot2_base_options = options_list[5:10] if len(options_list) > 5 else options_list

        for sibling in siblings:
            slot = int(sibling.get("slot", 1))
            base_options = slot1_base_options if slot == 1 else slot2_base_options
            default_selected = 1 if slot == 2 and len(base_options) > 1 else 0
            current_selected = int(sibling.get("selected_option", default_selected) or default_selected)
            current_selected = current_selected if current_selected < len(base_options) else default_selected
            sibling_options = prepare_options_for_review(
                base_options,
                lang,
                date_str,
                manual_background_url=manual_background_url,
                matching_news=matching_news,
                selected_option_index=current_selected,
            )
            sibling["options"] = clone_options(sibling_options)
            sibling["external_suggestions"] = clone_options(external_suggestions)
            sibling["selected_option"] = current_selected
            sibling["status"] = "pending"
            sibling["review_action"] = ""
            sibling["last_regenerated_at"] = datetime.now().isoformat()
            sibling["regeneration_count"] = int(sibling.get("regeneration_count", 0) or 0) + 1
        changed = True

    return True, changed, determine_focus_month(targets, fallback_month="")


def generate_review_html(pending_posts, focus_month="", lang_filter="pt"):
    embedded_posts = json.dumps(pending_posts, ensure_ascii=False)
    month_options = json.dumps(
        sorted({post.get("date", "")[:7] for post in pending_posts if post.get("date") and post.get("lang") == lang_filter})
    )
    initial_focus_month = focus_month or determine_focus_month([post for post in pending_posts if post.get("lang") == lang_filter])
    review_output_path = REVIEW_HTML_FILES[lang_filter]
    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delayed News - Review Queue ({lang_filter.upper()})</title>
    <style>
        :root {{
            color-scheme: dark;
            --bg: #0f141b;
            --panel: #161d27;
            --panel-soft: #1e2834;
            --text: #eef4f8;
            --muted: #9db1bf;
            --accent: #22c8d2;
            --border: rgba(255,255,255,0.08);
            --warning: #f7c14f;
        }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: Inter, "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); }}
        .page {{ max-width: 1320px; margin: 0 auto; padding: 24px; }}
        .toolbar {{
            position: sticky;
            top: 0;
            z-index: 10;
            background: rgba(15,20,27,0.96);
            backdrop-filter: blur(12px);
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 20px;
        }}
        .toolbar-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 12px;
            flex-wrap: wrap;
        }}
        .toolbar-header h1 {{
            font-size: 20px;
            font-weight: 800;
            margin: 0;
        }}
        .summary {{
            display: flex;
            gap: 8px;
            margin: 0;
            flex-wrap: wrap;
        }}
        .summary-card {{
            background: var(--panel-soft);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .summary-card strong {{
            font-size: 11px;
            color: var(--muted);
            font-weight: 700;
            text-transform: uppercase;
        }}
        .summary-card span {{
            font-size: 14px;
            font-weight: 800;
            color: var(--accent);
        }}
        .toolbar-main {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .toolbar-actions, .toolbar-filters {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }}
        button {{
            background: var(--accent);
            color: #081217;
            border: 0;
            border-radius: 8px;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: opacity 0.2s ease;
        }}
        button:hover {{ opacity: 0.9; }}
        button.secondary {{
            background: var(--panel-soft);
            color: var(--text);
            border: 1px solid var(--border);
        }}
        .toolbar-filters select, .toolbar-filters input {{
            background: var(--panel-soft);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            font: inherit;
        }}
        .toggle {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--panel-soft);
            padding: 8px 12px;
            border-radius: 8px;
            border: 1px solid var(--border);
            font-size: 13px;
            cursor: pointer;
        }}
        .toggle input {{ margin: 0; cursor: pointer; }}
        details.help-note {{
            margin-top: 10px;
            background: rgba(255,255,255,0.02);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
        }}
        details.help-note summary {{
            font-weight: 700;
            color: var(--accent);
            cursor: pointer;
        }}
        details.help-note p {{
            margin: 6px 0 0;
            color: var(--muted);
            line-height: 1.5;
        }}
        .post-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; margin-bottom: 22px; overflow: hidden; }}
        .post-card.needs-refresh {{ border-color: rgba(247,193,79,0.55); box-shadow: 0 0 0 1px rgba(247,193,79,0.2) inset; }}
        .post-header {{ padding: 16px 18px; display: flex; justify-content: space-between; align-items: center; gap: 12px; background: #1a2430; border-bottom: 1px solid var(--border); }}
        .post-title {{ font-weight: 700; }}
        .post-status {{ color: var(--muted); font-size: 13px; font-weight: 700; letter-spacing: 0.06em; }}
        .post-body {{ display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 22px; padding: 20px; }}
        .image-wrap {{ background: #0b0f14; border-radius: 14px; overflow: hidden; border: 1px solid var(--border); align-self: start; }}
        .image-wrap img {{ display: block; width: 100%; height: auto; }}
        .field-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }}
        .field, .field-full {{ display: flex; flex-direction: column; gap: 6px; }}
        .field-full {{ margin-bottom: 16px; }}
        label {{ font-size: 12px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }}
        select, input, textarea {{ width: 100%; background: var(--panel-soft); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 11px 12px; font: inherit; }}
        textarea {{ min-height: 96px; resize: vertical; }}
        .headline {{ font-size: 36px; line-height: 1.03; font-weight: 800; margin: 0 0 10px; }}
        .meta-row {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }}
        .pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: rgba(34,200,210,0.12); color: var(--accent); font-size: 12px; font-weight: 700; }}
        .pill.warning {{ background: rgba(247,193,79,0.14); color: var(--warning); }}
        .pill.info {{ background: rgba(52,152,219,0.14); color: #54a0ff; }}
        .caption {{ white-space: pre-wrap; color: #dce8ef; font-size: 14px; line-height: 1.55; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }}
        .options-list {{ display: grid; gap: 10px; margin-top: 18px; }}
        .option-item {{ display: grid; grid-template-columns: auto 74px minmax(0, 1fr); gap: 12px; align-items: center; padding: 10px; border-radius: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); }}
        .option-thumb img {{ width: 74px; height: 92px; object-fit: cover; border-radius: 8px; display: block; }}
        .option-copy {{ color: var(--muted); font-size: 13px; }}
        .option-copy strong {{ display: block; color: var(--text); font-size: 14px; margin-bottom: 3px; }}
        .json-output {{ margin-top: 20px; }}
        .json-output textarea {{ min-height: 220px; font-family: Consolas, monospace; font-size: 13px; }}
        .empty {{ color: var(--muted); font-style: italic; padding: 18px 0; }}
        @media (max-width: 980px) {{
            .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            .post-body {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="page">
        <div class="toolbar">
            <div class="toolbar-header">
                <h1>Review Queue · {lang_filter.upper()}</h1>
                <div class="summary" id="summary"></div>
            </div>
            <div class="toolbar-main">
                <div class="toolbar-actions">
                    <button onclick="downloadJson()">Descarregar JSON</button>
                    <button class="secondary" onclick="saveDirect()">Guardar diretamente</button>
                    <button class="secondary" onclick="copyJson()">Copiar JSON</button>
                </div>
                <div class="toolbar-filters">
                    <select id="month-filter" onchange="onMonthFilter(this.value)"></select>
                    <input id="search-filter" placeholder="Pesquisar..." oninput="onSearch(this.value)">
                    <label class="toggle"><input type="checkbox" id="show-approved" onchange="onShowApproved(this.checked)"> Mostrar aprovados</label>
                </div>
            </div>
            <details class="help-note">
                <summary>Instruções de Edição</summary>
                <p>
                    Aqui podes trocar entre os 5 templates, mudar a opção escolhida, sugerir um novo tema, ver a fonte da imagem, trocar a imagem de fundo por um link teu, ou pedir uma nova imagem sem mexer no texto.
                    Depois de guardares o pending_posts.json e correres novamente o pregenerator, só os posts marcados para refresh de imagem ou regeneração NVIDIA serão refeitos.
                    Por defeito, a vista esconde posts já aprovados/publicados, mas podes mostrá-los e alterá-los quando quiseres.
                </p>
            </details>
        </div>
        <div id="posts-root"></div>
        <div class="json-output">
            <label for="json-preview">JSON atualizado</label>
            <textarea id="json-preview" readonly></textarea>
        </div>
    </div>
    <script>
        const posts = {embedded_posts};
        const monthOptions = {month_options};
        const initialFocusMonth = {json.dumps(initial_focus_month)};
        const fixedLang = {json.dumps(lang_filter)};
        const templateOptions = [
            ["", "Sugestao IA + legibilidade"],
            ["template_1", "Template 1"],
            ["template_2", "Template 2"],
            ["template_3", "Template 3"],
            ["template_4", "Template 4"],
            ["breaking", "Template Especial"],
        ];
        const statusOptions = ["pending", "approved", "skip", "published"];
        const reviewActionOptions = [
            ["", "Manter como esta"],
            ["refresh_image", "Pedir nova imagem"],
            ["regenerate", "Regenerar com NVIDIA"],
        ];
        const uiState = {{
            showApproved: false,
            monthFilter: initialFocusMonth || "",
            search: "",
        }};

        function escapeHtml(value) {{
            return String(value ?? "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }}

        function selectedOption(post) {{
            const options = Array.isArray(post.options) ? post.options : [];
            return options[post.selected_option] || options[0] || null;
        }}

        function monthKey(post) {{
            return String(post.date || "").slice(0, 7);
        }}

        function isOpenPost(post) {{
            const status = post.status || "pending";
            return ["regenerate", "refresh_image"].includes(post.review_action || "") || !["approved", "published", "skip"].includes(status);
        }}

        function matchesFilters(post, option) {{
            if ((post.lang || "") !== fixedLang) return false;
            if (!uiState.showApproved && !isOpenPost(post)) return false;
            if (uiState.monthFilter && monthKey(post) !== uiState.monthFilter) return false;
            if (!uiState.search) return true;
            const haystack = [
                post.date,
                post.lang,
                post.theme_suggestion,
                post.manual_background_url,
                post.review_note,
                option?.title,
                option?.caption,
                option?.summary,
                option?.image_theme,
                option?.background_source_url,
                ...(Array.isArray(post.external_suggestions) ? post.external_suggestions.flatMap(item => [item?.title, item?.summary, item?.category, item?.year]) : []),
            ].join(" ").toLowerCase();
            return haystack.includes(uiState.search.toLowerCase());
        }}

        function updateSummary() {{
            const counts = {{
                total: 0,
                open: 0,
                approved: 0,
                regenerate: 0,
            }};
            posts.forEach(post => {{
                if ((post.lang || "") !== fixedLang) return;
                counts.total += 1;
                if (isOpenPost(post)) counts.open += 1;
                if ((post.status || "pending") === "approved") counts.approved += 1;
                if (["regenerate", "refresh_image"].includes(post.review_action || "")) counts.regenerate += 1;
            }});
            document.getElementById("summary").innerHTML = `
                <div class="summary-card"><strong>Total</strong><span>${{counts.total}}</span></div>
                <div class="summary-card"><strong>Em revisao</strong><span>${{counts.open}}</span></div>
                <div class="summary-card"><strong>Aprovados</strong><span>${{counts.approved}}</span></div>
                <div class="summary-card"><strong>Marcados para refresh</strong><span>${{counts.regenerate}}</span></div>
            `;
        }}

        function refreshJsonPreview() {{
            document.getElementById("json-preview").value = JSON.stringify(posts, null, 2);
        }}

        function fillMonthFilter() {{
            const select = document.getElementById("month-filter");
            select.innerHTML = [`<option value="">Todos os meses</option>`]
                .concat(monthOptions.map(month => {{
                    const selected = uiState.monthFilter === month ? "selected" : "";
                    return `<option value="${{month}}" ${{selected}}>${{month}}</option>`;
                }}))
                .join("");
        }}

        function onStatusChange(postIndex, value) {{
            posts[postIndex].status = value;
            render();
        }}

        function onSelectedOption(postIndex, value) {{
            const post = posts[postIndex];
            const previous = Number(post.selected_option || 0);
            const next = Number(value);
            post.selected_option = next;
            const selected = Array.isArray(post.options) ? post.options[next] : null;
            if (next !== previous && (!selected || !selected.image_url)) {{
                post.review_action = "refresh_image";
                post.status = "pending";
            }}
            render();
        }}

        function onLayoutChange(postIndex, value) {{
            posts[postIndex].layout_override = value;
            refreshJsonPreview();
        }}

        function onThemeChange(postIndex, value) {{
            posts[postIndex].theme_suggestion = value;
            refreshJsonPreview();
        }}

        function onManualBackgroundUrl(postIndex, value) {{
            posts[postIndex].manual_background_url = value;
            refreshJsonPreview();
        }}

        function onReviewAction(postIndex, value) {{
            posts[postIndex].review_action = value;
            render();
        }}

        function onReviewNote(postIndex, value) {{
            posts[postIndex].review_note = value;
            refreshJsonPreview();
        }}

        function useExternalSuggestion(postIndex, suggestionIndex) {{
            const post = posts[postIndex];
            const sug = (post.external_suggestions || [])[suggestionIndex];
            if (!sug) return;
            post.review_note = `Gera opções baseadas no evento de ${{sug.year}}: ${{sug.title}} (${{sug.summary}})`;
            post.review_action = "regenerate";
            post.theme_suggestion = sug.title;
            render();
        }}

        function onMonthFilter(value) {{
            uiState.monthFilter = value;
            render();
        }}

        function onSearch(value) {{
            uiState.search = value;
            render();
        }}

        function onShowApproved(checked) {{
            uiState.showApproved = checked;
            render();
        }}

        function render() {{
            updateSummary();
            fillMonthFilter();
            const root = document.getElementById("posts-root");
            const visibleCards = posts.map((post, postIndex) => {{
                const option = selectedOption(post);
                if (!matchesFilters(post, option)) return "";

                const optionCount = Array.isArray(post.options) ? post.options.length : 0;
                const optionsMarkup = (post.options || []).map((opt, optionIndex) => {{
                    const checked = optionIndex === Number(post.selected_option || 0) ? "checked" : "";
                    const thumb = opt.image_url ? `<div class="option-thumb"><img src="${{escapeHtml(opt.image_url)}}" alt=""></div>` : `<div class="option-thumb"></div>`;
                    return `
                        <label class="option-item">
                            <input type="radio" name="selected-option-${{postIndex}}" value="${{optionIndex}}" ${{checked}} onchange="onSelectedOption(${{postIndex}}, this.value)">
                            ${{thumb}}
                            <div class="option-copy">
                                <strong>Opcao ${{optionIndex + 1}} · ${{escapeHtml(opt.year || "")}}</strong>
                                <div>${{escapeHtml(opt.summary || "")}}</div>
                                <div>Layout IA: <strong>${{escapeHtml(opt.layout_preference || "template_1")}}</strong> · Tema: <strong>${{escapeHtml(opt.image_theme || opt.title || "")}}</strong></div>
                                <div>Fonte imagem: ${{opt.background_source_url ? `<a href="${{escapeHtml(opt.background_source_url)}}" target="_blank" rel="noreferrer">abrir origem</a>` : "sem origem guardada"}}</div>
                            </div>
                        </label>
                    `;
                }}).join("") || `<div class="empty">Sem opcoes.</div>`;

                 const externalSuggestionsMarkup = (post.external_suggestions || []).map((suggestion, suggestionIndex) => `
                    <div class="option-item">
                        <div></div>
                        <div class="option-thumb" style="display:flex; flex-direction:column; justify-content:center; align-items:center;">
                            <button type="button" class="btn secondary" style="font-size:11px; padding:6px 10px; cursor:pointer;" onclick="useExternalSuggestion(${{postIndex}}, ${{suggestionIndex}})">Usar sugestão</button>
                        </div>
                        <div class="option-copy">
                            <strong>Sugestao externa ${{suggestionIndex + 1}} · ${{escapeHtml(suggestion.year || "")}}</strong>
                            <div>${{escapeHtml(suggestion.title || "")}}</div>
                            <div>${{escapeHtml(suggestion.summary || "")}}</div>
                            <div>${{escapeHtml(suggestion.category || "")}}</div>
                        </div>
                    </div>
                `).join("") || `<div class="empty">Sem sugestoes externas guardadas.</div>`;

                const layoutMarkup = templateOptions.map(([value, label]) => {{
                    const selected = (post.layout_override || "") === value ? "selected" : "";
                    return `<option value="${{value}}" ${{selected}}>${{label}}</option>`;
                }}).join("");

                const statusMarkup = statusOptions.map((value) => {{
                    const selected = (post.status || "pending") === value ? "selected" : "";
                    return `<option value="${{value}}" ${{selected}}>${{value}}</option>`;
                }}).join("");

                const reviewActionMarkup = reviewActionOptions.map(([value, label]) => {{
                    const selected = (post.review_action || "") === value ? "selected" : "";
                    return `<option value="${{value}}" ${{selected}}>${{label}}</option>`;
                }}).join("");

                const selectedOptionMarkup = (post.options || []).map((opt, optionIndex) => {{
                    const selected = Number(post.selected_option || 0) === optionIndex ? "selected" : "";
                    return `<option value="${{optionIndex}}" ${{selected}}>Opcao ${{optionIndex + 1}} · ${{escapeHtml(opt.year || "")}}</option>`;
                }}).join("");

                const imageMarkup = option && option.image_url
                    ? `<div class="image-wrap"><img src="${{escapeHtml(option.image_url)}}" alt="preview"></div>`
                    : `<div class="image-wrap"><div class="empty" style="padding:24px;">Sem preview</div></div>`;

                const pills = [];
                if (option?.category) pills.push(`<span class="pill">${{escapeHtml(option.category)}}</span>`);
                if (option?.layout_preference) pills.push(`<span class="pill">IA layout: ${{escapeHtml(option.layout_preference)}}</span>`);
                pills.push(`<span class="pill">Breaking: ${{option?.breaking_candidate ? "sim" : "nao"}}</span>`);
                if (fixedLang === "pt") {{
                    const isFromArquivo = String(post.source_url || "").toLowerCase().includes("arquivo.pt") || 
                                          String(option?.background_source_url || "").toLowerCase().includes("arquivo.pt");
                    const sourceText = isFromArquivo ? "Arquivo.pt" : "Dados Extraídos";
                    pills.push(`<span class="pill info">Fonte: ${{sourceText}}</span>`);
                }}
                if ((post.review_action || "") === "regenerate") pills.push(`<span class="pill warning">A regenerar no proximo run</span>`);
                if ((post.review_action || "") === "refresh_image") pills.push(`<span class="pill warning">A pedir nova imagem no proximo run</span>`);

                const meta = option
                    ? `
                        <div class="meta-row">${{pills.join("")}}</div>
                        <h2 class="headline">${{escapeHtml(option.title || "")}}</h2>
                        <div class="caption">${{option.background_source_url ? `Fonte da imagem: ${{escapeHtml(option.background_source_url)}}` : "Fonte da imagem: sem origem guardada"}}</div>
                        <div class="caption">${{escapeHtml(option.caption || "")}}</div>
                    `
                    : `<div class="empty">Sem opcao selecionada.</div>`;

                const cardClass = ["regenerate", "refresh_image"].includes(post.review_action || "") ? "post-card needs-refresh" : "post-card";

                return `
                    <section class="${{cardClass}}">
                        <div class="post-header">
                            <div class="post-title">${{escapeHtml(post.date || "")}} · ${{escapeHtml((post.lang || "").toUpperCase())}} · Post ${{escapeHtml(post.slot || "")}}/${{optionCount >= 2 ? 2 : 1}}</div>
                            <div class="post-status">${{escapeHtml((post.status || "pending").toUpperCase())}}</div>
                        </div>
                        <div class="post-body">
                            ${{imageMarkup}}
                            <div>
                                <div class="field-grid">
                                    <div class="field">
                                        <label>Status</label>
                                        <select onchange="onStatusChange(${{postIndex}}, this.value)">${{statusMarkup}}</select>
                                    </div>
                                    <div class="field">
                                        <label>Opcao selecionada</label>
                                        <select onchange="onSelectedOption(${{postIndex}}, this.value)">${{selectedOptionMarkup}}</select>
                                    </div>
                                    <div class="field">
                                        <label>Template final</label>
                                        <select onchange="onLayoutChange(${{postIndex}}, this.value)">${{layoutMarkup}}</select>
                                    </div>
                                    <div class="field">
                                        <label>Acao de revisao</label>
                                        <select onchange="onReviewAction(${{postIndex}}, this.value)">${{reviewActionMarkup}}</select>
                                    </div>
                                    <div class="field">
                                        <label>Tema atual da IA</label>
                                        <input value="${{escapeHtml(option?.image_theme || option?.title || "")}}" readonly>
                                    </div>
                                    <div class="field">
                                        <label>Mes do lote</label>
                                        <input value="${{escapeHtml(post.generated_month || monthKey(post))}}" readonly>
                                    </div>
                                    <div class="field">
                                        <label>Fonte atual da imagem</label>
                                        <input value="${{escapeHtml(option?.background_source_url || "")}}" readonly>
                                    </div>
                                </div>
                                <div class="field-full">
                                    <label>Sugestao manual de tema</label>
                                    <input value="${{escapeHtml(post.theme_suggestion || "")}}" placeholder="Ex.: incendio urbano noturno, manifestacao em lisboa, bolsa, meme classico" oninput="onThemeChange(${{postIndex}}, this.value)">
                                </div>
                                <div class="field-full">
                                    <label>Link manual para imagem de fundo</label>
                                    <input value="${{escapeHtml(post.manual_background_url || "")}}" placeholder="https://..." oninput="onManualBackgroundUrl(${{postIndex}}, this.value)">
                                </div>
                                <div class="field-full">
                                    <label>Nota para regeneracao seletiva</label>
                                    <textarea placeholder="Ex.: trocar por uma historia mais pop, evitar desporto, procurar algo mais meme/viral..." oninput="onReviewNote(${{postIndex}}, this.value)">${{escapeHtml(post.review_note || "")}}</textarea>
                                </div>
                                ${{meta}}
                                <div class="options-list">
                                    <label>Alternativas</label>
                                    ${{optionsMarkup}}
                                </div>
                                <div class="options-list">
                                    <label>3 sugestoes externas da NVIDIA para este dia</label>
                                    ${{externalSuggestionsMarkup}}
                                </div>
                            </div>
                        </div>
                    </section>
                `;
            }}).filter(Boolean);

            root.innerHTML = visibleCards.length
                ? visibleCards.join("")
                : `<div class="empty">Nenhum post corresponde aos filtros atuais.</div>`;
            refreshJsonPreview();
        }}

        function downloadJson() {{
            const blob = new Blob([JSON.stringify(posts, null, 2)], {{ type: "application/json" }});
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "pending_posts.json";
            link.click();
            URL.revokeObjectURL(url);
        }}

        async function saveDirect() {{
            const content = JSON.stringify(posts, null, 2);
            if (window.showSaveFilePicker) {{
                try {{
                    const handle = await window.showSaveFilePicker({{
                        suggestedName: "pending_posts.json",
                        types: [{{ description: "JSON", accept: {{ "application/json": [".json"] }} }}],
                    }});
                    const writable = await handle.createWritable();
                    await writable.write(content);
                    await writable.close();
                    return;
                }} catch (error) {{
                    console.warn(error);
                }}
            }}
            downloadJson();
        }}

        async function copyJson() {{
            const content = JSON.stringify(posts, null, 2);
            try {{
                await navigator.clipboard.writeText(content);
            }} catch (error) {{
                console.warn(error);
            }}
        }}

        render();
    </script>
</body>
</html>
"""
    with open(review_output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {review_output_path}")


def generate_review_files(pending_posts, focus_months=None, langs=None):
    focus_months = focus_months or {}
    langs = langs or ["pt"]
    for lang in langs:
        generate_review_html(
            pending_posts,
            focus_month=focus_months.get(lang, ""),
            lang_filter=lang,
        )


def parse_cli_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} tem de estar no formato YYYY-MM-DD.") from exc


def generate_pending_posts_for_interval(pending_posts, lang, start_date, end_date, source_mode="", save_progress=False):
    os.makedirs("temp_pregen", exist_ok=True)
    existing_ids = {post["id"]: post for post in pending_posts if post.get("id")}
    new_entries_added = False
    current_date = start_date
    focus_month = month_key(start_date)

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"\n--- Dia: {date_str} [{lang}] ---")
        day_entries_added = False

        slot1_exists = f"{lang}_{date_str}_{1}" in existing_ids
        slot2_exists = f"{lang}_{date_str}_{2}" in existing_ids
        if slot1_exists and slot2_exists:
            print(f"[{lang}] Ambos os slots ja existem. A saltar.")
            current_date += timedelta(days=1)
            continue

        matching_news = get_news_for_generation(current_date, lang, source_mode=source_mode)
        if not matching_news:
            print(f"[{lang}] Sem noticias historicas para este dia.")
            current_date += timedelta(days=1)
            continue

        print(f"[{lang}] A enviar {len(matching_news)} noticias para a IA...")
        options_list = rank_all_stories_for_day(matching_news, lang)
        if not options_list:
            print(f"[{lang}] Falha na IA.")
            current_date += timedelta(days=1)
            continue

        external_suggestions = generate_external_day_suggestions(current_date, lang, options_list)
        slot1_base_options = options_list[:5]
        slot2_base_options = options_list[5:10] if len(options_list) > 5 else options_list
        slots_to_create = [1, 2] if len(options_list) >= 2 else [1]

        for slot in slots_to_create:
            post_id = f"{lang}_{date_str}_{slot}"
            if post_id in existing_ids:
                continue
            selected_option = 0
            base_options = slot1_base_options if slot == 1 else slot2_base_options
            slot_options = prepare_options_for_review(
                base_options,
                lang,
                date_str,
                matching_news=matching_news,
                selected_option_index=selected_option,
            )
            new_post = normalize_pending_post(
                {
                    "id": post_id,
                    "date": date_str,
                    "slot": slot,
                    "lang": lang,
                    "selected_option": selected_option if selected_option < len(slot_options) else 0,
                    "layout_override": "",
                    "theme_suggestion": "",
                    "manual_background_url": "",
                    "review_action": "",
                    "review_note": "",
                    "status": "pending",
                    "generated_month": month_key(current_date),
                    "external_suggestions": clone_options(external_suggestions),
                    "options": clone_options(slot_options),
                }
            )
            pending_posts.append(new_post)
            existing_ids[post_id] = new_post
            new_entries_added = True
            day_entries_added = True
            print(f"[{lang}] Slot {slot}: Criado ({len(slot_options)} opcoes).")

        if save_progress and day_entries_added:
            sort_pending_posts(pending_posts)
            save_json(PENDING_POSTS_FILE, pending_posts)
            print(f"[{lang}] Progresso guardado ate {date_str}.")

        current_date += timedelta(days=1)

    sort_pending_posts(pending_posts)
    return new_entries_added, focus_month


def main():
    parser = argparse.ArgumentParser(description="Gera e revê filas mensais de posts históricos.")
    parser.add_argument("--lang", choices=["pt"], help="Processa apenas um idioma e gera o respetivo review.")
    parser.add_argument("--start-date", help="Data inicial do intervalo manual (YYYY-MM-DD). Ativa o modo por intervalo para um unico idioma.")
    parser.add_argument("--end-date", help="Data final do intervalo manual (YYYY-MM-DD). Se omitida, usa a data inicial.")
    parser.add_argument(
        "--source-mode",
        choices=["local", "local-first", "arquivo-first", "arquivo-only"],
        default=PREGENERATOR_SOURCE_MODE,
        help="Fonte de noticias historicas: arquivo-first usa Arquivo.pt como principal; arquivo-only nao usa fallback local.",
    )
    args = parser.parse_args()

    interval_mode = bool(args.start_date or args.end_date)
    start_date = None
    end_date = None

    if interval_mode:
        if not args.lang:
            parser.error("O modo por intervalo requer --lang pt|en.")
        if not args.start_date:
            parser.error("O modo por intervalo requer --start-date.")
        try:
            start_date = parse_cli_date(args.start_date, "--start-date")
            end_date = parse_cli_date(args.end_date, "--end-date") if args.end_date else start_date
        except ValueError as exc:
            parser.error(str(exc))
        if start_date and end_date:
            if end_date < start_date:
                parser.error("--end-date tem de ser igual ou posterior a --start-date.")

    langs_to_process = [args.lang] if args.lang else ["pt"]

    print("=== STARTING PREGENERATOR ===")
    pending_posts = [normalize_pending_post(post) for post in load_json(PENDING_POSTS_FILE, [])]

    if interval_mode:
        print("=== STARTING PREGENERATOR INTERVAL MODE ===")
        interval_lang = args.lang
        new_entries_added, interval_focus_month = generate_pending_posts_for_interval(
            pending_posts,
            interval_lang,
            start_date,
            end_date,
            source_mode=args.source_mode,
            save_progress=True,
        )

        if new_entries_added:
            save_json(PENDING_POSTS_FILE, pending_posts)
            print("\npending_posts.json atualizado.")

        generate_review_files(
            pending_posts,
            focus_months={interval_lang: interval_focus_month},
            langs=[interval_lang],
        )
        return

    had_refresh_targets, refresh_changed, refresh_focus_month = refresh_marked_post_images(
        [post for post in pending_posts if post.get("lang") in langs_to_process]
    )

    if had_refresh_targets:
        if refresh_changed:
            sort_pending_posts(pending_posts)
            save_json(PENDING_POSTS_FILE, pending_posts)
            print("\npending_posts.json atualizado apos refresh de imagem.")
        generate_review_files(
            pending_posts,
            focus_months={args.lang: refresh_focus_month} if args.lang else {post_lang: refresh_focus_month for post_lang in langs_to_process},
            langs=langs_to_process,
        )
        return

    had_regeneration_targets, regeneration_changed, regeneration_focus_month = regenerate_marked_posts(
        [post for post in pending_posts if post.get("lang") in langs_to_process]
    )

    if had_regeneration_targets:
        if regeneration_changed:
            sort_pending_posts(pending_posts)
            save_json(PENDING_POSTS_FILE, pending_posts)
            print("\npending_posts.json atualizado apos regeneracao seletiva.")
        generate_review_files(
            pending_posts,
            focus_months={args.lang: regeneration_focus_month} if args.lang else {post_lang: regeneration_focus_month for post_lang in langs_to_process},
            langs=langs_to_process,
        )
        return

    state = load_pregeneration_state()
    if not isinstance(state, dict):
        state = {}
    os.makedirs("temp_pregen", exist_ok=True)
    existing_ids = {post["id"]: post for post in pending_posts if post.get("id")}
    new_entries_added = False
    focus_months = {}
    new_entries_by_lang = {lang: False for lang in langs_to_process}

    for lang in langs_to_process:
        target_month_start = determine_next_target_month(pending_posts, state, lang_filter=lang)
        start_date = target_month_start
        end_date = end_of_month(target_month_start)
        target_month_label = month_key(target_month_start)
        focus_months[lang] = target_month_label
        print(f"Gerando apenas o proximo mes [{lang}]: {target_month_label} ({start_date} a {end_date})")

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            print(f"\n--- Dia: {date_str} [{lang}] ---")

            slot1_exists = f"{lang}_{date_str}_{1}" in existing_ids
            slot2_exists = f"{lang}_{date_str}_{2}" in existing_ids
            if slot1_exists and slot2_exists:
                print(f"[{lang}] Ambos os slots ja existem. A saltar.")
                current_date += timedelta(days=1)
                continue

            matching_news = get_news_for_generation(current_date, lang, source_mode=args.source_mode)
            if not matching_news:
                print(f"[{lang}] Sem noticias historicas para este dia.")
                current_date += timedelta(days=1)
                continue

            print(f"[{lang}] A enviar {len(matching_news)} noticias para a IA...")
            options_list = rank_all_stories_for_day(matching_news, lang)
            if not options_list:
                print(f"[{lang}] Falha na IA.")
                current_date += timedelta(days=1)
                continue

            external_suggestions = generate_external_day_suggestions(current_date, lang, options_list)
            slot1_base_options = options_list[:5]
            slot2_base_options = options_list[5:10] if len(options_list) > 5 else options_list
            slots_to_create = [1, 2] if len(options_list) >= 2 else [1]

            for slot in slots_to_create:
                post_id = f"{lang}_{date_str}_{slot}"
                if post_id in existing_ids:
                    continue
                selected_option = 0
                base_options = slot1_base_options if slot == 1 else slot2_base_options
                slot_options = prepare_options_for_review(
                    base_options,
                    lang,
                    date_str,
                    matching_news=matching_news,
                    selected_option_index=selected_option,
                )
                new_post = normalize_pending_post(
                    {
                        "id": post_id,
                        "date": date_str,
                        "slot": slot,
                        "lang": lang,
                        "selected_option": selected_option if selected_option < len(slot_options) else 0,
                        "layout_override": "",
                        "theme_suggestion": "",
                        "manual_background_url": "",
                        "review_action": "",
                        "review_note": "",
                        "status": "pending",
                        "generated_month": target_month_label,
                        "external_suggestions": clone_options(external_suggestions),
                        "options": clone_options(slot_options),
                    }
                )
                pending_posts.append(new_post)
                existing_ids[post_id] = new_post
                new_entries_added = True
                new_entries_by_lang[lang] = True
                print(f"[{lang}] Slot {slot}: Criado ({len(slot_options)} opcoes).")

            current_date += timedelta(days=1)

    sort_pending_posts(pending_posts)
    if new_entries_added:
        save_json(PENDING_POSTS_FILE, pending_posts)
        print("\npending_posts.json atualizado.")

    for lang in langs_to_process:
        state.setdefault(lang, {})
        if new_entries_by_lang.get(lang):
            state[lang]["last_generated_month"] = focus_months.get(lang, state[lang].get("last_generated_month", ""))
        state[lang]["updated_at"] = datetime.now().isoformat()
        state[lang]["new_entries_added"] = new_entries_added
    save_pregeneration_state(state)
    generate_review_files(pending_posts, focus_months=focus_months, langs=langs_to_process)


if __name__ == "__main__":
    main()
