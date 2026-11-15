import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nexora.core import Paper
from nexora.live_tracker import LiveTracker, QUARANTINE_AFTER
from nexora.constants import USDC_MINT
JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

def swap_tx(sig, W, t=1000):
    def bal(m, a): return dict(accountIndex=1, mint=m, owner=W, uiTokenAmount=dict(amount=str(a), decimals=6))
    return dict(slot=1, blockTime=t, transaction=dict(signatures=[sig], message=dict(accountKeys=[W, "x"], instructions=[dict(programId=JUP)])),
        meta=dict(err=None, fee=5000, logMessages=[f"Program {JUP} invoke [1]"], preBalances=[10**9, 0], postBalances=[10**9 - 5000, 0],
                  preTokenBalances=[bal("TOK", 0), bal(USDC_MINT, 50)], postTokenBalances=[bal("TOK", 100), bal(USDC_MINT, 40)]))

class FakeClient:
    def __init__(self): self.sigs, self.txs, self.fail = {}, {}, set()
    def call(self, method, params):
        if method == "getSignaturesForAddress":
            w = params[0]
            if w in self.fail: raise RuntimeError("API hatası")
            until, out = params[1].get("until"), []
            for s in self.sigs.get(w, []):            # yeniden eskiye
                if s == until: break
                out.append({"signature": s, "err": None})
            return out
        return self.txs.get(params[0])

class T(unittest.TestCase):
    def setUp(self):
        self.c, self.p = FakeClient(), Paper()
        self.tr = LiveTracker(self.c, self.p, ":memory:", ["A", "B"], clock=lambda: 1005)
    def test_first_run_skips_history_then_detects_new(self):
        self.c.sigs["A"] = ["old"]; self.c.txs["old"] = swap_tx("old", "A")
        self.assertEqual(self.tr.poll_all()["A"], 0)                  # geçmiş işlenmez
        self.c.sigs["A"] = ["new", "old"]; self.c.txs["new"] = swap_tx("new", "A")
        self.assertEqual(self.tr.poll_all()["A"], 1)
        s = self.tr.signals()[0]
        self.assertEqual((s["side"], s["decision"]), ("BUY", "REDDEDİLDİ"))   # bilinmeyen likidite -> engel
        self.assertIn("likidite", s["reason"]); self.assertAlmostEqual(s["latency_s"], 5)
        self.assertEqual(self.p.cash(), 100.0)                        # sanal sermaye harcanmadı
    def test_no_double_processing(self):
        self.c.sigs["A"] = ["o"]; self.tr.poll_all()
        self.c.sigs["A"] = ["n", "o"]; self.c.txs["n"] = swap_tx("n", "A")
        self.tr.poll_all(); self.assertEqual(self.tr.poll_all()["A"], 0)
        self.assertEqual(len(self.tr.signals()), 1)
    def test_failing_wallet_isolated_and_quarantined(self):
        self.c.fail.add("A"); self.c.sigs["B"] = ["o"]; self.tr.poll_all()
        self.c.sigs["B"] = ["n", "o"]; self.c.txs["n"] = swap_tx("n", "B")
        rep = self.tr.poll_all()
        self.assertEqual(rep["A"], "hata"); self.assertEqual(rep["B"], 1)    # B etkilenmedi
        for _ in range(QUARANTINE_AFTER): self.tr.poll_all()
        st = {s["wallet"]: s for s in self.tr.status()}
        self.assertEqual(st["A"]["quarantined"], 1); self.assertEqual(st["B"]["quarantined"], 0)
        self.assertNotIn("A", self.tr.poll_all())
    def test_restart_resumes_from_checkpoint(self):
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        tr1 = LiveTracker(self.c, self.p, db, ["A"], clock=lambda: 1005)
        self.c.sigs["A"] = ["o"]; tr1.poll_all()
        self.c.sigs["A"] = ["n", "o"]; self.c.txs["n"] = swap_tx("n", "A")
        tr2 = LiveTracker(self.c, self.p, db, ["A"], clock=lambda: 1005)    # yeniden başlatma
        self.assertEqual(tr2.poll_all()["A"], 1)
if __name__ == "__main__": unittest.main()


class EtiketKancaTests(unittest.TestCase):
    def test_every_signal_forwarded_and_errors_ignored(self):
        from unittest.mock import Mock
        c, p, et = FakeClient(), Paper(), Mock()
        tr = LiveTracker(c, p, ":memory:", ["A"], clock=lambda: 1005, etiketci=et)
        c.sigs["A"] = ["o"]; tr.poll_all()
        c.sigs["A"] = ["n", "o"]; c.txs["n"] = swap_tx("n", "A"); tr.poll_all()
        args = et.sinyal.call_args.args
        self.assertEqual(args[:5], ("A:n", "A", "TOK", "buy", "n")); self.assertEqual(args[7], "REDDEDİLDİ")
        et.sinyal.side_effect = RuntimeError("bozuk")                    # ölçüm hatası takibi durdurmaz
        c.sigs["A"] = ["m", "n", "o"]; c.txs["m"] = swap_tx("m", "A"); self.assertEqual(tr.poll_all()["A"], 1)
