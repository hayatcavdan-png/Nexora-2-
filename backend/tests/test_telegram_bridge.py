"""NEXORA's repo-stored Telegram bridge must remain metadata-only."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from nexora.social_ai.telegram_bridge import (
    BridgeUnavailable, from_t10, read_t10
)

NOW = 1800000000


def fixture():
    return {
        "schema_version": 1,
        "mode": "LOCAL_METADATA_ONLY",
        "social_ai_transfer": False,
        "updated_at": datetime.fromtimestamp(NOW-10, tz=timezone.utc).isoformat(),
        "source_status": [
            {"source_id": "solana_early_trending", "platform": "telegram",
             "handle": "@solearlytrending", "bridge_status": "LOCAL_METADATA_ONLY",
             "metadata_count": 19, "social_ai_transfer": False,
             "live_verified": False},
            {"source_id": "kolscope", "platform": "telegram",
             "handle": "@KOLscope", "bridge_status": "LOCAL_METADATA_ONLY",
             "metadata_count": 91, "social_ai_transfer": False,
             "live_verified": False},
        ]
    }


class TelegramBridgeTests(unittest.TestCase):
    def test_two_sources_only_and_no_content_leak(self):
        source = fixture()
        source["token_mint"] = "a-bad-leak"
        source["api_hash"] = "never-show"
        source["source_status"][0]["text"] = "private-message"
        source["source_status"][0]["session"] = "fake-session"
        result = from_t10(source, now=NOW, worker_status={
            "nexora_tg_bridge": True, "nexora_tg_status": True,
            "nexora_tg_t10": True,
        })
        self.assertEqual(result["mode"], "LOCAL_METADATA_ONLY")
        self.assertEqual(sorted(x["metadata_count"] for x in result["source_status"]), [19, 91])
        self.assertTrue(result["listener_running"])
        self.assertTrue(result["updater_running"])
        self.assertTrue(result["sync_running"])
        self.assertFalse(result["social_ai_transfer"])
        dumped = json.dumps(result)
        for forbidden in ("private-message", "never-show", "fake-session", "token_mint"):
            self.assertNotIn(forbidden, dumped)
        self.assertTrue(all(row["live_verified"] is False for row in result["source_status"]))

    def test_status_not_claimed_from_untrusted_data(self):
        source = fixture()
        source["listener_running"] = True
        source["updater_running"] = True
        source["sync_running"] = True
        result = from_t10(source, now=NOW)
        self.assertFalse(result["listener_running"])
        self.assertFalse(result["updater_running"])
        self.assertFalse(result["sync_running"])

    def test_source_swap_duplicate_and_extra_rejected(self):
        for modification in ("duplicate", "extra", "wrong_handle", "wrong_platform", "wrong_status"):
            with self.subTest(modification=modification):
                data = fixture()
                if modification == "duplicate":
                    data["source_status"][1]["source_id"] = "solana_early_trending"
                elif modification == "extra":
                    data["source_status"].append({})
                elif modification == "wrong_handle":
                    data["source_status"][0]["handle"] = "@fake"
                elif modification == "wrong_platform":
                    data["source_status"][0]["platform"] = "x"
                else:
                    data["source_status"][0]["bridge_status"] = "LIVE"
                with self.assertRaises(BridgeUnavailable):
                    from_t10(data, now=NOW)

    def test_invalid_count_or_enabled_ai_rejected(self):
        for value in (-1, 1.5, True, None, "5", 1_000_001):
            with self.subTest(value=value):
                row = fixture()
                row["source_status"][0]["metadata_count"] = value
                with self.assertRaises(BridgeUnavailable):
                    from_t10(row, now=NOW)
        for key in ("social_ai_transfer", "live_verified"):
            row = fixture()
            row["source_status"][0][key] = True
            with self.assertRaises(BridgeUnavailable):
                from_t10(row, now=NOW)
        row = fixture()
        row["social_ai_transfer"] = True
        with self.assertRaises(BridgeUnavailable):
            from_t10(row, now=NOW)

    def test_stale_future_naive_and_wrong_mode_rejected(self):
        for stamp in (
            datetime.fromtimestamp(NOW-91, tz=timezone.utc).isoformat(),
            datetime.fromtimestamp(NOW+6, tz=timezone.utc).isoformat(),
            "2026-11-18T10:00:00",
            "not-a-date"
        ):
            with self.subTest(stamp=stamp):
                row = fixture()
                row["updated_at"] = stamp
                with self.assertRaises(BridgeUnavailable):
                    from_t10(row, now=NOW)
        row = fixture()
        row["mode"] = "LIVE_AUTHORIZED"
        with self.assertRaises(BridgeUnavailable):
            from_t10(row, now=NOW)

    def test_read_file_and_reject_large_file(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "t9.json"
            p.write_text(json.dumps(fixture()), encoding="utf-8")
            self.assertEqual(read_t10(str(p), now=NOW)["source_status"][0]["metadata_count"], 91)
            p.write_text(" " * 100_001, encoding="utf-8")
            with self.assertRaises(BridgeUnavailable):
                read_t10(str(p), now=NOW)


if __name__ == "__main__":
    unittest.main()
