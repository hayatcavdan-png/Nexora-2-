import os, sqlite3, tempfile, unittest


class WalTest(unittest.TestCase):
    def test_wal_kalici_ve_okuyucu_yazicilari_bloke_etmez(self):
        from nexora.etiket import Etiketci
        d = tempfile.mkdtemp(); yol = os.path.join(d, "e.db")
        e = Etiketci(yol, quoter=lambda *a, **k: None)
        self.assertEqual(e.db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        # WAL ile yazıcı açıkken ayrı bir bağlantı okuyabilmeli
        e.db.execute("CREATE TABLE IF NOT EXISTS t(x)"); e.db.execute("INSERT INTO t VALUES(1)"); e.db.commit()
        r = sqlite3.connect(yol, timeout=1)
        self.assertEqual(r.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        r.close(); e.db.close()


if __name__ == "__main__":
    unittest.main()
