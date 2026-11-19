"""Founder-private paper automation summary is redacted and default-off."""
import json
from pathlib import Path
import tempfile
import unittest

from nexora.strategy_lab.report import auto_paper_status
from nexora.social_ai.paper_watch import Store, open_study, settle_horizon

NOW = 1_800_000_000
MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"


class AutoStatusTests(unittest.TestCase):
    def test_no_configuration_never_implies_worker_running(self):
        self.assertEqual(auto_paper_status("", enabled=False)["status"], "DISABLED")
        self.assertEqual(auto_paper_status("", enabled=True)["status"],
                         "PATH_NOT_CONFIGURED")
        self.assertFalse(auto_paper_status("", enabled=True)["real_order"])

    def test_private_summary_only_returns_aggregates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "isolated.json")
            store = Store(path)
            data = {
                "mode": "READ_ONLY_RESEARCH",
                "status": "RESEARCH_CANDIDATE",
                "real_order": False,
                "quote_only": True,
                "paper_entry": False,
                "social_ai_transfer": False,
                "mint": MINT,
                "observed_at": NOW,
                "expected_token_qty_raw": "500000",
                "planned_exit_horizon_min": 5,
                "api_key": "SECRET_NOT_ALLOWED_IN_HTTP",
            }
            store.mutate(lambda state: open_study(state, data, now=NOW))
            before = auto_paper_status(path, enabled=True)
            self.assertEqual(before["total_studies"], 1)
            self.assertEqual(before["active_recent_studies"], 1)
            self.assertEqual(before["status"], "LEDGER_AVAILABLE")
            self.assertEqual(before["ai_signal_research"]["status"], "SHADOW_LEARNING")
            self.assertFalse(before["ai_signal_research"]["may_filter_new_paper"])
            self.assertFalse(before["worker_running_verified"])
            self.assertNotIn(MINT, json.dumps(before))
            self.assertNotIn("SECRET_NOT_ALLOWED_IN_HTTP", json.dumps(before))
            quote = {"in_amount": 500000, "out_amount": 5_000_000,
                     "price_impact_pct": 1}
            store.mutate(lambda state: settle_horizon(state, MINT, "5dk",
                                                       now=NOW+301, quote=quote))
            after = auto_paper_status(path, enabled=True)
            self.assertEqual(after["recent_sell_signals"], 1)
            self.assertEqual(after["precommitted_sell_quote_signals"], 1)
            self.assertEqual(after["precommitted_exit_unavailable"], 0)
            self.assertEqual(after["available_research_cash_usdt"], "95.92")
            self.assertEqual(after["recent_exit_unavailable"], 0)
            self.assertFalse(after["live_trading"])


if __name__ == "__main__":
    unittest.main()
