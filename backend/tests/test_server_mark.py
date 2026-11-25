import importlib, json, os, sys, tempfile, threading, unittest, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from http.server import ThreadingHTTPServer
from nexora.core import Paper
from nexora.decision import Decider
from nexora.live_tracker import LiveTracker
from test_decision import FakeQuoter, Safe, TOK
from test_tracker import swap_tx
from unittest.mock import Mock

class MarkTests(unittest.TestCase):
    def test_mark_to_market_updates_unrealized(self):
        p, q = Paper(), FakeQuoter(); d = Decider(p, q, Safe())
        d.decide("e1", "W", TOK, "buy", 1)
        q.sell_price = 2.0                                     # token değeri iki katına çıktı
        self.assertEqual(d.mark_to_market(), (1, 0))
        pf = p.portfolio(); pos = pf["positions"][0]
        self.assertAlmostEqual(pos["qty"] * pos["last_price"], 10.0)
        self.assertAlmostEqual(pf["pnl"], 10.0 - 5.0 - 0.01)
    def test_mark_keeps_old_price_when_no_quote(self):
        from nexora.constants import USDC_MINT
        p, q = Paper(), FakeQuoter(); d = Decider(p, q, Safe()); d.decide("e1", "W", TOK, "buy", 1)
        before = p.portfolio()["positions"][0]["last_price"]
        q.fail.add((TOK, USDC_MINT))
        self.assertEqual(d.mark_to_market(), (0, 1))
        self.assertEqual(p.portfolio()["positions"][0]["last_price"], before)

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        os.environ.update(NEXORA_API_KEY="k", NEXORA_DB=os.path.join(self.d, "p.db"), TRACKER_DB=os.path.join(self.d, "t.db"))
        with open("wallets.txt", "w") as f: f.write("A\nB\nOLD\n")
        with open("kara_liste.txt", "w") as f: f.write("# bot\nB\n")
        import server; self.server = importlib.reload(server)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self.server.H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); os.chdir(self.cwd)
        for k in ("NEXORA_API_KEY", "NEXORA_DB", "TRACKER_DB"): os.environ.pop(k, None)
    def get(self, path, key="k"):
        req = urllib.request.Request(self.base + path, headers={"X-API-Key": key})
        with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read())
    def test_takip_empty_then_with_data(self):
        self.assertEqual(self.get("/takip"), dict(cuzdanlar=[], sinyaller=[], gecikme={}))
        client = Mock(); client.call = Mock(side_effect=lambda m, p: swap_tx(p[0], "A") if m == "getTransaction" else [])
        tr = LiveTracker(client, Paper(os.environ["NEXORA_DB"]), os.environ["TRACKER_DB"], ["A", "B"],
                         clock=lambda: 1002, sleep=lambda s: None)
        tr.handle_signature("A", "s1")
        d = self.get("/takip")
        self.assertEqual([w["wallet"] for w in d["cuzdanlar"]], ["A"])       # kara listedeki B gösterilmez
        self.assertEqual((d["sinyaller"][0]["side"], d["sinyaller"][0]["source"]), ("BUY", "ws"))
        self.assertEqual(d["gecikme"]["ws"]["n"], 1)
        self.assertNotIn("token_delta", d["sinyaller"][0])
    def test_btc_bos_sonra_ozet(self):
        d = self.get("/btc")
        self.assertTrue(d["bos"]); self.assertEqual(d["mod"], "PAPER")
        Paper(os.path.join(self.d, "nexora_btc.db"), ekosistem="btc", dagit=False)
        d = self.get("/btc")
        self.assertEqual((d["toplam"], d["kz"], d["yz"]["n"], d["mod"]), (100.0, 0.0, 0, "PAPER"))
    def test_takip_requires_key(self):
        with self.assertRaises(urllib.error.HTTPError) as c: self.get("/takip", key="yanlis")
        self.assertEqual(c.exception.code, 401)
if __name__ == "__main__": unittest.main()
