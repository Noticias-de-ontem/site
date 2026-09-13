"""Análise de fotografias com a API Gemini.

Escolhe o ponto focal correto para recortes de banner (1600x700) e de capa
(1080x1350) e avalia se uma foto serve para os dois formatos. Os resultados
são guardados em cache por hash do ficheiro, pelo que rebuilds não repetem
chamadas à API e o CI consegue construir o site sem chave configurada.
"""

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "gemini_photo_cache.json"
# Cada modelo tem quota própria na free tier (quotaId "...PerModel"): quando
# um esgota (dia) ou falha (404), passa ao seguinte; aliases como
# "gemini-flash-latest" apontam para o mesmo modelo e não trazem quota nova.
DEFAULT_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
]
ANALYSIS_MAX_EDGE = 832
ANALYSIS_JPEG_QUALITY = 82
REQUEST_TIMEOUT = 45
# O free tier limita pedidos por minuto: espaçar chamadas e esperar nos 429
# evita que rebuilds com muitas fotos esgotam a quota a meio.
MIN_CALL_INTERVAL = 4.0
_last_call_monotonic = 0.0

_PROMPT_BASE = """Analisa esta fotografia para um site de notícias histórico.
Notícia a ilustrar: "{news_title}"

Contexto: a foto será recortada em dois formatos:
- "banner": recorte largo 1600x700 (proporção ~2.3:1), mostrado atrás do título no topo da página;
- "capa": recorte vertical 1080x1350 (proporção 4:5), usado nos cartões de notícias.

Responde APENAS com um objeto JSON válido, sem markdown, com estas chaves:
{{
  "subject": "descrição curta do motivo principal (max 12 palavras)",
  "embedded_text": true se contém texto/gráficos/logo/cartaz dominante que ficaria atrás de títulos, senão false,
  "faces": [[cx, cy, w, h], ...] caixas das ATÉ 4 caras principais em coordenadas normalizadas 0-1 (lista vazia se nenhuma; nunca mais de 4),
  "banner_focus": [cx, cy] centro normalizado 0-1 da região a MANTER num recorte largo 2.3:1 (colocar o motivo/cara principal visível e inteira, com margem acima da cabeça),
  "cover_focus": [cx, cy] centro normalizado 0-1 da região a manter num recorte vertical 4:5,
  "banner_suitable": true se um recorte 2.3:1 desta foto continua a mostrar bem o motivo principal (cara inteira, sem cortes brutais, sem texto dominante), senão false,
  "cover_suitable": true se um recorte 4:5 mostra bem o motivo principal, senão false,
  "relevant": true se esta foto é uma escolha plausível para ilustrar a notícia (pessoa, lugar, objeto ou tema direta ou contextualmente ligado à notícia), senão false,
  "reason": "justificação curta em português (max 20 palavras)"
}}

Regras:
- As coordenadas são frações 0-1 da largura/altura da imagem (origem topo-esquerda).
- Em banner_focus, prefere centro-x do motivo e um cy que mantenha a cara completa com espaço acima (olhos na zona superior, nunca cortados pelo topo).
- banner_suitable=false se o motivo é alto/vertical (ex.: pessoa de corpo inteiro em primeiro plano) ou se qualquer cara principal ficaria cortada no recorte largo. Uma foto vertical pode continuar cover_suitable=true.
- embedded_text=true para cartazes, capas de jornal, memes, capturas de ecrã ou marcas de água visíveis.
- relevant=false para fotos genéricas que não se ligam à notícia (ex.: candeeiro para notícia de guitarras; logótipo; imagem aleatória). Retratos da pessoa notícia, do lugar, do edifício ou da atividade em causa são relevant=true."""


def _prompt(news_title=""):
    return _PROMPT_BASE.format(news_title=(news_title or "").strip()[:160])


def _load_env():
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    return _load_env().get("GEMINI_API_KEY", "").strip()


def _active_models():
    env = _load_env()
    configured = (os.environ.get("GEMINI_VISION_MODEL") or env.get("GEMINI_VISION_MODEL") or "").strip()
    models = list(DEFAULT_MODELS)
    if configured:
        models = [configured] + [m for m in models if m != configured]
    return models


def _load_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache):
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _prepare_inline_data(source):
    image = Image.open(source)
    image = ImageOps_exif_transpose(image)
    if max(image.size) > ANALYSIS_MAX_EDGE:
        scale = ANALYSIS_MAX_EDGE / max(image.size)
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=ANALYSIS_JPEG_QUALITY)
    raw = buffer.getvalue()
    return {
        "inline_data": {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(raw).decode("ascii"),
        }
    }, hashlib.sha1(raw).hexdigest()


def ImageOps_exif_transpose(image):
    try:
        from PIL import ImageOps

        return ImageOps.exif_transpose(image) or image
    except Exception:
        return image


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return [x, y]


def normalize_analysis(raw):
    if not isinstance(raw, dict):
        return None
    banner_focus = _normalize_point(raw.get("banner_focus"))
    cover_focus = _normalize_point(raw.get("cover_focus"))
    if not banner_focus or not cover_focus:
        return None
    return {
        "subject": str(raw.get("subject") or "")[:120],
        "embedded_text": bool(raw.get("embedded_text")),
        "faces": [
            _normalize_point(face[:2])
            for face in (raw.get("faces") or [])[:4]
            if isinstance(face, (list, tuple)) and len(face) >= 2
        ] if isinstance(raw.get("faces"), list) else [],
        "banner_focus": banner_focus,
        "cover_focus": cover_focus,
        "banner_suitable": bool(raw.get("banner_suitable")),
        "cover_suitable": bool(raw.get("cover_suitable")),
        # Análises em cache anteriores ao campo não têm veredicto de
        # relevância: assume-se relevante para não invalidar a cache.
        "relevant": bool(raw.get("relevant", True)),
        "reason": str(raw.get("reason") or "")[:200],
    }


def _call_model(model, key, inline, prompt_text):
    payload = {
        "contents": [
            {"role": "user", "parts": [inline, {"text": prompt_text}]},
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 3072,
            "responseMimeType": "application/json",
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        data = json.load(response)
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("sem candidatos na resposta")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(part.get("text") or "") for part in parts)
    if not text.strip():
        raise ValueError("resposta vazia")
    return text


class GeminiUnavailableError(Exception):
    """A API não respondeu (quota/rede/serviço) — não é um veredicto sobre a foto."""


# Estado de quota por modelo: cada modelo da free tier tem o seu próprio
# limite diário, pelo que esgotar um não impede usar os restantes.
_MODEL_DAILY_EXHAUSTED = set()
_MODEL_UNAVAILABLE = set()


def exhausted_models():
    return sorted(_MODEL_DAILY_EXHAUSTED)


def _quota_failure_info(exc):
    """Extrai a causa de um 429 da resposta da API.

    Devolve (por_minuto, por_dia, retry_delay_segundos). O corpo do erro
    traz violations com quotaId — "GenerateRequestsPerMinute..." indica
    limite por minuto (vale a pena esperar), "GenerateRequestsPerDay..."
    indica quota diária (não há nada a esperar que compense).
    """
    per_minute = per_day = False
    retry_delay = 0.0
    try:
        body = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
    except Exception:
        body = ""
    try:
        details = (json.loads(body).get("error") or {}).get("details") or []
    except Exception:
        details = []
    for detail in details:
        violations = detail.get("violations") or []
        for violation in violations:
            quota_id = str(violation.get("quotaId") or "")
            if "PerMinute" in quota_id:
                per_minute = True
            elif "PerDay" in quota_id:
                per_day = True
        if not per_minute and not per_day:
            quota_metric = str(detail.get("quotaMetric") or "")
            if "PerMinute" in quota_metric:
                per_minute = True
            elif "PerDay" in quota_metric:
                per_day = True
        delay = str(detail.get("retryDelay") or "")
        match = re.match(r"^(\d+(?:\.\d+)?)s$", delay)
        if match:
            retry_delay = max(retry_delay, float(match.group(1)))
    return per_minute, per_day, retry_delay


def _throttle():
    global _last_call_monotonic
    now = time.monotonic()
    wait = MIN_CALL_INTERVAL - (now - _last_call_monotonic)
    if wait > 0:
        time.sleep(wait)
    _last_call_monotonic = time.monotonic()


def analyze_photo(source, use_cache=True, verbose=True, news_title=""):
    """Analisa uma foto e devolve o dicionário de enquadramentos (ou None).

    Lança GeminiUnavailableError quando nenhum modelo tem quota disponível;
    erros de leitura do ficheiro devolvem None. Quem chama decide o fallback.
    news_title dá contexto à avaliação de relevância da foto para a notícia.
    """
    if not source or not Path(source).exists():
        return None
    key = api_key()
    if not key:
        return None

    cache = _load_cache() if use_cache else {}
    cache_key = f"{Path(source).name}:{Path(source).stat().st_size}"
    cached = cache.get(cache_key)
    if use_cache and isinstance(cached, dict) and cached.get("_final"):
        return cached.get("_final")

    try:
        inline, _ = _prepare_inline_data(source)
    except Exception as exc:
        if verbose:
            print(f"[gemini] nao foi possivel ler {Path(source).name}: {exc}")
        return None

    available = [model for model in _active_models() if model not in _MODEL_DAILY_EXHAUSTED and model not in _MODEL_UNAVAILABLE]
    for attempt, model in enumerate(available):
        minute_waits = 0
        for retry in range(3):
            try:
                _throttle()
                text = _call_model(model, key, inline, _prompt(news_title))
                analysis = normalize_analysis(_extract_json(text))
                if not analysis:
                    raise ValueError("JSON de analise invalido")
                if use_cache:
                    cache[cache_key] = {"_final": analysis, "_model": model}
                    _save_cache(cache)
                if verbose:
                    print(
                        f"[gemini] {Path(source).name} [{model}]: banner={'ok' if analysis['banner_suitable'] else 'nao'} "
                        f"({analysis['banner_focus']}) capa={'ok' if analysis['cover_suitable'] else 'nao'} "
                        f"texto={'sim' if analysis['embedded_text'] else 'nao'} - {analysis['reason']}"
                    )
                return analysis
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    per_minute, per_day, retry_delay = _quota_failure_info(exc)
                    if per_minute and not per_day and minute_waits < 2:
                        minute_waits += 1
                        wait = min(max(retry_delay, 15.0), 75.0)
                        if verbose:
                            print(f"[gemini] {model}: limite por MINUTO; a aguardar {wait:.0f}s (retry {minute_waits}/2)")
                        time.sleep(wait)
                        continue
                    # Quota diária é por modelo: esgota este e salta para o
                    # próximo do pool, que tem o seu próprio limite.
                    _MODEL_DAILY_EXHAUSTED.add(model)
                    remaining = [m for m in available[attempt + 1:] if m not in _MODEL_DAILY_EXHAUSTED]
                    if verbose:
                        print(f"[gemini] {model}: quota DIARIA esgotada; a trocar para {remaining[0] if remaining else '(nenhum)'}")
                    break
                if exc.code == 404:
                    # Modelo indisponível para esta chave: não voltar a tentar.
                    _MODEL_UNAVAILABLE.add(model)
                    if verbose:
                        print(f"[gemini] {model}: indisponivel para esta chave (404); a trocar de modelo")
                    break
                if verbose:
                    print(f"[gemini] {model} falhou (HTTP {exc.code}); tentativa {attempt + 1}.{retry + 1}")
                time.sleep(3)
            except (urllib.error.URLError, ValueError, OSError) as exc:
                if verbose:
                    print(f"[gemini] {model} falhou ({exc}); tentativa {attempt + 1}.{retry + 1}")
                time.sleep(3)
    raise GeminiUnavailableError(
        "nenhum modelo Gemini disponivel (quota diaria esgotada em todos ou sem rede)"
    )
