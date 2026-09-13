"""Popula o site localmente: notícias, índice de eventos e backfill.

Uso comum:
  python popular_site.py --start 2026-03-01 --end 2026-03-10
  python popular_site.py --tudo-ano --source-mode local --limite 40
  python popular_site.py --jornal publico.pt --jornal dn.pt --start ... --end ...
  python popular_site.py --com-eventos            # índice Wikipedia 365 dias
  python popular_site.py --backfill-relevance     # pontuar posts antigos

Notas:
- Retomável: dias com posts existentes são sempre saltados.
- `--jornal` filtra as fontes usadas (blocos locais e pesquisa no Arquivo.pt).
- A geração usa a chave NVIDIA do .env (2-3 chamadas por dia gerado).
"""

import argparse
import calendar as calendar_module
import json
import os
import re
import sys
import time
from datetime import date as date_type
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import pregenerator  # noqa: E402
from historical_relevance import normalize_relevance  # noqa: E402
from nvidia_client import NvidiaKeyPool, load_nvidia_api_keys  # noqa: E402
from pregenerator import load_json, save_json  # noqa: E402
from wikipedia_scraper import fetch_wikipedia_events  # noqa: E402

EVENTS_INDEX_FILE = ROOT / "data" / "eventos_por_dia.json"
EVENTS_PER_DAY = 6


def load_env():
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def get_pool():
    keys = load_nvidia_api_keys()
    pool = NvidiaKeyPool(keys)
    return pool


def dates_between(start: date_type, end: date_type):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def existing_dates(posts):
    return {str(post.get("date", ""))[:10] for post in posts}


def configure_source_filter(domains):
    if not domains:
        return
    pregenerator.SOURCE_DOMAIN_FILTER = set(domains)
    os.environ["ARQUIVO_SOURCE_DOMAINS"] = ",".join(domains)
    print(f"Filtro de fontes ativo: {', '.join(sorted(domains))}")


def generate_range(start, end, source_mode, limite):
    posts = pregenerator.load_json(pregenerator.PENDING_POSTS_FILE, [])
    before = len(posts)
    pregenerator.generate_pending_posts_for_interval(
        posts,
        "pt",
        start,
        end,
        source_mode=source_mode,
        save_progress=True,
    )
    pregenerator.save_json(pregenerator.PENDING_POSTS_FILE, posts)
    print(f"\n== {start} a {end}: {len(posts) - before} post(s) novos (total {len(posts)}).", flush=True)


def prompt_events_for_day(pool, month, day, events_payload):
    simplified = []
    for event in (events_payload.get("selected") or []) + (events_payload.get("events") or [])[:20]:
        text = str(event.get("text") or "").strip()
        year = event.get("year")
        if not text or not year:
            continue
        simplified.append({"year": str(year), "text": text})
    if not simplified:
        return []
    prompt = f"""Você é o curador de um site português de notícias históricas ("Notícias de Ontem").
Data: dia {day} de {calendar_module.month_name[month] if month <= 12 else month} (qualquer ano).

A partir dos acontecimentos reais abaixo (Wikipedia "on this day"), escolha até {EVENTS_PER_DAY} que valem uma notícia no site — priorize acontecimentos verdadeiramente marcantes (política, guerra e paz, ciência, desporto, catástrofe, cultura) com reconhecimento imediato para o público português.

Para cada escolhido devolva (JSON válido, sem markdown):
{{
  "events": [
    {{
      "year": "YYYY",
      "title": "Manchete curta em português (sem ano no título)",
      "title_en": "A mesma manchete em inglês americano natural",
      "summary": "1 frase em português com o essencial",
      "relevance": {{"impacto_historico": 0-100, "dimensao_impacto": 0-100, "consequencias": 0-100, "relevancia_posterior": 0-100, "dimensao_duracao": 0-100, "relevancia_mediatica": 0-100, "singularidade": 0-100, "justification": "1 frase em português"}}
    }}
  ]
}}

Acontecimentos (reais, não invente):
{json.dumps(simplified, ensure_ascii=False)}
"""
    for attempt in range(3):
        if not pool.has_keys():
            return []
        try:
            response = pool.chat_json(prompt, timeout=120)
            payload = json.loads(response or "{}")
            events = payload.get("events") or []
            return [event for event in events if isinstance(event, dict) and event.get("title")][:EVENTS_PER_DAY]
        except Exception as exc:
            print(f"[eventos {month:02d}-{day:02d}] tentativa {attempt + 1} falhou: {exc}")
            pool.rotate()
            time.sleep(2)
    return []


def build_events_index(lang="pt"):
    pool = get_pool()
    index = load_json(EVENTS_INDEX_FILE, {})
    today_month_day = datetime.now().strftime("%m-%d")
    total_days = 0
    for month in range(1, 13):
        for day in range(1, calendar_module.monthrange(2024, month)[1] + 1):
            month_day = f"{month:02d}-{day:02d}"
            if month_day == "02-29":
                continue
            if month_day in index and index[month_day]:
                continue
            payload = fetch_wikipedia_events(lang, month, day)
            chosen = prompt_events_for_day(pool, month, day, payload) if pool.has_keys() else []
            normalized = []
            for event in chosen:
                year = str(event.get("year") or "").strip()
                if not re.match(r"^\d{3,4}$", year):
                    continue
                relevance = normalize_relevance(event.get("relevance")) or {}
                normalized.append({
                    "year": year,
                    "event_date": f"{year}-{month_day}",
                    "title": str(event.get("title") or "").strip(),
                    "title_en": str(event.get("title_en") or "").strip(),
                    "summary": str(event.get("summary") or "").strip(),
                    "relevance_level": relevance.get("level"),
                    "justification": relevance.get("justification") or "",
                    "source_url": f"https://pt.wikipedia.org/wiki/{month_day.replace('-', '_')}",
                })
            index[month_day] = normalized
            total_days += 1
            save_json(EVENTS_INDEX_FILE, index)
            if total_days % 10 == 0:
                print(f"[eventos] {total_days} dias processados (último: {month_day}, {len(normalized)} eventos)")
            if month_day == today_month_day:
                pass
            time.sleep(0.6)
    save_json(EVENTS_INDEX_FILE, index)
    filled = sum(1 for value in index.values() if value)
    print(f"[eventos] índice concluído: {filled}/366 dias com eventos.")


def backfill_relevance():
    """Pontua options antigas sem relevance, completa EN e ancora wayback."""
    pool = get_pool()
    posts = pregenerator.load_json(pregenerator.PENDING_POSTS_FILE, [])
    changed = 0
    for post in posts:
        for option in post.get("options") or []:
            option_changed = False
            if not option.get("relevance"):
                prompt = f"""Avalie a relevância histórica desta notícia e devolva APENAS JSON:
{{"impacto_historico": 0-100, "dimensao_impacto": 0-100, "consequencias": 0-100, "relevancia_posterior": 0-100, "dimensao_duracao": 0-100, "relevancia_mediatica": 0-100, "singularidade": 0-100, "justification": "1-2 frases em português sobre o nível, citando consequências duradouras se existirem"}}

Ano: {option.get("year")}
Categoria: {option.get("category")}
Título: {option.get("title")}
Resumo: {option.get("summary")}
Legenda: {option.get("caption")}"""
                if pool.has_keys():
                    try:
                        response = pool.chat_json(prompt, timeout=90)
                        relevance = normalize_relevance(json.loads(response or "{}"))
                        if relevance:
                            option["relevance"] = relevance
                            option_changed = True
                    except Exception as exc:
                        print(f"[backfill] {post.get('id')}: {exc}")
            if not option.get("title_en") and pool.has_keys():
                try:
                    response = pool.chat_json(
                        "Traduza para inglês americano natural (não literal). Responda apenas JSON: "
                        f'{{"title_en": "...", "summary_en": "..."}}\n'
                        f'Título: {option.get("title")}\nResumo: {option.get("overlay_description") or option.get("summary")}',
                        timeout=60,
                    )
                    translated = json.loads(response or "{}")
                    if translated.get("title_en"):
                        option["title_en"] = str(translated["title_en"]).strip()
                        option["summary_en"] = str(translated.get("summary_en") or "").strip()
                        option_changed = True
                except Exception as exc:
                    print(f"[backfill EN] {post.get('id')}: {exc}")
            if not option.get("article_url") and option.get("year"):
                resolved = pregenerator.resolve_wayback_capture(
                    option.get("background_source_url") or option.get("source_url") or "",
                    str(option.get("year")),
                    title=str(option.get("title") or ""),
                )
                if resolved:
                    option["article_url"] = resolved
                    option_changed = True
            if option_changed:
                changed += 1
    pregenerator.save_json(pregenerator.PENDING_POSTS_FILE, posts)
    print(f"[backfill] {changed} option(s) atualizadas.")


def main():
    parser = argparse.ArgumentParser(description="Popula o site com notícias históricas.")
    parser.add_argument("--start", help="Data inicial YYYY-MM-DD")
    parser.add_argument("--end", help="Data final YYYY-MM-DD")
    parser.add_argument("--tudo-ano", action="store_true", help="Todos os dias do ano sem posts (default: ano atual)")
    parser.add_argument("--ano", type=int, default=datetime.now().year, help="Ano para --tudo-ano")
    parser.add_argument("--source-mode", default="local-first", choices=["local", "local-first", "arquivo-first", "arquivo-only"])
    parser.add_argument("--jornal", action="append", default=[], help="Domínio/handle a incluir (repetível)")
    parser.add_argument("--limite", type=int, default=0, help="Máximo de DIAS a gerar nesta execução")
    parser.add_argument("--com-eventos", action="store_true", help="Reconstruir o índice de eventos por dia (Wikipedia + IA)")
    parser.add_argument("--backfill-relevance", action="store_true", help="Pontuar/completar posts existentes")
    args = parser.parse_args()

    env = load_env()
    os.environ.setdefault("ARQUIVO_SEARCH_TERMS", env.get("ARQUIVO_SEARCH_TERMS", ""))
    configure_source_filter({item.lower() for item in args.jornal})

    did_work = False
    if args.backfill_relevance:
        backfill_relevance()
        did_work = True
    if args.com_eventos:
        build_events_index()
        did_work = True
    if args.start or args.end or args.tudo_ano:
        posts = load_json(pregenerator.PENDING_POSTS_FILE, [])
        taken = existing_dates(posts)
        if args.tudo_ano:
            year = args.ano
            targets = [
                date_type(year, month, day)
                for month in range(1, 13)
                for day in range(1, calendar_module.monthrange(year, month)[1] + 1)
                if f"{year:04d}-{month:02d}-{day:02d}" not in taken
            ]
        else:
            if not (args.start and args.end):
                parser.error("--start e --end são obrigatórios sem --tudo-ano")
            start = datetime.strptime(args.start, "%Y-%m-%d").date()
            end = datetime.strptime(args.end, "%Y-%m-%d").date()
            targets = [day for day in dates_between(start, end) if day.isoformat() not in taken]
        if args.limite > 0:
            targets = targets[: args.limite]
        print(f"Dias a gerar: {len(targets)} ({args.source_mode})")
        for index in range(0, len(targets), 10):
            batch = targets[index : index + 10]
            generate_range(batch[0], batch[-1], args.source_mode, args.limite)
        did_work = True
    if not did_work:
        parser.print_help()


if __name__ == "__main__":
    main()
