"""24.11: sunucu çok iş parçacıklı; Paper ve Uyelik tek bağlantıyı paylaşıyor. Eşzamanlı okuma/yazma
'bad parameter or other API misuse' ya da float(None) hatası vermemeli."""
import os, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nexora.core import Paper
from nexora.uyelik import Uyelik


def _calistir(isler):
    hatalar = []
    def sar(f):
        def g():
            try: f()
            except Exception as e: hatalar.append(repr(e))
        return g
    ts = [threading.Thread(target=sar(f)) for f in isler]
    [t.start() for t in ts]; [t.join() for t in ts]
    return hatalar


class EszamanliTest(unittest.TestCase):
    def test_paper_eszamanli_okuma_yazma(self):
        p = Paper(os.path.join(tempfile.mkdtemp(), "t.db"))
        for i in range(200):
            p._log(f"e{i}", "W", "T", "buy", 1, 1, 0, 0, "REDDEDILDI", "x")
        def oku():
            for _ in range(150):
                p.cash(); p.killed(); p.portfolio(); p.trades(50, kopya=100); p.ayarlar(); p.son_nabiz()
        def yaz():
            for _ in range(200): p.nabiz(); p.set_kill(False)
        self.assertEqual(_calistir([oku] * 8 + [yaz] * 2), [])
        self.assertEqual(len(p.trades(50, kopya=100)), 50)

    def test_uyelik_eszamanli_okuma(self):
        u = Uyelik(os.path.join(tempfile.mkdtemp(), "u.db"))
        def oku():
            for _ in range(300): u.uye("gecersiz-oturum")
        self.assertEqual(_calistir([oku] * 8), [])

    def test_sonuc_imlec_gibi(self):
        p = Paper()
        cur = p.db.execute("INSERT INTO state VALUES(?,?)", ("deneme", "1"))
        self.assertEqual(cur.rowcount, 1)
        self.assertIsNone(cur.fetchone())
        r = p.db.execute("SELECT v FROM state WHERE k=?", ("deneme",))
        self.assertEqual(r.fetchone()["v"], "1"); self.assertIsNone(r.fetchone())
        self.assertEqual([x["k"] for x in p.db.execute("SELECT k FROM state WHERE k='deneme'")], ["deneme"])


if __name__ == "__main__":
    unittest.main()
