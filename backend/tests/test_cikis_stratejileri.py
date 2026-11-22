import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import cikis_stratejileri as C

G0 = 1_000_000.0
P0 = 1.0


class CikisTests(unittest.TestCase):
    def test_kaynak_satisi_ve_net_getiri(self):
        yol = [(G0 + 10, 1.05), (G0 + 60, 1.10)]
        r = C.simule(G0, P0, yol, kaynak_satis_ts=G0 + 50, giris_maliyet_pct=2.0)
        self.assertEqual(r["kaynak"]["durum"], "kapandi")
        self.assertEqual(r["kaynak"]["cikis_fiyat"], 1.10)
        self.assertAlmostEqual(r["kaynak"]["getiri_net"], 10.0 - 2.0 - C.CIKIS_MALIYET_PCT, places=3)

    def test_kaynak_satmadiysa_acik(self):
        r = C.simule(G0, P0, [(G0 + 10, 1.0)], kaynak_satis_ts=None)
        self.assertEqual(r["kaynak"]["durum"], "acik")

    def test_gelecek_fiyat_erken_kararini_degistirmez(self):
        """Erken çıkış ilk eşik ihlalinde yapılır; sonradan gelen fiyatlar eski kararı değiştirmemeli."""
        temel = [(G0 + 5, 0.70)]                       # %30 düşüş: erken eşik (%25) ihlali
        a = C.simule(G0, P0, temel + [(G0 + 100, 0.5)])
        b = C.simule(G0, P0, temel + [(G0 + 100, 3.0)])
        self.assertEqual(a["erken"]["cikis_fiyat"], 0.70)
        self.assertEqual(b["erken"]["cikis_fiyat"], 0.70)
        self.assertGreater(a["erken"]["kayma_pct"], -1000)     # kayma hesaplandı

    def test_kademe_agirlikli(self):
        yol = [(G0 + 1, 1.25), (G0 + 2, 1.60)]           # %25 (1. kademe) ve %60 (2. kademe)
        r = C.simule(G0, P0, yol)
        self.assertEqual(r["kademe"]["durum"], "kapandi")
        self.assertAlmostEqual(r["kademe"]["brut_pct"], 0.5 * 25 + 0.5 * 60, places=3)

    def test_iz_durdurma_zirveden_dusus(self):
        yol = [(G0 + 1, 1.5), (G0 + 2, 1.2)]            # zirve 1.5, %15 eşik = 1.275; 1.2 altına indi
        r = C.simule(G0, P0, yol)
        self.assertEqual(r["iz"]["durum"], "kapandi")
        self.assertEqual(r["iz"]["cikis_fiyat"], 1.2)

    def test_gozlem_yoksa_satilamadi_kârlı_sayilmaz(self):
        r = C.simule(G0, P0, [])
        for y in ("sure", "kademe", "iz", "erken"):
            self.assertEqual(r[y]["durum"], "satilamadi")
            self.assertIsNone(r[y]["getiri_net"])

    def test_ozet_acik_ve_satilamayan_kara_karismaz(self):
        yol = [(G0 + 1, 1.5), (G0 + 2, 1.2)]
        o = C.ozetle([C.simule(G0, P0, yol), C.simule(G0, P0, [])])
        self.assertEqual(o["iz"]["pozisyon"], 2)
        self.assertEqual(o["iz"]["kapandi"], 1)
        self.assertEqual(o["iz"]["satilamadi"], 1)
        self.assertEqual(o["kaynak"]["acik"], 2)


if __name__ == "__main__":
    unittest.main()
