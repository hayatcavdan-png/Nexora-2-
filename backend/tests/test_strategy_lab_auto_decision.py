"""Offline tests: no signing, orders, wallet keys, network or production DB."""
import unittest

from nexora.strategy_lab.auto_decision import entry_signal, exit_signal
from nexora.social_ai.paper_watch import initial_state, open_study, settle_horizon

NOW = 1_800_000_000
MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"


def candidate():
    return {
        "mode": "READ_ONLY_RESEARCH",
        "status": "RESEARCH_CANDIDATE",
        "real_order": False,
        "quote_only": True,
        "paper_entry": False,
        "social_ai_transfer": False,
        "mint": MINT,
        "observed_at": NOW - 1,
        "buy_in_usdt": "4",
        "expected_token_qty_raw": "500000",
        "liquidity_usd": "45000",
        "quote_roundtrip_pct": "5",
        "buy_price_impact_pct": "1",
        "sell_price_impact_pct": "1",
        "immediate_sell_quote_usdt": "3.8",
    }


def position():
    return {"observed_at": NOW, "token_qty_raw": "500000",
            "reserved_cost_usdt": "4.08"}


def quote(out=5_000_000, impact=1):
    return {"in_amount": 500000, "out_amount": out,
            "price_impact_pct": impact}


class AutoDecisionTests(unittest.TestCase):
    def test_only_verified_quotes_make_paper_entry(self):
        result = entry_signal(candidate(), now=NOW)
        self.assertEqual(result["action"], "OPEN_PAPER_STUDY")
        self.assertFalse(result["real_order"])
        self.assertFalse(result["signer_used"])
        self.assertNotIn("predicted_win_probability", result)

    def test_fail_closed_no_proof_or_market_evidence(self):
        failures = [
            ("mode", "SOCIAL_POST"),
            ("real_order", True),
            ("quote_only", False),
            ("paper_entry", True),
            ("liquidity_usd", "1000"),
            ("quote_roundtrip_pct", "15"),
            ("quote_roundtrip_pct", "-1"),
            ("buy_price_impact_pct", "2.5"),
            ("sell_price_impact_pct", None),
            ("immediate_sell_quote_usdt", "7.0"),
            ("expected_token_qty_raw", "0"),
            ("mint", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
        ]
        for key, value in failures:
            with self.subTest(key=key, value=value):
                item = candidate()
                item[key] = value
                self.assertEqual(entry_signal(item, now=NOW)["action"], "SKIP")
        self.assertEqual(entry_signal(candidate(), now=NOW+60)["reason"], "QUOTE_STALE")
        self.assertEqual(entry_signal(candidate(), now=NOW-60)["reason"], "QUOTE_STALE")
        self.assertEqual(entry_signal({}, now=NOW)["action"], "SKIP")

    def test_paper_exit_signal_with_real_quote_not_fills(self):
        take = exit_signal(position(), quote(out=5_000_000),
                           observed_at=NOW+301, now=NOW+301)
        stop = exit_signal(position(), quote(out=3_000_000),
                           observed_at=NOW+301, now=NOW+301)
        hold = exit_signal(position(), quote(out=4_300_000),
                           observed_at=NOW+301, now=NOW+301)
        timeout = exit_signal(position(), quote(out=4_300_000),
                              observed_at=NOW+3601, now=NOW+3601)
        self.assertEqual((take["action"], take["reason"]),
                         ("PAPER_SELL_SIGNAL", "TAKE_PROFIT"))
        self.assertEqual((stop["action"], stop["reason"]),
                         ("PAPER_SELL_SIGNAL", "STOP_LOSS"))
        self.assertEqual(hold["action"], "HOLD")
        self.assertEqual(timeout["reason"], "TIME_LIMIT")
        self.assertFalse(take["real_order"])
        self.assertTrue(take["estimated_not_executed"])

    def test_missing_quote_cannot_fake_stop_sale(self):
        out = exit_signal(position(), {}, observed_at=NOW+301, now=NOW+301)
        self.assertEqual(out["action"], "EXIT_UNAVAILABLE")
        self.assertNotIn("hypothetical_net_return_pct", out)
        self.assertEqual(exit_signal(position(), quote(), observed_at=NOW,
                                      now=NOW+100)["reason"], "QUOTE_STALE")

    def test_sell_signals_attach_to_existing_research_horizon(self):
        state = initial_state()
        self.assertTrue(open_study(state, candidate(), now=NOW)["opened"])
        result = settle_horizon(state, MINT, "5dk",
                                now=NOW+301, quote=quote())
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["lab_exit_signal"]["reason"], "TAKE_PROFIT")
        self.assertFalse(result["lab_exit_signal"]["real_order"])
        self.assertTrue(state["entries"][0]["reserved"])
        self.assertEqual(state["available_research_cash_usdt"], "95.92")


if __name__ == "__main__":
    unittest.main()
