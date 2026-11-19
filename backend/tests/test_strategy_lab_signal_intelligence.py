"""No-network regression tests: causal learning, conservative AI shadow gate."""
import unittest

from nexora.social_ai.paper_watch import initial_state
from nexora.strategy_lab.profit_engine import MATURITY_S
from nexora.strategy_lab.signal_intelligence import (
    MIN_TRAIN, assess, entry_features, review,
)

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"
T0 = 1_800_000_000


def candidate(now, *, strong=True):
    liquidity = "100000" if strong else "20000"
    roundtrip = "1" if strong else "8"
    buy_impact = "0.2" if strong else "2"
    sell_impact = "0.2" if strong else "2"
    return {
        "mode": "READ_ONLY_RESEARCH",
        "status": "RESEARCH_CANDIDATE",
        "real_order": False,
        "quote_only": True,
        "paper_entry": False,
        "social_ai_transfer": False,
        "mint": MINT,
        "observed_at": now - 1,
        "liquidity_usd": liquidity,
        "quote_roundtrip_pct": roundtrip,
        "buy_price_impact_pct": buy_impact,
        "sell_price_impact_pct": sell_impact,
        "organic_score": "92" if strong else "15",
        "top_holders_pct": "5" if strong else "39",
        "dev_balance_pct": "1" if strong else "19",
        "expected_token_qty_raw": "123456",
        "buy_in_usdt": "4",
        "immediate_sell_quote_usdt": "3.96" if strong else "3.68",
    }


def history(n=70, *, net="0.35", success=True, ex_ante=True):
    state = initial_state()
    good_features = entry_features(candidate(T0))
    for i in range(n):
        ts = T0 + i * 7200
        record = {
            "mint": MINT,
            "observed_at": ts,
            "reserved_cost_usdt": "4.08",
            "planned_exit_horizon_min": 5,
            "plan_decided_at": ts + 1 if ex_ante else ts + 4000,
            "lab_pretrade_features": good_features,
            "horizons": {
                "5dk": {
                    "status": "OK" if success else "UNKNOWN",
                    "net_usdt": net if success else None,
                    "measured_at": ts + 301 if success else None,
                },
                **{f"{m}dk": {"status": "UNKNOWN"} for m in (15, 30, 60)},
            },
        }
        state["entries"].append(record)
    return state


class SignalIntelligenceTests(unittest.TestCase):
    def test_empty_history_stays_shadow_and_has_no_trade_permission(self):
        state = initial_state()
        result = review(state, as_of=T0)
        self.assertEqual(result["status"], "SHADOW_LEARNING")
        self.assertFalse(result["may_filter_new_paper"])
        self.assertFalse(result["real_order"])
        self.assertFalse(result["operator_approval"])
        prediction = assess(candidate(T0), state=state, as_of=T0, validation=result)
        self.assertEqual(prediction["action"], "SHADOW_ONLY")
        self.assertFalse(prediction["order_allowed"])

    def test_causal_positive_forward_validation_enables_only_paper_filter(self):
        state = history()
        now = T0 + 70 * 7200 + MATURITY_S
        result = review(state, as_of=now)
        self.assertEqual(result["trained_samples"], 70)
        self.assertEqual(result["status"], "PAPER_FILTER_VALIDATED")
        self.assertTrue(result["may_filter_new_paper"])
        self.assertGreaterEqual(result["forward"]["walk_forward_checked"], 20)
        self.assertGreater(result["forward"]["selected_stress_lower_bound_usdt"], 0)
        decision = assess(candidate(now), state=state, as_of=now, validation=result)
        self.assertEqual(decision["action"], "PAPER_PRIORITY_CANDIDATE")
        self.assertFalse(decision["real_order"])
        self.assertFalse(decision["order_allowed"])
        self.assertNotIn(MINT, str(result))

    def test_anti_lookahead_excludes_not_yet_mature_history(self):
        state = history(70)
        # Only the first item has fully finished; the next cannot leak.
        result = review(state, as_of=T0 + MATURITY_S + 1)
        self.assertEqual(result["trained_samples"], 1)
        self.assertEqual(result["status"], "SHADOW_LEARNING")
        self.assertFalse(result["may_filter_new_paper"])

    def test_no_precommitted_plan_no_training(self):
        state = history(ex_ante=False)
        result = review(state, as_of=T0 + 70 * 7200 + MATURITY_S)
        self.assertEqual(result["trained_samples"], 0)
        self.assertFalse(result["may_filter_new_paper"])

    def test_missing_exit_quotes_are_loss_stress_not_fabricated_wins(self):
        state = history(success=False)
        out = review(state, as_of=T0 + 70 * 7200 + MATURITY_S)
        self.assertEqual(out["exit_quotes_observed"], 0)
        self.assertFalse(out["may_filter_new_paper"])
        self.assertEqual(out["status"], "SHADOW_LEARNING")

    def test_negative_paper_returns_do_not_activate_ai(self):
        state = history(net="-0.5")
        out = review(state, as_of=T0 + 70 * 7200 + MATURITY_S)
        self.assertEqual(out["status"], "SHADOW_LEARNING")
        self.assertFalse(out["may_filter_new_paper"])

    def test_source_fields_are_bounded_and_unknown_not_invented(self):
        p = candidate(T0)
        self.assertEqual(set(entry_features(p)), {
            "liquidity", "roundtrip", "buy_impact", "sell_impact",
            "organic", "holders", "developer",
        })
        p["organic_score"] = "nan"
        p["top_holders_pct"] = "1e999"
        p["dev_balance_pct"] = None
        features = entry_features(p)
        self.assertEqual(features["organic"], 0.5)
        self.assertEqual(features["holders"], 0.5)
        self.assertEqual(features["developer"], 0.5)
        p["quote_roundtrip_pct"] = -1
        self.assertIsNone(entry_features(p))

    def test_wrong_mode_never_activates_model(self):
        state = history()
        state["real_order"] = True
        out = review(state, as_of=T0 + 70 * 7200 + MATURITY_S)
        self.assertEqual(out["status"], "EVIDENCE_INVALID")
        self.assertFalse(out["may_filter_new_paper"])
        bad = assess(candidate(T0), state=state, as_of=T0, validation=out)
        self.assertEqual(bad["action"], "NO_MODEL_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
