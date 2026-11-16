import unittest
from nexora.evm import EvmHatasi, gezgin_islemleri
from nexora.evm_kesif import _loglar
from nexora import evm_analiz as A

W = "0x" + "c1" * 20


class R:
    def __init__(self, b, kod=200): self.b, self.status_code = b, kod
    def json(self): return self.b


class Gezgin:
    """İki sayfa: yeni sürüm alan adları (transaction_hash) ve eski sürüm (tx_hash, block)."""
    def __init__(self, sayfalar): self.sayfalar, self.istekler = sayfalar, []
    def get(self, url, params=None, timeout=None):
        self.istekler.append(dict(params or {}))
        i = 1 if (params or {}).get("block_number") else 0
        return R(self.sayfalar[i]) if i < len(self.sayfalar) else R(None, 500)


class GezginTest(unittest.TestCase):
    def test_sayfalama_ve_alan_adlari(self):
        g = Gezgin([
            {"items": [{"block_number": 120, "transaction_hash": "0xa"}, {"block_number": 115, "transaction_hash": "0xa"}],
             "next_page_params": {"block_number": 115, "index": 3, "bos": None}},
            {"items": [{"block": "110", "tx_hash": "0xb"}, {"block_number": 90, "transaction_hash": "0xeski"}],
             "next_page_params": {"block_number": 90, "index": 1}},
        ])
        out = gezgin_islemleri(g, "base", W, 100)
        self.assertEqual(out, {"0xa": 120, "0xb": 110})
        self.assertEqual(len(g.istekler), 2)                       # eski bloğa inince durur
        self.assertEqual(g.istekler[1], {"type": "ERC-20", "block_number": 115, "index": 3})

    def test_yanit_yoksa_none_gezgin_yoksa_none(self):
        self.assertIsNone(gezgin_islemleri(Gezgin([]), "base", W, 0))
        self.assertIsNone(gezgin_islemleri(Gezgin([]), "bnb", W, 0))


class Rpc:
    def __init__(self, sinir): self.sinir, self.cagri = sinir, []
    def call(self, m, p):
        a, b = int(p[0]["fromBlock"], 16), int(p[0]["toBlock"], 16)
        self.cagri.append((a, b))
        if b - a + 1 > self.sinir:
            raise EvmHatasi("RPC: Under the Free tier plan, you can make eth_getLogs requests with up to a 10 block range. Based on your parameters")
        return [{"b": x} for x in range(a, b + 1)]


class BlokAraligiTest(unittest.TestCase):
    def test_izin_verilen_boyutta_bolunur(self):
        r = Rpc(10)
        out = _loglar(r, {}, 100, 134)
        self.assertEqual([x["b"] for x in out], list(range(100, 135)))
        self.assertEqual(r.cagri[1:], [(100, 109), (110, 119), (120, 129), (130, 134)])

    def test_hiz_siniri_bolunmez(self):
        class H:
            def call(self, m, p): raise EvmHatasi("RPC hız sınırı (düğüm anahtarı gerekebilir) 10 block range")
        with self.assertRaises(EvmHatasi): _loglar(H(), {}, 0, 1000)


class SwaplarGezginTest(unittest.TestCase):
    def test_gezgin_varsa_loglara_gidilmez(self):
        class Rp:
            def call(self, m, p):
                if m == "eth_getLogs": raise AssertionError("log sorgusu yapılmamalı")
                return {}
        sy = {}
        A.swaplar(Rp(), W, "base", 0, 10, sayac=sy, gezgin=lambda w, b: {"0x1": 5, "0x2": 6})
        self.assertEqual(sy["islem"], 2)


if __name__ == "__main__":
    unittest.main()
