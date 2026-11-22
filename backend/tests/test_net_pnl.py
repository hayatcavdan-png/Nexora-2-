import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import net_pnl as N

W, T = "W1", "TOK"


def al(ts, qty, price, fee=0.0):
    return dict(ts=ts, wallet=W, token=T, side="buy", qty=qty, price=price, fee=fee, pnl=None)


def sat(ts, qty, price, fee=0.0, pnl=None):
    return dict(ts=ts, wallet=W, token=T, side="sell", qty=qty, price=price, fee=fee, pnl=pnl)


class EslestirTests(unittest.TestCase):
    def test_basit_bacak_ve_net(self):
        kap, acik, sm = N.eslestir([al(1, 10, 1.0, fee=0.1), sat(2, 10, 1.2, fee=0.1, pnl=1.8)])
        self.assertEqual(len(kap), 1); self.assertEqual(acik, [])
        self.assertAlmostEqual(kap[0]["brut_usd"], 2.0)
        self.assertAlmostEqual(kap[0]["ucret_usd"], 0.2)
        self.assertAlmostEqual(kap[0]["net_usd"], 1.8)
        self.assertAlmostEqual(N.mutabakat(sm)["toplam_fark"], 0.0)

    def test_fifo_kismi_satis_ucret_oransali(self):
        kap, acik, _ = N.eslestir([al(1, 10, 1.0, fee=1.0), al(2, 10, 2.0, fee=1.0), sat(3, 15, 3.0, fee=0.0)])
        self.assertEqual(len(kap), 2)
        self.assertAlmostEqual(kap[0]["qty"], 10); self.assertAlmostEqual(kap[1]["qty"], 5)
        self.assertAlmostEqual(kap[0]["ucret_usd"], 1.0)                 # ilk alımın tamamı
        self.assertAlmostEqual(kap[1]["ucret_usd"], 0.5)                 # ikinci alımın yarısı
        self.assertEqual(len(acik), 1); self.assertAlmostEqual(acik[0]["qty"], 5)
        self.assertAlmostEqual(acik[0]["ucret_usd"], 0.5)                # kalan ücret kalan miktarla orantılı

    def test_satis_iki_bacaga_bolunur_mutabakat_olay_bazinda(self):
        kap, _, sm = N.eslestir([al(1, 5, 1.0), al(2, 5, 1.0), sat(3, 10, 2.0, pnl=10.0)])
        self.assertEqual(len(kap), 2)
        self.assertEqual(len(sm), 1)
        self.assertAlmostEqual(sm[0]["net_usd"], 10.0)
        self.assertEqual(N.mutabakat(sm)["toleransi_asan"], 0)

    def test_mutabakat_fark_yakalar(self):
        _, _, sm = N.eslestir([al(1, 10, 1.0), sat(2, 10, 1.2, pnl=5.0)])
        m = N.mutabakat(sm)
        self.assertEqual(m["toleransi_asan"], 1)
        self.assertAlmostEqual(m["toplam_fark"], 3.0, places=3)

    def test_ayni_satis_iki_kez_sayilmaz(self):
        kap, _, _ = N.eslestir([al(1, 10, 1.0), sat(2, 10, 1.2), sat(3, 10, 1.2)])
        self.assertEqual(len(kap), 1)


class OzetTests(unittest.TestCase):
    def test_ozet_ve_maks_dusus(self):
        b = [dict(brut_usd=1, ucret_usd=0.1, net_usd=0.9, satim_ts=1),
             dict(brut_usd=-3, ucret_usd=0.1, net_usd=-3.1, satim_ts=2),
             dict(brut_usd=1, ucret_usd=0.1, net_usd=0.9, satim_ts=3)]
        o = N.ozet(b)
        self.assertEqual(o["bacak"], 3)
        self.assertAlmostEqual(o["net"], -1.3, places=3)
        self.assertAlmostEqual(o["maks_dusus"], -3.1, places=3)           # kümülatif 0.9 -> -2.2: zirveden düşüş -3.1
        self.assertEqual(o["kazanma"], 66.7)

    def test_bos(self):
        self.assertEqual(N.ozet([])["bacak"], 0)


class AcikTests(unittest.TestCase):
    def test_acik_fiyatsiz_belirsiz_sayilir(self):
        acik = [dict(token="A", qty=10, alim_fiyat=1.0, ucret_usd=0.0), dict(token="B", qty=5, alim_fiyat=1.0, ucret_usd=0.0)]
        r = N.acik_deger(acik, {"A": 1.5})
        self.assertAlmostEqual(r["gerceklesmemis"], 5.0)
        self.assertEqual(r["belirsiz"], 1)


class AnahtarModuTests(unittest.TestCase):
    """Paper motoru pozisyonları token bazında tutar; cüzdan bazlı FIFO ile farkı bu test gösterir."""
    def test_token_modu_cuzdanlari_birlestirir(self):
        t = [dict(ts=1, wallet="A", token="T", side="buy", qty=10, price=1.0, fee=0.0, pnl=None),
             dict(ts=2, wallet="B", token="T", side="buy", qty=10, price=2.0, fee=0.0, pnl=None),
             dict(ts=3, wallet="B", token="T", side="sell", qty=10, price=3.0, fee=0.0, pnl=None)]
        kap_c, _, _ = N.eslestir(t, anahtar_modu="cuzdan")
        kap_t, acik_t, _ = N.eslestir(t, anahtar_modu="token")
        # cüzdan modu: B kendi 2.0 alımını satar -> brüt 10. Token modu: B, A'nın 1.0 alımını satar -> brüt 20.
        self.assertAlmostEqual(sum(b["brut_usd"] for b in kap_c), 10.0)
        self.assertAlmostEqual(sum(b["brut_usd"] for b in kap_t), 20.0)
        self.assertEqual(len(acik_t), 1)


if __name__ == "__main__":
    unittest.main()
