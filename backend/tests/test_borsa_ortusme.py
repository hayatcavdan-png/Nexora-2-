import io, os, sqlite3, tempfile, time, unittest
from contextlib import redirect_stdout
import borsa_ortusme as B

BONK, SAHTE, YENI = "DezX" + "a" * 40, "Sahte" + "b" * 39, "Yeni" + "c" * 40


class R:
    def __init__(self, body, code=200): self.status_code, self.b = code, body
    def json(self): return self.b


class S:
    def __init__(self, gecko): self.gecko, self.cagri = gecko, []
    def get(self, url, params=None, headers=None, timeout=None):
        self.cagri.append(url)
        if "binance" in url:
            return R({"symbols": [{"baseAsset": "BONK", "status": "TRADING"}, {"baseAsset": "ESKI", "status": "BREAK"}]})
        if "tokens/v2" in url:
            return R([{"id": BONK, "symbol": "Bonk"}, {"id": SAHTE, "symbol": "BONK"}, {"id": YENI, "symbol": "YENI"}])
        for m, v in self.gecko.items():
            if m in url: return v
        return R({}, 404)


def db(now):
    d = tempfile.mkdtemp(); t = os.path.join(d, "t.db"); p = os.path.join(d, "p.db")
    c = sqlite3.connect(t); c.execute("CREATE TABLE tracker_signals(ts REAL, wallet TEXT, side TEXT, token TEXT)")
    rows = [(now - 60, "W1", "buy", BONK)] * 3 + [(now - 60, "W2", "buy", SAHTE)] * 2 + [(now - 60, "W1", "buy", YENI)] * 5 \
         + [(now - 30 * 86400, "W1", "buy", BONK), (now - 60, "W1", "sell", YENI)]
    c.executemany("INSERT INTO tracker_signals VALUES(?,?,?,?)", rows); c.commit(); c.close()
    c = sqlite3.connect(p); c.execute("CREATE TABLE trades(ts REAL, token TEXT, side TEXT, decision TEXT)")
    c.executemany("INSERT INTO trades VALUES(?,?,?,?)", [(now - 60, BONK, "buy", "KOPYALANDI"), (now - 60, YENI, "buy", "KOPYALANDI"),
                                                       (now - 60, YENI, "buy", "REDDEDİLDİ")]); c.commit(); c.close()
    return t, p


class Test(unittest.TestCase):
    def test_olcum(self):
        now = time.time(); t, p = db(now)
        s = S({BONK: R({"tickers": [{"market": {"identifier": "binance"}}]}), SAHTE: R({}, 404)})
        r = B.olc(s, t, p, 7, now, uyku=lambda x: None)
        self.assertEqual((r["token"], r["sinyal"], r["kopya"]), (3, 10, 2))
        self.assertEqual((r["sembol_eslesen"], r["dogrulanan"], r["dogrulanan_sinyal"]), (2, 1, 3))   # sahte BONK elendi
        self.assertEqual((r["sinyal_payi_pct"], r["kopya_payi_pct"]), (30.0, 50.0))
        self.assertEqual({x["mint"]: x["binance"] for x in r["tokenler"]}[BONK], "evet")
        self.assertIn("hayır", [x for x in r["tokenler"] if x["mint"] == SAHTE][0]["binance"])

    def test_dogrulanamayan_ust_sinir_ve_cikti(self):
        now = time.time(); t, p = db(now)
        s = S({BONK: R({}, 500), SAHTE: R({}, 429)})
        r = B.olc(s, t, p, 7, now, uyku=lambda x: None)
        self.assertEqual((r["dogrulanan"], r["dogrulanamayan"], r["sinyal_payi_pct"], r["ust_sinir_pct"]), (0, 2, 0.0, 50.0))
        bos = B.olc(s, os.path.join(tempfile.mkdtemp(), "yok.db"), p, 7, now)
        self.assertEqual(bos["token"], 0)

    def test_emir_ve_anahtar_yok(self):
        src = open(B.__file__).read()
        for yasak in ("sendTransaction", "/execute", "pilot.json", "signature="): self.assertNotIn(yasak, src)


if __name__ == "__main__":
    unittest.main()
