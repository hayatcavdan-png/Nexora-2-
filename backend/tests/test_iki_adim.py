import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import uyelik as U


class TotpTests(unittest.TestCase):
    def test_rfc6238_ornegi(self):
        g = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"                  # "12345678901234567890"
        self.assertEqual(U.totp(g, 59 // 30), "287082")             # RFC 6238: 94287082 (8 hane) -> son 6
        self.assertEqual(U.totp_dogrula(g, "287 082", 59), 1)
        self.assertIsNone(U.totp_dogrula(g, "287082", 59, son=1))   # aynı kod ikinci kez geçmez
        self.assertIsNone(U.totp_dogrula(g, "12345", 59)); self.assertIsNone(U.totp_dogrula(g, "000000", 10_000))

    def test_akis(self):
        u = U.Uyelik(); u.kayit("a@b.co", "parola123"); uid = u.db.execute("SELECT id FROM uye").fetchone()[0]
        k = u.iki_adim_kur(uid); self.assertTrue(k["uri"].startswith("otpauth://totp/NEXORA:a%40b.co?secret="))
        self.assertTrue(u.giris("a@b.co", "parola123", now=1000))               # kurulum bitmeden giriş kodsuz
        with self.assertRaises(U.UyelikHatasi): u.iki_adim_onayla(uid, "000000", now=1000)
        t = 1_000_000.0
        u.iki_adim_onayla(uid, U.totp(k["gizli"], int(t // 30)), now=t)
        self.assertTrue(u.profil(u.uye(u.giris("a@b.co", "parola123", now=t + 60, kod=U.totp(k["gizli"], int((t + 60) // 30))), now=t + 60))["iki_adim"])
        with self.assertRaises(U.UyelikHatasi) as e: u.giris("a@b.co", "parola123", now=t + 120)
        self.assertEqual(str(e.exception), U.IKI_ADIM_GEREKLI)
        with self.assertRaises(U.UyelikHatasi): u.giris("a@b.co", "parola123", now=t + 120, kod="111111")
        with self.assertRaises(U.UyelikHatasi): u.giris("a@b.co", "yanlis", now=t + 120, kod=U.totp(k["gizli"], int((t + 120) // 30)))
        with self.assertRaises(U.UyelikHatasi): u.iki_adim_kur(uid)                # açıkken yeniden kurulamaz
        with self.assertRaises(U.UyelikHatasi): u.iki_adim_kapat(uid, "yanlis", U.totp(k["gizli"], int((t + 150) // 30)), now=t + 150)
        u.iki_adim_kapat(uid, "parola123", U.totp(k["gizli"], int((t + 180) // 30)), now=t + 180)
        self.assertTrue(u.giris("a@b.co", "parola123", now=t + 200))

    def test_deneme_siniri_ve_sunucu_sifirlama(self):
        u = U.Uyelik(); u.kayit("c@d.co", "parola123"); uid = u.db.execute("SELECT id FROM uye").fetchone()[0]
        k = u.iki_adim_kur(uid); t = 2_000_000.0; u.iki_adim_onayla(uid, U.totp(k["gizli"], int(t // 30)), now=t)
        for _ in range(U.GIRIS_DENEME):
            with self.assertRaises(U.UyelikHatasi): u.giris("c@d.co", "parola123", now=t + 40, kod="000000")
        with self.assertRaises(PermissionError): u.giris("c@d.co", "parola123", now=t + 40, kod=U.totp(k["gizli"], int((t + 40) // 30)))
        u.iki_adim_sifirla("c@d.co"); self.assertTrue(u.giris("c@d.co", "parola123", now=t + 50))     # telefon kaybı: sunucudan kapatılır


if __name__ == "__main__": unittest.main()
