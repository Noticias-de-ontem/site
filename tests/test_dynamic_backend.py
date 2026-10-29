import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


TEST_DATABASE = Path(tempfile.gettempdir()) / "noticias_ontem_backend_test.db"
TEST_DATABASE.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["SITE_SYNC_TOKEN"] = "test-sync-token"
os.environ["TOPIC_TASK_ALWAYS_EAGER"] = "false"

try:
    from fastapi.testclient import TestClient  # noqa: E402
    from backend.app import app  # noqa: E402
    from backend import calendar_service, fast_topic_service, index_update_worker  # noqa: E402
    from backend.database import SessionLocal, engine  # noqa: E402
    from backend.models import SiteSnapshot, TopicJob  # noqa: E402
    from backend.topic_service import TopicProbeBudget, period_slices, verified_interval_count  # noqa: E402
    HAS_BACKEND_DEPS = True
except ImportError:
    HAS_BACKEND_DEPS = False
    TestClient = None
    app = None


TEST_SITE_DATA = {
    "generated_at": "2026-07-11T12:00:00+00:00",
    "featured": None,
    "carousel": [],
    "latest": [],
    "all": [],
    "metrics": {"published_posts": 17, "followers": 42},
    "topic_search": {
        "min_date": "1996-01-01",
        "max_date": "2026-07-08",
        "sources": ["publico.pt"],
        "source_metadata": {
            "publico.pt": {
                "analysis_start": "1996-09-22",
                "analysis_end": "2026-07-07",
                "search_hosts": ["www.publico.pt", "publico.pt"],
            }
        },
    },
}


@unittest.skipUnless(HAS_BACKEND_DEPS, 'FastAPI or backend dependencies not installed')
class DynamicBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        engine.dispose()
        TEST_DATABASE.unlink(missing_ok=True)

    def test_health_and_protected_site_sync(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.post("/api/admin/site-data", json=TEST_SITE_DATA).status_code, 401)
        response = self.client.post(
            "/api/admin/site-data",
            json=TEST_SITE_DATA,
            headers={"Authorization": "Bearer test-sync-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/metrics").json()["followers"], 42)
        self.assertEqual(self.client.get("/api/coverage").json()["max_date"], "2026-07-08")

    def test_source_specific_maximum_is_enforced(self):
        self.client.post(
            "/api/admin/site-data",
            json=TEST_SITE_DATA,
            headers={"Authorization": "Bearer test-sync-token"},
        )
        payload = {
            "analyses": [{"query": "Ronaldo", "source": "publico.pt", "color": "#005a8d"}],
            "from_date": "2026-07-01",
            "to_date": "2026-07-08",
        }
        response = self.client.post("/api/topic-analyses", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["maximum"], "2026-07-07")

    @patch("backend.app.run_topic_job.delay")
    def test_cache_ignores_presentation_color(self, delay):
        self.client.post(
            "/api/admin/site-data",
            json=TEST_SITE_DATA,
            headers={"Authorization": "Bearer test-sync-token"},
        )
        payload = {
            "analyses": [{"query": "Ronaldo", "source": "publico.pt", "color": "#005a8d"}],
            "from_date": "2026-07-01",
            "to_date": "2026-07-07",
            "show_values": True,
        }
        first = self.client.post("/api/topic-analyses", json=payload)
        self.assertEqual(first.status_code, 202)
        job_id = first.json()["id"]
        with SessionLocal() as db:
            job = db.get(TopicJob, job_id)
            job.status = "completed"
            job.progress = 100
            job.result_json = json.dumps({"analyses": []})
            job.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
            db.commit()

        payload["analyses"][0]["color"] = "#c44f3b"
        payload["show_values"] = False
        second = self.client.post("/api/topic-analyses", json=payload)
        self.assertEqual(second.status_code, 202)
        self.assertTrue(second.json()["cached"])
        self.assertEqual(second.json()["id"], job_id)
        delay.assert_called_once_with(job_id)

    def test_estimate_is_verified_at_the_boundary(self):
        def fake_probe(_session, _query, _source, _from, _to, offset, _budget):
            return {"has_result": offset < 9, "estimate": 9}

        with patch("backend.topic_service.probe", side_effect=fake_probe):
            count = verified_interval_count(
                object(),
                "Ronaldo",
                "publico.pt",
                "20260101000000",
                "20261231235959",
                TopicProbeBudget(20),
            )
        self.assertEqual(count, 9)

    def test_cdxj_coverage_updates_dynamic_documentation_metrics(self):
        self.client.post(
            "/api/admin/site-data",
            json=TEST_SITE_DATA,
            headers={"Authorization": "Bearer test-sync-token"},
        )
        state = {
            "coverage_updated_at": "2026-07-11T12:00:00+00:00",
            "domain_coverage": {
                "publico.pt": {"first_date": "1996-09-22", "latest_date": "2026-07-08"},
                "expresso.pt": {"first_date": "2000-01-02", "latest_date": "2026-07-07"},
            },
            "processed": {
                "AWP1.cdxj": {"written": 12},
                "AWP2.cdxj": {"written": 30},
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "arquivo_cdxj_state.json").write_text(json.dumps(state), encoding="utf-8")
            with patch.object(index_update_worker, "WORKSPACE", workspace):
                index_update_worker.sync_dynamic_coverage()

        with SessionLocal() as db:
            payload = json.loads(db.get(SiteSnapshot, 1).payload_json)
        self.assertEqual(payload["metrics"]["coverage_start_year"], 1996)
        self.assertEqual(payload["metrics"]["coverage_end_year"], 2026)
        self.assertEqual(payload["metrics"]["news_sources"], 2)
        self.assertEqual(payload["metrics"]["news_covered"], 42)
        self.assertEqual(payload["topic_search"]["sources"], ["expresso.pt", "publico.pt"])
        self.assertEqual(payload["topic_search"]["source_metadata"]["expresso.pt"]["analysis_start"], "2000-01-02")

    def test_fast_index_returns_all_years_in_one_query(self):
        response = {
            "aggregations": {
                "years": {
                    "buckets": [
                        {"key_as_string": "2020-01-01T00:00:00.000Z", "doc_count": 12},
                        {"key_as_string": "2021-01-01T00:00:00.000Z", "doc_count": 27},
                    ]
                }
            }
        }
        with patch.object(fast_topic_service, "opensearch_request", return_value=response) as search:
            result = fast_topic_service.analyze_topic_fast(
                {"query": "Ronaldo", "source": "publico.pt", "color": "#005a8d"},
                datetime(2020, 6, 1).date(),
                datetime(2021, 6, 30).date(),
            )
        self.assertEqual([item["count"] for item in result["series"]], [12, 27])
        self.assertEqual(result["method"], "opensearch_fulltext_arquivo_pt")
        request_payload = search.call_args.args[2]
        filters = request_payload["query"]["bool"]["filter"]
        self.assertIn({"term": {"domain": "publico.pt"}}, filters)
        self.assertEqual(search.call_count, 1)

    def test_dynamic_calendar_uses_day_source_and_stable_news_page(self):
        search_response = {
            "hits": {
                "hits": [{
                    "_source": {
                        "capture_id": "capture-1",
                        "captured_at": "2020-07-05T12:30:00Z",
                        "domain": "publico.pt",
                        "title": "Uma noticia preservada",
                        "original_url": "https://publico.pt/noticia/1",
                        "original_url_key": "a" * 64,
                        "arquivo_url": "https://arquivo.pt/noFrame/replay/20200705123000/https://publico.pt/noticia/1",
                    }
                }]
            }
        }
        with (
            patch.object(calendar_service, "index_status", return_value={"ready": True}),
            patch.object(calendar_service, "opensearch_request", return_value=search_response) as search,
        ):
            result = calendar_service.recommendations_for_day("07-05", 2030, "publico.pt", 25)
            detail = calendar_service.news_item(f"noticia-{'a' * 64}")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["page_id"], f"noticia-{'a' * 64}")
        self.assertEqual(detail["page_id"], result["items"][0]["page_id"])
        recommendation_query = search.call_args_list[0].args[2]
        filters = recommendation_query["query"]["bool"]["filter"]
        self.assertIn({"term": {"month_day": "07-05"}}, filters)
        self.assertIn({"term": {"domain": "publico.pt"}}, filters)

    @patch("backend.app.enforce_rate_limit")
    @patch("backend.app.run_topic_job.delay")
    def test_topic_granularity_validation_and_caching(self, delay, rate_mock):
        self.client.post(
            "/api/admin/site-data",
            json=TEST_SITE_DATA,
            headers={"Authorization": "Bearer test-sync-token"},
        )
        base_payload = {
            "analyses": [{"query": "Ronaldo", "source": "publico.pt", "color": "#005a8d"}],
            "from_date": "2026-01-01",
            "to_date": "2026-06-30",
        }
        # Invalid granularity should be rejected with 422
        bad_response = self.client.post("/api/topic-analyses", json={**base_payload, "granularity": "decade"})
        self.assertEqual(bad_response.status_code, 422)

        # Year granularity creates job 1
        resp_year = self.client.post("/api/topic-analyses", json={**base_payload, "granularity": "year"})
        self.assertEqual(resp_year.status_code, 202)
        job_id_year = resp_year.json()["id"]

        with SessionLocal() as db:
            job = db.get(TopicJob, job_id_year)
            job.status = "completed"
            job.progress = 100
            job.result_json = json.dumps({"analyses": []})
            job.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
            db.commit()

        # Month granularity for identical query must NOT hit year cache (separate fingerprint)
        resp_month = self.client.post("/api/topic-analyses", json={**base_payload, "granularity": "month"})
        self.assertEqual(resp_month.status_code, 202)
        self.assertNotEqual(resp_month.json()["id"], job_id_year)
        self.assertFalse(resp_month.json()["cached"])

        # Repeating month granularity should hit month cache once completed
        job_id_month = resp_month.json()["id"]
        with SessionLocal() as db:
            job = db.get(TopicJob, job_id_month)
            job.status = "completed"
            job.progress = 100
            job.result_json = json.dumps({"analyses": []})
            job.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
            db.commit()

        resp_month_cached = self.client.post("/api/topic-analyses", json={**base_payload, "granularity": "month"})
        self.assertEqual(resp_month_cached.status_code, 202)
        self.assertTrue(resp_month_cached.json()["cached"])
        self.assertEqual(resp_month_cached.json()["id"], job_id_month)

    def test_topic_period_slices_year_month_day(self):
        # Year slices
        year_slices = period_slices(datetime(2023, 5, 10).date(), datetime(2025, 2, 20).date(), "year")
        self.assertEqual(len(year_slices), 3)
        self.assertEqual(year_slices[0]["label"], "2023")
        self.assertEqual(year_slices[0]["from_date"].isoformat(), "2023-05-10")
        self.assertEqual(year_slices[0]["to_date"].isoformat(), "2023-12-31")
        self.assertEqual(year_slices[1]["label"], "2024")
        self.assertEqual(year_slices[2]["to_date"].isoformat(), "2025-02-20")

        # Month slices
        month_slices = period_slices(datetime(2024, 1, 15).date(), datetime(2024, 3, 10).date(), "month")
        self.assertEqual(len(month_slices), 3)
        self.assertEqual(month_slices[0]["label"], "2024-01")
        self.assertEqual(month_slices[0]["from_date"].isoformat(), "2024-01-15")
        self.assertEqual(month_slices[0]["to_date"].isoformat(), "2024-01-31")
        self.assertEqual(month_slices[1]["label"], "2024-02")
        self.assertEqual(month_slices[1]["to_date"].isoformat(), "2024-02-29")  # Leap year check!
        self.assertEqual(month_slices[2]["to_date"].isoformat(), "2024-03-10")

        # Day slices
        day_slices = period_slices(datetime(2024, 2, 28).date(), datetime(2024, 3, 2).date(), "day")
        self.assertEqual(len(day_slices), 4)
        self.assertEqual([s["label"] for s in day_slices], ["2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02"])


if __name__ == "__main__":
    unittest.main()
