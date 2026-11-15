import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from nexora.core import Paper, CFG
from nexora.constants import USDC_MINT
from nexora.decision import Decider
from test_decision import FakeQuoter, Safe, TOK
import golge_rapor

class ShadowTests(unittest.TestCase):
    def make(self, path=":memory:", **kw):
        self.p, self.q = Paper(path), FakeQuoter(**kw)
        return Decider(self.p, self.q, Safe())
    def test_rejected_buy_opens_shadow_without_touching_cash(self):
        d = self.make(back_ratio=0.919)                                       # %8.1 al-sat kaybı
        self.assertIn("al-sat kaybı yüksek", d.decide("b1", "W", TOK, "buy", 1)["reason"])
        sh = self.p.shadows()
        self.assertEqual((len(sh), sh[0]["status"], sh[0]["size_usd"]), (1, "open", 5.0))
        self.assertAlmostEqual(sh[0]["rt_loss_pct"], 8.1, places=1)
        self.assertEqual((self.p.cash(), self.p.portfolio()["positions"]), (100.0, []))
    def test_source_sell_closes_shadow_with_real_quote(self):
        d = self.make(back_ratio=0.919); d.decide("b1", "W", TOK, "buy", 1)
        self.q.sell_price = 1.5                                               # token %50 değerlendi
        r = d.decide("s1", "W", TOK, "sell", 1)
        self.assertIn("sahip olunmayan", r["reason"])                         # gerçek portföyde pozisyon yok
        sh = self.p.shadows()[0]
        self.assertEqual(sh["status"], "closed"); self.assertAlmostEqual(sh["pnl_usd"], 7.5 - 5.0 - 2 * CFG["net_fee_usd"])
        self.assertEqual(self.p.cash(), 100.0)
    def test_impact_reject_also_shadowed(self):
        d = self.make(impact=5); d.decide("b1", "W", TOK, "buy", 1)
        sh = self.p.shadows()[0]; self.assertIsNone(sh["rt_loss_pct"]); self.assertEqual(sh["impact_pct"], 5)
    def test_other_wallet_sell_does_not_close(self):
        d = self.make(back_ratio=0.919); d.decide("b1", "W", TOK, "buy", 1)
        d.decide("s1", "BASKA", TOK, "sell", 1)
        self.assertEqual(self.p.shadows()[0]["status"], "open")
    def test_unsellable_at_exit_recorded_as_total_loss(self):
        d = self.make(back_ratio=0.919); d.decide("b1", "W", TOK, "buy", 1)
        self.q.fail.add((TOK, USDC_MINT)); d.decide("s1", "W", TOK, "sell", 1)
        sh = self.p.shadows()[0]
        self.assertEqual(sh["status"], "satilamadi"); self.assertAlmostEqual(sh["pnl_usd"], -5.0 - 2 * CFG["net_fee_usd"])
    def test_accepted_buy_not_shadowed_and_duplicate_ignored(self):
        d = self.make(); d.decide("b1", "W", TOK, "buy", 1)
        self.assertEqual(self.p.shadows(), [])
        p = Paper(); self.assertTrue(p.shadow_open("e", "W", TOK, 5, 100, 6, 9, None, "x"))
        self.assertFalse(p.shadow_open("e", "W", TOK, 5, 100, 6, 9, None, "x"))
    def test_open_shadow_cap(self):
        p = Paper()
        for i in range(Paper.MAX_OPEN_SHADOWS): p.shadow_open(f"e{i}", "W", f"T{i}", 5, 100, 6, 9, None, "x")
        self.assertFalse(p.shadow_open("fazla", "W", "T", 5, 100, 6, 9, None, "x"))
    def test_report_buckets(self):
        path = os.path.join(tempfile.mkdtemp(), "p.db")
        d = self.make(path, back_ratio=0.919)
        d.decide("b1", "W", TOK, "buy", 1); self.q.sell_price = 1.5; d.decide("s1", "W", TOK, "sell", 1)
        self.q.back_ratio, self.q.sell_price = 0.80, None; d.decide("b2", "W", "T2", "buy", 1)
        out = golge_rapor.report(path)
        self.assertIn("Gölge işlem: 2 (açık 1, kapanmış 1)", out)
        self.assertIn("al-sat %8-10", out); self.assertIn("+2.48$", out); self.assertIn("al-sat %15+", out)
        self.assertIn("Paper veritabanı yok", golge_rapor.report("/yok/boyle.db"))
if __name__ == "__main__": unittest.main()
