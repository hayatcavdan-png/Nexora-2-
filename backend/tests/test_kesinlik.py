import os, sqlite3, tempfile, unittest
from nexora.core import Paper
from nexora.live_tracker import LiveTracker, kesinlik_from_db
from nexora.helius_client import HeliusClient
from nexora import panel
from nexora.rapor import build_report, as_text


class FakeClient:
    def __init__(self, statuses): self.statuses, self.calls = statuses, []
    def call(self, method, params):
        self.calls.append((method, params))
        assert method == "getSignatureStatuses" and params[1] == {"searchTransactionHistory": True}
        return {"context": {"slot": 1}, "value": [self.statuses.get(s) for s in params[0]]}


class KesinlikTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.tp = os.path.join(self.d, "t.db")
        self.now = 10_000.0

    def tracker(self, statuses):
        self.client = FakeClient(statuses)
        tr = LiveTracker(self.client, Paper(), self.tp, ["W"], clock=lambda: self.now)
        return tr

    def sig(self, tr, sig, ts, decision="KOPYALANDI", side="BUY"):
        tr.db.execute("""INSERT INTO tracker_signals(ts,wallet,sig,side,token,token_delta,quote,block_time,latency_s,decision,reason,source)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (ts, "W", sig, side, "TOKEN1234567", "1", "SOL", 0, 1.0, decision, "r", "ws"))
        tr.db.commit()

    def test_classification(self):
        tr = self.tracker({"fin": {"confirmationStatus": "finalized", "err": None},
                           "fail": {"confirmationStatus": "finalized", "err": {"InstructionError": [0, "x"]}},
                           "conf": {"confirmationStatus": "confirmed", "err": None}})
        self.sig(tr, "fin", self.now - 60); self.sig(tr, "fail", self.now - 60)
        self.sig(tr, "conf", self.now - 60)                  # henüz finalized değil -> bekler
        self.sig(tr, "gone", self.now - 200)                 # 150 sn sonra hâlâ yok -> düştü
        self.sig(tr, "young", self.now - 60)                 # yok ama süre dolmadı -> bekler
        self.sig(tr, "fresh", self.now - 5)                  # 30 sn dolmadı -> sorulmaz
        r = tr.verify_finality()
        self.assertEqual((r["kesin"], r["hatali"], r["dusuruldu"], r["bekliyor"]), (1, 1, 1, 2))
        self.assertNotIn("fresh", self.client.calls[0][1][0])
        self.assertEqual(sorted(u["sig"] for u in r["uyarilar"]), ["fail", "gone"])
        k = dict(tr.db.execute("SELECT sig, kesinlik FROM tracker_signals").fetchall())
        self.assertEqual((k["fin"], k["fail"], k["gone"], k["conf"], k["fresh"]), ("kesin", "hatali", "dusuruldu", None, None))
        r2 = tr.verify_finality()                            # karara bağlananlar tekrar sorulmaz
        self.assertEqual(set(self.client.calls[1][1][0]), {"conf", "young"})
        self.assertEqual(kesinlik_from_db(tr.db)["kopyalanan_sorunlu"], 2)

    def test_rejected_signals_do_not_warn(self):
        tr = self.tracker({})
        self.sig(tr, "gone", self.now - 200, decision="REDDEDİLDİ")
        self.assertEqual(tr.verify_finality()["uyarilar"], [])

    def test_bad_response_raises_and_keeps_pending(self):
        tr = self.tracker({}); self.sig(tr, "a", self.now - 60)
        tr.client.call = lambda m, p: {"value": []}
        with self.assertRaises(ValueError): tr.verify_finality()
        self.assertIsNone(tr.db.execute("SELECT kesinlik FROM tracker_signals").fetchone()[0])

    def test_events_and_report(self):
        tr = self.tracker({}); self.sig(tr, "gone", self.now - 200); tr.verify_finality()
        pp = os.path.join(self.d, "p.db"); Paper(pp)
        ev = panel.olaylar(pp, self.tp, son=0, now=self.now)["olaylar"]
        self.assertEqual([e["baslik"] for e in ev], ["Kopyalanan sinyal kesinleşmedi: TOKE…4567"])
        self.assertEqual(panel.olaylar(pp, self.tp, son=self.now, now=self.now)["olaylar"], [])
        r = build_report(pp, self.tp)
        self.assertEqual(r["kesinlik"]["dusuruldu"], 1)
        self.assertIn("Zincir kesinliği", as_text(r))

    def test_old_db_migrates(self):
        c = sqlite3.connect(self.tp)
        c.execute("""CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, wallet TEXT, sig TEXT, side TEXT,
            token TEXT, token_delta TEXT, quote TEXT, block_time INTEGER, latency_s REAL, decision TEXT, reason TEXT)""")
        c.commit(); c.close()
        self.assertEqual(kesinlik_from_db(sqlite3.connect(self.tp)), {})
        tr = self.tracker({})
        self.assertIn("kesinlik", {r[1] for r in tr.db.execute("PRAGMA table_info(tracker_signals)")})

    def test_method_whitelisted(self):
        self.assertIn("getSignatureStatuses", HeliusClient.READ_ONLY_METHODS)


if __name__ == "__main__":
    unittest.main()
