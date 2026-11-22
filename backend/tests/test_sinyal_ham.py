import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import core as C


class SinyalHamTests(unittest.TestCase):
    def test_sinyal_ham_kaydedilir_ve_tekrar_ezmez(self):
        p = C.Paper()
        p.handle_signal("e1", "A", "T1", "buy", 1.5, 2e5, 7)
        p.handle_signal("e1", "A", "T1", "buy", 9.9, 1.0, 99)     # aynı olay: ezilmemeli
        r = p.db.execute("SELECT price, liquidity_usd, signal_age_s FROM sinyal_ham WHERE event_id='e1'").fetchone()
        self.assertEqual((r["price"], r["liquidity_usd"], r["signal_age_s"]), (1.5, 2e5, 7))

    def test_kayit_hatasi_sinyali_bozmaz(self):
        p = C.Paper()
        p.db.execute("DROP TABLE sinyal_ham")
        d = p.handle_signal("e2", "A", "T1", "buy", 1.0, 1e6, 1)
        self.assertEqual(d["decision"], "KOPYALANDI")


if __name__ == "__main__":
    unittest.main()
