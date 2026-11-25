"""BTC piyasa duygusu ve konumlanma verisi (SALT OKUNUR, anahtarsız herkese açık uç noktalar).

Kaynaklar:
- Binance vadeli (fapi): fonlama oranı, açık pozisyon (OI), tüm hesapların long/short oranı, BÜYÜK TRADER'ların
  (en yüksek bakiyeli hesaplar) pozisyon long/short oranı, taker alış/satış hacim oranı. 1 saatlik geçmiş ~20 gün.
- alternative.me Korku & Açgözlülük endeksi (günlük, sosyal medya + hacim + oynaklık bileşenli).
- Hyperliquid: hl_cuzdanlar.txt'deki (liderlik tablosundan seçilmiş, sürekli kârlı) trader'ların ŞU ANKİ BTC pozisyonları.
  Geçmişi yoktur; her tur kaydedilir ve ileride sınanır.

Geleceği görme yok: her seri noktası, zaman damgasından sonra temkinli bir gecikmeyle (GECIKME) 'bilinir' sayılır;
özellikler t anında yalnızca o ana kadar bilinen noktalardan hesaplanır. Canlı ve geçmiş sınama AYNI fonksiyonu kullanır.
Hata/erişim sorunu olan kaynak None döner; sistem onsuz devam eder."""
import os, time

import requests

FAPI = os.getenv("BINANCE_FAPI", "https://fapi.binance.com")
FNG_URL = os.getenv("FNG_URL", "https://api.alternative.me/fng/")
SEMBOL = "BTCUSDT"
GECIKME = {"oi": 3600, "ls": 3600, "buyuk": 3600, "taker": 3600, "fonlama": 0, "korku": 86400}
BAYAT = {"oi": 3 * 3600, "ls": 3 * 3600, "buyuk": 3 * 3600, "taker": 3 * 3600, "fonlama": 9 * 3600, "korku": 3 * 86400}
KURALLAR = ("fonlama", "kalabalik", "buyuk_trader", "oi_fiyat", "taker", "korku")
CANLI_KURALLAR = ("uzman_hl", "haber")              # geçmişi yok; canlı kaydedilir, ileride sınanır


# ---------------------------------------------------------------- veri çekme
def _get(s, url, params, timeout=15):
    r = s.get(url, params=params, timeout=timeout); r.raise_for_status(); return r.json()


def seriler(s=None, limit=500):
    """{ad: [(ts_sn, değer)]} artan sırada. Erişilemeyen seri atlanır (sözlükte yok)."""
    s = s or requests.Session(); out = {}
    uc = {"oi": ("/futures/data/openInterestHist", "sumOpenInterest"),
          "ls": ("/futures/data/globalLongShortAccountRatio", "longShortRatio"),
          "buyuk": ("/futures/data/topLongShortPositionRatio", "longShortRatio"),
          "taker": ("/futures/data/takerlongshortRatio", "buySellRatio")}
    for ad, (yol, alan) in uc.items():
        try:
            out[ad] = sorted((int(x["timestamp"]) / 1000, float(x[alan]))
                             for x in _get(s, FAPI + yol, {"symbol": SEMBOL, "period": "1h", "limit": limit}))
        except Exception:
            pass
    try:
        out["fonlama"] = sorted((int(x["fundingTime"]) / 1000, float(x["fundingRate"]))
                                for x in _get(s, FAPI + "/fapi/v1/fundingRate", {"symbol": SEMBOL, "limit": 1000}))
    except Exception:
        pass
    try:
        out["korku"] = sorted((int(x["timestamp"]), float(x["value"])) for x in _get(s, FNG_URL, {"limit": 120}).get("data", []))
    except Exception:
        pass
    return out


def uzman_hl(s=None, liste_yolu="hl_cuzdanlar.txt", coin="BTC", en_fazla=40):
    """Seçilmiş Hyperliquid trader'larının şu anki BTC pozisyonları: dict(long, short, net_oran, long_usd, short_usd, n)."""
    from nexora import hl
    cuzdanlar = hl.liste_oku(liste_yolu)[:en_fazla]
    if not cuzdanlar: return None
    s = s or requests.Session(); lu = su = 0.0; nl = ns = sorgu = 0
    for w in cuzdanlar:
        try:
            r = s.post(hl.API, json={"type": "clearinghouseState", "user": w}, timeout=10); r.raise_for_status()
            sorgu += 1
            for a in (r.json() or {}).get("assetPositions") or []:
                p = a.get("position") or {}
                if p.get("coin") != coin: continue
                szi, deger = float(p.get("szi") or 0), abs(float(p.get("positionValue") or 0))
                if szi > 0: lu += deger; nl += 1
                elif szi < 0: su += deger; ns += 1
        except Exception:
            continue
    if sorgu == 0: return None
    top = lu + su
    return dict(n=sorgu, long=nl, short=ns, long_usd=round(lu), short_usd=round(su),
                net_oran=round((lu - su) / top, 3) if top > 0 else 0.0)


# ---------------------------------------------------------------- özellikler (saf)
def _bilinen(seri, ad, t):
    """t anında bilinen noktalar (zaman damgası + gecikme ≤ t)."""
    g = GECIKME.get(ad, 0)
    return [v for ts, v in seri if ts + g <= t] if seri else []


def _son(seri, ad, t):
    g = GECIKME.get(ad, 0)
    son = None
    for ts, v in seri or []:
        if ts + g <= t: son = (ts, v)
        else: break
    if son is None or t - (son[0] + g) > BAYAT.get(ad, 3 * 3600): return None
    return son[1]


def ozellik(seri, t, r4=None):
    """t anındaki duygu özellikleri (bilinmeyen None)."""
    o = {}
    f = _son(seri.get("fonlama"), "fonlama", t)
    o["fonlama_pct"] = None if f is None else f * 100
    ls = _bilinen(seri.get("ls"), "ls", t)
    if _son(seri.get("ls"), "ls", t) is not None and len(ls) >= 48:
        pencere = ls[-168:]
        o["ls_oran"] = ls[-1]; o["ls_yuzdelik"] = sum(x < ls[-1] for x in pencere) / len(pencere) * 100
    else:
        o["ls_oran"] = o["ls_yuzdelik"] = None
    b = _bilinen(seri.get("buyuk"), "buyuk", t)
    o["buyuk_oran"] = b[-1] if b and _son(seri.get("buyuk"), "buyuk", t) is not None else None
    o["buyuk_degisim_4s_pct"] = (b[-1] / b[-5] - 1) * 100 if o["buyuk_oran"] is not None and len(b) >= 5 and b[-5] > 0 else None
    oi = _bilinen(seri.get("oi"), "oi", t)
    o["oi_degisim_4s_pct"] = ((oi[-1] / oi[-5] - 1) * 100 if _son(seri.get("oi"), "oi", t) is not None and len(oi) >= 5
                              and oi[-5] > 0 else None)
    tk = _bilinen(seri.get("taker"), "taker", t)
    o["taker_4s"] = sum(tk[-4:]) / 4 if _son(seri.get("taker"), "taker", t) is not None and len(tk) >= 4 else None
    o["korku_acgozluluk"] = _son(seri.get("korku"), "korku", t)
    o["r4"] = r4
    return o


def _isaret(a, e): return 1 if a else (-1 if e else 0)


def sinyaller(o):
    """Kural -> -1/0/+1. Kalabalık/fonlama/korku TERS (aşırı konumlanma tersine döner), büyük trader/taker/OI YÖN izler."""
    s = {}
    f = o.get("fonlama_pct")
    s["fonlama"] = 0 if f is None else _isaret(f <= -0.01, f >= 0.03)
    y = o.get("ls_yuzdelik")
    s["kalabalik"] = 0 if y is None else _isaret(y <= 20, y >= 80)
    d = o.get("buyuk_degisim_4s_pct")
    s["buyuk_trader"] = 0 if d is None else _isaret(d > 3, d < -3)
    oi, r4 = o.get("oi_degisim_4s_pct"), o.get("r4")
    s["oi_fiyat"] = 0 if oi is None or r4 is None or oi <= 1 else (1 if r4 > 0 else -1)
    tk = o.get("taker_4s")
    s["taker"] = 0 if tk is None else _isaret(tk > 1.08, tk < 0.92)
    k = o.get("korku_acgozluluk")
    s["korku"] = 0 if k is None else _isaret(k <= 25, k >= 75)
    u = o.get("uzman_hl") or {}
    s["uzman_hl"] = 0 if u.get("net_oran") is None or (u.get("long", 0) + u.get("short", 0)) < 3 else \
        _isaret(u["net_oran"] >= 0.3, u["net_oran"] <= -0.3)
    h = o.get("haber") or {}
    s["haber"] = 0 if h.get("duygu") is None else _isaret(h["duygu"] >= 1, h["duygu"] <= -1)
    return s


def topla(s=None, now=None, r4=None, hl_liste="hl_cuzdanlar.txt"):
    """Canlı tur: (özellikler, sinyaller). Hiçbir kaynak yoksa özellikler yine döner (hepsi None)."""
    now = now or time.time()
    seri = seriler(s)
    o = ozellik(seri, now, r4)
    try: o["uzman_hl"] = uzman_hl(s, hl_liste)
    except Exception: o["uzman_hl"] = None
    o["kaynaklar"] = sorted(seri)
    return o, sinyaller(o)
