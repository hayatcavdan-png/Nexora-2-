"""Offline, fake-provider CI for the combined paper signal -> quote-exit loop."""
import importlib.util
from pathlib import Path
import unittest

from nexora.social_ai.paper_watch import initial_state, open_study, public_status

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nexora_ai_paper_runner_test", ROOT / "tools/strategy_lab/ai_paper_runner.py"
)
# Path lookup for auto_paper import without external dependencies.
import sys
TOOL_DIR = str(ROOT / "tools/strategy_lab")
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"
NOW = 1_800_000_000


def candidate():
    return {
        "mode": "READ_ONLY_RESEARCH", "status": "RESEARCH_CANDIDATE",
        "real_order": False, "quote_only": True, "paper_entry": False,
        "social_ai_transfer": False, "mint": MINT,
        "observed_at": NOW - 1, "expected_token_qty_raw": "123456",
        "buy_in_usdt": "4", "liquidity_usd": "100000",
        "quote_roundtrip_pct": "1", "buy_price_impact_pct": "0.2",
        "sell_price_impact_pct": "0.2",
        "immediate_sell_quote_usdt": "3.96",
        "organic_score": "80", "top_holders_pct": "5",
        "dev_balance_pct": "1",
    }


class MemoryStore:
    def __init__(self):
        self.history = initial_state()

    def _read(self):
        return self.history

    def mutate(self, callback):
        return callback(self.history)


class SignalRunnerTests(unittest.TestCase):
    def test_refresh_runs_before_new_signal_and_persists_ex_ante_inputs(self):
        store = MemoryStore()
        order = []

        def refresher(store, quoter, *, now, max_quotes):
            order.append("refresh")
            self.assertEqual(max_quotes, 3)
            return public_status(store._read())

        def provider(**kwargs):
            order.append("research")
            self.assertEqual(kwargs["limit"], 2)
            return {"mode": "READ_ONLY_RESEARCH", "status": "OK",
                    "real_order": False, "results": [candidate()]}

        out = runner.tick(store=store, quoter=None, research=provider,
                          now=NOW, refresh=refresher)
        self.assertEqual(order, ["refresh", "research"])
        self.assertEqual(out["paper_entries"], 1)
        self.assertFalse(out["real_order"])
        self.assertEqual(store.history["entries"][0]["planned_exit_horizon_min"], 5)
        self.assertEqual(store.history["entries"][0]["lab_ai_action_at_entry"], "SHADOW_ONLY")
        features = store.history["entries"][0]["lab_pretrade_features"]
        self.assertEqual(len(features), 7)
        self.assertGreater(features["liquidity"], 0)
        self.assertNotIn("api_key", features)

    def test_exit_only_never_scans_candidates(self):
        store = MemoryStore()
        called = []

        def refresh(store, quoter, **kwargs):
            called.append("quote-monitor")
            return public_status(store._read())

        def blocked(**kwargs):
            raise AssertionError("No new discovery when scan=False")

        out = runner.tick(store=store, quoter=None, research=blocked,
                          now=NOW, scan=False, refresh=refresh)
        self.assertEqual(called, ["quote-monitor"])
        self.assertEqual(out["status"], "EXIT_MONITOR_ONLY")
        self.assertEqual(out["paper_entries"], 0)

    def test_unsafe_refresh_response_blocks_provider(self):
        store = MemoryStore()
        def forbidden(**kwargs):
            raise AssertionError("Unsafe refresh must block provider")

        with self.assertRaises(ValueError):
            runner.tick(store=store, quoter=None, research=forbidden,
                        now=NOW, refresh=lambda *a, **k: {
                            "mode": "QUOTE_PAPER_RESEARCH",
                            "real_order": True, "total_studies": 0
                        })

    def test_no_fabricated_exit_when_sell_route_unavailable(self):
        from nexora.social_ai.paper_watch import settle_horizon
        store = MemoryStore()
        c = candidate()
        c["planned_exit_horizon_min"] = 5
        opened = store.mutate(lambda state: open_study(state, c, now=NOW))
        self.assertTrue(opened["opened"])
        result = store.mutate(
            lambda state: settle_horizon(state, MINT, "5dk", now=NOW + 300, quote=None)
        )
        self.assertEqual(result["precommitted_exit"]["action"], "EXIT_UNAVAILABLE")
        self.assertIsNone(result["precommitted_exit"]["net_usdt"])
        self.assertFalse(result["precommitted_exit"]["actual_execution"])


if __name__ == "__main__":
    unittest.main()
