import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import sembol as S
from nexora.core import Paper


class SembolTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.eski = os.getcwd(); os.chdir(self.d); S._BELLEK = None; S._DENENDI.clear()
    def tearDown(self): os.chdir(self.eski)

    def test_bul_onbellek_ve_tekrar_deneme(self):
        cagri = []
        def toplu(ms): cagri.append(list(ms)); return {"A": {"symbol": "FLOAT"}}
        self.assertEqual(S.bul(["A", "B"], toplu, now=1000), {"A": "FLOAT"})
        self.assertEqual(S.bul(["A", "B"], toplu, now=1100), {"A": "FLOAT"})     # B 1 saat içinde yeniden denenmez
        self.assertEqual(len(cagri), 1)
        S.bul(["A", "B"], toplu, now=5000); self.assertEqual(cagri[-1], ["B"])  # A kalıcı, B yeniden denenir
        S._BELLEK = None; self.assertEqual(S.bul(["A"], None), {"A": "FLOAT"})   # dosyadan

    def test_hata_bos(self):
        def toplu(ms): raise RuntimeError("ağ")
        r = S.ekle([{"token": "X"}], toplu)
        self.assertEqual(r, [{"token": "X", "sembol": ""}])


class TradesKopyaTests(unittest.TestCase):
    def test_reddedilenler_kopyalari_itmez(self):
        p = Paper(":memory:")
        p._log("e0", "W", "T", "sell", 1, 1, 0, 2.0, "KOPYALANDI", "ok")
        for i in range(60): p._log(f"r{i}", "W", "T", "buy", 0, 0, 0, None, "REDDEDILDI", "x")
        self.assertFalse(any(t["decision"] == "KOPYALANDI" for t in p.trades(50)))
        t = p.trades(50, kopya=100)
        self.assertEqual(len(t), 51); self.assertEqual(t[-1]["decision"], "KOPYALANDI")
        self.assertEqual([x["id"] for x in t], sorted([x["id"] for x in t], reverse=True))


if __name__ == "__main__":
    unittest.main()
