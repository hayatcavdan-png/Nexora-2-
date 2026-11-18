"""NEXORA seven-tool Strategy Lab core is isolated, fail-closed and offline."""
import json
from pathlib import Path
import tempfile
import unittest

from nexora.strategy_lab.engine import LabInputError, backtest, rank_candidates
from nexora.strategy_lab.integrations import sdk_pool_snapshot, capabilities
from nexora.strategy_lab.report import empty, read_snapshot, sanitize


def bars(n=35):
    return [{
        "ts": 1_800_000_000 + i*60,
        "open": str(1 + i*.01),
        "high": str(1.02 + i*.01),
        "low": str(.99 + i*.01),
        "close": str(1 + i*.01),
    } for i in range(n)]


def candidate():
    return {
        "mint": "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw",
        "mint_checked": True, "sell_route_checked": True,
        "liquidity_checked": True, "holders_checked": True,
        "quote_fresh": True, "danger_flag": False,
        "liquidity_score": 80, "wallet_score": 65,
        "momentum_score": 75, "risk_score": 90,
    }


class StrategyLabTests(unittest.TestCase):
    def test_defaults_make_no_real_trades(self):
        out = empty()
        self.assertFalse(out["real_order"])
        self.assertFalse(out["live_trading"])
        self.assertEqual(out["equity"], [])
        self.assertEqual(len(out["capabilities"]), 7)
        self.assertTrue(all(not x["used_for_orders"] for x in capabilities().values()))

    def test_next_open_no_future_candle_leak(self):
        sample = bars()
        a = backtest(sample)
        b = backtest(sample)
        self.assertEqual(a, b)
        self.assertEqual(a["mode"], "HISTORICAL_PAPER_ONLY")
        self.assertFalse(a["real_order"])
        self.assertEqual(a["initial_usdt"], "100")
        self.assertEqual(len(a["equity"]), len(sample))
        self.assertTrue(all(t["source"] == "NEXT_OPEN" for t in a["trades"]))
        self.assertTrue(all(0 < len(str(t["price_usdt"])) for t in a["trades"]))

    def test_bad_prices_and_times_rejected(self):
        for edit in [
            ("ts", 1_800_000_000),
            ("open", "-1"),
            ("high", "nan"),
            ("low", "99999"),
            ("close", "0"),
        ]:
            with self.subTest(edit=edit):
                sample = bars()
                sample[5][edit[0]] = edit[1]
                with self.assertRaises(LabInputError):
                    backtest(sample)
        with self.assertRaises(LabInputError):
            backtest(bars(2), fee_bps=-1)
        self.assertEqual(backtest(bars(10), fee_bps=0, slippage_bps=0)["initial_usdt"], "100")

    def test_evidence_gate_is_not_buy_instruction(self):
        row = candidate()
        ranked = rank_candidates([row])
        self.assertEqual(ranked[0]["status"], "RESEARCH_ONLY")
        self.assertGreater(ranked[0]["score"], 0)
        self.assertFalse(ranked[0]["real_order"])
        for key in ("mint_checked", "sell_route_checked", "holders_checked"):
            sample = candidate()
            sample[key] = False
            self.assertEqual(rank_candidates([sample])[0]["status"], "INSUFFICIENT_EVIDENCE")
        sample = candidate()
        sample["danger_flag"] = True
        self.assertIsNone(rank_candidates([sample])[0]["score"])

    def test_sdk_normalizer_is_readonly_unverified(self):
        data = {"schema_version": 1, "mode": "SDK_READ_ONLY",
                "real_order": False, "pools": [
                    {"source": "raydium",
                     "mint": candidate()["mint"],
                     "pool_id": "So11111111111111111111111111111111111111112",
                     "api_key": "dont-leak"},
                    {"source": "telegram", "mint": candidate()["mint"],
                     "pool_id": "So11111111111111111111111111111111111111112"},
                ]}
        out = sdk_pool_snapshot(data)
        self.assertEqual(len(out["pools"]), 1)
        self.assertEqual(out["pools"][0]["status"], "UNVERIFIED_POOL_OBSERVATION")
        self.assertNotIn("dont-leak", json.dumps(out))
        bad = dict(data, real_order=True)
        with self.assertRaises(LabInputError):
            sdk_pool_snapshot(bad)

    def test_snapshot_sanitizes_unknown_fields(self):
        report = {"schema_version": 1, "mode": "PAPER_STRATEGY_LAB",
                  "real_order": False, "api_key": "private",
                  "candidates": [candidate()],
                  "equity": backtest(bars())["equity"]}
        result = sanitize(report)
        self.assertEqual(result["snapshot_status"], "OFFLINE_SNAPSHOT")
        self.assertEqual(len(result["equity"]), 35)
        self.assertEqual(result["summary"]["profitable_proven"], False)
        self.assertNotIn("private", json.dumps(result))

    def test_optional_metrics_without_base_history(self):
        item = {"schema_version":1,"mode":"PAPER_STRATEGY_LAB","real_order":False,
                "equity":[],"candidates":[],
                "optional_reports":{"vectorbt":{
                    "real_order":False,"final_equity_usdt":101.25,
                    "api_key":"DO_NOT_LEAK"}}}
        data = sanitize(item)
        self.assertEqual(data["optional_reports"]["vectorbt"]["final_equity_usdt"], 101.25)
        self.assertNotIn("DO_NOT_LEAK", json.dumps(data))

    def test_snapshot_defaults_and_invalid_files(self):
        self.assertEqual(read_snapshot("")["snapshot_status"], "NOT_CONFIGURED")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.json"
            path.write_text("corrupt", encoding="utf-8")
            self.assertEqual(read_snapshot(str(path))["snapshot_status"], "UNAVAILABLE")
            path.write_text(json.dumps({
                "schema_version": 1, "mode": "PAPER_STRATEGY_LAB",
                "real_order": False, "candidates": [], "equity": []}))
            self.assertEqual(read_snapshot(str(path))["snapshot_status"], "OFFLINE_SNAPSHOT")


if __name__ == "__main__":
    unittest.main()
