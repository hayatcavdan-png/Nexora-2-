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
    def test_kural_golgesi(self):
        """Sınır yüzünden reddedilen alım gölgede ölçülür; paper defteri değişmez; saatlik kota ve süzgeçler geçerli."""
        d = self.make()
        for i in range(CFG["max_positions_per_wallet"]): d.decide(f"e{i}", "W1", f"T{i}", "buy", 1)
        nakit = self.p.cash()
        r = d.decide("x", "W1", "T9", "buy", 1)
        self.assertEqual(r["decision"], "REDDEDİLDİ"); self.assertEqual(self.p.cash(), nakit); self.assertIsNone(self.p.position("T9"))
        sh = self.p.open_shadows("W1", "T9")
        self.assertEqual(len(sh), 1); self.assertEqual(sh[0]["reason"], "kural: bu cüzdan için pozisyon sınırı dolu")
        self.q.sell_price = 1.2                                            # kaynak satınca gölge kapanır, K/Z ölçülür
        d.decide("s", "W1", "T9", "sell", 1)
        kapali = [s for s in self.p.shadows() if s["token"] == "T9"][0]
        self.assertEqual(kapali["status"], "closed"); self.assertGreater(kapali["pnl_usd"], 0)
        from nexora.rapor import shadow_summary
        g = shadow_summary(self.p.shadows())
        self.assertEqual([(x["grup"], x["kapanan"], x["kazanan"]) for x in g], [("kural: bu cüzdan için pozisyon sınırı dolu", 1, 1)])
        self.q.sell_price = None
        for i in range(20): d.decide(f"k{i}", "W1", f"K{i}", "buy", 1)       # kota: saatte en fazla KURAL_GOLGE_SAAT
        self.assertEqual(sum(1 for s in self.p.shadows() if s["status"] == "open"), d.KURAL_GOLGE_SAAT - 1)
        d2 = Decider(Paper(), FakeQuoter(impact=9.0), Safe())                 # süzgeçten geçmeyen ölçülmez
        for i in range(CFG["max_positions_per_wallet"]): d2.paper.record_buy(f"b{i}", "W1", f"T{i}", 5.0, 1000, 6)
        d2.decide("x", "W1", "T9", "buy", 1); self.assertEqual(d2.paper.open_shadows("W1", "T9"), [])
    def test_watch_only_wallet(self):
        p, q = Paper(), FakeQuoter(); d = Decider(p, q, Safe(), izle={"IZ"})
        self.assertEqual(d.decide("e1", "IZ", TOK, "buy", 1)["reason"], "cüzdan yalnızca izleniyor")
        self.assertEqual(q.calls, []); self.assertIsNone(p.position(TOK))               # ağ isteği yok, pozisyon yok
        self.assertEqual(d.decide("e2", "W", TOK, "buy", 1)["decision"], "KOPYALANDI")  # diğer cüzdanlar etkilenmez
        d2 = Decider(p, q, Safe())                                                      # izlemeye alınmadan önce açılmış pozisyon
        d2.decide("e3", "IZ", "T2", "buy", 1)
        self.assertEqual(d.decide("s3", "IZ", "T2", "sell", 1)["decision"], "KOPYALANDI")  # satış kapatmaya devam eder
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


class KaynakDenetimiTests(unittest.TestCase):
    def setUp(self):
        self.p, self.q = Paper(), FakeQuoter()
        self.d = Decider(self.p, self.q, Safe())
        self.d.decide("e1", "W", TOK, "buy", 1)
        self.acilis = self.p.portfolio()["positions"][0]["opened_ts"] or 0

    def test_kaynakta_token_yoksa_kapatir(self):
        sorulan = []
        r = self.d.kaynak_denetimi(lambda w, t: sorulan.append((w, t)) or 0, now=self.acilis + 3600)
        self.assertEqual(sorulan, [("W", TOK)])
        self.assertEqual(r[0][1], "KOPYALANDI"); self.assertIsNone(self.p.position(TOK))
        sat = [x for x in self.p.trades() if x["side"] == "sell"][0]
        self.assertIn("kaynakta token kalmadı", sat["reason"])

    def test_bakiye_var_bilinmiyor_ya_da_yeni_pozisyon(self):
        self.assertEqual(self.d.kaynak_denetimi(lambda w, t: 5, now=self.acilis + 3600), [])        # kaynak hâlâ tutuyor
        self.assertEqual(self.d.kaynak_denetimi(lambda w, t: None, now=self.acilis + 3600), [])     # RPC hatası: dokunma
        self.assertEqual(self.d.kaynak_denetimi(lambda w, t: 0, now=self.acilis + 60), [])          # 10 dk dolmadı
        self.assertIsNotNone(self.p.position(TOK))

    def test_kaynak_bakiyesi_ayristirma(self):
        from nexora.decision import kaynak_bakiyesi
        hesap = lambda m: {"account": {"data": {"parsed": {"info": {"tokenAmount": {"amount": m}}}}}}
        c = Mock(); c.call = Mock(return_value={"value": [hesap("100"), hesap("23")]})
        self.assertEqual(kaynak_bakiyesi(c, "W", TOK), 123)
        self.assertEqual(c.call.call_args.args[0], "getTokenAccountsByOwner")
        c.call = Mock(return_value={"value": []}); self.assertEqual(kaynak_bakiyesi(c, "W", TOK), 0)   # hesap kapatılmış
        c.call = Mock(side_effect=RuntimeError("ağ")); self.assertIsNone(kaynak_bakiyesi(c, "W", TOK))
        c.call = Mock(return_value={"value": [{"account": {}}]}); self.assertIsNone(kaynak_bakiyesi(c, "W", TOK))


class KismiSatisOlcumTests(unittest.TestCase):
    def setUp(self):
        self.p, self.q = Paper(), FakeQuoter()
        self.d = Decider(self.p, self.q, Safe())
        self.d.decide("e1", "W", TOK, "buy", 1)                       # 5 USDC = 1e9 ham token
        self.q.sell_price = 1.0

    def test_kaynak_kademeli_satarsa_kalan_pay_izlenir(self):
        r = self.d.decide("e2", "W", TOK, "sell", 1, kaynak_oran=0.3)   # kaynak %30 sattı: biz yine hepsini satarız
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertIsNone(self.p.position(TOK))
        self.assertIn("kaynak %30 sattı", [x for x in self.p.trades() if x["side"] == "sell"][0]["reason"])
        k = self.p.kismi_acik("W", TOK)[0]
        self.assertEqual((int(k["kalan_raw"]), k["simdi_usd"]), (700_000_000, 3.5))   # kalan %70 o an 3.5 $
        self.q.sell_price = 2.0
        self.d.decide("e3", "W", TOK, "sell", 1, kaynak_oran=0.5)       # kaynak kalanın yarısını sattı
        k = self.p.kismi_acik("W", TOK)[0]
        self.assertEqual(int(k["kalan_raw"]), 350_000_000); self.assertAlmostEqual(k["sonra_usd"], 3.5)
        self.q.sell_price = 3.0
        self.d.decide("e4", "W", TOK, "sell", 1, kaynak_oran=1.0)       # kaynak tamamen çıktı
        self.assertEqual(self.p.kismi_acik("W", TOK), [])
        row = dict(self.p.db.execute("SELECT * FROM kismi_olcum").fetchone())
        self.assertEqual(row["status"], "closed"); self.assertAlmostEqual(row["sonra_usd"], 8.75)   # 3.5 + 5.25 > 3.5

    def test_tam_satis_ve_bilinmeyen_oran_olcum_acmaz(self):
        self.d.decide("e2", "W", TOK, "sell", 1, kaynak_oran=0.99)
        self.assertEqual(self.p.kismi_acik(), [])
        d2 = Decider(Paper(), FakeQuoter(), Safe()); d2.decide("e1", "W", TOK, "buy", 1)
        d2.decide("e2", "W", TOK, "sell", 1)
        self.assertEqual(d2.paper.kismi_acik(), [])

    def test_zaman_asimi_kalanla_kapatir(self):
        self.d.decide("e2", "W", TOK, "sell", 1, kaynak_oran=0.4)
        k = self.p.kismi_acik()[0]
        self.d.kismi_zaman_asimi(now=k["acilis_ts"] + 3600); self.assertEqual(len(self.p.kismi_acik()), 1)
        self.d.kismi_zaman_asimi(now=k["acilis_ts"] + 90_000)
        row = dict(self.p.db.execute("SELECT * FROM kismi_olcum").fetchone())
        self.assertEqual(row["status"], "zaman"); self.assertAlmostEqual(row["sonra_usd"], 3.0)

    def test_satis_orani_islemden(self):
        from nexora.decision import satis_orani
        b = lambda owner, mint, amt: {"owner": owner, "mint": mint, "uiTokenAmount": {"amount": str(amt)}}
        tx = {"meta": {"preTokenBalances": [b("W", TOK, 1000), b("X", TOK, 5)], "postTokenBalances": [b("W", TOK, 250)]}}
        self.assertEqual(satis_orani(tx, "W", TOK), 0.75)
        tx["meta"]["postTokenBalances"] = []                                   # hesap kapatıldı: hepsi satıldı
        self.assertEqual(satis_orani(tx, "W", TOK), 1.0)
        self.assertIsNone(satis_orani({"meta": {}}, "W", TOK))
        self.assertIsNone(satis_orani({"meta": {"preTokenBalances": [{"owner": "W", "mint": TOK}]}}, "W", TOK))


class GuclendirmeTests(unittest.TestCase):
    def setUp(self):
        self.p, self.q = Paper(), FakeQuoter()
        self.p.ayar_degistir({"max_positions": 10, "max_pos_pct": 0.04})
        self.d = Decider(self.p, self.q, Safe())

    def test_tutulan_tokena_bir_kez_ek_parca(self):
        self.assertEqual(self.d.decide("e1", "W1", TOK, "buy", 1)["decision"], "KOPYALANDI")
        maliyet = self.p.position(TOK)["cost"]; nakit = self.p.cash()
        r = self.d.decide("e2", "W2", TOK, "buy", 1)                         # ikinci cüzdan: teyit
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertIn("güçlendirme", r["reason"])
        pos = self.p.position(TOK)
        self.assertAlmostEqual(pos["cost"], maliyet * 2, places=2)
        self.assertAlmostEqual(int(pos["qty_raw"]) / (4_000_000 * 200), 2.0, places=3)   # iki parçanın miktarı toplandı
        self.assertLess(self.p.cash(), nakit)
        self.assertEqual(self.d.decide("e3", "W3", TOK, "buy", 1)["reason"], "bu pozisyon zaten güçlendirildi")
        self.q.sell_price = 1.0
        self.assertEqual(self.d.decide("e4", "W1", TOK, "sell", 1)["decision"], "KOPYALANDI")    # tümü satılır
        self.assertIsNone(self.p.position(TOK)); self.assertEqual(self.p._get(f"ek:{TOK}"), "0")

    def test_ayni_cuzdan_teyit_sayilmaz_ve_sure(self):
        self.d.decide("e1", "W1", TOK, "buy", 1)
        self.assertEqual(self.d.decide("e2", "W1", TOK, "buy", 1)["reason"], "bu token'da zaten pozisyon var")
        self.d._alimlar[TOK]["W1"] = (self.d._alimlar[TOK]["W1"][0] - 2000, False)                                   # 15 dk'dan eski alım teyit sayılmaz
        self.assertEqual(self.d.decide("e3", "W2", TOK, "buy", 1)["reason"], "bu token'da zaten pozisyon var")

    def test_tutulmayan_teyitli_tokena_iki_kat(self):
        self.d._teyit("W0", TOK)                                             # W0'ın alımı reddedilmiş olsun (ör. yer yok)
        r = self.d.decide("e1", "W1", TOK, "buy", 1)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertAlmostEqual(self.p.position(TOK)["cost"], 8.0, places=2)

    def test_toplam_risk_ek_parcayi_engeller(self):
        for i in range(10):
            t = f"TK{i:02d}" + "1" * 28
            self.assertEqual(self.d.decide(f"a{i}", f"W{i}", t, "buy", 1)["decision"], "KOPYALANDI")
        r = self.d.decide("b", "X", "TK00" + "1" * 28, "buy", 1)
        self.assertEqual(r["reason"], "toplam risk sınırı (%40) dolu")

    def test_kapali_ve_elle_islem(self):
        self.d.GUC_KAT = 1.0
        self.d.decide("e1", "W1", TOK, "buy", 1)
        self.assertEqual(self.d.decide("e2", "W2", TOK, "buy", 1)["reason"], "bu token'da zaten pozisyon var")


class GolgeTeyitTests(unittest.TestCase):
    def test_golge_alimi_canli_teyidi_degistirmez(self):
        from nexora.decision import Decider
        d = Decider.__new__(Decider); d.GUC_SN = 900
        d._teyit("G1", "T", now=100, golge=True)
        self.assertEqual(d._teyit("W1", "T", now=110), (1, 2))          # kopyalanan 1, gölge dahil 2
        self.assertEqual(d._teyit("W2", "T", now=120), (2, 3))
        self.assertEqual(d._teyit("W3", "T", now=2000), (1, 1))         # 15 dk'dan eskiler düşer
