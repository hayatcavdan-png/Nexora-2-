import unittest
from nexora.core import Paper, KESINTI_ESIK_SN


class Test(unittest.TestCase):
    def test_kesinti_kaydi_ve_oran(self):
        p = Paper(); t0 = 1_000_000.0
        self.assertIsNone(p.kararlilik(t0))
        for i in range(0, 601, 60): p.nabiz(t0 + i)                       # 10 dk düzenli nabız
        p.nabiz(t0 + 600 + 10)                                            # güncelleme yeniden başlatması: kesinti değil
        p.nabiz(t0 + 610 + 1800)                                          # 30 dk boşluk: kesinti
        p.nabiz(t0 + 2410 + 60)
        k = p.kararlilik(t0 + 2470 + 3600)                                # 1 saat sonra bakılıyor; nabız 1 saattir yok: açık kesinti
        self.assertEqual(k["kesinti_sayisi"], 2)
        self.assertEqual(k["en_uzun_dk"], 60.0); self.assertEqual(k["kesintisiz_saat"], 0.0)
        k = p.kararlilik(t0 + 2470 + 30)
        self.assertEqual((k["kesinti_sayisi"], k["kesinti_toplam_dk"], k["en_uzun_dk"]), (1, 30.0, 30.0))
        self.assertAlmostEqual(k["calisma_pct"], (1 - 1800 / 2500) * 100, places=2)
        self.assertAlmostEqual(k["kesintisiz_saat"], round(90 / 3600, 1))
        self.assertGreater(KESINTI_ESIK_SN, 60)

    def test_rapor_ve_saglik(self):
        import os, tempfile, time
        from nexora import panel
        from nexora.rapor import build_report, as_text
        d = tempfile.mkdtemp(); yol = os.path.join(d, "p.db")
        p = Paper(yol); now = time.time()
        p.nabiz(now - 7200); p.nabiz(now - 7140); p.nabiz(now - 3600); p.nabiz(now - 5)
        s = panel.saglik(yol, os.path.join(d, "yok.db"), now=now)
        self.assertEqual(s["kararlilik"]["kesinti_sayisi"], 2)
        self.assertIn("Kesintisiz çalışma (N13)", as_text(build_report(yol, os.path.join(d, "yok.db"))))


if __name__ == "__main__":
    unittest.main()
