import os, sys, tempfile, time, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import uyelik as U

PAROLA = "guclu-parola-1"


class KayitOnayTests(unittest.TestCase):
    def setUp(self):
        self.u = U.Uyelik(os.path.join(tempfile.mkdtemp(), "u.db"))
        self.kutu = []
        self.gonder = lambda alici, kod: self.kutu.append((alici, kod))
        self.t = time.time()

    def kod(self):
        return self.kutu[-1][1]

    def test_kod_gelmeden_hesap_acilmaz_ve_dogru_kodla_acilir(self):
        r = self.u.kayit_iste("ali@ornek.com", PAROLA, gonder=self.gonder, now=self.t)
        self.assertTrue(r["onay_gerekli"])
        self.assertIsNone(self.u.db.execute("SELECT 1 FROM uye WHERE eposta='ali@ornek.com'").fetchone())
        tok = self.u.kayit_onayla("ali@ornek.com", self.kod(), now=self.t + 1)
        self.assertTrue(tok)
        self.assertIsNotNone(self.u.db.execute("SELECT 1 FROM uye WHERE eposta='ali@ornek.com'").fetchone())
        self.assertIsNone(self.u.db.execute("SELECT 1 FROM kayit_bekleyen WHERE eposta='ali@ornek.com'").fetchone())

    def test_yanlis_kod_ve_bes_deneme_sonrasi_iptal(self):
        self.u.kayit_iste("ali@ornek.com", PAROLA, gonder=self.gonder, now=self.t)
        for _ in range(U.KAYIT_KOD_DENEME):
            with self.assertRaises(U.UyelikHatasi):
                self.u.kayit_onayla("ali@ornek.com", "000000", now=self.t + 1)
        with self.assertRaises(U.UyelikHatasi):                      # doğru kod bile artık işe yaramaz
            self.u.kayit_onayla("ali@ornek.com", self.kod(), now=self.t + 2)

    def test_suresi_dolan_kod_reddedilir(self):
        self.u.kayit_iste("ali@ornek.com", PAROLA, gonder=self.gonder, now=self.t)
        with self.assertRaises(U.UyelikHatasi):
            self.u.kayit_onayla("ali@ornek.com", self.kod(), now=self.t + U.KAYIT_KOD_SN + 5)

    def test_gecici_eposta_engelli(self):
        self.assertTrue(U.engelli_posta("x@mailinator.com"))
        self.assertFalse(U.engelli_posta("x@gmail.com"))
        with self.assertRaises(U.UyelikHatasi):
            self.u.kayit_iste("x@mailinator.com", PAROLA, gonder=self.gonder, now=self.t)

    def test_mevcut_eposta_ve_gecersiz_davet(self):
        self.u.kayit_iste("ali@ornek.com", PAROLA, gonder=self.gonder, now=self.t)
        self.u.kayit_onayla("ali@ornek.com", self.kod(), now=self.t + 1)
        with self.assertRaises(U.UyelikHatasi):
            self.u.kayit_iste("ali@ornek.com", PAROLA, gonder=self.gonder, now=self.t + 2)
        with self.assertRaises(U.UyelikHatasi):
            self.u.kayit_iste("veli@ornek.com", PAROLA, davet="YOKTUR", gonder=self.gonder, now=self.t + 2)

    def test_davet_kodu_onay_sonrasi_eden_kisiye_baglanir(self):
        ev = self.u.kayit("sahip@ornek.com", PAROLA)        # eski yol: sahibin davet kodu var
        sahip = self.u.db.execute("SELECT id, davet_kodu FROM uye WHERE eposta='sahip@ornek.com'").fetchone()
        self.u.kayit_iste("yeni@ornek.com", PAROLA, davet=sahip["davet_kodu"], gonder=self.gonder, now=self.t)
        self.u.kayit_onayla("yeni@ornek.com", self.kod(), now=self.t + 1)
        yeni = self.u.db.execute("SELECT davet_eden FROM uye WHERE eposta='yeni@ornek.com'").fetchone()
        self.assertEqual(yeni["davet_eden"], sahip["id"])

    def test_eski_kayit_yolu_degismedi(self):
        self.assertTrue(self.u.kayit("eski@ornek.com", PAROLA))


if __name__ == "__main__":
    unittest.main()
