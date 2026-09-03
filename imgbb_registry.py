import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


IMGBB_UPLOADS_FILE = "imgbb_uploads.json"


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_imgbb_registry(filepath=IMGBB_UPLOADS_FILE):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_imgbb_registry(records, filepath=IMGBB_UPLOADS_FILE):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)


def register_imgbb_upload(record, filepath=IMGBB_UPLOADS_FILE):
    image_url = str(record.get("image_url") or "").strip()
    delete_url = str(record.get("delete_url") or "").strip()
    if not image_url and not delete_url:
        return

    records = load_imgbb_registry(filepath)
    record_key = delete_url or image_url
    existing = next(
        (
            item for item in records
            if (item.get("delete_url") or item.get("image_url")) == record_key
        ),
        None,
    )

    payload = {
        **record,
        "image_url": image_url,
        "delete_url": delete_url,
        "created_at": record.get("created_at") or utc_now_iso(),
        "deleted_at": record.get("deleted_at") or "",
        "delete_status": record.get("delete_status") or "",
    }

    if existing is not None:
        existing.update(payload)
    else:
        records.append(payload)
    save_imgbb_registry(records, filepath)


def parse_imgbb_delete_url(delete_url):
    parsed = urlparse(str(delete_url or "").strip())
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc not in {"ibb.co", "www.ibb.co"} or len(parts) < 2:
        return "", ""
    return parts[0], parts[1]


def delete_imgbb_image(delete_url, timeout=20):
    image_id, image_hash = parse_imgbb_delete_url(delete_url)
    if not image_id or not image_hash:
        return False, "invalid_delete_url"

    data = {
        "pathname": f"/{image_id}/{image_hash}",
        "action": "delete",
        "delete": "image",
        "from": "resource",
        "deleting[id]": image_id,
        "deleting[hash]": image_hash,
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    try:
        response = requests.post("https://ibb.co/json", data=data, headers=headers, timeout=timeout)
        if response.status_code < 400:
            try:
                payload = response.json()
                if payload.get("status_code") in (200, "200") or payload.get("success") is True:
                    return True, "deleted"
            except Exception:
                pass
            if "delete" in response.text.lower() or "success" in response.text.lower():
                return True, "deleted"
        return False, f"http_{response.status_code}"
    except Exception as exc:
        return False, str(exc)
