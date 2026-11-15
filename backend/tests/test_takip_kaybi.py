import contextlib, io, json, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from nexora.core import Paper
from nexora.constants import USDC_MINT
from nexora.takip_kaybi import analyze, round_trips, source_price_usd, teshis
from test_lifecycle import tx as ltx, CREATE, CLOSE, RENT, FEE, L, W, TOK

class PriceTests(unittest.TestCase):
    def test_source_price(self):
        self.assertAlmostEqual(source_price_usd(dict(token_delta_raw=2_000_000, token_decimals=6, quote_mint=USDC_MINT, quote_delta_raw=-10_000_000), 150), 5.0)
        self.assertAlmostEqual(source_price_usd(dict(token_delta_raw=10**9, token_decimals=9, sol_delta_lamports=-L), 150), 150.0)
        self.assertIsNone(source_price_usd(dict(token_delta_raw=0, token_decimals=6, sol_delta_lamports=-1), 150))

class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        # Kaynak: 1 SOL (=100$) ile 1e9 ham (1000 token, 6 ondalık) alıyor -> 0.1 $/token
        #         sonra 1000 tokeni 1.5 SOL (=150$) karşılığı satıyor -> 0.15 $/token (+%50)
        self.txs = {
            "sb": ltx("sb", 1000, None, 10**9, 10 * L, 9 * L - RENT - FEE, 0, RENT, ins=[CREATE]),
            "ss": ltx("ss", 2000, 10**9, None, 9 * L, 9 * L + int(1.5 * L) + RENT - FEE, RENT, 0, ins=[CLOSE]),
        }
        p = Paper()
        # Biz: 5$ ile 40 token (0.125 $/token, kaynaktan %25 pahalı), 40 tokeni 5.2$ karşılığı sattık (0.13, kaynaktan %13.3 ucuz)
        p.record_buy(f"{W}:sb", W, TOK, 5.0, 40_000_000, 6)
        p.record_sell(f"{W}:ss", W, TOK, 5.2)
        self.trades = p.trades()
    def test_round_trip_decomposition(self):
        r = analyze(self.trades, lambda s: self.txs.get(s), 100.0)
        t = r["islemler"][0]
        self.assertEqual(t["durum"], "kapandi")
        self.assertAlmostEqual(t["kaynak_alis"], 0.1); self.assertAlmostEqual(t["kaynak_satis"], 0.15)
        self.assertAlmostEqual(t["giris_kaybi"], 0.25); self.assertAlmostEqual(t["cikis_kaybi"], 1 - 0.13 / 0.15)
        self.assertAlmostEqual(t["kaynak_getiri"], 0.5); self.assertAlmostEqual(t["tutma_sn"], 0, delta=5)
        self.assertLess(t["bizim_getiri"], 0.05)                       # kaynak +%50, biz ~+%4: fark takip kaybı
        w = r["cuzdanlar"][0]; self.assertEqual((w["islem"], w["kapanan"]), (1, 1)); self.assertAlmostEqual(w["giris_kaybi_ort"], 0.25)
        self.assertIn("giriş kaybı %+25.0", teshis(t))
    def test_unreadable_source_and_open_position(self):
        p = Paper(); p.record_buy("Z:yok", "Z", "T", 5.0, 1000, 6)
        r = analyze(p.trades(), lambda s: None, 100.0)
        t = r["islemler"][0]
        self.assertEqual((t["durum"], t["giris_kaybi"]), ("acik", None)); self.assertEqual(teshis(t), "açık pozisyon")
        r = analyze(self.trades, lambda s: (_ for _ in ()).throw(ConnectionError()), 100.0)   # ağ hatası çökertmez
        self.assertIsNone(r["islemler"][0]["giris_kaybi"])
    def test_round_trip_pairing(self):
        rows = [dict(ts=1, id=1, decision="KOPYALANDI", side="buy", wallet="A", token="T"),
                dict(ts=2, id=2, decision="REDDEDİLDİ", side="sell", wallet="A", token="T"),
                dict(ts=3, id=3, decision="KOPYALANDI", side="sell", wallet="A", token="T"),
                dict(ts=4, id=4, decision="KOPYALANDI", side="buy", wallet="A", token="T")]
        rt = round_trips(rows)
        self.assertEqual([(x["alis"]["id"], x["satis"] and x["satis"]["id"]) for x in rt], [(1, 3), (4, None)])
    def test_cli_writes_json(self):
        d = tempfile.mkdtemp(); path = os.path.join(d, "p.db"); out = os.path.join(d, "k.json")
        p = Paper(path); p.record_buy(f"{W}:sb", W, TOK, 5.0, 40_000_000, 6); p.record_sell(f"{W}:ss", W, TOK, 5.2)
        import takip_kaybi as cli
        class C:
            def get_transaction(s, sig): return self.txs.get(sig)
        class Q:
            def quote(s, i, o, a): return dict(out_amount=100_000_000)
        with contextlib.redirect_stdout(io.StringIO()) as buf: cli.main(client=C(), quoter=Q(), paper_path=path, out=out)
        self.assertEqual(json.load(open(out))["islemler"][0]["durum"], "kapandi"); self.assertIn("giriş kaybı", buf.getvalue())
if __name__ == "__main__": unittest.main()
