import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import giris_stratejileri as G

T0 = 1_000_000.0          # sinyal anı
U = T0 + 2                # NEXORA'ya ulaşma (2 sn gecikme)


class GirisTests(unittest.TestCase):
    def test_anında_girer_ve_maliyet_dusulur(self):
        yol = [(U, 1.00), (U + 61, 1.00)]
        r = G.simule(T0, U, 1.00, yol, cikis_fiyat=1.10)
        self.assertEqual(r["A"]["durum"], "girdi"); self.assertEqual(r["A"]["giris_fiyat"], 1.00)
        self.assertAlmostEqual(r["A"]["getiri_net"], 10.0 - G.MALIYET_PCT, places=3)

    def test_gelecek_fiyat_karari_degistirmez(self):
        """Bekleme sonrası (B) ve geri çekilme penceresi sonrası fiyatlar değişince geçmiş karar değişmemeli."""
        temel = [(U, 1.00), (U + 10, 1.01)]
        yol_a = temel + [(U + G.WAIT_SN, 1.02)]
        yol_b = temel + [(U + G.WAIT_SN, 1.02), (U + G.WAIT_SN + 5, 9.99)]          # sonradan uçuş
        ra, rb = G.simule(T0, U, 1.00, yol_a, 1.05), G.simule(T0, U, 1.00, yol_b, 1.05)
        self.assertEqual(ra["B"]["giris_fiyat"], rb["B"]["giris_fiyat"])
        self.assertEqual(ra["A"]["giris_fiyat"], rb["A"]["giris_fiyat"])

    def test_bekleme_asiri_yukselisi_filtreler(self):
        yol = [(U, 1.00), (U + G.WAIT_SN, 1.0 + (G.ASIRI_PCT + 1) / 100)]
        r = G.simule(T0, U, 1.00, yol, 1.20)
        self.assertEqual(r["B"]["durum"], "kaçırıldı"); self.assertIn("aşırı", r["B"]["neden"])
        self.assertEqual(r["A"]["durum"], "girdi")

    def test_geri_cekilme_dolar_ve_kacar(self):
        dolan = [(U, 1.00), (U + 30, 1.00 * (1 - (G.GERI_PCT + 0.5) / 100))]
        r = G.simule(T0, U, 1.00, dolan, 1.05)
        self.assertEqual(r["C"]["durum"], "girdi")
        self.assertAlmostEqual(r["C"]["giris_fiyat"], 1.00 * (1 - (G.GERI_PCT + 0.5) / 100))
        kacan = [(U, 1.00), (U + 30, 1.00)]
        self.assertEqual(G.simule(T0, U, 1.00, kacan, 1.05)["C"]["durum"], "kaçırıldı")

    def test_geri_cekilme_pencere_disinda_sayilmaz(self):
        gec = [(U, 1.00), (U + G.WINDOW_SN + 10, 0.5)]
        self.assertEqual(G.simule(T0, U, 1.00, gec, 1.0)["C"]["durum"], "kaçırıldı")

    def test_bayat_likidite_ve_tekrar_reddi(self):
        yol = [(U, 1.00), (U + 61, 1.00)]
        self.assertEqual(G.simule(T0, T0 + G.STALE_SN + 5, 1.0, yol, 1.1)["A"]["neden"][:5], "bayat")
        self.assertEqual(G.simule(T0, U, 1.0, yol, 1.1, likit=False)["B"]["durum"], "reddedildi")
        self.assertEqual(G.simule(T0, U, 1.0, yol, 1.1, son_giris_ts=U - 60)["A"]["durum"], "reddedildi")

    def test_fiyat_yoksa_kacirilir(self):
        r = G.simule(T0, U, 1.0, [], 1.1)
        self.assertEqual(r["A"]["durum"], "kaçırıldı")

    def test_ozet(self):
        yol = [(U, 1.00), (U + 61, 1.00)]
        s = [G.simule(T0, U, 1.0, yol, 1.10), G.simule(T0, U, 1.0, yol, 0.90)]
        o = G.ozetle(s)
        self.assertEqual(o["A"]["girdi"], 2)
        self.assertEqual(o["A"]["kazanma"], 50.0)
        self.assertEqual(o["A"]["sinyal"], 2)


if __name__ == "__main__":
    unittest.main()
