import os, sqlite3, tempfile, unittest

from nexora.core import Paper, STOP_ESIKLERI
from nexora.rapor import stop_summary, build_report, as_text
import zarar_kesme


def buy(p, ev, token, size=5.0):
    return p.record_buy(ev, "W" * 44, token, size, 1_000_000, 6)      # 1 token, fiyat = size


class ZararKesmeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "p.db")
        self.p = Paper(self.path)

    def rows(self):
        c = self.p.db
        return [dict(r) for r in c.execute("SELECT * FROM pos_iz")], [dict(r) for r in c.execute("SELECT * FROM stop_tetik")]

    def test_buy_opens_full_record(self):
        buy(self.p, "e1", "T1")
        iz, tet = self.rows()
        self.assertEqual(len(iz), 1); self.assertEqual(iz[0]["tam"], 1); self.assertEqual(iz[0]["status"], "open")
        self.assertIsNone(iz[0]["min_pct"]); self.assertEqual(tet, [])

    def test_first_crossing_records_trigger_once(self):
        buy(self.p, "e1", "T1")
        self.p.mark_price("T1", 4.0)        # %-20.2 (ücret dahil): 10 ve 20 tetiklenir
        self.p.mark_price("T1", 3.0)        # %-40.2: 30 tetiklenir; 10/20 ilk değerinde kalır
        iz, tet = self.rows()
        by = {t["esik"]: t["pnl"] for t in tet}
        self.assertEqual(sorted(by), [10, 20, 30])
        self.assertAlmostEqual(by[10], 4.0 - 0.01 - 5.0); self.assertAlmostEqual(by[30], 3.0 - 0.01 - 5.0)
        self.assertEqual(iz[0]["marks"], 2)
        self.assertAlmostEqual(iz[0]["min_pct"], (3.0 - 0.01 - 5.0) / 5 * 100)

    def test_summary_compares_with_actual(self):
        buy(self.p, "e1", "T1"); self.p.mark_price("T1", 4.0); self.p.record_sell("s1", "W" * 44, "T1", 1.0)   # dibe gitti
        buy(self.p, "e2", "T2"); self.p.mark_price("T2", 4.4); self.p.record_sell("s2", "W" * 44, "T2", 7.0)   # toparlandı
        iz, tet = self.rows()
        z = stop_summary(iz, tet)
        self.assertEqual(z["kapanan"], 2)
        self.assertAlmostEqual(z["gercek_kz"], round((1.0 - 0.01 - 5) + (7.0 - 0.01 - 5), 2))
        e10 = next(x for x in z["esikler"] if x["esik"] == 10)
        self.assertEqual((e10["tetiklenen"], e10["korudu"], e10["kacirdi"]), (2, 1, 1))
        self.assertAlmostEqual(e10["stoplu_kz"], round((4.0 - 0.01 - 5) + (4.4 - 0.01 - 5), 2))
        e20 = next(x for x in z["esikler"] if x["esik"] == 20)
        self.assertEqual(e20["tetiklenen"], 1)       # yalnızca T1 (%-20.2)
        self.assertEqual(len(z["esikler"]), len(STOP_ESIKLERI))

    def test_legacy_position_gets_incomplete_record(self):
        self.p.db.execute("INSERT INTO positions(token,qty,cost,last_price,wallet,qty_raw,decimals) VALUES('OLD',1,5,5,'W','1000000',6)")
        self.p.db.commit()
        self.p.mark_price("OLD", 2.0)
        self.p.record_sell("s", "W", "OLD", 2.0)
        iz, _ = self.rows()
        self.assertEqual(len(iz), 1); self.assertEqual(iz[0]["tam"], 0); self.assertEqual(iz[0]["status"], "closed")

    def test_no_behaviour_change(self):
        buy(self.p, "e1", "T1"); cash = self.p.cash()
        self.p.mark_price("T1", 1.0)                 # %-80: tüm eşikler tetiklenir ama pozisyon açık kalır
        self.assertEqual(self.p.cash(), cash)
        self.assertEqual(len(self.p.portfolio()["positions"]), 1)

    def test_reports(self):
        self.assertIn("Henüz ölçüm yok", zarar_kesme.report(self.path))
        buy(self.p, "e1", "T1"); self.p.mark_price("T1", 4.0); self.p.record_sell("s1", "W" * 44, "T1", 1.0)
        txt = zarar_kesme.report(self.path)
        self.assertIn("1 kapanmış", txt); self.assertIn("%10", txt)
        r = build_report(self.path)
        self.assertEqual(r["zarar_kesme"]["kapanan"], 1)
        self.assertIn("Zarar kesme ölçümü", as_text(r))

    def test_old_db_without_tables(self):
        c = sqlite3.connect(os.path.join(self.dir, "old.db"))
        c.execute("CREATE TABLE trades(id INTEGER, ts REAL, event_id TEXT, wallet TEXT, token TEXT, side TEXT, qty REAL, price REAL, fee REAL, pnl REAL, decision TEXT, reason TEXT)")
        c.commit(); c.close()
        self.assertIn("Henüz ölçüm yok", zarar_kesme.report(os.path.join(self.dir, "old.db")))
        self.assertEqual(build_report(os.path.join(self.dir, "old.db"))["zarar_kesme"]["kapanan"], 0)


if __name__ == "__main__":
    unittest.main()
