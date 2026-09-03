import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
SITE_DATA_FILE = ROOT / "site" / "data" / "news.json"
ARQUIVO_TEXTSEARCH_URL = "https://arquivo.pt/textsearch"
EXACT_SLICE_LIMIT = 1800
REQUEST_TIMEOUT = int(os.environ.get("ARQUIVO_TOPIC_TIMEOUT", "45"))
MIN_REQUEST_INTERVAL = float(os.environ.get("ARQUIVO_TOPIC_MIN_INTERVAL", "0.31"))
_request_lock = threading.Lock()
_next_request_at = 0.0


class TopicVerificationError(RuntimeError):
    def __init__(self, message, code="request_failed"):
        super().__init__(message)
        self.code = code


@dataclass
class TopicProbeBudget:
    maximum: int
    used: int = 0

    def consume(self):
        if self.used >= self.maximum:
            raise TopicVerificationError("Topic verification limit reached", "verification_limit")
        self.used += 1


@lru_cache(maxsize=1)
def load_site_data():
    try:
        return json.loads(SITE_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"topic_search": {"sources": [], "source_metadata": {}}}


def topic_config():
    return load_site_data().get("topic_search", {})


def source_hosts(source):
    if not source:
        return []
    metadata = topic_config().get("source_metadata", {}).get(source, {})
    configured = metadata.get("search_hosts")
    hosts = configured if isinstance(configured, list) and configured else [f"www.{source}", source]
    return list(dict.fromkeys(str(host).strip() for host in hosts if str(host).strip()))


def parse_estimate(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return int(digits or 0)


def timestamp_for(value, end_of_day=False):
    if isinstance(value, str) and len(value) == 14 and value.isdigit():
        return value
    if isinstance(value, str):
        value = date.fromisoformat(value)
    moment = datetime.combine(value, datetime_time.max if end_of_day else datetime_time.min, tzinfo=timezone.utc)
    return moment.strftime("%Y%m%d%H%M%S")


def timestamp_datetime(value):
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def probe(session, query, source, from_timestamp, to_timestamp, offset, budget):
    params = [
        ("q", query),
        ("from", from_timestamp),
        ("to", to_timestamp),
        ("maxItems", "1"),
        ("offset", str(offset)),
        ("dedupValue", "0"),
    ]
    params.extend(("siteSearch", host) for host in source_hosts(source))
    last_error = None
    for attempt in range(3):
        budget.consume()
        try:
            global _next_request_at
            with _request_lock:
                delay = max(0.0, _next_request_at - time.monotonic())
                if delay:
                    time.sleep(delay)
                _next_request_at = time.monotonic() + MIN_REQUEST_INTERVAL
            response = session.get(
                ARQUIVO_TEXTSEARCH_URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=(10, REQUEST_TIMEOUT),
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("response_items") or payload.get("responseItems") or []
            return {
                "has_result": bool(items),
                "estimate": parse_estimate(payload.get("estimated_nr_results") or payload.get("estimatedNrResults")),
            }
        except TopicVerificationError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.45 * (attempt + 1))
    raise TopicVerificationError(f"Arquivo.pt request failed: {type(last_error).__name__}")


def first_empty_offset(session, query, source, from_timestamp, to_timestamp, low_present, high_empty, budget):
    low = low_present
    high = high_empty
    while high - low > 1:
        middle = (low + high) // 2
        result = probe(session, query, source, from_timestamp, to_timestamp, middle, budget)
        if result["has_result"]:
            low = middle
        else:
            high = middle
    return high


def verified_interval_count(session, query, source, from_timestamp, to_timestamp, budget):
    first = probe(session, query, source, from_timestamp, to_timestamp, 0, budget)
    if not first["has_result"]:
        return 0

    hint = max(0, first["estimate"])
    if 0 < hint <= EXACT_SLICE_LIMIT:
        before = first if hint == 1 else probe(
            session, query, source, from_timestamp, to_timestamp, hint - 1, budget
        )
        after = probe(session, query, source, from_timestamp, to_timestamp, hint, budget)
        if before["has_result"] and not after["has_result"]:
            return hint
        if not before["has_result"]:
            return first_empty_offset(
                session, query, source, from_timestamp, to_timestamp, 0, hint - 1, budget
            )
        limit = after if hint == EXACT_SLICE_LIMIT else probe(
            session, query, source, from_timestamp, to_timestamp, EXACT_SLICE_LIMIT, budget
        )
        if limit["has_result"]:
            return None
        return first_empty_offset(
            session, query, source, from_timestamp, to_timestamp, hint, EXACT_SLICE_LIMIT, budget
        )

    limit = probe(session, query, source, from_timestamp, to_timestamp, EXACT_SLICE_LIMIT, budget)
    if limit["has_result"]:
        return None
    return first_empty_offset(
        session, query, source, from_timestamp, to_timestamp, 0, EXACT_SLICE_LIMIT, budget
    )


def count_interval_exactly(session, query, source, from_timestamp, to_timestamp, budget):
    direct = verified_interval_count(session, query, source, from_timestamp, to_timestamp, budget)
    if direct is not None:
        return direct

    start = timestamp_datetime(from_timestamp)
    end = timestamp_datetime(to_timestamp)
    if start >= end:
        raise TopicVerificationError("Arquivo.pt result window could not be divided")
    middle = start + ((end - start) / 2)
    middle = middle.replace(microsecond=0)
    left = count_interval_exactly(
        session,
        query,
        source,
        start.strftime("%Y%m%d%H%M%S"),
        middle.strftime("%Y%m%d%H%M%S"),
        budget,
    )
    right = count_interval_exactly(
        session,
        query,
        source,
        (middle + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
        end.strftime("%Y%m%d%H%M%S"),
        budget,
    )
    return left + right


def year_slices(from_date, to_date):
    slices = []
    for year in range(from_date.year, to_date.year + 1):
        start = max(from_date, date(year, 1, 1))
        end = min(to_date, date(year, 12, 31))
        slices.append({"year": year, "from_date": start, "to_date": end})
    return slices


def analyze_topic(analysis, from_date, to_date, budget, progress_callback=None):
    series = []
    with requests.Session() as session:
        for slice_data in year_slices(from_date, to_date):
            try:
                count = count_interval_exactly(
                    session,
                    analysis["query"],
                    analysis.get("source", ""),
                    timestamp_for(slice_data["from_date"]),
                    timestamp_for(slice_data["to_date"], end_of_day=True),
                    budget,
                )
                item = {
                    "year": slice_data["year"],
                    "from_date": slice_data["from_date"].isoformat(),
                    "to_date": slice_data["to_date"].isoformat(),
                    "count": count,
                    "failed": False,
                }
            except TopicVerificationError as exc:
                item = {
                    "year": slice_data["year"],
                    "from_date": slice_data["from_date"].isoformat(),
                    "to_date": slice_data["to_date"].isoformat(),
                    "count": None,
                    "failed": True,
                    "error_code": exc.code,
                }
            series.append(item)
            if progress_callback:
                progress_callback()

    return {
        **analysis,
        "series": series,
        "total": sum(item["count"] for item in series if isinstance(item.get("count"), int)),
        "complete": not any(item.get("failed") for item in series),
    }
