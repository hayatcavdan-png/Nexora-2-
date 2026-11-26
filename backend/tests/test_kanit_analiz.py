import math, random, unittest

from nexora import btc_trend as T, cuzdan_karne as C


class CuzdanKarneTest(unittest.TestCase):
    def test_hukumler(self):
        rnd = random.Random(1)
        satir = [("kotu", 5.0, -0.5 + rnd.gauss(0, 0.2), 1.0) for _ in range(30)]          # sürekli zarar
        satir += [("iyi", 5.0, 0.6 + rnd.gauss(0, 0.2), 1.0) for _ in range(30)]
        satir += [("gurultu", 5.0, rnd.gauss(0, 1.0), 1.0) for _ in range(30)]
        satir += [("az", 5.0, -1.0, 1.0) for _ in range(5)]
        cuz, genel = C.karne(satir)
        h = {d["wallet"]: d["hukum"] for d in cuz}
        self.assertEqual(h["kotu"], "kanıtlı zarar"); self.assertEqual(h["iyi"], "kanıtlı kâr")
        self.assertEqual(h["az"], "az veri"); self.assertIn(h["gurultu"], ("belirsiz", "kanıtlı zarar", "kanıtlı kâr"))
        self.assertEqual(cuz[0]["wallet"], "kotu")                                        # en kötü t başta
        self.assertEqual(genel["n"], 95)

    def test_ek_maliyet_sonucu_kotulestirir(self):
        satir = [("w", 5.0, 0.05 + 0.01 * (i % 3), 1.0) for i in range(20)]
        _, g0 = C.karne(satir); _, g1 = C.karne(satir, ek=0.2)
        self.assertGreater(g0["toplam"], 0); self.assertLess(g1["toplam"], 0)
        self.assertEqual(g1["hukum"], "kanıtlı zarar")

    def test_alsat_kaybi_ve_haftalik(self):
        k = C.alsat_kaybi(["etki %1.0, al-sat kaybı %2.5", "etki %0.2, al-sat kaybı %0.5", None, "kaynak sattı"])
        self.assertEqual((k["n"], k["ort"], k["p90"]), (2, 1.5, 2.5))
        h = C.haftalik([("w", 5, 1.0, 1000.0), ("w", 5, -2.0, 1000.0 - 8 * 86400 + 10)], now=1000.0 + 10)
        self.assertEqual(h[0], dict(hafta_once=0, n=1, toplam=1.0)); self.assertEqual(h[1]["hafta_once"], 1)

    def test_bos_ve_tek(self):
        self.assertEqual(C.istatistik([])["n"], 0)
        self.assertIsNone(C.istatistik([1.0])["t"])


def _gunler(n, getiri_fn, tohum=0):
    rnd = random.Random(tohum); f, out = 100.0, []
    for i in range(n):
        f *= 1 + getiri_fn(i, rnd); out.append((1_500_000_000 + i * 86400.0, f))
    return out


class TrendTest(unittest.TestCase):
    def test_sinyal_gelecegi_gormez(self):
        k = [100 + i for i in range(300)]
        s = T.sinyal(k, "sma", 50)
        k2 = k[:200] + [1.0] * 100
        self.assertEqual(s[:200], T.sinyal(k2, "sma", 50)[:200])
        self.assertIsNone(s[48]); self.assertTrue(s[49] is True or s[49] is False)

    def test_olc_tut_ve_maliyet(self):
        k = [100.0, 110.0, 121.0]
        r = T.olc(k, [True, True, True], 0, 3, maliyet=0.0)
        self.assertAlmostEqual(r["getiri_pct"], 21.0, places=1); self.assertEqual(r["islem"], 1)
        r2 = T.olc(k, [True, True, True], 0, 3, maliyet=0.01)
        self.assertLess(r2["getiri_pct"], r["getiri_pct"])
        r3 = T.olc([100.0, 50.0, 100.0], [True, True, True], 0, 3, maliyet=0.0)
        self.assertEqual(r3["en_buyuk_dusus_pct"], -50.0)

    def test_cokuste_trend_dususu_keser(self):
        # 400 gün yükseliş, 400 gün sert düşüş, 400 gün yükseliş: trend takibi düşüşün çoğundan kaçmalı
        g = lambda i, rnd: (0.004 if (i // 400) % 2 == 0 else -0.004) + rnd.gauss(0, 0.01)
        r = T.sina(_gunler(1200, g))
        tum_tut, tum_sec = r["sonuc"]["tut"]["tum"], r["sonuc"][r["secilen"]]["tum"]
        self.assertGreater(tum_sec["en_buyuk_dusus_pct"], tum_tut["en_buyuk_dusus_pct"])   # daha küçük düşüş
        self.assertIn(r["secilen"], r["sonuc"])

    def test_yetersiz(self):
        with self.assertRaises(ValueError): T.sina(_gunler(300, lambda i, r: 0.0))


if __name__ == "__main__":
    unittest.main()
