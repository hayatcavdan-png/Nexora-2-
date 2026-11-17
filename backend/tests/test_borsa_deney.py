import os, sqlite3, tempfile, unittest
from array import array
import borsa_deney as B


def V(fiyatlar): return B.Seri(array("d", fiyatlar))


class GostergeTests(unittest.TestCase):
    def test_degisim_ve_zirve(self):
        s = V([100.0] * 60 + [103.0] * 15 + [110.0])
        x = s.an(75)
        self.assertAlmostEqual(x["r15"], (110 / 103 - 1) * 100)
        self.assertAlmostEqual(x["r60"], 10.0)
        self.assertEqual(x["z60"], 103.0)                        # zirve şimdiki dakikayı içermez
        self.assertIsNone(s.an(0)["r15"])

    def test_eksik_dakika_ve_izgara(self):
        a = B.izgara([(0, 1.0), (120, 3.0)], 0, 3)
        self.assertEqual((a[0], a[2]), (1.0, 3.0)); self.assertNotEqual(a[1], a[1])   # eksik dakika NaN
        self.assertEqual(B.Seri(a).son_fiyat(), 3.0)


class SimuleTests(unittest.TestCase):
    def test_kar_al_ve_maliyet(self):
        r = B.simule({"A": V([100.0, 100.0, 112.0, 112.0])}, giris=lambda x: x["p"] == 100.0, kar_al=10, zarar_kes=5,
                     sure_dk=60, bekleme_dk=1000)
        self.assertEqual(r["islem"], 1)
        net = 112 * (1 - B.MALIYET) / (100 * (1 + B.MALIYET)) - 1
        self.assertAlmostEqual(r["kz"], round(5.0 * net, 2))

    def test_iz_ve_bekleme(self):
        v = {"A": V([100.0, 104.0, 100.5, 100.0, 100.0])}
        self.assertEqual(B.simule(v, giris=lambda x: x["p"] == 100.0, iz=3, zarar_kes=10, sure_dk=600, bekleme_dk=60)["islem"], 1)
        self.assertEqual(B.simule(v, giris=lambda x: x["p"] == 100.0, iz=3, zarar_kes=10, sure_dk=600, bekleme_dk=0)["islem"], 2)

    def test_pozisyon_siniri(self):
        v = {s: V([10.0, 10.0]) for s in "ABCDEFGHIJ"}
        self.assertEqual(B.simule(v, giris=lambda x: True, sure_dk=600, max_poz=8, bekleme_dk=1000)["islem"], 8)

    def test_rapor(self):
        v = {"BTCUSDT": V([100.0] * 400 + [90.0]), "XUSDT": V([10.0] * 401)}
        r = B.rapor(v, 7)
        self.assertIn("BTC tutmak %-10.00", r); self.assertIn("trend (canlı)", r)


class _S:
    """Binance taklidi: startTime'dan itibaren 1000 dakikalık mum (bitis'e kadar)."""
    def __init__(self, bitis): self.bitis, self.istek = bitis, []
    def get(self, url, params=None, timeout=None):
        bas = params["startTime"] // 1000; self.istek.append(params["startTime"]); bitis = self.bitis
        class R:
            status_code = 200
            def json(_): return [[(bas + i * 60) * 1000, "0", "0", "0", "1"] for i in range(1000) if bas + i * 60 < bitis]
        return R()


class IndirTests(unittest.TestCase):
    def test_tam_sayi_zaman_ve_onbellek(self):
        db = os.path.join(tempfile.mkdtemp(), "m.db"); s = _S(1_000_000)
        n = B.indir(s, ["XUSDT"], 0.5, db=db, now=1_000_000.5, uyku=0, yaz=lambda m: None)
        self.assertTrue(all(isinstance(x, int) for x in s.istek))       # Binance ondalıklı startTime'ı reddeder
        self.assertGreater(n["XUSDT"], 700)
        k = len(s.istek); B.indir(s, ["XUSDT"], 0.5, db=db, now=1_000_000, uyku=0, yaz=lambda m: None)
        self.assertLessEqual(len(s.istek) - k, 1)                        # ikinci çalıştırma yalnızca eksik kısmı ister

    def test_geriye_doldurma_ve_yukle(self):
        db = os.path.join(tempfile.mkdtemp(), "m.db"); now = 2_000_000; s = _S(now)
        B.indir(s, ["XUSDT"], 1.0, db=db, now=now, uyku=0, yaz=lambda m: None)
        s.istek.clear()
        n = B.indir(s, ["XUSDT"], 3.0, db=db, now=now, uyku=0, yaz=lambda m: None)
        self.assertEqual(min(s.istek), (int(now - 3 * 86400) // 60 * 60) * 1000)
        self.assertGreaterEqual(n["XUSDT"], 3 * 1440 - 5)
        v = B.yukle(["XUSDT", "YOK"], 3.0, db=db, now=now)
        self.assertEqual(list(v), ["XUSDT"]); self.assertEqual(len(v["XUSDT"].p), 3 * 1440)


if __name__ == "__main__":
    unittest.main()
