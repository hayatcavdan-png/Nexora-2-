"""Isolated 100 USDT quote-only watch: no DB, network, or live orders."""
from copy import deepcopy
from pathlib import Path
import stat
import tempfile
import unittest

from nexora.social_ai import paper_watch as P

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"
OTHER = "So11111111111111111111111111111111111111112"
T0 = 1_800_000_000


def proof(mint=MINT, t0=T0):
    return {
        "mode": "READ_ONLY_RESEARCH", "status": "RESEARCH_CANDIDATE",
        "quote_only": True, "real_order": False, "paper_entry": False,
        "social_ai_transfer": False,
        "mint": mint, "observed_at": t0,
        "expected_token_qty_raw": "500000",
    }


class Quote:
    def __init__(self, *, out=5_000_000, impact=1):
        self.out = out
        self.impact = impact
        self.calls = []

    def quote(self, mint, out, qty):
        self.calls.append((mint, out, qty))
        return {"in_amount": qty, "out_amount": self.out,
                "price_impact_pct": self.impact}


class PaperWatchTests(unittest.TestCase):
    def test_default_cash_and_study_open(self):
        st = P.initial_state()
        r = P.open_study(st, proof(), now=T0 + 2)
        self.assertTrue(r["opened"])
        self.assertEqual(st["available_research_cash_usdt"], "95.92")
        self.assertEqual(st["entries"][0]["reserved_cost_usdt"], "4.08")
        self.assertFalse(st["real_order"])
        self.assertEqual(st["entries"][0]["horizons"]["5dk"]["status"], "PENDING")

    def test_idempotent_mint_across_restarts(self):
        st = P.initial_state()
        self.assertTrue(P.open_study(st, proof(), now=T0 + 1)["opened"])
        dup = proof()
        dup["observed_at"] += 1
        self.assertEqual(P.open_study(st, dup, now=T0+2)["reason"], "DUPLICATE_MINT")
        self.assertEqual(len(st["entries"]), 1)

    def test_untrusted_telegram_and_proof_gates(self):
        for change in [
            {"mode": "LOCAL_METADATA_ONLY"}, {"status": "BLOCKED"},
            {"real_order": True}, {"quote_only": False},
            {"paper_entry": True}, {"social_ai_transfer": True},
            {"expected_token_qty_raw": "0"}, {"mint": "NOT_A_MINT"},
        ]:
            with self.subTest(change=change):
                item = proof()
                item.update(change)
                self.assertFalse(P.open_study(P.initial_state(), item, now=T0+1)["opened"])
        self.assertFalse(P.open_study(P.initial_state(), proof(), now=T0+50)["opened"])

    def test_early_quotes_and_missing_windows(self):
        st = P.initial_state()
        P.open_study(st, proof(), now=T0+1)
        rec = P.settle_horizon(st, MINT, "5dk", now=T0+200,
                               quote={"in_amount": 500000, "out_amount": 5_000_000,
                                      "price_impact_pct": 1})
        self.assertEqual(rec["status"], "PENDING")
        rec = P.settle_horizon(st, MINT, "5dk", now=T0+301,
                               quote={"in_amount": 500000, "out_amount": 5_000_000,
                                      "price_impact_pct": 1})
        self.assertEqual(rec["status"], "OK")
        self.assertEqual(rec["net_usdt"], "0.830000")
        self.assertEqual(rec["quoted_exit_usdt"], "5")
        self.assertTrue(P.expire_missed(st, now=T0+4500))
        self.assertEqual(st["entries"][0]["horizons"]["15dk"]["status"], "UNKNOWN")
        self.assertEqual(st["entries"][0]["horizons"]["60dk"]["status"], "UNKNOWN")
        self.assertEqual(P.settle_horizon(st, MINT, "5dk", now=T0+4500)["net_usdt"], "0.830000")

    def test_late_quote_cannot_fill_historical_horizon(self):
        st = P.initial_state()
        P.open_study(st, proof(), now=T0)
        quote = {"in_amount": 500000, "out_amount": 20_000_000, "price_impact_pct": 1}
        res = P.settle_horizon(st, MINT, "5dk", now=T0+900, quote=quote)
        self.assertEqual(res["status"], "UNKNOWN")
        self.assertEqual(res["reason"], "WINDOW_MISSED")
        self.assertIsNone(res["net_usdt"])

    def test_missing_and_invalid_exit_quotes(self):
        st = P.initial_state()
        P.open_study(st, proof(), now=T0+1)
        res = P.settle_horizon(st, MINT, "5dk", now=T0+310, quote={
            "in_amount": 500000, "out_amount": 5000000, "price_impact_pct": None,
        })
        self.assertEqual(res["reason"], "QUOTE_INVALID")

    def test_bounded_active_paper_studies(self):
        st = P.initial_state()
        tokens = [MINT, OTHER,
                  "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                  "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
                  "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"]
        for mint in tokens:
            if mint == P.USDT_MINT:
                self.assertFalse(P.open_study(st, proof(mint), now=T0)["opened"])
            else:
                self.assertTrue(P.open_study(st, proof(mint), now=T0)["opened"])
        self.assertGreater(P._valid_state(st), 0)

    def test_store_atomic_private_and_refresh_due(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.json"
            store = P.Store(str(path))
            self.assertEqual(store.read()["total_studies"], 0)
            opened = store.mutate(lambda s: P.open_study(s, proof(), now=T0+1))
            self.assertTrue(opened["opened"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(store.read()["total_studies"], 1)
            self.assertEqual(store.mutate(lambda s: P.open_study(s, proof(), now=T0+2))["reason"],
                             "DUPLICATE_MINT")
            quote = Quote(out=5_000_000)
            before = P.refresh_due(store, quote, now=T0+250)
            self.assertEqual(len(quote.calls), 0)
            self.assertEqual(before["entries"][0]["horizons"]["5dk"]["status"], "PENDING")
            after = P.refresh_due(store, quote, now=T0+310)
            self.assertEqual(quote.calls, [(MINT, P.USDT_MINT, 500000)])
            self.assertEqual(after["entries"][0]["horizons"]["5dk"]["status"], "OK")
            self.assertEqual(after["entries"][0]["horizons"]["5dk"]["net_usdt"], "0.830000")

    def test_exit_plan_is_frozen_at_entry_and_only_quote_based(self):
        st = P.initial_state()
        p = proof()
        p["planned_exit_horizon_min"] = 5
        self.assertTrue(P.open_study(st, p, now=T0 + 1)["opened"])
        self.assertEqual(st["entries"][0]["planned_exit_horizon_min"], 5)
        self.assertEqual(st["entries"][0]["plan_decided_at"], T0 + 1)
        five = P.settle_horizon(st, MINT, "5dk", now=T0+301,
                                quote={"in_amount": 500000, "out_amount": 5_000_000,
                                       "price_impact_pct": 1})
        self.assertEqual(five["precommitted_exit"]["status"], "HYPOTHETICAL_QUOTE_ONLY")
        self.assertEqual(five["precommitted_exit"]["net_usdt"], "0.830000")
        self.assertFalse(five["precommitted_exit"]["actual_execution"])
        fifteen = P.settle_horizon(st, MINT, "15dk", now=T0+901,
                                   quote={"in_amount": 500000, "out_amount": 9_000_000,
                                          "price_impact_pct": 1})
        self.assertNotIn("precommitted_exit", fifteen)
        self.assertEqual(st["entries"][0]["planned_exit_horizon_min"], 5)

    def test_planned_exit_missing_quote_is_not_fabricated(self):
        st = P.initial_state()
        p = proof()
        p["planned_exit_horizon_min"] = 5
        self.assertTrue(P.open_study(st, p, now=T0)["opened"])
        five = P.settle_horizon(st, MINT, "5dk", now=T0+301, quote=None)
        self.assertEqual(five["precommitted_exit"]["status"], "UNAVAILABLE")
        self.assertIsNone(five["precommitted_exit"]["net_usdt"])
        st2 = P.initial_state()
        p["planned_exit_horizon_min"] = 7
        self.assertEqual(P.open_study(st2, p, now=T0)["reason"],
                         "INVALID_PRECOMMITTED_HORIZON")

    def test_file_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = P.Store(str(Path(folder) / "ledger.json"))
            self.assertRaises(P.PaperWatchError, P.Store, "relative.json")
            store.mutate(lambda s: P.open_study(s, proof(), now=T0))
            Path(folder, "ledger.json").write_text("bad JSON", encoding="utf-8")
            with self.assertRaises(ValueError):
                store.read()


if __name__ == "__main__":
    unittest.main()
