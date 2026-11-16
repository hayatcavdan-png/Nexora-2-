"""Kullanıcı borsa hesabı bağlantısı (N29) ve gerçek bakiye görüntüleme (N30). YALNIZCA OKUMA.

Emanetsiz model: para her zaman kullanıcının kendi borsa hesabındadır; uygulama yalnızca kullanıcının verdiği API
anahtarıyla izinleri ve bakiyeyi OKUR.
  - Bu modülde emir gönderen, para çeken ya da transfer yapan HİÇBİR çağrı yoktur: istemci yalnızca GET yapar ve yalnızca
    aşağıdaki OKUMA uç noktalarına izin verir (IZINLI). Gerçek emir N31'de, ayrı ve açık onayla eklenecek.
  - Çekim (withdraw) izni AÇIK olan anahtar REDDEDİLİR ve saklanmaz. İzin doğrulanamıyorsa da reddedilir.
  - Kabul edilen anahtar sunucuda yalnızca şifreli saklanır (kasa.py; kayıt üye + borsaya bağlı). Ekrana ve yanıtlara
    yalnızca son 4 karakter çıkar; hata mesajlarına anahtar yazılmaz.
"""
import base64, hashlib, hmac, json, time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

BORSALAR = {
    "binance": dict(ad="Binance", parola=False, taban="https://api.binance.com"),
    "okx": dict(ad="OKX", parola=True, taban="https://www.okx.com"),
    "kucoin": dict(ad="KuCoin", parola=True, taban="https://api.kucoin.com"),
    "mexc": dict(ad="MEXC", parola=False, taban="https://api.mexc.com"),
}
IZINLI = {                                        # salt okunur uç noktalar; başka hiçbir yol çağrılamaz
    "binance": {"/sapi/v1/account/apiRestrictions", "/api/v3/account"},
    "okx": {"/api/v5/account/config", "/api/v5/account/balance"},
    "kucoin": {"/api/v1/user/api-key", "/api/v1/accounts"},
    "mexc": {"/api/v3/account"},
}
STABIL = {"USDT", "USDC", "FDUSD", "BUSD", "DAI", "TUSD", "USD"}
TOZ_USD = 1.0                                     # bunun altındaki varlıklar listede gösterilmez (toplama dahil)


class BorsaHesapHatasi(ValueError):
    pass


def _temiz(x, en_az=8, en_cok=200):
    if not isinstance(x, str): return ""
    x = x.strip()
    return x if en_az <= len(x) <= en_cok and x.isprintable() and " " not in x else ""


class Istemci:
    """İmzalı, yalnızca GET yapan borsa istemcisi."""

    def __init__(self, borsa, anahtar, gizli, parola="", s=None, saat=time.time, timeout=15):
        if borsa not in BORSALAR: raise BorsaHesapHatasi("desteklenmeyen borsa")
        self.b, self.k, self.g, self.p = borsa, anahtar, gizli, parola
        self.s, self.saat, self.timeout = s or requests.Session(), saat, timeout

    def _hmac(self, mesaj):
        return hmac.new(self.g.encode(), mesaj.encode(), hashlib.sha256)

    def get(self, yol, params=None):
        if yol not in IZINLI[self.b]: raise BorsaHesapHatasi("izin verilmeyen uç nokta")
        params = dict(params or {}); taban = BORSALAR[self.b]["taban"]; baslik = {"Accept": "application/json"}
        if self.b in ("binance", "mexc"):
            params.update(timestamp=int(self.saat() * 1000), recvWindow=10000)
            sorgu = urlencode(params); sorgu += "&signature=" + self._hmac(sorgu).hexdigest()
            baslik["X-MBX-APIKEY" if self.b == "binance" else "X-MEXC-APIKEY"] = self.k
            url = f"{taban}{yol}?{sorgu}"
        else:
            yol_tam = yol + ("?" + urlencode(params) if params else "")
            if self.b == "okx":
                ts = datetime.fromtimestamp(self.saat(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                imza = base64.b64encode(self._hmac(ts + "GET" + yol_tam).digest()).decode()
                baslik.update({"OK-ACCESS-KEY": self.k, "OK-ACCESS-SIGN": imza, "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.p})
            else:
                ts = str(int(self.saat() * 1000))
                imza = base64.b64encode(self._hmac(ts + "GET" + yol_tam).digest()).decode()
                baslik.update({"KC-API-KEY": self.k, "KC-API-SIGN": imza, "KC-API-TIMESTAMP": ts, "KC-API-KEY-VERSION": "2",
                               "KC-API-PASSPHRASE": base64.b64encode(self._hmac(self.p).digest()).decode()})
            url = taban + yol_tam
        try:
            r = self.s.get(url, headers=baslik, timeout=self.timeout)
            d = r.json()
        except (requests.RequestException, ValueError):
            raise BorsaHesapHatasi(f"{BORSALAR[self.b]['ad']} yanıt vermedi") from None
        hata = self._hata(r.status_code, d)
        if hata: raise BorsaHesapHatasi(f"{BORSALAR[self.b]['ad']}: {hata}")
        return d

    def _hata(self, kod, d):
        if self.b in ("binance", "mexc"):
            if kod == 200 and not (isinstance(d, dict) and "code" in d and "msg" in d and d.get("code") not in (0, 200)): return None
            return _kisa(d.get("msg") if isinstance(d, dict) else None, kod)
        if self.b == "okx":
            if kod == 200 and isinstance(d, dict) and str(d.get("code")) == "0": return None
            return _kisa(d.get("msg") if isinstance(d, dict) else None, kod)
        if kod == 200 and isinstance(d, dict) and str(d.get("code")) == "200000": return None
        return _kisa(d.get("msg") if isinstance(d, dict) else None, kod)


def _kisa(msg, kod):
    return (str(msg)[:100] if msg else f"HTTP {kod}") + " (anahtar, gizli anahtar, parola ya da IP kısıtını kontrol edin)"


def izinler(c):
    """dict(okuma, islem, cekim, ip_kisitli): bool ya da None (bilinmiyor)."""
    if c.b == "binance":
        d = c.get("/sapi/v1/account/apiRestrictions")
        return dict(okuma=bool(d.get("enableReading")), islem=bool(d.get("enableSpotAndMarginTrading")),
                    cekim=d.get("enableWithdrawals") if isinstance(d.get("enableWithdrawals"), bool) else None,
                    ip_kisitli=bool(d.get("ipRestrict")))
    if c.b == "okx":
        cfg = (c.get("/api/v5/account/config").get("data") or [{}])[0]
        perm = {x.strip() for x in str(cfg.get("perm", "")).split(",") if x.strip()}
        return dict(okuma=bool(perm), islem="trade" in perm, cekim=("withdraw" in perm) if perm else None,
                    ip_kisitli=bool(cfg.get("ip")) if "ip" in cfg else None)
    if c.b == "kucoin":
        d = c.get("/api/v1/user/api-key").get("data") or {}
        perm = {x.strip().lower() for x in str(d.get("permission", "")).split(",") if x.strip()}
        return dict(okuma=bool(perm), islem=bool(perm & {"spot", "trade"}), cekim=any("withdraw" in x for x in perm) if perm else None,
                    ip_kisitli=bool(d.get("ipWhitelist")) if "ipWhitelist" in d else None)
    d = c.get("/api/v3/account")                    # MEXC: anahtar izni ayrı sorgulanamıyor; hesap bilgisinin alanları
    return dict(okuma=True, islem=d.get("canTrade") if isinstance(d.get("canTrade"), bool) else None,
                cekim=d.get("canWithdraw") if isinstance(d.get("canWithdraw"), bool) else None, ip_kisitli=None)


def kabul_et(izin):
    """Kabul kuralı: okuma izni var VE çekim izninin KAPALI olduğu doğrulandı. Değilse gerekçeyle reddeder."""
    if izin.get("cekim") is True:
        raise BorsaHesapHatasi("Bu anahtarda PARA ÇEKME izni açık. Güvenliğiniz için kabul edilmedi ve saklanmadı. "
                               "Borsada çekim izni KAPALI yeni bir anahtar oluşturun.")
    if izin.get("cekim") is None:
        raise BorsaHesapHatasi("Anahtarın para çekme izni doğrulanamadı; güvenlik için kabul edilmedi.")
    if not izin.get("okuma"):
        raise BorsaHesapHatasi("Anahtarda okuma izni yok: bakiye görüntülenemez.")


def bakiyeler(c, fiyatlar=None):
    """[(varlık, miktar, usd ya da None)]: sıfır olmayanlar. `fiyatlar` = {taban: dict(son=...)} (piyasa.borsa_fiyatlari)."""
    fiyatlar = fiyatlar or {}
    ham = []
    if c.b in ("binance", "mexc"):
        d = c.get("/api/v3/account", {"omitZeroBalances": "true"} if c.b == "binance" else None)
        for x in d.get("balances") or []:
            ham.append((x.get("asset"), _sayi(x.get("free")) + _sayi(x.get("locked")), None))
    elif c.b == "okx":
        for x in ((c.get("/api/v5/account/balance").get("data") or [{}])[0].get("details") or []):
            ham.append((x.get("ccy"), _sayi(x.get("eq")), _sayi(x.get("eqUsd")) if x.get("eqUsd") not in (None, "") else None))
    else:
        top = {}
        for x in c.get("/api/v1/accounts").get("data") or []:
            top[x.get("currency")] = top.get(x.get("currency"), 0.0) + _sayi(x.get("balance"))
        ham = [(k, v, None) for k, v in top.items()]
    out = []
    for varlik, miktar, usd in ham:
        if not varlik or miktar <= 0: continue
        varlik = str(varlik).upper()
        if usd is None:
            if varlik in STABIL: usd = miktar
            elif varlik in fiyatlar: usd = miktar * fiyatlar[varlik]["son"]
        out.append((varlik, miktar, usd))
    return out


def _sayi(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0


def ozet_bakiye(liste):
    """Toplam USD (değeri bilinenler), gösterilecek varlıklar (toz hariç, büyükten küçüğe), değeri bilinmeyen sayısı."""
    bilinen = [x for x in liste if x[2] is not None]
    gorunur = sorted((x for x in bilinen if x[2] >= TOZ_USD), key=lambda x: -x[2])
    return dict(toplam_usd=round(sum(x[2] for x in bilinen), 2),
                varliklar=[dict(varlik=v, miktar=round(m, 8), usd=round(u, 2)) for v, m, u in gorunur[:20]],
                degeri_bilinmeyen=len(liste) - len(bilinen))
