import hashlib
import hmac
import html
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, init_db
from backend.calendar_service import news_item, recommendations_for_day
from backend.fast_topic_service import FastTopicSearchError, index_status
from backend.models import SiteSnapshot, TopicJob
from backend.rate_limit import (
    consume_rate_limit,
    positive_int,
    release_topic_job_slot,
    reserve_topic_job_slot,
    trust_proxy_headers,
)
from backend.schemas import TopicJobCreated, TopicJobInput, TopicJobResponse
from backend.tasks import run_topic_job
from backend.topic_service import load_site_data


ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
DEFAULT_PUBLIC_URL = "https://luisflmaximo.github.io/Noticias-de-ontem-pt"
TOPIC_MAX_ACTIVE_JOBS = positive_int("TOPIC_MAX_ACTIVE_JOBS", 8)
TOPIC_JOB_SLOT_TTL_SECONDS = positive_int("TOPIC_JOB_SLOT_TTL_SECONDS", 7200)
TOPIC_JOB_STALE_SECONDS = positive_int("TOPIC_JOB_STALE_SECONDS", 7200)
RATE_LIMIT_WINDOW_SECONDS = positive_int("RATE_LIMIT_WINDOW_SECONDS", 60)
TOPIC_CREATE_RATE_LIMIT = positive_int("TOPIC_CREATE_RATE_LIMIT", 5)
TOPIC_CREATE_GLOBAL_RATE_LIMIT = positive_int("TOPIC_CREATE_GLOBAL_RATE_LIMIT", 30)
TOPIC_POLL_RATE_LIMIT = positive_int("TOPIC_POLL_RATE_LIMIT", 120)
TOPIC_POLL_GLOBAL_RATE_LIMIT = positive_int("TOPIC_POLL_GLOBAL_RATE_LIMIT", 600)
CALENDAR_RATE_LIMIT = positive_int("CALENDAR_RATE_LIMIT", 60)
CALENDAR_GLOBAL_RATE_LIMIT = positive_int("CALENDAR_GLOBAL_RATE_LIMIT", 300)
NEWS_RATE_LIMIT = positive_int("NEWS_RATE_LIMIT", 120)
NEWS_GLOBAL_RATE_LIMIT = positive_int("NEWS_GLOBAL_RATE_LIMIT", 600)
ADMIN_RATE_LIMIT = positive_int("ADMIN_RATE_LIMIT", 10)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        bundled = load_site_data()
        existing = db.get(SiteSnapshot, 1)
        bundled_generated_at = str(bundled.get("generated_at") or "")
        if bundled and (not existing or bundled_generated_at > (existing.generated_at or "")):
            snapshot = existing or SiteSnapshot(id=1, payload_json="{}")
            snapshot.generated_at = bundled_generated_at
            snapshot.payload_json = json.dumps(bundled, ensure_ascii=False, separators=(",", ":"))
            db.add(snapshot)
            db.commit()
    yield


app = FastAPI(title="Notícias de Ontem API", version="1.0.0", lifespan=lifespan)

cors_origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


def database():
    with SessionLocal() as db:
        yield db


def request_identity(request: Request):
    if trust_proxy_headers():
        forwarded = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded:
            return forwarded.split(",")[-1].strip()
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, scope: str, limit: int, global_limit: int | None = None):
    identity = request_identity(request)
    decisions = [
        (scope, consume_rate_limit(scope, identity, limit, RATE_LIMIT_WINDOW_SECONDS)),
    ]
    if global_limit is not None:
        decisions.append(
            (
                f"{scope}:global",
                consume_rate_limit(f"{scope}:global", "all", global_limit, RATE_LIMIT_WINDOW_SECONDS),
            )
        )
    for _, decision in decisions:
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many requests; try again later",
                headers={
                    "Retry-After": str(decision.retry_after),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )


def expire_stale_topic_jobs(db: Session):
    cutoff = utc_now() - timedelta(seconds=TOPIC_JOB_STALE_SECONDS)
    stale_jobs = list(
        db.scalars(
            select(TopicJob).where(
                TopicJob.status.in_(["queued", "running"]),
                TopicJob.updated_at < cutoff,
            )
        )
    )
    if not stale_jobs:
        return
    for job in stale_jobs:
        job.status = "failed"
        job.progress = min(int(job.progress or 0), 99)
        job.error = "Analysis expired before completion"
    db.commit()
    for job in stale_jobs:
        release_topic_job_slot(job.id)


def active_topic_job_count(db: Session):
    return int(
        db.scalar(
            select(func.count(TopicJob.id)).where(TopicJob.status.in_(["queued", "running"]))
        )
        or 0
    )


def utc_now():
    return datetime.now(timezone.utc)


def aware(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def job_payload(job):
    result = json.loads(job.result_json) if job.result_json else None
    return TopicJobResponse(
        id=job.id,
        status=job.status,
        progress=job.progress,
        result=result,
        error=job.error,
    )


def current_site_data(db):
    snapshot = db.get(SiteSnapshot, 1)
    if snapshot:
        try:
            return json.loads(snapshot.payload_json)
        except Exception:
            pass
    return load_site_data()


def public_site_url():
    return (os.environ.get("SITE_PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")


def absolute_site_url(path=""):
    return f"{public_site_url()}/{str(path or '').lstrip('/')}"


def story_title(item):
    title = str(item.get("title") or "Notícia preservada").strip()
    year = str(item.get("original_year") or "").strip()
    if year and not re.search(rf"\b{re.escape(year)}\b", title):
        return f"{title} em {year}"
    return title


def find_snapshot_item(site_payload, page_id):
    for item in site_payload.get("all", []):
        if str(item.get("page_id") or "") == page_id:
            return item
    recommendations = (site_payload.get("calendar") or {}).get("recommendations_by_day") or {}
    for items in recommendations.values():
        for item in items or []:
            if str(item.get("page_id") or "") == page_id:
                return item
    return None


def render_story_page(item):
    template_path = SITE_DIR / "index.html"
    if not template_path.exists():
        raise HTTPException(status_code=503, detail="Website template unavailable")
    page_id = str(item.get("page_id") or "").strip()
    title = story_title(item)
    description = str(item.get("summary") or f"Consulte {title} e a fonte preservada no Arquivo.pt.").strip()
    canonical = absolute_site_url(f"noticia/{page_id}/")
    image_path = str(item.get("detail_image") or item.get("image") or item.get("banner_image") or "assets/icon.png")
    image = absolute_site_url(image_path)
    should_index = str(item.get("status") or "").lower() != "pending" and bool(item.get("source_url"))
    robots = (
        "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"
        if should_index
        else "noindex,follow"
    )
    structured = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": description,
        "url": canonical,
        "mainEntityOfPage": canonical,
        "image": [image],
        "datePublished": item.get("date"),
        "articleSection": item.get("category"),
        "inLanguage": "pt-PT",
        "isBasedOn": item.get("source_url") or "https://arquivo.pt/",
        "publisher": {
            "@type": "Organization",
            "name": "Notícias de Ontem",
            "url": absolute_site_url(),
        },
    }
    structured = {key: value for key, value in structured.items() if value}
    escaped_title = html.escape(f"{title} | Notícias de Ontem", quote=True)
    escaped_description = html.escape(description, quote=True)
    escaped_canonical = html.escape(canonical, quote=True)
    escaped_image = html.escape(image, quote=True)
    structured_json = json.dumps(structured, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    seo = "\n".join(
        [
            "    <!-- SEO:START -->",
            f"    <title>{escaped_title}</title>",
            f'    <meta name="description" content="{escaped_description}">',
            f'    <meta name="robots" content="{robots}">',
            '    <meta name="author" content="Notícias de Ontem">',
            '    <meta name="theme-color" content="#ffffff">',
            f'    <link rel="canonical" href="{escaped_canonical}">',
            '    <meta property="og:site_name" content="Notícias de Ontem">',
            '    <meta property="og:type" content="article">',
            '    <meta property="og:locale" content="pt_PT">',
            f'    <meta property="og:title" content="{escaped_title}">',
            f'    <meta property="og:description" content="{escaped_description}">',
            f'    <meta property="og:url" content="{escaped_canonical}">',
            f'    <meta property="og:image" content="{escaped_image}">',
            f'    <meta property="og:image:alt" content="{escaped_title}">',
            '    <meta name="twitter:card" content="summary_large_image">',
            f'    <meta name="twitter:title" content="{escaped_title}">',
            f'    <meta name="twitter:description" content="{escaped_description}">',
            f'    <meta name="twitter:image" content="{escaped_image}">',
            f'    <script type="application/ld+json" id="structured-data">{structured_json}</script>',
            "    <!-- SEO:END -->",
        ]
    )
    page = template_path.read_text(encoding="utf-8")
    page = re.sub(
        r"\s*<!-- SEO:START -->.*?<!-- SEO:END -->",
        f"\n{seo}",
        page,
        count=1,
        flags=re.DOTALL,
    )
    return (
        page
        .replace('href="assets/', 'href="../../assets/')
        .replace('src="assets/', 'src="../../assets/')
        .replace('href="styles.css?v=20260903a"', 'href="../../styles.css?v=20260903a"')
        .replace('src="app.js?v=20260903a"', 'src="../../app.js?v=20260903a"')
        .replace('href="inicio/"', 'href="../../inicio/"')
        .replace('href="calendário/"', 'href="../../calendario/"')
        .replace('href="temas/"', 'href="../../temas/"')
        .replace('href="documentação/"', 'href="../../documentacao/"')
    )


def validate_coverage(payload, site_data):
    config = site_data.get("topic_search", {})
    sources = set(config.get("sources") or [])
    global_minimum = config.get("min_date", "1996-01-01")
    global_maximum = config.get("max_date", utc_now().date().isoformat())
    common_minimum = global_minimum
    common_maximum = global_maximum
    for analysis in payload.analyses:
        if analysis.source and analysis.source not in sources:
            raise HTTPException(status_code=422, detail=f"Unknown source: {analysis.source}")
        metadata = (config.get("source_metadata") or {}).get(analysis.source, {})
        common_minimum = max(common_minimum, metadata.get("analysis_start") or global_minimum)
        common_maximum = min(common_maximum, metadata.get("analysis_end") or global_maximum)
    if payload.from_date.isoformat() < common_minimum or payload.to_date.isoformat() > common_maximum:
        raise HTTPException(
            status_code=422,
            detail={"message": "Date range is outside preserved coverage", "minimum": common_minimum, "maximum": common_maximum},
        )


@app.get("/api/health")
def health():
    return {"status": "ok", "source": "Arquivo.pt"}


@app.get("/api/coverage")
def coverage(db: Session = Depends(database)):
    config = current_site_data(db).get("topic_search", {})
    return {
        "min_date": config.get("min_date"),
        "max_date": config.get("max_date"),
        "sources": config.get("sources", []),
        "source_metadata": config.get("source_metadata", {}),
        "updated_at": config.get("coverage_updated_at", ""),
        "coverage_basis": config.get("coverage_basis", ""),
        "coverage_precise": bool(config.get("coverage_precise")),
    }


@app.get("/api/metrics")
def metrics(db: Session = Depends(database)):
    return current_site_data(db).get("metrics", {})


@app.get("/api/search-status")
def search_status():
    return index_status()


@app.get("/api/site-data")
def site_data(db: Session = Depends(database)):
    return current_site_data(db)


@app.get("/api/calendar-recommendations")
def calendar_recommendations(
    request: Request,
    selected_date: str,
    source: str = "",
    limit: int = 25,
    db: Session = Depends(database),
):
    enforce_rate_limit(request, "calendar", CALENDAR_RATE_LIMIT, CALENDAR_GLOBAL_RATE_LIMIT)
    try:
        parsed_date = date.fromisoformat(selected_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid calendar date") from exc
    sources = set(current_site_data(db).get("topic_search", {}).get("sources") or [])
    if source and source not in sources:
        raise HTTPException(status_code=422, detail=f"Unknown source: {source}")
    try:
        return recommendations_for_day(
            parsed_date.strftime("%m-%d"),
            parsed_date.year,
            source,
            min(max(limit, 1), 25),
        )
    except FastTopicSearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/news/{page_id}")
def dynamic_news(request: Request, page_id: str):
    enforce_rate_limit(request, "news", NEWS_RATE_LIMIT, NEWS_GLOBAL_RATE_LIMIT)
    try:
        item = news_item(page_id)
    except FastTopicSearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Story not found")
    return item


@app.get("/noticia/{page_id}/", response_class=HTMLResponse)
def public_news_page(page_id: str, db: Session = Depends(database)):
    if not re.fullmatch(r"[a-z0-9-]+", page_id):
        raise HTTPException(status_code=404, detail="Story not found")
    site_payload = current_site_data(db)
    item = find_snapshot_item(site_payload, page_id)
    if not item:
        try:
            item = news_item(page_id)
        except FastTopicSearchError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Story not found")
    return HTMLResponse(
        render_story_page(item),
        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=3600"},
    )


@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(database)):
    site_payload = current_site_data(db)
    generated_date = str(site_payload.get("generated_at") or utc_now().date().isoformat())[:10]
    urls = [
        absolute_site_url("inicio/"),
        absolute_site_url("calendario/"),
        absolute_site_url("temas/"),
        absolute_site_url("documentacao/"),
    ]
    for item in site_payload.get("all", []):
        if str(item.get("status") or "").lower() != "published":
            continue
        page_id = str(item.get("page_id") or "")
        if re.fullmatch(r"[a-z0-9-]+", page_id):
            urls.append(absolute_site_url(f"noticia/{page_id}/"))
    entries = "\n".join(
        f"  <url><loc>{html.escape(url)}</loc><lastmod>{generated_date}</lastmod></url>"
        for url in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )
    return Response(xml, media_type="application/xml")


@app.get("/robots.txt")
def robots():
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /*?id=",
            f"Sitemap: {absolute_site_url('sitemap.xml')}",
            "",
        ]
    )
    return Response(content, media_type="text/plain")


@app.post("/api/admin/site-data")
def update_site_data(
    request: Request,
    payload: dict = Body(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(database),
):
    enforce_rate_limit(request, "admin-site-sync", ADMIN_RATE_LIMIT)
    expected = os.environ.get("SITE_SYNC_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected:
        raise HTTPException(status_code=503, detail="Site synchronization is not configured")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid synchronization token")
    if not isinstance(payload.get("topic_search"), dict) or not isinstance(payload.get("metrics"), dict):
        raise HTTPException(status_code=422, detail="Invalid site data payload")
    snapshot = db.get(SiteSnapshot, 1) or SiteSnapshot(id=1, payload_json="{}")
    snapshot.generated_at = str(payload.get("generated_at") or utc_now().isoformat())
    snapshot.payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    db.add(snapshot)
    db.commit()
    return {"status": "updated", "generated_at": snapshot.generated_at}


@app.post("/api/topic-analyses", response_model=TopicJobCreated, status_code=202)
def create_topic_job(request: Request, payload: TopicJobInput, db: Session = Depends(database)):
    enforce_rate_limit(request, "topic-create", TOPIC_CREATE_RATE_LIMIT, TOPIC_CREATE_GLOBAL_RATE_LIMIT)
    validate_coverage(payload, current_site_data(db))
    canonical = payload.model_dump(mode="json")
    cache_identity = {
        "analyses": [
            {"query": analysis["query"], "source": analysis.get("source", "")}
            for analysis in canonical["analyses"]
        ],
        "from_date": canonical["from_date"],
        "to_date": canonical["to_date"],
    }
    fingerprint = hashlib.sha256(
        json.dumps(cache_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    now = utc_now()
    cached = db.scalar(
        select(TopicJob)
        .where(TopicJob.fingerprint == fingerprint, TopicJob.status == "completed")
        .order_by(desc(TopicJob.updated_at))
    )
    if cached and aware(cached.expires_at) > now:
        return TopicJobCreated(id=cached.id, status=cached.status, progress=100, cached=True)

    expire_stale_topic_jobs(db)
    if active_topic_job_count(db) >= TOPIC_MAX_ACTIVE_JOBS:
        raise HTTPException(
            status_code=429,
            detail="Too many analyses are already running; try again later",
            headers={"Retry-After": "60"},
        )

    job_id = str(uuid.uuid4())
    if not reserve_topic_job_slot(job_id, TOPIC_MAX_ACTIVE_JOBS, TOPIC_JOB_SLOT_TTL_SECONDS):
        raise HTTPException(
            status_code=429,
            detail="Too many analyses are already running; try again later",
            headers={"Retry-After": "60"},
        )

    job = TopicJob(
        id=job_id,
        fingerprint=fingerprint,
        status="queued",
        progress=0,
        request_json=json.dumps(canonical, ensure_ascii=False),
        expires_at=now + timedelta(days=int(os.environ.get("TOPIC_CACHE_DAYS", "30"))),
    )
    try:
        db.add(job)
        db.commit()
        try:
            run_topic_job.delay(job.id)
        except Exception as exc:
            job.status = "failed"
            job.error = f"Queue unavailable: {type(exc).__name__}"
            db.commit()
            release_topic_job_slot(job.id)
            raise HTTPException(status_code=503, detail="Analysis queue is unavailable") from exc
    except Exception:
        release_topic_job_slot(job.id)
        raise
    return TopicJobCreated(id=job.id, status=job.status, progress=job.progress, cached=False)


@app.get("/api/topic-analyses/{job_id}", response_model=TopicJobResponse)
def get_topic_job(request: Request, job_id: str, db: Session = Depends(database)):
    enforce_rate_limit(request, "topic-poll", TOPIC_POLL_RATE_LIMIT, TOPIC_POLL_GLOBAL_RATE_LIMIT)
    job = db.get(TopicJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return job_payload(job)


if SITE_DIR.exists():
    app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
