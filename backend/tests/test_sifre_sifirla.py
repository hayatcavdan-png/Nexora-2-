import unittest
from nexora.uyelik import Uyelik, UyelikHatasi, SIFIRLA_SN
from nexora import eposta as E


class Kutu:
    def __init__(self): self.kodlar = []
    def __call__(self, alici, kod): self.kodlar.append((alici, kod))


class SifreSifirlaTest(unittest.TestCase):
    def setUp(self):
        self.u = Uyelik(); self.u.kayit("a@b.co", "eski-parola-1"); self.kutu = Kutu()

    def test_kod_ile_parola_degisir_ve_eski_oturumlar_kapanir(self):
        eski = self.u.giris("a@b.co", "eski-parola-1")
        self.u.sifre_sifirla_iste("A@B.co", self.kutu)
        alici, kod = self.kutu.kodlar[0]
        self.assertEqual(alici, "a@b.co")
        yeni = self.u.sifre_sifirla("a@b.co", kod.lower(), "yeni-parola-2")
        self.assertIsNone(self.u.uye(eski))                       # eski oturum kapandı
        self.assertIsNotNone(self.u.uye(yeni))                    # bu cihaza yeni oturum
        self.assertIsNotNone(self.u.giris("a@b.co", "yeni-parola-2"))
        with self.assertRaises(UyelikHatasi): self.u.giris("a@b.co", "eski-parola-1")

    def test_kod_tek_kullanimlik(self):
        self.u.sifre_sifirla_iste("a@b.co", self.kutu); kod = self.kutu.kodlar[0][1]
        self.u.sifre_sifirla("a@b.co", kod, "yeni-parola-2")
        with self.assertRaises(UyelikHatasi): self.u.sifre_sifirla("a@b.co", kod, "baska-parola-3")

    def test_yanlis_ve_suresi_dolmus_kod(self):
        self.u.sifre_sifirla_iste("a@b.co", self.kutu); kod = self.kutu.kodlar[0][1]
        with self.assertRaises(UyelikHatasi): self.u.sifre_sifirla("a@b.co", "YANLIS00", "yeni-parola-2")
        with self.assertRaises(UyelikHatasi):
            self.u.sifre_sifirla("a@b.co", kod, "yeni-parola-2", now=__import__("time").time() + SIFIRLA_SN + 5)

    def test_yanlis_kod_denemesi_sinirlanir(self):
        self.u.sifre_sifirla_iste("a@b.co", self.kutu); kod = self.kutu.kodlar[0][1]
        for _ in range(5):
            with self.assertRaises(UyelikHatasi): self.u.sifre_sifirla("a@b.co", "YANLIS00", "yeni-parola-2")
        with self.assertRaises(PermissionError): self.u.sifre_sifirla("a@b.co", kod, "yeni-parola-2")

    def test_istek_siniri_ve_hesap_yokken_sessiz(self):
        for _ in range(3): self.u.sifre_sifirla_iste("a@b.co", self.kutu)
        with self.assertRaises(PermissionError): self.u.sifre_sifirla_iste("a@b.co", self.kutu)
        n = len(self.kutu.kodlar)
        self.u.sifre_sifirla_iste("yok@b.co", self.kutu)          # hesap yok: hata yok, e-posta da gitmez
        self.assertEqual(len(self.kutu.kodlar), n)

    def test_kod_veritabaninda_duz_metin_degil(self):
        self.u.sifre_sifirla_iste("a@b.co", self.kutu); kod = self.kutu.kodlar[0][1]
        satir = self.u.db.execute("SELECT ozet FROM sifirla").fetchone()[0]
        self.assertNotIn(kod, satir)

    def test_ayar_eksikse_gonderim_hata_verir(self):
        with self.assertRaises(E.EpostaHatasi):
            E.gonder("a@b.co", "k", "m", cfg=dict(host="", port=587, kullanici="", parola="", gonderen=""))

    def test_smtp_akisi(self):
        class S:
            def __init__(self, h, p, timeout=None): self.log = [("baglan", h, p)]
            def __enter__(self): return self
            def __exit__(self, *a): self.log.append(("kapat",))
            def starttls(self, context=None): self.log.append(("tls",))
            def login(self, k, p): self.log.append(("giris", k))
            def send_message(self, m): self.log.append(("gonder", m["To"], m["From"]))
        s = {}
        def fabrika(h, p, timeout=None):
            s["x"] = S(h, p, timeout); return s["x"]
        E.gonder("a@b.co", "konu", "metin", cfg=dict(host="smtp.x", port=587, kullanici="g@x", parola="p", gonderen="g@x"), smtp=fabrika)
        self.assertEqual(s["x"].log, [("baglan", "smtp.x", 587), ("tls",), ("giris", "g@x"), ("gonder", "a@b.co", "g@x"), ("kapat",)])


if __name__ == "__main__":
    unittest.main()
