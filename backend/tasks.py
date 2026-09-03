import json
import os
from datetime import date

from celery import Celery

from backend.database import SessionLocal, init_db
from backend.fast_topic_service import FastTopicSearchError, analyze_topic_fast, can_answer, index_status
from backend.models import TopicJob
from backend.rate_limit import release_topic_job_slot
from backend.topic_service import TopicProbeBudget, analyze_topic, year_slices


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("noticias_de_ontem", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,
    task_always_eager=os.environ.get("TOPIC_TASK_ALWAYS_EAGER", "").lower() in {"1", "true", "yes"}
    or "REDIS_URL" not in os.environ,
)


@celery_app.task(name="backend.tasks.run_topic_job")
def run_topic_job(job_id):
    try:
        init_db()
        with SessionLocal() as db:
            job = db.get(TopicJob, job_id)
            if not job:
                return
            request_data = json.loads(job.request_json)
            job.status = "running"
            job.progress = 0
            db.commit()

            from_date = date.fromisoformat(request_data["from_date"])
            to_date = date.fromisoformat(request_data["to_date"])
            analyses = request_data["analyses"]
            total_periods = max(1, len(year_slices(from_date, to_date)) * len(analyses))
            completed_periods = 0
            budget = TopicProbeBudget(int(os.environ.get("TOPIC_MAX_PROBES_BACKEND", "5000")))

            def update_progress():
                nonlocal completed_periods
                completed_periods += 1
                job.progress = min(99, round((completed_periods / total_periods) * 100))
                db.commit()

            try:
                fast_search = can_answer(from_date, to_date)
                if fast_search:
                    try:
                        results = []
                        for analysis in analyses:
                            result = analyze_topic_fast(analysis, from_date, to_date)
                            results.append(result)
                            for _ in result["series"]:
                                update_progress()
                    except FastTopicSearchError:
                        fast_search = False
                        completed_periods = 0
                        job.progress = 0
                        db.commit()
                if not fast_search:
                    results = [
                        analyze_topic(analysis, from_date, to_date, budget, update_progress)
                        for analysis in analyses
                    ]
                job.result_json = json.dumps({
                    "analyses": results,
                    "from_date": request_data["from_date"],
                    "to_date": request_data["to_date"],
                    "show_values": bool(request_data.get("show_values", True)),
                    "probes_used": budget.used,
                    "complete": all(result.get("complete") for result in results),
                    "engine": "opensearch" if fast_search else "arquivo_pt_api",
                    "search_status": index_status(),
                }, ensure_ascii=False)
                job.status = "completed"
                job.progress = 100
                job.error = None
            except Exception as exc:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
            db.commit()
    finally:
        release_topic_job_slot(str(job_id))
