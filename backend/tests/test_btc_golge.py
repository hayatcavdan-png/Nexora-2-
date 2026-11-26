import os, sqlite3, tempfile, unittest

from nexora import btc_golge as Gg
from nexora import btc_ongoru as b
from nexora.core import Paper
from tests.test_btc_ongoru import _Oturum, _Quoter, _mum, _post


class GolgeTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")

    def tearDown(self):
        self.db.close()

    def test_yontemler_ayri_isler(self):
        Gg.adim(self.db, 100.0, 1.0, "YUKARI", dict(yon="BELIRSIZ"), "BELIRSIZ")
        k = {x["ad"]: x for x in Gg.karne(self.db)}
        self.assertTrue(k["kural"]["pozisyonda"]); self.assertFalse(k["yz_her"]["pozisyonda"])
        self.assertFalse(k["topluluk"]["pozisyonda"])
        Gg.adim(self.db, 110.0, 2.0, "ASAGI", None, "BELIRSIZ")            # kural çıkar, kârda
        k = {x["ad"]: x for x in Gg.karne(self.db)}
        self.assertFalse(k["kural"]["pozisyonda"]); self.assertEqual((k["kural"]["kapanan"], k["kural"]["kazanma_pct"]), (1, 100.0))
        self.assertAlmostEqual(k["kural"]["kz_pct"], 50 * (1.1 * 0.999 * 0.999 - 1), places=2)   # yarı portföy, maliyetli
        self.assertEqual(k["yz_her"]["kz_pct"], 0.0); self.assertEqual(k["kural"]["tut_pct"], 10.0)

    def test_yz_guvenden_bagimsiz_ve_yanitsizda_bekler(self):
        Gg.adim(self.db, 100.0, 1.0, "BELIRSIZ", dict(yon="YUKARI", guven=20), "BELIRSIZ")
        Gg.adim(self.db, 101.0, 2.0, "BELIRSIZ", None, "BELIRSIZ")          # YZ yok: pozisyon korunur
        k = {x["ad"]: x for x in Gg.karne(self.db)}
        self.assertTrue(k["yz_her"]["pozisyonda"]); self.assertEqual(k["yz_her"]["islem"], 1)

    def test_zarar_kes(self):
        Gg.adim(self.db, 100.0, 1.0, "YUKARI", None, None)
        Gg.adim(self.db, 96.0, 2.0, "YUKARI", None, None)                 # %-4: zarar kes, kural YUKARI dese de
        k = {x["ad"]: x for x in Gg.karne(self.db)}
        self.assertFalse(k["kural"]["pozisyonda"]); self.assertEqual(k["kural"]["kazanma_pct"], 0.0)


class MotorGolgeTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ); os.environ["BTC_ONGORU"] = "1"; self.d = tempfile.mkdtemp()
        self.paper = Paper(os.path.join(self.d, "btc.db"), ekosistem="btc", dagit=False)

    def tearDown(self):
        self.paper.db.close(); os.environ.clear(); os.environ.update(self._env)

    def test_tur_golge_yazar_ve_ozet_gosterir(self):
        mum = _mum(adim=0.002)
        d = b.calistir(self.paper, _Quoter(mum[-1][2]), s=_Oturum(mum), post=_post('{"yon":"YUKARI","guven":40,"gerekce":"x"}'),
                       now=mum[-1][1] + 10, durum_yolu=os.path.join(self.d, "d.json"), agirlik_yolu=os.path.join(self.d, "y.json"))
        self.assertEqual(d["karar"], "bekle")                              # asıl: güven 40 < 60
        self.assertEqual(set(d["golge"]), set(Gg.YONTEMLER))
        oz = {x["ad"]: x for x in b.ozet(self.paper, agirlik_yolu=os.path.join(self.d, "y.json"))["golge"]}
        self.assertTrue(oz["yz_her"]["pozisyonda"]); self.assertTrue(oz["kural"]["pozisyonda"])


if __name__ == "__main__":
    unittest.main()
