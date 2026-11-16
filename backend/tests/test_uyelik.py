import time
import unittest
from nexora.uyelik import Uyelik, UyelikHatasi, adres_gecerli, komisyon_hesapla, maskele

ADRES = "So11111111111111111111111111111111111111112"


class Test(unittest.TestCase):
    def test_kayit_giris_oturum(self):
        u = Uyelik()
        tok = u.kayit("Ali@Ornek.com", "gizli-parola-1")
        self.assertEqual(u.uye(tok)["eposta"], "ali@ornek.com")
        with self.assertRaises(UyelikHatasi): u.kayit("ali@ornek.com", "baska-parola-1")      # aynı e-posta
        with self.assertRaises(UyelikHatasi): u.kayit("kotu", "gizli-parola-1")
        with self.assertRaises(UyelikHatasi): u.kayit("b@ornek.com", "kisa")
        self.assertIsNotNone(u.uye(u.giris("ali@ornek.com", "gizli-parola-1")))
        with self.assertRaises(UyelikHatasi): u.giris("ali@ornek.com", "yanlis-parola")
        u.cikis(tok); self.assertIsNone(u.uye(tok)); self.assertIsNone(u.uye(""))

    def test_parola_dugun_saklanmaz_ve_oturum_ozeti(self):
        u = Uyelik(); tok = u.kayit("a@b.co", "gizli-parola-1")
        satir = u.db.execute("SELECT * FROM uye").fetchone()
        self.assertNotIn(b"gizli-parola-1", bytes(satir["ozet"]))
        self.assertIsNone(u.db.execute("SELECT 1 FROM oturum WHERE ozet=?", (tok,)).fetchone())   # ham anahtar yok

    def test_oturum_suresi(self):
        u = Uyelik(); tok = u.kayit("a@b.co", "gizli-parola-1")
        self.assertIsNone(u.uye(tok, now=time.time() + 31 * 86400))

    def test_deneme_siniri(self):
        u = Uyelik(); u.kayit("a@b.co", "gizli-parola-1"); now = time.time()
        for _ in range(5):
            with self.assertRaises(UyelikHatasi): u.giris("a@b.co", "yanlis-yanlis", now)
        with self.assertRaises(PermissionError): u.giris("a@b.co", "gizli-parola-1", now)         # doğru parola bile kilitli
        self.assertTrue(u.giris("a@b.co", "gizli-parola-1", now + 700))

    def test_davet(self):
        u = Uyelik(); t1 = u.kayit("a@b.co", "gizli-parola-1"); kod = u.uye(t1)["davet_kodu"]
        self.assertEqual(len(kod), 8)
        u.kayit("veli@ornek.com", "gizli-parola-1", kod.lower())
        with self.assertRaises(UyelikHatasi): u.kayit("c@d.co", "gizli-parola-1", "YOKKODXX")
        p = u.profil(u.uye(t1))
        self.assertEqual(p["davet_sayisi"], 1)
        self.assertEqual(p["davetliler"][0]["eposta"], "ve***@ornek.com")
        self.assertEqual(maskele("ab@x.com"), "a***@x.com")

    def test_baglanti(self):
        u = Uyelik(); me = u.uye(u.kayit("a@b.co", "gizli-parola-1"))
        self.assertTrue(adres_gecerli(ADRES)); self.assertFalse(adres_gecerli("kisa")); self.assertFalse(adres_gecerli("0" * 44))
        u.baglanti_kaydet(me["id"], "phantom", ADRES)
        ph = [b for b in u.baglantilar(me["id"]) if b["tur"] == "phantom"][0]
        self.assertEqual((ph["durum"], ph["adres"]), ("bağlı", ADRES))
        with self.assertRaises(UyelikHatasi): u.baglanti_kaydet(me["id"], "borsa", "anahtar")      # borsa anahtarı bu yoldan alınmaz
        with self.assertRaises(UyelikHatasi): u.baglanti_kaydet(me["id"], "jupiter", "x")
        with self.assertRaises(UyelikHatasi): u.baglanti_kaydet(me["id"], "phantom", "5" * 88)     # uzun gizli anahtar biçimi reddedilir
        u.baglanti_sil(me["id"], "phantom")
        self.assertEqual([b for b in u.baglantilar(me["id"]) if b["tur"] == "phantom"][0]["durum"], "bağlı değil")
        self.assertEqual({b["tur"]: b["durum"] for b in u.baglantilar(me["id"])}["borsa"], "bağlı değil")

    def test_komisyon(self):
        k = komisyon_hesapla(100, 10, 20)
        self.assertEqual((k["komisyon"], k["net_kar"], k["net_bakiye"]), (2.0, 8.0, 108.0))
        k = komisyon_hesapla(100, -5, 20)                                    # zararda komisyon yok
        self.assertEqual((k["komisyon"], k["net_bakiye"]), (0.0, 95.0))
        self.assertEqual(komisyon_hesapla(100, 10, 999)["komisyon_pct"], 50.0)   # üst sınır
        b = Uyelik.bakiye(100, 3.54, 20)
        self.assertTrue(b["sanal"]); self.assertEqual(b["brut_bakiye"], 103.54)


if __name__ == "__main__":
    unittest.main()


class TestPortfoy(unittest.TestCase):
    def test_kisisel_hesap_katilimdan_itibaren(self):
        u = Uyelik(); a = u.uye(u.kayit("a@b.co", "gizli-parola-1"))["id"]; b = u.uye(u.kayit("c@d.co", "gizli-parola-1"))["id"]
        r = u.uye_bakiye(a, 103.54, 20)                                   # ilk bakış: 100 USDC ile şimdi başlar
        self.assertEqual((r["baslangic"], r["brut_kar"], r["komisyon"]), (100.0, 0.0, 0.0))
        u.portfoy_baslat(b, 1000, 103.54)
        r = u.uye_bakiye(b, 113.894, 20)                                  # sistem +%10
        self.assertAlmostEqual(r["brut_kar"], 100.0, places=1); self.assertAlmostEqual(r["komisyon"], 20.0, places=1)
        self.assertAlmostEqual(r["net_bakiye"], 1080.0, places=1); self.assertAlmostEqual(r["getiri_pct"], 10.0, places=1)
        r = u.uye_bakiye(b, 98.363, 20)                                   # sistem katılıma göre −%5: komisyon yok, zirve korunur
        self.assertEqual(r["komisyon"], 0.0); self.assertAlmostEqual(r["zirve"], 1100.0, places=1)
        self.assertAlmostEqual(r["zirveden_dusus_pct"], (1100 - 950) / 1100 * 100, places=1)
        self.assertAlmostEqual(u.uye_bakiye(a, 98.363, 20)["getiri_pct"], -5.0, places=1)   # a'nın hesabı ayrı

    def test_sinirlar(self):
        u = Uyelik(); a = u.uye(u.kayit("a@b.co", "gizli-parola-1"))["id"]
        for kotu in (5, 1e9, "abc", None):
            with self.assertRaises(UyelikHatasi): u.portfoy_baslat(a, kotu, 100)
        with self.assertRaises(UyelikHatasi): u.portfoy_baslat(a, 100, 0)
