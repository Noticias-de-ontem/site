import argparse
import hashlib
import gzip
import json
import os
import re
import sys
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


MANIFEST_URL = "https://arquivo.pt/datasets/cdxj/"
STATE_FILE = "arquivo_cdxj_state.json"
DEFAULT_OUTPUT_DIR = "arquivo_cdxj"
RESUME_ANCHOR_BYTES = 64 * 1024

NEWS_DOMAINS = [
    "publico.pt",
    "expresso.pt",
    "cmjornal.pt",
    "sabado.pt",
    "rtp.pt",
    "observador.pt",
    "jn.pt",
    "dn.pt",
    "sicnoticias.pt",
    "noticiasaominuto.com",
    "record.pt",
    "ojogo.pt",
    "abola.pt",
    "caras.pt",
    "flash.pt",
    "tv7dias.pt",
    "holofote.pt",
    "selfie.iol.pt",
    "lux.iol.pt",
    "nit.pt",
    "timeout.pt",
    "blitz.pt",
    "mag.sapo.pt",
    "visao.pt",
    "exameinformatica.pt",
    "activa.pt",
    "maxima.pt",
]

NEWS_DOMAIN_HOST_ALIASES = {
    "expresso.pt": {"expresso.sapo.pt"},
    "sicnoticias.pt": {"sicnoticias.sapo.pt"},
    "caras.pt": {"caras.sapo.pt"},
    "blitz.pt": {"blitz.sapo.pt", "blitz.aeiou.pt"},
}

STATIC_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".mp3", ".avi", ".mov", ".pdf",
    ".zip", ".rar", ".xml", ".json", ".rss",
)

CDXJ_SUFFIXES = (
    ".cdxj",
    ".cdxj_filtered",
    ".cdxj.gz",
    ".cdxj_filtered.gz",
    ".jsonl",
    ".jsonl.gz",
    ".ndjson",
    ".ndjson.gz",
)


class RemoteSourceUnavailable(RuntimeError):
    """A remote CDXJ collection was removed or is no longer published."""


class ResumeValidationUnavailable(RuntimeError):
    """The source could not be validated safely for an incremental update."""


class OutputFileCache:
    """Reuses buffered daily output files instead of reopening them per record."""

    def __init__(self, max_open=128):
        self.max_open = max_open
        self.handles = OrderedDict()

    def write(self, path, text):
        path = Path(path)
        handle = self.handles.pop(path, None)
        if handle is None:
            handle = open(path, "a", encoding="utf-8", buffering=1024 * 1024)
        handle.write(text)
        self.handles[path] = handle
        while len(self.handles) > self.max_open:
            _, old_handle = self.handles.popitem(last=False)
            old_handle.flush()
            old_handle.close()

    def close(self):
        for handle in self.handles.values():
            handle.flush()
            handle.close()
        self.handles.clear()

    def flush(self):
        for handle in self.handles.values():
            handle.flush()


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def parse_datetime_value(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def source_key_for(source):
    return source.get("url") or source.get("path") or source["name"]


def positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def source_size_from_signature(signature):
    if not isinstance(signature, dict):
        return 0
    if signature.get("type") == "local":
        return positive_int(signature.get("size"))
    return positive_int(signature.get("content_length"))


def source_is_compressed(source):
    return bool(source.get("path") and str(source["path"]).lower().endswith(".gz"))


def source_signature(source):
    if source.get("path"):
        path = Path(source["path"])
        stat = path.stat()
        return {
            "type": "local",
            "path": str(path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
        }

    url = source["url"]
    signature = {
        "type": "remote",
        "url": url,
    }
    try:
        response = requests.head(url, headers={"Accept-Encoding": "identity"}, allow_redirects=True, timeout=(10, 30))
        if response.status_code >= 400:
            response.raise_for_status()
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        content_length = response.headers.get("Content-Length")
        if etag:
            signature["etag"] = etag
        if last_modified:
            signature["last_modified"] = last_modified
            modified_at = parse_datetime_value(last_modified)
            if modified_at:
                signature["modified_at"] = modified_at.replace(microsecond=0).isoformat()
        if content_length:
            signature["content_length"] = content_length
    except requests.exceptions.RequestException as exc:
        signature["unverified"] = exc.__class__.__name__
    return signature


def legacy_source_seems_modified(previous, signature):
    processed_at = parse_datetime_value(previous.get("processed_at"))
    modified_at = parse_datetime_value(signature.get("modified_at") or signature.get("last_modified"))
    return bool(processed_at and modified_at and modified_at > processed_at)


def signatures_match(prev, curr):
    if not prev or not curr:
        return False
    if prev.get("type") != curr.get("type"):
        return False
    if prev.get("type") == "local":
        return (
            prev.get("size") == curr.get("size")
            and prev.get("mtime_ns") == curr.get("mtime_ns")
        )
    
    # Remote source
    prev_length = positive_int(prev.get("content_length"))
    curr_length = positive_int(curr.get("content_length"))
    if prev_length and curr_length and prev_length != curr_length:
        return False

    prev_etag = prev.get("etag", "")
    curr_etag = curr.get("etag", "")
    if prev_etag and curr_etag:
        p_norm = prev_etag.strip('"').replace("-gzip", "")
        c_norm = curr_etag.strip('"').replace("-gzip", "")
        if p_norm == c_norm:
            return True
            
    prev_mod = prev.get("modified_at") or prev.get("last_modified")
    curr_mod = curr.get("modified_at") or curr.get("last_modified")
    if prev_mod and curr_mod and prev_mod == curr_mod:
        return True
        
    return False


def signature_has_fingerprint(signature):
    return any(
        key in signature
        for key in ("size", "mtime_ns", "etag", "content_length", "modified_at", "last_modified")
    )


def parse_content_range(value):
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", str(value or "").strip(), re.IGNORECASE)
    if not match:
        return None
    return {
        "start": int(match.group(1)),
        "end": int(match.group(2)),
        "total": positive_int(match.group(3)),
    }


def read_remote_range(url, start, end):
    """Read one bounded byte range; return None when Range is not honoured."""
    if start < 0 or end < start:
        return None
    try:
        with requests.get(
            url,
            headers={"Accept-Encoding": "identity", "Range": f"bytes={start}-{end}"},
            stream=True,
            timeout=(20, 60),
        ) as response:
            if response.status_code == 416:
                return None
            if response.status_code in (404, 410):
                raise RemoteSourceUnavailable(
                    f"A coleção remota deixou de estar disponível ({response.status_code}): {url}"
                )
            if response.status_code != 206:
                return None
            content_range = parse_content_range(response.headers.get("Content-Range"))
            expected_length = end - start + 1
            if not content_range or content_range["start"] != start:
                return None
            if content_range["end"] > end:
                return None

            data = bytearray()
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if chunk:
                    data.extend(chunk)
                    if len(data) > expected_length:
                        return None
            if len(data) != content_range["end"] - start + 1:
                return None
            return bytes(data), content_range, {
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
    except (requests.exceptions.RequestException, ConnectionResetError, OSError):
        raise


def probe_remote_size(url):
    """Discover a missing remote size without downloading the collection."""
    try:
        with requests.get(
            url,
            headers={"Accept-Encoding": "identity", "Range": "bytes=0-0"},
            stream=True,
            timeout=(20, 60),
        ) as response:
            if response.status_code == 206:
                content_range = parse_content_range(response.headers.get("Content-Range"))
                return content_range["total"] if content_range and content_range["total"] >= 0 else None
            if response.status_code == 200:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        return int(content_length)
                    except ValueError:
                        return None
            return None
    except (requests.exceptions.RequestException, ConnectionResetError, OSError):
        return None


def source_boundary_fingerprint(source, offset):
    """Return a digest of the bytes immediately before an absolute offset."""
    offset = positive_int(offset)
    if offset <= 0 or source_is_compressed(source):
        return None
    start = max(0, offset - RESUME_ANCHOR_BYTES)
    end = offset - 1

    if source.get("path"):
        path = Path(source["path"])
        with open(path, "rb") as handle:
            handle.seek(start)
            data = handle.read(end - start + 1)
        if len(data) != end - start + 1:
            return None
        return {
            "start": start,
            "end": end,
            "sha256": hashlib.sha256(data).hexdigest(),
            "ends_with_newline": data.endswith(b"\n"),
        }

    result = read_remote_range(source["url"], start, end)
    if result is None:
        return None
    data, content_range, response_metadata = result
    if content_range["end"] != end:
        return None
    return {
        "start": start,
        "end": end,
        "sha256": hashlib.sha256(data).hexdigest(),
        "ends_with_newline": data.endswith(b"\n"),
        "content_length": content_range["total"] or None,
        "etag": response_metadata.get("etag"),
        "last_modified": response_metadata.get("last_modified"),
    }


def validate_resume_boundary(source, offset, expected_anchor=None, require_line_boundary=False):
    """Validate Range support and, when available, the saved prefix boundary."""
    try:
        actual = source_boundary_fingerprint(source, offset)
    except (requests.exceptions.RequestException, ConnectionResetError, OSError) as exc:
        raise ResumeValidationUnavailable(str(exc)) from exc
    if not actual:
        return False
    if require_line_boundary and actual.get("ends_with_newline") is not True:
        return False
    if not expected_anchor:
        return True
    return (
        actual.get("start") == expected_anchor.get("start")
        and actual.get("end") == expected_anchor.get("end")
        and actual.get("sha256") == expected_anchor.get("sha256")
    )


def source_from_state_entry(source_key, details):
    signature = details.get("source_signature") if isinstance(details, dict) else None
    signature = signature if isinstance(signature, dict) else {}
    if signature.get("type") == "remote" and signature.get("url"):
        return {"name": details.get("name") or source_key, "url": signature["url"]}
    if signature.get("type") == "local" and signature.get("path"):
        return {"name": details.get("name") or Path(signature["path"]).name, "path": signature["path"]}
    if str(source_key).startswith(("http://", "https://")):
        return {"name": details.get("name") or Path(urlparse(source_key).path).name, "url": source_key}
    return {"name": details.get("name") or Path(str(source_key)).name, "path": source_key}


def completed_source_progress(source_key, details, fetch_anchors=True):
    """Build a resumable position for a source already marked as processed."""
    signature = details.get("source_signature") if isinstance(details, dict) else None
    signature = signature if isinstance(signature, dict) else {}
    source = source_from_state_entry(source_key, details)
    offset = source_size_from_signature(signature)
    progress = {
        "status": "complete",
        "mode": "append_only",
        "bytes_downloaded": offset,
        "scanned": positive_int(details.get("scanned")),
        "written": positive_int(details.get("written")),
        "recorded_at": details.get("processed_at") or utc_now(),
    }

    size_is_known = "size" in signature or "content_length" in signature
    if not offset and not (size_is_known and signature.get("type") == "remote"):
        progress["status"] = "unavailable"
        progress["mode"] = "full_scan_only"
        progress["reason"] = "source_size_not_recorded"
        return progress

    if not offset:
        progress["reason"] = "empty_source"
        progress["anchor_status"] = "not_needed"
        return progress

    if source_is_compressed(source):
        progress["status"] = "unsupported"
        progress["mode"] = "full_scan_only"
        progress["reason"] = "compressed_source_requires_a_decompressed_seek"
        return progress

    existing = details.get("source_progress") if isinstance(details, dict) else None
    existing_anchor = existing.get("anchor") if isinstance(existing, dict) else None
    if existing_anchor:
        progress["anchor"] = existing_anchor
    elif fetch_anchors:
        try:
            anchor = source_boundary_fingerprint(source, offset)
        except (requests.exceptions.RequestException, ConnectionResetError, OSError, RemoteSourceUnavailable) as exc:
            anchor = None
            progress["anchor_error"] = f"{exc.__class__.__name__}: {exc}"
        if anchor:
            progress["anchor"] = anchor
    if not progress.get("anchor"):
        progress["anchor_status"] = "unavailable"
    else:
        progress["anchor_status"] = "recorded"
    return progress


def migrate_processed_state(state, fetch_anchors=True):
    """Add byte positions and boundary anchors to legacy completed entries."""
    if not isinstance(state, dict):
        state = {"processed": {}}
    processed = state.setdefault("processed", {})
    state.setdefault("in_progress", {})
    state.setdefault("failed", {})
    changed = False

    for source_key, details in list(processed.items()):
        if not isinstance(details, dict):
            continue
        signature = details.get("source_signature") if isinstance(details.get("source_signature"), dict) else {}
        if signature.get("type") == "remote" and "content_length" not in signature:
            source = source_from_state_entry(source_key, details)
            current_signature = source_signature(source)
            if "content_length" not in current_signature:
                probed_size = probe_remote_size(source.get("url", ""))
                if probed_size is not None:
                    current_signature["content_length"] = str(probed_size)
            current_size = source_size_from_signature(current_signature)
            processed_at = parse_datetime_value(details.get("processed_at"))
            modified_at = parse_datetime_value(
                current_signature.get("modified_at") or current_signature.get("last_modified")
            )
            if "content_length" in current_signature and (
                not modified_at or not processed_at or modified_at <= processed_at
            ):
                details["source_signature"] = current_signature
                details["signature_recorded_at"] = utc_now()
                changed = True
        progress = completed_source_progress(source_key, details, fetch_anchors=fetch_anchors)
        old_progress = details.get("source_progress")
        if old_progress != progress:
            details["source_progress"] = progress
            changed = True

    if state.get("schema_version") != 2:
        state["schema_version"] = 2
        changed = True
    return state, changed


def incremental_resume_decision(source, previous, signature):
    """Return (decision, offset, reason) for a changed source.

    ``decision`` is True when the saved prefix boundary matches, False when a
    complete rebuild is required, and None when validation could not be
    completed because the source was temporarily unreachable.
    """
    progress = previous.get("source_progress") if isinstance(previous, dict) else None
    if not isinstance(progress, dict) or progress.get("status") != "complete":
        return False, 0, "no_completed_source_progress"
    if progress.get("mode") != "append_only" or source_is_compressed(source):
        return False, 0, "source_does_not_support_append_resume"

    offset = positive_int(progress.get("bytes_downloaded"))
    anchor = progress.get("anchor")
    if not offset or not isinstance(anchor, dict):
        return False, 0, "missing_prefix_anchor"
    if anchor.get("ends_with_newline") is False:
        return False, 0, "prefix_does_not_end_at_line_boundary"

    current_size = source_size_from_signature(signature)
    if current_size and current_size <= offset:
        return False, 0, "source_did_not_grow"

    try:
        valid = validate_resume_boundary(source, offset, expected_anchor=anchor)
    except (ResumeValidationUnavailable, RemoteSourceUnavailable) as exc:
        return None, offset, str(exc)
    if not valid:
        return False, 0, "prefix_boundary_changed"
    return True, offset, "prefix_boundary_matches"


def runtime_source_progress(source, checkpoint_bytes, scanned, written):
    """Create the final durable position, including a cheap boundary digest."""
    offset = positive_int(checkpoint_bytes)
    progress = {
        "status": "complete",
        "mode": "append_only",
        "bytes_downloaded": offset,
        "scanned": positive_int(scanned),
        "written": positive_int(written),
        "recorded_at": utc_now(),
    }
    if source_is_compressed(source):
        progress["status"] = "unsupported"
        progress["mode"] = "full_scan_only"
        progress["reason"] = "compressed_source_requires_a_decompressed_seek"
        return progress
    if offset <= 0:
        progress["status"] = "unavailable"
        progress["mode"] = "full_scan_only"
        progress["reason"] = "source_empty_or_position_unknown"
        return progress
    try:
        anchor = source_boundary_fingerprint(source, offset)
    except (requests.exceptions.RequestException, ConnectionResetError, OSError, RemoteSourceUnavailable) as exc:
        anchor = None
        progress["anchor_error"] = f"{exc.__class__.__name__}: {exc}"
    if anchor:
        progress["anchor"] = anchor
        progress["anchor_status"] = "recorded"
    else:
        progress["anchor_status"] = "unavailable"
    return progress


def checkpoint_for_source(source, signature, checkpoint_bytes, scanned, written, source_coverage):
    return {
        "name": source["name"],
        "checkpoint_version": 2,
        "updated_at": utc_now(),
        "bytes_downloaded": positive_int(checkpoint_bytes),
        "scanned": positive_int(scanned),
        "written": positive_int(written),
        "domain_coverage": source_coverage,
        "source_signature": signature,
    }


def remove_existing_records_for_source(output_dir, source_name):
    root = Path(output_dir)
    if not root.exists():
        return 0

    removed = 0
    touched = 0
    for path in root.glob("*/*.cdxj"):
        temp_path = path.with_name(path.name + ".tmp")
        changed = False
        with open(path, "r", encoding="utf-8", errors="ignore") as src, open(temp_path, "w", encoding="utf-8") as dst:
            for line in src:
                try:
                    record = json.loads(line)
                except Exception:
                    dst.write(line)
                    continue
                if record.get("source_collection") == source_name:
                    removed += 1
                    changed = True
                    continue
                dst.write(line)
        if changed:
            os.replace(temp_path, path)
            touched += 1
        else:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass

    if removed:
        print(f"[CDXJ] Removidas {removed} entradas antigas de {source_name} em {touched} ficheiros.")
    return removed


def discover_remote_collections(manifest_url=MANIFEST_URL):
    response = requests.get(manifest_url, timeout=60)
    response.raise_for_status()
    names = sorted(set(re.findall(r'href="([^"]+\.cdxj(?:_filtered)?)"', response.text)))
    return [
        {
            "name": name,
            "url": manifest_url.rstrip("/") + "/" + name,
        }
        for name in names
    ]


def source_domain(url, domains):
    value = str(url or "").lower()
    separator = value.find("://")
    start = separator + 3 if separator >= 0 else 0
    end_candidates = [index for index in (value.find("/", start), value.find("?", start), value.find("#", start)) if index >= 0]
    host = value[start:min(end_candidates) if end_candidates else len(value)]
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    if not host:
        return ""
    for domain in domains:
        if host == domain or host.endswith(f".{domain}"):
            return domain
        if host in NEWS_DOMAIN_HOST_ALIASES.get(domain, set()):
            return domain
    return ""


def domain_line_pattern(domains):
    markers = set(domains)
    for domain in domains:
        markers.update(NEWS_DOMAIN_HOST_ALIASES.get(domain, set()))
    return re.compile("|".join(re.escape(marker) for marker in sorted(markers, key=len, reverse=True)), re.IGNORECASE)


def update_domain_coverage(coverage, record):
    domain = str(record.get("domain") or "").strip().lower()
    timestamp = re.sub(r"\D", "", str(record.get("timestamp") or ""))
    if not domain or len(timestamp) < 8:
        return
    date = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
    entry = coverage.setdefault(domain, {"first_date": date, "latest_date": date, "records": 0})
    entry["first_date"] = min(entry.get("first_date") or date, date)
    entry["latest_date"] = max(entry.get("latest_date") or date, date)
    entry["records"] = int(entry.get("records") or 0) + 1


def aggregate_state_coverage(state):
    aggregated = {}
    for details in state.get("processed", {}).values():
        if not isinstance(details, dict):
            continue
        for domain, coverage in (details.get("domain_coverage") or {}).items():
            if not isinstance(coverage, dict):
                continue
            first_date = str(coverage.get("first_date") or "")
            latest_date = str(coverage.get("latest_date") or "")
            if not first_date or not latest_date:
                continue
            entry = aggregated.setdefault(domain, {
                "first_date": first_date,
                "latest_date": latest_date,
                "records": 0,
            })
            entry["first_date"] = min(entry["first_date"], first_date)
            entry["latest_date"] = max(entry["latest_date"], latest_date)
            entry["records"] += int(coverage.get("records") or 0)
    state["domain_coverage"] = aggregated
    state["coverage_updated_at"] = utc_now()
    return aggregated


def rebuild_coverage_from_output(output_dir, state, state_file):
    coverage_by_collection = {}
    scanned = 0
    paths = sorted(Path(output_dir).glob("*/*.cdxj"))
    print(f"[CDXJ] A reconstruir cobertura a partir de {len(paths)} ficheiros filtrados...")
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="ignore") as source:
            for line in source:
                scanned += 1
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                collection = str(record.get("source_collection") or "").strip()
                if not collection:
                    continue
                update_domain_coverage(coverage_by_collection.setdefault(collection, {}), record)
                if scanned % 500000 == 0:
                    print(f"[CDXJ] Cobertura: {scanned} registos lidos...")

    processed_by_name = {
        str(details.get("name") or ""): details
        for details in state.get("processed", {}).values()
        if isinstance(details, dict) and details.get("name")
    }
    for collection, coverage in coverage_by_collection.items():
        if collection in processed_by_name:
            processed_by_name[collection]["domain_coverage"] = coverage
    aggregate_state_coverage(state)
    save_json(state_file, state)
    print(f"[CDXJ] Cobertura reconstruida: {scanned} registos, {len(state.get('domain_coverage', {}))} fontes.")


def is_probable_article_url(url):
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return False
    if not path or path == "/":
        return False
    if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
        return False
    exclude = [
        "/opiniao/", "/editorial/", "/tag/", "/tags/", "/autor/", "/author/",
        "/comentarios/", "/page/", "/feed/", "/wp-json/", "/wp-admin/",
        "/comments/", "/blogs/", "/opinion/", "/pesquisa", "/search",
        "/login", "/logout", "/newsletter", "/passatempos/",
    ]
    if any(part in path for part in exclude):
        return False
    include = [
        "/noticia", "/noticias/", "/article/", "/politica/", "/economia/",
        "/desporto/", "/sociedade/", "/cultura/", "/local/", "/insolito/",
        "/gente/", "/bizarro/", "/curioso/", "/famosos/", "/vida/",
        "/champions/", "/mundial/", "/euro/", "/espetaculo/",
        "/entertainment/", "/showbiz/", "/sport/", "/lifestyle/", "/odd/",
        "/weird/", "/bizarre/", "/pais/", "/mundo/", "/musica/", "/cinema/",
        "/televisao/", "/tecnologia/",
    ]
    return (
        path.endswith(".html")
        or ".asp" in path
        or "/jornal/noticia/" in path
        or "/shownews.asp" in path
        or re.search(r"/20\d{2}/\d{1,2}/\d{1,2}/", path)
        or any(part in path for part in include)
    )


def ensure_text_line(line):
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="ignore")
    return str(line)


def parse_cdxj_line(line):
    line = ensure_text_line(line)
    line = line.lstrip("\ufeff").strip()
    if not line or line.startswith("#"):
        return None
    timestamp = ""
    payload = ""
    if line.startswith("{"):
        payload = line
    else:
        parts = line.split(maxsplit=2)
        if len(parts) >= 3:
            timestamp = parts[1]
            payload = parts[2]
    if not payload:
        return None
    try:
        record = json.loads(payload)
    except Exception:
        return None
    if timestamp and not record.get("timestamp") and not record.get("tstamp"):
        record["_cdxj_timestamp"] = timestamp
    return record


def normalized_record(record, start_year, end_year, domains, source_name):
    timestamp = str(record.get("timestamp") or record.get("tstamp") or record.get("_cdxj_timestamp") or "")
    timestamp = re.sub(r"\D", "", timestamp)
    if len(timestamp) < 8:
        return None
    year = int(timestamp[:4])
    if year < start_year or year > end_year:
        return None
    if len(timestamp) == 8:
        timestamp = timestamp + "120000"
    if len(timestamp) < 14:
        return None

    status = str(record.get("status") or record.get("statuscode") or record.get("statusCode") or "")
    if status and status not in {"200", "-"}:
        return None
    mime = str(record.get("mime") or record.get("mimeType") or record.get("mimetype") or "").lower()
    if mime and "html" not in mime and "text/plain" not in mime:
        return None

    url = str(record.get("url") or record.get("originalURL") or record.get("original") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    try:
        domain = source_domain(url, domains)
        if not domain:
            return None
        if not is_probable_article_url(url):
            return None
    except (TypeError, ValueError):
        return None

    return {
        "url": url,
        "timestamp": timestamp[:14],
        "mime": mime or "text/html",
        "status": status or "200",
        "title": str(record.get("title") or "").strip(),
        "digest": str(record.get("digest") or "").strip(),
        "domain": domain,
        "source_collection": source_name,
    }


def output_path_for_record(output_dir, record):
    timestamp = record["timestamp"]
    year = timestamp[:4]
    month_day = f"{timestamp[4:6]}-{timestamp[6:8]}"
    path = Path(output_dir) / year / f"{month_day}.cdxj"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def iter_local_sources(input_dir):
    root = Path(input_dir)
    if not root.exists():
        return []
    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name.endswith(CDXJ_SUFFIXES)
    )
    return [{"name": path.name, "path": str(path)} for path in paths]


def iter_url_lines_with_resume(url, max_retries=15, initial_bytes=0):
    bytes_downloaded = positive_int(initial_bytes)
    retries = 0
    buffer = b""

    while retries < max_retries:
        headers = {"Accept-Encoding": "identity"}
        if bytes_downloaded > 0:
            headers["Range"] = f"bytes={bytes_downloaded}-"
            print(f"[CDXJ] A retomar download de {url} a partir do byte {bytes_downloaded} (Tentativa {retries + 1}/{max_retries})...")
        else:
            print(f"[CDXJ] A iniciar download de {url}...")

        try:
            with requests.get(url, headers=headers, stream=True, timeout=(20, 60)) as response:
                if response.status_code == 416:
                    if buffer:
                        yield buffer.decode("utf-8", errors="ignore"), bytes_downloaded
                    return

                if response.status_code in (404, 410):
                    raise RemoteSourceUnavailable(
                        f"A coleção remota deixou de estar disponível ({response.status_code}): {url}"
                    )

                if bytes_downloaded > 0 and response.status_code == 200:
                    raise ResumeValidationUnavailable(
                        f"[CDXJ] Erro: O servidor não suporta Range requests (recebido status 200). "
                        f"Impossível retomar de {bytes_downloaded} bytes sem duplicar dados."
                    )
                elif response.status_code not in (200, 206):
                    response.raise_for_status()
                if bytes_downloaded > 0 and response.status_code == 206:
                    content_range = parse_content_range(response.headers.get("Content-Range"))
                    if not content_range or content_range["start"] != bytes_downloaded:
                        raise ResumeValidationUnavailable(
                            f"[CDXJ] Range inválido para {url}: esperado byte {bytes_downloaded}, "
                            f"recebido {response.headers.get('Content-Range')!r}."
                        )

                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if not chunk:
                        continue
                    data_start = bytes_downloaded - len(buffer)
                    bytes_downloaded += len(chunk)
                    buffer += chunk

                    lines = buffer.split(b"\n")
                    buffer = lines[-1]

                    for line in lines[:-1]:
                        line_end = data_start + len(line) + 1
                        yield line.decode("utf-8", errors="ignore"), line_end
                        data_start = line_end

                if buffer:
                    yield buffer.decode("utf-8", errors="ignore"), bytes_downloaded
                return

        except (requests.exceptions.RequestException, ConnectionResetError, OSError) as e:
            error_text = str(e).lower()
            if "failed to resolve" in error_text or "name or service not known" in error_text:
                raise
            retries += 1
            if retries >= max_retries:
                print(f"[CDXJ] Falha permanente ao ler {url}: {e}")
                raise
            time.sleep(min(2 ** retries, 30))


def iter_source_lines(source, initial_bytes=0):
    if source.get("path"):
        opener = gzip.open if source["path"].lower().endswith(".gz") else open
        bytes_read = 0
        with opener(source["path"], "rb") as f:
            for raw_line in f:
                bytes_read += len(raw_line)
                if bytes_read <= initial_bytes:
                    continue
                yield raw_line.decode("utf-8", errors="ignore"), bytes_read
        return

    for line, checkpoint_bytes in iter_url_lines_with_resume(source["url"], initial_bytes=initial_bytes):
        yield line, checkpoint_bytes


def process_source_legacy(source, args, domains, state):
    source_key = source_key_for(source)
    signature = source_signature(source)
    previous = state.get("processed", {}).get(source_key)
    previous_signature = previous.get("source_signature") if previous else None
    has_fingerprint = signature_has_fingerprint(signature)
    should_reprocess = bool(args.force)

    if previous and not args.force:
        if signatures_match(previous_signature, signature):
            if previous_signature != signature:
                previous["source_signature"] = signature
                previous["signature_recorded_at"] = utc_now()
                if not args.dry_run:
                    save_json(args.state_file, state)
            print(f"[CDXJ] Ja processado e sem alteracoes, a saltar: {source['name']}")
            return 0
        if previous_signature:
            if not has_fingerprint:
                print(f"[CDXJ] Nao foi possivel confirmar alteracoes em {source['name']}; a saltar para evitar reprocessamento pesado.")
                return 0
            should_reprocess = True
            print(f"[CDXJ] Fonte modificada, a reprocessar: {source['name']}")
        elif legacy_source_seems_modified(previous, signature):
            should_reprocess = True
            print(f"[CDXJ] Fonte parece modificada desde o ultimo processamento, a reprocessar: {source['name']}")
        else:
            if not has_fingerprint:
                print(f"[CDXJ] Nao foi possivel registar assinatura util para {source['name']}; a saltar.")
                return 0
            previous["source_signature"] = signature
            previous["signature_recorded_at"] = utc_now()
            if not args.dry_run:
                save_json(args.state_file, state)
            print(f"[CDXJ] Assinatura registada para {source['name']}; de agora em diante alteracoes serao detetadas.")
            return 0

    # Verificar checkpoint em progresso anterior
    in_prog = state.get("in_progress", {}).get(source_key)
    resuming = False
    initial_bytes = 0
    written = 0
    scanned = 0
    source_coverage = {}

    if in_prog and not args.force:
        in_prog_sig = in_prog.get("source_signature")
        if signatures_match(in_prog_sig, signature):
            resuming = True
            initial_bytes = in_prog.get("bytes_downloaded", 0)
            scanned = in_prog.get("scanned", 0)
            written = in_prog.get("written", 0)
            source_coverage = in_prog.get("domain_coverage", {})
            print(f"[CDXJ] A retomar {source['name']} a partir de {initial_bytes} bytes ({scanned} linhas lidas, {written} candidatos salvos)...")
        else:
            print(f"[CDXJ] Assinatura da fonte em progresso mudou, a recomeçar {source['name']} do início...")

    if not resuming and (should_reprocess or in_prog) and not args.dry_run:
        remove_existing_records_for_source(args.output_dir, source["name"])

    if not resuming:
        print(f"[CDXJ] A processar {source['name']}...")

    started = time.time()
    output_cache = None if args.dry_run else OutputFileCache()
    domain_pattern = domain_line_pattern(domains)
    last_checkpoint_bytes = initial_bytes
    last_checkpoint_scanned = scanned
    checkpoint_bytes = initial_bytes

    try:
        for line, checkpoint_bytes in iter_source_lines(source, initial_bytes=initial_bytes):
            scanned += 1
            if scanned and scanned % 1_000_000 == 0:
                print(f"[CDXJ] {source['name']}: {scanned} linhas lidas ({checkpoint_bytes / (1024*1024):.1f} MB), {written} candidatos.")

            # Guardar checkpoint a cada ~10 MB ou 500.000 linhas lidas
            if not args.dry_run and (checkpoint_bytes - last_checkpoint_bytes >= 10 * 1024 * 1024 or scanned - last_checkpoint_scanned >= 500_000):
                state.setdefault("in_progress", {})[source_key] = {
                    "name": source["name"],
                    "updated_at": utc_now(),
                    "bytes_downloaded": checkpoint_bytes,
                    "scanned": scanned,
                    "written": written,
                    "domain_coverage": source_coverage,
                    "source_signature": signature,
                }
                save_json(args.state_file, state)
                last_checkpoint_bytes = checkpoint_bytes
                last_checkpoint_scanned = scanned

            if not domain_pattern.search(ensure_text_line(line)):
                continue
            record = parse_cdxj_line(line)
            if not record:
                continue
            normalized = normalized_record(record, args.start_year, args.end_year, domains, source["name"])
            if not normalized:
                continue
            update_domain_coverage(source_coverage, normalized)
            if args.dry_run:
                written += 1
                continue
            path = output_path_for_record(args.output_dir, normalized)
            output_cache.write(path, json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n")
            written += 1

            if written and written % 1000 == 0:
                print(f"[CDXJ] {source['name']}: {written} candidatos escritos ({scanned} linhas lidas).")

    except RemoteSourceUnavailable as exc:
        if output_cache:
            output_cache.close()
        print(f"[CDXJ] A ignorar {source['name']}: {exc}")
        if not args.dry_run:
            remove_existing_records_for_source(args.output_dir, source["name"])
            state.get("in_progress", {}).pop(source_key, None)
            state.setdefault("skipped", {})[source_key] = {
                "name": source["name"],
                "reason": "remote_not_found",
                "skipped_at": utc_now(),
            }
            save_json(args.state_file, state)
        return 0
    except requests.exceptions.RequestException as exc:
        if output_cache:
            output_cache.close()
        print(f"[CDXJ] Falha temporária em {source['name']} no byte {checkpoint_bytes}; progresso guardado. {exc}")
        if not args.dry_run:
            state.setdefault("in_progress", {})[source_key] = {
                "name": source["name"],
                "updated_at": utc_now(),
                "bytes_downloaded": checkpoint_bytes,
                "scanned": scanned,
                "written": written,
                "domain_coverage": source_coverage,
                "source_signature": signature,
            }
            state.setdefault("failed", {})[source_key] = {
                "name": source["name"],
                "reason": exc.__class__.__name__,
                "error": str(exc),
                "failed_at": utc_now(),
                "bytes_downloaded": checkpoint_bytes,
            }
            save_json(args.state_file, state)
        return 0

    if output_cache:
        output_cache.close()

    elapsed = max(time.time() - started, 0.1)
    print(f"[CDXJ] {source['name']} concluido: {written} candidatos, {scanned} linhas, {elapsed/60:.1f} min.")

    if not args.dry_run:
        state.setdefault("processed", {})[source_key] = {
            "name": source["name"],
            "processed_at": utc_now(),
            "start_year": args.start_year,
            "end_year": args.end_year,
            "written": written,
            "scanned": scanned,
            "domain_coverage": source_coverage,
            "source_signature": signature,
        }
        state.get("in_progress", {}).pop(source_key, None)
        state.get("failed", {}).pop(source_key, None)
        aggregate_state_coverage(state)
        save_json(args.state_file, state)
    return written


def process_source(source, args, domains, state):
    source_key = source_key_for(source)
    signature = source_signature(source)
    previous = state.get("processed", {}).get(source_key)
    previous_signature = previous.get("source_signature") if previous else None
    has_fingerprint = signature_has_fingerprint(signature)
    should_reprocess = bool(args.force)
    in_prog = state.get("in_progress", {}).get(source_key)
    resuming = False
    initial_bytes = 0
    written = 0
    scanned = 0
    source_coverage = {}

    # An interrupted run for the current version takes precedence over the
    # completed state for the previous version.
    if in_prog and not args.force and signatures_match(in_prog.get("source_signature"), signature):
        resuming = True
        initial_bytes = positive_int(in_prog.get("bytes_downloaded"))
        scanned = positive_int(in_prog.get("scanned"))
        written = positive_int(in_prog.get("written"))
        source_coverage = deepcopy(in_prog.get("domain_coverage") or {})
        print(
            f"[CDXJ] A retomar {source['name']} a partir de {initial_bytes} bytes "
            f"({scanned} linhas lidas, {written} candidatos salvos)..."
        )
        legacy_checkpoint = in_prog.get("checkpoint_version") != 2
        if initial_bytes:
            try:
                if not validate_resume_boundary(
                    source,
                    initial_bytes,
                    require_line_boundary=legacy_checkpoint,
                ):
                    resuming = False
                    should_reprocess = True
                    if legacy_checkpoint:
                        print(
                            f"[CDXJ] O checkpoint antigo de {source['name']} não tem uma fronteira de linha "
                            "validável; será reconstruído."
                        )
                    else:
                        print(f"[CDXJ] O checkpoint de {source['name']} não coincide com a fonte; será reconstruído.")
                elif legacy_checkpoint:
                    print(
                        f"[CDXJ] Checkpoint antigo de {source['name']} validado; "
                        f"a retomar a partir do byte {initial_bytes}."
                    )
            except ResumeValidationUnavailable as exc:
                print(f"[CDXJ] Não foi possível validar a retoma de {source['name']}: {exc}")
                return 0
        elif scanned or written:
            resuming = False
            should_reprocess = True
            print(f"[CDXJ] O checkpoint antigo de {source['name']} não tem uma posição segura; será reconstruído.")
    elif in_prog and not args.force:
        print(f"[CDXJ] Assinatura da fonte em progresso mudou, a recomeçar {source['name']} do início...")

    if not resuming and previous and not args.force:
        if signatures_match(previous_signature, signature):
            if previous_signature != signature:
                previous["source_signature"] = signature
                previous["signature_recorded_at"] = utc_now()
                if not args.dry_run:
                    save_json(args.state_file, state)
            print(f"[CDXJ] Já processado e sem alterações, a saltar: {source['name']}")
            return 0

        if previous_signature:
            if not has_fingerprint:
                print(f"[CDXJ] Não foi possível confirmar alterações em {source['name']}; a saltar para evitar reprocessamento pesado.")
                return 0
            if args.dry_run:
                should_reprocess = True
                print(f"[CDXJ] Fonte modificada, a contar novamente: {source['name']}")
            else:
                decision, resume_offset, reason = incremental_resume_decision(source, previous, signature)
                if decision is None:
                    print(f"[CDXJ] Não foi possível validar a retoma incremental de {source['name']}: {reason}")
                    state.setdefault("failed", {})[source_key] = {
                        "name": source["name"],
                        "reason": "resume_validation_unavailable",
                        "error": reason,
                        "failed_at": utc_now(),
                    }
                    save_json(args.state_file, state)
                    return 0
                if decision:
                    resuming = True
                    initial_bytes = resume_offset
                    progress = previous.get("source_progress") or {}
                    scanned = positive_int(progress.get("scanned") or previous.get("scanned"))
                    written = positive_int(progress.get("written") or previous.get("written"))
                    source_coverage = deepcopy(previous.get("domain_coverage") or {})
                    print(
                        f"[CDXJ] Fonte atualizada; a continuar {source['name']} a partir do byte "
                        f"{initial_bytes} (prefixo validado)."
                    )
                else:
                    should_reprocess = True
                    print(f"[CDXJ] Fonte modificada sem prefixo seguro ({reason}); a reconstruir: {source['name']}")
        elif legacy_source_seems_modified(previous, signature):
            should_reprocess = True
            print(f"[CDXJ] Fonte parece modificada desde o último processamento, a reprocessar: {source['name']}")
        else:
            if not has_fingerprint:
                print(f"[CDXJ] Não foi possível registar assinatura útil para {source['name']}; a saltar.")
                return 0
            previous["source_signature"] = signature
            previous["signature_recorded_at"] = utc_now()
            if not args.dry_run:
                save_json(args.state_file, state)
            print(f"[CDXJ] Assinatura registada para {source['name']}; de agora em diante alterações serão detetadas.")
            return 0

    if not resuming and (should_reprocess or in_prog) and not args.dry_run:
        remove_existing_records_for_source(args.output_dir, source["name"])
        initial_bytes = 0
        written = 0
        scanned = 0
        source_coverage = {}

    if not resuming:
        print(f"[CDXJ] A processar {source['name']}...")

    started = time.time()
    output_cache = None if args.dry_run else OutputFileCache()
    domain_pattern = domain_line_pattern(domains)
    last_checkpoint_bytes = initial_bytes
    last_checkpoint_scanned = scanned
    checkpoint_bytes = initial_bytes

    try:
        for line, checkpoint_bytes in iter_source_lines(source, initial_bytes=initial_bytes):
            scanned += 1
            text_line = ensure_text_line(line)
            if domain_pattern.search(text_line):
                record = parse_cdxj_line(line)
                if record:
                    normalized = normalized_record(record, args.start_year, args.end_year, domains, source["name"])
                    if normalized:
                        update_domain_coverage(source_coverage, normalized)
                        if args.dry_run:
                            written += 1
                        else:
                            path = output_path_for_record(args.output_dir, normalized)
                            output_cache.write(
                                path,
                                json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n",
                            )
                            written += 1
                        if written and written % 1000 == 0:
                            print(f"[CDXJ] {source['name']}: {written} candidatos escritos ({scanned} linhas lidas).")

            if scanned and scanned % 1_000_000 == 0:
                print(f"[CDXJ] {source['name']}: {scanned} linhas lidas ({checkpoint_bytes / (1024*1024):.1f} MB), {written} candidatos.")

            # Checkpoint only after this line and its output are durable.
            if not args.dry_run and (
                checkpoint_bytes - last_checkpoint_bytes >= 10 * 1024 * 1024
                or scanned - last_checkpoint_scanned >= 500_000
            ):
                output_cache.flush()
                state.setdefault("in_progress", {})[source_key] = checkpoint_for_source(
                    source, signature, checkpoint_bytes, scanned, written, source_coverage
                )
                save_json(args.state_file, state)
                last_checkpoint_bytes = checkpoint_bytes
                last_checkpoint_scanned = scanned

    except RemoteSourceUnavailable as exc:
        if output_cache:
            output_cache.close()
        print(f"[CDXJ] A ignorar {source['name']}: {exc}")
        if not args.dry_run:
            remove_existing_records_for_source(args.output_dir, source["name"])
            state.get("in_progress", {}).pop(source_key, None)
            state.setdefault("skipped", {})[source_key] = {
                "name": source["name"],
                "reason": "remote_not_found",
                "skipped_at": utc_now(),
            }
            save_json(args.state_file, state)
        return 0
    except ResumeValidationUnavailable as exc:
        if output_cache:
            output_cache.close()
        print(f"[CDXJ] Retoma insegura para {source['name']}; o estado fica pendente: {exc}")
        if not args.dry_run:
            state.setdefault("in_progress", {})[source_key] = checkpoint_for_source(
                source, signature, checkpoint_bytes, scanned, written, source_coverage
            )
            state.setdefault("failed", {})[source_key] = {
                "name": source["name"],
                "reason": "resume_not_safe",
                "error": str(exc),
                "failed_at": utc_now(),
                "bytes_downloaded": checkpoint_bytes,
            }
            save_json(args.state_file, state)
        return 0
    except requests.exceptions.RequestException as exc:
        if output_cache:
            output_cache.close()
        print(f"[CDXJ] Falha temporária em {source['name']} no byte {checkpoint_bytes}; progresso guardado. {exc}")
        if not args.dry_run:
            state.setdefault("in_progress", {})[source_key] = checkpoint_for_source(
                source, signature, checkpoint_bytes, scanned, written, source_coverage
            )
            state.setdefault("failed", {})[source_key] = {
                "name": source["name"],
                "reason": exc.__class__.__name__,
                "error": str(exc),
                "failed_at": utc_now(),
                "bytes_downloaded": checkpoint_bytes,
            }
            save_json(args.state_file, state)
        return 0

    if output_cache:
        output_cache.close()

    elapsed = max(time.time() - started, 0.1)
    print(f"[CDXJ] {source['name']} concluído: {written} candidatos, {scanned} linhas, {elapsed/60:.1f} min.")

    if not args.dry_run:
        state.setdefault("processed", {})[source_key] = {
            "name": source["name"],
            "processed_at": utc_now(),
            "start_year": args.start_year,
            "end_year": args.end_year,
            "written": written,
            "scanned": scanned,
            "domain_coverage": source_coverage,
            "source_signature": signature,
            "source_progress": runtime_source_progress(source, checkpoint_bytes, scanned, written),
        }
        state.get("in_progress", {}).pop(source_key, None)
        state.get("failed", {}).pop(source_key, None)
        aggregate_state_coverage(state)
        save_json(args.state_file, state)
    return written


def selected_sources(args):
    if args.input_dir:
        return iter_local_sources(args.input_dir)

    remote = discover_remote_collections(args.manifest_url)
    if args.collections:
        wanted = set(args.collections)
        return [item for item in remote if item["name"] in wanted]
    if args.collection_regex:
        pattern = re.compile(args.collection_regex)
        return [item for item in remote if pattern.search(item["name"])]
    if args.all_remote:
        return remote
    return []


def main():
    parser = argparse.ArgumentParser(description="Cria indices CDXJ filtrados por dia para o Noticias de Ontem.")
    parser.add_argument("--start-year", type=int, default=1996)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--state-file", default=STATE_FILE)
    parser.add_argument("--manifest-url", default=MANIFEST_URL)
    parser.add_argument("--input-dir", help="Pasta com CDXJ brutos ja descarregados localmente.")
    parser.add_argument("--collections", nargs="*", help="Nomes exatos de colecoes remotas, ex: EAWP5.cdxj FAWP60.cdxj.")
    parser.add_argument("--collection-regex", help="Regex para escolher colecoes remotas.")
    parser.add_argument("--all-remote", action="store_true", help="Processa todas as colecoes remotas listadas pelo Arquivo.pt.")
    parser.add_argument("--domains", default=",".join(NEWS_DOMAINS), help="Dominios separados por virgula.")
    parser.add_argument("--force", action="store_true", help="Reprocessa fontes ja marcadas no estado.")
    parser.add_argument("--dry-run", action="store_true", help="Conta candidatos sem escrever ficheiros.")
    parser.add_argument(
        "--migrate-state-only",
        action="store_true",
        help="Preenche offsets e âncoras de retoma nas coleções já processadas e termina.",
    )
    parser.add_argument(
        "--rebuild-coverage",
        action="store_true",
        help="Reconstrói apenas as datas de cobertura a partir dos CDXJ filtrados existentes.",
    )
    args = parser.parse_args()

    domains = [domain.strip().lower() for domain in args.domains.split(",") if domain.strip()]
    state = load_json(args.state_file, {"processed": {}})
    if args.rebuild_coverage:
        rebuild_coverage_from_output(args.output_dir, state, args.state_file)
        return

    if not args.dry_run:
        state, migrated = migrate_processed_state(state, fetch_anchors=True)
        if migrated:
            save_json(args.state_file, state)
            print("[CDXJ] Estado legado migrado com posições byte-a-byte para retomas futuras.")
    if args.migrate_state_only:
        print("[CDXJ] Migração do estado concluída.")
        return

    sources = selected_sources(args)
    if not sources:
        print("Nenhuma fonte CDXJ selecionada.")
        print("Exemplos:")
        print("  python build_arquivo_cdxj_index.py --start-year 1996 --end-year 2026 --all-remote")
        print("  python build_arquivo_cdxj_index.py --input-dir C:\\\\cdxj_brutos --start-year 1996 --end-year 2026")
        print("  python build_arquivo_cdxj_index.py --collections EAWP5.cdxj FAWP60.cdxj")
        sys.exit(1)

    total = 0
    print(f"[CDXJ] Fontes selecionadas: {len(sources)}")
    print(f"[CDXJ] Anos: {args.start_year}-{args.end_year}")
    print(f"[CDXJ] Dominios: {', '.join(domains)}")
    for source in sources:
        total += process_source(source, args, domains, state)
    if not args.dry_run:
        aggregate_state_coverage(state)
        save_json(args.state_file, state)
    print(f"[CDXJ] Total de candidatos escritos/contados: {total}")


if __name__ == "__main__":
    main()
