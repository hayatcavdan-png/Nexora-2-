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
