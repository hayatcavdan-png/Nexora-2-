import os, tempfile, unittest
from nexora.wallet_analysis import saglamlik, verdict, score, THRESHOLDS
from nexora import analiz_gecmis as G


def c(pnl, cost=10.0, ts=0, hold=300):
    return dict(pnl=pnl, cost=cost, ts=ts, holds=[hold], token="T")


def m(**kw):
    taban = dict(swap=50, kapanan=20, satis=20, eslesmeyen_satis=0, medyan_tutma_sn=300, gerceklesen_usd=40, kazanma_orani=0.6,
                 kar_faktoru=2.0, ort_getiri=0.2, en_buyuk_token_payi=0.3, sifir_tur_orani=0, tek_token_tur=1)
    taban.update(kw); return taban


class Test(unittest.TestCase):
    def test_istikrarli_cuzdan(self):
        s = saglamlik([c(2 if i % 3 else -1, ts=i) for i in range(30)])
        self.assertGreater(s["medyan_getiri"], 0); self.assertGreater(s["getiri_guven_alt"], 0); self.assertGreater(s["en_iyi_haric_usd"], 0)
        self.assertEqual(s["max_kayip_serisi"], 1); self.assertGreaterEqual(s["kalite_puani"], 90)

    def test_tek_islem_sansi(self):
        s = saglamlik([c(-1, ts=i) for i in range(11)] + [c(50, ts=11)])       # toplam +39 ama 11 kayıp, 1 büyük kazanç
        self.assertLess(s["en_iyi_haric_usd"], 0); self.assertLess(s["medyan_getiri"], 0); self.assertEqual(s["max_kayip_serisi"], 11)
        self.assertLess(s["kalite_puani"], 30)
        k, why = verdict(m(kapanan=12, **s))
        self.assertEqual(k, "zayıf"); self.assertTrue(any("tek işlem şansı" in w for w in why))
        self.assertTrue(any("üst üste 11 kayıp" in w for w in why))

    def test_form_dusmus_ve_hizli(self):
        s = saglamlik([c(3, ts=i) for i in range(10)] + [c(-1, ts=10 + i, hold=20) for i in range(10)])
        self.assertGreater(s["ilk_yari_getiri"], 0); self.assertLess(s["son_yari_getiri"], 0); self.assertEqual(s["hizli_satis_orani"], 0.5)
        k, why = verdict(m(**s)); self.assertEqual(k, "zayıf"); self.assertTrue(any("form düşmüş" in w for w in why))
        s2 = saglamlik([c(1, ts=i, hold=10 if i % 3 else 300) for i in range(12)])
        self.assertTrue(any("kısa tutulmuş" in w for w in verdict(m(**s2))[1]))

    def test_kucuk_ornekte_saglamlik_uygulanmaz_ve_eski_kayit_bozulmaz(self):
        s = saglamlik([c(-1, ts=i) for i in range(4)] + [c(30, ts=5)])
        self.assertEqual(verdict(m(kapanan=5, **s))[0], "kopyalanabilir")        # 8'den az: yalnızca eski eşikler
        self.assertEqual(verdict(m())[0], "kopyalanabilir")                      # yeni alanları olmayan eski kayıt
        self.assertGreater(score(m(kalite_puani=90)), score(m(kalite_puani=20)))
        self.assertEqual(saglamlik([])["kalite_puani"], 0); self.assertGreaterEqual(THRESHOLDS["min_robust_n"], THRESHOLDS["min_closed"])

    def test_gecmis_ve_egilim(self):
        db = os.path.join(tempfile.mkdtemp(), "g.db"); W = "W" * 40
        self.assertEqual(G.gecmis(db, W), []); self.assertIsNone(G.egilim(db, W))
        G.kaydet(db, [dict(wallet=W, karar="kopyalanabilir", kalite_puani=80, gerceklesen_usd=10)], now=86400.0)
        self.assertIsNone(G.egilim(db, W))
        G.kaydet(db, [dict(wallet=W, karar="kopyalanabilir", kalite_puani=55, gerceklesen_usd=4)], now=2 * 86400.0)
        e = G.egilim(db, W); self.assertEqual((e["durum"], e["kz_fark"], e["gun"]), ("bozuldu", -6.0, 1.0))
        G.kaydet(db, [dict(wallet=W, karar="zayıf", gerekce="x", kalite_puani=50)], now=3 * 86400.0)
        self.assertEqual(G.egilim(db, W)["durum"], "bozuldu")
        G.kaydet(db, [dict(wallet=W, karar="kopyalanabilir", kalite_puani=60)], now=4 * 86400.0)
        self.assertEqual(G.egilim(db, W)["durum"], "iyilesti")
        o = G.ozet(db, [W, "Y" * 40])
        self.assertEqual((o[0]["goruntu"], o[0]["kopyalanabilir_orani"], o[1]["goruntu"]), (4, 0.75, 0))
        for i in range(G.SAKLA_ADET + 5): G.kaydet(db, [dict(wallet=W, karar="zayıf")], now=10 * 86400.0 + i)
        self.assertEqual(len(G.gecmis(db, W, 1000)), G.SAKLA_ADET)


if __name__ == "__main__":
    unittest.main()
