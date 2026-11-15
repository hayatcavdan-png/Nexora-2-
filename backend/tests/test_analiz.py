import contextlib, csv, io, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from nexora.constants import USDC_MINT, WSOL_MINT
from nexora.wallet_analysis import analyze, verdict, THRESHOLDS
import cuzdan_analiz as ca

W = "WaLLet1111111111111111111111111111111"
JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

def tx(sig, t, tok, tok_pre, tok_post, quote=USDC_MINT, q_pre=0, q_post=0, sol_pre=10**10, sol_post=10**10, create=False):
    """Jupiter swap'ı. quote=None -> yerel SOL ile (lamport farkı). create=True -> token hesabı açılıyor."""
    def bal(i, m, a, d): return dict(accountIndex=i, mint=m, owner=W, uiTokenAmount=dict(amount=str(a), decimals=d))
    pre, post = [bal(1, tok, tok_pre, 6)], [bal(1, tok, tok_post, 6)]
    if create: pre = []
    if quote:
        d = 9 if quote == WSOL_MINT else 6
        pre.append(bal(2, quote, q_pre, d)); post.append(bal(2, quote, q_post, d))
    return dict(slot=t, blockTime=t, transaction=dict(signatures=[sig], message=dict(accountKeys=[W, "x", "y"], instructions=[dict(programId=JUP)])),
        meta=dict(err=None, fee=5000, logMessages=[f"Program {JUP} invoke [1]"], preBalances=[sol_pre, 0, 0],
                  postBalances=[sol_post - 5000, 0, 0], preTokenBalances=pre, postTokenBalances=post))

def round_trip(i, tok, buy_usdc, sell_usdc, t0, hold=600):
    """USDC ile al, sonra sat (miktarlar USDC)."""
    q = 10**6
    return [tx(f"b{i}", t0, tok, 0, 1000 * q, q_pre=1000 * q, q_post=1000 * q - buy_usdc * q),
            tx(f"s{i}", t0 + hold, tok, 1000 * q, 0, q_pre=0, q_post=int(round(sell_usdc * q)))]

class AnalyzeTests(unittest.TestCase):
    def test_profitable_trader(self):
        txs = []
        for i in range(10):                                   # 7 kazanç (+%50), 3 kayıp (-%20)
            txs += round_trip(i, f"T{i}", 10, 15 if i < 7 else 8, 1000 + i * 5000)
        m = analyze(txs, W, 150.0)
        self.assertEqual((m["swap"], m["kapanan"], m["token_sayisi"]), (20, 10, 10))
        self.assertAlmostEqual(m["gerceklesen_usd"], 7 * 5 - 3 * 2, places=1)
        self.assertEqual(m["kazanma_orani"], 0.7); self.assertEqual(m["medyan_tutma_sn"], 600)
        self.assertEqual(verdict(m)[0], "kopyalanabilir")
    def test_losing_and_fast_and_insufficient(self):
        lose = sum((round_trip(i, f"T{i}", 10, 8, 1000 + i * 5000) for i in range(6)), [])
        self.assertEqual(verdict(analyze(lose, W, 150.0))[0], "zararda")
        fast = sum((round_trip(i, f"T{i}", 10, 15, 1000 + i * 5000, hold=5) for i in range(6)), [])
        self.assertEqual(verdict(analyze(fast, W, 150.0))[0], "çok hızlı")
        few = sum((round_trip(i, f"T{i}", 10, 15, 1000 + i * 5000) for i in range(2)), [])
        self.assertEqual(verdict(analyze(few, W, 150.0))[0], "yetersiz veri")
        self.assertEqual(verdict(analyze([], W, 150.0))[0], "swap yok")
    def test_one_lucky_token_flagged(self):
        txs = round_trip(0, "BIG", 10, 500, 1000) + sum((round_trip(i, f"T{i}", 10, 10.5, 9000 + i * 5000) for i in range(1, 6)), [])
        k, why = verdict(analyze(txs, W, 150.0))
        self.assertEqual(k, "zayıf"); self.assertTrue(any("tek token" in w for w in why))
    def test_unmatched_sells_mean_missing_history(self):
        q = 10**6
        sells = [tx(f"s{i}", 1000 + i, f"T{i}", 1000 * q, 0, q_pre=0, q_post=15 * q) for i in range(8)]
        txs = sells + sum((round_trip(i, f"U{i}", 10, 15, 50000 + i * 5000) for i in range(5)), [])
        self.assertEqual(verdict(analyze(txs, W, 150.0))[0], "eksik veri")
    def test_volume_bot_pattern_826t(self):
        # 826t örneği: aynı token'ı aynı miktarda alıp neredeyse aynı fiyata geri satan turlar
        txs = sum((round_trip(i, "CTM", 10, 10, 1000 + i * 600, hold=300) for i in range(8)), [])
        m = analyze(txs, W, 150.0); k, why = verdict(m)
        self.assertEqual(k, "bot şüphesi"); self.assertEqual(m["tek_token_tur"], 8); self.assertIn("hacim botu", why[0])
    def test_real_trader_not_flagged_as_bot(self):
        txs = sum((round_trip(i, f"T{i}", 10, 15 if i % 2 else 9, 1000 + i * 5000) for i in range(8)), [])
        self.assertNotEqual(verdict(analyze(txs, W, 150.0))[0], "bot şüphesi")
    def test_sol_and_wsol_match_same_queue_in_usd(self):
        L = 10**9
        buy = tx("b", 1000, "T", 0, 10**6, quote=None, sol_pre=10 * L, sol_post=9 * L)            # 1 SOL ile al (yerel)
        sell = tx("s", 2000, "T", 10**6, 0, quote=WSOL_MINT, q_pre=0, q_post=2 * L)                 # 2 WSOL'a sat
        m = analyze([buy, sell], W, 100.0)
        self.assertEqual((m["kapanan"], m["eslesmeyen_satis"]), (1, 0))
        self.assertAlmostEqual(m["gerceklesen_usd"], 100.0, delta=0.01)                           # +1 SOL (ücretler hariç küçük fark)
    def test_account_creation_is_counted_not_hidden(self):
        q = 10**6
        created = tx("b", 1000, "T", 0, 1000 * q, q_pre=100 * q, q_post=90 * q, create=True)
        m = analyze([created], W, 150.0)
        self.assertEqual((m["swap"], m["hesap_ac_kapa"]), (0, 1))

class CliTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        with open("cuzdan_tarama.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "durum", "islem_24s", "max_10dk"]); w.writeheader()
            for name, n, peak in [("A", 20, 3), ("B", 30, 5), ("C", 150, 40), ("K", 20, 3)]:
                w.writerow(dict(wallet=name * 32, durum="aday", islem_24s=n, max_10dk=peak))
        with open("kara_liste.txt", "w") as f: f.write("K" * 32 + "\n")
    def tearDown(self): os.chdir(self.cwd)
    def test_end_to_end(self):
        good = sum((round_trip(i, f"T{i}", 10, 15, 1000 + i * 5000) for i in range(8)), [])
        bad = sum((round_trip(i, f"T{i}", 10, 7, 1000 + i * 5000) for i in range(8)), [])
        class C:
            calls = []
            def call(self, m, p):
                self.calls.append(p[0]); opts = p[1]
                assert opts["maxSupportedTransactionVersion"] == 1 and opts["transactionDetails"] == "full"
                src = good if p[0] == "A" * 32 else bad
                return {"data": [dict(t, meta=dict(t["meta"])) for t in src]}
        class Q:
            def quote(self, i, o, a): return dict(in_amount=a, out_amount=150 * 10**6, price_impact_pct=0)
        # testte cüzdan adresi W sabit: fixture'ları her cüzdan için yeniden adresle
        import cuzdan_analiz as mod
        orig = mod.analyze
        mod.analyze = lambda txs, w, p: dict(orig(txs, W, p), wallet=w)
        try:
            c = C()
            with contextlib.redirect_stdout(io.StringIO()) as out: rows = mod.main(client=c, quoter=Q(), sleep=lambda s: None)
        finally:
            mod.analyze = orig
        self.assertEqual(sorted(c.calls), ["A" * 32, "B" * 32])                    # bot (C) ve kara liste (K) hariç
        self.assertEqual({r["wallet"][0]: r["karar"] for r in rows}, {"A": "kopyalanabilir", "B": "zararda"})
        self.assertEqual([l.strip() for l in open("wallets_onerilen.txt") if not l.startswith("#")], ["A" * 32])
        self.assertIn("SOL ≈ 150.00", out.getvalue()); self.assertTrue(os.path.exists("cuzdan_analiz.csv"))
if __name__ == "__main__": unittest.main()
