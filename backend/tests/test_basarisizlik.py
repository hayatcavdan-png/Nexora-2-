import unittest
from nexora import rapor


def r(side, k): return dict(side=side, kayip_pct=k)


class Test(unittest.TestCase):
    def test_tolerans_orani(self):
        rows = [r("buy", 0.2), r("buy", 0.8), r("buy", 1.5), r("buy", 4.0), r("sell", None), r("sell", -0.3)]
        m = rapor.basarisizlik_modeli(rows, toleranslar=(1.0, 5.0))
        hep = {t["tolerans"]: t for t in m["toleranslar"] if t["yon"] == "hepsi"}
        self.assertEqual((hep[1.0]["basarisiz"], hep[5.0]["basarisiz"]), (3, 1))        # None her toleransta düşer
        self.assertAlmostEqual(hep[1.0]["basarili_ort_kayip"], round((0.2 + 0.8 - 0.3) / 3, 3))
        alim = {t["tolerans"]: t for t in m["toleranslar"] if t["yon"] == "buy"}
        self.assertEqual(alim[1.0]["oran"], 0.5)
        self.assertEqual(m["teklif_yok"], 1)

    def test_wilson_ust_sinir(self):
        self.assertIsNone(rapor._wilson_ust(0, 0))
        u = rapor._wilson_ust(0, 10)
        self.assertGreater(u, 0.2); self.assertLess(u, 0.35)                            # 0/10 "sıfır risk" demek değil
        self.assertGreater(rapor._wilson_ust(5, 10), 0.5)

    def test_bos(self):
        self.assertEqual(rapor.basarisizlik_modeli([])["toleranslar"], [])


if __name__ == "__main__":
    unittest.main()
