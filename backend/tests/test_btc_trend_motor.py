import os, tempfile, unittest

from nexora import btc_trend_motor as M
from nexora.core import Paper
from tests.test_btc_ongoru import _Quoter


class _Gunluk:
    def __init__(self, kapanislar, t0=1_700_000_000.0):
        self.k, self.t0 = kapanislar, t0
    def son_ts(self): return self.t0 + len(self.k) * 86400
    def get(self, url, params=None, timeout=None):
        k, t0 = self.k[-params["limit"]:], self.t0 + (len(self.k) - min(len(self.k), params["limit"])) * 86400
        class R:
            def raise_for_status(s): pass
            def json(s): return [[int((t0 + i * 86400) * 1000), "0", "0", "0", str(c), "0", int((t0 + i * 86400 + 86399) * 1000)]
                                 for i, c in enumerate(k)]
        return R()


class TrendMotorTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ); os.environ["BTC_TREND"] = "1"; self.d = tempfile.mkdtemp()
        self.paper = Paper(os.path.join(self.d, "t.db"), ekosistem="btc_trend", dagit=False)

    def tearDown(self):
        self.paper.db.close(); os.environ.clear(); os.environ.update(self._env)

    def _tur(self, kap, fiyat=None):
        s = _Gunluk(kap)
        return M.calistir(self.paper, _Quoter(fiyat or kap[-1]), s=s, now=s.son_ts() + 600)

    def test_kapali(self):
        os.environ.pop("BTC_TREND"); self.assertEqual(M.calistir(self.paper, _Quoter(1)), dict(durum="kapali"))

    def test_hedef(self):
        self.assertTrue(M.hedef([100.0] * 99 + [120.0])[0])
        self.assertFalse(M.hedef([100.0] * 99 + [80.0])[0])
        with self.assertRaises(ValueError): M.hedef([1.0] * 50)

    def test_al_tut_sat_ve_gunde_tek_karar(self):
        yuk = [100.0 + i for i in range(120)]
        d = self._tur(yuk); self.assertEqual(d["karar"], "al")
        self.assertAlmostEqual(self.paper.position(M.BTC_MINT)["cost"], 99.0, places=1)       # nakit - rezerv
        self.assertEqual(self._tur(yuk)["karar"], "zaten karar verildi")                      # aynı gün
        d = self._tur(yuk + [221.0]); self.assertEqual(d["karar"], "tut")
        d = self._tur(yuk + [221.0, 100.0]); self.assertEqual(d["karar"], "sat")
        self.assertIsNone(self.paper.position(M.BTC_MINT))
        d = self._tur(yuk + [221.0, 100.0, 99.0]); self.assertEqual(d["karar"], "nakit")
        oz = M.ozet(self.paper)
        self.assertEqual((oz["islem"], oz["piyasada"], oz["mod"]), (2, False, "PAPER"))
        self.assertEqual(oz["son"]["karar"], "nakit")

    def test_yuksek_etki_ertelenir_ve_yeniden_denenir(self):
        yuk = [100.0 + i for i in range(120)]
        s = _Gunluk(yuk)
        d = M.calistir(self.paper, _Quoter(yuk[-1], etki=3.0), s=s, now=s.son_ts() + 600)
        self.assertEqual(d["karar"], "bekle")
        self.assertEqual(self._tur(yuk)["karar"], "al")                                      # aynı gün ikinci deneme

    def test_veri_hatasi(self):
        class Bozuk:
            def get(self, *a, **k): raise OSError("ağ")
        self.assertEqual(M.calistir(self.paper, _Quoter(1), s=Bozuk())["durum"], "hata")


if __name__ == "__main__":
    unittest.main()
