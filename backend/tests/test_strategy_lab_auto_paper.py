"""Offline no-key tests for automated, rate-bounded paper research orchestration."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from nexora.social_ai.paper_watch import Store

SCRIPT = Path(__file__).resolve().parents[2] / "tools/strategy_lab/auto_paper.py"
SPEC = importlib.util.spec_from_file_location("auto_paper_isolated", SCRIPT)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"


def candidate(now):
    return {
        "mode":"READ_ONLY_RESEARCH",
        "status":"RESEARCH_CANDIDATE",
        "real_order": False,
        "quote_only": True,
        "paper_entry": False,
        "social_ai_transfer": False,
        "mint": MINT,
        "expected_token_qty_raw": "123456",
        "observed_at": now-1,
        "buy_in_usdt": "4",
        "liquidity_usd": "45000",
        "quote_roundtrip_pct": "5",
        "buy_price_impact_pct": "1",
        "sell_price_impact_pct": "1",
        "immediate_sell_quote_usdt": "3.8",
    }


class StrategyLabAutoPaperTests(unittest.TestCase):
    def test_quiet_dedup_replay(self):
        now = 1_800_000_000
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory)/"watch.json"))
            def provider(**kwargs):
                self.assertTrue(kwargs["enabled"])
                self.assertLessEqual(kwargs["limit"], 2)
                return {"mode":"READ_ONLY_RESEARCH", "real_order":False,
                        "status":"OK", "results":[candidate(now)]}
            out = auto.cycle(research=provider, store=store, now=now)
            self.assertEqual(out["paper_opened"], 1)
            self.assertFalse(out["real_order"])
            self.assertEqual(store.read()["total_studies"], 1)
            duplicate = auto.cycle(research=provider, store=store, now=now)
            self.assertEqual(duplicate["paper_opened"], 0)
            self.assertEqual(store.read()["total_studies"], 1)

    def test_bad_proof_cannot_open(self):
        now = 1_800_000_000
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory)/"watch.json"))
            for field, invalid in (
                ("status","BLOCKED"), ("real_order",True), ("quote_only",False),
                ("social_ai_transfer",True), ("observed_at",now-1000),
            ):
                with self.subTest(field=field):
                    row = candidate(now); row[field] = invalid
                    result = auto.cycle(research=lambda **kwargs: {
                        "mode":"READ_ONLY_RESEARCH","real_order":False,
                        "status":"OK","results":[row]
                    }, store=store, now=now)
                    self.assertEqual(result["paper_opened"], 0)
            self.assertEqual(store.read()["total_studies"], 0)

    def test_disabled_providers_cannot_open(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory)/"watch.json"))
            res = auto.cycle(research=lambda **kw: {
                "mode":"READ_ONLY_RESEARCH", "status":"DISABLED",
                "real_order":False,"results":[candidate(1800000000)]
            }, store=store, now=1800000000)
            self.assertEqual(res["paper_opened"], 0)
            self.assertEqual(store.read()["total_studies"], 0)


if __name__ == "__main__":
    unittest.main()
