import json
import os
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
SITE_DATA_FILE = ROOT / "site" / "data" / "news.json"


def main():
    api_url = os.environ.get("SITE_API_URL", "").strip().rstrip("/")
    token = os.environ.get("SITE_SYNC_TOKEN", "").strip()
    if not api_url or not token:
        print("SITE_API_URL ou SITE_SYNC_TOKEN nao configurado; sincronizacao ignorada.")
        return 0
    if not SITE_DATA_FILE.exists():
        print(f"Ficheiro nao encontrado: {SITE_DATA_FILE}", file=sys.stderr)
        return 1
    payload = json.loads(SITE_DATA_FILE.read_text(encoding="utf-8"))
    endpoint = f"{api_url}/api/admin/site-data"
    response = requests.post(
        endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=(15, 120),
    )
    response.raise_for_status()
    result = response.json()
    print(f"Site dinamico atualizado: {result.get('generated_at', 'sem data')}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
