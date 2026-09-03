import os
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("INDEX_WORKSPACE", "/data")).resolve()
INTERVAL = max(300, int(os.environ.get("INDEX_UPDATE_INTERVAL_SECONDS", "86400")))


def run(command):
    print(f"[index-worker] {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def sync_dynamic_coverage():
    if not os.environ.get("DATABASE_URL"):
        print("[index-worker] DATABASE_URL ausente; cobertura dinamica nao atualizada.", flush=True)
        return
    state_file = WORKSPACE / "arquivo_cdxj_state.json"
    if not state_file.exists():
        return
    state = json.loads(state_file.read_text(encoding="utf-8"))
    domain_coverage = state.get("domain_coverage") or {}
    if not domain_coverage:
        print("[index-worker] domain_coverage ainda nao existe.", flush=True)
        return

    from backend.database import SessionLocal, init_db
    from backend.models import SiteSnapshot

    init_db()
    with SessionLocal() as database:
        snapshot = database.get(SiteSnapshot, 1)
        if not snapshot:
            print("[index-worker] Retrato publico ainda nao existe no PostgreSQL.", flush=True)
            return
        payload = json.loads(snapshot.payload_json)
        topic_search = payload.setdefault("topic_search", {})
        metrics = payload.setdefault("metrics", {})
        previous_metadata = topic_search.get("source_metadata") or {}
        valid_coverage = {
            source: details
            for source, details in domain_coverage.items()
            if isinstance(details, dict) and details.get("first_date") and details.get("latest_date")
        }
        if not valid_coverage:
            print("[index-worker] Cobertura sem datas validas; retrato mantido.", flush=True)
            return
        sources = sorted(valid_coverage)
        first_date = min(details["first_date"] for details in valid_coverage.values())
        latest_date = max(details["latest_date"] for details in valid_coverage.values())
        today = datetime.now().date().isoformat()
        latest_date = min(latest_date, today)

        source_metadata = {}
        for source in sources:
            coverage = valid_coverage[source]
            previous = previous_metadata.get(source) or {}
            created_year = int(previous.get("created_year") or str(coverage.get("first_date") or first_date)[:4])
            source_start = max(f"{created_year}-01-01", coverage.get("first_date") or first_date)
            source_end = min(latest_date, coverage.get("latest_date") or latest_date)
            source_metadata[source] = {
                "created_year": created_year,
                "analysis_start": source_start,
                "analysis_end": source_end,
                "first_capture_date": coverage.get("first_date") or "",
                "latest_capture_date": coverage.get("latest_date") or source_end,
                "search_hosts": previous.get("search_hosts") or [f"www.{source}", source],
            }

        old_news_sources = int(metrics.get("news_sources") or len(sources))
        extra_sources = max(0, int(metrics.get("unique_sources") or old_news_sources) - old_news_sources)
        metrics["coverage_start_year"] = int(first_date[:4])
        metrics["coverage_end_year"] = int(latest_date[:4])
        metrics["news_sources"] = len(sources)
        metrics["unique_sources"] = len(sources) + extra_sources
        metrics["news_source_domains"] = sources
        metrics["news_covered"] = sum(
            int(details.get("written") or 0)
            for details in (state.get("processed") or {}).values()
            if isinstance(details, dict)
        )
        topic_search.update({
            "start_year": metrics["coverage_start_year"],
            "end_year": metrics["coverage_end_year"],
            "min_date": first_date,
            "max_date": latest_date,
            "sources": sources,
            "source_metadata": source_metadata,
            "coverage_updated_at": state.get("coverage_updated_at") or datetime.now(timezone.utc).isoformat(),
            "coverage_basis": "cdxj_domain",
            "coverage_precise": True,
        })
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload["generated_at"] = generated_at
        snapshot.generated_at = generated_at
        snapshot.payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        database.commit()
        print(f"[index-worker] Cobertura dinamica atualizada ate {latest_date}.", flush=True)


def update_once():
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    lock = WORKSPACE / "index-update.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
    except FileExistsError:
        print("[index-worker] Outra atualizacao ainda esta ativa.", flush=True)
        return
    try:
        download_code = run([
            sys.executable,
            str(ROOT / "sync_cdxj_storage.py"),
            "download",
            "--workspace",
            str(WORKSPACE),
        ])
        if download_code:
            print(f"[index-worker] Download terminou com codigo {download_code}.", flush=True)
            return
        if os.environ.get("INDEX_REFRESH_CDXJ", "true").lower() in {"1", "true", "yes"}:
            cdxj_code = run([
                sys.executable,
                str(ROOT / "build_arquivo_cdxj_index.py"),
                "--output-dir",
                str(WORKSPACE / "arquivo_cdxj"),
                "--state-file",
                str(WORKSPACE / "arquivo_cdxj_state.json"),
                "--start-year",
                os.environ.get("INDEX_START_YEAR", "1996"),
                "--end-year",
                os.environ.get("INDEX_END_YEAR", str(datetime.now().year)),
                "--all-remote",
            ])
            if cdxj_code:
                print(f"[index-worker] Atualizacao CDXJ terminou com codigo {cdxj_code}.", flush=True)
                return
            upload_code = run([
                sys.executable,
                str(ROOT / "sync_cdxj_storage.py"),
                "upload",
                "--workspace",
                str(WORKSPACE),
            ])
            if upload_code:
                print(f"[index-worker] Backup CDXJ terminou com codigo {upload_code}.", flush=True)
                return
            sync_dynamic_coverage()
        index_code = run([
            sys.executable,
            str(ROOT / "build_topic_search_index.py"),
            "--input-dir",
            str(WORKSPACE / "arquivo_cdxj"),
            "--state-file",
            str(WORKSPACE / "topic_index_state.json"),
            "--start-date",
            os.environ.get("INDEX_COVERAGE_START", "1996-01-01"),
        ])
        print(f"[index-worker] Indexacao terminou com codigo {index_code}.", flush=True)
        run([
            sys.executable,
            str(ROOT / "sync_cdxj_storage.py"),
            "upload",
            "--workspace",
            str(WORKSPACE),
            "--include-index-state",
        ])
    finally:
        lock.unlink(missing_ok=True)


def main():
    while True:
        update_once()
        if os.environ.get("INDEX_RUN_ONCE", "").lower() in {"1", "true", "yes"}:
            return
        print(f"[index-worker] Proxima verificacao em {INTERVAL} segundos.", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
