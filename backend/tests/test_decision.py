import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unittest.mock import Mock
from nexora.core import Paper, CFG
from nexora.constants import USDC_MINT
from nexora.market import JupiterQuoter, QuoteError
from nexora.token_safety import evaluate, TokenSafety, TOKEN_PROGRAM, TOKEN_2022
from nexora.decision import Decider
from nexora.live_tracker import LiveTracker

TOK = "MEME111111111111111111111111111111"

def resp(status=200, body=None):
    r = Mock(status_code=status); r.json = Mock(return_value=body); return r

class QuoterTests(unittest.TestCase):
    def q(self, r, key=""):
        s = Mock(); s.get = Mock(return_value=r)
        return JupiterQuoter(api_key=key, session=s, min_interval=0), s
    def test_parses_quote(self):
        jq, s = self.q(resp(body={"inAmount": "5000000", "outAmount": "123456", "priceImpact": -0.4, "router": "metis"}))
        d = jq.quote(USDC_MINT, TOK, 5_000_000)
        self.assertEqual((d["out_amount"], d["price_impact_pct"]), (123456, 0.4))
        self.assertNotIn("taker", s.get.call_args.kwargs["params"])           # işlem oluşturulmaz
        self.assertEqual(s.get.call_args.kwargs["headers"], {})               # anahtar yoksa başlık yok
    def test_legacy_impact_field(self):
        jq, _ = self.q(resp(body={"inAmount": "10", "outAmount": "5", "priceImpactPct": "0.012"}))
        self.assertAlmostEqual(jq.quote("A", "B", 10)["price_impact_pct"], 1.2)
    def test_errors(self):
        for r, msg in [(resp(400), "rota yok"), (resp(429), "429"), (resp(500), "HTTP 500"),
                       (resp(body={"inAmount": "9", "outAmount": "5", "priceImpact": 0}), "tutarsız"),
                       (resp(body={"inAmount": "10", "outAmount": "0", "priceImpact": 0}), "rota yok"),
                       ]:
            jq, _ = self.q(r)
            with self.assertRaises(QuoteError) as c: jq.quote("A", "B", 10)
            self.assertIn(msg, str(c.exception))
    def test_unpriced_token_impact_unknown(self):
        # Gerçek yanıt (15.11.2026, 8z38…mi1m): Jupiter USD fiyatı yok -> outUsdValue 0, priceImpact -100
        jq, _ = self.q(resp(body={"inAmount": "5000000", "outAmount": "36696720", "inUsdValue": 4.9987,
                                  "outUsdValue": 0, "priceImpact": -100, "priceImpactPct": "-1", "router": "metis"}))
        d = jq.quote(USDC_MINT, TOK, 5_000_000)
        self.assertIsNone(d["price_impact_pct"]); self.assertEqual(d["out_amount"], 36696720)
        jq, _ = self.q(resp(body={"inAmount": "10", "outAmount": "5"}))         # hiç etki alanı yok
        self.assertIsNone(jq.quote("A", "B", 10)["price_impact_pct"])
    def test_api_key_header_and_not_in_errors(self):
        jq, s = self.q(resp(400), key="GIZLIANAHTAR")
        with self.assertRaises(QuoteError) as c: jq.quote("A", "B", 10)
        self.assertEqual(s.get.call_args.kwargs["headers"], {"x-api-key": "GIZLIANAHTAR"})
        self.assertNotIn("GIZLI", str(c.exception))
    def test_throttle(self):
        t = [0.0]; slept = []
        jq = JupiterQuoter(api_key="", session=Mock(get=Mock(return_value=resp(body={"inAmount": "10", "outAmount": "5", "priceImpact": 0}))),
                           clock=lambda: t[0], sleep=lambda x: (slept.append(x), t.__setitem__(0, t[0] + x)))
        jq.quote("A", "B", 10); jq.quote("A", "B", 10)
        self.assertAlmostEqual(slept[0], 2.1)                                 # anahtarsız: 0.5 istek/sn

def mint(owner=TOKEN_PROGRAM, freeze=None, mint_auth=None, exts=None, decimals=6):
    info = {"decimals": decimals, "freezeAuthority": freeze, "mintAuthority": mint_auth}
    if exts is not None: info["extensions"] = [{"extension": e} for e in exts]
    return {"owner": owner, "data": {"parsed": {"info": info, "type": "mint"}}}

class SafetyTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(evaluate(mint())["verdict"], "UYGUN")
        self.assertEqual(evaluate(mint(freeze="X"))["verdict"], "REDDEDİLDİ")
        self.assertEqual(evaluate(mint(mint_auth="X"))["verdict"], "REDDEDİLDİ")
        self.assertEqual(evaluate(mint(TOKEN_2022, exts=["metadataPointer", "tokenMetadata"]))["verdict"], "UYGUN")
        self.assertEqual(evaluate(mint(TOKEN_2022, exts=["transferHook"]))["verdict"], "REDDEDİLDİ")
        self.assertEqual(evaluate(mint(TOKEN_2022, exts=["yeniOzellik"]))["verdict"], "BİLİNMİYOR")
        self.assertEqual(evaluate(None)["verdict"], "BİLİNMİYOR")
        self.assertEqual(evaluate(mint(owner="Baska"))["verdict"], "REDDEDİLDİ")
    def test_cache_only_safe_and_errors_unknown(self):
        c = Mock(); c.call = Mock(return_value={"value": mint()})
        ts = TokenSafety(c); ts.check("M"); ts.check("M"); self.assertEqual(c.call.call_count, 1)
        c.call = Mock(return_value={"value": mint(freeze="X")}); ts.check("N"); ts.check("N")
        self.assertEqual(c.call.call_count, 2)                                 # olumsuz sonuç önbelleğe alınmaz
        c.call = Mock(side_effect=ConnectionError()); self.assertEqual(ts.check("Z")["verdict"], "BİLİNMİYOR")

class FakeQuoter:
    """USDC->TOK: 5 USDC = 1000 token (6 ondalık). TOK->USDC: geri satış oranı ayarlanabilir."""
    def __init__(self, impact=0.5, back_ratio=0.97, sell_price=None, fail=()):
        self.impact, self.back_ratio, self.sell_price, self.fail, self.calls = impact, back_ratio, sell_price, set(fail), []
    def quote(self, i, o, amt):
        self.calls.append((i, o, amt))
        if (i, o) in self.fail: raise QuoteError("rota yok")
        if i == USDC_MINT: return dict(in_amount=amt, out_amount=amt * 200, price_impact_pct=self.impact)
        usdc = int(amt / 200 * (self.sell_price if self.sell_price else self.back_ratio))
        return dict(in_amount=amt, out_amount=usdc, price_impact_pct=0.3)

class Safe:
    def __init__(self, verdict="UYGUN"): self.verdict, self.calls = verdict, 0
    def check(self, m): self.calls += 1; return dict(verdict=self.verdict, reasons=["test"], decimals=6)

class DecisionTests(unittest.TestCase):
    def make(self, **kw):
        self.p, self.q, self.s = Paper(), FakeQuoter(**kw), Safe(kw.pop("verdict", "UYGUN") if "verdict" in kw else "UYGUN")
        return Decider(self.p, self.q, self.s)
    def test_buy_uses_real_quote(self):
        d = self.make(); r = d.decide("e1", "W", TOK, "buy", 1)
        self.assertEqual(r["decision"], "KOPYALANDI")
        pos = self.p.position(TOK)
        self.assertEqual((pos["qty_raw"], pos["decimals"], pos["cost"]), (str(5_000_000 * 200), 6, 5.0))
        self.assertAlmostEqual(self.p.cash(), 100 - 5 - CFG["net_fee_usd"])
        self.assertIn("al-sat kaybı %3.0", r["reason"])
    def test_sell_realizes_pnl_from_quote(self):
        d = self.make(); d.decide("e1", "W", TOK, "buy", 1)
        self.q.sell_price = 1.5                                                 # token %50 değerlendi
        r = d.decide("e2", "W", TOK, "sell", 1)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertAlmostEqual(r["pnl"], 7.5 - 0.01 - 5.0)
        self.assertIsNone(self.p.position(TOK))
    def test_no_double_buy_same_token(self):
        d = self.make(); d.decide("e1", "W", TOK, "buy", 1); n = len(self.q.calls)
        self.assertEqual(d.decide("e2", "W", TOK, "buy", 1)["reason"], "bu token'da zaten pozisyon var")
        self.assertEqual(len(self.q.calls), n)                                  # gereksiz teklif yok
    def test_rejections(self):
        self.assertIn("fiyat etkisi", self.make(impact=5).decide("e", "W", TOK, "buy", 1)["reason"])
        self.assertIn("al-sat kaybı yüksek", self.make(back_ratio=0.90).decide("e", "W", TOK, "buy", 1)["reason"])
        r = self.make(fail=[(TOK, USDC_MINT)]).decide("e", "W", TOK, "buy", 1)
        self.assertIn("geri satış teklifi yok", r["reason"]); self.assertIsNone(self.p.position(TOK))
        self.assertIn("alış teklifi yok", self.make(fail=[(USDC_MINT, TOK)]).decide("e", "W", TOK, "buy", 1)["reason"])
    def test_unknown_impact_decided_by_round_trip(self):
        p, q = Paper(), FakeQuoter(impact=None, back_ratio=0.919); d = Decider(p, q, Safe())
        r = d.decide("e", "W", TOK, "buy", 1)                                   # 8z38 örneği: %8.1 kayıp
        self.assertIn("al-sat kaybı yüksek (%8.1)", r["reason"])
        p, q = Paper(), FakeQuoter(impact=None, back_ratio=0.97); d = Decider(p, q, Safe())
        r = d.decide("e", "W", TOK, "buy", 1)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertIn("etki bilinmiyor", r["reason"])
    def test_unsafe_token_no_quotes(self):
        p, q = Paper(), FakeQuoter(); d = Decider(p, q, Safe("REDDEDİLDİ"))
        self.assertIn("token REDDEDİLDİ", d.decide("e", "W", TOK, "buy", 1)["reason"]); self.assertEqual(q.calls, [])
    def test_stale_and_kill_no_network(self):
        d = self.make(); self.assertEqual(d.decide("e1", "W", TOK, "buy", 60)["reason"], "sinyal bayat")
        self.p.set_kill(True); self.assertEqual(d.decide("e2", "W", TOK, "buy", 1)["reason"], "acil durdurma aktif")
        self.assertEqual((self.q.calls, self.s.calls), ([], 0))
    def test_sell_without_position_and_failed_sell_quote(self):
        d = self.make(); self.assertIn("sahip olunmayan", d.decide("s0", "W", TOK, "sell", 1)["reason"])
        d.decide("e1", "W", TOK, "buy", 1); self.q.fail.add((TOK, USDC_MINT))
        r = d.decide("s1", "W", TOK, "sell", 1)
        self.assertIn("pozisyon açık kaldı", r["reason"]); self.assertIsNotNone(self.p.position(TOK))
    def test_per_wallet_position_limit(self):
        d = self.make()
        for i in range(CFG["max_positions_per_wallet"]): self.assertEqual(d.decide(f"e{i}", "W1", f"T{i}", "buy", 1)["decision"], "KOPYALANDI")
        self.assertEqual(d.decide("x", "W1", "T9", "buy", 1)["reason"], "bu cüzdan için pozisyon sınırı dolu")
        self.assertEqual(d.decide("y", "W2", "T9", "buy", 1)["decision"], "KOPYALANDI")    # başka cüzdan etkilenmez
    def test_fee_reserve_kept(self):
        p = Paper(); d = Decider(p, FakeQuoter(), Safe())
        p.db.execute("UPDATE state SET v='5.5' WHERE k IN ('cash','day_start')"); p.db.commit()   # 5.5 USDC (zarar limiti dışı)
        r = d.decide("e", "W", TOK, "buy", 1)                                        # 0.275 + 0.01 + 1.0 rezerv <= 5.5: geçer
        self.assertEqual(r["decision"], "KOPYALANDI")
        p.db.execute("UPDATE state SET v='1.04' WHERE k IN ('cash','day_start')"); p.db.execute("DELETE FROM positions"); p.db.commit()
        self.assertIn("ücret rezervi", d.decide("e2", "W2", "T2", "buy", 1)["reason"])
    def test_duplicate_event_skipped(self):
        d = self.make(); d.decide("e1", "W", TOK, "buy", 1)
        self.assertEqual(d.decide("e1", "W", TOK, "buy", 1)["decision"], "ATLANDI")
    def test_max_positions_and_old_schema_migration(self):
        d = self.make()
        for i in range(CFG["max_positions"]): d.decide(f"e{i}", f"W{i}", f"T{i}", "buy", 1)
        self.assertEqual(d.decide("x", "W", "T9", "buy", 1)["reason"], "maks. eşzamanlı pozisyon")
        import sqlite3, tempfile
        db = os.path.join(tempfile.mkdtemp(), "old.db"); c = sqlite3.connect(db)
        c.execute("CREATE TABLE positions(token TEXT PRIMARY KEY, qty REAL, cost REAL, last_price REAL, wallet TEXT)"); c.commit(); c.close()
        Paper(db).record_buy("e", "W", TOK, 5.0, 1000, 6)                       # eski veritabanı açılabilir

class TrackerIntegration(unittest.TestCase):
    def test_signal_goes_through_decider(self):
        from test_tracker import swap_tx
        client = Mock(); client.call = Mock(side_effect=lambda m, p: swap_tx(p[0], "A") if m == "getTransaction" else [])
        p = Paper(); dec = Decider(p, FakeQuoter(), Safe())
        tr = LiveTracker(client, p, ":memory:", ["A"], clock=lambda: 1001, sleep=lambda s: None, decider=dec)
        r = tr.handle_signature("A", "sig1")
        self.assertEqual((r["side"], r["decision"]), ("BUY", "KOPYALANDI"))     # test token'ı 'TOK'
        self.assertEqual(tr.signals()[0]["decision"], "KOPYALANDI")
        self.assertEqual(p.trades()[0]["event_id"], "A:sig1")
if __name__ == "__main__": unittest.main()
