import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from publisher import publish_to_facebook, normalize_text

PENDING_POSTS_FILE = ROOT / "pending_posts.json"

def main():
    dates = sys.argv[1:] if len(sys.argv) > 1 else ["2026-10-27", "2026-10-28"]
    print(f"A verificar posts para publicar no Feed do Facebook para as datas: {dates}")

    if not PENDING_POSTS_FILE.exists():
        print(f"Ficheiro {PENDING_POSTS_FILE} nao encontrado.")
        return 1

    with open(PENDING_POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)

    updated = False
    for post in posts:
        post_date = post.get("date")
        if post_date not in dates:
            continue

        sel_idx = post.get("selected_option", 0)
        options = post.get("options", [])
        if not options or sel_idx >= len(options):
            continue

        opt = options[sel_idx]
        networks = opt.get("networks", ["instagram", "facebook"])
        if "facebook" not in networks:
            continue

        caption_fb = normalize_text(opt.get("caption_facebook", "") or opt.get("caption", "") or opt.get("title", ""))
        image_url = opt.get("image_url", "")
        if not image_url or not caption_fb:
            print(f"Post {post.get('id')} sem image_url ou caption_facebook.")
            continue

        print(f"\nA publicar no Feed do Facebook: {post.get('id')} ({post_date}) - {opt.get('title')[:60]}...")
        result = publish_to_facebook(caption_fb, image_url)
        if result and isinstance(result, dict) and result.get("success"):
            post["facebook_id"] = result.get("id", "")
            post["facebook_url"] = result.get("permalink", "")
            updated = True
            print(f"-> Sucesso! Publicado no Feed: {result.get('permalink')}")
        else:
            print(f"-> Falha ao publicar {post.get('id')} no Facebook Feed.")

    if updated:
        with open(PENDING_POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=4)
        print("\nFicheiro pending_posts.json atualizado com os novos IDs de Feed!")
    else:
        print("\nNenhuma alteracao efetuada.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
