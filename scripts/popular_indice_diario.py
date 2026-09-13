"""Índice diário de relevância: top 25/dia globais + top 25/dia por fonte.

Varre o índice CDXJ (disco local ou D:\arquivo_cdxj) de 2026 → 1996,
extrai candidatos por dia/fonte, pontua com a IA (NVIDIA) e grava
indice_diario/YYYY/MM-DD.json. Retomável: dias já feitos são saltados.

Uso: python popular_indice_diario.py [--ano-inicio 1996] [--ano-fim 2026] [--limite-dias 0]
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date as date_type
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from historical_relevance import normalize_relevance  # noqa: E402
from nvidia_client import NvidiaKeyPool, load_nvidia_api_keys  # noqa: E402
from publisher import load_arquivo_cdxj_candidates_for_day  # noqa: E402

INDEX_DIR = ROOT / "indice_diario"
STATE_FILE = ROOT / "indice_diario_state.json"
TOP_GLOBAL = 25
TOP_PER_SOURCE = 25
MAX_CANDIDATES_PER_DAY = 120  # candidatos lidos antes de enviar para IA


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path, data):
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def get_pool():
    return NvidiaKeyPool(load_nvidia_api_keys())


def score_day_with_ai(pool, day_str, candidates):
    """Envia os candidatos do dia para a IA e recebe o top com pontuação."""
    if not candidates:
        return []
    compact = []
    for index, candidate in enumerate(candidates[:MAX_CANDIDATES_PER_DAY]):
        compact.append({
            "idx": index,
            "source": candidate.get("domain", ""),
            "date": candidate.get("date", day_str),
            "title": (candidate.get("title") or "")[:200],
            "snippet": (candidate.get("snippet") or candidate.get("global_context") or "")[:250],
        })
    prompt = f"""Você é o curador de um site português de notícias históricas ("Notícias de Ontem").
Data do dia: {day_str} (mesmo dia em anos anteriores).

Dos acontecimentos reais abaixo (candidatos do índice CDXJ do Arquivo.pt), escolha os {TOP_GLOBAL} mais relevantes historicamente.

Para cada escolhido, devolva JSON válido (sem markdown):
{{
  "news": [
    {{
      "idx": 0,
      "title": "Manchete curta em português (máx 70 caracteres, sem ano no título)",
      "title_en": "Em inglês americano natural",
      "summary": "1 frase em português",
      "category": "POLÍTICA|DESPORTO|CULTURA|SOCIEDADE|CIÊNCIA|ECONOMIA|MUNDIAL",
      "networks": ["instagram", "facebook" e/ou "x"],
      "relevance": {{
        "impacto_historico": 0-100,
        "dimensao_impacto": 0-100,
        "consequencias": 0-100,
        "relevancia_posterior": 0-100,
        "dimensao_duracao": 0-100,
        "relevancia_mediatica": 0-100,
        "singularidade": 0-100,
        "justification": "1-2 frases em português (máx 25 palavras)"
      }},
      "source_idx": índice do candidato original (para ligar à fonte)
    }}
  ]
}}

Candidatos reais (não invente):
{json.dumps(compact, ensure_ascii=False)}
"""
    for attempt in range(3):
        if not pool.has_keys():
            return []
        try:
            response = pool.chat_json(prompt, timeout=180)
            payload = json.loads(response or "{}")
            news = payload.get("news") or []
            results = []
            for item in news:
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                source_idx = item.get("source_idx")
                source_candidate = None
                if isinstance(source_idx, int) and 0 <= source_idx < len(candidates):
                    source_candidate = candidates[source_idx]
                relevance = normalize_relevance(item.get("relevance")) or {}
                entry = {
                    "title": str(item.get("title") or "").strip(),
                    "title_en": str(item.get("title_en") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "category": str(item.get("category") or "ATUALIDADE").upper(),
                    "networks": item.get("networks") or ["instagram"],
                    "relevance_level": relevance.get("level"),
                    "relevance_scores": relevance.get("scores") or {},
                    "justification": relevance.get("justification") or "",
                    "source_url": (source_candidate or {}).get("source_url", ""),
                    "source_domain": (source_candidate or {}).get("domain", ""),
                }
                results.append(entry)
            return results[:TOP_GLOBAL]
        except Exception as exc:
            print(f"[indice {day_str}] tentativa {attempt + 1}: {exc}")
            pool.rotate()
            time.sleep(3)
    return []


def group_by_source(entries):
    """Agrupa por domínio (top 25 por fonte)."""
    by_source = {}
    for entry in entries:
        domain = entry.get("source_domain") or "outros"
        by_source.setdefault(domain, []).append(entry)
    return {source: items[:TOP_PER_SOURCE] for source, items in by_source.items()}


def process_day(pool, year, month, day, sources_list, seen_urls):
    day_str = f"{year:04d}-{month:02d}-{day:02d}"
    try:
        candidates = load_arquivo_cdxj_candidates_for_day(year, month, day, sources_list, seen_urls)
    except Exception as exc:
        print(f"[{day_str}] erro a ler CDXJ: {exc}")
        return None
    if not candidates:
        return None
    # Ranquear por score local antes de enviar para IA (cortar para 120)
    from pregenerator import score_nvidia_candidate
    candidates.sort(key=score_nvidia_candidate, reverse=True)
    candidates = candidates[:MAX_CANDIDATES_PER_DAY]
    entries = score_day_with_ai(pool, day_str, candidates)
    if not entries:
        return None
    return {
        "day": day_str,
        "entries": entries,
        "by_source": group_by_source(entries),
        "generated_at": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Popula o índice diário de relevância.")
    parser.add_argument("--ano-inicio", type=int, default=1996)
    parser.add_argument("--ano-fim", type=int, default=datetime.now().year)
    parser.add_argument("--limite-dias", type=int, default=0, help="Máximo de dias nesta execução (0 = todos)")
    args = parser.parse_args()

    pool = get_pool()
    state = load_json(STATE_FILE, {})
    done_days = set(state.get("done_days", []))
    sources_list = [
        {"domain": domain}
        for domain in sorted(state.get("sources") or [
            "publico.pt", "expresso.pt", "cmjornal.pt", "sabado.pt", "rtp.pt",
            "observador.pt", "jn.pt", "dn.pt", "sicnoticias.pt", "noticiasaominuto.com",
        ])
    ]

    total_days = 0
    skipped = 0
    current = date_type(args.ano_fim, 12, 31)
    start = date_type(args.ano_inicio, 1, 1)

    while current >= start:
        day_str = current.isoformat()
        if day_str in done_days:
            current -= timedelta(days=1)
            skipped += 1
            continue
        month_dir = INDEX_DIR / f"{current.year:04d}"
        month_dir.mkdir(parents=True, exist_ok=True)
        output = month_dir / f"{current.month:02d}-{current.day:02d}.json"
        if output.exists():
            done_days.add(day_str)
            current -= timedelta(days=1)
            skipped += 1
            continue

        entries = process_day(pool, current.year, current.month, current.day, sources_list, set())
        if entries:
            save_json(output, entries)
            done_days.add(day_str)
            total_days += 1
            print(f"[{day_str}] {len(entries.get('entries', []))} notícias", flush=True)
        else:
            print(f"[{day_str}] sem resultado", flush=True)

        state["done_days"] = sorted(done_days)
        state["sources"] = [s.get("domain") for s in sources_list]
        state["updated_at"] = datetime.now().isoformat()
        save_json(STATE_FILE, state)

        if args.limite_dias > 0 and total_days >= args.limite_dias:
            print(f"Limite de {args.limite_dias} dias atingido.")
            break
        current -= timedelta(days=1)
        time.sleep(1)

    print(f"Concluído: {total_days} dias processados, {skipped} saltados.")


if __name__ == "__main__":
    main()
