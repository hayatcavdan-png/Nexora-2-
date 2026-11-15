import csv, json, os, sys, tempfile, threading, unittest, urllib.request, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from http.server import ThreadingHTTPServer
from nexora.core import Paper, CFG
from nexora.decision import Decider
from nexora import panel
from test_decision import FakeQuoter, Safe

class PanelTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        self.pp = os.path.join(self.d, "p.db"); self.tp = os.path.join(self.d, "t.db")
        p, q = Paper(self.pp), FakeQuoter(); dec = Decider(p, q, Safe())
        dec.decide("a1", "W1", "T1", "buy", 1); q.sell_price = 1.4; dec.decide("a2", "W1", "T1", "sell", 1)
        q.sell_price = None; dec.decide("a3", "W2", "T2", "buy", 1)
        self.paper = p
        with open("wallets.txt", "w") as f: f.write("W1\nW2\nBOT\n")
        with open("kara_liste.txt", "w") as f: f.write("# x\nBOT\n")
        with open("cuzdan_analiz.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "karar", "kazanma_orani", "kar_faktoru", "gerceklesen_usd", "ort_getiri", "medyan_tutma_sn", "kapanan", "skor"])
            w.writeheader()
            w.writerow(dict(wallet="W1", karar="kopyalanabilir", kazanma_orani=0.7, kar_faktoru=3, gerceklesen_usd=100, ort_getiri=0.2, medyan_tutma_sn=600, kapanan=20, skor=0.5))
            w.writerow(dict(wallet="W3", karar="kopyalanabilir", kazanma_orani=0.5, kar_faktoru=2, gerceklesen_usd=50, ort_getiri=0.1, medyan_tutma_sn=300, kapanan=10, skor=0.9))
            w.writerow(dict(wallet="W4", karar="zararda", kazanma_orani=0.2, kar_faktoru=0.5, gerceklesen_usd=-5, ort_getiri=-0.1, medyan_tutma_sn="", kapanan=6, skor=0))
        with open("cuzdan_tarama.csv", "w") as f: f.write("wallet,durum\nW1,aday\nW2,aday\nW3,aday\nW4,pasif\n")
        with open("takip_kaybi.json", "w") as f:
            json.dump(dict(cuzdanlar=[dict(cuzdan="W1", islem=2, giris_kaybi_ort=0.08, cikis_kaybi_ort=0.12, kaynak_getiri_ort=0.3, bizim_getiri_ort=-0.05)]), f)
        with open("asamalar.json", "w") as f: json.dump(dict(rows=[dict(kod="N0", yuzde=25)], meta=[dict(label="Kaynak", value="test")]), f)
    def tearDown(self): os.chdir(self.cwd)
    def test_gecmis_curve(self):
        g = panel.gecmis(self.pp)
        vals = [p["deger"] for p in g["noktalar"]]
        self.assertEqual(vals[0], 100.0)
        self.assertAlmostEqual(vals[-2], 100 - 0.01 + (7.0 - 0.01 - 5.0) - 0.01, places=3)   # 3 işlem sonrası gerçekleşen
        self.assertAlmostEqual(g["guncel"], self.paper.portfolio()["equity"], places=3)
        self.assertEqual(panel.gecmis(os.path.join(self.d, "yok.db"))["guncel"], 100.0)
    def test_cuzdanlar(self):
        d = panel.cuzdanlar(self.pp, self.tp)
        ws = [r["wallet"] for r in d["cuzdanlar"]]
        self.assertEqual(ws, ["W1", "W2", "W3"])                     # takiptekiler önce; kara liste ve zararda yok
        r = d["cuzdanlar"][0]
        self.assertEqual((r["karar"], r["kazanma_orani"], r["medyan_tutma_sn"], r["paper_kapanan"]), ("kopyalanabilir", 0.7, 600, 1))
        self.assertGreater(r["paper_kz"], 0)
        self.assertEqual((r["takip_tur"], r["takip_giris"], r["takip_cikis"]), (2, 0.08, 0.12))
        self.assertIsNone(d["cuzdanlar"][1]["takip_giris"])
        self.assertEqual((d["cuzdanlar"][1]["karar"], d["cuzdanlar"][2]["durum"]), ("analiz yok", "takip dışı"))
        o = d["ozet"]
        self.assertEqual((o["taranan"], o["analiz"], o["kopyalanabilir"], o["takipte"], o["kara_liste"]), (4, 3, 2, 2, 1))
    def test_olaylar(self):
        import time as _t
        self.paper.db.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(?,?,?,?,?,0,0,0,0,'REDDEDİLDİ','günlük zarar limiti')",
                              (_t.time(), "z1", "W1", "T9", "buy"))
        self.paper.db.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(?,?,?,?,?,0,0,0,0,'REDDEDİLDİ','günlük zarar limiti')",
                              (_t.time() + 1, "z2", "W1", "T8", "buy"))
        self.paper.db.commit()
        from nexora.live_tracker import LiveTracker
        tr = LiveTracker(None, self.paper, self.tp, ["W9"], clock=lambda: 5e9)
        tr.db.execute("UPDATE tracker_wallets SET quarantined=2, last_error='yüksek frekans', updated=?", (_t.time() + 2,)); tr.db.commit()
        e = panel.olaylar(self.pp, self.tp)["olaylar"]
        self.assertEqual([x["tur"] for x in e], ["alim", "kapanis", "alim", "risk", "bot"])    # zarar sınırı günde bir kez
        self.assertIn("+1.99 USDC", e[1]["baslik"])
        son = e[2]["ts"]
        self.assertEqual([x["tur"] for x in panel.olaylar(self.pp, self.tp, son)["olaylar"]], ["risk", "bot"])
    def test_asamalar(self):
        self.assertEqual(panel.asamalar()["rows"][0]["kod"], "N0")
        os.remove("asamalar.json"); self.assertEqual(panel.asamalar()["rows"], [])
    def test_endpoints_and_key_whitespace(self):
        os.environ.update(NEXORA_API_KEY=" anahtar ", NEXORA_DB=self.pp, TRACKER_DB=self.tp)
        try:
            import server; server = importlib.reload(server)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            def get(path, key="anahtar "):
                req = urllib.request.Request(base + path, headers={"X-API-Key": key})
                with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read())
            self.assertIn("noktalar", get("/gecmis"))
            self.assertEqual(get("/cuzdanlar")["ozet"]["takipte"], 2)
            self.assertEqual(get("/asamalar")["rows"][0]["kod"], "N0")
            self.assertEqual(len(get("/olaylar?son=0")["olaylar"]), 3)
            self.assertEqual(get("/olaylar?son=9e12")["olaylar"], [])
            with self.assertRaises(urllib.error.HTTPError): get("/gecmis", key="yanlis")
            srv.shutdown(); srv.server_close()
        finally:
            for k in ("NEXORA_API_KEY", "NEXORA_DB", "TRACKER_DB"): os.environ.pop(k, None)
if __name__ == "__main__": unittest.main()


class NabizTests(unittest.TestCase):
    def test_takip_durdu_event_once(self):
        import tempfile, os
        from nexora.core import Paper
        from nexora import panel
        path = os.path.join(tempfile.mkdtemp(), "p.db")
        p = Paper(path); p.nabiz(1000.0)
        self.assertEqual(panel.olaylar(path, None, son=0, now=1200)["olaylar"], [])          # 200 sn: sorun yok
        ev = panel.olaylar(path, None, son=0, now=1400)["olaylar"]
        self.assertEqual([(e["baslik"], e["ts"]) for e in ev], [("Takip durdu", 1300.0)])
        self.assertEqual(panel.olaylar(path, None, son=1300.0, now=1500)["olaylar"], [])     # bir kez bildirilir
        p.nabiz(1450.0)
        self.assertEqual(panel.olaylar(path, None, son=1300.0, now=1500)["olaylar"], [])     # yeniden çalışıyor
        self.assertEqual(p.son_nabiz(), 1450.0)


class DususTests(unittest.TestCase):
    def test_drawdown(self):
        pts = [dict(ts=1, deger=100), dict(ts=2, deger=104), dict(ts=3, deger=98.8), dict(ts=4, deger=101), dict(ts=5, deger=99)]
        d = panel.dusus(pts, 100)
        self.assertAlmostEqual(d["max_dusus_pct"], 5.0); self.assertAlmostEqual(d["max_dusus_usd"], 5.2)
        self.assertAlmostEqual(d["zirveden_uzaklik_pct"], round(5 / 104 * 100, 2))
        self.assertEqual(panel.dusus([dict(ts=1, deger=100)], 100)["max_dusus_pct"], 0.0)
