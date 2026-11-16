import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from test_analiz import tx, round_trip, W
from nexora.wallet_analysis import analyze, gerceklesmemis


class Test(unittest.TestCase):
    def kesecik(self):
        q = 10 ** 6
        txs = sum((round_trip(i, f"T{i}", 10, 15, 1000 + i * 5000) for i in range(6)), [])
        txs.append(tx("acik1", 90_000, "BAG", 0, 500 * q, q_pre=1000 * q, q_post=1000 * q - 40 * q))   # 40 USDC'lik açık pozisyon
        txs.append(tx("acik2", 91_000, "OLU", 0, 200 * q, q_pre=1000 * q, q_post=1000 * q - 20 * q))   # 20 USDC, teklif yok
        return analyze(txs, W, 150.0)

    def test_acik_lotlar(self):
        m = self.kesecik()
        lot = {l["token"]: l for l in m["acik_lotlar"]}
        self.assertEqual(set(lot), {"BAG", "OLU"})
        self.assertEqual(lot["BAG"]["miktar_raw"], 500 * 10 ** 6)
        self.assertAlmostEqual(lot["BAG"]["maliyet_usd"], 40.0, places=2)

    def test_degerleme(self):
        m = self.kesecik()
        g = gerceklesmemis(m["acik_lotlar"], lambda t, raw: 10.0 if t == "BAG" else None)
        self.assertEqual((g["acik_token"], g["teklifsiz_token"]), (2, 1))
        self.assertAlmostEqual(g["gerceklesmemis_usd"], 10.0 - 60.0, places=1)       # teklifsiz token değersiz sayılır
        self.assertAlmostEqual(m["gerceklesen_usd"] + g["gerceklesmemis_usd"], 30 - 50, places=0)

    def test_sinir(self):
        lotlar = [dict(token=f"T{i}", miktar_raw=1, maliyet_usd=float(i)) for i in range(1, 6)]
        cagri = []
        g = gerceklesmemis(lotlar, lambda t, r: cagri.append(t) or 0.0, en_fazla=2)
        self.assertEqual(cagri, ["T5", "T4"])                                          # en büyük maliyetliler önce
        self.assertEqual(g["degerlenmeyen_maliyet_usd"], 6.0)


    def test_analizde_karar_dusurulur(self):
        import contextlib, csv, io, tempfile
        import cuzdan_analiz as mod
        from nexora.constants import USDC_MINT, WSOL_MINT
        m_tx = []
        q = 10 ** 6
        m_tx = sum((round_trip(i, f"T{i}", 10, 15, 1000 + i * 5000) for i in range(6)), [])
        m_tx.append(tx("acik", 90_000, "BAG", 0, 500 * q, q_pre=1000 * q, q_post=1000 * q - 80 * q))
        class C:
            def call(self, m, p):
                if m == "getMultipleAccounts": return {"value": [dict(owner="11111111111111111111111111111111") for _ in p[0]]}
                return {"data": m_tx}
        class Q:
            def quote(self, i, o, a):
                if i == WSOL_MINT: return dict(in_amount=a, out_amount=150 * q, price_impact_pct=0)
                return dict(in_amount=a, out_amount=1 * q, price_impact_pct=0)          # açık pozisyon artık 1 USDC
        d = tempfile.mkdtemp(); eski = os.getcwd(); os.chdir(d)
        orig, egri = mod.analyze, mod.hesap_turu.egri_ustunde
        mod.analyze = lambda txs, w, p: dict(orig(txs, W, p), wallet=w); mod.hesap_turu.egri_ustunde = lambda a: True
        try:
            open("l.txt", "w").write("A" * 32 + "\n")
            with contextlib.redirect_stdout(io.StringIO()):
                rows = mod.main(client=C(), quoter=Q(), sleep=lambda s: None, list_path="l.txt")
            r = rows[0]
            self.assertEqual(r["karar"], "zayıf")                                        # gerçekleşen +30, açık -79
            self.assertAlmostEqual(r["toplam_usd"], 30 - 79, places=0)
            self.assertIn("gerceklesmemis_usd", next(csv.DictReader(open("cuzdan_analiz.csv"))))
        finally:
            mod.analyze, mod.hesap_turu.egri_ustunde = orig, egri; os.chdir(eski)


if __name__ == "__main__":
    unittest.main()
