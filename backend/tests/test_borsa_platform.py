import io, json, os, tempfile, unittest
from contextlib import redirect_stdout
from nexora import borsa_liste as L
from nexora.borsa_motor import BorsaFiyat, BorsaMotoru, FiyatHatasi
from nexora.core import Paper

BONK, WIF = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"


class R:
    def __init__(self, body, code=200): self.status_code, self.b = code, body
    def json(self): return self.b


class Gecko:
    def __init__(self): self.n = 0
    def get(self, url, params=None, timeout=None):
        self.n += 1
        if url.endswith("/coins/list"):
            return R([{"id": "bonk", "symbol": "bonk", "platforms": {"solana": BONK}},
                      {"id": "dogwifcoin", "symbol": "wif", "platforms": {"solana": WIF}},
                      {"id": "eth", "symbol": "eth", "platforms": {}}])
        if "/exchanges/binance/" in url:
            return R({"tickers": [{"coin_id": "bonk", "base": "BONK", "target": "USDT", "converted_volume": {"usd": 5e6}},
                                  {"coin_id": "bonk", "base": "BONK", "target": "TRY", "converted_volume": {"usd": 9e9}},
                                  {"coin_id": "eth", "base": "ETH", "target": "USDT", "converted_volume": {"usd": 1e9}}]})
        if "/exchanges/mxc/" in url:
            return R({"tickers": [{"coin_id": "dogwifcoin", "base": "WIF", "target": "USDT", "converted_volume": {"usd": 2e6}},
                                  {"coin_id": "bonk", "base": "BONK", "target": "USDT", "converted_volume": {"usd": 1e5}}]})
        if "/exchanges/kucoin/" in url: return R({}, 500)
        return R({"tickers": []})


class Fiyat:
    def __init__(self, bid=0.99, ask=1.0, hata=False): self.bid, self.ask, self.hata, self.cagri = bid, ask, hata, []
    def teklif(self, borsa, taban, karsi):
        self.cagri.append((borsa, taban, karsi))
        if self.hata: raise FiyatHatasi("bağlantı yok")
        return self.bid, self.ask


class Test(unittest.TestCase):
    def test_liste(self):
        d = os.path.join(tempfile.mkdtemp(), "b.json")
        v = L.olustur(Gecko(), uyku=lambda x: None, dosya=d, now=1.0)
        self.assertEqual(v["token"], 2); self.assertIn("KuCoin", v["hatalar"])
        t = L.yukle(d)
        self.assertEqual(t[BONK]["borsalar"]["Binance"], dict(taban="BONK", karsi="USDT", hacim_usd=5e6))   # TRY çifti alınmaz
        self.assertEqual(L.en_iyi_borsa(t[BONK]), "Binance"); self.assertEqual(L.en_iyi_borsa(t[WIF]), "MEXC")
        self.assertEqual(L.yukle(os.path.join(tempfile.mkdtemp(), "yok.json")), {})

    def test_fiyat_ayrisma(self):
        class S:
            def __init__(self, body): self.body = body
            def get(self, url, params=None, timeout=None): self.url, self.p = url, params; return R(self.body)
        f = BorsaFiyat(S({"bidPrice": "0.5", "askPrice": "0.51"})); self.assertEqual(f.teklif("Binance", "BONK", "USDT"), (0.5, 0.51))
        self.assertEqual(f.s.p, {"symbol": "BONKUSDT"})
        self.assertEqual(BorsaFiyat(S({"data": [{"bidPx": "1", "askPx": "1.1"}]})).teklif("OKX", "WIF", "USDT"), (1.0, 1.1))
        self.assertEqual(BorsaFiyat(S({"data": {"bestBid": "2", "bestAsk": "2.2"}})).teklif("KuCoin", "WIF", "USDT"), (2.0, 2.2))
        with self.assertRaises(FiyatHatasi): BorsaFiyat(S({"bidPrice": "0", "askPrice": "1"})).teklif("MEXC", "X", "USDT")
        with self.assertRaises(FiyatHatasi): BorsaFiyat(S({"code": 1})).teklif("OKX", "X", "USDT")

    def motor(self, **kw):
        liste = {BONK: dict(sembol="BONK", borsalar={"Binance": dict(taban="BONK", karsi="USDT", hacim_usd=5e6)})}
        return BorsaMotoru(Paper(), liste, Fiyat(**kw))

    def test_al_sat_ayri_portfoy(self):
        m = self.motor(bid=0.99, ask=1.0)
        self.assertFalse(m.sinyal("e0", "W", WIF, "buy", 1))                       # listede değil: kuyruğa girmez
        r = m.karar("e1", "W", BONK, "buy", 1)
        self.assertEqual((r["decision"], r["borsa"], r["cift"], r["fiyat"]), ("KOPYALANDI", "Binance", "BONK/USDT", 1.0))
        self.assertEqual(len(m.paper.portfolio()["positions"]), 1)
        m.fiyat.bid, m.fiyat.ask = 1.2, 1.21
        m.degerle(); self.assertEqual(m.paper.portfolio()["positions"][0]["last_price"], 1.2)
        r = m.karar("e2", "W", BONK, "sell", 1)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertGreater(r["pnl"], 0); self.assertEqual(r["fiyat"], 1.2)
        self.assertEqual(m.paper.trades()[0]["event_id"], "borsa:e2")             # olay kimliği platform 1'den ayrı

    def test_genis_makas_ve_fiyat_hatasi(self):
        m = self.motor(bid=0.9, ask=1.0)
        r = m.karar("e1", "W", BONK, "buy", 1)
        self.assertEqual(r["decision"], "REDDEDİLDİ"); self.assertIn("makası geniş", r["reason"])
        m = self.motor(hata=True)
        r = m.karar("e1", "W", BONK, "buy", 1); self.assertEqual(r["decision"], "REDDEDİLDİ"); self.assertIn("bağlantı yok", r["reason"])
        self.assertEqual(m.paper.portfolio()["positions"], [])

    def test_kurallar_gecerli(self):
        m = self.motor()
        r = m.karar("e1", "W", BONK, "buy", 60)                                     # bayat sinyal
        self.assertEqual(r["reason"], "sinyal bayat")

    def test_takip_kancasi(self):
        from nexora.live_tracker import LiveTracker
        alinan = []
        class B:
            def sinyal(self, *a): alinan.append(a)
        tr = LiveTracker(None, Paper(), ":memory:", ["W"], borsa=B())
        self.assertIs(tr.borsa.__class__, B)

    def test_kesif_ve_ekle(self):
        import borsa_kesif as K
        d = tempfile.mkdtemp(); eski = os.getcwd(); os.chdir(d)
        try:
            open("wallets.txt", "w").write("ESKI\n")
            liste = {BONK: dict(sembol="BONK", borsalar={"Binance": dict(hacim_usd=5e6)}),
                     WIF: dict(sembol="WIF", borsalar={"MEXC": dict(hacim_usd=1e6)})}
            alici = {BONK: {"A", "B", "ESKI"}, WIF: {"A", "ESKI", "C"}}
            aday, say = K.kesfet(None, liste, n=2, en_az=2, alicilar=lambda m: alici[m])
            self.assertEqual(aday, ["A"]); self.assertEqual(say["ESKI"], 2)           # zaten takipte olan aday değil
            self.assertEqual(K.ekle(["A", "B"], en_fazla=1), ["A"]); self.assertEqual(K.ekle(["A"]), [])
            self.assertEqual(open("wallets_borsa.txt").read(), "A\n")
        finally:
            os.chdir(eski)


if __name__ == "__main__":
    unittest.main()
