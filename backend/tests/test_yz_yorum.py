import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import yz_yorum as Y


class Yanit:
    def __init__(self, kod, govde): self.status_code, self._g, self.text = kod, govde, str(govde)
    def json(self): return self._g


class FakeS:
    def __init__(self, kod=200): self.kod, self.cagri = kod, []
    def post(self, url, **kw):
        self.cagri.append(kw); return Yanit(self.kod, {"content": [{"type": "text", "text": "Özet: deneme."}]})


class YorumTests(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()

    def test_anahtarsiz_kural(self):
        r = Y.analiz("hl", "rapor", "kural metni", dizin=self.d, anahtar="")
        self.assertFalse(r["etkin"]); self.assertEqual(r["metin"], "kural metni"); self.assertIn("ANTHROPIC_API_KEY", r["uyari"])

    def test_cagri_onbellek_ve_yenile(self):
        s = FakeS()
        r = Y.analiz("hl", "rapor", dizin=self.d, now=1000, anahtar="k", s=s)
        self.assertEqual((r["kaynak"], r["metin"]), ("yz", "Özet: deneme."))
        h = s.cagri[0]["headers"]; self.assertEqual(h["x-api-key"], "k")
        self.assertIn("PAPER", s.cagri[0]["json"]["system"])
        self.assertEqual(Y.analiz("hl", "rapor", dizin=self.d, now=2000, anahtar="k", s=s)["kaynak"], "onbellek")   # 1 saat
        self.assertEqual(Y.analiz("hl", "rapor", yenile=True, dizin=self.d, now=1100, anahtar="k", s=s)["kaynak"], "onbellek")  # 5 dk
        self.assertEqual(Y.analiz("hl", "rapor", yenile=True, dizin=self.d, now=1400, anahtar="k", s=s)["kaynak"], "yz")
        self.assertEqual(len(s.cagri), 2)

    def test_hata_ve_gunluk_sinir(self):
        r = Y.analiz("teshis", "x", "kural", dizin=self.d, now=1000, anahtar="k", s=FakeS(500))
        self.assertEqual(r["kaynak"], "kural"); self.assertIn("başarısız", r["uyari"])
        eski = Y.GUNLUK; Y.GUNLUK = 1
        try:
            s = FakeS(); Y.analiz("teshis", "x", dizin=self.d, now=1000, anahtar="k", s=s)
            r = Y.analiz("teshis", "x", yenile=True, dizin=self.d, now=1400, anahtar="k", s=s)
            self.assertIn("sınırı", r["uyari"]); self.assertEqual(len(s.cagri), 1)
        finally:
            Y.GUNLUK = eski
        with self.assertRaises(ValueError): Y.analiz("baska", "x", dizin=self.d, anahtar="")

    def test_kural_yorumu(self):
        self.assertIn("Henüz", Y.kural_yorumu_hl(None))
        r = dict(kapanan=5, biz=dict(n=5, ort=1.2, medyan=0.5, pozitif=60), kaynak=dict(n=5, ort=2.0, medyan=1, pozitif=60),
                 dk30=dict(n=5, ort=-0.3, medyan=0, pozitif=40), gecikme_pct=0.05)
        m = Y.kural_yorumu_hl(r); self.assertIn("5 kapanan", m); self.assertIn("küçük", m)


if __name__ == "__main__": unittest.main()
