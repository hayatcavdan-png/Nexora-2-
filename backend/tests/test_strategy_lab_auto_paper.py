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


    def test_profitable_history_fixes_exit_plan_before_entry(self):
        from nexora.social_ai.paper_watch import initial_state, open_study
        from nexora.strategy_lab.profit_engine import MATURITY_S
        now = 1_800_500_000
        past = initial_state()
        past["entries"] = [
            {
                "mint": MINT,
                "observed_at": now - MATURITY_S - 100 - i * 7200,
                "reserved_cost_usdt": "4.08",
                "horizons": {
                    "5dk": {"status": "OK", "net_usdt": "0.3",
                             "measured_at": now - MATURITY_S - 100 - i * 7200 + 301},
                    **{f"{m}dk": {"status": "UNKNOWN"} for m in (15, 30, 60)}
                },
            }
            for i in range(35)
        ]
        class SyntheticStore:
            def __init__(self):
                self.private = None

            def _read(self):
                return past

            def mutate(self, callback):
                state = initial_state()
                result = callback(state)
                self.private = state
                return result

        store = SyntheticStore()
        outcome = auto.cycle(
            research=lambda **kwargs: {"mode": "READ_ONLY_RESEARCH",
                                       "status": "OK", "real_order": False,
                                       "results": [candidate(now)]},
            store=store, now=now,
        )
        self.assertEqual(outcome["paper_opened"], 1)
        self.assertEqual(store.private["entries"][0]["planned_exit_horizon_min"], 5)
        self.assertEqual(store.private["entries"][0]["plan_decided_at"], now)
        self.assertFalse(outcome["real_order"])

    def test_full_paper_capacity_skips_expensive_provider_calls(self):
        from nexora.social_ai.paper_watch import initial_state
        now = 1_800_500_000
        state = initial_state()
        state["available_research_cash_usdt"] = "1.00"

        class NoWriteStore:
            def _read(self):
                return state
            def mutate(self, callback):
                raise AssertionError("Paper book must not be written")

        def forbidden_provider(**kwargs):
            raise AssertionError("No provider calls when capital is exhausted")

        result = auto.cycle(research=forbidden_provider,
                            store=NoWriteStore(), now=now)
        self.assertEqual(result["status"], "PAPER_CAPACITY_PAUSED")
        self.assertEqual(result["scanned"], 0)
        self.assertFalse(result["real_order"])

    def test_profit_circuit_breaker_skips_provider_entirely(self):
        from nexora.social_ai.paper_watch import initial_state
        from nexora.strategy_lab.profit_engine import MATURITY_S
        now = 1_800_500_000
        history = initial_state()
        history["entries"] = [
            {
                "mint": MINT,
                "observed_at": now - MATURITY_S - 20 - i * 7200,
                "reserved_cost_usdt": "4.08",
                "horizons": {f"{m}dk": {"status": "UNKNOWN",
                                         "net_usdt": None}
                             for m in (5, 15, 30, 60)},
            }
            for i in range(35)
        ]

        class FixedHistoryStore:
            def _read(self):
                return history

            def mutate(self, callback):
                self_ref = self
                raise AssertionError("no paper write allowed during cooldown")

        def forbidden_provider(**kwargs):
            raise AssertionError("no live provider call during cooldown")

        result = auto.cycle(research=forbidden_provider,
                            store=FixedHistoryStore(), now=now)
        self.assertEqual(result["status"], "PROFIT_GUARD_PAUSED")
        self.assertEqual(result["paper_opened"], 0)
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["profit_guard"], "CIRCUIT_BREAKER_COOLDOWN")
        self.assertFalse(result["real_order"])


if __name__ == "__main__":
    unittest.main()
