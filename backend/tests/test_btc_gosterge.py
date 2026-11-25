import json, math, os, random, tempfile, unittest

from nexora import btc_gosterge as G, btc_ongoru as b, btc_sinama as S
from nexora.core import Paper
from tests.test_btc_ongoru import _Oturum, _Quoter, _mum, _post


def _rejimli(n=1500, tohum=7, blok=48, egim=0.004, gurultu=0.002):
    """Sırayla 48 saat yükselen / 48 saat düşen, gürültülü seri: trend izleyen kuralların gerçek avantajı vardır."""
    rnd = random.Random(tohum); out, f, t0 = [], 50_000.0, 1_700_000_000.0
    for i in range(n):
        yon = 1 if (i // blok) % 2 == 0 else -1
        f *= 1 + yon * egim + rnd.gauss(0, gurultu)
        a = t0 + i * 3600
        out.append((a, a + 3599.999, f, f * 1.002, f * 0.998, 100 + rnd.random() * 50))
    return out


def _rastgele(n=1500, tohum=3):
    rnd = random.Random(tohum); out, f, t0 = [], 50_000.0, 1_700_000_000.0
    for i in range(n):
        f *= 1 + rnd.gauss(0, 0.004)
        a = t0 + i * 3600
        out.append((a, a + 3599.999, f, f * 1.002, f * 0.998, 100.0))
    return out


class GostergeTest(unittest.TestCase):
    def test_ema_sabit_seride_sabit(self):
        e = G.ema([5.0] * 30, 10)
        self.assertIsNone(e[8]); self.assertAlmostEqual(e[-1], 5.0)

    def test_rsi_uclar(self):
        self.assertEqual(G.rsi([float(i) for i in range(1, 40)]), 100.0)
        self.assertAlmostEqual(G.rsi([10.0, 11.0] * 20), 50.0, delta=5)
        self.assertIsNone(G.rsi([1.0] * 10))

    def test_bollinger_ve_atr(self):
        k = [100.0] * 19 + [110.0]
        self.assertGreater(G.bollinger_b(k), 1.0 - 1e-9)
        self.assertGreater(G.atr_pct(_mum()), 0)

    def test_macd_yukselen_seride_pozitif(self):
        m = G.macd([100 * 1.002 ** i for i in range(80)])
        self.assertGreater(m[0], 0)

    def test_sinyaller_yukselen(self):
        s = G.sinyaller(G.hesapla(_mum(adim=0.002)))
        self.assertEqual((s["ema_kesisim"], s["trend_ema50"], s["momentum"], s["rsi"]), (1, 1, 1, -1))
        self.assertEqual(set(s), set(G.KURALLAR))

    def test_topluluk(self):
        s = dict(rsi=-1, macd=1, bollinger=0, ema_kesisim=1, trend_ema50=1, momentum=-1)
        self.assertEqual(G.topluluk(s, None), 0.0)
        self.assertEqual(G.topluluk(s, dict(rsi=0, macd=0)), 0.0)
        self.assertAlmostEqual(G.topluluk(s, dict(ema_kesisim=3, rsi=1)), 0.5)
        self.assertEqual((G.yon(0.2), G.yon(-0.2), G.yon(0.1)), ("YUKARI", "ASAGI", "BELIRSIZ"))

    def test_yetersiz_mum(self):
        with self.assertRaises(ValueError): G.hesapla(_mum(n=59))


class SinamaTest(unittest.TestCase):
    def test_gelecegi_gormez(self):
        m = _rejimli(400)
        i = 250
        once = [o for o in S.ornekler(m) if o[0] == i][0][1]
        bozuk = m[:i + 1] + [(a, kt, k * 3, y * 3, d * 3, h) for a, kt, k, y, d, h in m[i + 1:]]
        sonra = [o for o in S.ornekler(bozuk) if o[0] == i][0][1]
        self.assertEqual(once, sonra)

    def test_trendli_veride_trend_kurali_kanit_bulur(self):
        s = S.sina(_rejimli())
        self.assertGreater(s["agirlik"]["trend_ema50"] + s["agirlik"]["ema_kesisim"], 0)
        self.assertGreaterEqual(s["kurallar"]["ema_kesisim"]["sinama"]["z"], S.MIN_Z)
        self.assertTrue(s["kanit"])
        self.assertEqual(s["egitim_ornek"] + s["sinama_ornek"], s["ornek"])

    def test_rastgele_veride_kanit_yok_ya_da_zayif(self):
        s = S.sina(_rastgele())
        for k, v in s["kurallar"].items():
            z = v["sinama"]["z"]
            self.assertTrue(z is None or abs(z) < 3.5, (k, z))     # rastgele yürüyüşte güçlü 'avantaj' çıkmamalı

    def test_maliyet_dusulur(self):
        orn = S.ornekler(_rejimli(600))
        bedava = S.strateji(orn, lambda s: s["ema_kesisim"] == 1, maliyet=0.0)
        pahali = S.strateji(orn, lambda s: s["ema_kesisim"] == 1, maliyet=0.01)
        self.assertGreater(bedava["getiri_pct"], pahali["getiri_pct"]); self.assertGreater(bedava["islem"], 0)

    def test_yetersiz_veri(self):
        with self.assertRaises(ValueError): S.sina(_rejimli(200))

    def test_yaz_ve_yukle(self):
        d = tempfile.mkdtemp(); yol = os.path.join(d, "a.json")
        S.yaz(dict(agirlik=dict(macd=1.0), kanit=False), yol)
        self.assertEqual(b.agirlik_yukle(yol)["agirlik"], dict(macd=1.0))
        self.assertIsNone(b.agirlik_yukle(os.path.join(d, "yok.json")))


class ToplulukKararTest(unittest.TestCase):
    oz = dict(r4=0.5)

    def test_gostergeler_karsiysa_alim_yok(self):
        k, neden = b.karar(self.oz, dict(yon="YUKARI", guven=90), False, skor=-0.5)
        self.assertEqual(k, "bekle"); self.assertIn("göstergeler", neden)
        self.assertEqual(b.karar(self.oz, dict(yon="YUKARI", guven=90), False, skor=0.0)[0], "al")

    def test_gostergeler_asagi_satar_yz_guclu_yukari_degilse(self):
        self.assertEqual(b.karar(self.oz, dict(yon="BELIRSIZ", guven=40), True, poz_pct=0.5, skor=-0.4)[0], "sat")
        self.assertEqual(b.karar(self.oz, dict(yon="YUKARI", guven=80), True, poz_pct=0.5, skor=-0.4)[0], "bekle")


class CalistirToplulukTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ); os.environ["BTC_ONGORU"] = "1"
        self.d = tempfile.mkdtemp()
        self.paper = Paper(os.path.join(self.d, "btc.db"), ekosistem="btc", dagit=False)
        self.agirlik = os.path.join(self.d, "agirlik.json")
        S.yaz(dict(agirlik=dict(ema_kesisim=1.0, trend_ema50=1.0), kanit=True, ts=1.0,
                   topluluk_sinama=dict(getiri_pct=5.0, tut_pct=2.0, islem=4), ornek=900,
                   kurallar={k: dict(sinama=dict(isabet_al=55.0, baz_yukari=50.0, z=1.5, n_al=100)) for k in G.KURALLAR}),
              self.agirlik)

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)

    def test_istem_gostergeleri_ve_karneyi_tasir(self):
        gonderilen = {}
        def post(govde):
            gonderilen["metin"] = json.loads(govde.decode("utf-8"))["input"]
            return _post('{"yon":"YUKARI","guven":70,"gerekce":"trend"}')(govde)
        mum = _mum(adim=-0.002)                                     # düşüş: göstergeler aşağı
        d = b.calistir(self.paper, _Quoter(mum[-1][2]), s=_Oturum(mum), post=post, now=mum[-1][1] + 10,
                       durum_yolu=os.path.join(self.d, "d.json"), agirlik_yolu=self.agirlik)
        self.assertEqual(d["topluluk_yon"], "ASAGI"); self.assertLessEqual(d["topluluk_skor"], -0.2)
        self.assertEqual(d["karar"], "bekle"); self.assertIn("göstergeler", d["neden"])
        for anahtar in ("rsi14", "macd_hist_pct", "bb_b", "gosterge_sinyalleri", "topluluk_skoru", "gecmis_sinama"):
            self.assertIn(anahtar, gonderilen["metin"])
        oz = b.ozet(self.paper, agirlik_yolu=self.agirlik)
        self.assertTrue(oz["sinama"]["kanit"]); self.assertEqual(oz["topluluk"]["n"], 0)
        self.assertEqual(oz["tahminler"][0]["topluluk_yon"], "ASAGI")

    def test_kanit_yoksa_gostergeler_oy_kullanmaz(self):
        oz = b.ozellikler(_mum(adim=-0.002))
        _, skor, yon = b.topluluk_hesap(oz, dict(agirlik=dict(ema_kesisim=1.0), kanit=False))
        self.assertEqual((skor, yon), (0.0, "BELIRSIZ"))
        _, skor, yon = b.topluluk_hesap(oz, dict(agirlik=dict(ema_kesisim=1.0), kanit=True))
        self.assertEqual((skor, yon), (-1.0, "ASAGI"))

    def test_eski_sema_goc(self):
        db = self.paper.db
        db.executescript("CREATE TABLE btc_tahmin(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, fiyat REAL, yon TEXT, guven INTEGER,"
                         " gerekce TEXT, kural_yon TEXT, ozellik TEXT, karar TEXT, karar_neden TEXT, hedef_ts REAL, sonuc_fiyat REAL,"
                         " sonuc_pct REAL, isabet INTEGER, kural_isabet INTEGER, model TEXT, hata TEXT);")
        b.sema_kur(db); b.sema_kur(db)                               # iki kez: idempotent
        sutun = {r[1] for r in db.execute("PRAGMA table_info(btc_tahmin)")}
        self.assertTrue({"topluluk_yon", "topluluk_skor", "topluluk_isabet"} <= sutun)


if __name__ == "__main__":
    unittest.main()
