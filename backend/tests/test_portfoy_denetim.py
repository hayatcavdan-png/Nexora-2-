import os, tempfile, unittest
from nexora.core import Paper
import portfoy_denetim as P


class DenetimTests(unittest.TestCase):
    def test_consistent_ledger(self):
        path = os.path.join(tempfile.mkdtemp(), "p.db"); p = Paper(path)
        p.record_buy("b1", "W", "T1", 5.0, 1_000_000, 6); p.record_sell("s1", "W", "T1", 11.9)       # +6.88 gerçekleşen
        p.record_buy("b2", "W", "T2", 5.0, 1_000_000, 6); p.mark_price("T2", 4.0)
        d = P.denetle(path)
        self.assertAlmostEqual(d["nakit_farki"], 0, places=6); self.assertAlmostEqual(d["toplam_farki"], 0, places=6)
        self.assertAlmostEqual(d["gerceklesen"], 11.9 - 0.01 - 5.0, places=6)
        self.assertEqual(d["en_buyuk"][0]["token"], "T1"); self.assertEqual(d["pozisyonlar"][0]["kz"], -1.0)
        self.assertIn("DEFTER TUTARLI", P.metin(d))

    def test_detects_tampered_cash(self):
        path = os.path.join(tempfile.mkdtemp(), "p.db"); p = Paper(path)
        p.record_buy("b1", "W", "T1", 5.0, 1_000_000, 6)
        p._set("cash", 200); p.db.commit()
        self.assertIn("TUTARSIZ", P.metin(P.denetle(path)))


if __name__ == "__main__":
    unittest.main()


class TutarsizTeklifTests(unittest.TestCase):
    def test_negative_roundtrip_rejected_and_flagged(self):
        import sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        from test_decision import FakeQuoter, Safe, TOK
        from nexora.decision import Decider
        p = Paper(); d = Decider(p, FakeQuoter(back_ratio=1.19), Safe())     # geri satış %19 fazla: tutarsız
        r = d.decide("e1", "W", TOK, "buy", 1)
        self.assertEqual(r["decision"], "REDDEDİLDİ"); self.assertIn("teklif tutarsız", r["reason"])
        self.assertEqual(p.shadows()[0]["reason"].split(" (")[0], "teklif tutarsız")
        self.assertEqual(Decider(Paper(), FakeQuoter(back_ratio=0.99), Safe()).decide("e2", "W", TOK, "buy", 1)["decision"], "KOPYALANDI")

    def test_audit_flags_past_suspicious(self):
        path = os.path.join(tempfile.mkdtemp(), "p.db"); p = Paper(path)
        p.record_buy("b1", "W", "T1", 5.0, 1_000_000, 6, note="etki %0.87, al-sat kaybı %-18.9"); p.record_sell("s1", "W", "T1", 11.7)
        p.record_buy("b2", "W", "T2", 5.0, 1_000_000, 6, note="etki %0.1, al-sat kaybı %1.2"); p.record_sell("s2", "W", "T2", 4.0)
        d = P.denetle(path)
        self.assertEqual([x["token"] for x in d["supheli"]], ["T1"]); self.assertAlmostEqual(d["supheli_kz"], 11.7 - 0.01 - 5, places=4)
        self.assertIn("tutarsız teklifle", P.metin(d))
