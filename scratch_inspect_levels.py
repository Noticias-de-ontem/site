import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("site/data/news.json", encoding="utf-8"))
all_items = data.get("all", [])
lvl_1_2 = [it for it in all_items if it.get("relevance_level") in [1, 2]]
print("Count of Level 1 & 2:", len(lvl_1_2))
for i, it in enumerate(lvl_1_2, 1):
    print(f"{i}. [{it.get('id')}] ({it.get('original_year')}) Nivel {it.get('relevance_level')} | {it.get('category')} | {it.get('title')}")

print("\n--- Level 3 items ---")
lvl_3 = [it for it in all_items if it.get("relevance_level") == 3]
print("Count of Level 3:", len(lvl_3))
for i, it in enumerate(lvl_3, 1):
    print(f"{i}. [{it.get('id')}] ({it.get('original_year')}) Nivel {it.get('relevance_level')} | {it.get('category')} | {it.get('title')}")
