import os, tempfile, unittest
from nexora import piyasa as P
from nexora.core import Paper


class R:
    def __init__(self, b): self.b = b
    def json(self): return self.b


class S:
    def __init__(self, yanit): self.y = yanit
    def get(self, url, params=None, timeout=None):
        for k, v in self.y.items():
            if k in url: return R(v)
        raise P.requests.ConnectionError("yok")


def fiyat(son, hacim=5e6, makas=0.0005):
    return dict(son=son, bid=son * (1 - makas / 2), ask=son * (1 + makas / 2), hacim=hacim)


def motor():
    d = tempfile.mkdtemp()
    pf = {st.ad: Paper(os.path.join(d, st.ad + ".db"), kayma=P.KAYMA, ucret_orani=P.UCRET) for st in P.STRATEJILER}
    return P.Motor(pf, s=None, borsalar=("Binance",), durum_dosyasi=os.path.join(d, "durum.json")), pf


class Test(unittest.TestCase):
    def test_ayristirma_ve_evren(self):
        s = S({"binance.com": [dict(symbol="BTCUSDT", lastPrice="60000", bidPrice="59999", askPrice="60001", quoteVolume="9e8"),
                               dict(symbol="ETHBTC", lastPrice="0.05", bidPrice="0.05", askPrice="0.05", quoteVolume="9e8"),
                               dict(symbol="USDCUSDT", lastPrice="1", bidPrice="1", askPrice="1", quoteVolume="9e8"),
                               dict(symbol="BTCUPUSDT", lastPrice="1", bidPrice="1", askPrice="1", quoteVolume="9e8"),
                               dict(symbol="SOLUSDT", lastPrice="150", bidPrice="149.9", askPrice="150.1", quoteVolume="5e5")],
               "okx.com": {"data": [dict(instId="SOL-USDT", last="150", bidPx="149.95", askPx="150.05", volCcy24h="3e6")]},
               "kucoin.com": {"data": {"ticker": [dict(symbol="ETH-USDT", last="3000", buy="2999", sell="3001", volValue="2e6")]}}})
        b = P.borsa_fiyatlari(s, "Binance")
        self.assertEqual(set(b), {"BTC", "SOL"})                                 # ETH/BTC, stablecoin, kaldıraçlı token yok
        f = {"Binance": b, "OKX": P.borsa_fiyatlari(s, "OKX"), "KuCoin": P.borsa_fiyatlari(s, "KuCoin"), "MEXC": P.borsa_fiyatlari(s, "MEXC")}
        self.assertIsNone(f["MEXC"])
        e = P.evren(f)
        self.assertEqual({k: v["borsa"] for k, v in e.items()}, {"BTC": "Binance", "SOL": "OKX", "ETH": "KuCoin"})  # en hacimli borsa

    def test_momentum_al_ve_kar_al(self):
        m, pf = motor(); t0 = 1_000_000.0
        for i in range(61): m.tur(t0 + i * 60, {"Binance": {"BTC": fiyat(100.0), "XYZ": fiyat(100.0)}})
        olay, d = m.tur(t0 + 61 * 60, {"Binance": {"BTC": fiyat(100.0), "XYZ": fiyat(104.0)}})   # 15 dk'da %4, 1 saatte %4
        self.assertIn(("momentum", "al", "Binance:XYZ/USDT"), [o[:3] for o in olay])
        self.assertEqual(len(pf["momentum"].portfolio()["positions"]), 1)
        olay, _ = m.tur(t0 + 62 * 60, {"Binance": {"BTC": fiyat(101.0), "XYZ": fiyat(110.5)}})
        sat = [o for o in olay if o[:2] == ("momentum", "sat")]
        self.assertTrue(sat and sat[0][3].startswith("kâr al"))
        t = [x for x in pf["momentum"].trades() if x["side"] == "sell" and x["decision"] == "KOPYALANDI"][0]
        self.assertGreater(t["pnl"], 0); self.assertGreater(t["fee"], 0.004)        # yüzdelik ücret düşüldü
        olay, _ = m.tur(t0 + 63 * 60, {"Binance": {"BTC": fiyat(101.0), "XYZ": fiyat(120.0)}})
        self.assertNotIn(("momentum", "al", "Binance:XYZ/USDT"), [o[:3] for o in olay])   # bekleme süresi: yeniden girmez
        self.assertEqual(_["kiyas_btc_pct"], 1.0)

    def test_zarar_kes_ve_genis_makas(self):
        m, pf = motor(); t0 = 2_000_000.0
        for i in range(61): m.tur(t0 + i * 60, {"Binance": {"A": fiyat(10.0), "B": fiyat(10.0)}})
        olay, _ = m.tur(t0 + 61 * 60, {"Binance": {"A": fiyat(10.4), "B": fiyat(10.4, makas=0.01)}})
        alinan = {o[2] for o in olay if o[:2] == ("momentum", "al")}
        self.assertEqual(alinan, {"Binance:A/USDT"})                                # B'nin makası %1: alınmaz
        olay, _ = m.tur(t0 + 62 * 60, {"Binance": {"A": fiyat(10.0)}})
        self.assertTrue(any(o[:2] == ("momentum", "sat") and "zarar kes" in o[3] for o in olay))

    def test_trend_iz_suren(self):
        st = P.Trend(); poz = dict(giris_fiyat=100.0, giris_ts=0.0, zirve=120.0)
        self.assertIsNone(st.cikis(poz, fiyat(119.0), 3600))
        self.assertIn("iz süren", st.cikis(poz, fiyat(116.0), 3600))
        self.assertIn("süre", P.Momentum().cikis(dict(giris_fiyat=100.0, giris_ts=0.0, zirve=100.0), fiyat(101.0), 5 * 3600))

    def test_ozet(self):
        m, pf = motor()
        o = P.ozet(pf["trend"], P.Trend())
        self.assertEqual((o["kapanan"], o["kazanma_pct"], o["toplam"]), (0, None, 100.0))


if __name__ == "__main__":
    unittest.main()
