import tempfile
import unittest
from pathlib import Path

from sync_cdxj_storage import local_files, safe_target


class StorageSyncTests(unittest.TestCase):
    def test_local_files_only_lists_cdxj_and_requested_states(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            day = workspace / "arquivo_cdxj" / "2026" / "07-08.cdxj"
            day.parent.mkdir(parents=True)
            day.write_text("{}\n", encoding="utf-8")
            (workspace / "arquivo_cdxj_state.json").write_text("{}", encoding="utf-8")
            (workspace / "topic_index_state.json").write_text("{}", encoding="utf-8")
            regular = [relative for _path, relative in local_files(workspace, False)]
            with_index = [relative for _path, relative in local_files(workspace, True)]
        self.assertEqual(regular, ["arquivo_cdxj/2026/07-08.cdxj", "arquivo_cdxj_state.json"])
        self.assertEqual(with_index[-1], "topic_index_state.json")

    def test_remote_key_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(RuntimeError):
                safe_target(workspace, "../outside.cdxj")


if __name__ == "__main__":
    unittest.main()
