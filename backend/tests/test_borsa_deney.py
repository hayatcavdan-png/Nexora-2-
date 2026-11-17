import unittest
import borsa_deney as B


def seri(fiyatlar, bas=0):
    return [(bas + i * 60, p) for i, p in enumerate(fiyatlar)]


class GostergeTests(unittest.TestCase):
    def test_degisim_ve_zirve(self):
        g = B.gostergeler(seri([100.0] * 60 + [103.0] * 15 + [110.0]))
        son = g[75 * 60]
        self.assertAlmostEqual(son["r15"], (110 / 103 - 1) * 100)
        self.assertAlmostEqual(son["r60"], 10.0)
        self.assertEqual(son["z60"], 103.0)                       # zirve şimdiki dakikayı içermez
        self.assertIsNone(g[0]["r15"])


class SimuleTests(unittest.TestCase):
    def test_kar_al_ve_maliyet(self):
        veri = {"A": B.gostergeler(seri([100.0, 100.0, 112.0, 112.0]))}
        r = B.simule(veri, giris=lambda x: x["p"] == 100.0, kar_al=10, zarar_kes=5, sure_dk=60, bekleme_dk=1000)
        self.assertEqual(r["islem"], 1)
        net = 112 * (1 - B.MALIYET) / (100 * (1 + B.MALIYET)) - 1
        self.assertAlmostEqual(r["kz"], round(5.0 * net, 2))

    def test_zarar_kes_iz_ve_bekleme(self):
        veri = {"A": B.gostergeler(seri([100.0, 104.0, 100.5, 100.0, 100.0]))}
        r = B.simule(veri, giris=lambda x: x["p"] == 100.0, iz=3, zarar_kes=10, sure_dk=600, bekleme_dk=60)
        self.assertEqual(r["islem"], 1)                           # iz %3 ile 100.5'te çıkar; bekleme yeniden girişi engeller
        r = B.simule(veri, giris=lambda x: x["p"] == 100.0, iz=3, zarar_kes=10, sure_dk=600, bekleme_dk=0)
        self.assertEqual(r["islem"], 2)

    def test_pozisyon_siniri(self):
        veri = {s: B.gostergeler(seri([10.0, 10.0])) for s in "ABCDEFGHIJ"}
        r = B.simule(veri, giris=lambda x: True, sure_dk=600, max_poz=8, bekleme_dk=1000)   # açık kalırlar: yer açılmaz
        self.assertEqual(r["islem"], 8)


class IndirTests(unittest.TestCase):
    def test_indir_onbellek(self):
        import os, tempfile
        db = os.path.join(tempfile.mkdtemp(), "m.db"); cagri = []
        class S:
            def get(self, url, params=None, timeout=None):
                cagri.append(params["startTime"])
                class R:
                    def json(_):
                        t = params["startTime"]
                        return [[t + i * 60_000, "0", "0", "0", str(100 + i)] for i in range(3)] if t < 1_000_000 * 1000 else []
                return R()
        out = B.indir(S(), ["XUSDT"], 0.01, db=db, now=1_000_000, uyku=0, yaz=lambda m: None)
        self.assertGreaterEqual(len(out["XUSDT"]), 3)
        n = len(cagri); B.indir(S(), ["XUSDT"], 0.01, db=db, now=1_000_000, uyku=0, yaz=lambda m: None)
        self.assertLessEqual(len(cagri) - n, 1)                  # ikinci çalıştırma yalnızca eksik kısmı ister


if __name__ == "__main__":
    unittest.main()


class TamSayiZamanTests(unittest.TestCase):
    def test_baslangic_zamani_tam_sayi(self):
        import os, tempfile
        gonderilen = []
        class S:
            def get(self, url, params=None, timeout=None):
                gonderilen.append(params["startTime"])
                class R:
                    status_code = 200
                    def json(_): return []
                return R()
        B.indir(S(), ["XUSDT"], 7.0, db=os.path.join(tempfile.mkdtemp(), "m.db"), now=1_000_000.5, uyku=0, yaz=lambda m: None)
        self.assertTrue(gonderilen and all(isinstance(x, int) for x in gonderilen))   # Binance ondalıklı startTime'ı reddeder


class GeriDoldurmaTests(unittest.TestCase):
    def test_eski_gunler_de_indirilir(self):
        import os, tempfile
        db = os.path.join(tempfile.mkdtemp(), "m.db"); istek = []
        class S:
            def get(self, url, params=None, timeout=None):
                bas = params["startTime"] // 1000; istek.append(bas)
                class R:
                    status_code = 200
                    def json(_):
                        return [[(bas + i * 60) * 1000, "0", "0", "0", "1"] for i in range(1000) if bas + i * 60 < 2_000_000]
                return R()
        now = 2_000_000
        B.indir(S(), ["XUSDT"], 1.0, db=db, now=now, uyku=0, yaz=lambda m: None)             # önce 1 gün
        istek.clear()
        out = B.indir(S(), ["XUSDT"], 3.0, db=db, now=now, uyku=0, yaz=lambda m: None)       # sonra 3 gün: geriye doldurur
        self.assertEqual(min(istek), int(now - 3 * 86400) // 60 * 60)
        self.assertGreaterEqual(len(out["XUSDT"]), 3 * 1440 - 5)
