"""Remove posts antigos cuja notícia selecionada não tem âncora wayback.

Mantém apenas conteúdo com origem preservada verificável (arquivo-first).
Cria sempre um backup antes de alterar pending_posts.json.

Uso: python limpar_posts_antigos.py [--aplicar]
Sem --aplicar apenas mostra o que seria removido.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "pending_posts.json"


def main():
    aplicar = "--aplicar" in sys.argv
    backup = ROOT / f"pending_posts_backup_{datetime.now():%Y-%m-%d_%H%M}.json"
    shutil.copyfile(PENDING, backup)
    posts = json.loads(PENDING.read_text(encoding="utf-8"))

    manter, remover = [], []
    for post in posts:
        options = post.get("options") or []
        try:
            index = int(post.get("selected_option", 0) or 0)
        except (TypeError, ValueError):
            index = 0
        option = options[index] if 0 <= index < len(options) else {}
        anchored = "/wayback/" in str(option.get("article_url") or "")
        (manter if anchored else remover).append(post)

    print(f"Backup: {backup.name}")
    print(f"Mantidos: {len(manter)} | A remover: {len(remover)}")
    for post in remover:
        options = post.get("options") or []
        try:
            index = int(post.get("selected_option", 0) or 0)
        except (TypeError, ValueError):
            index = 0
        title = (options[index] if 0 <= index < len(options) else {}).get("title", "?")
        print(f"  - {post.get('id')}: {str(title)[:60]}")

    if aplicar and remover:
        PENDING.write_text(json.dumps(manter, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nAplicado: {len(posts)} -> {len(manter)} posts.")
    elif aplicar:
        print("\nNada a remover.")
    else:
        print("\n(simulação — correr com --aplicar para remover)")


if __name__ == "__main__":
    main()
