import base64, hashlib, hmac, json, unittest
from urllib.parse import urlsplit, parse_qs

from nexora import borsa_hesap as BH
from nexora.kasa import Kasa
from nexora.uyelik import Uyelik, UyelikHatasi

K, G, P = "ANAHTAR1234abcd", "GIZLI-5678-efgh", "parola1"
SAAT = lambda: 1_700_000_000.0


class R:
    def __init__(self, d, kod=200): self.d, self.status_code = d, kod
    def json(self): return self.d


class Sahte:
    """Borsa API taklidi: imzayı doğrular, yanıtları yol başına verir; her isteği kaydeder."""
    def __init__(self, borsa, yanit): self.b, self.yanit, self.istek = borsa, yanit, []

    def get(self, url, headers=None, timeout=None):
        p = urlsplit(url); self.istek.append((p.path, headers))
        if self.b in ("binance", "mexc"):
            q = p.query.rsplit("&signature=", 1)
            assert hmac.new(G.encode(), q[0].encode(), hashlib.sha256).hexdigest() == q[1], "imza"
        elif self.b == "okx":
            beklenen = base64.b64encode(hmac.new(G.encode(), (headers["OK-ACCESS-TIMESTAMP"] + "GET" + p.path + (("?" + p.query) if p.query else "")).encode(), hashlib.sha256).digest()).decode()
            assert headers["OK-ACCESS-SIGN"] == beklenen and headers["OK-ACCESS-PASSPHRASE"] == P
        else:
            beklenen = base64.b64encode(hmac.new(G.encode(), (headers["KC-API-TIMESTAMP"] + "GET" + p.path).encode(), hashlib.sha256).digest()).decode()
            assert headers["KC-API-SIGN"] == beklenen
        return R(*self.yanit[p.path]) if isinstance(self.yanit[p.path], tuple) else R(self.yanit[p.path])


def ist(borsa, yanit):
    s = Sahte(borsa, yanit)
    return BH.Istemci(borsa, K, G, P, s=s, saat=SAAT), s


class IzinTest(unittest.TestCase):
    def test_binance_cekim_acik_reddedilir(self):
        c, _ = ist("binance", {"/sapi/v1/account/apiRestrictions": {"enableReading": True, "enableWithdrawals": True, "ipRestrict": False}})
        with self.assertRaises(BH.BorsaHesapHatasi) as e: BH.kabul_et(BH.izinler(c))
        self.assertIn("ÇEKME", str(e.exception))

    def test_binance_uygun(self):
        c, _ = ist("binance", {"/sapi/v1/account/apiRestrictions": {"enableReading": True, "enableWithdrawals": False,
                                                                     "enableSpotAndMarginTrading": True, "ipRestrict": True}})
        i = BH.izinler(c); BH.kabul_et(i)
        self.assertEqual(i, dict(okuma=True, islem=True, cekim=False, ip_kisitli=True))

    def test_okx_kucoin_mexc(self):
        c, _ = ist("okx", {"/api/v5/account/config": {"code": "0", "data": [{"perm": "read_only,trade", "ip": "1.2.3.4"}]}})
        BH.kabul_et(BH.izinler(c))
        c, _ = ist("okx", {"/api/v5/account/config": {"code": "0", "data": [{"perm": "read_only,withdraw"}]}})
        self.assertTrue(BH.izinler(c)["cekim"])
        c, _ = ist("kucoin", {"/api/v1/user/api-key": {"code": "200000", "data": {"permission": "General,Spot", "ipWhitelist": ""}}})
        BH.kabul_et(BH.izinler(c))
        c, _ = ist("kucoin", {"/api/v1/user/api-key": {"code": "200000", "data": {"permission": "General,Withdrawal"}}})
        self.assertTrue(BH.izinler(c)["cekim"])
        c, _ = ist("mexc", {"/api/v3/account": {"canTrade": True, "canWithdraw": False, "balances": []}})
        BH.kabul_et(BH.izinler(c))

    def test_dogrulanamayan_cekim_reddedilir(self):
        with self.assertRaises(BH.BorsaHesapHatasi): BH.kabul_et(dict(okuma=True, islem=True, cekim=None))

    def test_borsa_hatasi_anahtari_yazmaz(self):
        c, _ = ist("binance", {"/sapi/v1/account/apiRestrictions": ({"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}, 401)})
        with self.assertRaises(BH.BorsaHesapHatasi) as e: BH.izinler(c)
        self.assertNotIn(K, str(e.exception)); self.assertNotIn(G, str(e.exception))

    def test_yalnizca_okuma_uc_noktalari(self):
        c, _ = ist("binance", {})
        for yol in ("/api/v3/order", "/sapi/v1/capital/withdraw/apply", "/api/v3/account/../order"):
            with self.assertRaises(BH.BorsaHesapHatasi): c.get(yol)
        self.assertFalse(hasattr(c, "post"))


class BakiyeTest(unittest.TestCase):
    def test_degerleme(self):
        c, _ = ist("binance", {"/api/v3/account": {"balances": [{"asset": "USDT", "free": "50", "locked": "10"},
                                                                {"asset": "BTC", "free": "0.001", "locked": "0"},
                                                                {"asset": "XYZ", "free": "5", "locked": "0"},
                                                                {"asset": "DOGE", "free": "1", "locked": "0"}]}})
        oz = BH.ozet_bakiye(BH.bakiyeler(c, {"BTC": {"son": 50000.0}, "DOGE": {"son": 0.1}}))
        self.assertEqual(oz["toplam_usd"], 110.1)
        self.assertEqual([v["varlik"] for v in oz["varliklar"]], ["USDT", "BTC"])     # toz (DOGE 0.1 $) gösterilmez
        self.assertEqual(oz["degeri_bilinmeyen"], 1)

    def test_fiat_kurlari_ve_tl_degerleme(self):
        class Fiyat:
            def __init__(self, d): self.d, self.url = d, None
            def get(self, url, timeout=None): self.url = url; return R(self.d)
        s = Fiyat([{"symbol": "USDTTRY", "price": "40.00"}, {"symbol": "EURUSDT", "price": "1.10"}, {"symbol": "BTCUSDT", "price": "50000"}])
        kur = BH.fiat_kurlari(s, "binance")
        self.assertEqual(s.url, BH.FIYAT_URL["binance"])
        self.assertAlmostEqual(kur["TRY"]["son"], 0.025); self.assertAlmostEqual(kur["EUR"]["son"], 1.10)
        self.assertNotIn("BTC", kur)                                                     # yalnızca itibari paralar
        c, _ = ist("binance", {"/api/v3/account": {"balances": [{"asset": "TRY", "free": "72", "locked": "0"},
                                                                {"asset": "BNB", "free": "0.002", "locked": "0"}]}})
        oz = BH.ozet_bakiye(BH.bakiyeler(c, {"BNB": {"son": 600.0}, **kur}))
        self.assertEqual(oz["degeri_bilinmeyen"], 0); self.assertEqual(oz["toplam_usd"], 3.0)   # 72/40 + 1.2
        self.assertEqual(BH.fiat_kurlari(Fiyat({"code": -1, "msg": "x"}), "binance"), {})        # hata: boş
        self.assertEqual(BH.fiat_kurlari(Fiyat([]), "kucoin"), {})                                # desteklenmeyen borsa

    def test_binance_earn_ld_varliklari(self):
        c, _ = ist("binance", {"/api/v3/account": {"balances": [{"asset": "LDBNB", "free": "0.002", "locked": "0"},
                                                                {"asset": "LDUSDT", "free": "3", "locked": "0"},
                                                                {"asset": "LDO", "free": "1", "locked": "0"},
                                                                {"asset": "QQQ", "free": "1", "locked": "0"}]}})
        oz = BH.ozet_bakiye(BH.bakiyeler(c, {"BNB": {"son": 600.0}, "LDO": {"son": 2.0}}))
        self.assertEqual(oz["toplam_usd"], 6.2)                                          # 1.2 + 3 + 2
        self.assertEqual(oz["degeri_bilinmeyen"], 1); self.assertEqual(oz["bilinmeyenler"], ["QQQ"])

    def test_okx_equsd_kucoin_toplama(self):
        c, _ = ist("okx", {"/api/v5/account/balance": {"code": "0", "data": [{"details": [{"ccy": "ETH", "eq": "0.5", "eqUsd": "1500"}]}]}})
        self.assertEqual(BH.bakiyeler(c), [("ETH", 0.5, 1500.0)])
        c, _ = ist("kucoin", {"/api/v1/accounts": {"code": "200000", "data": [{"currency": "USDT", "balance": "5"}, {"currency": "USDT", "balance": "7"}]}})
        self.assertEqual(BH.bakiyeler(c), [("USDT", 12.0, 12.0)])


class UyelikBorsaTest(unittest.TestCase):
    def setUp(self):
        self.u = Uyelik(); self.me = self.u.uye(self.u.kayit("a@b.co", "gizli-parola-1"))["id"]
        self.kasa = Kasa(ana=bytes(32))
        self.yanit = {"/sapi/v1/account/apiRestrictions": {"enableReading": True, "enableWithdrawals": False, "ipRestrict": True},
                      "/api/v3/account": {"balances": [{"asset": "USDT", "free": "25", "locked": "0"}]}}
        self.fab = lambda b, k, g, p: BH.Istemci(b, k, g, p, s=Sahte(b, self.yanit), saat=SAAT)

    def test_bagla_sifreli_sakla_bakiye_sil(self):
        bl = self.u.borsa_bagla(self.me, "Binance", K, G, "", self.kasa, self.fab)
        b = [x for x in bl if x["borsa"] == "binance"][0]
        self.assertTrue(b["bagli"]); self.assertEqual(b["maske"], "••••••abcd")
        ham = self.u.db.execute("SELECT * FROM borsa_anahtar").fetchone()
        self.assertNotIn(K, ham["sifreli"]); self.assertNotIn(G, ham["sifreli"])           # düz metin yok
        bk = self.u.borsa_bakiye(self.me, self.kasa, self.fab)
        self.assertEqual(bk["toplam_usd"], 25.0)
        self.u.db.execute("UPDATE borsa_anahtar SET uye=999"); bk = self.u.borsa_bakiye(999, self.kasa, self.fab)
        self.assertIn("hata", bk["borsalar"][0])                                            # başka üyeye taşınan kayıt çözülmez
        self.u.db.execute("UPDATE borsa_anahtar SET uye=?", (self.me,))
        self.assertFalse([x for x in self.u.borsa_sil(self.me, "binance") if x["borsa"] == "binance"][0]["bagli"])

    def test_cekim_acik_saklanmaz(self):
        self.yanit["/sapi/v1/account/apiRestrictions"]["enableWithdrawals"] = True
        with self.assertRaises(UyelikHatasi): self.u.borsa_bagla(self.me, "binance", K, G, "", self.kasa, self.fab)
        self.assertEqual(self.u.db.execute("SELECT COUNT(*) FROM borsa_anahtar").fetchone()[0], 0)

    def test_eksik_alan_ve_deneme_siniri(self):
        with self.assertRaises(UyelikHatasi): self.u.borsa_bagla(self.me, "okx", K, G, "", self.kasa, self.fab)    # parola gerekli
        with self.assertRaises(UyelikHatasi): self.u.borsa_bagla(self.me, "binance", "kisa", G, "", self.kasa, self.fab)
        with self.assertRaises(UyelikHatasi): self.u.borsa_bagla(self.me, "ftx", K, G, "", self.kasa, self.fab)
        self.yanit["/sapi/v1/account/apiRestrictions"]["enableWithdrawals"] = True
        for _ in range(10):
            with self.assertRaises(UyelikHatasi): self.u.borsa_bagla(self.me, "binance", K, G, "", self.kasa, self.fab)
        with self.assertRaises(PermissionError): self.u.borsa_bagla(self.me, "binance", K, G, "", self.kasa, self.fab)


if __name__ == "__main__":
    unittest.main()
