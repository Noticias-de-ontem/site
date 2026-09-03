import argparse
import os
import sys
import json
import random
import requests
from datetime import datetime


sys.path.insert(0, os.getcwd())
from archive_storage import block_id_for_month_day, load_block, save_block

LOCAL_LLM = None

def now_local():
    return datetime.now().astimezone()

def fetch_wikipedia_events(lang, month, day):
    url = f"https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/all/{month:02d}/{day:02d}"
    headers = {"User-Agent": "NewsArchiveBot/1.0 (contact: admin@example.com)"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        print(f"[{lang}] Erro ao aceder à API da Wikipedia: {response.status_code}")
    except Exception as e:
        print(f"[{lang}] Erro de ligação à Wikipedia: {e}")
    return {}

def extract_image_url(event):
    for page in event.get("pages", []):
        orig = page.get("originalimage")
        if orig and orig.get("source"):
            return orig["source"]
        thumb = page.get("thumbnail")
        if thumb and thumb.get("source"):
            return thumb["source"]
    return ""

def curate_events_with_local_llm(events, lang, month, day, model_name=None):
    model = model_name or LOCAL_LLM
    if not model:
        print("[Aviso] Modelo local/Ollama não configurado. A usar os primeiros 8 eventos sem curadoria inteligente.")
        selected = events.get("selected", []) or events.get("events", [])
        return selected[:8]

    simplified_list = []
    for ev in events.get("selected", []) + events.get("events", [])[:15]:
        simplified_list.append({
            "year": ev.get("year"),
            "text": ev.get("text"),
            "image_url": extract_image_url(ev)
        })

    prompt_pt = f"""You are a curator for a Portuguese historical news archive site called "Notícias de Ontem".
Filter and select the most relevant daily events from the list below for the date: Month {month}, Day {day}.

Rules for selection:
1. Select exactly between 5 and 10 events.
2. Prioritize:
   - Important events in Portuguese or Brazilian history (national landmarks, kings, key events).
   - Major international events of global relevance (World Wars, Space/Moon landing, giant scientific discoveries, major global treaties).
3. Reject minor/niche foreign events (e.g. local political events in the US, minor sports matches).
4. If the text is in English, translate it to clear, professional Portuguese (European/Standard Portuguese).
5. Preserve the year and the correct image_url if provided.

Raw events list:
{json.dumps(simplified_list, ensure_ascii=False, indent=2)}

Return a JSON array of objects with exactly these keys:
- year: integer
- title: a short, catchy title/headline for the event (in Portuguese)
- summary: 1-2 sentence description of the event (in Portuguese)
- image_url: string (preserve from input, or empty if none)"""

    prompt_en = f"""You are a curator for an English historical news archive site.
Filter and select the most relevant daily events from the list below for the date: Month {month}, Day {day}.

Rules for selection:
1. Select exactly between 5 and 10 events.
2. Keep only the most globally significant events (Space milestones, world wars, historical turning points). Skip niche country-specific events.
3. Year and summary must be in English.
4. Preserve the year and the correct image_url if provided.

Raw events list:
{json.dumps(simplified_list, ensure_ascii=False, indent=2)}

Return a JSON array of objects with exactly these keys:
- year: integer
- title: a short, catchy title/headline for the event (in English)
- summary: 1-2 sentence description of the event (in English)
- image_url: string (preserve from input, or empty if none)"""

    prompt = prompt_pt if lang == "pt" else prompt_en

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a cataloging assistant. Return only valid JSON array."},
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
            response_text = res_data.get("message", {}).get("content", "[]")
            return json.loads(response_text)
    except Exception as e:
        print(f"[Ollama] Erro na curadoria Wikipedia com local LLM {model}: {e}")

    selected = events.get("selected", []) or events.get("events", [])
    return [{"year": ev.get("year"), "title": "Notícia Histórica", "summary": ev.get("text"), "image_url": extract_image_url(ev)} for ev in selected[:5]]

def save_wiki_events_to_block(lang, month, day, curated_events):
    block_id = block_id_for_month_day(month, day)
    from archive_storage import block_lock
    lock = block_lock(lang, block_id)
    lock.__enter__()
    try:
        posts = load_block(lang, block_id)
        
        existing_shortcodes = set()
        for p in posts:
            existing_shortcodes.update(p.get("shortcodes", []))
            
        added_count = 0
        for ev in curated_events:
            year = ev.get("year")
            if not year:
                continue
                
            shortcode = f"wiki-{month:02d}{day:02d}-{year}"
            if shortcode in existing_shortcodes:

                continue
                

            post_record = {
                "shortcodes": [shortcode],
                "date": f"{year:04d}-{month:02d}-{day:02d} 12:00:00",
                "global_context": ev.get("summary") or ev.get("title", ""),
                "raw_caption": ev.get("summary") or ev.get("title", ""),
                "image_url": ev.get("image_url") or "",
                "source_platform": "wikipedia",
                "source_profile": "wikipedia",
                "source_url": f"https://{lang}.wikipedia.org/wiki/{month:02d}_{day:02d}",
                "media_type": "image",
                "media_count": 1,
                "is_video": False,
                "video_url": "",
                "slide_urls": [ev.get("image_url") or ""],
                "slide_video_urls": [""],
                "content_flags": ["historical_event"],
                "content_mode": "single_story",
                "needs_enrichment": False,
                "enrichment_status": "done",
                "enriched_at": now_local().isoformat(),
                "ai_summary": ev.get("summary", ""),
                "topic_keywords": ["historia", "wikipedia", "efemeride"],
                "virality_signals": [],
                "carousel_items": [],
                "should_skip": False,
                "options": [
                    {
                        "year": str(year),
                        "category": "HISTÓRIA" if lang == "pt" else "HISTORY",
                        "title": ev.get("title", "Notícia Histórica"),
                        "summary": ev.get("summary", ""),
                        "highlight_text": str(year),
                        "overlay_description": ev.get("title", ""),
                        "image_theme": ev.get("title", ""),
                        "caption": f"Neste dia em {year}: {ev.get('summary')}" if lang == "pt" else f"On this day in {year}: {ev.get('summary')}",
                        "layout_preference": "template_2",
                        "breaking_candidate": False,
                        "background_source_url": ev.get("image_url") or "",
                        "image_url": ev.get("image_url") or ""
                    }
                ],
                "selected_option": 0,
                "status": "pending"
            }
            posts.append(post_record)
            existing_shortcodes.add(shortcode)
            added_count += 1
            
        if added_count > 0:
            save_block(lang, block_id, posts)
            print(f"[{lang}][bloco {block_id}] Adicionados {added_count} eventos históricos da Wikipedia para o dia {month:02d}-{day:02d}.")
        else:
            print(f"[{lang}][bloco {block_id}] Nenhum evento novo adicionado (todos já existem ou nenhum foi encontrado).")
    finally:
        lock.__exit__(None, None, None)

def process_day(month, day, lang=None, curate=False, local_llm=None):
    langs = [lang] if lang else ["pt", "en"]
    for l in langs:
        print(f"\n--- A processar Wikipedia [{l}] para o dia {month:02d}-{day:02d} (Curadoria AI: {'Sim' if (curate or local_llm) else 'Não'}) ---")
        raw_events = fetch_wikipedia_events(l, month, day)
        if not raw_events:
            continue
            
        if curate or local_llm:
            model = local_llm if isinstance(local_llm, str) else "gemma2:2b"
            curated = curate_events_with_local_llm(raw_events, l, month, day, model_name=model)
        else:
            all_raw = raw_events.get("selected", []) + raw_events.get("events", [])
            curated = []
            for ev in all_raw:
                year = ev.get("year")
                if not year:
                    continue
                text = ev.get("text", "")
                title = "Notícia Histórica" if l == "pt" else "Historical Event"
                words = text.split()
                if words:
                    title = " ".join(words[:6])
                    if not title.endswith(".") and len(words) > 6:
                        title += "..."
                curated.append({
                    "year": year,
                    "title": title,
                    "summary": text,
                    "image_url": extract_image_url(ev)
                })
                
        save_wiki_events_to_block(l, month, day, curated)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recolhe eventos históricos da Wikipedia e guarda no arquivo.")
    parser.add_argument("--month", type=int, help="Mês (1 a 12). Padrão: mês atual.")
    parser.add_argument("--day", type=int, help="Dia (1 a 31). Padrão: dia atual.")
    parser.add_argument("--lang", choices=["pt", "en"], help="Processa apenas este idioma. Padrão: processa ambos (pt e en).")
    parser.add_argument("--curate", action="store_true", help="Usa um modelo local do Ollama (gemma2:2b) para curar e traduzir os eventos.")
    parser.add_argument("--local-llm", type=str, help="Especifica um modelo local do Ollama para curar os eventos (ex: llama3).")
    args = parser.parse_args()
    
    today = datetime.now()
    month = args.month if args.month is not None else today.month
    day = args.day if args.day is not None else today.day
    
    process_day(month, day, args.lang, args.curate, args.local_llm)

