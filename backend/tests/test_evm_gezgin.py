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
    def get(self, url, params=None, timeout=None, headers=None):
        if 'routescan' in url: return R(None, 503)
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


class Routescan:
    def get(self, url, params=None, timeout=None, headers=None):
        if "blockscout" in url: return R({"message": "Forbidden"}, 403)
        return R({"status": "1", "message": "OK", "result": [
            {"blockNumber": "130", "hash": "0xr1"}, {"blockNumber": "120", "hash": "0xr1"}, {"blockNumber": "50", "hash": "0xeski"}]})


class YedekGezginTest(unittest.TestCase):
    def test_blockscout_reddederse_routescan(self):
        tani = {}
        self.assertEqual(gezgin_islemleri(Routescan(), "base", W, 100, tani=tani), {"0xr1": 130})
        self.assertEqual(tani, {"blockscout": "HTTP 403", "routescan": "tamam"})

    def test_bilinmeyen_adres_bos_gecmis(self):
        class G:
            def get(self, url, params=None, timeout=None, headers=None): return R({"message": "Not found"}, 404)
        self.assertEqual(gezgin_islemleri(G(), "base", W, 0), {})


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

    def test_cok_dar_sinirda_kota_korunur(self):
        r = Rpc(10)
        with self.assertRaises(EvmHatasi): _loglar(r, {}, 0, 43_200)        # 24 saat Base = 4320 parça: yapılmaz
        self.assertEqual(len(r.cagri), 1)

    def test_aktiflik_gezginle(self):
        from nexora.evm_kesif import aktiflik
        class Rp:
            def call(self, m, p): raise AssertionError("düğüm sorgusu yapılmamalı")
        self.assertEqual(aktiflik(Rp(), W, 1000, 100, gezgin=lambda w, b: {"0x1": 950, "0x2": 960}), 2)
        with self.assertRaises(EvmHatasi): aktiflik(Rp(), W, 1000, 100, gezgin=lambda w, b: None)

    def test_hiz_siniri_bolunmez(self):
        class H:
            def call(self, m, p): raise EvmHatasi("RPC hız sınırı (düğüm anahtarı gerekebilir) 10 block range")
        with self.assertRaises(EvmHatasi): _loglar(H(), {}, 0, 1000)


class V4HavuzTest(unittest.TestCase):
    def test_32_bayt_havuz_kimligi_adres_filtresine_konmaz(self):
        from nexora.evm_kesif import erken_alicilar
        from nexora.evm import TRANSFER, _konu
        A1 = "0x" + "e1" * 20
        class Rp:
            def call(self, m, p):
                f = p[0]
                if len(f["topics"]) > 1: raise EvmHatasi("RPC: Invalid params")
                return [{"topics": [TRANSFER, _konu("0x" + "f0" * 20), _konu(A1)]}]
        self.assertEqual(erken_alicilar(Rp(), "0x" + "aa" * 20, "0x" + "bb" * 32, 100, pencere_blok=10, parca=10), {A1})


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


class ZamanAsimiTest(unittest.TestCase):
    def test_blockscout_bir_kez_yeniden_dener(self):
        import requests
        class G:
            n = 0
            def get(self, url, params=None, timeout=None, headers=None):
                G.n += 1
                if G.n == 1: raise requests.Timeout("yavaş")
                return R({"items": [{"block_number": 120, "transaction_hash": "0xa"}], "next_page_params": None})
        self.assertEqual(gezgin_islemleri(G(), "base", W, 100), {"0xa": 120})
