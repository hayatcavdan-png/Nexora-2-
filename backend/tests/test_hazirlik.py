import os, tempfile, time, unittest
from nexora.core import Paper
from nexora.hazirlik import hazirlik, islem_istatistigi


def _paper(pnller, gun_once=20):
    d = tempfile.mkdtemp(); yol = os.path.join(d, "p.db"); p = Paper(yol); now = time.time()
    for i, pnl in enumerate(pnller):
        ts = now - gun_once * 86400 + i * 3600
        for side, pn in (("buy", 0.0), ("sell", pnl)):
            p.db.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (ts, f"e{i}{side}", "w", "t", side, 1, 1, 0, pn, "KOPYALANDI", ""))
    p.db.commit(); return yol, now


class Test(unittest.TestCase):
    def test_istatistik(self):
        s = islem_istatistigi([1, -0.5, 2, -0.5]); self.assertEqual((s["n"], s["kazanma_pct"], s["profit_factor"]), (4, 50.0, 3.0))
        self.assertEqual(islem_istatistigi([])["n"], 0)

    def test_az_veri_bekler_ve_hazir_demez(self):
        yol, now = _paper([1.0, 2.0, 1.5])                                 # 3 işlem, hepsi kârlı: şans olabilir
        r = hazirlik(yol, {"etiketli": 40}, now)
        self.assertEqual(r["sonuc"], "bekliyor"); d = {x["kod"]: x["durum"] for x in r["olcutler"]}
        self.assertEqual((d["islem"], d["beklenen"], d["guven"]), ("bekliyor",) * 3)

    def test_zararli_seri_gecmez(self):
        yol, now = _paper([-0.3, 0.2] * 20)
        r = hazirlik(yol, {"etiketli": 600}, now)
        d = {x["kod"]: x["durum"] for x in r["olcutler"]}
        self.assertEqual((d["islem"], d["beklenen"], d["pf"]), ("gecti", "gecmedi", "gecmedi")); self.assertEqual(r["sonuc"], "gecmedi")

    def test_iyi_seri_ama_calisma_verisi_olmadan_hazir_denmez(self):
        yol, now = _paper([0.5, 0.6, 0.4, -0.1] * 10)
        r = hazirlik(yol, {"etiketli": 600}, now)
        d = {x["kod"]: x["durum"] for x in r["olcutler"]}
        self.assertEqual((d["beklenen"], d["guven"], d["pf"], d["sure"]), ("gecti",) * 4)
        self.assertEqual(d["calisma"], "bekliyor"); self.assertNotEqual(r["sonuc"], "teknik_tamam")
        self.assertTrue(any("açık onay" in m.lower() for m in r["manuel"]))

    def test_bos_veritabani(self):
        r = hazirlik(os.path.join(tempfile.mkdtemp(), "yok.db"), None, time.time())
        self.assertEqual(r["sonuc"], "bekliyor"); self.assertEqual(r["gecen"], 0)


if __name__ == "__main__":
    unittest.main()
