import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_arquivo_cdxj_index as cdxj


def args_for(workspace):
    return SimpleNamespace(
        force=False,
        dry_run=False,
        state_file=str(workspace / "state.json"),
        output_dir=str(workspace / "arquivo_cdxj"),
        start_year=2020,
        end_year=2026,
    )


def cdxj_line(timestamp, slug):
    return (
        f"pt,publico,pt)/noticias/{slug} {timestamp} "
        + json.dumps(
            {
                "url": f"https://publico.pt/noticias/{slug}",
                "mime": "text/html",
                "status": "200",
            }
        )
        + "\n"
    )


class CdxjResumeTests(unittest.TestCase):
    def test_remote_iterator_reports_exact_offsets_for_multiple_lines_in_one_chunk(self):
        class Response:
            status_code = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_content(self, chunk_size):
                del chunk_size
                yield b"one\ntwo\nthree\n"

        with patch.object(cdxj.requests, "get", return_value=Response()):
            rows = list(cdxj.iter_url_lines_with_resume("https://example.test/data.cdxj"))
        self.assertEqual([(line, offset) for line, offset in rows], [
            ("one", 4),
            ("two", 8),
            ("three", 14),
        ])

    def test_legacy_in_progress_remote_checkpoint_resumes_from_saved_offset(self):
        prefix = b"already-processed\n"
        tail = cdxj_line("20200101000000", "continued").encode("utf-8")
        payload_length = len(prefix) + len(tail)
        offset = len(prefix)
        source = {
            "name": "TEST.cdxj",
            "url": "https://arquivo.example/TEST.cdxj",
        }
        signature = {
            "type": "remote",
            "url": source["url"],
            "etag": '"same"',
            "content_length": str(payload_length),
        }
        state = {
            "processed": {},
            "in_progress": {
                source["url"]: {
                    "name": source["name"],
                    "bytes_downloaded": offset,
                    "scanned": 1,
                    "written": 0,
                    "source_signature": signature,
                }
            },
            "failed": {},
        }
        args = args_for(Path(tempfile.mkdtemp()))
        seen_headers = []

        class Response:
            status_code = 206
            headers = {
                "Content-Range": f"bytes {offset}-{payload_length - 1}/{payload_length}",
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_content(self, chunk_size):
                del chunk_size
                yield tail

        def get(_url, **kwargs):
            seen_headers.append(kwargs["headers"])
            return Response()

        try:
            with patch.object(cdxj, "source_signature", return_value=signature), \
                    patch.object(cdxj, "source_boundary_fingerprint", return_value={"ends_with_newline": True}), \
                    patch.object(
                        cdxj,
                        "runtime_source_progress",
                        return_value={
                            "status": "complete",
                            "mode": "append_only",
                            "bytes_downloaded": payload_length,
                        },
                    ), \
                    patch.object(cdxj.requests, "get", side_effect=get):
                self.assertEqual(cdxj.process_source(source, args, ["publico.pt"], state), 1)
            self.assertEqual(seen_headers[0]["Range"], f"bytes={offset}-")
            output = list((Path(args.output_dir) / "2020").glob("*.cdxj"))
            records = [
                json.loads(line)
                for item in output
                for line in item.read_text(encoding="utf-8").splitlines()
            ]
        finally:
            shutil.rmtree(Path(args.state_file).parent)

        self.assertEqual([record["url"] for record in records], ["https://publico.pt/noticias/continued"])

    def test_updated_remote_source_appends_from_previous_completed_offset(self):
        prefix = b"previous-version\n"
        tail = cdxj_line("20200102000000", "new-record").encode("utf-8")
        old_length = len(prefix)
        new_length = old_length + len(tail)
        source = {
            "name": "TEST.cdxj",
            "url": "https://arquivo.example/TEST.cdxj",
        }
        old_signature = {
            "type": "remote",
            "url": source["url"],
            "etag": '"old"',
            "content_length": str(old_length),
        }
        current_signature = {
            "type": "remote",
            "url": source["url"],
            "etag": '"new"',
            "content_length": str(new_length),
        }
        anchor = {
            "start": 0,
            "end": old_length - 1,
            "sha256": "prefix",
            "ends_with_newline": True,
        }
        args = args_for(Path(tempfile.mkdtemp()))
        output_path = cdxj.output_path_for_record(
            args.output_dir,
            {
                "timestamp": "20200101000000",
                "url": "https://publico.pt/noticias/old-record",
            },
        )
        old_record = {
            "url": "https://publico.pt/noticias/old-record",
            "timestamp": "20200101000000",
            "mime": "text/html",
            "status": "200",
            "title": "",
            "digest": "",
            "domain": "publico.pt",
            "source_collection": source["name"],
        }
        output_path.write_text(json.dumps(old_record) + "\n", encoding="utf-8")
        state = {
            "processed": {
                source["url"]: {
                    "name": source["name"],
                    "scanned": 1,
                    "written": 1,
                    "domain_coverage": {},
                    "source_signature": old_signature,
                    "source_progress": {
                        "status": "complete",
                        "mode": "append_only",
                        "bytes_downloaded": old_length,
                        "scanned": 1,
                        "written": 1,
                        "anchor": anchor,
                    },
                }
            },
            "in_progress": {},
            "failed": {},
        }
        seen_headers = []

        class Response:
            status_code = 206
            headers = {
                "Content-Range": f"bytes {old_length}-{new_length - 1}/{new_length}",
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_content(self, chunk_size):
                del chunk_size
                yield tail

        def get(_url, **kwargs):
            seen_headers.append(kwargs["headers"])
            return Response()

        try:
            with patch.object(cdxj, "source_signature", return_value=current_signature), \
                    patch.object(cdxj, "source_boundary_fingerprint", return_value=anchor), \
                    patch.object(
                        cdxj,
                        "runtime_source_progress",
                        return_value={
                            "status": "complete",
                            "mode": "append_only",
                            "bytes_downloaded": new_length,
                        },
                    ), \
                    patch.object(cdxj.requests, "get", side_effect=get):
                self.assertEqual(cdxj.process_source(source, args, ["publico.pt"], state), 2)
            self.assertEqual(seen_headers[0]["Range"], f"bytes={old_length}-")
            output_files = list((Path(args.output_dir) / "2020").glob("*.cdxj"))
            records = [
                json.loads(line)
                for item in output_files
                for line in item.read_text(encoding="utf-8").splitlines()
            ]
        finally:
            shutil.rmtree(Path(args.state_file).parent)

        self.assertEqual({record["url"] for record in records}, {
            "https://publico.pt/noticias/old-record",
            "https://publico.pt/noticias/new-record",
        })

    def test_local_iterator_reports_exact_line_end_offsets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.cdxj"
            path.write_bytes(b"one\ntwo\nthree\n")
            rows = list(cdxj.iter_source_lines({"name": path.name, "path": str(path)}))
            self.assertEqual([(line, offset) for line, offset in rows], [
                ("one\n", 4),
                ("two\n", 8),
                ("three\n", 14),
            ])

    def test_legacy_processed_state_gets_offset_and_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.cdxj"
            path.write_bytes(b"a" * 100_000)
            stat = path.stat()
            state = {
                "processed": {
                    str(path): {
                        "name": path.name,
                        "processed_at": "2026-01-01T00:00:00+00:00",
                        "scanned": 10,
                        "written": 2,
                        "source_signature": {
                            "type": "local",
                            "path": str(path.resolve()),
                            "size": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns,
                        },
                    }
                }
            }
            state, changed = cdxj.migrate_processed_state(state)
            progress = state["processed"][str(path)]["source_progress"]
            self.assertTrue(changed)
            self.assertEqual(progress["bytes_downloaded"], stat.st_size)
            self.assertEqual(progress["scanned"], 10)
            self.assertEqual(progress["status"], "complete")
            self.assertEqual(progress["anchor"]["end"], stat.st_size - 1)

    def test_changed_source_resumes_only_when_prefix_anchor_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.cdxj"
            path.write_bytes(b"old-prefix\n")
            old_signature = cdxj.source_signature({"name": path.name, "path": str(path)})
            progress = {
                "status": "complete",
                "mode": "append_only",
                "bytes_downloaded": path.stat().st_size,
                "anchor": cdxj.source_boundary_fingerprint({"name": path.name, "path": str(path)}, path.stat().st_size),
            }
            previous = {"source_signature": old_signature, "source_progress": progress}

            path.write_bytes(b"old-prefix\nnew-line\n")
            new_signature = cdxj.source_signature({"name": path.name, "path": str(path)})
            decision, offset, reason = cdxj.incremental_resume_decision(
                {"name": path.name, "path": str(path)}, previous, new_signature
            )
            self.assertTrue(decision)
            self.assertEqual(offset, len(b"old-prefix\n"))
            self.assertEqual(reason, "prefix_boundary_matches")

            path.write_bytes(b"changed!!\nnew-line\n")
            changed_signature = cdxj.source_signature({"name": path.name, "path": str(path)})
            decision, offset, reason = cdxj.incremental_resume_decision(
                {"name": path.name, "path": str(path)}, previous, changed_signature
            )
            self.assertFalse(decision)
            self.assertEqual(offset, 0)
            self.assertEqual(reason, "prefix_boundary_changed")

    def test_remote_legacy_state_uses_recorded_content_length_as_offset(self):
        state = {
            "processed": {
                "https://arquivo.pt/datasets/cdxj/TEST.cdxj": {
                    "name": "TEST.cdxj",
                    "scanned": 100,
                    "written": 3,
                    "source_signature": {
                        "type": "remote",
                        "url": "https://arquivo.pt/datasets/cdxj/TEST.cdxj",
                        "content_length": "123456",
                    },
                }
            }
        }
        anchor = {"start": 58000, "end": 123455, "sha256": "abc"}
        with patch.object(cdxj, "source_boundary_fingerprint", return_value=anchor) as fingerprint:
            state, changed = cdxj.migrate_processed_state(state)
        progress = state["processed"]["https://arquivo.pt/datasets/cdxj/TEST.cdxj"]["source_progress"]
        self.assertTrue(changed)
        self.assertEqual(progress["bytes_downloaded"], 123456)
        self.assertEqual(progress["anchor"], anchor)
        fingerprint.assert_called_once()

    def test_process_source_appends_only_new_local_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            path = workspace / "source.cdxj"
            path.write_bytes(cdxj_line("20200101000000", "first").encode("utf-8"))
            source = {"name": path.name, "path": str(path)}
            args = args_for(workspace)
            state = {"processed": {}, "in_progress": {}, "failed": {}}
            domains = ["publico.pt"]

            self.assertEqual(cdxj.process_source(source, args, domains, state), 1)
            original_offset = state["processed"][str(path)]["source_progress"]["bytes_downloaded"]
            path.write_bytes(
                (
                    cdxj_line("20200101000000", "first")
                    + cdxj_line("20200102000000", "second")
                ).encode("utf-8")
            )

            self.assertEqual(cdxj.process_source(source, args, domains, state), 2)
            processed = state["processed"][str(path)]
            self.assertEqual(processed["source_progress"]["bytes_downloaded"], path.stat().st_size)
            self.assertEqual(processed["written"], 2)
            output = list((workspace / "arquivo_cdxj").glob("*/*.cdxj"))
            records = [json.loads(line) for item in output for line in item.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual({record["url"] for record in records}, {
                "https://publico.pt/noticias/first",
                "https://publico.pt/noticias/second",
            })
            self.assertEqual(original_offset, len(cdxj_line("20200101000000", "first").encode("utf-8")))

    def test_remote_signature_detects_content_length_change_even_with_same_etag(self):
        previous = {"type": "remote", "etag": '"same"', "content_length": "100"}
        current = {"type": "remote", "etag": '"same"', "content_length": "101"}
        self.assertFalse(cdxj.signatures_match(previous, current))


if __name__ == "__main__":
    unittest.main()
