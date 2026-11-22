import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import kopyalanabilirlik as K


def m(n, ort, medyan=None, pozitif=0.6):
    return dict(n=n, ort=ort, medyan=ort if medyan is None else medyan, pozitif=pozitif)


class SinifTests(unittest.TestCase):
    def test_a_kanitli_pozitif(self):
        s, _ = K.sinif(m(20, 4.0), {"yarilar": (5.0, 10, 3.0, 10)})
        self.assertEqual(s, "A")

    def test_az_veri_b(self):
        s, g = K.sinif(m(5, 9.0))
        self.assertEqual(s, "B"); self.assertTrue(any("yetersiz" in x for x in g))

    def test_maliyet_sonrasi_negatif_c(self):
        self.assertEqual(K.sinif(m(12, -2.0))[0], "C")

    def test_bot_ve_tek_token_c(self):
        self.assertEqual(K.sinif(m(30, 8.0), {"bot_suphe": True})[0], "C")
        self.assertEqual(K.sinif(m(30, 8.0), {"tek_token_pay": 0.8})[0], "C")

    def test_asiri_dusus_c_ve_iyi_ama_dusus_b(self):
        self.assertEqual(K.sinif(m(30, 8.0), {"maks_dusus": -70})[0], "C")
        s, _ = K.sinif(m(30, 8.0), {"maks_dusus": -45})
        self.assertEqual(s, "B")

    def test_olcum_yok(self):
        self.assertEqual(K.sinif(None), ("B", ["henüz ölçüm yok"]))
        self.assertEqual(K.puan(None), 0.0)


class PuanTests(unittest.TestCase):
    def test_puan_sinirda_ve_siralama(self):
        iyi, orta = m(30, 6.0), m(30, 1.0, pozitif=0.5)
        self.assertGreater(K.puan(iyi), K.puan(orta))
        self.assertTrue(0 <= K.puan(m(30, -10.0, medyan=-10, pozitif=0)) <= 100)

    def test_ceza_puani_dusurur(self):
        temiz = K.puan(m(30, 5.0))
        self.assertLess(K.puan(m(30, 5.0), {"bot_suphe": True}), temiz)

    def test_az_olcum_puani_guvene_gore_sinirli(self):
        self.assertLess(K.puan(m(3, 9.0)), K.puan(m(30, 9.0)))


class RaporTests(unittest.TestCase):
    def test_rapor_sirali_ve_sayim(self):
        olc = {"W1": m(30, 6.0), "W2": m(30, -3.0), "W3": m(4, 2.0)}
        r = K.rapor(olc, {"W1": {"tek_token_pay": 0.0, "yarilar": (5.0, 15, 3.0, 15)}})
        self.assertEqual(list(r)[0], "W1")
        self.assertEqual(K.sayim(r), {"A": 1, "B": 1, "C": 1})

    def test_mod_varsayilan_kapali(self):
        self.assertEqual(K.MOD, os.getenv("KOPYA_SKOR_MOD", "kapali"))


if __name__ == "__main__":
    unittest.main()


class ZamanTutarliligiTests(unittest.TestCase):
    M = dict(n=20, ort=4.0, medyan=2.0, pozitif=0.7)

    def test_yarilar_yoksa_a_olmaz(self):
        self.assertEqual(K.sinif(self.M)[0], "B")

    def test_bir_yari_zararda_a_olmaz(self):
        self.assertEqual(K.sinif(self.M, {"yarilar": (6.0, 10, -1.0, 10)})[0], "B")

    def test_iki_yari_kârda_a_olabilir(self):
        self.assertEqual(K.sinif(self.M, {"yarilar": (5.0, 10, 3.0, 10)})[0], "A")
