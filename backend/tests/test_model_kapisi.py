import io, json, os, sqlite3, sys, tempfile, time, unittest
from contextlib import redirect_stdout
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from nexora import model_kapisi as mk
from nexora.model import Model
from nexora.ozellik import OZELLIKLER
from nexora.core import Paper
from nexora.decision import Decider
from test_decision import FakeQuoter, Safe, TOK
import yz_filtre


def model_yaz(yol, esik=0.5, isaret=1.0):
    """al_sat_kaybi düşükse kârlı diyen basit model."""
    X = [dict(al_sat_kaybi=float(i % 10)) for i in range(60)]
    y = [(-1.0 if (i % 10) > 4 else 1.0) * isaret for i in range(60)]
    m = Model(tur=200).egit(X, y)
    m.kaydet(yol, dict(ufuk="kaynak", esik=esik))
    return m


class Test(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.my = os.path.join(self.d, "yz_model.json"); self.fy = os.path.join(self.d, "model_filtre.json")

    def test_model_dosyasi_yukle_ve_yenile(self):
        md = mk.ModelDosyasi(self.my)
        self.assertIsNone(md.yukle()); self.assertIsNone(md.olasilik({"al_sat_kaybi_pct": 1}))
        model_yaz(self.my)
        iyi = md.olasilik({"al_sat_kaybi_pct": 1.0}); kotu = md.olasilik({"al_sat_kaybi_pct": 9.0})
        self.assertGreater(iyi["olasilik"], kotu["olasilik"])
        self.assertTrue(iyi["secerdi"]); self.assertFalse(kotu["secerdi"])
        s1 = iyi["surum"]; time.sleep(0.01)
        model_yaz(self.my, esik=0.9); os.utime(self.my, (time.time() + 5, time.time() + 5))
        self.assertNotEqual(md.olasilik({"al_sat_kaybi_pct": 1.0})["surum"], s1)        # dosya değişince yenilenir
        open(self.my, "w").write("{bozuk"); os.utime(self.my, (time.time() + 9, time.time() + 9))
        self.assertIsNone(md.yukle())

    def test_kapi_kapaliyken_ve_modelsizken_filtre_yok(self):
        k = mk.ModelKapisi(mk.ModelDosyasi(self.my), ayar_yolu=self.fy)
        self.assertIsNone(k.izin("W", "T", 1, 0.1, 9.0))                               # kapalı
        mk.filtre_ac({}, self.fy, zorla=True)
        self.assertIsNone(k.izin("W", "T", 1, 0.1, 9.0))                               # açık ama model yok
        self.assertEqual(k.durum()["etkin"], False)
        model_yaz(self.my)
        self.assertFalse(k.izin("W", "T", 1, 0.1, 9.0)["secerdi"])
        mk.filtre_kapat(self.fy); self.assertIsNone(k.izin("W", "T", 1, 0.1, 9.0))

    def test_filtre_ac_kabul_sartlari(self):
        with self.assertRaises(ValueError): mk.filtre_ac(dict(yeterli=False, gun=3, etiketli=10), self.fy)
        with self.assertRaises(ValueError): mk.filtre_ac(dict(yeterli=True, secili_ort=-1, hepsi_ort=0.5), self.fy)
        with self.assertRaises(ValueError): mk.filtre_ac(dict(yeterli=True, secili_ort=2, hepsi_ort=1, kayma=0.4), self.fy)
        mk.filtre_ac(dict(yeterli=True, secili_ort=2, hepsi_ort=1, kayma=0.1), self.fy)
        self.assertTrue(json.load(open(self.fy))["acik"])

    def test_karar_motorunda_filtre(self):
        model_yaz(self.my); mk.filtre_ac({}, self.fy, zorla=True)
        kapi = mk.ModelKapisi(mk.ModelDosyasi(self.my), ayar_yolu=self.fy)
        p, q = Paper(), FakeQuoter(back_ratio=0.945)                                    # al-sat kaybı %5.5: model eler
        d = Decider(p, q, Safe(), kapi=kapi)
        r = d.decide("e1", "W", TOK, "buy", 1)
        self.assertIn("model olasılığı düşük", r["reason"]); self.assertIsNone(p.position(TOK))
        adimlar = json.loads(p.db.execute("SELECT adimlar FROM karar_izi WHERE event_id='e1'").fetchone()[0])
        self.assertEqual([a for a in adimlar if a["adim"] == "model"][0]["sonuc"], "eledi")
        self.assertEqual(len(p.open_shadows("W", TOK)), 1)                            # elenen gölgede ölçülür
        p2, q2 = Paper(), FakeQuoter(back_ratio=0.99)
        self.assertEqual(Decider(p2, q2, Safe(), kapi=kapi).decide("e2", "W", TOK, "buy", 1)["decision"], "KOPYALANDI")
        mk.filtre_kapat(self.fy)                                                       # geri alma
        p3, q3 = Paper(), FakeQuoter(back_ratio=0.945)
        r3 = Decider(p3, q3, Safe(), kapi=kapi).decide("e3", "W", TOK, "buy", 1)
        self.assertNotIn("model", r3.get("reason") or "")

    def test_golge_kayit_ve_rapor(self):
        db = os.path.join(self.d, "e.db"); c = sqlite3.connect(db)
        c.execute("CREATE TABLE etiket_sonuc(event_id TEXT, ufuk TEXT, ts REAL, cikis_usdc REAL, getiri_pct REAL, sapma_sn REAL, hata TEXT)")
        t0 = 1_000_000.0
        for i in range(30):
            secti = i % 2 == 0
            mk.golge_yaz(c, f"e{i}", t0 + i * 86400 * 0.6, dict(surum="s1", olasilik=0.7 if secti else 0.3, esik=0.5, secerdi=secti))
            c.execute("INSERT INTO etiket_sonuc VALUES(?,?,?,?,?,?,NULL)", (f"e{i}", "kaynak", 0, 0, 10.0 if secti else -5.0, 0))
        c.commit(); c.close()
        g = mk.golge_rapor(db)
        self.assertEqual((g["n"], g["etiketli"], g["secili_ort"], g["secilmeyen_ort"], g["hepsi_ort"]), (30, 30, 10.0, -5.0, 2.5))
        self.assertFalse(g["yeterli"])                                                # 100 etiket şartı
        with redirect_stdout(io.StringIO()) as out:
            yz_filtre.main(["durum"], etiket_db=db)
        self.assertIn("modelin seçtikleri %+10.00", out.getvalue())


if __name__ == "__main__":
    unittest.main()
