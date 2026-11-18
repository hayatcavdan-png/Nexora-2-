"""Sosyal Radar API güvenli varsayılanlar: ağ ve üretim DB gerektirmez."""
import json
import tempfile
import unittest
from pathlib import Path

from nexora.social_ai.radar.api import dashboard
from nexora.social_ai.radar.sources import CATALOG

NOW = 1800000000.0


class SocialRadarApiTests(unittest.TestCase):
    def file(self, data):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "snapshot.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    def record(self):
        return dict(
            schema_version=1, mod="GOZLEM", read_only=True, as_of=NOW - 15,
            sources=[dict(source_id="ansem", live_verified=True,
                          enabled=True, access_mode="LIVE_AUTHORIZED",
                          status="OK", trust_status="verified",
                          last_seen=NOW - 30)],
            olaylar=[dict(
                olay=dict(first_source="ansem",
                          token_mint="So11111111111111111111111111111111111111112",
                          mint_status="VERIFIED", observed_at=NOW - 30),
                karar=dict(sinif="SOSYAL_ERKEN_UYARI", gerekce=["ZINCIR_TEYIDI"]),
                timely=True)],
        )

    def test_missing_snapshot_is_not_live(self):
        out = dashboard(now=NOW)
        self.assertEqual(out["snapshot_status"], "BAGLANTI_BEKLENIYOR")
        self.assertEqual(len(out["sources"]), len(CATALOG))
        self.assertEqual(out["alerts"], [])
        self.assertFalse(out["live_enabled"])
        self.assertTrue(all(not x["live_verified"] for x in out["sources"]))

    def test_mock_snapshot_is_not_live(self):
        data = self.record()
        data["mod"] = "MOCK"
        out = dashboard(self.file(data), now=NOW)
        self.assertEqual(out["snapshot_status"], "CANLI_KANIT_YOK")
        self.assertEqual(out["alerts"], [])
        self.assertFalse(out["live_enabled"])

    def test_stale_snapshot_rejected(self):
        data = self.record()
        data["as_of"] = NOW - 2000
        out = dashboard(self.file(data), now=NOW)
        self.assertEqual(out["snapshot_status"], "SNAPSHOT_ESKI")
        self.assertFalse(out["live_enabled"])

    def test_unverified_source_has_no_live_alerts(self):
        data = self.record()
        data["sources"][0]["trust_status"] = "unverified"
        out = dashboard(self.file(data), now=NOW)
        self.assertFalse(out["live_enabled"])
        self.assertEqual(out["alerts"], [])

    def test_verified_snapshot_projects_only_allowed_fields(self):
        data = self.record()
        data["olaylar"][0]["olay"]["secret"] = "PRIVATE"
        data["sources"][0].update(last_seen=NOW - 1000, lag_seconds=30)
        out = dashboard(self.file(data), now=NOW)
        self.assertTrue(out["live_enabled"])
        self.assertEqual(len(out["alerts"]), 1)
        self.assertEqual(out["alerts"][0]["source_id"], "ansem")
        source = next(s for s in out["sources"] if s["source_id"] == "ansem")
        self.assertEqual((source["last_seen"], source["lag_seconds"]), (NOW - 1000, 30))
        self.assertNotIn("PRIVATE", json.dumps(out))

    def test_event_requires_valid_mint_and_time(self):
        data = self.record()
        data["olaylar"][0]["olay"]["token_mint"] = "NOT_A_MINT"
        self.assertEqual(dashboard(self.file(data), now=NOW)["alerts"], [])

    def test_malformed_or_future_snapshot_evidence_is_ignored(self):
        data = self.record()
        event = data["olaylar"][0]
        data["olaylar"] += [
            dict(event, olay=dict(event["olay"], first_source=[])),
            dict(event, karar=dict(event["karar"], sinif={})),
            dict(event, olay=dict(event["olay"], observed_at=10**400)),
            dict(event, olay=dict(event["olay"], observed_at=NOW)),
        ]
        data["sources"][0].update(last_seen={"secret": "PRIVATE"}, lag_seconds=float("inf"))
        event["karar"]["gerekce"] += [{"secret": "PRIVATE"}, "raw social text"]
        out = dashboard(self.file(data), now=NOW)
        self.assertEqual([a["reason_codes"] for a in out["alerts"]], [["ZINCIR_TEYIDI"]])
        self.assertNotIn("PRIVATE", json.dumps(out, allow_nan=False))

    def test_unavailable_path_is_safe(self):
        out = dashboard("/definitely-not-exists-nexora-social.json", now=NOW)
        self.assertEqual(out["snapshot_status"], "SNAPSHOT_OKUNAMADI")
        self.assertFalse(out["live_enabled"])


if __name__ == "__main__":
    unittest.main()
