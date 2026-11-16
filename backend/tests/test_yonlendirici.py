import os, tempfile, unittest
from nexora.core import Paper
from nexora import yonlendirici as Y

NOW = 1_800_000_000.0


def defter(yol, islemler):
    """islemler: [(ts, pnl, maliyet)] -> kapanan satışlar."""
    p = Paper(yol)
    for i, (ts, pnl, maliyet) in enumerate(islemler):
        p.db.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (ts, f"e{i}", "w", "t", "sell", 1.0, maliyet + pnl, 0.0, pnl, "KOPYALANDI", "ok"))
    p.db.commit(); return p


class YonlendiriciTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.k = [("iyi", "İyi", os.path.join(self.d, "a.db")), ("kotu", "Kötü", os.path.join(self.d, "b.db")),
                  ("az", "Az", os.path.join(self.d, "c.db")), ("yok", "Yok", os.path.join(self.d, "yok.db"))]
        self.a = defter(self.k[0][2], [(NOW - 3600, 1.0, 10.0)] * 8 + [(NOW - 3600, -0.5, 10.0)] * 2)
        self.b = defter(self.k[1][2], [(NOW - 3600, -1.0, 10.0)] * 10)
        defter(self.k[2][2], [(NOW - 3600, 5.0, 10.0)] * 3)                         # 3 işlem: güvenilmez
        defter(os.path.join(self.d, "eski.db"), [(NOW - 30 * 86400, 5.0, 10.0)] * 10)

    def test_karne_ve_agirlik(self):
        kr = Y.karne(self.k[0][2], NOW)
        self.assertEqual(kr["n"], 10); self.assertAlmostEqual(kr["ort_getiri"], 0.07); self.assertEqual(kr["kazanma"], 0.8)
        self.assertEqual(Y.karne(os.path.join(self.d, "eski.db"), NOW)["n"], 0)              # pencere dışı
        w = Y.agirliklar({i: Y.karne(y, NOW) for i, _, y in self.k})
        self.assertEqual(w, {"iyi": 0.4})                                                   # tek kaynak: üst sınır, kalan nakit

    def test_gelecege_bakmadan_deger(self):
        y = Y.Yonlendirici(os.path.join(self.d, "y.db"))
        d = y.tur(self.k, NOW); self.assertEqual(d["deger"], 100.0)
        self.a._set("cash", self.a.cash() * 1.10); self.a.db.commit()                    # iyi kaynak +%10
        self.b._set("cash", self.b.cash() * 0.50); self.b.db.commit()                    # kötü kaynak -%50 (payı 0)
        d = y.tur(self.k, NOW + 3600)
        self.assertAlmostEqual(d["deger"], 104.0)                                          # 0.4 x %10
        s = {x["kaynak"]: x for x in d["kaynaklar"]}
        self.assertEqual(s["iyi"]["getiri_pct"], 10.0); self.assertEqual(s["kotu"]["getiri_pct"], -50.0)
        self.assertIsNone(s["yok"]["getiri_pct"]); self.assertEqual(d["nakit_pay"], 0.6)

    def test_bos(self):
        self.assertTrue(Y.Yonlendirici(":memory:").durum(self.k).get("bos"))


if __name__ == "__main__":
    unittest.main()
