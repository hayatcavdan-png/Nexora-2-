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
        with redirect_stdout(io.StringIO()):
            aday = K.main(client=cl, tracker_db=self.tdb, out_dir=self.d)
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
