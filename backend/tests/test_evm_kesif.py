import unittest
from nexora import evm_kesif as K
from nexora.evm import TRANSFER, _konu

TOK1, TOK2, ESKI = "0x" + "a1" * 20, "0x" + "a2" * 20, "0x" + "a3" * 20
GTT, GTP = "0x" + "a4" * 20, "0x" + "b4" * 20
P1, P2 = "0x" + "b1" * 20, "0x" + "b2" * 20
U1, U2, KONTRAT = "0x" + "c1" * 20, "0x" + "c2" * 20, "0x" + "dd" * 20
NOW = 2_000_000_000.0


class R:
    def __init__(self, b): self.b = b
    def json(self): return self.b


class DS:
    def get(self, url, timeout=None):
        if "geckoterminal" in url:
            if "trending" not in url: return R({"data": []})
            return R({"data": [dict(attributes=dict(address=GTP, reserve_in_usd="70000", volume_usd=dict(h24="300000"),
                                                    pool_created_at="2033-05-18T02:33:20Z"),
                                    relationships=dict(base_token=dict(data=dict(id="bsc_" + GTT))))]})
        if "token-boosts/top" in url:
            return R([dict(chainId="bsc", tokenAddress=TOK1), dict(chainId="solana", tokenAddress="X"), dict(chainId="bsc", tokenAddress=ESKI)])
        if "token-profiles" in url: return R([dict(chainId="bsc", tokenAddress=TOK2)])
        if "token-boosts/latest" in url: return R(None)
        cift = lambda tok, p, lik, hacim, yas: dict(baseToken=dict(address=tok), pairAddress=p, liquidity=dict(usd=lik),
                                                     volume=dict(h24=hacim), pairCreatedAt=(NOW - yas) * 1000)
        return R([cift(TOK1, P1, 90000, 5e5, 3600), cift(TOK1, "0x" + "99" * 20, 100, 9e9, 60), cift(TOK2, P2, 60000, 2e5, 7200),
                  cift(ESKI, "0x" + "98" * 20, 9e5, 9e6, 30 * 86400)])


class Rpc:
    def blok(self): return 10_000
    def blok_zamani(self, n): return NOW - (10_000 - n) * 1.0           # 1 sn/blok
    def call(self, y, p):
        if y == "eth_getCode": return "0x6080" if p[0] == KONTRAT else "0x"
        f = p[0]; cift = "0x" + f["topics"][1][-40:]
        alici = {P1: [U1, U2, KONTRAT, P1], P2: [U1, KONTRAT]}.get(cift, [])
        return [dict(topics=[TRANSFER, f["topics"][1], _konu(a)]) for a in alici] if f["fromBlock"] == hex(int(f["fromBlock"], 16)) and int(f["fromBlock"], 16) < 9000 else []


class Test(unittest.TestCase):
    def test_sicak_tokenler(self):
        t = K.sicak_tokenler(DS(), "bnb", now=NOW, uyku=lambda x: None)
        self.assertEqual([(x[0], x[1]) for x in t], [(TOK1, P1), (GTT, GTP), (TOK2, P2)])   # GeckoTerminal de kaynak; eski çift elenir
        self.assertEqual(K.sicak_tokenler(DS(), "bnb", min_likidite=80000, now=NOW, uyku=lambda x: None)[0][0], TOK1)

    def test_limit_bolme(self):
        from nexora.evm import EvmHatasi
        class L:
            def __init__(self): self.n = 0
            def call(self, y, p):
                self.n += 1; f = p[0]
                if int(f["toBlock"], 16) - int(f["fromBlock"], 16) > 100: raise EvmHatasi("RPC: limit exceeded")
                return [dict(topics=[TRANSFER, _konu(P1), _konu(U1)])]
        r = L(); self.assertEqual(len(K._loglar(r, {}, 0, 399)), 4); self.assertGreater(r.n, 4)
        class B:
            def call(self, y, p): raise EvmHatasi("RPC: execution reverted")
        with self.assertRaises(EvmHatasi): K._loglar(B(), {}, 0, 399)                          # başka hata bölünmez

    def test_blok_bul(self):
        self.assertEqual(K.blok_bul(Rpc(), NOW - 3600), 10_000 - 3600)

    def test_kesif(self):
        tok = K.sicak_tokenler(DS(), "bnb", now=NOW, uyku=lambda x: None)
        adaylar, say = K.kesfet(Rpc(), tok, en_az=2, pencere_blok=1600, log=lambda m: None)
        self.assertEqual(adaylar, [U1])                                                    # iki token'ı da erken alan tek kullanıcı
        self.assertEqual((say[U2], say[KONTRAT]), (1, 2))                                   # sözleşme sayılır ama aday olmaz
        self.assertEqual(K.kesfet(Rpc(), tok, en_az=2, bilinen=[U1.upper().replace("0X", "0x")], pencere_blok=1600, log=lambda m: None)[0], [])


if __name__ == "__main__":
    unittest.main()
