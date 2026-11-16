import json, os, sqlite3, sys, tempfile, threading, unittest, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unittest.mock import Mock
from nexora.core import Paper
from nexora.decision import Decider
from nexora.yurutme import YurutmeOlcer
from nexora.market import QuoteError
from nexora.constants import USDC_MINT
from nexora import panel
from nexora.rapor import build_report, as_text, yurutme_summary
from nexora.ws_listener import WSListener
from test_decision import FakeQuoter, Safe, TOK


class DenetimIziTests(unittest.TestCase):
    def setUp(self):
        self.p, self.q = Paper(), FakeQuoter()
        self.y = Mock()
        self.d = Decider(self.p, self.q, Safe(), yurutme=self.y)

    def test_buy_trail_has_every_step(self):
        self.assertEqual(self.d.decide("e1", "W", TOK, "buy", 1.5)["decision"], "KOPYALANDI")
        iz = self.p.karar_izi("e1")
        self.assertEqual((iz["karar"], iz["yas_sn"]), ("KOPYALANDI", 1.5))
        self.assertEqual([a["adim"] for a in iz["adimlar"]], ["kurallar", "token_guvenligi", "alis_teklifi", "geri_satis_teklifi"])
        self.assertEqual(iz["adimlar"][0]["limitler"]["max_positions"], 5)
        self.assertEqual(iz["adimlar"][2]["cikis"], 5_000_000 * 200)
        self.assertAlmostEqual(iz["adimlar"][3]["al_sat_kaybi_pct"], 3.0, places=3)
        self.y.enqueue.assert_called_once_with("e1", "buy", TOK, USDC_MINT, TOK, 5_000_000, 5_000_000 * 200)

    def test_rejections_and_sell_logged(self):
        Decider(self.p, self.q, Safe("REDDEDİLDİ")).decide("r1", "W", TOK, "buy", 1)
        self.assertEqual([a["adim"] for a in self.p.karar_izi("r1")["adimlar"]], ["kurallar", "token_guvenligi"])
        self.d.decide("e1", "W", TOK, "buy", 1); self.d.decide("s1", "W", TOK, "sell", 1)
        s = self.p.karar_izi("s1")
        self.assertEqual((s["karar"], [a["adim"] for a in s["adimlar"]]), ("KOPYALANDI", ["kurallar", "durum", "satis_teklifi"]))
        self.d.decide("x1", "W", "BASKA", "sell", 1)                       # sahip olunmayan -> kurallarda reddedilir
        self.assertEqual(self.p.karar_izi("x1")["adimlar"][0]["sonuc"], "sahip olunmayan pozisyon satılamaz")
        self.assertEqual(self.d.decide("e1", "W", TOK, "buy", 1)["decision"], "ATLANDI")   # tekrar: iz yazılmaz

    def test_trail_is_immutable(self):
        self.d.decide("e1", "W", TOK, "buy", 1)
        with self.assertRaises(sqlite3.DatabaseError): self.p.db.execute("UPDATE karar_izi SET karar='X'")
        with self.assertRaises(sqlite3.DatabaseError): self.p.db.execute("DELETE FROM karar_izi")


class YurutmeTests(unittest.TestCase):
    def test_measures_loss_after_delay(self):
        p = Paper(); t = [100.0]; uyku = []
        q = Mock(); q.quote = Mock(return_value=dict(out_amount=980, in_amount=10))
        o = YurutmeOlcer(q, p, gecikme=3, clock=lambda: t[0], sleep=lambda s: (uyku.append(s), t.__setitem__(0, t[0] + s)))
        o.enqueue("e1", "buy", TOK, USDC_MINT, TOK, 10, 1000)
        self.assertAlmostEqual(o.isle(o.q.get()), 2.0)                  # 1000 -> 980: %2 kayıp
        self.assertEqual(uyku, [3]); q.quote.assert_called_once_with(USDC_MINT, TOK, 10)
        q.quote = Mock(side_effect=QuoteError("rota yok")); o.enqueue("e2", "sell", TOK, TOK, USDC_MINT, 10, 1000)
        self.assertIsNone(o.isle(o.q.get()))
        rows = {r["event_id"]: dict(r) for r in p.db.execute("SELECT * FROM yurutme_olcum")}
        self.assertEqual((rows["e1"]["kayip_pct"], rows["e2"]["hata"]), (2.0, "rota yok"))
        s = yurutme_summary(list(rows.values()))
        self.assertEqual((s["olculen"], s["hatali"], s["buy"]["n"], s["buy"]["ort"]), (2, 1, 1, 2.0))

    def test_rate_limit_retried_once(self):
        p = Paper(); t = [0.0]
        q = Mock(); q.quote = Mock(side_effect=[QuoteError("Jupiter hız sınırı (429)"), dict(out_amount=990, in_amount=10)])
        o = YurutmeOlcer(q, p, gecikme=3, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
        o.enqueue("e1", "buy", TOK, USDC_MINT, TOK, 10, 1000)
        self.assertAlmostEqual(o.isle(o.q.get()), 1.0); self.assertEqual(q.quote.call_count, 2)
        q.quote = Mock(side_effect=QuoteError("rota yok")); o.enqueue("e2", "buy", TOK, USDC_MINT, TOK, 10, 1000)
        o.isle(o.q.get()); self.assertEqual(q.quote.call_count, 1)        # piyasa hatası tekrarlanmaz

    def test_depth_measured_on_buy(self):
        p = Paper(); t = [0.0]
        def quote(i, o, a):                                  # 5 USDC -> 1000 token; büyük tutarda birim fiyat kötüleşir
            return dict(out_amount={5_000_000: 1000, 25_000_000: 4750, 100_000_000: 16000}.get(a, 5_000_000), in_amount=a)
        q = Mock(); q.quote = Mock(side_effect=quote)
        o = YurutmeOlcer(q, p, gecikme=3, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
        o.enqueue("e1", "buy", TOK, USDC_MINT, TOK, 5_000_000, 1000); o.isle(o.q.get())
        d = dict(p.db.execute("SELECT * FROM derinlik_olcum").fetchone())
        self.assertEqual((d["kayip_25"], d["kayip_100"], d["taban_usd"]), (5.0, 20.0, 5.0))
        o.enqueue("e2", "sell", TOK, TOK, USDC_MINT, 1000, 5_000_000); o.isle(o.q.get())
        self.assertEqual(p.db.execute("SELECT COUNT(*) FROM derinlik_olcum").fetchone()[0], 1)   # satışta ölçülmez

    def test_full_queue_drops(self):
        o = YurutmeOlcer(Mock(), Paper(), maxsize=1)
        o.enqueue("a", "buy", TOK, "x", "y", 1, 1); o.enqueue("b", "buy", TOK, "x", "y", 1, 1)
        self.assertEqual(o.q.qsize(), 1)


class SaglikTests(unittest.TestCase):
    def test_health_snapshot(self):
        d = tempfile.mkdtemp(); pp = os.path.join(d, "p.db"); yd = os.path.join(d, "yed"); os.makedirs(yd)
        p = Paper(pp)
        p.nabiz(1000.0, saglik=dict(baslangic=400.0, ws="bağlı", ws_kopma=2, ws_son_mesaj=990.0, okunamayan=1, cuzdan=7, bot=0))
        open(os.path.join(yd, "nexora_20261115_000000.tar.gz"), "wb").write(b"x")
        h = panel.saglik(pp, None, yedek_dizin=yd, now=1030.0)
        self.assertEqual((h["takip"], h["takip_nabiz_once_sn"], h["takip_calisma_sn"], h["ws"], h["ws_kopma"]), ("çalışıyor", 30, 630, "bağlı", 2))
        self.assertEqual((h["ws_son_mesaj_once_sn"], h["cuzdan"], h["son_yedek"]), (40, 7, "nexora_20261115_000000.tar.gz"))
        self.assertIsNotNone(h["disk"])
        self.assertEqual(panel.saglik(pp, None, yedek_dizin=yd, now=2000.0)["takip"], "durdu")
        self.assertEqual(panel.saglik(os.path.join(d, "yok.db"), None, now=1.0)["takip"], "yok")
        self.assertEqual(p.takip_saglik()["cuzdan"], 7)

    def test_ws_reconnect_counter(self):
        from nexora.ws_client import WSClosed
        n = [0]; stop = threading.Event()
        def bad(url, timeout):
            n[0] += 1
            if n[0] >= 3: stop.set()
            raise WSClosed("x")
        l = WSListener("wss://x", ["W"], lambda w, s: None, connect=bad, log=lambda m: None)
        stop_wait = stop.wait
        stop.wait = lambda d: stop_wait(0)
        l.run_forever(stop)
        self.assertEqual(l.kopma, 3)


class ServerTests(unittest.TestCase):
    def test_endpoints(self):
        d = tempfile.mkdtemp()
        os.environ["NEXORA_API_KEY"] = "k"; os.environ["NEXORA_DB"] = os.path.join(d, "s.db")
        sys.modules.pop("server", None)
        import server
        from http.server import ThreadingHTTPServer
        Decider(server.paper, FakeQuoter(), Safe()).decide("e1", "W", TOK, "buy", 1)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        def get(path):
            req = urllib.request.Request(base + path, headers={"X-API-Key": "k"})
            try:
                with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
        c, h = get("/saglik"); self.assertEqual(c, 200); self.assertIn("takip", h); self.assertEqual(h["karar_izi"], 1)
        c, iz = get("/karar-izi?olay=e1"); self.assertEqual((c, iz["karar"]), (200, "KOPYALANDI"))
        self.assertEqual(get("/karar-izi?olay=yok")[0], 404)
        srv.shutdown(); srv.server_close()


if __name__ == "__main__":
    unittest.main()
