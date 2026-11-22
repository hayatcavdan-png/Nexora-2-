import os, random, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import filtre_deney as F


def olaylar(n, seed=1, avantajli=False):
    r = random.Random(seed)
    out = []
    for i in range(n):
        ts = 1_000_000 + i * 60
        likidite = r.uniform(1e3, 1e6)
        net = r.gauss(0, 5)
        if avantajli and likidite > 5e5: net += 6          # yapay sinyal: yüksek likidite daha iyi
        out.append(dict(sinyal_ts=ts - 2, ulasma_ts=ts, likidite_usd=likidite, net=net))
    return out


class SizintiTests(unittest.TestCase):
    def test_karar_anindan_sonraki_zaman_reddedilir(self):
        o = dict(sinyal_ts=100, ulasma_ts=200)
        with self.assertRaises(F.SizintiHatasi):
            F.ozellik(o, karar_ts=150)

    def test_gelecek_alan_ozelligi_degistirmez(self):
        temel = dict(sinyal_ts=100, ulasma_ts=110, likidite_usd=5000.0)
        a = F.ozellik(dict(temel), karar_ts=110)
        b = F.ozellik(dict(temel, gelecek_fiyat=9999.0), karar_ts=110)
        self.assertEqual(a, b)


class WalkForwardTests(unittest.TestCase):
    def test_test_dilimi_egitimde_yok_ve_zamana_gore(self):
        s = olaylar(200)
        for egit, test in F.walk_forward(s, fold=4):
            self.assertTrue(max(o["ulasma_ts"] for o in egit) < min(o["ulasma_ts"] for o in test))
            ids_e = {id(o) for o in egit}
            self.assertFalse(any(id(o) in ids_e for o in test))

    def test_kisa_veri_bos(self):
        self.assertEqual(F.walk_forward(olaylar(5), fold=4), [])


class KararTests(unittest.TestCase):
    def test_yetersiz_ornek_kanitlanmadi(self):
        r = F.degerlendir(olaylar(10))
        self.assertEqual(r["durum"], "yetersiz")
        self.assertIn("KANITLANMADI", r["karar"])

    def test_gurultu_kanitlanmadi(self):
        r = F.degerlendir(olaylar(400, seed=3))
        self.assertNotIn("AVANTAJ GÖRÜLDÜ", r["karar"])
        self.assertTrue(r["karar"].startswith("MODEL AVANTAJI KANITLANMADI"))

    def test_gercek_avantaj_gorulur_ama_yetki_vermez(self):
        r = F.degerlendir(olaylar(600, seed=5, avantajli=True))
        self.assertTrue(r["karar"].startswith("AVANTAJ GÖRÜLDÜ"))
        self.assertIn("işlem yetkisi yok", r["karar"])

    def test_varsayilan_mod_kapali(self):
        self.assertEqual(F.FILTRE_MOD, os.getenv("FILTRE_MOD", "kapali"))

    def test_deterministik(self):
        a = F.degerlendir(olaylar(300, seed=9))
        b = F.degerlendir(olaylar(300, seed=9))
        self.assertEqual(a["fark_ci"], b["fark_ci"])


if __name__ == "__main__":
    unittest.main()
