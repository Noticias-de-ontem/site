import argparse
import os
import sys
import json
import requests

sys.path.insert(0, os.getcwd())
from archive_storage import all_block_ids, block_path, load_block, save_block

LOCAL_LLM = None

def prune_events_for_block(lang, block_id, model_name=None):
    model = model_name or LOCAL_LLM
    if not model:
        print("[Aviso] Modelo local/Ollama não configurado. Impossível podar eventos.")
        return
        
    path = block_path(lang, block_id)
    if not os.path.exists(path):
        return
        
    posts = load_block(lang, block_id)
    wiki_posts = [p for p in posts if p.get("source_platform") == "wikipedia"]
    other_posts = [p for p in posts if p.get("source_platform") != "wikipedia"]
    
    if not wiki_posts:
        return
        
    print(f"\n--- A analisar bloco {block_id} [{lang}] ({len(wiki_posts)} efemérides Wikipedia) ---")
    
    from collections import defaultdict
    grouped = defaultdict(list)
    for p in wiki_posts:
        date_str = p.get("date", "")[:10]
        if len(date_str) == 10:
            mm_dd = date_str[5:10]
            grouped[mm_dd].append(p)
            
    kept_wiki_posts = []
    has_changes = False
    
    for mm_dd, day_posts in grouped.items():
        if len(day_posts) <= 8:
            kept_wiki_posts.extend(day_posts)
            continue
            
        print(f"  Dia {mm_dd}: {len(day_posts)} eventos encontrados. A filtrar com Ollama ({model})...")
        
        simplified = []
        for idx, p in enumerate(day_posts):
            simplified.append({
                "idx": idx,
                "year": p.get("options", [{}])[0].get("year", ""),
                "text": p.get("global_context", "")
            })
            
        prompt = f"""You are a historical editor for a news archive.
Analyze the list of historical events below for the day {mm_dd} (Language: {lang.upper()}).

Filter out minor, niche, or local regional events (e.g. minor municipal elections in small countries, opening of local roads, minor births/deaths, local utility announcements).
Keep only events of:
- Major national historical importance for Portugal/Brazil (in PT version) or global significance.
- Large scientific, space, cultural milestones, wars, treaties, or famous historical turning points.

Raw events list:
{json.dumps(simplified, ensure_ascii=False)}

Return a JSON object with exactly one key "keep_indexes" containing a list of integers representing the indexes of the events to KEEP.
Do not explain anything, return only the JSON.
"""
        
        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a cataloging assistant. Return only valid JSON object."},
                        {"role": "user", "content": prompt}
                    ],
                    "format": "json",
                    "options": {"temperature": 0.3},
                    "stream": False
                },
                timeout=60
            )
            if response.status_code == 200:
                res_data = response.json()
                response_text = res_data.get("message", {}).get("content", "{}")
                payload = json.loads(response_text)
                keep_indexes = payload.get("keep_indexes", [])
                
                day_kept = [day_posts[i] for i in keep_indexes if 0 <= i < len(day_posts)]
                print(f"  -> Mantidos {len(day_kept)} de {len(day_posts)} eventos.")
                kept_wiki_posts.extend(day_kept)
                if len(day_kept) < len(day_posts):
                    has_changes = True
            else:
                raise RuntimeError(f"Ollama respondeu com HTTP {response.status_code}")
        except Exception as e:
            print(f"  [Erro] Falha ao filtrar dia {mm_dd}: {e}. A manter todos por segurança.")
            kept_wiki_posts.extend(day_posts)
            
    if has_changes:
        new_posts = other_posts + kept_wiki_posts
        save_block(lang, block_id, new_posts)
        print(f"  [OK] Bloco {block_id} [{lang}] limpo e atualizado.")

def main():
    parser = argparse.ArgumentParser(description="Limpa efemérides irrelevantes ou menores da Wikipedia dos blocos usando Ollama.")
    parser.add_argument("--lang", choices=["pt", "en"], help="Processa apenas este idioma.")
    parser.add_argument("--block", help="ID de bloco específico (01 a 61).")
    parser.add_argument("--local-llm", type=str, default="gemma2:2b", help="Modelo local do Ollama a usar (padrão: gemma2:2b).")
    args = parser.parse_args()
    
    langs = [args.lang] if args.lang else ["pt", "en"]
    blocks = [args.block] if args.block else all_block_ids()
    
    for lang in langs:
        for block_id in blocks:
            prune_events_for_block(lang, block_id, model_name=args.local_llm)

if __name__ == "__main__":
    main()
