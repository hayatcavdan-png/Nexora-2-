import unittest
from nexora import evm as E, evm_analiz as A, evm_kesif as K

W = "0x" + "11" * 20; R = "0x" + "22" * 20
Z = E.ZINCIRLER["bnb"]; USDT = Z["usd"]
T1, T2 = "0x" + "a1" * 20, "0x" + "a2" * 20


def tr(tok, frm, to, v, blok, karma):
    return dict(address=tok, topics=[E.TRANSFER, E._konu(frm), E._konu(to)], data=hex(v), blockNumber=hex(blok), transactionHash=karma)


class Rpc:
    """Her işlem: (blok, [transferler]). Al: USDT öde, token al. Sat: token ver, USDT al."""
    def __init__(self, islemler): self.isl = islemler
    def ondalik(self, t): return 18
    def call(self, y, p):
        if y == "eth_getLogs":
            f = p[0]; k = f["topics"]; bas, son = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            out = []
            for karma, (blok, tl) in self.isl.items():
                if not bas <= blok <= son: continue
                for t in tl:
                    if (len(k) == 3 and t["topics"][2] == k[2]) or (len(k) == 2 and t["topics"][1] == k[1]): out.append(t)
            return out
        karma = p[0]
        if y == "eth_getTransactionByHash": return {"from": W, "value": "0x0"}
        return dict(status="0x1", logs=self.isl[karma][1])


def al(karma, blok, tok, usd, adet):
    return karma, (blok, [tr(USDT, W, R, int(usd * 1e18), blok, karma), tr(tok, R, W, adet, blok, karma)])


def sat(karma, blok, tok, usd, adet):
    return karma, (blok, [tr(tok, W, R, adet, blok, karma), tr(USDT, R, W, int(usd * 1e18), blok, karma)])


class Test(unittest.TestCase):
    def test_swaplar_ve_analiz(self):
        isl = dict([al("0x1", 100, T1, 10, 1000), sat("0x2", 200, T1, 15, 1000),          # +5
                    al("0x3", 300, T2, 10, 500), sat("0x4", 900, T2, 8, 250), sat("0x5", 950, T2, 9, 250),   # maliyet 5+5: +3 ve +4
                    sat("0x6", 990, "0x" + "a3" * 20, 3, 5)])                               # alışı pencerede yok
        isl["0x7"] = (500, [tr(USDT, W, R, 10**18, 500, "0x7")])                           # yalnızca USDT transferi: swap değil
        rpc = Rpc(isl)
        sy = {}
        sw = A.swaplar(rpc, W, "bnb", 0, 1000, sayac=sy)
        self.assertEqual(sy, dict(islem=6, cozulemeyen=0))                                  # yalnızca USDT hareketi işlem sayılmaz
        self.assertEqual([(s["yon"], s["blok"]) for s in sw], [("buy", 100), ("sell", 200), ("buy", 300), ("sell", 900), ("sell", 950), ("sell", 990)])
        m = A.analiz(sw, rpc, "bnb", 600.0, W)
        self.assertEqual((m["kapanan"], m["satis"], m["eslesmeyen_satis"]), (3, 4, 1))
        self.assertAlmostEqual(m["gerceklesen_usd"], 12.0, places=2)
        self.assertEqual(m["kazanma_orani"], 1.0); self.assertEqual(m["kar_faktoru"], 99.0)
        self.assertEqual(m["medyan_tutma_sn"], 450)                                         # tutmalar 75, 450, 487 sn (blok × 0.75)
        self.assertEqual(m["karar"], "yetersiz veri")                                       # 5'ten az kapanan: Solana ile aynı kural

    def test_kopyalanabilir_ve_yerel(self):
        isl = {}
        for i in range(8):
            isl.update(dict([al(f"0xa{i}", 100 + i * 200, f"0x{i:02d}" + "b" * 38, 10, 100), sat(f"0xb{i}", 200 + i * 200, f"0x{i:02d}" + "b" * 38, 13 if i % 4 else 9, 100)]))
        rpc = Rpc(isl); m = A.analiz(A.swaplar(rpc, W, "bnb", 0, 5000), rpc, "bnb", 600.0, W)
        self.assertEqual((m["kapanan"], m["karar"]), (8, "kopyalanabilir")); self.assertGreater(m["skor"], 0)
        self.assertAlmostEqual(A.usd(rpc, "bnb", E.YEREL, 2 * 10**17, 600.0), 120.0)          # 0.2 BNB × 600 $

    def test_aday_secimi(self):
        class C:
            def call(self, y, p): return "0x60" if p[0] == "0xk" else "0x"
        g = [["0xa", "0xb", "0xk", "0x0000bot"], ["0xa", "0xc"], ["0xd"]]
        from collections import Counter
        say = Counter(w for x in g for w in x)
        s = K.analiz_adaylari(C(), g, say, bilinen=["0xc"], en_fazla=4)
        self.assertEqual(s[0], "0xa"); self.assertEqual(set(s), {"0xa", "0xb", "0xd"})   # çoklu önce; sözleşme, bot adresi, bilinen yok
        self.assertTrue(K.bot_adresi_mi("0x0000a1b2" + "c" * 32)); self.assertFalse(K.bot_adresi_mi("0x00a1" + "c" * 36))

    def test_aktiflik(self):
        isl = dict([al("0x1", 900, T1, 10, 1), sat("0x2", 950, T1, 12, 1)])
        self.assertEqual(K.aktiflik(Rpc(isl), W, 1000, 200), 2); self.assertEqual(K.aktiflik(Rpc(isl), W, 1000, 30), 0)


if __name__ == "__main__":
    unittest.main()
