import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import core as C


class CuzdanModuTests(unittest.TestCase):
    """POZISYON_MOD=cuzdan: satış yalnızca satan cüzdanın payını kapatır; diğer cüzdanın hissesine dokunmaz."""
    def setUp(self):
        self.eski = C.POZISYON_MOD
        C.POZISYON_MOD = "cuzdan"
        self.p = C.Paper()

    def tearDown(self):
        C.POZISYON_MOD = self.eski

    def al(self, e, w, tok="T1", price=1.0):
        return self.p.handle_signal(e, w, tok, "buy", price, 1e6, 1)

    def sat(self, e, w, tok="T1", price=1.0):
        return self.p.handle_signal(e, w, tok, "sell", price, 1e6, 1)

    def test_a_ve_b_ayri_paylar(self):
        self.assertEqual(self.al("e1", "A")["decision"], "KOPYALANDI")
        self.assertEqual(self.al("e2", "B")["decision"], "KOPYALANDI")
        toplam = self.p.db.execute("SELECT SUM(qty) q FROM pozisyon_bacak WHERE token='T1'").fetchone()["q"]
        pos = self.p.db.execute("SELECT qty FROM positions WHERE token='T1'").fetchone()["qty"]
        self.assertAlmostEqual(toplam, pos, places=6)

    def test_b_satisi_a_hissesini_kapatmaz(self):
        self.al("e1", "A")
        self.al("e2", "B")
        b_qty = self.p.db.execute("SELECT qty FROM pozisyon_bacak WHERE token='T1' AND wallet='B'").fetchone()["qty"]
        r = self.sat("e3", "B")
        self.assertEqual(r["decision"], "KOPYALANDI")
        self.assertAlmostEqual(r["qty"], b_qty, places=6)
        kalan = self.p.db.execute("SELECT qty, wallet FROM pozisyon_bacak WHERE token='T1'").fetchall()
        self.assertEqual([x["wallet"] for x in kalan], ["A"])
        self.assertTrue(self.p.db.execute("SELECT 1 FROM positions WHERE token='T1'").fetchone())

    def test_payi_olmayan_cuzdan_satamaz(self):
        self.al("e1", "A")
        r = self.sat("e2", "B")
        self.assertEqual(r["decision"], "REDDEDİLDİ")
        self.assertIn("payı yok", r["reason"])
        self.assertTrue(self.p.db.execute("SELECT 1 FROM pozisyon_bacak WHERE token='T1' AND wallet='A'").fetchone())

    def test_son_pay_kapaninca_toplam_satir_silinir(self):
        self.al("e1", "A")
        self.sat("e2", "A")
        self.assertIsNone(self.p.db.execute("SELECT 1 FROM positions WHERE token='T1'").fetchone())
        self.assertIsNone(self.p.db.execute("SELECT 1 FROM pozisyon_bacak WHERE token='T1'").fetchone())

    def test_varsayilan_mod_eski_davranis(self):
        C.POZISYON_MOD = "token"
        p = C.Paper()
        p.handle_signal("e1", "A", "T1", "buy", 1.0, 1e6, 1)
        p.handle_signal("e2", "B", "T1", "buy", 1.0, 1e6, 1)
        r = p.handle_signal("e3", "B", "T1", "sell", 1.0, 1e6, 1)
        self.assertEqual(r["decision"], "KOPYALANDI")
        self.assertIsNone(p.db.execute("SELECT 1 FROM positions WHERE token='T1'").fetchone())   # havuz tamamen kapandı (eski)


if __name__ == "__main__":
    unittest.main()
