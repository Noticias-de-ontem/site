import argparse
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = ROOT / "arquivo_cdxj"
DEFAULT_STATE_FILE = ROOT / "topic_index_state.json"
DEFAULT_INDEX = "noticias-ontem-captures-v1"
INDEX_SCHEMA_VERSION = 2
USER_AGENT = "NoticiasDeOntemIndexer/1.0 (+https://github.com/luisflmaximo/Noticias-de-ontem-pt)"


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def truthy(value, default=True):
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


class RateLimiter:
    def __init__(self, requests_per_second):
        self.interval = 1 / max(float(requests_per_second), 0.1)
        self.lock = threading.Lock()
        self.next_request_at = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            scheduled = max(now, self.next_request_at)
            self.next_request_at = scheduled + self.interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)


class DigestCache:
    def __init__(self, maximum=500):
        self.maximum = maximum
        self.values = OrderedDict()
        self.lock = threading.Lock()

    def get(self, digest):
        if not digest:
            return None
        with self.lock:
            value = self.values.get(digest)
            if value is not None:
                self.values.move_to_end(digest)
            return value

    def put(self, digest, value):
        if not digest:
            return
        with self.lock:
            self.values[digest] = value
            self.values.move_to_end(digest)
            while len(self.values) > self.maximum:
                self.values.popitem(last=False)


class SearchClient:
    def __init__(self, base_url, index, meta_index, verify_ssl=True):
        self.base_url = base_url.rstrip("/")
        self.index = index
        self.meta_index = meta_index
        self.verify_ssl = verify_ssl
        self.username = os.environ.get("OPENSEARCH_USERNAME", "").strip()
        self.password = os.environ.get("OPENSEARCH_PASSWORD", "").strip()
        self.api_key = os.environ.get("OPENSEARCH_API_KEY", "").strip()

    def headers(self, content_type="application/json"):
        headers = {"Accept": "application/json", "Content-Type": content_type}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        return headers

    def auth(self):
        if self.api_key or not self.username:
            return None
        return (self.username, self.password)

    def request(self, method, path, payload=None, data=None, content_type="application/json", accepted=(200, 201)):
        response = requests.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            json=payload,
            data=data,
            headers=self.headers(content_type),
            auth=self.auth(),
            verify=self.verify_ssl,
            timeout=(15, 120),
        )
        if response.status_code not in accepted:
            detail = response.text[:300].replace("\n", " ")
            raise RuntimeError(f"OpenSearch HTTP {response.status_code}: {detail}")
        return response.json() if response.content else {"_http_status": response.status_code}

    def ensure_indices(self):
        capture_mapping = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "capture_id": {"type": "keyword"},
                    "captured_at": {"type": "date"},
                    "year": {"type": "integer"},
                    "month_day": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": "standard"},
                    "text": {"type": "text", "analyzer": "standard"},
                    "original_url": {"type": "keyword", "index": False},
                    "original_url_key": {"type": "keyword"},
                    "arquivo_url": {"type": "keyword", "index": False},
                    "source_collection": {"type": "keyword"},
                    "source_file": {"type": "keyword"},
                    "digest": {"type": "keyword"},
                    "mime": {"type": "keyword"},
                    "content_bytes": {"type": "long"},
                },
            },
        }
        meta_mapping = {"mappings": {"dynamic": True}}
        capture_exists = self.request("HEAD", quote(self.index), accepted=(200, 404)).get("_http_status") == 200
        meta_exists = self.request("HEAD", quote(self.meta_index), accepted=(200, 404)).get("_http_status") == 200
        if not capture_exists:
            self.request("PUT", quote(self.index), capture_mapping)
        else:
            self.request(
                "PUT",
                f"{quote(self.index)}/_mapping",
                {"properties": {
                    "month_day": {"type": "keyword"},
                    "original_url_key": {"type": "keyword"},
                }},
            )
        if not meta_exists:
            self.request("PUT", quote(self.meta_index), meta_mapping)

    def metadata(self):
        try:
            return self.request("GET", f"{quote(self.meta_index)}/_doc/coverage").get("_source", {})
        except Exception:
            return {}

    def write_metadata(self, payload):
        self.request("PUT", f"{quote(self.meta_index)}/_doc/coverage", payload)

    def delete_source_file(self, relative_path):
        payload = {"query": {"term": {"source_file": relative_path}}}
        self.request(
            "POST",
            f"{quote(self.index)}/_delete_by_query?conflicts=proceed&refresh=true",
            payload,
        )

    def bulk_index(self, documents):
        lines = []
        for document in documents:
            lines.append(json.dumps({"index": {"_index": self.index, "_id": document["capture_id"]}}, separators=(",", ":")))
            lines.append(json.dumps(document, ensure_ascii=False, separators=(",", ":")))
        body = ("\n".join(lines) + "\n").encode("utf-8")
        response = self.request(
            "POST",
            "_bulk?refresh=false",
            data=body,
            content_type="application/x-ndjson",
        )
        if response.get("errors"):
            failures = [
                item.get("index", {}).get("error")
                for item in response.get("items", [])
                if item.get("index", {}).get("error")
            ]
            raise RuntimeError(f"OpenSearch bulk error: {failures[:1]}")

    def refresh(self):
        self.request("POST", f"{quote(self.index)}/_refresh", accepted=(200,))


thread_local = threading.local()


def http_session():
    session = getattr(thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"})
        thread_local.session = session
    return session


def extract_page(content, encoding=None):
    soup = BeautifulSoup(content, "html.parser", from_encoding=encoding)
    for element in soup(["script", "style", "noscript", "template"]):
        element.decompose()
    title = " ".join(soup.title.stripped_strings) if soup.title else ""
    text = " ".join(soup.stripped_strings)
    if not text:
        raise ValueError("empty extracted text")
    return title, text


def fetch_content(record, replay_limiter, text_limiter, maximum_bytes):
    url = str(record.get("url") or "")
    timestamp = str(record.get("timestamp") or "")[:14]
    replay_url = f"https://arquivo.pt/noFrame/replay/{timestamp}id_/{url}"
    last_error = None
    for attempt in range(3):
        try:
            replay_limiter.wait()
            response = http_session().get(replay_url, timeout=(10, 45), stream=True)
            response.raise_for_status()
            chunks = []
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError(f"page exceeds {maximum_bytes} bytes")
                chunks.append(chunk)
            content = b"".join(chunks)
            title, text = extract_page(content, response.encoding)
            return title, text, size
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))

    extracted_url = "https://arquivo.pt/textextracted?m=" + quote(f"{url}/{timestamp}", safe="")
    try:
        text_limiter.wait()
        response = http_session().get(extracted_url, timeout=(10, 60))
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            raise ValueError("empty Arquivo.pt extracted text")
        return str(record.get("title") or ""), text, len(response.content)
    except Exception as exc:
        raise RuntimeError(f"capture unavailable: {type(last_error).__name__}/{type(exc).__name__}") from exc


def captured_at(timestamp):
    return f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}T{timestamp[8:10]}:{timestamp[10:12]}:{timestamp[12:14]}Z"


def document_for_record(record, relative_path, replay_limiter, text_limiter, digest_cache, maximum_bytes):
    url = str(record.get("url") or "").strip()
    timestamp = str(record.get("timestamp") or "").strip()[:14]
    domain = str(record.get("domain") or "").strip().lower()
    if len(timestamp) != 14 or not url or not domain:
        raise ValueError("invalid filtered CDXJ record")
    digest = str(record.get("digest") or "").strip()
    cached = digest_cache.get(digest)
    if cached:
        title, text, content_size = cached
    else:
        title, text, content_size = fetch_content(record, replay_limiter, text_limiter, maximum_bytes)
        digest_cache.put(digest, (title, text, content_size))
    capture_id = hashlib.sha256(f"{timestamp}\0{url}".encode("utf-8")).hexdigest()
    return {
        "capture_id": capture_id,
        "captured_at": captured_at(timestamp),
        "year": int(timestamp[:4]),
        "month_day": f"{timestamp[4:6]}-{timestamp[6:8]}",
        "domain": domain,
        "title": str(record.get("title") or title or "").strip(),
        "text": text,
        "original_url": url,
        "original_url_key": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "arquivo_url": f"https://arquivo.pt/noFrame/replay/{timestamp}/{url}",
        "source_collection": str(record.get("source_collection") or ""),
        "source_file": relative_path,
        "digest": digest,
        "mime": str(record.get("mime") or "text/html"),
        "content_bytes": content_size,
    }


def file_date(path):
    if len(path.parts) < 2 or not path.parent.name.isdigit():
        return ""
    stem = path.stem
    if len(stem) != 5 or stem[2] != "-":
        return ""
    return f"{path.parent.name}-{stem}"


def file_signature(path):
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def iter_batches(path, batch_size):
    batch = []
    seen = set()
    with path.open("r", encoding="utf-8", errors="ignore") as source:
        for line in source:
            try:
                record = json.loads(line)
            except Exception:
                continue
            key = f"{record.get('timestamp', '')}\0{record.get('url', '')}"
            if key in seen:
                continue
            seen.add(key)
            batch.append(record)
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def process_file(path, input_dir, client, args, replay_limiter, text_limiter, digest_cache):
    relative_path = path.relative_to(input_dir).as_posix()
    signature_before = file_signature(path)
    client.delete_source_file(relative_path)
    indexed = 0
    failed = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for records in iter_batches(path, args.batch_size):
            futures = [
                executor.submit(
                    document_for_record,
                    record,
                    relative_path,
                    replay_limiter,
                    text_limiter,
                    digest_cache,
                    args.maximum_page_bytes,
                )
                for record in records
            ]
            documents = []
            for record, future in zip(records, futures):
                try:
                    documents.append(future.result())
                except Exception as exc:
                    failed.append({
                        "url": str(record.get("url") or ""),
                        "timestamp": str(record.get("timestamp") or ""),
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            if documents:
                client.bulk_index(documents)
                indexed += len(documents)
                print(f"[indice] {relative_path}: {indexed} documentos indexados", flush=True)
    if file_signature(path) != signature_before:
        failed.append({"error": "O ficheiro mudou durante a indexacao; sera repetido."})
    return indexed, failed, signature_before


def main():
    parser = argparse.ArgumentParser(description="Constroi o indice de texto rapido a partir de capturas preservadas pelo Arquivo.pt.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--start-date", default="1996-01-01")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=120)
    parser.add_argument("--requests-per-second", type=float, default=20)
    parser.add_argument("--text-requests-per-second", type=float, default=3)
    parser.add_argument("--maximum-page-bytes", type=int, default=8_000_000)
    parser.add_argument("--max-files", type=int, default=0, help="Limite apenas para testes; zero processa todos.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    paths = sorted(path for path in input_dir.glob("*/*.cdxj") if file_date(path))
    if args.end_date:
        paths = [path for path in paths if file_date(path) <= args.end_date]
    paths = [path for path in paths if file_date(path) >= args.start_date]
    if not paths:
        print("Nenhum CDXJ diario encontrado para o intervalo.")
        return 1
    selected_paths = paths[:args.max_files] if args.max_files else paths
    if args.dry_run:
        print(f"[indice] {len(selected_paths)} de {len(paths)} ficheiros seriam processados.")
        return 0

    base_url = os.environ.get("OPENSEARCH_URL", "").strip()
    if not base_url:
        print("OPENSEARCH_URL nao esta configurado.")
        return 1
    index = os.environ.get("OPENSEARCH_INDEX", DEFAULT_INDEX).strip()
    meta_index = os.environ.get("OPENSEARCH_META_INDEX", f"{index}-meta").strip()
    client = SearchClient(base_url, index, meta_index, truthy(os.environ.get("OPENSEARCH_VERIFY_SSL"), True))
    client.ensure_indices()
    state = load_json(args.state_file, {"files": {}})
    if not client.metadata() or state.get("schema_version") != INDEX_SCHEMA_VERSION:
        state = {"schema_version": INDEX_SCHEMA_VERSION, "files": {}}
    state["schema_version"] = INDEX_SCHEMA_VERSION
    state.setdefault("files", {})
    client.write_metadata({
        "complete": False,
        "start_date": args.start_date,
        "end_date": file_date(paths[-1]),
        "indexed_at": utc_now(),
        "documents": sum(int(item.get("documents") or 0) for item in state["files"].values()),
        "failed_documents": 0,
        "schema_version": INDEX_SCHEMA_VERSION,
    })

    replay_limiter = RateLimiter(args.requests_per_second)
    text_limiter = RateLimiter(args.text_requests_per_second)
    digest_cache = DigestCache()
    failed_files = {}
    for index_number, path in enumerate(selected_paths, start=1):
        relative_path = path.relative_to(input_dir).as_posix()
        signature = file_signature(path)
        previous = state["files"].get(relative_path, {})
        if not args.force and previous.get("signature") == signature and not previous.get("failed"):
            print(f"[indice] {index_number}/{len(selected_paths)} sem alteracoes: {relative_path}", flush=True)
            continue
        print(f"[indice] {index_number}/{len(selected_paths)} a processar {relative_path}", flush=True)
        documents, failures, processed_signature = process_file(
            path,
            input_dir,
            client,
            args,
            replay_limiter,
            text_limiter,
            digest_cache,
        )
        state["files"][relative_path] = {
            "signature": processed_signature,
            "documents": documents,
            "indexed_at": utc_now(),
            "failed": len(failures),
            "failures": failures[:100],
        }
        if failures:
            failed_files[relative_path] = len(failures)
        save_json(args.state_file, state)

    client.refresh()
    all_current = all(
        state["files"].get(path.relative_to(input_dir).as_posix(), {}).get("signature") == file_signature(path)
        and not state["files"].get(path.relative_to(input_dir).as_posix(), {}).get("failed")
        for path in paths
    )
    complete = all_current and not failed_files and not args.max_files
    documents = sum(
        int(state["files"].get(path.relative_to(input_dir).as_posix(), {}).get("documents") or 0)
        for path in paths
    )
    failed_documents = sum(
        int(state["files"].get(path.relative_to(input_dir).as_posix(), {}).get("failed") or 0)
        for path in paths
    )
    metadata = {
        "complete": complete,
        "start_date": args.start_date,
        "end_date": file_date(paths[-1]),
        "indexed_at": utc_now(),
        "documents": documents,
        "failed_documents": failed_documents,
        "files": len(paths),
        "schema_version": INDEX_SCHEMA_VERSION,
    }
    client.write_metadata(metadata)
    state["coverage"] = metadata
    save_json(args.state_file, state)
    print(f"[indice] Concluido: {documents} documentos; completo={complete}; falhas={failed_documents}.")
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
