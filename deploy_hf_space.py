"""Publish the generated static site to a Hugging Face Space."""

import argparse
import os
from pathlib import Path

from huggingface_hub import HfApi


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(
        description="Envia a pasta site/ para um Hugging Face Static Space."
    )
    parser.add_argument(
        "--space-id",
        default=os.environ.get("HF_SPACE_ID", "").strip(),
        help="Space no formato utilizador/nome (ou HF_SPACE_ID).",
    )
    parser.add_argument(
        "--site-dir",
        default=str(ROOT / "site"),
        help="Pasta estática a publicar (por defeito: site/).",
    )
    parser.add_argument(
        "--commit-message",
        default="Deploy static website",
        help="Mensagem do commit no Hugging Face.",
    )
    args = parser.parse_args()

    if not args.space_id or "/" not in args.space_id:
        raise SystemExit("Indica --space-id utilizador/nome ou define HF_SPACE_ID.")
    site_dir = Path(args.site_dir).resolve()
    if not (site_dir / "index.html").is_file():
        raise SystemExit(f"A pasta do site não contém index.html: {site_dir}")

    token = os.environ.get("HF_TOKEN", "").strip() or None
    api = HfApi(token=token)
    api.create_repo(
        repo_id=args.space_id,
        repo_type="space",
        space_sdk="static",
        exist_ok=True,
    )
    api.upload_folder(
        folder_path=str(site_dir),
        repo_id=args.space_id,
        repo_type="space",
        delete_patterns="*",
        commit_message=args.commit_message,
    )
    print(f"Space publicado: https://huggingface.co/spaces/{args.space_id}")


if __name__ == "__main__":
    main()
