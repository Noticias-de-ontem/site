"""Recolhe os snapshots das páginas preservadas no Arquivo.pt.

Usa a API de screenshots (https://arquivo.pt/screenshot?url=<wayback>) para
guardar uma imagem local por notícia em site/assets/snapshots/<page_id>.jpg.
Os builds futuros do site preferem o ficheiro local ao pedido on-the-fly.
"""

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
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
        url = f"https://arquivo.pt/screenshot?url={requests.utils.quote(item['source_url'], safe='')}"
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


if __name__ == "__main__":
    import sys

    collect(sys.argv[1] if len(sys.argv) > 1 else None)
