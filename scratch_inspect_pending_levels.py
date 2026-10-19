import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

posts = json.load(open("pending_posts.json", encoding="utf-8"))
print(f"Total posts: {len(posts)}")

by_level = {}
for p in posts:
    opt_idx = int(p.get("selected_option", 0) or 0)
    opt = p["options"][opt_idx]
    rel = opt.get("relevance", {})
    lvl = rel.get("level")
    by_level.setdefault(lvl, []).append((p["id"], opt.get("title"), opt.get("category"), opt.get("original_year")))

for lvl in sorted(by_level.keys(), key=lambda x: (x is None, x)):
    items = by_level[lvl]
    print(f"\n=== LEVEL {lvl} ({len(items)} items) ===")
    for pid, title, cat, yr in items:
        print(f"  {pid} ({yr}) [{cat}] - {title}")
