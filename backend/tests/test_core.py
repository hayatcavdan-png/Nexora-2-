import sys, unittest; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nexora.core import Paper

class T(unittest.TestCase):
    def setUp(self): self.p = Paper()
    def buy(self, e, tok="T1", liq=1e6, age=1): return self.p.handle_signal(e, "W", tok, "buy", 1.0, liq, age)
    def test_buy_sizing(self):
        self.assertEqual(self.buy("e1")["decision"], "KOPYALANDI")
        self.assertAlmostEqual(self.p.cash(), 100 - 5 - 0.01, 4)
    def test_idempotent(self):
        self.buy("e1"); self.assertEqual(self.buy("e1")["decision"], "ATLANDI")
        self.assertEqual(len(self.p.trades()), 1)
    def test_stale_and_illiquid(self):
        self.assertEqual(self.buy("a", age=60)["reason"], "sinyal bayat")
        self.assertIn("likidite", self.buy("b", liq=100)["reason"])
    def test_max_positions(self):
        for i in range(5): self.assertEqual(self.buy(f"e{i}", tok=f"T{i}")["decision"], "KOPYALANDI")
        self.assertEqual(self.buy("x", tok="T9")["reason"], "maks. eşzamanlı pozisyon")
    def test_sell_only_owned(self):
        self.assertEqual(self.p.handle_signal("s1", "W", "NOPE", "sell", 1.0, 1e6, 1)["decision"], "REDDEDİLDİ")
    def test_sell_realizes_pnl(self):
        self.buy("e1"); r = self.p.handle_signal("s1", "W", "T1", "sell", 1.2, 1e6, 1)
        self.assertGreater(r["pnl"], 0); self.assertEqual(self.p.portfolio()["positions"], [])
    def test_kill_switch(self):
        self.p.set_kill(True); self.assertEqual(self.buy("e1")["reason"], "acil durdurma aktif")
    def test_daily_loss_limit(self):
        self.buy("e1"); self.p.db.execute("UPDATE positions SET last_price=0.0"); self.p.db.commit()
        self.assertEqual(self.buy("e2", tok="T2")["reason"], "günlük zarar limiti")
if __name__ == "__main__": unittest.main()
