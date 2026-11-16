import json, os, sqlite3, sys, tempfile, threading, unittest, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nexora import kesif_api as K
from nexora.core import Paper
from nexora.decision import Decider
from test_decision import FakeQuoter, Safe, TOK

M1 = "So11111111111111111111111111111111111111112"
M2 = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def tracker_db(path, rows):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, wallet TEXT, sig TEXT, side TEXT,
        token TEXT, token_delta TEXT, quote TEXT, block_time INTEGER, latency_s REAL, decision TEXT, reason TEXT)""")
    for ts, w, side, tok, dec in rows:
        c.execute("INSERT INTO tracker_signals(ts,wallet,side,token,decision) VALUES(?,?,?,?,?)", (ts, w, side, tok, dec))
    c.commit(); c.close()


class RadarTests(unittest.TestCase):
    def setUp(self): K._radar.update(ts=0, veri=None)

    def test_radar(self):
        p = os.path.join(tempfile.mkdtemp(), "t.db")
        tracker_db(p, [(99_000, "A", "BUY", M1, "KOPYALANDI"), (99_500, "B", "BUY", M1, "REDDEDİLDİ"), (99_600, "A", "BUY", M2, "REDDEDİLDİ"),
                       (99_700, "A", "SELL", M2, "x"), (100, "A", "BUY", "ESKI", "x")])
        istek = []
        def bilgi(ms):
            istek.append(ms)
            return {M1: {"id": M1, "symbol": "SOL", "name": "Solana", "usdPrice": 150.0, "liquidity": 1e9, "organicScore": 98,
                         "stats24h": {"priceChange": 6.37, "buyVolume": 1e6, "sellVolume": 1.1e6}}}
        r = K.radar(p, bilgi, now=100_000)
        self.assertEqual([t["sembol"] for t in r["tokenler"]], [M2[:4], "SOL"])          # en son alınan önce; eski elendi
        sol = r["tokenler"][1]
        self.assertEqual((sol["cuzdan"], sol["alim"], sol["kopyalandi"], sol["degisim_24s"], sol["hacim_24s"]), (2, 2, True, 6.37, 2.1e6))
        self.assertIn("2 farklı token", r["ozet"])
        K.radar(p, bilgi, now=100_050); self.assertEqual(len(istek), 1)                    # önbellek
        K.radar(p, lambda ms: (_ for _ in ()).throw(RuntimeError("x")), now=300_000)      # bilgi hatası radarı bozmaz

    def test_empty(self):
        self.assertIn("alım sinyali yok", K.radar(None, lambda m: {}, now=1)["ozet"])


class DnaTests(unittest.TestCase):
    def m(self, **kw):
        d = dict(kazanma_orani=0.7, kar_faktoru=2.5, ort_getiri=0.2, kapanan=20, dusus_kazanc_orani=0.2, gerceklesen_usd=50,
                 swap=80, pencere_gun=10)
        d.update(kw); return d

    def test_score_and_profile(self):
        self.assertEqual(K.nexora_puani(self.m(), "kopyalanabilir"), 21 + 25 + 14 + 10 + 8)
        self.assertIsNone(K.nexora_puani(self.m(), "yetersiz veri"))
        self.assertLess(K.nexora_puani(self.m(), "bot şüphesi"), K.nexora_puani(self.m(), "kopyalanabilir"))
        o = K.dna_ozeti(self.m(dusus_kazanc_orani=0.8), "zayıf", "kâr faktörü")
        self.assertEqual(o["risk"], "Yüksek"); self.assertEqual(len(o["kontrol"]), 4)

    def test_service_cache_limit_validation(self):
        t = [100_000.0]; n = [0]
        def analiz(a): n[0] += 1; return self.m(), "kopyalanabilir", "tüm eşikler geçti"
        s = K.DnaServisi(os.path.join(tempfile.mkdtemp(), "d.db"), analiz, now=lambda: t[0])
        with self.assertRaises(ValueError): s.getir("kötü adres!")
        a = s.getir(M1); self.assertFalse(a["onbellek"]); self.assertEqual(a["puan"], 78)
        self.assertTrue(s.getir(M1)["onbellek"]); self.assertEqual(n[0], 1)
        old = K.DNA_GUNLUK; K.DNA_GUNLUK = 1
        try:
            with self.assertRaises(PermissionError): s.getir(M2)
        finally: K.DNA_GUNLUK = old


class ManuelTests(unittest.TestCase):
    def test_manual_trade_uses_same_rules(self):
        p = Paper(); d = Decider(p, FakeQuoter(), Safe())
        with self.assertRaises(ValueError): K.manuel_islem(d, "x", "buy", 1)
        tok = "MEME" + "1" * 30
        r = K.manuel_islem(d, tok, "buy", 2.0)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertEqual(p.position(tok)["cost"], 2.0)
        self.assertEqual(p.position(tok)["wallet"], "MANUEL")
        r2 = K.manuel_islem(d, "MEMF" + "1" * 30, "buy", 50.0)                         # sınırı aşamaz: en çok %5
        self.assertAlmostEqual(p.position("MEMF" + "1" * 30)["cost"], round(p.equity() * 0.05 + 2.0 * 0.05 * 0, 2), delta=0.2)
        self.assertEqual(K.manuel_islem(d, "MEMG" + "1" * 30, "buy", 0.1)["decision"], "REDDEDİLDİ")
        p.set_kill(True)
        self.assertEqual(K.manuel_islem(d, "MEMH" + "1" * 30, "buy", 2.0)["reason"], "acil durdurma aktif")
        p.set_kill(False)
        self.assertEqual(K.manuel_islem(d, tok, "sell")["decision"], "KOPYALANDI"); self.assertIsNone(p.position(tok))


class ServerTests(unittest.TestCase):
    def test_endpoints_registered(self):
        d = tempfile.mkdtemp()
        os.environ["NEXORA_API_KEY"] = "k"; os.environ["NEXORA_DB"] = os.path.join(d, "s.db"); os.environ["TRACKER_DB"] = os.path.join(d, "t.db")
        sys.modules.pop("server", None)
        import server
        from http.server import ThreadingHTTPServer
        server._servis["bilgi"] = object()
        K._radar.update(ts=0, veri=None)
        tracker_db(os.environ["TRACKER_DB"], [])
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={"X-API-Key": "k"},
                                         method="GET" if body is None else "POST")
            try:
                with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
        c, r = call("/radar"); self.assertEqual((c, r["tokenler"]), (200, []))
        server._servis["dna"] = K.DnaServisi(os.path.join(d, "d.db"), lambda a: (DnaTests().m(), "kopyalanabilir", "ok"))
        c, r = call("/cuzdan-dna", {"adres": M1}); self.assertEqual((c, r["puan"]), (200, 78))
        self.assertEqual(call("/cuzdan-dna", {"adres": "x"})[0], 400)
        server._servis["decider"] = Decider(server.paper, FakeQuoter(), Safe())
        c, r = call("/manuel", {"token": "MEME" + "1" * 30, "yon": "buy", "usd": 1.5}); self.assertEqual((c, r["decision"]), (200, "KOPYALANDI"))
        self.assertEqual(call("/manuel", {"token": "x", "yon": "buy"})[0], 400)
        srv.shutdown(); srv.server_close()


if __name__ == "__main__":
    unittest.main()
