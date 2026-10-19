import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

KEEP_IDS = [
    "pt_2026-01-01_1", "pt_2026-01-02_1", "pt_2026-01-04_2", "pt_2026-01-05_1",
    "pt_2026-01-06_2", "pt_2026-01-07_1", "pt_2026-01-08_1", "pt_2026-01-08_2",
    "pt_2026-01-10_1", "pt_2026-01-13_1", "pt_2026-01-18_1", "pt_2026-01-20_2",
    "pt_2026-01-21_2", "pt_2026-01-24_1", "pt_2026-01-25_2", "pt_2026-01-27_2",
    "pt_2026-01-30_1", "pt_2026-02-01_1", "pt_2026-02-02_1", "pt_2026-02-03_1",
    "pt_2026-02-04_1", "pt_2026-02-06_1", "pt_2026-02-07_1", "pt_2026-02-07_2",
    "pt_2026-02-11_1", "pt_2026-02-11_2",
]

CATEGORY_CORRECTIONS = {
    "pt_2026-01-05_1": "CULTURA",
    "pt_2026-01-07_1": "DESPORTO",
    "pt_2026-01-25_2": "TECNOLOGIA",
    "pt_2026-02-06_1": "CULTURA",
    "pt_2026-02-07_1": "SOCIEDADE",
    "pt_2026-02-07_2": "CIÊNCIA",
}

with open("pending_posts.json", "r", encoding="utf-8") as f:
    posts = json.load(f)

print(f"Total posts antes: {len(posts)}")

keep_set = set(KEEP_IDS)
filtered = [p for p in posts if p.get("id") in keep_set]

print(f"Posts filtrados: {len(filtered)}")

for post in filtered:
    post["status"] = "approved"
    pid = post.get("id", "")
    if pid in CATEGORY_CORRECTIONS:
        sel = post.get("selected_option", 0)
        options = post.get("options", [])
        if sel < len(options):
            old_cat = options[sel].get("category", "?")
            options[sel]["category"] = CATEGORY_CORRECTIONS[pid]
            print(f"  Corrigido {pid}: {old_cat} -> {CATEGORY_CORRECTIONS[pid]}")

# Verify count
assert len(filtered) == 26, f"Expected 26 posts, got {len(filtered)}"

with open("pending_posts.json", "w", encoding="utf-8") as f:
    json.dump(filtered, f, ensure_ascii=False, indent=2)

print(f"\nGuardados {len(filtered)} posts em pending_posts.json")
print("\nIDs mantidos:")
for p in filtered:
    sel = p.get("selected_option", 0)
    opts = p.get("options", [])
    cat = opts[sel].get("category", "?") if sel < len(opts) else "?"
    title = opts[sel].get("title", "?") if sel < len(opts) else "?"
    print(f"  {p['id']} | {cat} | {title}")
