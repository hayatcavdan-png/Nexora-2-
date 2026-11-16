import os, stat, tempfile, unittest
from nexora.kasa import Kasa, KasaHatasi, maskele


class Test(unittest.TestCase):
    def test_gidis_donus_ve_rastgelelik(self):
        k = Kasa(ana=bytes(range(32)))
        a, b = k.sifrele("gizli-api-anahtari", "uye:1:binance"), k.sifrele("gizli-api-anahtari", "uye:1:binance")
        self.assertNotEqual(a, b); self.assertNotIn("gizli", a)                      # aynı değer her seferinde farklı şifrelenir
        self.assertEqual(k.coz(a, "uye:1:binance"), "gizli-api-anahtari")
        self.assertEqual(k.coz(k.sifrele("ğüşİ ✓"), ""), "ğüşİ ✓")

    def test_degistirme_ve_baglam(self):
        k = Kasa(ana=bytes(range(32))); s = k.sifrele("deger", "uye:1:binance")
        with self.assertRaises(KasaHatasi): k.coz(s, "uye:2:binance")                # başka üyenin satırına kopyalanamaz
        import base64
        ham = bytearray(base64.b64decode(s[3:])); ham[20] ^= 1
        with self.assertRaises(KasaHatasi): k.coz("v1:" + base64.b64encode(bytes(ham)).decode(), "uye:1:binance")
        with self.assertRaises(KasaHatasi): Kasa(ana=bytes(32)).coz(s, "uye:1:binance")   # başka anahtar
        for kotu in ("duz-metin", "v1:@@@", "v1:" + "A" * 8):
            with self.assertRaises(KasaHatasi): k.coz(kotu)
        with self.assertRaises(KasaHatasi): k.sifrele("")

    def test_anahtar_dosyasi(self):
        yol = os.path.join(tempfile.mkdtemp(), "kasa.key")
        k1 = Kasa(yol); s = k1.sifrele("x")
        self.assertEqual(stat.S_IMODE(os.stat(yol).st_mode), 0o600)
        self.assertEqual(Kasa(yol).coz(s), "x")                                       # aynı dosya: aynı anahtar
        open(yol, "w").write("bozuk")
        with self.assertRaises(KasaHatasi): Kasa(yol)
        self.assertEqual(maskele("abcdefgh123"), "••••••h123"); self.assertEqual(maskele("ab"), "••••")


if __name__ == "__main__":
    unittest.main()
