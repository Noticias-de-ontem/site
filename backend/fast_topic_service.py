import os
import time
from datetime import date
from urllib.parse import quote

import requests


OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "").strip().rstrip("/")
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "noticias-ontem-captures-v1").strip()
OPENSEARCH_META_INDEX = os.environ.get("OPENSEARCH_META_INDEX", f"{OPENSEARCH_INDEX}-meta").strip()
OPENSEARCH_USERNAME = os.environ.get("OPENSEARCH_USERNAME", "").strip()
OPENSEARCH_PASSWORD = os.environ.get("OPENSEARCH_PASSWORD", "").strip()
OPENSEARCH_API_KEY = os.environ.get("OPENSEARCH_API_KEY", "").strip()
OPENSEARCH_VERIFY_SSL = os.environ.get("OPENSEARCH_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
OPENSEARCH_TIMEOUT = int(os.environ.get("OPENSEARCH_TIMEOUT", "20"))
_status_cache = {"loaded_at": 0.0, "value": None}


class FastTopicSearchError(RuntimeError):
    pass


def is_configured():
    return bool(OPENSEARCH_URL and OPENSEARCH_INDEX)


def request_headers():
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if OPENSEARCH_API_KEY:
        headers["Authorization"] = f"ApiKey {OPENSEARCH_API_KEY}"
    return headers


def request_auth():
    if OPENSEARCH_API_KEY or not OPENSEARCH_USERNAME:
        return None
    return (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)


def opensearch_request(method, path, payload=None):
    if not is_configured():
        raise FastTopicSearchError("OpenSearch is not configured")
    response = requests.request(
        method,
        f"{OPENSEARCH_URL}/{path.lstrip('/')}",
        json=payload,
        headers=request_headers(),
        auth=request_auth(),
        timeout=(10, OPENSEARCH_TIMEOUT),
        verify=OPENSEARCH_VERIFY_SSL,
    )
    if response.status_code >= 400:
        raise FastTopicSearchError(f"OpenSearch returned HTTP {response.status_code}")
    return response.json() if response.content else {}


def index_status(force=False):
    now = time.monotonic()
    if not force and _status_cache["value"] is not None and now - _status_cache["loaded_at"] < 60:
        return _status_cache["value"]
    if not is_configured():
        value = {"configured": False, "ready": False, "engine": "arquivo_pt_api"}
    else:
        try:
            payload = opensearch_request("GET", f"{quote(OPENSEARCH_META_INDEX)}/_doc/coverage")
            source = payload.get("_source") or {}
            value = {
                "configured": True,
                "ready": bool(source.get("complete")),
                "engine": "opensearch" if source.get("complete") else "arquivo_pt_api",
                "start_date": source.get("start_date", ""),
                "end_date": source.get("end_date", ""),
                "documents": int(source.get("documents") or 0),
                "indexed_at": source.get("indexed_at", ""),
                "failed_documents": int(source.get("failed_documents") or 0),
            }
        except Exception as exc:
            value = {
                "configured": True,
                "ready": False,
                "engine": "arquivo_pt_api",
                "error": type(exc).__name__,
            }
    _status_cache.update({"loaded_at": now, "value": value})
    return value


def can_answer(from_date, to_date):
    status = index_status()
    return bool(
        status.get("ready")
        and status.get("start_date")
        and status.get("end_date")
        and from_date.isoformat() >= status["start_date"]
        and to_date.isoformat() <= status["end_date"]
    )


def year_slices(from_date, to_date):
    return [
        {
            "year": year,
            "from_date": max(from_date, date(year, 1, 1)),
            "to_date": min(to_date, date(year, 12, 31)),
        }
        for year in range(from_date.year, to_date.year + 1)
    ]


def analyze_topic_fast(analysis, from_date, to_date):
    filters = [{
        "range": {
            "captured_at": {
                "gte": f"{from_date.isoformat()}T00:00:00Z",
                "lte": f"{to_date.isoformat()}T23:59:59Z",
            }
        }
    }]
    if analysis.get("source"):
        filters.append({"term": {"domain": analysis["source"]}})
    payload = {
        "size": 0,
        "track_total_hits": False,
        "query": {
            "bool": {
                "must": [{
                    "simple_query_string": {
                        "query": analysis["query"],
                        "fields": ["title^3", "text"],
                        "default_operator": "and",
                    }
                }],
                "filter": filters,
            }
        },
        "aggs": {
            "years": {
                "date_histogram": {
                    "field": "captured_at",
                    "calendar_interval": "year",
                    "time_zone": "UTC",
                    "min_doc_count": 0,
                    "extended_bounds": {
                        "min": f"{from_date.isoformat()}T00:00:00Z",
                        "max": f"{to_date.isoformat()}T23:59:59Z",
                    },
                }
            }
        },
    }
    response = opensearch_request("POST", f"{quote(OPENSEARCH_INDEX)}/_search", payload)
    buckets = response.get("aggregations", {}).get("years", {}).get("buckets", [])
    counts = {int(str(bucket.get("key_as_string", ""))[:4]): int(bucket.get("doc_count") or 0) for bucket in buckets}
    series = []
    for slice_data in year_slices(from_date, to_date):
        series.append({
            "year": slice_data["year"],
            "from_date": slice_data["from_date"].isoformat(),
            "to_date": slice_data["to_date"].isoformat(),
            "count": counts.get(slice_data["year"], 0),
            "failed": False,
            "method": "opensearch_fulltext_arquivo_pt",
        })
    return {
        **analysis,
        "series": series,
        "total": sum(item["count"] for item in series),
        "complete": True,
        "method": "opensearch_fulltext_arquivo_pt",
    }
