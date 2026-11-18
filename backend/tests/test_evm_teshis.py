import unittest
import evm_teshis as T
from nexora.evm import TRANSFER

W = "0x" + "c1" * 20; O = "0x" + "d2" * 20


def k(a): return "0x" + "0" * 24 + a[2:]
def log(token, kimden, kime, v): return {"address": token, "topics": [TRANSFER, k(kimden), k(kime)], "data": hex(v)}


class NedenTests(unittest.TestCase):
    def test_siniflar(self):
        A, B = "0x" + "aa" * 20, "0x" + "bb" * 20
        ok = lambda logs: {"status": "0x1", "logs": logs}
        self.assertEqual(T.neden({"from": W}, ok([log(A, W, O, 5), log(B, O, W, 7)]), W, "base")[0], "token→token takas (iki token, karşı varlık yok)")
        self.assertEqual(T.neden({"from": O}, ok([log(A, O, W, 5)]), W, "base")[0], "başkasının gönderdiği gelen token (airdrop/ödül/transfer)")
        self.assertEqual(T.neden({"from": W}, ok([log(A, W, O, 5)]), W, "base")[0], "kendi gönderdiği token (transfer, karşılık yok)")
        self.assertEqual(T.neden({"from": W}, {"status": "0x0"}, W, "base")[0], "başarısız işlem")
        self.assertEqual(T.neden({"from": W}, ok([]), W, "base")[0], "token hareketi yok (makbuzda Transfer olayı yok)")


if __name__ == "__main__":
    unittest.main()


class CozumKarariTests(unittest.TestCase):
    def test_cozulemiyor(self):
        from collections import Counter
        from nexora import evm_analiz as A
        sy = dict(islem=100, cozulemeyen=80, araci=Counter({"0x4857db57aaaa": 70}))
        m = A.cozum_karari(dict(karar="yetersiz veri", gerekce="x"), sy)
        self.assertEqual(m["karar"], "çözülemiyor"); self.assertIn("%80", m["gerekce"]); self.assertIn("0x4857db57", m["gerekce"])
        self.assertEqual(A.cozum_karari(dict(karar="zayıf"), dict(islem=100, cozulemeyen=20))["karar"], "zayıf")
        self.assertEqual(A.cozum_karari(dict(karar="kopyalanabilir"), sy)["karar"], "çözülemiyor")
        self.assertEqual(A.cozum_karari(dict(karar="yetersiz veri"), dict(islem=5, cozulemeyen=5))["karar"], "yetersiz veri")
