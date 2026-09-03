import hashlib
from urllib.parse import quote

from backend.fast_topic_service import OPENSEARCH_INDEX, FastTopicSearchError, index_status, opensearch_request


def require_ready_index():
    status = index_status()
    if not status.get("ready"):
        raise FastTopicSearchError("The Arquivo.pt search index is not complete")


def page_id_for_key(original_url_key):
    return f"noticia-{original_url_key}"


def screenshot_url(arquivo_url):
    return f"https://arquivo.pt/screenshot/?url={quote(arquivo_url, safe='')}" if arquivo_url else ""


def item_from_source(source):
    original_url = str(source.get("original_url") or "").strip()
    original_url_key = str(source.get("original_url_key") or "").strip()
    if not original_url_key and original_url:
        original_url_key = hashlib.sha256(original_url.encode("utf-8")).hexdigest()
    captured_at = str(source.get("captured_at") or "")
    domain = str(source.get("domain") or "").strip()
    year = captured_at[:4]
    arquivo_url = str(source.get("arquivo_url") or "").strip()
    title = str(source.get("title") or "").strip() or "Noticia preservada"
    return {
        "id": str(source.get("capture_id") or original_url_key),
        "page_id": page_id_for_key(original_url_key),
        "date": captured_at[:10],
        "original_year": year,
        "title": title,
        "summary": f"Noticia publicada por {domain or 'uma fonte jornalistica'} em {year}, preservada pelo Arquivo.pt.",
        "summary_en": f"Story published by {domain or 'a news source'} in {year} and preserved by Arquivo.pt.",
        "category": "Arquivo.pt",
        "domain": domain,
        "source_url": arquivo_url,
        "original_url": original_url,
        "detail_image": screenshot_url(arquivo_url),
        "archive_credit": "Arquivo.pt",
    }


def balanced_by_source(items, limit):
    grouped = {}
    source_order = []
    for item in items:
        source = item.get("domain") or "arquivo.pt"
        if source not in grouped:
            grouped[source] = []
            source_order.append(source)
        grouped[source].append(item)
    output = []
    while len(output) < limit and any(grouped.values()):
        for source in source_order:
            if grouped[source] and len(output) < limit:
                output.append(grouped[source].pop(0))
    return output


def recommendations_for_day(month_day, selected_year, source="", limit=25):
    require_ready_index()
    filters = [{"term": {"month_day": month_day}}]
    if source:
        filters.append({"term": {"domain": source}})
    payload = {
        "size": 150 if source else 500,
        "track_total_hits": False,
        "_source": [
            "capture_id",
            "captured_at",
            "domain",
            "title",
            "original_url",
            "original_url_key",
            "arquivo_url",
        ],
        "query": {"bool": {"filter": filters}},
        "collapse": {"field": "original_url_key"},
        "sort": [{"captured_at": {"order": "desc"}}, {"capture_id": {"order": "asc"}}],
    }
    response = opensearch_request("POST", f"{quote(OPENSEARCH_INDEX)}/_search", payload)
    hits = [item_from_source(hit.get("_source") or {}) for hit in response.get("hits", {}).get("hits", [])]
    hits.sort(
        key=lambda item: (
            int(item.get("original_year") or 0) <= selected_year,
            int(item.get("original_year") or 0),
        ),
        reverse=True,
    )
    selected = hits[:limit] if source else balanced_by_source(hits, limit)
    return {
        "date_key": month_day,
        "selected_year": selected_year,
        "source": source,
        "count": len(selected),
        "items": selected,
        "method": "opensearch_arquivo_pt_captures",
    }


def news_item(page_id):
    require_ready_index()
    prefix = "noticia-"
    original_url_key = page_id[len(prefix):] if page_id.startswith(prefix) else ""
    if len(original_url_key) != 64:
        return None
    payload = {
        "size": 1,
        "query": {"term": {"original_url_key": original_url_key}},
        "sort": [{"captured_at": {"order": "desc"}}],
    }
    response = opensearch_request("POST", f"{quote(OPENSEARCH_INDEX)}/_search", payload)
    hits = response.get("hits", {}).get("hits", [])
    return item_from_source(hits[0].get("_source") or {}) if hits else None
