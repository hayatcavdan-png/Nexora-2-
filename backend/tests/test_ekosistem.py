import os, sqlite3, tempfile, unittest
from nexora import ekosistem as E
from nexora.core import Paper, SEMA_SURUMU
from nexora.live_tracker import LiveTracker

SOL = "7sygH3NxKWnWyVXVbYeLuuKjgfDLSZUSyLGT9TuCoaaa"
EVM = "0x" + "a1" * 20
TON = "EQ" + "A" * 46


class Test(unittest.TestCase):
    def test_tespit(self):
        self.assertEqual((E.tespit(SOL), E.tespit(EVM), E.tespit(TON)), ("solana", "evm", "ton"))
        self.assertIsNone(E.tespit("0x123")); self.assertIsNone(E.tespit(None)); self.assertIsNone(E.tespit("merhaba dunya"))
        self.assertEqual(E.bul("bnb")["zincir_id"], 56); self.assertEqual(E.bul("base")["zincir_id"], 8453); self.assertIsNone(E.bul("yok"))

    def test_cuzdan_dosyalari(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "wallets.txt"), "w").write(f"# yorum\n{SOL}\n{EVM}\n")
        open(os.path.join(d, "wallets_bnb.txt"), "w").write(f"{EVM}\n{SOL}\n")
        self.assertEqual(E.cuzdanlar("solana", d), [SOL]); self.assertEqual(E.cuzdanlar("bnb", d), [EVM])   # yanlış biçim atlanır
        self.assertEqual(E.cuzdanlar("base", d), []); self.assertEqual(E.cuzdanlar("borsa", d), [])

    def test_eski_veritabani_gecisi(self):
        yol = os.path.join(tempfile.mkdtemp(), "p.db")
        c = sqlite3.connect(yol)
        c.executescript("""CREATE TABLE trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, event_id TEXT UNIQUE, wallet TEXT, token TEXT,
                           side TEXT, qty REAL, price REAL, fee REAL, pnl REAL, decision TEXT, reason TEXT);
                           CREATE TABLE positions(token TEXT PRIMARY KEY, qty REAL, cost REAL, last_price REAL, wallet TEXT);
                           CREATE TABLE state(k TEXT PRIMARY KEY, v TEXT);""")
        c.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(1,'e','W','T','sell',1,1,0,2.5,'KOPYALANDI','ok')")
        c.execute("INSERT INTO positions VALUES('T2',1,5,1,'W')"); c.commit(); c.close()
        p = Paper(yol)
        self.assertEqual(p.trades()[0]["ekosistem"], "solana")                          # eski kayıt korunur, etiketlenir
        self.assertEqual(p._get("sema_surumu"), str(SEMA_SURUMU))
        oz = {x["id"]: x for x in E.ozet([yol])}
        self.assertEqual((oz["solana"]["kapanan"], oz["solana"]["kz"], oz["solana"]["acik"]), (1, 2.5, 1))

    def test_portfoy_etiketi_ve_ozet(self):
        d = tempfile.mkdtemp(); a, b = os.path.join(d, "a.db"), os.path.join(d, "b.db")
        p1, p2 = Paper(a), Paper(b, ekosistem="borsa")
        p1.handle_signal("e1", "W", "T", "buy", 1.0, 1e6, 1)
        p2.handle_signal("e1", "S", "X", "buy", 1.0, 1e6, 1); p2.handle_signal("e2", "S", "X", "sell", 1.2, 1e6, 1)
        self.assertEqual(p2.trades()[0]["ekosistem"], "borsa")
        self.assertEqual(p1.portfolio()["positions"][0]["ekosistem"], "solana")
        oz = {x["id"]: x for x in E.ozet([a, b, os.path.join(d, "yok.db")])}
        self.assertEqual((oz["solana"]["kopya"], oz["solana"]["acik"]), (1, 1))
        self.assertEqual((oz["borsa"]["kopya"], oz["borsa"]["kapanan"], oz["borsa"]["acik"]), (1, 1, 0)); self.assertGreater(oz["borsa"]["kz"], 0)
        self.assertEqual((oz["bnb"]["aktif"], oz["bnb"]["kopya"], oz["base"]["aktif"]), (True, 0, False))

    def test_takip_tablosu(self):
        tr = LiveTracker(None, Paper(), ":memory:", [SOL])
        self.assertIn("ekosistem", {r[1] for r in tr.db.execute("PRAGMA table_info(tracker_signals)")})


if __name__ == "__main__":
    unittest.main()
