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


def stokastik(mum, n=14, d=3):
    """(%K, %D) son değerler."""
    if len(mum) < n + d - 1: return None
    ks = []
    for j in range(len(mum) - d, len(mum)):
        p = mum[j - n + 1: j + 1]
        hh, ll = max(m[3] for m in p), min(m[4] for m in p)
        ks.append(50.0 if hh == ll else (mum[j][2] - ll) / (hh - ll) * 100)
    return ks[-1], sum(ks) / d


def cci(mum, n=20):
    if len(mum) < n: return None
    tp = [(m[3] + m[4] + m[2]) / 3 for m in mum[-n:]]
    ort = sum(tp) / n; sapma = sum(abs(x - ort) for x in tp) / n
    return 0.0 if sapma == 0 else (tp[-1] - ort) / (0.015 * sapma)


def adx(mum, n=14):
    """Wilder ADX: (adx, +DI, -DI)."""
    if len(mum) < 2 * n + 1: return None
    tr, pdm, mdm = [], [], []
    for o, m in zip(mum[:-1], mum[1:]):
        yukari, asagi = m[3] - o[3], o[4] - m[4]
        pdm.append(yukari if yukari > asagi and yukari > 0 else 0.0)
        mdm.append(asagi if asagi > yukari and asagi > 0 else 0.0)
        tr.append(max(m[3] - m[4], abs(m[3] - o[2]), abs(m[4] - o[2])))
    a_tr, a_p, a_m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])
    dx, pdi, mdi = [], 0.0, 0.0
    for i in range(n, len(tr) + 1):
        if i > n:
            a_tr = a_tr - a_tr / n + tr[i - 1]; a_p = a_p - a_p / n + pdm[i - 1]; a_m = a_m - a_m / n + mdm[i - 1]
        pdi = 100 * a_p / a_tr if a_tr else 0.0; mdi = 100 * a_m / a_tr if a_tr else 0.0
        dx.append(0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi))
    if len(dx) < n: return None
    a = sum(dx[:n]) / n
    for x in dx[n:]: a = (a * (n - 1) + x) / n
    return a, pdi, mdi


def donchian(mum, n=20):
    """Önceki n mumun (şimdiki hariç) en yüksek ve en düşüğü."""
    if len(mum) < n + 1: return None
    p = mum[-n - 1:-1]
    return max(m[3] for m in p), min(m[4] for m in p)


def supertrend(mum, n=10, k=3.0):
    """Supertrend yönü: +1 / -1."""
    if len(mum) < n + 2: return None
    tr = [max(m[3] - m[4], abs(m[3] - o[2]), abs(m[4] - o[2])) for o, m in zip(mum[:-1], mum[1:])]
    atr = sum(tr[:n]) / n
    fub = flb = None; yon = 1; onceki_k = mum[n][2]
    for i in range(n, len(tr)):
        if i > n: atr = (atr * (n - 1) + tr[i]) / n
        m = mum[i + 1]; hl2 = (m[3] + m[4]) / 2
        ub, lb = hl2 + k * atr, hl2 - k * atr
        fub = ub if fub is None or ub < fub or onceki_k > fub else fub
        flb = lb if flb is None or lb > flb or onceki_k < flb else flb
        if yon == 1 and m[2] < flb: yon = -1
        elif yon == -1 and m[2] > fub: yon = 1
        onceki_k = m[2]
    return yon


def obv_egim(mum, n=12):
    """Son n mumdaki OBV değişimi / toplam hacim: -1..+1 (alıcı/satıcı baskısı)."""
    if len(mum) < n + 1: return None
    p = mum[-n - 1:]; net = 0.0; top = 0.0
    for o, m in zip(p[:-1], p[1:]):
        h = m[5] if len(m) > 5 else 0.0
        net += h if m[2] > o[2] else (-h if m[2] < o[2] else 0.0); top += h
    return net / top if top > 0 else None


def vwap(mum, n=24):
    p = mum[-n:]
    hv = sum((m[5] if len(m) > 5 else 0.0) for m in p)
    if len(p) < n or hv <= 0: return None
    return sum((m[3] + m[4] + m[2]) / 3 * m[5] for m in p) / hv


def mfi(mum, n=14):
    if len(mum) < n + 1: return None
    art = azl = 0.0
    p = mum[-n - 1:]
    for o, m in zip(p[:-1], p[1:]):
        tp0, tp = (o[3] + o[4] + o[2]) / 3, (m[3] + m[4] + m[2]) / 3
        akis = tp * (m[5] if len(m) > 5 else 0.0)
        if tp > tp0: art += akis
        elif tp < tp0: azl += akis
    if art + azl == 0: return None
    return 100.0 if azl == 0 else 100 - 100 / (1 + art / azl)


def bb_genislik_yuzdelik(kapanis, n=20, geri=100, kaydir=0):
    """Bollinger bant genişliğinin son `geri` mum içindeki yüzdelik sırası (0 = en dar). kaydir=1: bir önceki mum."""
    son = len(kapanis) - kaydir
    if son < n + geri // 2: return None
    gen = []
    for j in range(max(n, son - geri), son + 1):
        p = kapanis[j - n:j]; ort = sum(p) / n
        gen.append(math.sqrt(sum((x - ort) ** 2 for x in p) / n) / ort)
    return sum(g < gen[-1] for g in gen) / len(gen) * 100


def toplu_kapanis(mum, adim):
    """Saatlik mumlardan `adim` saatlik kapanışlar (son grup son mumla biter)."""
    return [mum[i][2] for i in range(len(mum) - 1, -1, -adim)][::-1]


def _trend(kapanis, n, geri):
    e = ema(kapanis, n)
    if len(kapanis) < n + geri or e[-1] is None or e[-1 - geri] is None: return None, None
    return (kapanis[-1] / e[-1] - 1) * 100, (e[-1] / e[-1 - geri] - 1) * 100


def hesapla(mum):
    """Göstergeler sözlüğü. En az EN_AZ_MUM mum gerekir; uzun pencere isteyenler (günlük trend) yetersiz veride None."""
    if len(mum) < EN_AZ_MUM: raise ValueError("yetersiz mum")
    k = [m[2] for m in mum]; f = k[-1]
    e9, e21, e50 = ema(k, 9), ema(k, 21), ema(k, 50)
    mc = macd(k)
    hacim = [m[5] if len(m) > 5 else 0.0 for m in mum]
    onceki = hacim[-25:-1]
    sma24 = sum(k[-24:]) / 24
    st, ad, dc, vw, vw4 = stokastik(mum), adx(mum), donchian(mum), vwap(mum), vwap(mum[:-4])
    t4 = _trend(toplu_kapanis(mum, 4), 21, 2)
    tg = _trend(toplu_kapanis(mum, 24), 7, 1)
    return dict(
        fiyat=f,
        r4=(f / k[-5] - 1) * 100, sma24_sapma=(f / sma24 - 1) * 100,
        rsi14=rsi(k),
        macd_hist_pct=mc[2] / f * 100 if mc else None, macd_hist_onceki_pct=mc[3] / f * 100 if mc else None,
        bb_b=bollinger_b(k),
        bb_genislik_yuzdelik=bb_genislik_yuzdelik(k), bb_genislik_yuzdelik_onceki=bb_genislik_yuzdelik(k, kaydir=1),
        ema_fark_pct=(e9[-1] / e21[-1] - 1) * 100,
        ema50_sapma=(f / e50[-1] - 1) * 100, ema50_egim=(e50[-1] / e50[-5] - 1) * 100,
        atr_pct=atr_pct(mum),
        hacim_oran=hacim[-1] / (sum(onceki) / len(onceki)) if onceki and sum(onceki) > 0 else None,
        stok_k=st[0] if st else None, stok_d=st[1] if st else None,
        cci20=cci(mum),
        adx14=ad[0] if ad else None, pdi=ad[1] if ad else None, mdi=ad[2] if ad else None,
        donchian_ust_pct=(f / dc[0] - 1) * 100 if dc else None, donchian_alt_pct=(f / dc[1] - 1) * 100 if dc else None,
        supertrend=supertrend(mum),
        obv_egim=obv_egim(mum),
        vwap_sapma=(f / vw - 1) * 100 if vw else None, vwap_egim=(vw / vw4 - 1) * 100 if vw and vw4 else None,
        mfi14=mfi(mum),
        trend4s_sapma=t4[0], trend4s_egim=t4[1], trend1g_sapma=tg[0], trend1g_egim=tg[1])


def _isaret(kosul_art, kosul_eks):
    return 1 if kosul_art else (-1 if kosul_eks else 0)


def _yon_cifti(sapma, egim):
    if sapma is None or egim is None: return 0
    return _isaret(sapma > 0 and egim > 0, sapma < 0 and egim < 0)


def _esik(x, alt, ust):
    """x < alt -> +1 (aşırı satım), x > ust -> -1 (aşırı alım)."""
    return 0 if x is None else _isaret(x < alt, x > ust)


def sinyaller(g):
    """Kural adı -> -1/0/+1. Aşırı alım/satım kuralları tersine (ortalamaya dönüş), trend/kırılım kuralları yönü izler.
    Göstergesi hesaplanamayan kural 0 (fikir yok) döner."""
    s = {}
    s["rsi"] = _esik(g.get("rsi14"), 30, 70)
    h, h0 = g.get("macd_hist_pct"), g.get("macd_hist_onceki_pct")
    s["macd"] = 0 if h is None or h0 is None else _isaret(h > 0 and h > h0, h < 0 and h < h0)
    b = g.get("bb_b")
    s["bollinger"] = 0 if b is None else _isaret(b < 0, b > 1)
    s["ema_kesisim"] = 0 if g.get("ema_fark_pct") is None else (1 if g["ema_fark_pct"] > 0 else -1)
    s["trend_ema50"] = _yon_cifti(g.get("ema50_sapma"), g.get("ema50_egim"))
    s["momentum"] = _yon_cifti(g.get("r4"), g.get("sma24_sapma"))
    k, d = g.get("stok_k"), g.get("stok_d")
    s["stokastik"] = 0 if k is None or d is None else _isaret(k < 20 and k > d, k > 80 and k < d)
    s["cci"] = _esik(g.get("cci20"), -100, 100)
    a = g.get("adx14")
    s["adx_trend"] = 0 if a is None or a < 25 else (1 if g["pdi"] > g["mdi"] else -1)
    du, da = g.get("donchian_ust_pct"), g.get("donchian_alt_pct")
    s["donchian"] = 0 if du is None else _isaret(du > 0, da < 0)
    s["supertrend"] = g.get("supertrend") or 0
    o = g.get("obv_egim")
    s["obv"] = 0 if o is None else _isaret(o > 0.2, o < -0.2)
    s["vwap"] = _yon_cifti(g.get("vwap_sapma"), g.get("vwap_egim"))
    s["mfi"] = _esik(g.get("mfi14"), 20, 80)
    gy = g.get("bb_genislik_yuzdelik_onceki")
    s["sikisma_kirilim"] = 0 if gy is None or b is None or gy > 20 else _isaret(b > 1, b < 0)
    s["trend_4s"] = _yon_cifti(g.get("trend4s_sapma"), g.get("trend4s_egim"))
    s["trend_gunluk"] = _yon_cifti(g.get("trend1g_sapma"), g.get("trend1g_egim"))
    return s


KURALLAR = ("rsi", "macd", "bollinger", "ema_kesisim", "trend_ema50", "momentum", "stokastik", "cci", "adx_trend",
            "donchian", "supertrend", "obv", "vwap", "mfi", "sikisma_kirilim", "trend_4s", "trend_gunluk")


def topluluk(sinyal, agirlik):
    """Ağırlıklı ortalama sinyal, [-1, 1]. Ağırlık yoksa ya da hepsi 0 ise 0 (fikir yok)."""
    if not agirlik: return 0.0
    w = {a: max(0.0, float(v or 0)) for a, v in agirlik.items()}       # teknik + duygu kuralları birlikte olabilir
    t = sum(w.values())
    if t <= 0: return 0.0
    return sum(w[a] * sinyal.get(a, 0) for a in w) / t


def yon(skor, esik=0.2):
    return "YUKARI" if skor >= esik else ("ASAGI" if skor <= -esik else "BELIRSIZ")
