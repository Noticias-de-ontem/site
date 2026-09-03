import os
import re
import unicodedata
from functools import lru_cache
from io import BytesIO
from urllib.parse import unquote, urlparse

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


TARGET_SIZE = (1080, 1350)
SUPPORTED_LAYOUTS = {
    "template_1",
    "template_2",
    "template_3",
    "breaking",
}

LOGO_CYAN = (0, 199, 214, 255)
TITLE_HIGHLIGHT = (0, 199, 214, 255)
PURE_WHITE = (255, 255, 255, 255)
BODY_CYAN = (193, 241, 244, 255)
OFF_BLACK = (21, 24, 29, 255)
SHADOW = (0, 0, 0, 170)
BADGE_LEFT = (13, 155, 168, 230)
BADGE_RIGHT = (34, 200, 210, 230)
BADGE_BORDER = (80, 234, 242, 90)
FONT_DIR = os.path.join(os.path.dirname(__file__), "montserrat")
FONT_FILES = {
    "black": "Montserrat-Black.ttf",
    "black_italic": "Montserrat-BlackItalic.ttf",
    "bold": "Montserrat-Bold.ttf",
    "extra_bold": "Montserrat-ExtraBold.ttf",
    "extra_bold_italic": "Montserrat-ExtraBoldItalic.ttf",
    "medium": "Montserrat-Medium.ttf",
    "regular": "Montserrat-Regular.ttf",
    "semi_bold": "Montserrat-SemiBold.ttf",
}
BLOCKED_SOURCE_HOST_TERMS = {
    "gettyimages",
    "alamy",
    "shutterstock",
    "istockphoto",
    "dreamstime",
    "depositphotos",
    "adobestock",
    "123rf",
    "freepik",
    "reuters",
    "apnews",
    "apimages",
    "afp",
    "epa",
    "cnn",
    "bbc",
    "nytimes",
    "theguardian",
    "guardian",
    "sicnoticias",
    "publico",
    "expresso",
    "observador",
    "rtp",
    "correiodamanha",
    "jn.pt",
    "instagram",
    "cdninstagram",
    "fbcdn",
    "facebook",
}
BLOCKED_METADATA_TERMS = {
    "watermark",
    "logo",
    "logos",
    "shutterstock",
    "getty",
    "alamy",
    "reuters",
    "afp",
    "associated press",
    "ap photo",
    "bbc news",
    "cnn",
    "sic noticias",
    "publico",
    "expresso",
    "observador",
    "newspaper",
    "headline",
    "breaking news",
    "screenshot",
    "screen shot",
    "infographic",
    "graphic",
    "poster",
    "meme",
    "caption",
    "djvu",
    "pdf",
    "book scan",
    "page scan",
    "document scan",
    "manuscript",
    "text page",
    "scanned page",
}
BLOCKED_IMAGE_URL_TERMS = {
    ".djvu",
    ".pdf",
    ".svg",
}
QUERY_NEGATIVE_TERMS = [
    "-logo",
    "-logos",
    "-watermark",
    "-headline",
    "-screenshot",
    "-infographic",
    "-graphic",
    "-poster",
    "-meme",
    "-caption",
    "-shutterstock",
    "-getty",
    "-alamy",
    "-reuters",
    "-afp",
    "-ap",
    "-cnn",
    "-bbc",
    "-sicnoticias",
    "-publico",
    "-expresso",
    "-observador",
    "-djvu",
    "-pdf",
    "-svg",
]
VOLATILE_IMAGE_HOST_TERMS = {
    "instagram.com",
    "instagram.",
    "cdninstagram.com",
    "cdninstagram",
    "fbcdn",
    "fbcdn.net",
    "fbsbx.com",
    "lookaside.fbsbx",
    "facebook.com",
    "facebook.net",
    "fna.fbcdn",
    "scontent",
}
MIN_BACKGROUND_WIDTH = 1000
MIN_BACKGROUND_HEIGHT = 1000
_GOOGLE_CSE_DISABLED = False


def _normalize_text_value(text, uppercase=False):
    if text is None:
        text = ""
    normalized = unicodedata.normalize("NFC", str(text)).strip()
    return normalized.upper() if uppercase else normalized


def _fold_text_for_compare(text):
    folded = unicodedata.normalize("NFKD", _normalize_text_value(text).casefold())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^\w]+", " ", folded).strip()


def _is_redundant_description(title, description):
    title_folded = _fold_text_for_compare(title)
    description_folded = _fold_text_for_compare(description)
    if not title_folded or not description_folded:
        return False
    if description_folded in title_folded or title_folded in description_folded:
        return True

    title_words = {word for word in title_folded.split() if len(word) > 3}
    description_words = {word for word in description_folded.split() if len(word) > 3}
    if not title_words or not description_words:
        return False
    overlap = len(title_words & description_words) / max(len(description_words), 1)
    return overlap >= 0.72


def _build_background_search_query(title, background_query, category):
    title_clean = " ".join(_normalize_text_value(title).split())
    query_clean = " ".join(_normalize_text_value(background_query).split())
    category_clean = " ".join(_normalize_text_value(category).split())

    if not query_clean:
        query_clean = title_clean
    elif title_clean:
        query_folded = _fold_text_for_compare(query_clean)
        title_folded = _fold_text_for_compare(title_clean)
        query_is_generic = len(query_folded.split()) <= 4 and query_folded not in title_folded
        if query_is_generic:
            query_clean = f"{title_clean} {query_clean}"

    if category_clean and category_clean.lower() not in query_clean.lower():
        query_clean = f"{query_clean} {category_clean}".strip()

    return query_clean[:180].strip()


def _is_blocked_image_candidate(url, mime="", metadata_text=""):
    value = f"{url or ''} {metadata_text or ''}".casefold()
    if any(term in value for term in BLOCKED_IMAGE_URL_TERMS):
        return True
    if mime:
        mime_value = str(mime).casefold()
        allowed_mimes = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
        if mime_value not in allowed_mimes:
            return True
    return any(term in value for term in BLOCKED_METADATA_TERMS)


def _fallback_font_candidates(key):
    win_dir = os.environ.get("WINDIR", "C:\\Windows")
    bold = os.path.join(win_dir, "Fonts", "arialbd.ttf")
    regular = os.path.join(win_dir, "Fonts", "arial.ttf")

    mapping = {
        "medium": [regular],
        "regular": [regular],
    }
    return mapping.get(key, [bold, regular]) + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]


@lru_cache(maxsize=None)
def get_font(key, size):
    filename = FONT_FILES.get(key)
    if filename:
        font_path = os.path.join(FONT_DIR, filename)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)

    for candidate in _fallback_font_candidates(key):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)

    return ImageFont.load_default()


def fit_and_crop(image, target_size):
    image = image.convert("RGBA")
    source_ratio = image.width / image.height
    target_ratio = target_size[0] / target_size[1]

    if source_ratio > target_ratio:
        resized_height = target_size[1]
        resized_width = int(resized_height * source_ratio)
        image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        left = (resized_width - target_size[0]) // 2
        image = image.crop((left, 0, left + target_size[0], target_size[1]))
    else:
        resized_width = target_size[0]
        resized_height = int(resized_width / source_ratio)
        image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        top = (resized_height - target_size[1]) // 2
        image = image.crop((0, top, target_size[0], top + target_size[1]))

    return image


def _build_search_query(query):
    base_terms = " ".join((query or "").split())
    negatives = " ".join(QUERY_NEGATIVE_TERMS)
    return f"{base_terms} {negatives}".strip()


def _candidate_metadata_text(item):
    return " ".join(
        str(value or "")
        for value in [
            item.get("title", ""),
            item.get("snippet", ""),
            item.get("displayLink", ""),
            item.get("link", ""),
            item.get("image", {}).get("contextLink", ""),
        ]
    ).casefold()


def _candidate_host(item):
    for raw_url in [
        item.get("image", {}).get("contextLink", ""),
        item.get("displayLink", ""),
        item.get("link", ""),
    ]:
        if not raw_url:
            continue
        parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
        host = parsed.netloc.casefold()
        if host:
            return host
    return ""


def _url_host(url):
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in str(url) else f"https://{url}")
        return parsed.netloc.casefold()
    except Exception:
        return ""


def is_volatile_image_url(url):
    raw_value = str(url or "")
    values = []
    current = raw_value
    for _ in range(4):
        folded = current.casefold()
        if folded not in values:
            values.append(folded)
        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded

    for value in values:
        if any(term in value for term in VOLATILE_IMAGE_HOST_TERMS):
            return True
        host = _url_host(value)
        if host and any(term in host for term in VOLATILE_IMAGE_HOST_TERMS):
            return True
    return False


def _metadata_is_blocked(item):
    host = _candidate_host(item)
    if any(term in host for term in BLOCKED_SOURCE_HOST_TERMS):
        return True

    metadata_text = _candidate_metadata_text(item)
    return any(term in metadata_text for term in BLOCKED_METADATA_TERMS)


def _prepare_binary_mask(mask_array):
    mask_image = Image.fromarray((mask_array.astype(np.uint8) * 255), mode="L")
    mask_image = mask_image.filter(ImageFilter.MaxFilter(3))
    mask_image = mask_image.filter(ImageFilter.MinFilter(3))
    return np.array(mask_image) > 0


def _component_boxes(mask):
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components = []

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue

            stack = [(x, y)]
            visited[y, x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0

            while stack:
                current_x, current_y = stack.pop()
                area += 1
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)

                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        next_x = current_x + dx
                        next_y = current_y + dy
                        if next_x < 0 or next_x >= width or next_y < 0 or next_y >= height:
                            continue
                        if visited[next_y, next_x] or not mask[next_y, next_x]:
                            continue
                        visited[next_y, next_x] = True
                        stack.append((next_x, next_y))

            components.append(
                {
                    "x1": min_x,
                    "x2": max_x,
                    "y1": min_y,
                    "y2": max_y,
                    "width": max_x - min_x + 1,
                    "height": max_y - min_y + 1,
                    "area": area,
                }
            )

    return components


def _looks_like_overlay_text_or_watermark(image):
    rgb = image.convert("RGB")
    scale = 420 / max(rgb.width, rgb.height)
    resized = rgb.resize(
        (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))),
        Image.Resampling.LANCZOS,
    )

    rgb_array = np.asarray(resized).astype(np.int16)
    gray = np.asarray(resized.convert("L")).astype(np.int16)
    blurred = np.asarray(resized.convert("L").filter(ImageFilter.GaussianBlur(7))).astype(np.int16)
    saturation = rgb_array.max(axis=2) - rgb_array.min(axis=2)
    contrast = np.abs(gray - blurred)

    bright_text = (gray >= 220) & (contrast >= 34) & (saturation <= 42)
    dark_text = (gray <= 28) & (contrast >= 34) & (saturation <= 42)
    candidate_mask = _prepare_binary_mask(bright_text | dark_text)

    components = _component_boxes(candidate_mask)
    if not components:
        return False

    height, width = candidate_mask.shape
    suspicious_large = 0
    suspicious_corner = 0

    for component in components:
        width_ratio = component["width"] / width
        height_ratio = component["height"] / height
        top_band = component["y2"] <= int(height * 0.24)
        bottom_band = component["y1"] >= int(height * 0.76)
        left_corner = component["x2"] <= int(width * 0.35)
        right_corner = component["x1"] >= int(width * 0.65)
        is_corner = (top_band or bottom_band) and (left_corner or right_corner)

        if component["area"] >= 120 and width_ratio >= 0.18 and height_ratio <= 0.14:
            suspicious_large += 1
        if component["area"] >= 55 and is_corner and width_ratio >= 0.07 and height_ratio <= 0.12:
            suspicious_corner += 1

    coverage = float(candidate_mask.mean())
    return suspicious_large >= 1 or suspicious_corner >= 2 or coverage >= 0.045


def _download_image_from_url(image_url, headers=None):
    response = requests.get(image_url, headers=headers or {}, timeout=10)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGBA")


def fetch_background_image(query, lang, google_cse_api_key=None, google_cse_id=None, target_size=TARGET_SIZE, manual_url="", exclude_urls=None):
    global _GOOGLE_CSE_DISABLED

    if manual_url:
        if is_volatile_image_url(manual_url):
            print(f"[{lang}] Imagem manual ignorada: URL temporario do Instagram/Facebook CDN.")
            print(f"[{lang}] Vou tentar pesquisa automatica de imagem como fallback...")
        else:
            try:
                image = _download_image_from_url(manual_url)
                return fit_and_crop(image, target_size), manual_url
            except Exception as exc:
                print(f"[{lang}] Erro imagem manual: {exc}")
                print(f"[{lang}] Vou tentar pesquisa automatica de imagem como fallback...")

    if not _GOOGLE_CSE_DISABLED and google_cse_api_key and google_cse_id and query:
        try:
            excluded = {url for url in (exclude_urls or []) if url}
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            }
            service = build("customsearch", "v1", developerKey=google_cse_api_key)
            result = service.cse().list(
                q=_build_search_query(query),
                cx=google_cse_id,
                searchType="image",
                imgSize="LARGE",
                imgType="photo",
                num=8,
                safe="active",
            ).execute()

            if "items" in result and result["items"]:
                for item in result["items"]:
                    image_url = item.get("link", "")
                    if not image_url or image_url in excluded:
                        continue
                    if is_volatile_image_url(image_url):
                        continue
                    if _is_blocked_image_candidate(image_url, metadata_text=_candidate_metadata_text(item)):
                        continue
                    if _metadata_is_blocked(item):
                        continue

                    try:
                        image = _download_image_from_url(image_url, headers=headers)
                        if image.width >= MIN_BACKGROUND_WIDTH and image.height >= MIN_BACKGROUND_HEIGHT:
                            if not _looks_like_overlay_text_or_watermark(image):
                                return fit_and_crop(image, target_size), image_url
                    except Exception:
                        continue
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (401, 403):
                _GOOGLE_CSE_DISABLED = True
                print(f"[{lang}] Google CSE indisponível para este projeto ({status}). Vou usar o Arquivo.pt...")
            else:
                print(f"[{lang}] Erro Google CSE: {exc}")
        except Exception as exc:
            print(f"[{lang}] Erro Google CSE: {exc}")

    if query:
        try:
            print(f"[{lang}][Wikimedia] A pesquisar imagem para: {query}...")
            excluded = {url for url in (exclude_urls or []) if url}
            headers = {
                "User-Agent": (
                    "NoticiasDeOntem/1.0 "
                    "(https://github.com/; image background lookup)"
                )
            }
            res = requests.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": " ".join(str(query or "").split()),
                    "gsrnamespace": 6,
                    "gsrlimit": 10,
                    "prop": "imageinfo",
                    "iiprop": "url|mime",
                    "iiurlwidth": max(target_size),
                    "format": "json",
                },
                headers=headers,
                timeout=10,
            )
            if res.status_code == 200:
                pages = (res.json().get("query", {}) or {}).get("pages", {}) or {}
                for page in pages.values():
                    info = (page.get("imageinfo") or [{}])[0]
                    image_url = info.get("thumburl") or info.get("url") or ""
                    if not image_url or image_url in excluded:
                        continue
                    source_url = info.get("descriptionurl") or image_url
                    metadata_text = f"{page.get('title', '')} {source_url}"
                    if _is_blocked_image_candidate(image_url, info.get("mime", ""), metadata_text):
                        continue
                    try:
                        image = _download_image_from_url(image_url, headers=headers)
                        if image.width >= MIN_BACKGROUND_WIDTH and image.height >= MIN_BACKGROUND_HEIGHT:
                            if not _looks_like_overlay_text_or_watermark(image):
                                return fit_and_crop(image, target_size), source_url
                    except Exception:
                        continue
        except Exception as exc:
            print(f"[{lang}] Erro Wikimedia: {exc}")

    # Fallback to Arquivo.pt imagesearch
    if query:
        print(f"[{lang}][Arquivo.pt] A pesquisar imagens no Arquivo.pt para: {query}...")
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            }
            res = requests.get("https://arquivo.pt/imagesearch", params={"q": query, "format": "json", "limit": 10}, timeout=8)
            if res.status_code == 200:
                data = res.json()
                items = data.get("responseItems", [])
                excluded = {url for url in (exclude_urls or []) if url}
                for item in items:
                    img_archive_url = item.get("imgLinkToArchive") or item.get("imgURL")
                    if not img_archive_url or img_archive_url in excluded:
                        continue
                    if is_volatile_image_url(img_archive_url):
                        continue
                    if _is_blocked_image_candidate(
                        img_archive_url,
                        metadata_text=" ".join(str(item.get(key, "")) for key in ("title", "pageTitle", "imgAlt", "pageLinkToArchive")),
                    ):
                        continue
                    try:
                        image = _download_image_from_url(img_archive_url, headers=headers)
                        if image.width >= MIN_BACKGROUND_WIDTH and image.height >= MIN_BACKGROUND_HEIGHT:
                            if not _looks_like_overlay_text_or_watermark(image):
                                source_url = item.get("pageLinkToArchive") or img_archive_url
                                return fit_and_crop(image, target_size), source_url
                    except Exception:
                        continue
        except Exception as exc:
            print(f"[{lang}] Erro ao buscar imagem no Arquivo.pt: {exc}")

    return None, ""


def _build_gradient(size, top_rgba, bottom_rgba):
    gradient = Image.new("RGBA", size)
    draw = ImageDraw.Draw(gradient)
    max_y = max(size[1] - 1, 1)

    for y in range(size[1]):
        mix = y / max_y
        color = tuple(
            int(top_rgba[index] * (1.0 - mix) + bottom_rgba[index] * mix)
            for index in range(4)
        )
        draw.line((0, y, size[0], y), fill=color)

    return gradient


def _build_vertical_fade(size, start_ratio, end_alpha, color=(0, 0, 0)):
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start_y = int(size[1] * start_ratio)
    fade_height = max(size[1] - start_y, 1)

    for y in range(start_y, size[1]):
        mix = (y - start_y) / fade_height
        alpha = int(end_alpha * mix)
        draw.line((0, y, size[0], y), fill=(*color, alpha))

    return overlay


def _build_top_fade(size, end_ratio, end_alpha, color=(255, 255, 255)):
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    end_y = max(int(size[1] * end_ratio), 1)

    for y in range(end_y):
        mix = 1.0 - (y / end_y)
        alpha = int(end_alpha * mix)
        draw.line((0, y, size[0], y), fill=(*color, alpha))

    return overlay


def _default_background(size):
    return _build_gradient(size, (92, 92, 92, 255), (20, 20, 20, 255)).filter(ImageFilter.GaussianBlur(2))


def _load_fallback_background(template_path, size):
    if template_path and os.path.exists(template_path):
        try:
            template = Image.open(template_path).convert("RGBA")
            return fit_and_crop(template, size)
        except Exception:
            pass
    return _default_background(size)


def _prepare_dark_background(background_image, template_path, size):
    if background_image is None:
        background_image = _load_fallback_background(template_path, size)
    else:
        background_image = fit_and_crop(background_image, size)

    background_image = ImageEnhance.Color(background_image).enhance(0.58)
    background_image = ImageEnhance.Brightness(background_image).enhance(0.60)
    background_image = ImageEnhance.Contrast(background_image).enhance(0.94)
    background_image = background_image.filter(ImageFilter.GaussianBlur(1.2))
    background_image = Image.alpha_composite(
        background_image,
        _build_gradient(size, (66, 66, 66, 110), (0, 0, 0, 96)),
    )
    return background_image


def _prepare_template_1_background(background_image, template_path, size):
    background = _prepare_dark_background(background_image, template_path, size)
    background = Image.alpha_composite(background, _build_vertical_fade(size, 0.50, 228))
    return background


def _prepare_template_2_background(background_image, template_path, size):
    if background_image is None:
        background_image = _load_fallback_background(template_path, size)
    else:
        background_image = fit_and_crop(background_image, size)

    background_image = ImageEnhance.Color(background_image).enhance(0.78)
    background_image = ImageEnhance.Brightness(background_image).enhance(0.92)
    background_image = ImageEnhance.Contrast(background_image).enhance(0.98)
    background_image = background_image.filter(ImageFilter.GaussianBlur(0.9))
    background_image = Image.alpha_composite(
        background_image,
        _build_top_fade(size, 0.70, 232),
    )
    background_image = Image.alpha_composite(
        background_image,
        _build_gradient(size, (255, 255, 255, 24), (0, 0, 0, 18)),
    )
    return background_image


def _prepare_template_3_background(background_image, template_path, size):
    background = _prepare_dark_background(background_image, template_path, size)
    background = ImageEnhance.Brightness(background).enhance(0.82)
    background = Image.alpha_composite(
        background,
        _build_gradient(size, (0, 0, 0, 86), (0, 0, 0, 46)),
    )
    background = Image.alpha_composite(background, _build_vertical_fade(size, 0.44, 205))
    return background


def _prepare_breaking_background(background_image, template_path, size):
    canvas = Image.new("RGBA", size, (0, 0, 0, 255))

    if background_image is not None:
        image = fit_and_crop(background_image, size)
        image = ImageEnhance.Color(image).enhance(0.22)
        image = ImageEnhance.Brightness(image).enhance(0.20)
        image = image.filter(ImageFilter.GaussianBlur(10))
        image = Image.alpha_composite(image, _build_gradient(size, (0, 0, 0, 215), (0, 0, 0, 245)))
        canvas = Image.blend(canvas, image, 0.12)

    return canvas


def _normalize_for_match(text):
    cleaned = unicodedata.normalize("NFKD", text.casefold())
    cleaned = "".join(ch for ch in cleaned if unicodedata.category(ch) != "Mn")
    return re.sub(r"^[^\w]+|[^\w]+$", "", cleaned)


def _title_tokens(title_text, highlight_text):
    clean_title = " ".join(_normalize_text_value(title_text).split()).upper()
    tokens = [{"text": token, "highlight": False} for token in clean_title.split()]

    clean_highlight = " ".join(_normalize_text_value(highlight_text).split()).upper()
    if not tokens or not clean_highlight:
        return tokens

    normalized_title = [_normalize_for_match(token["text"]) for token in tokens]
    normalized_highlight = [
        _normalize_for_match(token)
        for token in clean_highlight.split()
        if _normalize_for_match(token)
    ]

    if not normalized_highlight:
        return tokens

    for start in range(len(tokens) - len(normalized_highlight) + 1):
        if normalized_title[start:start + len(normalized_highlight)] == normalized_highlight:
            for index in range(start, start + len(normalized_highlight)):
                tokens[index]["highlight"] = True
            break

    return tokens


def _measure_text(draw, text, font):
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_tokens(draw, tokens, font, max_width):
    if not tokens:
        return []

    lines = []
    current = []

    for token in tokens:
        trial = current + [token]
        trial_text = " ".join(item["text"] for item in trial)
        trial_width, _ = _measure_text(draw, trial_text, font)

        if current and trial_width > max_width:
            lines.append(current)
            current = [token]
        else:
            current = trial

    if current:
        lines.append(current)

    return lines


def _wrap_text(draw, text, font, max_width):
    words = " ".join((text or "").split()).split()
    if not words:
        return []

    lines = []
    current = []

    for word in words:
        trial = current + [word]
        trial_text = " ".join(trial)
        trial_width, _ = _measure_text(draw, trial_text, font)

        if current and trial_width > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current = trial

    if current:
        lines.append(" ".join(current))

    return lines


def _fit_title(draw, title_text, highlight_text, max_width, max_height, max_lines=3, largest=100, smallest=60):
    tokens = _title_tokens(title_text, highlight_text)

    for size in range(largest, smallest - 1, -2):
        font = get_font("black", size)
        lines = _wrap_tokens(draw, tokens, font, max_width)
        line_height = _measure_text(draw, "ÁQ", font)[1]
        spacing = max(3, int(size * 0.08))
        total_height = line_height * len(lines) + spacing * max(0, len(lines) - 1)

        if len(lines) <= max_lines and total_height <= max_height:
            return font, lines, line_height, spacing

    fallback_font = get_font("black", smallest)
    fallback_lines = _wrap_tokens(draw, tokens, fallback_font, max_width)
    return fallback_font, fallback_lines[:max_lines], _measure_text(draw, "ÁQ", fallback_font)[1], 6


def _fit_paragraph(draw, text, font_key, max_width, max_height, max_lines, largest, smallest):
    clean_text = " ".join((text or "").split())

    for size in range(largest, smallest - 1, -2):
        font = get_font(font_key, size)
        lines = _wrap_text(draw, clean_text, font, max_width)
        line_height = _measure_text(draw, "Ág", font)[1]
        spacing = max(6, int(size * 0.18))
        total_height = line_height * len(lines) + spacing * max(0, len(lines) - 1)

        if len(lines) <= max_lines and total_height <= max_height:
            return font, lines, line_height, spacing

    font = get_font(font_key, smallest)
    lines = _wrap_text(draw, clean_text, font, max_width)[:max_lines]
    return font, lines, _measure_text(draw, "Ág", font)[1], max(6, int(smallest * 0.18))


def _draw_blurred_text_shadow(base_image, position, text, font, shadow_fill, offset, blur, spacing=0, align="left"):
    shadow_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_position = (position[0] + offset[0], position[1] + offset[1])
    shadow_draw.multiline_text(
        shadow_position,
        text,
        font=font,
        fill=shadow_fill,
        spacing=spacing,
        align=align,
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(base_image, shadow_layer)


def _draw_gradient_badge(width, height, radius, left_color=BADGE_LEFT, right_color=BADGE_RIGHT, border_color=BADGE_BORDER):
    badge = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (width, height))
    gradient_draw = ImageDraw.Draw(gradient)
    max_x = max(width - 1, 1)

    for x in range(width):
        mix = x / max_x
        color = tuple(
            int(left_color[index] * (1.0 - mix) + right_color[index] * mix)
            for index in range(4)
        )
        gradient_draw.line((x, 0, x, height), fill=color)

    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    gradient.putalpha(mask)
    badge.alpha_composite(gradient)

    border = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    border_draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=radius,
        outline=border_color,
        width=2,
    )
    badge.alpha_composite(border)
    return badge


def _draw_brand_badge(base_image, text, x, y, align="left", use_shadow=True, font_size=34, compact=False):
    text = _normalize_text_value(text or "ATUALIDADE", uppercase=True)
    measure_draw = ImageDraw.Draw(base_image)
    font = get_font("medium", font_size)
    text_width, text_height = _measure_text(measure_draw, text, font)

    badge_height = 58 if compact else 68
    padding_x = 20 if compact else 24
    badge_width = min(max(140 if compact else 196, text_width + padding_x * 2), 340 if compact else 360)
    radius = 10 if compact else 12

    if align == "center":
        x = int(x - badge_width / 2)
    elif align == "right":
        x = x - badge_width

    if use_shadow:
        shadow_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.rounded_rectangle(
            (x + 5, y + 8, x + badge_width + 5, y + badge_height + 8),
            radius=radius,
            fill=(0, 0, 0, 84),
        )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(12))
        base_image = Image.alpha_composite(base_image, shadow_layer)

    badge = _draw_gradient_badge(badge_width, badge_height, radius)
    base_image.paste(badge, (x, y), badge)

    text_x = x + (badge_width - text_width) // 2
    text_y = y + (badge_height - text_height) // 2 - 3

    if use_shadow:
        base_image = _draw_blurred_text_shadow(
            base_image,
            (text_x, text_y),
            text,
            font,
            (0, 0, 0, 120),
            (2, 3),
            4,
        )

    draw = ImageDraw.Draw(base_image)
    draw.text((text_x, text_y), text, font=font, fill=PURE_WHITE)
    return base_image


def _draw_breaking_badge(base_image, text, x, y):
    text = _normalize_text_value(text or "ÚLTIMA HORA", uppercase=True)
    measure_draw = ImageDraw.Draw(base_image)
    font = get_font("bold", 26)
    text_width, text_height = _measure_text(measure_draw, text, font)

    badge_height = 48
    badge_width = text_width + 26
    radius = 8
    badge = _draw_gradient_badge(
        badge_width,
        badge_height,
        radius,
        left_color=(22, 171, 185, 245),
        right_color=(0, 199, 214, 245),
        border_color=(255, 255, 255, 40),
    )
    base_image.paste(badge, (x, y), badge)

    draw = ImageDraw.Draw(base_image)
    text_x = x + (badge_width - text_width) // 2
    text_y = y + (badge_height - text_height) // 2 - 2
    draw.text((text_x, text_y), text, font=font, fill=PURE_WHITE)
    return base_image


def _draw_logo(base_image, lang, left=58, top=74, right=None, center_x=None, scale=1.0, use_shadows=True):
    top_text = "NOTÍCIAS" if lang == "pt" else "YESTERDAY'S"
    bottom_text = "DE ONTEM" if lang == "pt" else "NEWS"
    top_font = get_font("extra_bold_italic", int(74 * scale))
    bottom_font = get_font("black_italic", int(66 * scale))
    measure_draw = ImageDraw.Draw(base_image)
    top_width, top_height = _measure_text(measure_draw, top_text, top_font)
    bottom_width, _ = _measure_text(measure_draw, bottom_text, bottom_font)
    clock_size = int(94 * scale)
    content_width = max(top_width + clock_size - int(20 * scale), bottom_width)

    logo_left = left
    if right is not None:
        logo_left = base_image.width - right - content_width
    elif center_x is not None:
        logo_left = int(center_x - (content_width / 2))

    if use_shadows:
        base_image = _draw_blurred_text_shadow(
            base_image,
            (logo_left, top),
            top_text,
            top_font,
            SHADOW,
            (int(4 * scale), int(8 * scale)),
            max(4, int(9 * scale)),
        )

    draw = ImageDraw.Draw(base_image)
    draw.text((logo_left, top), top_text, font=top_font, fill=LOGO_CYAN)

    clock_left = logo_left + top_width - int(20 * scale)
    clock_top = top - int(10 * scale)

    if use_shadows:
        shadow_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.arc(
            (clock_left + int(5 * scale), clock_top + int(8 * scale), clock_left + clock_size + int(5 * scale), clock_top + clock_size + int(8 * scale)),
            start=210,
            end=35,
            fill=SHADOW,
            width=max(4, int(10 * scale)),
        )
        shadow_draw.line(
            (
                clock_left + clock_size * 0.52 + int(5 * scale),
                clock_top + clock_size * 0.28 + int(8 * scale),
                clock_left + clock_size * 0.52 + int(5 * scale),
                clock_top + clock_size * 0.56 + int(8 * scale),
            ),
            fill=SHADOW,
            width=max(4, int(9 * scale)),
        )
        shadow_draw.line(
            (
                clock_left + clock_size * 0.52 + int(5 * scale),
                clock_top + clock_size * 0.56 + int(8 * scale),
                clock_left + clock_size * 0.72 + int(5 * scale),
                clock_top + clock_size * 0.72 + int(8 * scale),
            ),
            fill=SHADOW,
            width=max(4, int(9 * scale)),
        )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(max(4, int(8 * scale))))
        base_image = Image.alpha_composite(base_image, shadow_layer)

    draw = ImageDraw.Draw(base_image)
    draw.arc(
        (clock_left, clock_top, clock_left + clock_size, clock_top + clock_size),
        start=210,
        end=35,
        fill=LOGO_CYAN,
        width=max(4, int(8 * scale)),
    )
    draw.line(
        (
            clock_left + clock_size * 0.52,
            clock_top + clock_size * 0.28,
            clock_left + clock_size * 0.52,
            clock_top + clock_size * 0.56,
        ),
        fill=LOGO_CYAN,
        width=max(4, int(8 * scale)),
    )
    draw.line(
        (
            clock_left + clock_size * 0.52,
            clock_top + clock_size * 0.56,
            clock_left + clock_size * 0.72,
            clock_top + clock_size * 0.72,
        ),
        fill=LOGO_CYAN,
        width=max(4, int(8 * scale)),
    )

    bottom_top = top + top_height - int(8 * scale)
    if use_shadows:
        base_image = _draw_blurred_text_shadow(
            base_image,
            (logo_left + int(2 * scale), bottom_top),
            bottom_text,
            bottom_font,
            SHADOW,
            (int(4 * scale), int(8 * scale)),
            max(4, int(9 * scale)),
        )

    draw = ImageDraw.Draw(base_image)
    draw.text((logo_left + int(2 * scale), bottom_top), bottom_text, font=bottom_font, fill=PURE_WHITE)
    return base_image


def _draw_year_tag(base_image, year, x, y, align="left", use_shadow=True, font_size=28):
    if not year:
        return base_image, 0
    text = f"EM {year}"
    font = get_font("bold", font_size)
    draw = ImageDraw.Draw(base_image)
    text_width, text_height = _measure_text(draw, text, font)
    
    draw_x = x
    if align == "center":
        draw_x = x - text_width // 2
    elif align == "right":
        draw_x = x - text_width
        
    if use_shadow:
        base_image = _draw_blurred_text_shadow(
            base_image,
            (draw_x, y),
            text,
            font,
            SHADOW,
            (2, 4),
            5,
        )
    
    draw = ImageDraw.Draw(base_image)
    draw.text(
        (draw_x, y),
        text,
        font=font,
        fill=TITLE_HIGHLIGHT,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 185),
    )
    return base_image, text_height


def _draw_title(
    base_image,
    title,
    highlight_text,
    x,
    y,
    max_width,
    max_height,
    align="left",
    base_fill=PURE_WHITE,
    highlight_fill=TITLE_HIGHLIGHT,
    use_shadow=True,
    shadow_fill=SHADOW,
    largest=100,
    smallest=60,
    max_lines=4,
    shadow_offset=(6, 10),
    shadow_blur=12,
):
    measure_draw = ImageDraw.Draw(base_image)
    font, lines, line_height, spacing = _fit_title(
        measure_draw,
        title,
        highlight_text,
        max_width,
        max_height,
        max_lines=max_lines,
        largest=largest,
        smallest=smallest,
    )

    current_y = y
    for line in lines:
        line_text = " ".join(token["text"] for token in line)
        line_width, _ = _measure_text(measure_draw, line_text, font)
        cursor_x = x
        if align == "center":
            cursor_x = x + (max_width - line_width) // 2
        elif align == "right":
            cursor_x = x + max_width - line_width

        if use_shadow:
            base_image = _draw_blurred_text_shadow(
                base_image,
                (cursor_x, current_y),
                line_text,
                font,
                shadow_fill,
                shadow_offset,
                shadow_blur,
            )

        draw = ImageDraw.Draw(base_image)
        running_x = cursor_x
        for index, token in enumerate(line):
            fill = highlight_fill if token["highlight"] else base_fill
            stroke_width = 2 if token["highlight"] else 0
            stroke_fill = (0, 0, 0, 175)
            draw.text(
                (running_x, current_y),
                token["text"],
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
            )
            token_width, _ = _measure_text(draw, token["text"], font)
            running_x += token_width
            if index < len(line) - 1:
                space_width, _ = _measure_text(draw, " ", font)
                running_x += space_width

        current_y += line_height + spacing

    return base_image, current_y - y


def _draw_description(base_image, description, lang, x, y, max_width, max_height, align="left", use_shadow=True):
    description = _normalize_text_value(description)
    if not description or max_height < 40:
        return base_image

    fallback = (
        "Breve descrição com detalhes adicionais para atrair o público jovem."
        if lang == "pt"
        else "Short description with extra details to attract a younger audience."
    )
    fallback = _normalize_text_value(fallback)
    measure_draw = ImageDraw.Draw(base_image)
    font, lines, line_height, spacing = _fit_paragraph(
        measure_draw,
        description,
        "regular",
        max_width,
        max_height,
        max_lines=3,
        largest=58,
        smallest=42,
    )

    current_y = y
    for line in lines:
        line_width, _ = _measure_text(measure_draw, line, font)
        text_x = x
        if align == "center":
            text_x = x + (max_width - line_width) // 2
        elif align == "right":
            text_x = x + max_width - line_width

        if use_shadow:
            base_image = _draw_blurred_text_shadow(
                base_image,
                (text_x, current_y),
                line,
                font,
                (0, 0, 0, 120),
                (2, 4),
                5,
            )

        draw = ImageDraw.Draw(base_image)
        draw.text((text_x, current_y), line, font=font, fill=BODY_CYAN)
        current_y += line_height + spacing

    return base_image


def _draw_footer(base_image, lang, use_shadow=True):
    footer = "LÊ A DESCRIÇÃO" if lang == "pt" else "READ THE DESCRIPTION"
    font = get_font("medium", 26)
    x = 62
    y = base_image.height - 86

    if use_shadow:
        base_image = _draw_blurred_text_shadow(
            base_image,
            (x, y),
            footer,
            font,
            (0, 0, 0, 110),
            (2, 3),
            4,
        )

    draw = ImageDraw.Draw(base_image)
    draw.text((x, y), footer, font=font, fill=BODY_CYAN)
    return base_image


def _clamp_box(box, width, height):
    x1, y1, x2, y2 = box
    return (
        max(0, min(int(x1), width - 1)),
        max(0, min(int(y1), height - 1)),
        max(1, min(int(x2), width)),
        max(1, min(int(y2), height)),
    )


def _region_stats(image, box):
    x1, y1, x2, y2 = _clamp_box(box, image.width, image.height)
    if x2 <= x1 or y2 <= y1:
        return {"mean": 0.0, "stddev": 0.0, "edge": 0.0}

    crop = image.crop((x1, y1, x2, y2)).convert("L")
    base_stat = ImageStat.Stat(crop)
    edge_stat = ImageStat.Stat(crop.filter(ImageFilter.FIND_EDGES))
    return {
        "mean": float(base_stat.mean[0]),
        "stddev": float(base_stat.stddev[0]),
        "edge": float(edge_stat.mean[0]),
    }


def _safe_score(value, low, high, invert=False):
    if high <= low:
        return 0.5
    ratio = (value - low) / (high - low)
    ratio = max(0.0, min(1.0, ratio))
    return 1.0 - ratio if invert else ratio


TEXT_ZONES_BY_LAYOUT = {
    "template_1": [(48, 760, 1040, 1250)],
    "template_2": [(76, 200, 1004, 690)],
    "template_3": [(70, 885, 1010, 1285)],
    "breaking": [(76, 330, 1004, 1165)],
}


def _box_area(box):
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def _intersect_area(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return _box_area((max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)))


def _expand_box(box, width, height, ratio=0.18):
    x1, y1, x2, y2 = box
    pad_x = int((x2 - x1) * ratio)
    pad_y = int((y2 - y1) * ratio)
    return _clamp_box((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), width, height)


def _detect_face_boxes(image):
    try:
        import cv2
    except Exception:
        return []

    try:
        rgb = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray = cv2.equalizeHist(gray)

        cascade_names = [
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
            "haarcascade_profileface.xml",
        ]
        boxes = []
        for name in cascade_names:
            cascade_path = os.path.join(cv2.data.haarcascades, name)
            detector = cv2.CascadeClassifier(cascade_path)
            if detector.empty():
                continue
            for x, y, w, h in detector.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(56, 56),
            ):
                boxes.append(_expand_box((int(x), int(y), int(x + w), int(y + h)), image.width, image.height))

        deduped = []
        for box in sorted(boxes, key=_box_area, reverse=True):
            if all(_intersect_area(box, existing) / max(1, _box_area(box)) < 0.55 for existing in deduped):
                deduped.append(box)
        return deduped[:8]
    except Exception:
        return []


def _face_text_overlap_score(face_boxes, text_zones):
    if not face_boxes:
        return 0.0
    score = 0.0
    for face in face_boxes:
        face_area = max(1, _box_area(face))
        for zone in text_zones:
            intersection = _intersect_area(face, zone)
            if intersection:
                score += intersection / face_area
    return score


def resolve_layout_name(layout_name, layout_preference="", background_image=None, breaking_candidate=False):
    normalized_direct = (layout_name or "").strip().lower()
    if normalized_direct and normalized_direct != "auto":
        normalized_direct = normalized_direct.replace("-", "_")
        if normalized_direct in SUPPORTED_LAYOUTS:
            return normalized_direct

    preference = (layout_preference or "").strip().lower().replace("-", "_")

    if background_image is None:
        if breaking_candidate:
            return "breaking"
        return preference if preference in SUPPORTED_LAYOUTS else "template_1"

    top_center = _region_stats(background_image, (160, 110, 920, 565))
    bottom_left = _region_stats(background_image, (40, 760, 650, 1260))
    bottom_center = _region_stats(background_image, (170, 850, 920, 1250))

    scores = {
        "template_1": 0.58,
        "template_2": 0.30,
        "template_3": 0.56,
    }

    scores["template_1"] += _safe_score(bottom_left["mean"], 65, 150, invert=True) * 0.26
    scores["template_1"] += _safe_score(bottom_left["edge"], 18, 56, invert=True) * 0.18

    scores["template_2"] += _safe_score(top_center["edge"], 16, 48, invert=True) * 0.28
    scores["template_2"] += _safe_score(top_center["mean"], 85, 190) * 0.14
    scores["template_2"] += _safe_score(top_center["stddev"], 10, 60, invert=True) * 0.08

    scores["template_3"] += _safe_score(bottom_center["mean"], 55, 138, invert=True) * 0.26
    scores["template_3"] += _safe_score(bottom_center["edge"], 18, 58, invert=True) * 0.20

    if top_center["mean"] > 140 and top_center["stddev"] < 62:
        scores["template_2"] -= 0.28
        scores["template_3"] += 0.10
    if top_center["edge"] > 32 or top_center["stddev"] > 45:
        scores["template_2"] -= 0.32

    if preference in scores:
        scores[preference] += 0.0 if preference == "template_2" else 0.18

    face_boxes = _detect_face_boxes(background_image)
    if face_boxes:
        for layout, zones in TEXT_ZONES_BY_LAYOUT.items():
            if layout not in scores:
                continue
            overlap = _face_text_overlap_score(face_boxes, zones)
            if overlap > 0:
                scores[layout] -= 3.5 + (overlap * 5.0)

        if breaking_candidate:
            breaking_overlap = _face_text_overlap_score(face_boxes, TEXT_ZONES_BY_LAYOUT["breaking"])
            if breaking_overlap <= 0.015:
                return "breaking"
    elif breaking_candidate:
        return "breaking"

    return max(scores, key=lambda k: scores[k])


def render_template_1(
    category,
    title,
    description,
    highlight_text,
    lang,
    background_image=None,
    template_path=None,
    text_shadows=True,
    year=None,
):
    canvas = _prepare_template_1_background(background_image, template_path, TARGET_SIZE)
    canvas = _draw_logo(canvas, lang, use_shadows=True)
    canvas = _draw_brand_badge(canvas, category, 58, 790, use_shadow=text_shadows)
    canvas, title_height = _draw_title(
        canvas,
        title,
        highlight_text,
        58,
        878,
        948,
        212,
        align="left",
        base_fill=PURE_WHITE,
        highlight_fill=TITLE_HIGHLIGHT,
        use_shadow=text_shadows,
        largest=100,
        smallest=60,
        max_lines=4,
    )
    year_height = 0
    if year:
        canvas, year_height = _draw_year_tag(canvas, year, 58, 878 + title_height + 12, align="left", use_shadow=text_shadows)
    
    description_top = 878 + title_height + 12 + (year_height + 28 if year_height else 28)
    footer_top = canvas.height - 86
    show_footer = description_top + 150 < footer_top
    description_limit = footer_top - 42 if show_footer else canvas.height - 30
    description_max_height = max(92, description_limit - description_top)
    canvas = _draw_description(canvas, description, lang, 62, description_top, 930, description_max_height, use_shadow=text_shadows)
    if show_footer:
        canvas = _draw_footer(canvas, lang, use_shadow=text_shadows)
    return canvas


def render_template_2(category, title, description, highlight_text, lang, background_image=None, template_path=None, year=None):
    del description
    canvas = _prepare_template_2_background(background_image, template_path, TARGET_SIZE)
    canvas = _draw_logo(canvas, lang, use_shadows=True)
    canvas = _draw_brand_badge(canvas, category, TARGET_SIZE[0] - 58, 74, align="right", use_shadow=True, compact=True, font_size=30)
    canvas, title_height = _draw_title(
        canvas,
        title,
        highlight_text,
        92,
        235,
        896,
        370,
        align="center",
        base_fill=OFF_BLACK,
        highlight_fill=TITLE_HIGHLIGHT,
        use_shadow=False,
        largest=84,
        smallest=52,
        max_lines=5,
    )
    if year:
        canvas, _ = _draw_year_tag(canvas, year, TARGET_SIZE[0] // 2, 235 + title_height + 16, align="center", use_shadow=False)
    return canvas


def render_template_3(category, title, description, highlight_text, lang, background_image=None, template_path=None, year=None):
    del description
    canvas = _prepare_template_3_background(background_image, template_path, TARGET_SIZE)
    canvas = _draw_logo(canvas, lang, use_shadows=True)
    canvas = _draw_brand_badge(canvas, category, TARGET_SIZE[0] // 2, 910, align="center", use_shadow=True, compact=True, font_size=28)
    canvas, title_height = _draw_title(
        canvas,
        title,
        highlight_text,
        94,
        978,
        892,
        280,
        align="center",
        base_fill=PURE_WHITE,
        highlight_fill=TITLE_HIGHLIGHT,
        use_shadow=True,
        largest=76,
        smallest=48,
        max_lines=5,
        shadow_offset=(4, 8),
        shadow_blur=9,
    )
    if year:
        canvas, _ = _draw_year_tag(canvas, year, TARGET_SIZE[0] // 2, 978 + title_height + 14, align="center", use_shadow=True)
    return canvas


def render_breaking_template(category, title, description, highlight_text, lang, background_image=None, template_path=None, year=None):
    del description
    canvas = _prepare_breaking_background(background_image, template_path, TARGET_SIZE)
    draw = ImageDraw.Draw(canvas)
    accent_width = 126
    accent_height = 8
    accent_x = (TARGET_SIZE[0] - accent_width) // 2
    accent_y = 168
    draw.rounded_rectangle(
        (accent_x, accent_y, accent_x + accent_width, accent_y + accent_height),
        radius=5,
        fill=(44, 216, 232, 255),
    )
    canvas = _draw_logo(canvas, lang, use_shadows=True)

    breaking_text = "ÚLTIMA HORA" if lang == "pt" else "BREAKING"
    measure_draw = ImageDraw.Draw(canvas)
    break_font = get_font("bold", 26)
    break_text_width, break_text_height = _measure_text(measure_draw, breaking_text, break_font)
    break_width = break_text_width + 26

    show_main_category = bool(category and category.strip() and category.strip().upper() not in {"NEWS", "ATUALIDADE"})
    main_width = 0
    badge_gap = 18
    if show_main_category:
        category_font = get_font("medium", 24)
        main_text_width, _ = _measure_text(measure_draw, category.upper().strip(), category_font)
        main_width = min(max(140, main_text_width + 40), 300)

    total_badges_width = break_width + (badge_gap + main_width if show_main_category else 0)
    badges_left = (TARGET_SIZE[0] - total_badges_width) // 2
    badge_top = 336

    canvas = _draw_breaking_badge(canvas, breaking_text, badges_left, badge_top)
    if show_main_category:
        canvas = _draw_brand_badge(
            canvas,
            category,
            badges_left + break_width + badge_gap,
            badge_top - 2,
            align="left",
            use_shadow=False,
            compact=True,
            font_size=24,
        )

    canvas, title_height = _draw_title(
        canvas,
        title,
        highlight_text,
        92,
        424,
        896,
        730,
        align="center",
        base_fill=PURE_WHITE,
        highlight_fill=TITLE_HIGHLIGHT,
        use_shadow=False,
        largest=82,
        smallest=54,
        max_lines=7,
    )
    if year:
        canvas, _ = _draw_year_tag(canvas, year, TARGET_SIZE[0] // 2, 424 + title_height + 18, align="center", use_shadow=False)
    return canvas


def create_image_with_text(
    category_to_draw,
    title_to_draw,
    lang,
    template_path="template.jpg",
    overlay_path=None,
    output_path="output.jpg",
    description_to_draw="",
    highlight_text="",
    layout_name="auto",
    background_query=None,
    google_cse_api_key=None,
    google_cse_id=None,
    background_image=None,
    layout_preference="",
    breaking_candidate=False,
    manual_background_url="",
    exclude_background_urls=None,
    return_details=False,
    year=None,
):
    del overlay_path

    title_to_draw = _normalize_text_value(title_to_draw or "Título principal")
    category_to_draw = _normalize_text_value(category_to_draw or ("ATUALIDADE" if lang == "pt" else "NEWS"), uppercase=True)
    description_to_draw = _normalize_text_value(description_to_draw)
    highlight_text = _normalize_text_value(highlight_text)
    background_query = _normalize_text_value(background_query)

    if _is_redundant_description(title_to_draw, description_to_draw):
        description_to_draw = ""

    # Limpar dinamicamente o ano do final do título para evitar duplicações
    if year:
        year_str = str(year).strip()
        pattern = re.compile(rf"\s+(?:em|in)?\s*{year_str}\s*$", re.IGNORECASE)
        title_to_draw = pattern.sub("", title_to_draw).strip()

    background_source_url = ""

    if background_image is None:
        query = _build_background_search_query(title_to_draw, background_query, category_to_draw)
        background_image, background_source_url = fetch_background_image(
            query,
            lang,
            google_cse_api_key=google_cse_api_key,
            google_cse_id=google_cse_id,
            target_size=TARGET_SIZE,
            manual_url=manual_background_url,
            exclude_urls=exclude_background_urls,
        )

    resolved_layout = resolve_layout_name(
        layout_name=layout_name,
        layout_preference=layout_preference,
        background_image=background_image,
        breaking_candidate=breaking_candidate,
    )

    if resolved_layout == "template_4":
        resolved_layout = "template_1"

    if resolved_layout == "template_1":
        rendered = render_template_1(
            category_to_draw,
            title_to_draw,
            description_to_draw,
            highlight_text,
            lang,
            background_image=background_image,
            template_path=template_path,
            text_shadows=True,
            year=year,
        )
    elif resolved_layout == "template_2":
        rendered = render_template_2(
            category_to_draw,
            title_to_draw,
            description_to_draw,
            highlight_text,
            lang,
            background_image=background_image,
            template_path=template_path,
            year=year,
        )
    elif resolved_layout == "template_3":
        rendered = render_template_3(
            category_to_draw,
            title_to_draw,
            description_to_draw,
            highlight_text,
            lang,
            background_image=background_image,
            template_path=template_path,
            year=year,
        )
    elif resolved_layout == "breaking":
        rendered = render_breaking_template(
            category_to_draw,
            title_to_draw,
            description_to_draw,
            highlight_text,
            lang,
            background_image=background_image,
            template_path=template_path,
            year=year,
        )
    else:
        raise ValueError(f"Layout não suportado: {resolved_layout}")

    rendered.convert("RGB").save(output_path, quality=95)

    if return_details:
        return {
            "output_path": output_path,
            "background_source_url": background_source_url,
            "background_query": background_query,
            "resolved_layout": resolved_layout,
        }

    return output_path

