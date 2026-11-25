import json, os, tempfile, unittest

from nexora import btc_ongoru as b, btc_rejim
from nexora.constants import USDC_MINT
from nexora.core import Paper


def _mum(n=72, bas=100_000.0, adim=0.001, t0=1_800_000_000.0):
    """n adet 1 saatlik mum; her saat `adim` oranında değişen kapanış."""
    out, f = [], bas
    for i in range(n):
        a = t0 + i * 3600
        out.append((a, a + 3599.999, f, f * 1.001, f * 0.999, 100.0 + i))
        f *= 1 + adim
    return out


class _Yanit:
    def __init__(self, veri): self.veri = veri
    def raise_for_status(self): pass
    def json(self): return self.veri


class _Oturum:
    """Binance klines yanıtı taklidi."""
    def __init__(self, mum): self.mum = mum
    def get(self, url, params=None, timeout=None):
        return _Yanit([[int(a * 1000), "0", str(y), str(d), str(k), str(h), int(kts * 1000)] for a, kts, k, y, d, h in self.mum])


class _Quoter:
    """1 BTC = fiyat USDC; ücretsiz, etkisiz teklif."""
    def __init__(self, fiyat, etki=0.05): self.fiyat, self.etki, self.n = fiyat, etki, 0
    def quote(self, inp, out, amount):
        self.n += 1
        if inp == USDC_MINT: o = int(amount / 10 ** 6 / self.fiyat * 10 ** 8)
        else: o = int(amount / 10 ** 8 * self.fiyat * 10 ** 6)
        return dict(in_amount=amount, out_amount=o, price_impact_pct=self.etki)


def _post(metin):
    return lambda govde: {"model": "gemini-3.1-flash-lite", "steps": [{"type": "model_output", "content": [{"type": "text", "text": metin}]}]}


class OzellikTest(unittest.TestCase):
    def test_yukselen_seri(self):
        oz = b.ozellikler(_mum(adim=0.001))
        self.assertGreater(oz["r4"], 0); self.assertGreater(oz["sma24_sapma"], 0)
        self.assertEqual(b.kural_yon(oz), "YUKARI")

    def test_dusen_seri(self):
        oz = b.ozellikler(_mum(adim=-0.002))
        self.assertLess(oz["r4"], 0); self.assertEqual(b.kural_yon(oz), "ASAGI")

    def test_yetersiz_mum(self):
        with self.assertRaises(ValueError): b.ozellikler(_mum(n=10))

    def test_degisim_at(self):
        m = _mum(adim=0.01)
        r = b.degisim_at(m, m[-1][1] + 1, 4 * 3600)
        self.assertAlmostEqual(r, (1.01 ** 4 - 1) * 100, places=6)
        self.assertIsNone(b.degisim_at(m, m[0][0], 3600))            # henüz kapanmış mum yok


class YanitTest(unittest.TestCase):
    def test_gecerli_json(self):
        t = b.yanit_coz('Analiz: {"yon": "yukarı", "guven": 72, "gerekce": "trend"}')
        self.assertEqual(t["yon"], "YUKARI"); self.assertEqual(t["guven"], 72)

    def test_gecersizler(self):
        for m in (None, "", "yukarı gider", '{"yon": "UP", "guven": 70}', '{"yon": "ASAGI", "guven": 140}', '{"yon": "ASAGI"}'):
            self.assertIsNone(b.yanit_coz(m), m)


class KararTest(unittest.TestCase):
    oz = dict(r4=0.5)

    def test_yz_yoksa_alim_yok(self):
        self.assertEqual(b.karar(self.oz, None, False)[0], "bekle")

    def test_zarar_kes_yzden_bagimsiz(self):
        self.assertEqual(b.karar(self.oz, None, True, poz_pct=-3.5)[0], "sat")
        self.assertEqual(b.karar(self.oz, dict(yon="YUKARI", guven=99), True, poz_pct=-3.0)[0], "sat")

    def test_guclu_yukari_alir(self):
        self.assertEqual(b.karar(self.oz, dict(yon="YUKARI", guven=60), False)[0], "al")

    def test_zayif_guven_beklenir(self):
        self.assertEqual(b.karar(self.oz, dict(yon="YUKARI", guven=59), False)[0], "bekle")

    def test_rejim_kapisi(self):
        k, neden = b.karar(dict(r4=-2.0), dict(yon="YUKARI", guven=90), False)
        self.assertEqual(k, "bekle"); self.assertIn("rejim", neden)

    def test_acil_durdurma_alimi_keser(self):
        self.assertEqual(b.karar(self.oz, dict(yon="YUKARI", guven=90), False, killed=True)[0], "bekle")

    def test_asagi_satar_pozisyon_varsa(self):
        self.assertEqual(b.karar(self.oz, dict(yon="ASAGI", guven=70), True, poz_pct=1.0)[0], "sat")
        self.assertEqual(b.karar(self.oz, dict(yon="ASAGI", guven=50), True, poz_pct=1.0)[0], "bekle")


class CalistirTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        self.d = tempfile.mkdtemp()
        self.paper = Paper(os.path.join(self.d, "btc.db"), ekosistem="btc", dagit=False)
        self.durum = os.path.join(self.d, "durum.json")

    def tearDown(self):
        self.paper.db.close()
        os.environ.clear(); os.environ.update(self._env)

    def _tur(self, metin, mum, fiyat, now):
        return b.calistir(self.paper, _Quoter(fiyat), s=_Oturum(mum), post=_post(metin), now=now, durum_yolu=self.durum)

    def test_kapali(self):
        os.environ.pop("BTC_ONGORU", None)
        self.assertEqual(b.calistir(self.paper, _Quoter(1)), dict(durum="kapali"))

    def test_al_sonra_asagi_sat_ve_puanla(self):
        os.environ["BTC_ONGORU"] = "1"
        mum = _mum(adim=0.001); f = mum[-1][2]; now = mum[-1][1] + 10
        d = self._tur('{"yon":"YUKARI","guven":80,"gerekce":"x"}', mum, f, now)
        self.assertEqual((d["karar"], d["islem"]), ("al", "KOPYALANDI"))
        pos = self.paper.position(b.BTC_MINT)
        self.assertAlmostEqual(pos["cost"], 50.0, places=2)           # özsermayenin yarısı (nakit - rezerv daha büyük)
        with open(self.durum) as f: self.assertEqual(json.load(f)["karar"], "al")
        # 5 saat sonra: fiyat yükselmiş, YZ aşağı diyor -> satış; ilk tahmin isabetli puanlanır
        mum2 = _mum(n=77, adim=0.001); f2 = mum2[-1][2]
        d2 = self._tur('{"yon":"ASAGI","guven":75,"gerekce":"y"}', mum2, f2, mum2[-1][1] + 10)
        self.assertEqual((d2["karar"], d2["islem"]), ("sat", "KOPYALANDI"))
        self.assertIsNone(self.paper.position(b.BTC_MINT))
        oz = b.ozet(self.paper)
        self.assertEqual(oz["yz"]["n"], 1); self.assertEqual(oz["yz"]["isabet_pct"], 100.0)
        self.assertEqual(oz["kapanan"], 1); self.assertGreater(oz["kz"], 0)
        self.assertIsNotNone(oz["btc_tut_pct"])

    def test_yz_hatasinda_islem_yok(self):
        os.environ["BTC_ONGORU"] = "1"
        mum = _mum(); q = _Quoter(mum[-1][2])
        def bozuk(govde): raise OSError("503")
        d = b.calistir(self.paper, q, s=_Oturum(mum), post=bozuk, now=mum[-1][1] + 10, durum_yolu=self.durum)
        self.assertEqual(d["karar"], "bekle"); self.assertIn("OSError", d["hata"])
        self.assertEqual(q.n, 0)                                     # teklif bile istenmedi
        self.assertIsNone(self.paper.position(b.BTC_MINT))

    def test_yuksek_etki_alimi_engeller(self):
        os.environ["BTC_ONGORU"] = "1"
        mum = _mum()
        d = b.calistir(self.paper, _Quoter(mum[-1][2], etki=2.5), s=_Oturum(mum), post=_post('{"yon":"YUKARI","guven":90,"gerekce":"x"}'),
                       now=mum[-1][1] + 10, durum_yolu=self.durum)
        self.assertEqual(d["karar"], "bekle"); self.assertIn("etki", d["neden"])

    def test_zarar_kes(self):
        os.environ["BTC_ONGORU"] = "1"
        mum = _mum(); f = mum[-1][2]
        self._tur('{"yon":"YUKARI","guven":80,"gerekce":"x"}', mum, f, mum[-1][1] + 10)
        d = self._tur('{"yon":"YUKARI","guven":80,"gerekce":"x"}', mum, f * 0.95, mum[-1][1] + 3700)
        self.assertEqual(d["karar"], "sat"); self.assertIn("zarar kes", d["neden"])


class RejimTest(unittest.TestCase):
    def test_kovalar_ve_kapi(self):
        mum = _mum(n=60, adim=-0.01)                                  # sürekli düşüş: 4 saatte ~%-3,9
        ts = mum[-1][1] + 1
        pozlar = [(ts, -1.0, 5.0), (ts, -0.5, 5.0), (mum[0][0], 2.0, 5.0)]   # sonuncusu ölçülemez (geçmiş yok)
        satir, olcusuz = btc_rejim.kova_analiz(pozlar, mum)
        self.assertEqual(olcusuz, 1)
        ilk = satir[0]
        self.assertEqual((ilk["n"], ilk["toplam"], ilk["kazanma_pct"]), (2, -1.5, 0.0))
        k = btc_rejim.kapi_karsi_olgu(pozlar, mum, -2.0)
        self.assertEqual((k["atlanacak"], k["atlanacak_kz"]), (2, -1.5))


if __name__ == "__main__":
    unittest.main()
