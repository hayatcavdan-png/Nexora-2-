import unittest

from nexora import kar_al_sinama as K


class KarAlTest(unittest.TestCase):
    # (cost, pnl, min_pct, max_pct, closed_ts)
    S = [(10.0, -3.0, -35.0, 22.0, 1),    # %22 gördü, %-30 kapandı: kural %20'de kurtarır
         (10.0, 5.0, -5.0, 60.0, 2),      # %60 gördü, %50 kapandı: %20 kuralı erken satar
         (10.0, -1.0, -45.0, 25.0, 3),    # zarar kesme bölgesi de görülmüş: temkinli sayımda kural yok
         (10.0, -0.5, -10.0, 3.0, 4)]     # hiç kâr görmedi

    def test_kuralsiz_ve_tam_satis(self):
        r = {x["esik"]: x for x in K.sina(self.S, kayma=1.0)}
        self.assertEqual(r[None]["toplam"], 0.5)
        x = r[20]
        self.assertEqual((x["tetik"], x["kacirilan"]), (2, 1))
        self.assertAlmostEqual(x["toplam"], (19 + 19 - 10 - 5) / 10)       # 1,9 + 1,9 − 1 − 0,5

    def test_iyimser_zarar_kesme_bolgesini_de_sayar(self):
        r = {x["esik"]: x for x in K.sina(self.S, kayma=1.0, iyimser=True)}
        self.assertEqual(r[20]["tetik"], 3)

    def test_yarim(self):
        g, t = K.sonuc(10.0, -3.0, -35.0, 22.0, 20, True, 1.0, False)
        self.assertTrue(t); self.assertAlmostEqual(g, (19 - 30) / 2)

    def test_ileri_sinama_az_veri_ve_bolme(self):
        self.assertIsNone(K.ileri_sinama(self.S))
        veri = [(10.0, -2.0, -30.0, 25.0, i) for i in range(30)]
        w = K.ileri_sinama(veri)
        self.assertEqual(w["ikinci"]["n"], 15)
        self.assertGreater(w["ikinci"]["toplam"], w["yok_ikinci"]["toplam"])


if __name__ == "__main__":
    unittest.main()
