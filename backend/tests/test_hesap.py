import os, shutil, tempfile, unittest
from unittest import mock

class HesapTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.patch = mock.patch("nexora.hesap.DIZIN", self.dir)
        self.patch.start()
        import nexora.hesap as H
        H._acik.clear()
        self.H = H

    def tearDown(self):
        self.patch.stop()
        self.H._acik.clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_yeni_hesap_secilen_baslangic_ile_acilir(self):
        d = self.H.bot_ac(1, baslangic=250)
        self.assertTrue(d["bot"]); self.assertEqual(d["baslangic"], 250)
        self.assertEqual(self.H.portfoy(1)["cash"], 250)
        self.assertEqual(self.H.portfoy(1)["pnl"], 0)

    def test_baslangic_siniri_ve_zorunlulugu(self):
        with self.assertRaises(self.H.HesapHatasi): self.H.bot_ac(2)
        with self.assertRaises(self.H.HesapHatasi): self.H.bot_ac(2, baslangic=5)
        with self.assertRaises(self.H.HesapHatasi): self.H.bot_ac(2, baslangic=20000)

    def test_bot_kapali_iken_sinyal_islenmez(self):
        self.H.bot_ac(1, baslangic=100)
        self.H.bot_kapat(1, onay=True)
        with mock.patch.object(self.H.Paper, "handle_signal") as hs:
            self.H.dagit("e1", "w", "tok", "buy", 1.0, 1e6, 0)
            hs.assert_not_called()

    def test_bot_acik_iken_sinyal_uyeye_gider_ama_baska_uyeye_gitmez(self):
        self.H.bot_ac(1, baslangic=100)
        self.H.bot_ac(2, baslangic=100)
        self.H.bot_kapat(2, onay=True)
        with mock.patch.object(self.H.Paper, "handle_signal", return_value={"decision": "x"}) as hs, \
             mock.patch.object(self.H, "_zamanla", side_effect=lambda sn, fn, *a: fn(*a)), \
             mock.patch.object(self.H, "canli_fiyat", return_value=1.0):
            self.H.dagit("e1", "w", "tok", "buy", 1.0, 1e6, 0)
        self.assertEqual(hs.call_count, 1)
        self.assertEqual(hs.call_args[0][0], "e1|u1")

    def test_yonetici_once_islenir(self):
        self.H.bot_ac(1, baslangic=100)
        self.H.bot_ac(2, baslangic=100, oncelik=1)      # yönetici
        sira = []
        with mock.patch.object(self.H.Paper, "handle_signal", side_effect=lambda ev, *a: sira.append((ev, a[3])) or {}), \
             mock.patch.object(self.H, "_zamanla", side_effect=lambda sn, fn, *a: fn(*a)), \
             mock.patch.object(self.H, "canli_fiyat", return_value=2.5):
            self.H.dagit("e1", "w", "tok", "buy", 1.0, 1e6, 0)
        self.assertEqual(sira, [("e1|u2", 1.0), ("e1|u1", 2.5)])   # yönetici sinyal fiyatı, üye anlık fiyat

    def test_uye_fiyat_alinamazsa_islem_yapilmaz(self):
        self.H.bot_ac(1, baslangic=100)
        with mock.patch.object(self.H.Paper, "handle_signal") as hs, \
             mock.patch.object(self.H, "_zamanla", side_effect=lambda sn, fn, *a: fn(*a)), \
             mock.patch.object(self.H, "canli_fiyat", return_value=None):
            self.H.dagit("e1", "w", "tok", "buy", 1.0, 1e6, 0)
        hs.assert_not_called()

    def test_piyasa_fiyati_uye_pozisyonunu_degerler(self):
        self.H.bot_ac(1, baslangic=100)
        p = self.H._hesap(1)
        p.db.execute("INSERT INTO positions(token, qty, cost, last_price, wallet) VALUES('tok', 10, 5.0, 0.5, NULL)")
        p.db.commit()
        self.H.fiyat_isle("tok", 0.8)
        self.assertAlmostEqual(p.db.execute("SELECT last_price FROM positions WHERE token='tok'").fetchone()[0], 0.8)

    def test_gecikmeli_fiyat_sinyal_basina_tek_sefer(self):
        self.H.bot_ac(1, baslangic=100); self.H.bot_ac(2, baslangic=100)
        self.H.bot_kapat(2, onay=True)
        self.H.bot_ac(2, baslangic=100)
        with mock.patch.object(self.H, "canli_fiyat", return_value=2.0) as cf, \
             mock.patch.object(self.H, "_zamanla", side_effect=lambda sn, fn, *a: fn(*a)), \
             mock.patch.object(self.H.Paper, "handle_signal") as hs:
            self.H.dagit("e1", "w", "tok", "buy", 1.0, 1e6, 0)
        self.assertEqual(cf.call_count, 1)
        self.assertEqual(hs.call_count, 2)

    def test_uye_gecikmesi_5_saniye(self):
        self.assertEqual(self.H.GECIKME_SN, 5.0)

    def test_kapatma_onay_gerektirir(self):
        self.H.bot_ac(1, baslangic=100)
        with self.assertRaises(self.H.HesapHatasi): self.H.bot_kapat(1, onay=False)
        self.assertTrue(self.H.durum(1)["bot"])

    def test_bot_kapatilinca_acik_pozisyon_kapanir(self):
        self.H.bot_ac(1, baslangic=100)
        p = self.H._hesap(1)
        p.db.execute("INSERT INTO positions(token, qty, cost, last_price, wallet) VALUES('tok', 10, 5.0, 0.5, NULL)")
        p.db.commit()
        p._set("cash", 95.0)
        r = self.H.bot_kapat(1, onay=True, fiyat=lambda t: 0.6)
        self.assertEqual(r["kapatilan"], 1)
        self.assertFalse(self.H.durum(1)["bot"])
        self.assertEqual(p.db.execute("SELECT COUNT(*) FROM positions").fetchone()[0], 0)
        from nexora.core import CFG
        self.assertAlmostEqual(p.cash(), 95.0 + 6.0 - CFG["net_fee_usd"], places=6)

    def test_uyeler_birbirinden_ayri(self):
        self.H.bot_ac(1, baslangic=100)
        self.H.bot_ac(2, baslangic=300)
        self.assertEqual(self.H.portfoy(1)["baslangic"], 100)
        self.assertEqual(self.H.portfoy(2)["baslangic"], 300)

if __name__ == "__main__":
    unittest.main()
