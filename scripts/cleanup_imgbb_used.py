import argparse
import json
import os
from datetime import datetime, timezone

from imgbb_registry import (
    IMGBB_UPLOADS_FILE,
    delete_imgbb_image,
    load_imgbb_registry,
    save_imgbb_registry,
)


PENDING_POSTS_FILE = "pending_posts.json"


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def is_imgbb_url(url):
    value = str(url or "").lower()
    return "ibb.co/" in value or "i.ibb.co/" in value


def add_target(targets, delete_url, image_url="", source="", post_id="", option_index=None, registry_index=None):
    delete_url = str(delete_url or "").strip()
    if not delete_url:
        return
    if delete_url in targets:
        return
    targets[delete_url] = {
        "delete_url": delete_url,
        "image_url": image_url,
        "source": source,
        "post_id": post_id,
        "option_index": option_index,
        "registry_index": registry_index,
    }


def collect_targets(pending_posts, registry, include_published_options=True):
    targets = {}

    for index, record in enumerate(registry):
        if record.get("deleted_at"):
            continue
        if record.get("kind") == "published_post":
            add_target(
                targets,
                record.get("delete_url", ""),
                image_url=record.get("image_url", ""),
                source="published_post_registry",
                post_id=record.get("post_id", ""),
                registry_index=index,
            )

    for post in pending_posts:
        if str(post.get("status", "")).strip().lower() != "published":
            continue
        options = post.get("options") or []
        selected = int(post.get("selected_option", 0) or 0)
        indexes = range(len(options)) if include_published_options else [selected]

        for option_index in indexes:
            if option_index < 0 or option_index >= len(options):
                continue
            option = options[option_index]
            if not isinstance(option, dict):
                continue
            image_url = option.get("image_url", "")
            delete_url = option.get("image_delete_url", "")
            if delete_url and is_imgbb_url(image_url):
                add_target(
                    targets,
                    delete_url,
                    image_url=image_url,
                    source="published_review_option",
                    post_id=post.get("id", ""),
                    option_index=option_index,
                )

    return list(targets.values())


def mark_pending_option_deleted(pending_posts, target, deleted_at):
    post_id = target.get("post_id", "")
    option_index = target.get("option_index")
    if option_index is None:
        return False

    for post in pending_posts:
        if post.get("id") != post_id:
            continue
        options = post.get("options") or []
        if option_index < 0 or option_index >= len(options):
            return False
        option = options[option_index]
        if not isinstance(option, dict):
            return False
        option["image_deleted_at"] = deleted_at
        option["image_delete_url"] = ""
        local_path = option.get("local_image_path", "")
        if local_path:
            option["image_url"] = local_path
        return True
    return False


def mark_registry_deleted(registry, target, deleted_at, status):
    changed = False
    for record in registry:
        if record.get("delete_url") == target.get("delete_url"):
            record["deleted_at"] = deleted_at
            record["delete_status"] = status
            changed = True
    return changed


def main():
    parser = argparse.ArgumentParser(description="Apaga do ImgBB imagens que ja pertencem a posts publicados.")
    parser.add_argument("--apply", action="store_true", help="Apaga mesmo. Sem isto, faz apenas dry-run.")
    parser.add_argument(
        "--selected-only",
        action="store_true",
        help="Em posts publicados, apaga apenas a opcao selecionada. Por defeito apaga todas as previews desse post publicado.",
    )
    args = parser.parse_args()

    pending_posts = load_json(PENDING_POSTS_FILE, [])
    registry = load_imgbb_registry(IMGBB_UPLOADS_FILE)
    targets = collect_targets(
        pending_posts,
        registry,
        include_published_options=not args.selected_only,
    )

    print(f"Encontradas {len(targets)} imagem(ns) ImgBB elegiveis para limpeza.")
    if not args.apply:
        for target in targets:
            print(f"[dry-run] {target['source']} {target.get('post_id', '')}: {target.get('image_url', '')}")
        return

    deleted = 0
    failed = 0
    pending_changed = False
    registry_changed = False

    for target in targets:
        ok, status = delete_imgbb_image(target["delete_url"])
        if ok:
            deleted += 1
            deleted_at = utc_now_iso()
            pending_changed = mark_pending_option_deleted(pending_posts, target, deleted_at) or pending_changed
            registry_changed = mark_registry_deleted(registry, target, deleted_at, status) or registry_changed
            print(f"[ok] {target['source']} {target.get('post_id', '')}: {target.get('image_url', '')}")
        else:
            failed += 1
            print(f"[falhou] {target['source']} {target.get('post_id', '')}: {status}")

    if pending_changed:
        save_json(PENDING_POSTS_FILE, pending_posts)
    if registry_changed:
        save_imgbb_registry(registry, IMGBB_UPLOADS_FILE)

    print(f"Limpeza concluida. Apagadas: {deleted}. Falharam: {failed}.")


if __name__ == "__main__":
    main()
