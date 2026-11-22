import os, sys, sqlite3, tempfile, time, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import asistan as A
from nexora import uye_ekran as U


class Yanit:
    def __init__(self, kod, govde): self.status_code, self._g, self.text = kod, govde, str(govde)
    def json(self): return self._g


class FakeS:
    def __init__(self, kod=200): self.kod, self.cagri = kod, []
    def post(self, url, **kw):
        self.cagri.append(kw); return Yanit(self.kod, {"content": [{"type": "text", "text": "Bugün iyi gitti."}]})


GIZLI = "WaLLetAdres1111111111111111111111111111111"


class FakePaper:
    def __init__(self, now):
        self.now = now
    def portfolio(self):
        return dict(cash=90.0, equity=104.2, pnl=4.2, positions=[dict(token="T1", wallet=GIZLI)], killed=False)
    def trades(self, limit=50):
        n = self.now
        return [dict(ts=n - 60, side="sell", token="TokenAAAAAAAAAAAA", wallet=GIZLI, decision="KOPYALANDI", pnl=2.5, reason="kaynak satti"),
                dict(ts=n - 120, side="sell", token="TokenBBBBBBBBBBBB", wallet=GIZLI, decision="KOPYALANDI", pnl=-1.1, reason="zarar sınırı"),
                dict(ts=n - 200, side="buy", token="TokenAAAAAAAAAAAA", wallet=GIZLI, decision="KOPYALANDI", pnl=None, reason="ok"),
                dict(ts=n - 300, side="buy", token="TokenCCCCCCCCCCCC", wallet=GIZLI, decision="REDDEDILDI", pnl=None, reason="x")]


class AsistanTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.now = time.mktime(time.localtime()[:3] + (15, 0, 0, 0, 0, -1))
        self.p = FakePaper(self.now)

    def test_veri_ve_kural_ozet(self):
        v = A.veri(self.p, self.now)
        self.assertEqual(v["bugun"], dict(adet=2, kazanan=1, kz=1.4))
        self.assertEqual(v["bugun_alim"], 1)
        self.assertEqual(v["son"][1]["neden"], "zarar sınırına geldi")
        m = A.kural_ozet(v)
        self.assertIn("2 işlem kapandı", m); self.assertIn("1 tanesi kârda", m)

    def test_cuzdan_adresi_modele_gitmez(self):
        s = FakeS()
        r = A.ozet(self.p, dizin=self.d, now=self.now, anahtar="k", s=s)
        self.assertEqual(r["kaynak"], "yz")
        govde = str(s.cagri[0]["json"])
        self.assertNotIn(GIZLI, govde); self.assertNotIn(GIZLI, str(r))
        self.assertEqual(A.ozet(self.p, dizin=self.d, now=self.now + 60, anahtar="k", s=s)["kaynak"], "onbellek")
        self.assertEqual(len(s.cagri), 1)

    def test_anahtarsiz_kural(self):
        self.assertEqual(A.ozet(self.p, dizin=self.d, now=self.now, anahtar="")["kaynak"], "kural")
        self.assertEqual(A.sor(self.p, 1, "nasıl gitti", dizin=self.d, now=self.now, anahtar="")["kaynak"], "kural")

    def test_soru_siniri(self):
        eski = A.SORU_GUNLUK; A.SORU_GUNLUK = 2
        try:
            s = FakeS()
            r1 = A.sor(self.p, 7, "bugün nasıl?", dizin=self.d, now=self.now, anahtar="k", s=s)
            self.assertEqual((r1["kaynak"], r1["kalan"]), ("yz", 1))
            A.sor(self.p, 7, "ya dün?", dizin=self.d, now=self.now, anahtar="k", s=s)
            r3 = A.sor(self.p, 7, "bir daha", dizin=self.d, now=self.now, anahtar="k", s=s)
            self.assertEqual(r3["kaynak"], "kural"); self.assertIn("doldu", r3["metin"])
            self.assertEqual(A.sor(self.p, 8, "ben?", dizin=self.d, now=self.now, anahtar="k", s=s)["kaynak"], "yz")   # başka üye
            self.assertEqual(len(s.cagri), 3)
        finally:
            A.SORU_GUNLUK = eski

    def test_bos_soru_ve_hata(self):
        with self.assertRaises(ValueError): A.sor(self.p, 1, "   ", dizin=self.d, anahtar="k")
        r = A.sor(self.p, 1, "x", dizin=self.d, now=self.now, anahtar="k", s=FakeS(500))
        self.assertEqual(r["kaynak"], "kural")


class KopyaOzetTests(unittest.TestCase):
    def test_takma_ad_kalici_ve_adressiz(self):
        a = U.takma_ad(GIZLI)
        self.assertEqual(a, U.takma_ad(GIZLI)); self.assertTrue(a.startswith("Trader #")); self.assertNotIn(GIZLI[:4], a)
        self.assertNotEqual(a, U.takma_ad(GIZLI + "x"))

    def test_kopya_ozet(self):
        d = tempfile.mkdtemp(); db = os.path.join(d, "p.db")
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, ts REAL, wallet TEXT, token TEXT, side TEXT, pnl REAL, decision TEXT)")
        now = time.time()
        c.executemany("INSERT INTO trades (ts, wallet, token, side, pnl, decision) VALUES (?,?,?,?,?,?)",
                      [(now - 100, "W1", "T", "sell", 3.0, "KOPYALANDI"), (now - 200, "W1", "T", "sell", -1.0, "KOPYALANDI"),
                       (now - 40 * 86400, "W1", "T", "sell", 50.0, "KOPYALANDI"), (now - 50, "W2", "T", "sell", 1.0, "REDDEDILDI")])
        c.commit(); c.close()
        eski = U.panel.cuzdanlar
        U.panel.cuzdanlar = lambda p, t: dict(cuzdanlar=[
            dict(wallet="W1", takipte=True, durum="aktif", kazanma_orani=65.0, medyan_tutma_sn=900, paper_acik=1),
            dict(wallet="W2", takipte=True, durum="aktif", kazanma_orani=40.0, medyan_tutma_sn=None, paper_acik=0),
            dict(wallet="W3", takipte=False, karar="kopyalanabilir")])
        try:
            r = U.kopya_ozet(db, None, now=now)
        finally:
            U.panel.cuzdanlar = eski
        self.assertEqual(r["deneniyor"], 1)
        k = r["kopyalanan"]
        self.assertEqual([x["kapanan"] for x in k], [2, 0])
        self.assertEqual((k[0]["kz"], k[0]["bizim_kazanma"]), (2.0, 50.0))
        self.assertEqual(k[0]["etiketler"], ["Hızlı al-sat", "İsabetli", "Şu an pozisyonda"])
        self.assertNotIn("W1", str(r).replace("Trader", ""))
        self.assertIsNone(k[1]["bizim_kazanma"])


if __name__ == "__main__":
    unittest.main()
