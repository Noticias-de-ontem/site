"""Recolhe os snapshots das páginas preservadas no Arquivo.pt.

Usa a API de screenshots (https://arquivo.pt/screenshot?url=<wayback>) para
guardar uma imagem local por notícia em site/assets/snapshots/<page_id>.jpg.
Os builds futuros do site preferem o ficheiro local ao pedido on-the-fly.
"""

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
NEWS_FILE = SITE_DIR / "data" / "news.json"
SNAPSHOTS_DIR = SITE_DIR / "assets" / "snapshots"


def load_news_items():
    if not NEWS_FILE.exists():
        return []
    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    return payload.get("all") or []


def collect(limit=None):
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    items = load_news_items()
    targets = [
        item for item in items
        if item.get("source_url")
        and "arquivo.pt/wayback/" in item["source_url"]
        and item.get("page_id")
    ]
    if limit:
        targets = targets[: int(limit)]
    downloaded = skipped = failed = 0
    for index, item in enumerate(targets, 1):
        target = SNAPSHOTS_DIR / f"{item['page_id']}.jpg"
        if target.exists() and target.stat().st_size > 1024:
            skipped += 1
            continue
        replay_url = item["source_url"].replace("/wayback/", "/noFrame/replay/")
        url = f"https://arquivo.pt/screenshot/?url={requests.utils.quote(replay_url, safe='')}"
        try:
            response = requests.get(url, timeout=180, headers={"User-Agent": "NoticiasDeOntem/1.0"})
            if response.ok and response.headers.get("content-type", "").startswith(("image/", "application/octet-stream")) and len(response.content) > 1024:
                target.write_bytes(response.content)
                downloaded += 1
                print(f"[{index}/{len(targets)}] ok: {item['page_id']} ({len(response.content) // 1024} KB)")
            else:
                failed += 1
                print(f"[{index}/{len(targets)}] falhou ({response.status_code}, {len(response.content)} B): {item['page_id']}")
        except Exception as exc:
            failed += 1
            print(f"[{index}/{len(targets)}] erro: {item['page_id']}: {exc}")
        time.sleep(1)
    print(f"Concluído: {downloaded} descarregados, {skipped} já existiam, {failed} falhados.")


def is_valid_snapshot_bytes(data: bytes) -> bool:
    """Valida se os bytes recebidos são um screenshot genuíno do Arquivo.pt.

    Rejeita:
    - Imagens com aspect ratio de capa Instagram (≈ 4:5, largura > 900 px)
    - Imagens demasiado pequenas (largura < 500 px)
    - Imagens com cores muito saturadas/escuras (páginas de erro coloridas)
    - Imagens quadradas ou landscape (não são screenshots de página web)
    Aceita screenshots portrait de página web (height > 1.5 × width, pale).
    """
    try:
        import io
        from PIL import Image
        import colorsys

        img = Image.open(io.BytesIO(data))
        w, h = img.size

        # Demasiado pequena
        if w < 500 or h < 500:
            return False

        # Landscape ou quase-quadrada
        if h < w * 1.2:
            return False

        # Aspect ratio de capa Instagram (4:5) — rejeitar
        ratio = h / w
        if ratio < 1.4 and w > 900:
            return False

        # Verificar cor dominante — rejeitar imagens muito saturadas (erros)
        thumb = img.convert("RGB").resize((50, 50))
        pixels = list(thumb.getdata())
        avg_r = sum(p[0] for p in pixels) / len(pixels)
        avg_g = sum(p[1] for p in pixels) / len(pixels)
        avg_b = sum(p[2] for p in pixels) / len(pixels)
        h_hls, l_hls, s_hls = colorsys.rgb_to_hls(avg_r / 255, avg_g / 255, avg_b / 255)
        # Rejeitar se saturação alta (>0.3) — páginas de erro coloridas
        if s_hls > 0.3:
            return False

        return True
    except Exception:
        return False


if __name__ == "__main__":
    import sys

    collect(sys.argv[1] if len(sys.argv) > 1 else None)
