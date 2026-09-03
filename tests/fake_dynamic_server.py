import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
SITE_DATA_FILE = SITE_DIR / "data" / "news.json"
jobs = {}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json({"status": "ok", "source": "Arquivo.pt"})
        if path == "/api/site-data":
            return self.send_json(json.loads(SITE_DATA_FILE.read_text(encoding="utf-8")))
        if path == "/api/metrics":
            data = json.loads(SITE_DATA_FILE.read_text(encoding="utf-8"))
            return self.send_json(data.get("metrics", {}))
        if path == "/api/search-status":
            return self.send_json({
                "configured": True,
                "ready": True,
                "engine": "opensearch",
                "start_date": "1996-01-01",
                "end_date": "2025-03-24",
            })
        if path == "/api/coverage":
            data = json.loads(SITE_DATA_FILE.read_text(encoding="utf-8")).get("topic_search", {})
            return self.send_json({
                "min_date": data.get("min_date"),
                "max_date": data.get("max_date"),
                "sources": data.get("sources", []),
                "source_metadata": data.get("source_metadata", {}),
            })
        if path.startswith("/api/topic-analyses/"):
            job_id = path.rsplit("/", 1)[-1]
            request = jobs.get(job_id)
            if not request:
                return self.send_json({"detail": "Analysis not found"}, 404)
            start_year = int(request["from_date"][:4])
            end_year = int(request["to_date"][:4])
            analyses = []
            for analysis_index, analysis in enumerate(request["analyses"]):
                series = []
                for year in range(start_year, end_year + 1):
                    count = ((year - start_year + 1) * (analysis_index + 2) * 37) + (analysis_index * 19)
                    series.append({
                        "year": year,
                        "from_date": max(request["from_date"], f"{year}-01-01"),
                        "to_date": min(request["to_date"], f"{year}-12-31"),
                        "count": count,
                        "failed": False,
                    })
                analyses.append({
                    **analysis,
                    "series": series,
                    "total": sum(item["count"] for item in series),
                    "complete": True,
                })
            return self.send_json({
                "id": job_id,
                "status": "completed",
                "progress": 100,
                "result": {"analyses": analyses, "complete": True},
                "error": None,
            })
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/topic-analyses":
            return self.send_json({"detail": "Not found"}, 404)
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        job_id = f"visual-{len(jobs) + 1}"
        jobs[job_id] = request
        return self.send_json({"id": job_id, "status": "queued", "progress": 0, "cached": False}, 202)

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Fake dynamic site: http://127.0.0.1:{args.port}/temas/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
