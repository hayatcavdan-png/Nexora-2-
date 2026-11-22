import io
from contextlib import redirect_stdout
import os, sqlite3, tempfile, unittest
import cuzdan_kesif as K
from nexora.helius_client import HeliusRPCError
from nexora.wallet_analysis import analyze
from nexora.constants import USDC_MINT
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_analiz import round_trip, W


JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"


def swap_tx(payer, token, t):
    """Ödeyici USDC verip token alır (test_analiz'deki Jupiter swap kalıbı)."""
    def bal(i, m, a): return dict(accountIndex=i, mint=m, owner=payer, uiTokenAmount=dict(amount=str(a), decimals=6))
    pre, post = [bal(1, token, 0), bal(2, USDC_MINT, 10**9)], [bal(1, token, 10**9), bal(2, USDC_MINT, 10**9 - 10**7)]
    return dict(slot=t, blockTime=t, transaction=dict(signatures=[f"s{payer}{t}"], message=dict(
        accountKeys=[payer, "x", "y"], instructions=[dict(programId=JUP)])),
        meta=dict(err=None, fee=5000, logMessages=[f"Program {JUP} invoke [1]"], preBalances=[10**10, 0, 0],
                  postBalances=[10**10 - 5000, 0, 0], preTokenBalances=pre, postTokenBalances=post))


def sell_tx(payer, token, t):
    tx = swap_tx(payer, token, t)
    m = tx["meta"]; m["preTokenBalances"], m["postTokenBalances"] = m["postTokenBalances"], m["preTokenBalances"]
    tx["transaction"]["signatures"] = [f"sat{payer}{t}"]
    return tx


class FakeClient:
    def __init__(self, by_token, filtre_hata=False): self.by_token, self.filtre_hata, self.calls = by_token, filtre_hata, []
    def call(self, method, params):
        self.calls.append(params)
        token, opts = params
        if self.filtre_hata and "blockTime" in opts["filters"]:
            e = HeliusRPCError("filtre yok"); e.rpc_code = -32602; raise e
        v = self.by_token.get(token, [])
        if isinstance(v, dict):                                     # sayfalı: {"p1": [...], "p2": [...]}
            sayfa = opts.get("paginationToken") or "p1"
            return {"data": v[sayfa], "paginationToken": v.get("sonraki_" + sayfa)}
        return {"data": v}


class KesifTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.eski = os.getcwd(); os.chdir(self.d)
        self.tdb = os.path.join(self.d, "t.db")
        c = sqlite3.connect(self.tdb)
        c.execute("""CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, wallet TEXT, sig TEXT, side TEXT,
            token TEXT, token_delta TEXT, quote TEXT, block_time INTEGER, latency_s REAL, decision TEXT, reason TEXT)""")
        for tok, bt in (("TOKA", 10_000), ("TOKB", 20_000), ("TOKA", 30_000)):
            c.execute("INSERT INTO tracker_signals(side,token,wallet,block_time) VALUES('BUY',?,?,?)", (tok, "SRC", bt))
        c.execute("INSERT INTO tracker_signals(side,token,wallet,block_time) VALUES('SELL','TOKC','SRC',40000)")
        c.commit(); c.close()
        open("wallets.txt", "w").write("SRC\nKNOWN\n")

    def tearDown(self): os.chdir(self.eski)

    def test_recent_distinct_buys(self):
        self.assertEqual(K.kaynak_alimlar(self.tdb, 10), [("TOKA", "SRC", 30_000), ("TOKB", "SRC", 20_000)])

    def test_finds_repeat_early_buyers(self):
        cl = FakeClient({"TOKA": [swap_tx("ERKEN", "TOKA", 29_000), swap_tx("KNOWN", "TOKA", 29_500), swap_tx("GEC", "TOKA", 30_500),
                                  swap_tx("TEK", "TOKA", 29_900)],
                         "TOKB": [swap_tx("ERKEN", "TOKB", 19_500)]})
        egri = K.egri_ustunde; K.egri_ustunde = lambda a: a != "TEK"     # test adları gerçek anahtar değil; TEK eğri dışı sayılır
        try:
            with redirect_stdout(io.StringIO()):
                aday = K.main(client=cl, tracker_db=self.tdb, out_dir=self.d, piyasa=lambda: [])
        finally:
            K.egri_ustunde = egri
        self.assertEqual(aday, ["ERKEN"])                                 # iki token'da erken; KNOWN bilinen, GEC sonra aldı
        self.assertEqual(cl.calls[0][1]["filters"]["blockTime"], {"gte": 30_000 - K.PENCERE, "lt": 30_000})
        rows = open(os.path.join(self.d, K.OUT_CSV)).read()
        self.assertIn("ERKEN,2", rows); self.assertIn("TEK,1", rows)

    def test_filter_fallback(self):
        cl = FakeClient({"TOKA": [swap_tx("X", "TOKA", 29_000)]}, filtre_hata=True)
        al, n, _ = K.erken_alicilar(cl, "TOKA", 30_000)
        self.assertEqual((al, n), ({"X"}, 1)); self.assertNotIn("blockTime", cl.calls[-1][1]["filters"])


class DususTests(unittest.TestCase):
    def test_wallet_drawdown(self):
        # +5, +5, -8, -2, +5 (USDC): zirve 10, dip 0 -> düşüş 10; toplam kazanç 15
        txs = sum((round_trip(i, f"T{i}", 10, s, 1000 + i * 5000) for i, s in enumerate([15, 15, 2, 8, 15])), [])
        m = analyze(txs, W, 150.0)
        self.assertAlmostEqual(m["max_dusus_usd"], 10.0, places=1)
        self.assertAlmostEqual(m["dusus_kazanc_orani"], round(10 / 15, 3), places=2)


class HizliElemeTests(unittest.TestCase):
    def test_hizli_al_satci_elenir(self):
        cl = FakeClient({"T": [swap_tx("BOT", "T", 900), sell_tx("BOT", "T", 911), swap_tx("TUTAN", "T", 800),
                               sell_tx("TUTAN", "T", 950)]})
        alicilar, n, elenen = K.erken_alicilar(cl, "T", 1000, pencere=3600, sayfa=1, min_tutma=60)
        self.assertEqual((alicilar, n, elenen), ({"TUTAN"}, 4, 1))

    def test_sayfalama(self):
        cl = FakeClient({"T": {"p1": [swap_tx("A", "T", 900)], "sonraki_p1": "p2", "p2": [swap_tx("B", "T", 800)]}})
        alicilar, n, _ = K.erken_alicilar(cl, "T", 1000, pencere=3600, sayfa=3, min_tutma=60)
        self.assertEqual((alicilar, n, len(cl.calls)), ({"A", "B"}, 2, 2))
        self.assertEqual(cl.calls[1][1]["paginationToken"], "p2")
        cl = FakeClient({"T": {"p1": [swap_tx("A", "T", 900)], "sonraki_p1": "p2", "p2": [swap_tx("B", "T", 800)]}})
        self.assertEqual(K.erken_alicilar(cl, "T", 1000, pencere=3600, sayfa=1)[0], {"A"})


class GT:
    """Sahte GeckoTerminal oturumu."""
    def __init__(self, havuzlar): self.havuzlar, self.istek = havuzlar, []
    def get(self, url, timeout=None):
        self.istek.append(url); h = self.havuzlar
        class R:
            def json(self_): return {"data": h if "page=2" not in url else []}
        return R()


def havuz(tok, acilis_iso, lik=50_000, hacim=200_000, h24=120.0, h6=10.0):
    return {"attributes": {"pool_created_at": acilis_iso, "reserve_in_usd": str(lik), "volume_usd": {"h24": str(hacim)},
                           "price_change_percentage": {"h24": str(h24), "h6": str(h6)}},
            "relationships": {"base_token": {"data": {"id": "solana_" + tok}}}}


class PiyasaTests(unittest.TestCase):
    def test_suzme_ve_siralama(self):
        now = 1_800_000_000.0
        import datetime
        iso = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        s = GT([havuz("IYI", iso(now - 86400), h24=300), havuz("ORTA", iso(now - 3 * 86400), h24=80),
                havuz("ZAYIF", iso(now - 86400), h24=20),                         # yükseliş az
                havuz("SIG", iso(now - 86400), lik=5_000),                        # likidite az
                havuz("YENI", iso(now - 600)),                                    # 2 saatten genç
                havuz("ESKI", iso(now - 30 * 86400)),                             # 7 günden yaşlı
                havuz(K.USDC if hasattr(K, "USDC") else "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", iso(now - 86400))])
        r = K.piyasa_kazananlari(10, s=s, now=now, uyku=lambda x: None)
        self.assertEqual([x[0] for x in r], ["IYI", "ORTA"])
        tok, kaynak, son, acilis = r[0]
        self.assertIsNone(kaynak); self.assertEqual(son - acilis, int(K.PIYASA_SAAT * 3600))
        self.assertEqual(K.piyasa_kazananlari(1, s=s, now=now, uyku=lambda x: None)[0][0], "IYI")
        self.assertEqual(K.piyasa_kazananlari(0, s=s, now=now), [])

    def test_ag_hatasi_bos(self):
        class Bozuk:
            def get(self, *a, **k): raise K.requests.ConnectionError("yok")
        self.assertEqual(K.piyasa_kazananlari(5, s=Bozuk(), uyku=lambda x: None), [])

    def test_main_piyasa_tokeni_eskiden_yeniye_taranir(self):
        d = tempfile.mkdtemp(); eski = os.getcwd(); os.chdir(d)
        try:
            tdb = os.path.join(d, "t.db"); c = sqlite3.connect(tdb)
            c.execute("CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, side TEXT, token TEXT, wallet TEXT, block_time INTEGER)")
            c.execute("INSERT INTO tracker_signals(side,token,wallet,block_time) VALUES('BUY','TOKA','SRC',10000)"); c.commit(); c.close()
            acilis = 100_000
            cl = FakeClient({"PIY": [swap_tx("ERKEN", "PIY", acilis + 600), swap_tx("SNIPER", "PIY", acilis + 30)],
                             "TOKA": [swap_tx("ERKEN", "TOKA", 9000)]})
            with redirect_stdout(io.StringIO()):
                K.main(client=cl, tracker_db=tdb, out_dir=d, piyasa=lambda: [("PIY", None, acilis + 4 * 3600, acilis)])
            piy = [p for p in cl.calls if p[0] == "PIY"][0][1]
            self.assertEqual(piy["sortOrder"], "asc")
            self.assertEqual(piy["filters"]["blockTime"], {"gte": acilis, "lt": acilis + 4 * 3600})
            satir = open(os.path.join(d, K.OUT_CSV)).read()
            self.assertIn("ERKEN,2", satir); self.assertNotIn("SNIPER", satir)
        finally:
            os.chdir(eski)


if __name__ == "__main__":
    unittest.main()


class BoyutTests(unittest.TestCase):
    def test_weights_and_summary(self):
        from nexora.decision import puan_agirligi, Decider
        from nexora.core import Paper
        from nexora.rapor import boyut_summary
        from test_decision import FakeQuoter, Safe, TOK
        self.assertEqual(puan_agirligi({"A": 2.0, "B": 0.5}, "A"), (2.0, 1.0))
        self.assertEqual(puan_agirligi({"A": 2.0, "B": 0.2}, "B"), (0.2, 0.2))       # alt sınır 0.2
        self.assertEqual(puan_agirligi({"A": 2.0}, "YOK"), (None, 0.5))
        p = Paper(); q = FakeQuoter()
        d = Decider(p, q, Safe(), puanlar={"W": 1.0, "Z": 2.0})
        d.decide("b", "W", TOK, "buy", 1); q.sell_price = 1.2; d.decide("s", "W", TOK, "sell", 1)   # alımdan sonra yükseldi
        iz = [dict(r) for r in p.db.execute("SELECT * FROM pos_iz")]
        bo = [dict(r) for r in p.db.execute("SELECT * FROM boyut_olcum")]
        self.assertEqual(bo[0]["agirlik"], 0.5)
        y = {x["yontem"]: x for x in boyut_summary(iz, bo)["yontemler"]}
        gercek = iz[0]["pnl"]
        self.assertAlmostEqual(y["sabit %5 (şu anki)"]["kz"], round(gercek, 4), places=4)
        brut = gercek + 0.02
        self.assertAlmostEqual(y["puan ağırlıklı"]["kz"], round(brut * 0.5 - 0.02, 4), places=4)
        self.assertAlmostEqual(y["sabit 1 USDC"]["kz"], round(brut / 5 - 0.02, 4), places=4)


class KazananTests(unittest.TestCase):
    def test_kazanan_alimlar_ve_sniper_elenir(self):
        d = tempfile.mkdtemp(); db = os.path.join(d, "e.db")
        from nexora.etiket import SEMA
        c = sqlite3.connect(db); c.executescript(SEMA)
        for i, (tok, g, yas) in enumerate([("TW", 45.0, 600), ("TW", 30.0, 900), ("TK", 5.0, 600), ("TX", 25.0, None)]):
            c.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token, block_time, tb_yas_sn) VALUES(?,?,?,?,?,?)",
                      (f"e{i}", 1_000_000.0, "SRC", tok, 999_990, yas))
            c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES(?, 'kaynak', 0, ?)", (f"e{i}", g))
        c.commit(); c.close()
        k = K.kazanan_alimlar(db, 10, now=1_000_100.0)
        self.assertEqual(k, [("TW", "SRC", 999_990, 1_000_000.0 - 600), ("TX", "SRC", 999_990, None)])   # TK %20 altında
        cl = FakeClient({"T": [swap_tx("SNIPER", "T", 1010), swap_tx("ERKEN", "T", 1500)]})
        alicilar, _, elenen = K.erken_alicilar(cl, "T", 2000, pencere=3600, sayfa=1, olusma=1000, sniper_sn=120)
        self.assertEqual((alicilar, elenen), ({"ERKEN"}, 1))                                              # 10 sn'de alan elenir
