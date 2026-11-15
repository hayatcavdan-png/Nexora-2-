import json, os, sqlite3, sys, tempfile, time, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from nexora.core import Paper, CFG
from nexora.decision import Decider
from nexora.rapor import build_report, as_text, reason_group, start_of_local_day
from test_decision import FakeQuoter, Safe, TOK

class RaporTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.path = os.path.join(self.d, "p.db")
        self.p, self.q = Paper(self.path), FakeQuoter()
        self.dec = Decider(self.p, self.q, Safe())
    def scenario(self):
        dec, q = self.dec, self.q
        dec.decide("a1", "W1", "T1", "buy", 1)                       # kopyalandı
        q.sell_price = 1.4; dec.decide("a2", "W1", "T1", "sell", 1)  # kâr ile kapandı
        q.sell_price = None
        dec.decide("a3", "W2", "T2", "buy", 60)                      # bayat
        q.back_ratio = 0.91; dec.decide("a4", "W2", "T3", "buy", 1)  # al-sat kaybı %9 -> gölge
        q.back_ratio = 0.88; dec.decide("a5", "W2", "T4", "buy", 1)  # al-sat kaybı %12 -> gölge
        q.back_ratio = 0.97
    def test_reason_grouping(self):
        self.assertEqual(reason_group("al-sat kaybı yüksek (%8.1)"), "al-sat kaybı yüksek")
        self.assertEqual(reason_group("fiyat etkisi yüksek (%5.00)"), "fiyat etkisi yüksek")
        self.assertEqual(reason_group("token REDDEDİLDİ: yeni basım yetkisi açık"), "token REDDEDİLDİ: yeni basım yetkisi açık")
    def test_full_report(self):
        self.scenario()
        r = build_report(self.path, None)
        b = r["bugun"]
        self.assertEqual((b["karar"], b["kopyalanan_alim"], b["kapanan"], b["reddedilen"]), (5, 1, 1, 3))
        self.assertAlmostEqual(b["gerceklesen_kz"], 7.0 - 0.01 - 5.0, places=2)
        self.assertEqual(dict((x["gerekce"], x["adet"]) for x in b["red_gerekceleri"]),
                         {"al-sat kaybı yüksek": 2, "sinyal bayat": 1})
        self.assertEqual(r["golge"]["toplam"], 2)
        self.assertEqual([g["grup"] for g in r["golge"]["gruplar"]], ["al-sat %8-10", "al-sat %10-15"])
        w = {x["wallet"]: x for x in r["cuzdanlar"]}
        self.assertEqual((w["W1"]["kopyalanan"], w["W1"]["kapanan"]), (1, 1)); self.assertGreater(w["W1"]["gerceklesen_kz"], 0)
        self.assertEqual((w["W2"]["sinyal"], w["W2"]["kopyalanan"]), (3, 0))
        self.assertAlmostEqual(r["portfoy"]["kz"], self.p.portfolio()["pnl"], places=2)
        txt = as_text(r)
        self.assertIn("2 × al-sat kaybı yüksek", txt); self.assertIn("W1…W1", txt); self.assertNotIn("\\n", txt)
    def test_day_boundary(self):
        self.scenario()
        yesterday = start_of_local_day() - 3600
        self.p.db.execute("UPDATE trades SET ts=? WHERE event_id IN ('a1','a2')", (yesterday,)); self.p.db.commit()
        r = build_report(self.path, None)
        self.assertEqual((r["bugun"]["karar"], r["bugun"]["kapanan"]), (3, 0))           # dün bugünü etkilemez
        self.assertEqual({x["wallet"]: x for x in r["cuzdanlar"]}["W1"]["kapanan"], 1)  # cüzdan özeti tüm zamanlar
    def test_missing_and_old_databases(self):
        self.assertFalse(build_report(os.path.join(self.d, "yok.db"), None)["hazir"])
        old = os.path.join(self.d, "old.db"); c = sqlite3.connect(old)
        c.execute("CREATE TABLE trades(id INTEGER PRIMARY KEY, ts REAL, event_id TEXT, wallet TEXT, token TEXT, side TEXT, qty REAL, price REAL, fee REAL, pnl REAL, decision TEXT, reason TEXT)")
        c.execute("CREATE TABLE state(k TEXT PRIMARY KEY, v TEXT)"); c.execute("INSERT INTO state VALUES('cash','100')"); c.commit(); c.close()
        r = build_report(old, None)
        self.assertTrue(r["hazir"]); self.assertEqual((r["golge"]["toplam"], r["portfoy"]["acik_pozisyon"]), (0, 0))
    def test_server_endpoint(self):
        self.scenario()
        import importlib, threading, urllib.request
        from http.server import ThreadingHTTPServer
        cwd = os.getcwd(); os.chdir(self.d)
        os.environ.update(NEXORA_API_KEY="k", NEXORA_DB=self.path, TRACKER_DB=os.path.join(self.d, "t.db"))
        try:
            import server; server = importlib.reload(server)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/rapor", headers={"X-API-Key": "k"})
            with urllib.request.urlopen(req, timeout=5) as resp: data = json.loads(resp.read())
            srv.shutdown(); srv.server_close()
        finally:
            os.chdir(cwd)
            for k in ("NEXORA_API_KEY", "NEXORA_DB", "TRACKER_DB"): os.environ.pop(k, None)
        self.assertEqual(data["bugun"]["kopyalanan_alim"], 1); self.assertEqual(data["golge"]["toplam"], 2)
if __name__ == "__main__": unittest.main()
