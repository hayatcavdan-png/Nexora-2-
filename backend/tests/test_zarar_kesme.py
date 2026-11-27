import unittest
from nexora.decision import zarar_kesme_asildi


class ZararKesmeTest(unittest.TestCase):
    def test_esik_altinda_satilmaz(self):
        # maliyet 100, teklif 61, ücret 0.01 -> zarar %39.01 (< %40); eski %12 eşiğinde satılırdı
        self.assertFalse(zarar_kesme_asildi(100.0, 61.0, 0.01))
        self.assertFalse(zarar_kesme_asildi(100.0, 87.9, 0.01))

    def test_esik_asilinca_satilir(self):
        # maliyet 100, teklif 59.9 -> net zarar %40.11
        self.assertTrue(zarar_kesme_asildi(100.0, 59.9, 0.01))

    def test_kar_satilmaz(self):
        self.assertFalse(zarar_kesme_asildi(100.0, 150.0, 0.01))

    def test_sifir_maliyet_guvenli(self):
        self.assertFalse(zarar_kesme_asildi(0.0, 0.0, 0.01))


if __name__ == "__main__":
    unittest.main()
