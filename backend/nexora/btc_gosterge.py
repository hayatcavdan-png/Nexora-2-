"""BTC teknik göstergeleri ve sinyal kuralları (SAF: ağ ve veritabanı yok).

Mum: (acilis_ts, kapanis_ts, kapanis, yuksek, dusuk, hacim). Göstergeler yalnızca o ana kadar KAPANMIŞ mumlardan hesaplanır
(geleceği görme yok). Her kural -1 (aşağı/çık), 0 (fikir yok), +1 (yukarı/gir) üretir. Hangi kuralın gerçekten işe
yaradığına btc_sinama karar verir; buradaki eşikler ders kitabı değerleridir, kanıt değildir."""
import math

EN_AZ_MUM = 60


def ema(seri, n):
    """Üstel hareketli ortalama; ilk n-1 değer None. Tohum: ilk n değerin basit ortalaması."""
    out = [None] * len(seri)
    if len(seri) < n: return out
    k = 2 / (n + 1)
    e = sum(seri[:n]) / n; out[n - 1] = e
    for i in range(n, len(seri)):
        e = seri[i] * k + e * (1 - k); out[i] = e
    return out


def rsi(kapanis, n=14):
    """Wilder RSI (son değer)."""
    if len(kapanis) <= n: return None
    d = [kapanis[i] - kapanis[i - 1] for i in range(1, len(kapanis))]
    art = sum(max(x, 0) for x in d[:n]) / n
    azl = sum(max(-x, 0) for x in d[:n]) / n
    for x in d[n:]:
        art = (art * (n - 1) + max(x, 0)) / n
        azl = (azl * (n - 1) + max(-x, 0)) / n
    if azl == 0: return 100.0
    return 100 - 100 / (1 + art / azl)


def macd(kapanis, hizli=12, yavas=26, sinyal=9):
    """(macd, sinyal, histogram, önceki histogram) son değerler; fiyat ölçeğinde."""
    eh, ey = ema(kapanis, hizli), ema(kapanis, yavas)
    m = [a - b for a, b in zip(eh, ey) if a is not None and b is not None]
    s = ema(m, sinyal)
    if len(m) < sinyal + 1 or s[-1] is None or s[-2] is None: return None
    return m[-1], s[-1], m[-1] - s[-1], m[-2] - s[-2]


def bollinger_b(kapanis, n=20, k=2.0):
    """%B: 0 = alt bant, 1 = üst bant."""
    if len(kapanis) < n: return None
    p = kapanis[-n:]; ort = sum(p) / n
    sd = math.sqrt(sum((x - ort) ** 2 for x in p) / n)
    if sd == 0: return 0.5
    return (kapanis[-1] - (ort - k * sd)) / (2 * k * sd)


def atr_pct(mum, n=14):
    """Ortalama gerçek aralık, fiyatın yüzdesi olarak."""
    if len(mum) <= n: return None
    tr = [max(m[3] - m[4], abs(m[3] - o[2]), abs(m[4] - o[2])) for o, m in zip(mum[:-1], mum[1:])]
    a = sum(tr[:n]) / n
    for x in tr[n:]: a = (a * (n - 1) + x) / n
    return a / mum[-1][2] * 100


def hesapla(mum):
    """Göstergeler sözlüğü. En az EN_AZ_MUM mum gerekir."""
    if len(mum) < EN_AZ_MUM: raise ValueError("yetersiz mum")
    k = [m[2] for m in mum]; f = k[-1]
    e9, e21, e50 = ema(k, 9), ema(k, 21), ema(k, 50)
    mc = macd(k)
    hacim = [m[5] if len(m) > 5 else 0.0 for m in mum]
    onceki = hacim[-25:-1]
    sma24 = sum(k[-24:]) / 24
    return dict(
        fiyat=f,
        r4=(f / k[-5] - 1) * 100, sma24_sapma=(f / sma24 - 1) * 100,
        rsi14=rsi(k),
        macd_hist_pct=mc[2] / f * 100 if mc else None, macd_hist_onceki_pct=mc[3] / f * 100 if mc else None,
        bb_b=bollinger_b(k),
        ema_fark_pct=(e9[-1] / e21[-1] - 1) * 100,
        ema50_sapma=(f / e50[-1] - 1) * 100, ema50_egim=(e50[-1] / e50[-5] - 1) * 100,
        atr_pct=atr_pct(mum),
        hacim_oran=hacim[-1] / (sum(onceki) / len(onceki)) if onceki and sum(onceki) > 0 else None)


def _isaret(kosul_art, kosul_eks):
    return 1 if kosul_art else (-1 if kosul_eks else 0)


def sinyaller(g):
    """Kural adı -> -1/0/+1. Aşırı alım/satım kuralları tersine (ortalamaya dönüş), trend kuralları yönü izler."""
    s = {}
    s["rsi"] = 0 if g["rsi14"] is None else _isaret(g["rsi14"] < 30, g["rsi14"] > 70)
    h, h0 = g["macd_hist_pct"], g["macd_hist_onceki_pct"]
    s["macd"] = 0 if h is None else _isaret(h > 0 and h > h0, h < 0 and h < h0)
    s["bollinger"] = 0 if g["bb_b"] is None else _isaret(g["bb_b"] < 0, g["bb_b"] > 1)
    s["ema_kesisim"] = 1 if g["ema_fark_pct"] > 0 else -1
    s["trend_ema50"] = _isaret(g["ema50_sapma"] > 0 and g["ema50_egim"] > 0, g["ema50_sapma"] < 0 and g["ema50_egim"] < 0)
    s["momentum"] = _isaret(g["r4"] > 0 and g["sma24_sapma"] > 0, g["r4"] < 0 and g["sma24_sapma"] < 0)
    return s


KURALLAR = ("rsi", "macd", "bollinger", "ema_kesisim", "trend_ema50", "momentum")


def topluluk(sinyal, agirlik):
    """Ağırlıklı ortalama sinyal, [-1, 1]. Ağırlık yoksa ya da hepsi 0 ise 0 (fikir yok)."""
    if not agirlik: return 0.0
    w = {a: max(0.0, float(agirlik.get(a, 0) or 0)) for a in KURALLAR}
    t = sum(w.values())
    if t <= 0: return 0.0
    return sum(w[a] * sinyal.get(a, 0) for a in KURALLAR) / t


def yon(skor, esik=0.2):
    return "YUKARI" if skor >= esik else ("ASAGI" if skor <= -esik else "BELIRSIZ")
