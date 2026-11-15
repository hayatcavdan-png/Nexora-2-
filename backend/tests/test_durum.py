import os, sqlite3, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nexora.core import Paper, SemaHatasi, SEMA_SURUMU
from nexora import durum as D
from nexora.decision import Decider
from nexora.constants import USDC_MINT
from nexora import panel
from test_decision import FakeQuoter, Safe, TOK


class DurumMakinesiTests(unittest.TestCase):
    def test_transition_table(self):
        D.dogrula(None, D.ACIK); D.dogrula(D.ACIK, D.KAPANIYOR); D.dogrula(D.KAPANIYOR, D.KAPANDI)
        for e, y in [(D.KAPANDI, D.ACIK), (D.KAPANDI, D.KAPANIYOR), (None, D.KAPANDI), (D.ACIK, D.KAPANDI), (D.ACIK, D.ACIK)]:
            with self.assertRaises(D.GecersizGecis): D.dogrula(e, y)

    def test_buy_sell_lifecycle(self):
        p = Paper(); d = Decider(p, FakeQuoter(), Safe())
        d.decide("b", "W", TOK, "buy", 1)
        self.assertEqual(p.durum(TOK), D.ACIK)
        self.assertEqual(p.portfolio()["positions"][0]["durum"], D.ACIK)
        d.decide("s", "W", TOK, "sell", 1)
        self.assertIsNone(p.durum(TOK))
        g = [(x["eski"], x["yeni"]) for x in reversed(p.durum_gecmisi())]
        self.assertEqual(g, [(None, D.ACIK), (D.ACIK, D.KAPANIYOR), (D.KAPANIYOR, D.KAPANDI)])
        self.assertEqual(p.db.execute("SELECT durum FROM pos_iz").fetchone()[0], D.KAPANDI)

    def test_sell_quote_failure_marks_stuck_then_recovers(self):
        p = Paper(); q = FakeQuoter(); d = Decider(p, q, Safe())
        d.decide("b", "W", TOK, "buy", 1)
        q.fail = {(TOK, USDC_MINT)}
        r = d.decide("s1", "W", TOK, "sell", 1)
        self.assertEqual(r["decision"], "REDDEDİLDİ"); self.assertEqual(p.durum(TOK), D.TAKILDI)
        q.fail = set(); d.mark_to_market()
        self.assertEqual(p.durum(TOK), D.ACIK)
        self.assertEqual(d.decide("s2", "W", TOK, "sell", 1)["decision"], "KOPYALANDI")
        self.assertIsNone(p.durum(TOK))

    def test_repeated_mark_failures_mark_stuck(self):
        p = Paper(); q = FakeQuoter(); d = Decider(p, q, Safe())
        d.decide("b", "W", TOK, "buy", 1)
        q.fail = {(TOK, USDC_MINT)}
        for _ in range(D.TAKILMA_ESIGI - 1): d.mark_to_market()
        self.assertEqual(p.durum(TOK), D.ACIK)
        d.mark_to_market(); self.assertEqual(p.durum(TOK), D.TAKILDI)

    def test_history_immutable_and_event(self):
        dd = tempfile.mkdtemp(); pp = os.path.join(dd, "p.db")
        p = Paper(pp); q = FakeQuoter(fail={(TOK, USDC_MINT)}); d = Decider(p, q, Safe())
        q.fail = set(); d.decide("b", "W", TOK, "buy", 1); q.fail = {(TOK, USDC_MINT)}
        d.decide("s", "W", TOK, "sell", 1)
        with self.assertRaises(sqlite3.DatabaseError): p.db.execute("DELETE FROM durum_gecis")
        ev = panel.olaylar(pp, None, son=0)["olaylar"]
        self.assertIn("Pozisyon satılamıyor: MEME…1111", [e["baslik"] for e in ev])

    def test_legacy_open_position(self):
        p = Paper()
        p.db.execute("INSERT INTO positions(token,qty,cost,last_price,wallet,qty_raw,decimals) VALUES('OLD',1,5,5,'W','1000000',6)")
        p.db.commit()
        self.assertEqual(p.durum("OLD"), D.ACIK)
        p.record_sell("s", "W", "OLD", 4.0)
        self.assertEqual([x["yeni"] for x in reversed(p.durum_gecmisi())], [D.ACIK, D.KAPANIYOR, D.KAPANDI])

    def test_newer_schema_refused(self):
        path = os.path.join(tempfile.mkdtemp(), "p.db")
        p = Paper(path); p._set("sema_surumu", SEMA_SURUMU + 1); p.db.commit(); p.db.close()
        with self.assertRaises(SemaHatasi): Paper(path)
        c = sqlite3.connect(path); c.execute("UPDATE state SET v=? WHERE k='sema_surumu'", (SEMA_SURUMU,)); c.commit(); c.close()
        Paper(path)                                         # aynı sürüm açılır


if __name__ == "__main__":
    unittest.main()
