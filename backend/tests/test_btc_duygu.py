import json, os, random, tempfile, unittest

from nexora import btc_duygu as D, btc_haber as H, btc_ongoru as b, btc_sinama as S
from nexora.core import Paper
from tests.test_btc_gosterge import _rejimli
from tests.test_btc_ongoru import _Oturum, _Quoter, _mum, _post

T0 = 1_700_000_000.0


def _seri(n=500, t0=T0, tohum=5):
    """Saatlik sentetik vadeli seriler + günlük korku endeksi."""
    rnd = random.Random(tohum)
    s = {"oi": [], "ls": [], "buyuk": [], "taker": [], "fonlama": [], "korku": []}
    oi, ls, bg = 1e5, 1.5, 1.2
    for i in range(n):
        t = t0 + i * 3600
        oi *= 1 + rnd.gauss(0, 0.01); ls = max(0.5, ls + rnd.gauss(0, 0.05)); bg = max(0.5, bg + rnd.gauss(0, 0.05))
        s["oi"].append((t, oi)); s["ls"].append((t, ls)); s["buyuk"].append((t, bg)); s["taker"].append((t, 1 + rnd.gauss(0, 0.1)))
        if i % 8 == 0: s["fonlama"].append((t, rnd.gauss(0.0001, 0.0002)))
        if i % 24 == 0: s["korku"].append((t, rnd.randint(10, 90)))
    return s


class OzellikTest(unittest.TestCase):
    def test_gelecegi_gormez(self):
        s = _seri(); t = T0 + 300 * 3600 + 1
        once = D.ozellik(s, t, 0.5)
        bozuk = {k: [(ts, v if ts + D.GECIKME[k] <= t else v * 50) for ts, v in seri] for k, seri in s.items()}
        self.assertEqual(once, D.ozellik(bozuk, t, 0.5))

    def test_gecikme_saat_verisini_bir_saat_sonra_bilir(self):
        s = {"taker": [(T0 + i * 3600, 1.0 + i) for i in range(10)]}
        o = D.ozellik(s, T0 + 9 * 3600 + 10, None)               # son nokta (i=9) henüz bilinmiyor
        self.assertAlmostEqual(o["taker_4s"], (5 + 6 + 7 + 8 + 4) / 4)  # 1+i, i=5..8 -> 6,7,8,9

    def test_bayat_veri_yok_sayilir(self):
        s = {"fonlama": [(T0, 0.001)]}
        self.assertIsNone(D.ozellik(s, T0 + 20 * 3600, None)["fonlama_pct"])
        self.assertAlmostEqual(D.ozellik(s, T0 + 3600, None)["fonlama_pct"], 0.1)

    def test_sinyaller(self):
        o = dict(fonlama_pct=0.05, ls_yuzdelik=90, buyuk_degisim_4s_pct=4, oi_degisim_4s_pct=2, r4=-1, taker_4s=0.9,
                 korku_acgozluluk=20, uzman_hl=dict(long=5, short=1, net_oran=0.6), haber=dict(duygu=-2))
        s = D.sinyaller(o)
        self.assertEqual(s, dict(fonlama=-1, kalabalik=-1, buyuk_trader=1, oi_fiyat=-1, taker=-1, korku=1, uzman_hl=1, haber=-1))
        bos = D.sinyaller({})
        self.assertTrue(all(v == 0 for v in bos.values()))

    def test_uzman_az_pozisyonda_fikirsiz(self):
        self.assertEqual(D.sinyaller(dict(uzman_hl=dict(long=1, short=0, net_oran=1.0)))["uzman_hl"], 0)


class _HlOturum:
    def __init__(self, poz): self.poz = poz
    def post(self, url, json=None, timeout=None):
        p = self.poz.get(json["user"], [])
        class R:
            def raise_for_status(s): pass
            def json(s): return {"assetPositions": [{"position": x} for x in p]}
        return R()


class UzmanTest(unittest.TestCase):
    def test_net_oran(self):
        d = tempfile.mkdtemp(); yol = os.path.join(d, "hl.txt")
        with open(yol, "w") as f: f.write("0xa\n0xb\n0xc\n")
        s = _HlOturum({"0xa": [dict(coin="BTC", szi="1", positionValue="300")],
                       "0xb": [dict(coin="BTC", szi="-0.5", positionValue="100"), dict(coin="ETH", szi="5", positionValue="9")],
                       "0xc": []})
        u = D.uzman_hl(s, yol)
        self.assertEqual((u["n"], u["long"], u["short"], u["net_oran"]), (3, 1, 1, 0.5))
        self.assertIsNone(D.uzman_hl(s, os.path.join(d, "yok.txt")))


def _haber_yanit(metin, kaynak=True):
    a = {"content": {"parts": [{"text": metin}]}}
    if kaynak: a["groundingMetadata"] = {"groundingChunks": [{"web": {"uri": "https://ornek.com/x", "title": "Örnek"}}]}
    return lambda govde: {"candidates": [a]}


class HaberTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ); self.d = tempfile.mkdtemp()
        self.paper = Paper(os.path.join(self.d, "btc.db"), ekosistem="btc", dagit=False)

    def tearDown(self):
        self.paper.db.close(); os.environ.clear(); os.environ.update(self._env)

    def test_cozumle(self):
        h = H.cozumle(_haber_yanit('```json\n{"duygu": -1, "ozet": "ETF çıkışı", "olaylar": ["a", "b"]}\n```')(None))
        self.assertEqual((h["duygu"], h["ozet"], h["kaynaklar"][0]["url"]), (-1, "ETF çıkışı", "https://ornek.com/x"))
        self.assertIsNone(H.cozumle(_haber_yanit('{"duygu": 5}')(None)))
        self.assertIsNone(H.cozumle({"candidates": []}))

    def test_kapali_ve_onbellek(self):
        os.environ.pop("BTC_HABER", None)
        self.assertEqual(H.getir(self.paper, T0), (None, None))
        os.environ["BTC_HABER"] = "1"
        n = {"i": 0}
        def post(govde):
            n["i"] += 1
            self.assertIn("google_search", govde.decode())
            return _haber_yanit('{"duygu": 1, "ozet": "olumlu"}')(govde)
        h, hata = H.getir(self.paper, T0, post=post)
        self.assertEqual((h["duygu"], hata), (1, None))
        H.getir(self.paper, T0 + 3600, post=post)                    # önbellekten
        self.assertEqual(n["i"], 1)
        H.getir(self.paper, T0 + 4 * 3600, post=post)                # süresi doldu
        self.assertEqual(n["i"], 2)

    def test_hata(self):
        os.environ["BTC_HABER"] = "1"
        def bozuk(g): raise OSError("503")
        h, hata = H.getir(self.paper, T0, post=bozuk)
        self.assertIsNone(h); self.assertIn("503", hata)


class DuyguSinamaTest(unittest.TestCase):
    def test_yetersiz_ve_yeterli(self):
        mum = _rejimli(520)
        mum = [(T0 + i * 3600, T0 + i * 3600 + 3599.999, *m[2:]) for i, m in enumerate(mum)]
        self.assertTrue(S.sina_duygu(mum[:100], _seri())["yetersiz"])
        d = S.sina_duygu(mum, _seri())
        self.assertFalse(d.get("yetersiz")); self.assertEqual(set(d["kurallar"]), set(D.KURALLAR))
        self.assertIn("kanit", d)

    def test_toplam_kural_sayisi_esigi(self):
        self.assertAlmostEqual(S.z_esik(), S.z_esik(len(D.KURALLAR) + 17))


class MotorDuyguTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ); os.environ["BTC_ONGORU"] = "1"; os.environ["BTC_HABER"] = "1"
        self.d = tempfile.mkdtemp()
        self.paper = Paper(os.path.join(self.d, "btc.db"), ekosistem="btc", dagit=False)

    def tearDown(self):
        self.paper.db.close(); os.environ.clear(); os.environ.update(self._env)

    def test_istem_duygu_haber_ve_puanlama(self):
        giden = {}
        def post(govde):
            giden["m"] = json.loads(govde.decode())["input"]
            return _post('{"yon":"BELIRSIZ","guven":40,"gerekce":"x"}')(govde)
        duygu = lambda now, r4: dict(fonlama_pct=0.05, korku_acgozluluk=20, ls_yuzdelik=50,
                                     uzman_hl=dict(n=10, long=6, short=1, net_oran=0.7))
        mum = _mum(); f = mum[-1][2]
        d = b.calistir(self.paper, _Quoter(f), s=_Oturum(mum), post=post, now=mum[-1][1] + 10,
                       durum_yolu=os.path.join(self.d, "d.json"), agirlik_yolu=os.path.join(self.d, "yok.json"),
                       duygu_fn=duygu, haber_post=_haber_yanit('{"duygu": -2, "ozet": "kötü haber"}'))
        for k in ("piyasa_duygusu", "fonlama_pct", "uzman_hl", "kötü haber", "korku_acgozluluk"):
            self.assertIn(k, giden["m"])
        self.assertEqual((d["sinyal"]["fonlama"], d["sinyal"]["korku"], d["sinyal"]["uzman_hl"], d["sinyal"]["haber"]), (-1, 1, 1, -1))
        self.assertEqual(d["topluluk_skor"], 0.0)                        # sınama yok: duygu da oy kullanmaz
        # 5 saat sonra yükseliş: uzman (yukarı) isabetli, haber (aşağı) isabetsiz
        mum2 = _mum(n=77)
        b.calistir(self.paper, _Quoter(mum2[-1][2]), s=_Oturum(mum2), post=post, now=mum2[-1][1] + 10,
                   durum_yolu=os.path.join(self.d, "d.json"), agirlik_yolu=os.path.join(self.d, "yok.json"),
                   duygu_fn=duygu, haber_post=_haber_yanit('{"duygu": -2, "ozet": "kötü haber"}'))
        oz = b.ozet(self.paper, agirlik_yolu=os.path.join(self.d, "yok.json"))
        self.assertEqual((oz["uzman"]["n"], oz["uzman"]["isabet_pct"]), (1, 100.0))
        self.assertEqual((oz["haber"]["n"], oz["haber"]["isabet_pct"]), (1, 0.0))
        self.assertEqual((oz["duygu_son"]["uzman_long"], oz["duygu_son"]["haber_duygu"]), (6, -2))

    def test_duygu_kaniti_varsa_oy_kullanir(self):
        oz = b.ozellikler(_mum())
        sin = dict(kanit=False, agirlik=dict(ema_kesisim=1.0), duygu=dict(kanit=True, agirlik=dict(fonlama=2.0)))
        _, skor, yon = b.topluluk_hesap(oz, sin, dict(fonlama=-1))
        self.assertEqual((skor, yon), (-1.0, "ASAGI"))                  # teknik kanıtsız: yalnız fonlama oy verir

    def test_yedek_model_ikinci_denemede(self):
        os.environ["YZ_MODEL_YEDEK"] = "yedek-model"
        modeller = []
        def post(govde):
            modeller.append(json.loads(govde.decode())["model"])
            if len(modeller) == 1: raise OSError("503")
            return _post('{"yon":"YUKARI","guven":70,"gerekce":"x"}')(govde)
        t, _, hata = b.yz_tahmin(b.ozellikler(_mum()), post=post)
        self.assertEqual((t["yon"], modeller[1]), ("YUKARI", "yedek-model"))
        self.assertNotEqual(modeller[0], "yedek-model")


if __name__ == "__main__":
    unittest.main()
