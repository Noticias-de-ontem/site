import argparse
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from archive_storage import all_block_ids, block_lock, load_block, save_block
from nvidia_client import DEFAULT_NVIDIA_MODEL, NvidiaKeyPool, load_nvidia_api_keys, NvidiaQuotaExceeded


BASIC_KEYWORDS = {"noticias", "news", "web"}


def now_local():
    return datetime.now(ZoneInfo("Europe/Lisbon"))


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def first_option(post):
    options = post.get("options")
    if isinstance(options, list) and options and isinstance(options[0], dict):
        return options[0]
    return {}


def best_title(post):
    option = first_option(post)
    return (
        normalize_text(option.get("title"))
        or normalize_text(post.get("ai_summary"))
        or normalize_text(post.get("raw_caption"))
        or normalize_text(post.get("global_context"))
        or "Noticia"
    )


def looks_like_basic_fallback(post):
    if post.get("source_platform") != "web":
        return False
    if "web_news" not in set(post.get("content_flags") or []):
        return False

    status = normalize_text(post.get("enrichment_status")).lower()
    if status in {"ai_error", "metadata_only"}:
        return True

    keywords = {normalize_text(item).lower() for item in post.get("topic_keywords") or []}
    signals = [normalize_text(item) for item in post.get("virality_signals") or [] if normalize_text(item)]
    mode = normalize_text(post.get("content_mode")).lower()
    summary = normalize_text(post.get("ai_summary"))
    raw_caption = normalize_text(post.get("raw_caption"))
    global_context = normalize_text(post.get("global_context"))
    enriched_context = normalize_text(post.get("enriched_context"))

    has_basic_keywords = bool(keywords) and keywords.issubset(BASIC_KEYWORDS)
    has_basic_summary = bool(summary) and summary in {raw_caption, global_context}
    has_no_real_context = not enriched_context or enriched_context in {raw_caption, summary}

    return mode == "photo_roundup" and has_basic_keywords and not signals and has_basic_summary and has_no_real_context


def post_to_article(post):
    title = best_title(post)
    description = normalize_text(post.get("raw_caption")) or normalize_text(post.get("ai_summary")) or title
    text = normalize_text(post.get("global_context")) or description
    return {
        "title": title,
        "description": description,
        "text": text,
        "image_url": normalize_text(post.get("image_url")),
    }


def enrich_with_nvidia(pool, model, article, lang):
    prompt = f"""
You are cataloging archived news articles for a daily news digest application.
Language required for the output: {lang.upper()}

Analyze the archived news article below and replace any basic fallback metadata with a real editorial analysis.

Title: {article["title"]}
Lead Paragraph: {article["description"]}
Body/context extract:
{article["text"]}

Return a JSON object with exactly these keys:
- content_mode: one of "single_story", "carousel_roundup", "weekly_recap", "internet_culture", "meme", "promo", "photo_roundup", "institutional_news", "feature", "unclear"
- enriched_context: 1 to 2 short paragraphs in {lang.upper()}, summarizing the news and its context. Remove hashtags and calls to action.
- summary: one sentence in {lang.upper()}
- topic_keywords: array with up to 5 short strings in {lang.upper()}
- virality_signals: array with up to 3 short strings
- should_skip: true only if this is essentially a duplicate announcement, advertising, or local utility notice without news value.
"""
    response_text = pool.chat_json(prompt, model=model)
    payload = json.loads(response_text or "{}")
    if not isinstance(payload, dict):
        raise ValueError("Resposta NVIDIA nao e um objeto JSON.")
    return payload


def apply_ai_payload(post, ai_payload, lang):
    article = post_to_article(post)
    summary = normalize_text(ai_payload.get("summary")) or article["description"] or article["title"]
    enriched_context = normalize_text(ai_payload.get("enriched_context")) or summary
    content_mode = normalize_text(ai_payload.get("content_mode")) or "single_story"
    topic_keywords = [
        normalize_text(item)
        for item in (ai_payload.get("topic_keywords") or [])
        if normalize_text(item)
    ][:5]
    virality_signals = [
        normalize_text(item)
        for item in (ai_payload.get("virality_signals") or [])
        if normalize_text(item)
    ][:3]

    post["global_context"] = enriched_context
    post["enriched_context"] = enriched_context
    post["ai_summary"] = summary
    post["topic_keywords"] = topic_keywords
    post["virality_signals"] = virality_signals
    post["content_mode"] = content_mode
    post["should_skip"] = bool(ai_payload.get("should_skip", False))
    post["needs_enrichment"] = False
    post["enrichment_status"] = "done"
    post["enriched_at"] = now_local().isoformat()
    post["ai_provider"] = "nvidia"

    option = first_option(post)
    if option:
        option["summary"] = summary
        option["overlay_description"] = summary[:120]
        year = normalize_text(option.get("year")) or normalize_text(post.get("date"))[:4]
        prefix = "Neste dia em" if lang == "pt" else "On this day in"
        option["caption"] = f"{prefix} {year}: {summary}" if year else summary


def reanalyze(lang, months, limit, dry_run, model):
    api_keys = load_nvidia_api_keys()
    pool = NvidiaKeyPool(api_keys)
    if not pool.has_keys():
        raise SystemExit("Erro: define NVIDIA_API_KEY ou cria nvidia_api_key.local.txt com a chave da NVIDIA.")

    changed = 0
    matched = 0
    failures = 0
    month_set = {int(month) for month in months} if months else None

    for block_id in all_block_ids():
        with block_lock(lang, block_id):
            posts = load_block(lang, block_id)
            block_changed = False

            for post in posts:
                date_text = normalize_text(post.get("date"))
                if month_set:
                    try:
                        month = int(date_text[5:7])
                    except ValueError:
                        continue
                    if month not in month_set:
                        continue

                if not looks_like_basic_fallback(post):
                    continue

                matched += 1
                title = best_title(post)
                print(f"[{lang}][bloco {block_id}] Reanalise candidata: {date_text} - {title[:80]}")

                if dry_run:
                    if limit and matched >= limit:
                        print(f"Limite de listagem atingido ({limit}).")
                        return matched, changed, failures
                    continue
                if limit and changed >= limit:
                    print(f"Limite atingido ({limit}).")
                    return matched, changed, failures

                attempts = 0
                max_attempts = max(len(pool.api_keys) * 2, 6)
                success = False
                while attempts < max_attempts:
                    attempts += 1
                    try:
                        ai_payload = enrich_with_nvidia(pool, model, post_to_article(post), lang)
                        apply_ai_payload(post, ai_payload, lang)
                        pool.save_key_status_to_file()
                        changed += 1
                        block_changed = True
                        success = True
                        break
                    except NvidiaQuotaExceeded as exc:
                        print(f"[{lang}][bloco {block_id}] Quota diária esgotada na chave #{pool.current_index + 1}: {exc}")
                        pool.mark_current_exhausted()
                        if not pool.rotate():
                            print("Todas as chaves NVIDIA esgotaram a quota diária.")
                            import sys
                            sys.exit(2)
                        continue
                    except Exception as exc:
                        print(f"[{lang}][bloco {block_id}] Erro temporário na chave #{pool.current_index + 1}: {exc}")
                        active_keys = sum(1 for x in pool.exhausted if not x)
                        if active_keys > 1:
                            pool.rotate()
                            time.sleep(1)
                            continue
                        else:
                            print("A aguardar 5s antes de tentar novamente...")
                            time.sleep(5)
                            continue
                
                if not success:
                    print(f"[{lang}][bloco {block_id}] Erro persistente na NVIDIA durante a reanálise. A parar a execução.")
                    import sys
                    sys.exit(1)

            if block_changed:
                save_block(lang, block_id, posts)

    return matched, changed, failures


def parse_months(value):
    if not value:
        return []
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def main():
    parser = argparse.ArgumentParser(description="Reanalisa noticias web guardadas apenas com fallback basico sem avaliacao por IA.")
    parser.add_argument("--lang", choices=["pt", "en", "both"], default="pt")
    parser.add_argument("--months", default="", help="Meses a processar, separados por virgulas. Ex: 1,2,3")
    parser.add_argument("--limit", type=int, default=0, help="Numero maximo de noticias a reanalisar nesta execucao.")
    parser.add_argument("--dry-run", action="store_true", help="Lista candidatas sem alterar ficheiros nem chamar a NVIDIA.")
    parser.add_argument("--model", default=os.environ.get("NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL))
    args = parser.parse_args()

    langs = ["pt", "en"] if args.lang == "both" else [args.lang]
    total_matched = 0
    total_changed = 0
    total_failures = 0

    for lang in langs:
        print(f"\n=== Reanalise {lang.upper()} ===")
        matched, changed, failures = reanalyze(
            lang=lang,
            months=parse_months(args.months),
            limit=args.limit,
            dry_run=args.dry_run,
            model=args.model,
        )
        total_matched += matched
        total_changed += changed
        total_failures += failures

        if args.dry_run:
            print(f"Resumo {lang}: {matched} candidatas listadas, 0 ficheiros alterados, {failures} falhas.")
        else:
            print(f"Resumo {lang}: {matched} candidatas, {changed} reanalisadas, {failures} falhas.")

    if len(langs) > 1:
        if args.dry_run:
            print(f"\nResumo total: {total_matched} candidatas listadas, 0 ficheiros alterados, {total_failures} falhas.")
        else:
            print(f"\nResumo total: {total_matched} candidatas, {total_changed} reanalisadas, {total_failures} falhas.")


if __name__ == "__main__":
    main()
