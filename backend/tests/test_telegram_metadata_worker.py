"""Deterministic tests for stand-alone T8/T10 source-controlled worker."""
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/telegram_bridge/metadata_worker.py"
SPEC = importlib.util.spec_from_file_location("telegram_metadata_worker", SCRIPT)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class TelegramMetadataWorkerTests(unittest.TestCase):
    def test_summarize_only_known_channels_and_deduplicate(self):
        log = "\n".join([
            "YENI PAYLASIM | @solearlytrending | ID: 11 | 18:25:33",
            "YENI PAYLASIM | @KOLscope | ID: 21 | 18:26:01",
            "YENI PAYLASIM | @KOLscope | ID: 21 | 18:26:02",
            "YENI PAYLASIM | @unknown | ID: 22 | 18:26:03",
            "text SOLANA CONTRACT_SECRET ",
        ])
        result = worker.summarize(log)
        self.assertEqual(result["solana_early_trending"]["count"], 1)
        self.assertEqual(result["kolscope"]["count"], 1)
        self.assertEqual(result["kolscope"]["last_id"], "21")
        self.assertNotIn("CONTRACT_SECRET", json.dumps(result))

    def test_atomic_status_matches_t10_schema_and_private_files(self):
        from nexora.social_ai.telegram_bridge import from_t10
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "t6_events.log").write_text(
                "YENI PAYLASIM | @solearlytrending | ID: 20 | 19:00:00\n"
                "YENI PAYLASIM | @KOLscope | ID: 30 | 19:00:01\n",
                encoding="utf-8")
            count = worker.update(folder)
            self.assertEqual(count, 2)
            a, b = folder / "t7_status.json", folder / "t9_nexora_bridge.json"
            self.assertEqual(stat.S_IMODE(a.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(b.stat().st_mode), 0o600)
            self.assertEqual(json.loads(a.read_text())["mode"], "METADATA_ONLY")
            data = json.loads(b.read_text())
            self.assertEqual(data["mode"], "LOCAL_METADATA_ONLY")
            self.assertFalse(data["social_ai_transfer"])
            safe = from_t10(data)
            self.assertEqual(sum(x["metadata_count"] for x in safe["source_status"]), 2)
            self.assertFalse(safe["listener_running"])

    def test_missing_log_fails_without_creating_status_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaises(ValueError):
                worker.update(folder)
            self.assertFalse((folder / "t7_status.json").exists())
            self.assertFalse((folder / "t9_nexora_bridge.json").exists())


if __name__ == "__main__":
    unittest.main()
