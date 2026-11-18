"""No-key, no-network profit model tests with precommitted forward data."""
import json
import unittest

from nexora.strategy_lab.profit_engine import (
    HORIZONS, MATURITY_S, review, ProfitEvidenceError,
)
from nexora.social_ai.paper_watch import initial_state

START = 1_800_000_000
MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"


def study(ts, *, success=(5, 15, 30, 60), net=0.30, gap=0):
    horizons = {}
    for minutes in HORIZONS:
        horizons[f"{minutes}dk"] = (
            {"status": "OK", "measured_at": ts + minutes * 60 + 1,
             "net_usdt": str(net)} if minutes in success
            else {"status": "UNKNOWN", "net_usdt": None,
                  "reason": "QUOTE_UNAVAILABLE"})
    return {
        "observed_at": ts,
        "mint": MINT,
        "token_qty_raw": "500000",
        "reserved_cost_usdt": "4.08",
        "horizons": horizons,
    }


def state_with(count, *, spacing=7200, success=(5, 15, 30, 60), net=0.30):
    result = initial_state()
    result["entries"] = [
        study(START + i * spacing, success=success, net=net)
        for i in range(count)
    ]
    last = START + (count - 1) * spacing if count else START
    return result, last + MATURITY_S + 1


class ProfitEngineTests(unittest.TestCase):
    def test_empty_ledger_no_false_profit_or_horizon(self):
        result = review(initial_state(), as_of=START)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["recommended_horizon_min"])
        self.assertTrue(result["intake"]["allow_new_paper"])
        self.assertFalse(result["real_order"])
        self.assertFalse(result["forward_stress"]["realized_profit"])

    def test_mature_early_quotes_select_forward_horizon_only(self):
        state, now = state_with(65)
        # 5-minute quotes are consistently modest; later quotes unavailable.
        for row in state["entries"]:
            for minute in (15, 30, 60):
                row["horizons"][f"{minute}dk"] = {"status": "UNKNOWN"}
        result = review(state, as_of=now)
        self.assertEqual(result["recommended_horizon_min"], 5)
        self.assertEqual(result["status"], "PAPER_EDGE_CANDIDATE")
        self.assertEqual(result["horizons"][0]["quotes_available"], 65)
        self.assertGreaterEqual(result["forward_stress"]["selected_paper_studies"], 20)
        self.assertGreater(result["forward_stress"]["stress_net_usdt"], 0)
        self.assertNotIn(MINT, json.dumps(result))
        self.assertFalse(result["real_order"])

    def test_no_lookahead_when_observations_overlap(self):
        state, now = state_with(70, spacing=60)
        result = review(state, as_of=now)
        self.assertEqual(result["mature_samples"], 70)
        self.assertEqual(result["forward_stress"]["selected_paper_studies"], 0)
        self.assertIsNotNone(result["recommended_horizon_min"])
        self.assertNotEqual(result["status"], "PAPER_EDGE_CANDIDATE")

    def test_missing_quotes_stress_not_pretend_wins(self):
        state, now = state_with(40, success=(), net=0.30)
        result = review(state, as_of=now)
        self.assertIsNone(result["recommended_horizon_min"])
        self.assertEqual(result["status"], "NO_VALID_EDGE")
        self.assertLess(result["horizons"][0]["stress_average_net_usdt"], -4.0)
        self.assertEqual(result["intake"]["reason"], "CIRCUIT_BREAKER_COOLDOWN")
        self.assertFalse(result["intake"]["allow_new_paper"])
        later = review(state, as_of=now+3700)
        self.assertTrue(later["intake"]["allow_new_paper"])
        self.assertEqual(later["intake"]["reason"], "CAUTIOUS_RESEARCH_AFTER_COOLDOWN")

    def test_outlier_cannot_certify_a_win(self):
        state, now = state_with(35, net=-0.1)
        first = state["entries"][0]
        first["horizons"]["5dk"]["net_usdt"] = "500"
        for item in state["entries"]:
            for minutes in (15, 30, 60):
                item["horizons"][f"{minutes}dk"] = {"status": "UNKNOWN"}
        result = review(state, as_of=now)
        self.assertIsNone(result["recommended_horizon_min"])
        self.assertLess(result["horizons"][0]["stress_average_net_usdt"], 0.2)

    def test_future_measurement_cannot_be_used(self):
        state, now = state_with(35)
        for item in state["entries"]:
            item["horizons"]["5dk"]["measured_at"] = item["observed_at"] + 9999
            for minutes in (15, 30, 60):
                item["horizons"][f"{minutes}dk"] = {"status": "UNKNOWN"}
        result = review(state, as_of=now)
        self.assertIsNone(result["recommended_horizon_min"])
        self.assertEqual(result["horizons"][0]["quotes_available"], 0)

    def test_as_of_and_invalid_mode_fail_closed(self):
        with self.assertRaises(ProfitEvidenceError):
            review(initial_state(), as_of=float("nan"))
        state, _ = state_with(10)
        self.assertEqual(review(state, as_of=START)["mature_samples"], 0)
        state["real_order"] = True
        result = review(state, as_of=START+200000)
        self.assertEqual(result["status"], "EVIDENCE_INVALID")
        self.assertFalse(result["intake"]["allow_new_paper"])

    def test_last_horizon_cannot_enter_earlier_training(self):
        state, now = state_with(60, spacing=3600)
        result = review(state, as_of=now)
        # Entries arrive hourly, but a 60m quote is not mature until +2m.
        # The model may train only on older, fully settled candidates.
        self.assertGreater(result["forward_stress"]["selected_paper_studies"], 0)
        self.assertLess(result["forward_stress"]["selected_paper_studies"], 60)


if __name__ == "__main__":
    unittest.main()
