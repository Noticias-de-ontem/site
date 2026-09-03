import argparse
import json
import os
from collections import Counter
from datetime import datetime

from archive_storage import LANG_DIRS


STATE_FILE = "enrich_saved_posts_state.json"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def shortcode(post):
    values = post.get("shortcodes") or []
    return values[0] if values else ""


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def scan_lang(lang):
    lang_dir = LANG_DIRS.get(lang)
    result = {
        "lang": lang,
        "total": 0,
        "statuses": Counter(),
        "carousel_items": 0,
        "latest_update": None,
        "latest_update_post": None,
    }
    if not lang_dir or not os.path.exists(lang_dir):
        return result

    for fname in sorted(os.listdir(lang_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(lang_dir, fname)
        posts = load_json(path, [])
        for index, post in enumerate(posts):
            result["total"] += 1
            status = post.get("enrichment_status") or "untouched"
            result["statuses"][status] += 1
            if post.get("carousel_items"):
                result["carousel_items"] += 1
            updated_at = parse_dt(post.get("enriched_at"))
            if updated_at and (result["latest_update"] is None or updated_at > result["latest_update"]):
                result["latest_update"] = updated_at
                result["latest_update_post"] = {
                    "file": path,
                    "index": index,
                    "date": post.get("date", ""),
                    "shortcode": shortcode(post),
                    "status": status,
                }
    return result


def state_post(state):
    file_path = state.get("file_path")
    index = int(state.get("post_index") or 0)
    if not file_path or not os.path.exists(file_path):
        return None
    posts = load_json(file_path, [])
    if 0 <= index < len(posts):
        post = posts[index]
        return {
            "date": post.get("date", ""),
            "shortcode": shortcode(post),
            "status": post.get("enrichment_status") or "untouched",
        }
    return None


def main():
    parser = argparse.ArgumentParser(description="Show enrichment progress and resume point.")
    parser.add_argument("--lang", choices=sorted(LANG_DIRS.keys()), help="Language to scan.")
    args = parser.parse_args()

    state = load_json(STATE_FILE, {})
    print("=== ENRICHMENT STATUS ===")
    if os.path.exists("enrich_saved_posts.stop"):
        print("Stop file: present")
    else:
        print("Stop file: absent")

    if state:
        print(f"State: {state.get('status', '')}")
        print(f"Resume file: {state.get('file_path', '')}")
        print(f"Resume post_index: {state.get('post_index', '')}")
        post = state_post(state)
        if post:
            print(f"Resume post: {post['date']} {post['shortcode']} ({post['status']})")
        if state.get("updated_at"):
            print(f"State updated_at: {state['updated_at']}")
    else:
        print("State: none")

    langs = [args.lang] if args.lang else sorted(LANG_DIRS.keys())
    for lang in langs:
        result = scan_lang(lang)
        print("")
        print(f"[{lang}] total posts: {result['total']}")
        for status, count in sorted(result["statuses"].items()):
            print(f"[{lang}] {status}: {count}")
        print(f"[{lang}] carousel_items saved: {result['carousel_items']}")
        if result["latest_update_post"]:
            post = result["latest_update_post"]
            print(
                f"[{lang}] last updated: {post['date']} {post['shortcode']} "
                f"({post['status']}) in {post['file']} at index {post['index']}"
            )
        else:
            print(f"[{lang}] last updated: none")


if __name__ == "__main__":
    main()
