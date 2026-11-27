import unittest

from nexora import iz_sinama as I
from nexora.core import Paper


class IzTest(unittest.TestCase):
    def test_zirveden_dusus_tetikler_ve_gelecegi_gormez(self):
        yol = [0, 10, 30, 20, 8, -20]                       # %30 zirve, sonra %8'e (değer oranı −%16,9)
        g, t = I.sonuc(-25.0, yol, 15, 0, 1.0)
        self.assertTrue(t); self.assertAlmostEqual(g, 7.0)   # %8 − 1 kayma
        self.assertEqual(I.sonuc(-25.0, yol, 15, 40, 1.0), (-25.0, False))   # %40 kâr hiç görülmedi: kural çalışmaz
        self.assertEqual(I.sonuc(50.0, [0, 20, 40, 50], 15, 0, 1.0), (50.0, False))   # yükselen kazanan kesilmez

    def test_sina_ve_az_veri(self):
        poz = [(10.0, -2.5, 1, [0, 10, 30, 8]), (10.0, 5.0, 2, [0, 20, 40, 50])]
        r = {(x["geri"], x["aktif"]): x for x in I.sina(poz, 1.0)}
        self.assertEqual(r[(None, None)]["toplam"], 2.5)
        self.assertGreater(r[(15, 0)]["toplam"], r[(None, None)]["toplam"])
        self.assertIsNone(I.ileri_sinama(poz))

    def test_paper_yol_kaydeder(self):
        p = Paper()
        p.record_buy("e1", "W", "TOK", 10.0, 1000 * 10 ** 6, 6)
        p.mark_price("TOK", 0.012); p.mark_price("TOK", 0.009)
        yol = [r[0] for r in p.db.execute("SELECT pct FROM pos_yol ORDER BY ts")]
        self.assertEqual(len(yol), 2); self.assertGreater(yol[0], yol[1])
        p.record_sell("e2", "W", "TOK", 11.0)
        self.assertEqual(len(I.oku(p.db)), 1)


if __name__ == "__main__":
    unittest.main()
