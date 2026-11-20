import unittest
from nexora import evm as E
from nexora.evm_motor import EvmKarar, EvmTakip
from nexora.core import Paper

W = "0x" + "11" * 20; ROUTER = "0x" + "22" * 20; TOK = "0x" + "33" * 20
Z = E.ZINCIRLER["bnb"]; USDT, WBNB = Z["usd"], Z["sarili"]


def tr(token, frm, to, v):
    return dict(address=token, topics=[E.TRANSFER, E._konu(frm), E._konu(to)], data=hex(v))


class Rpc:
    def __init__(self, blok=100, zaman=1000.0, txler=None):
        self.b, self.zaman, self.txler = blok, zaman, txler or {}
    def blok(self): return self.b
    def blok_zamani(self, n): return self.zaman
    def ondalik(self, t): return 18
    def cuzdan_islemleri(self, w, bas, son):
        self.aralik = (bas, son)
        return {k: (v[2], W) for k, v in self.txler.items() if bas <= v[2] <= son}
    def call(self, y, p):
        if y == "eth_getBalance": return hex(10**18)                     # bakiye değişmedi: düz transfer swap sayılmaz
        tx, mk, _ = self.txler[p[0]]
        return tx if y == "eth_getTransactionByHash" else mk


class Teklif:
    def __init__(self, oran=1.0, geri=0.98, hata=False): self.oran, self.geri, self.hata, self.n = oran, geri, hata, 0
    def teklif(self, giris, cikis, miktar):
        self.n += 1
        if self.hata: raise E.EvmHatasi("rota yok")
        if giris == USDT: return dict(cikis_raw=int(miktar * self.oran), giris_usd=0, cikis_usd=0)
        return dict(cikis_raw=int(miktar / self.oran * self.geri), giris_usd=0, cikis_usd=0)


class Guv:
    def __init__(self, uygun=True, lik=1e6): self.uygun, self.lik = uygun, lik
    def kontrol(self, t): return dict(uygun=self.uygun, gerekceler=["geçti"] if self.uygun else ["honeypot (satılamaz)"], likidite_usd=self.lik)


class Test(unittest.TestCase):
    def test_coz_alim_satim(self):
        ok = dict(status="0x1")
        al = E.coz(dict(**{"from": W}, value="0x0"), dict(ok, logs=[tr(USDT, W, ROUTER, 5 * 10**18), tr(TOK, ROUTER, W, 1000)]), W, "bnb")
        self.assertEqual((al["yon"], al["token"], al["miktar_raw"], al["karsi"]), ("buy", TOK, 1000, USDT))
        yerel = E.coz(dict(**{"from": W}, value=hex(10**17)), dict(ok, logs=[tr(TOK, ROUTER, W, 7)]), W, "bnb")
        self.assertEqual((yerel["yon"], yerel["karsi"], yerel["karsi_raw"]), ("buy", E.YEREL, 10**17))          # BNB ile alım
        sat = E.coz(dict(**{"from": W}, value="0x0"), dict(ok, logs=[tr(TOK, W, ROUTER, 7),
                    dict(address=WBNB, topics=[E.WITHDRAWAL, E._konu(ROUTER)], data=hex(3 * 10**16))]), W, "bnb")
        self.assertEqual((sat["yon"], sat["karsi"]), ("sell", E.YEREL))                                         # BNB'ye satım
        self.assertIsNone(E.coz({}, dict(ok, logs=[tr(TOK, ROUTER, W, 5)]), W, "bnb"))                          # düz transfer: swap değil
        self.assertIsNone(E.coz({}, dict(status="0x0", logs=[]), W, "bnb"))                                     # başarısız işlem
        iki = dict(ok, logs=[tr(USDT, W, ROUTER, 5), tr(TOK, ROUTER, W, 1), tr("0x" + "44" * 20, ROUTER, W, 1)])
        self.assertIsNone(E.coz({}, iki, W, "bnb"))                                                               # belirsiz (iki token)

    def test_yerel_bakiye_ile_satim(self):
        """PancakeSwap v4: token satılır, BNB olay kaydı bırakmadan cüzdana geçer -> bakiye farkından görülür."""
        tx = {"from": W, "value": "0x0", "gasPrice": hex(10**9)}
        mk = dict(status="0x1", gasUsed=hex(100000), effectiveGasPrice=hex(10**9), logs=[tr(TOK, W, ROUTER, 500)])
        class B:
            def __init__(self, hata=False): self.hata = hata
            def call(self, y, p):
                if self.hata: raise E.EvmHatasi("missing trie node")
                return hex(10**18) if p[1] == hex(99) else hex(10**18 + 5 * 10**16 - 10**14)   # +0.05 BNB, ücret 0.0001 düşülmüş
        self.assertIsNone(E.coz(tx, mk, W, "bnb"))
        s = E.coz_tam(B(), tx, mk, W, "bnb", 100)
        self.assertEqual((s["yon"], s["karsi"], s["karsi_raw"], s["miktar_raw"]), ("sell", E.YEREL, 5 * 10**16, 500))
        self.assertIsNone(E.coz_tam(B(hata=True), tx, mk, W, "bnb", 100))                         # eski bakiye yoksa tahmin yok
        duz = dict(status="0x1", logs=[tr(TOK, ROUTER, W, 5), tr(USDT, ROUTER, W, 5)])             # karşı varlık olayı var: bakiyeye bakılmaz
        self.assertIsNone(E.coz_tam(B(), {"from": W, "value": "0x0"}, duz, W, "bnb", 100))

    def test_goplus_ve_likidite_yedegi(self):
        class R:
            def __init__(self, b): self.b = b
            def json(self): return self.b
        class S:
            def __init__(self, gp, ds): self.gp, self.ds = gp, ds
            def get(self, url, params=None, timeout=None): return R(self.gp if "gopluslabs" in url else self.ds)
        tok = TOK.lower()
        g = E.GoPlus("bnb", session=S({"result": {tok: {"is_honeypot": "0", "buy_tax": "0", "sell_tax": "0.12", "dex": []}}},
                                      {"pairs": [{"chainId": "bsc", "liquidity": {"usd": 80000}}, {"chainId": "ethereum", "liquidity": {"usd": 1e9}}]}))
        r = g.kontrol(TOK)
        self.assertFalse(r["uygun"]); self.assertIn("satım vergisi %12", r["gerekceler"]); self.assertEqual(r["likidite_usd"], 80000.0)
        g2 = E.GoPlus("bnb", session=S({"result": {tok: {"dex": [{"liquidity": "150000.5"}]}}}, {}))
        self.assertEqual(g2.kontrol(TOK), dict(uygun=True, gerekceler=["geçti"], likidite_usd=150000.5))
        g3 = E.GoPlus("bnb", session=S({"result": {}}, {}))
        self.assertFalse(g3.kontrol(TOK)["uygun"])                                      # bilgi yoksa alınmaz

    def test_base_ayni_bagdastirici(self):
        zb = E.ZINCIRLER["base"]
        self.assertEqual((zb["zincir_id"], zb["kyber"], zb["goplus"], zb["usd_ondalik"]), (8453, "base", "8453", 6))
        al = E.coz({"from": W, "value": "0x0"}, dict(status="0x1", logs=[tr(zb["usd"], W, ROUTER, 5 * 10**6), tr(TOK, ROUTER, W, 9)]), W, "base")
        self.assertEqual((al["yon"], al["karsi"], al["karsi_raw"]), ("buy", zb["usd"], 5 * 10**6))
        self.assertIsNone(E.coz({"from": W, "value": "0x0"}, dict(status="0x1", logs=[tr(USDT, W, ROUTER, 5), tr(TOK, ROUTER, W, 9)]), W, "base"))  # BNB'nin USDT'si Base'de karşı varlık değil

    def test_rpc_hiz_siniri_ve_bos_yanit(self):
        class R:
            def __init__(self, code, b): self.status_code, self.b = code, b
            def json(self): return self.b
        class S:
            def __init__(self, yanitlar): self.y = list(yanitlar); self.n = 0
            def post(self, url, json=None, timeout=None): self.n += 1; return self.y.pop(0)
        bekle = []
        s = S([R(200, {"error": {"message": "request limit reached"}}), R(429, None), R(200, {"result": "0x10"})])
        rpc = E.EvmRpc("http://x", session=s, uyku=bekle.append)
        self.assertEqual(rpc.blok(), 16); self.assertEqual(len(bekle), 2)                    # iki kez bekleyip başardı
        rpc = E.EvmRpc("http://x", session=S([R(200, {"error": {"message": "request limit reached"}})] * 4), uyku=lambda x: None)
        with self.assertRaises(E.EvmHatasi) as h: rpc.blok()
        self.assertIn("hız sınırı", str(h.exception))
        with self.assertRaises(E.EvmHatasi): E.EvmRpc("http://x", session=S([R(200, {"jsonrpc": "2.0"})])).blok()   # boş yanıt: çökmez
        from nexora.evm_kesif import _loglar
        class H:
            n = 0
            def call(self, y, p): H.n += 1; raise E.EvmHatasi("RPC hız sınırı (düğüm anahtarı gerekebilir)")
        with self.assertRaises(E.EvmHatasi): _loglar(H(), {}, 0, 10000)
        self.assertEqual(H.n, 1)                                                              # hız sınırında aralık bölünmez

    def test_rpc_salt_okunur(self):
        with self.assertRaises(ValueError): E.EvmRpc("http://x").call("eth_sendRawTransaction", ["0x00"])
        self.assertNotIn("eth_sendRawTransaction", E.EvmRpc.YONTEMLER); self.assertNotIn("eth_sendTransaction", E.EvmRpc.YONTEMLER)

    def k(self, **kw):
        g = kw.pop("guv", Guv()); t = kw.pop("t", Teklif())
        return EvmKarar(Paper(kayma=0.0, ekosistem="bnb"), Rpc(), t, g, "bnb")

    def test_karar_al_sat(self):
        k = self.k()
        r = k.karar("e1", W, TOK, "buy", 2)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertEqual(k.p.trades()[0]["ekosistem"], "bnb")
        k.t.oran = 0.8                                                                 # token değerlendi
        r = k.karar("e2", W, TOK, "sell", 2)
        self.assertEqual(r["decision"], "KOPYALANDI"); self.assertGreater(r["pnl"], 0)
        self.assertEqual(k.karar("e2", W, TOK, "sell", 2)["decision"], "ATLANDI")

    def test_zaman_asimi(self):
        k = self.k(); k.karar("e1", W, TOK, "buy", 2)
        acilis = k.p.acilis_ts(TOK)
        self.assertEqual(k.zaman_asimi(now=acilis + 60), [])
        self.assertEqual(k.zaman_asimi(now=acilis + 86401)[0][1], "KOPYALANDI"); self.assertEqual(k.p.portfolio()["positions"], [])

    def test_reddler(self):
        self.assertIn("honeypot", self.k(guv=Guv(False)).karar("e", W, TOK, "buy", 1)["reason"])
        self.assertIn("al-sat kaybı", self.k(t=Teklif(geri=0.9)).karar("e", W, TOK, "buy", 1)["reason"])
        self.assertIn("teklif yok", self.k(t=Teklif(hata=True)).karar("e", W, TOK, "buy", 1)["reason"])
        self.assertEqual(self.k().karar("e", W, TOK, "buy", 60)["reason"], "sinyal bayat")
        self.assertIn("likidite", self.k(guv=Guv(lik=1000)).karar("e", W, TOK, "buy", 1)["reason"])
        self.assertEqual(self.k().karar("e", W, TOK, "sell", 1)["reason"], "sahip olunmayan pozisyon satılamaz")
        k = self.k(guv=Guv(False)); k.karar("e", W, TOK, "buy", 1)
        self.assertEqual(k.p.portfolio()["positions"], [])

    def test_takip_turu(self):
        ok = dict(status="0x1")
        txler = {"0xa": (dict(**{"from": W}, value="0x0"), dict(ok, logs=[tr(USDT, W, ROUTER, 5 * 10**18), tr(TOK, ROUTER, W, 1000)]), 101),
                 "0xb": (dict(**{"from": W}, value="0x0"), dict(ok, logs=[tr(TOK, ROUTER, W, 3)]), 102)}
        rpc = Rpc(blok=100, zaman=1000.0, txler=txler)
        k = EvmKarar(Paper(kayma=0.0, ekosistem="bnb"), rpc, Teklif(), Guv(), "bnb")
        t = EvmTakip(rpc, k, [W.upper().replace("0X", "0x")], "bnb", clock=lambda: 1002.0)
        self.assertEqual(t.tur(), []); self.assertEqual(rpc.aralik, (100, 100))                 # ilk tur: geçmişe dönmez
        rpc.b = 105
        o = t.tur()
        self.assertEqual([(x["karma"], x["yon"], x["karar"]) for x in o], [("0xa", "buy", "KOPYALANDI")])   # düz transfer atlandı
        self.assertEqual(rpc.aralik, (101, 105)); self.assertEqual(t.tur(), [])                    # aynı işlem iki kez işlenmez


if __name__ == "__main__":
    unittest.main()
