"""BTC günlük trend takibi sınaması (SALT OKUNUR). 4 saatlik yön tahmini yerine yavaş ufuk: fiyat uzun vadeli
ortalamanın üstündeyse BTC'de kal, altındaysa nakde geç. Yalnızca uzun/nakit (spot cbBTC).

Dürüstlük kuralları:
- Geleceği görme yok: i. günün KAPANIŞINDAKİ sinyal (i+1). günün getirisini belirler.
- Maliyet: her pozisyon değişiminde gidiş-dönüş maliyetinin yarısı (varsayılan %0,2 gidiş-dönüş).
- Örneklem dışı: en iyi değişken verinin ilk %60'ında Sharpe'a göre seçilir, son %40'ta değerlendirilir. Tüm
  değişkenlerin sınama sonuçları da gösterilir (çok değişken denendiğini gizlememek için).
- Kıyas: aynı dönemde BTC'yi tutmak. Ölçüler: toplam getiri, yıllık bileşik getiri, en büyük düşüş, Sharpe, piyasada
  kalma oranı, işlem sayısı. Trend takibi boğa piyasasında genelde BTC tutmanın gerisinde kalır; amacı büyük düşüşleri
  kesmektir, bu yüzden en büyük düşüş ve Sharpe birlikte okunmalı.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.btc_trend"""
import math, sys, time

import requests

KLINE_URL = "https://api.binance.com/api/v3/klines"
MALIYET = 0.002
EGITIM_ORAN = 0.6
DEGISKENLER = [("sma", n) for n in (20, 50, 100, 150, 200)] + [("mom", n) for n in (30, 90, 180)]


def gunluk_mumlar(s=None, bas_ms=1502928000000):
    """BTC/USDT günlük kapanışlar [(kapanis_ts_sn, kapanis)] (2017-08-17'den bugüne, yalnızca kapanmış günler)."""
    s = s or requests.Session(); out, imlec = [], bas_ms
    while True:
        r = s.get(KLINE_URL, params={"symbol": "BTCUSDT", "interval": "1d", "limit": 1000, "startTime": imlec}, timeout=20)
        r.raise_for_status(); parca = r.json()
        if not parca: break
        out.extend((m[6] / 1000, float(m[4])) for m in parca)
        yeni = parca[-1][0] + 86_400_000
        if yeni <= imlec or len(parca) < 1000: break
        imlec = yeni
    simdi = time.time()
    return [m for m in out if m[0] <= simdi]


def sinyal(kapanis, tur, n):
    """Her gün için True/False/None (None: yeterli geçmiş yok)."""
    out = [None] * len(kapanis)
    if tur == "sma":
        top = 0.0
        for i, k in enumerate(kapanis):
            top += k
            if i >= n: top -= kapanis[i - n]
            if i >= n - 1: out[i] = k > top / n
    else:
        for i in range(n, len(kapanis)): out[i] = kapanis[i] / kapanis[i - n] > 1
    return out


def olc(kapanis, poz, bas, bit, maliyet=MALIYET):
    """[bas, bit) aralığında: poz[i] (i. gün kapanışında karar) -> i+1 getirisi."""
    deger, tepe, en_dusuk_dd = 1.0, 1.0, 0.0
    getiriler, onceki, islem, icerde = [], False, 0, 0
    for i in range(bas, min(bit, len(kapanis) - 1)):
        p = bool(poz[i])
        g = kapanis[i + 1] / kapanis[i] - 1
        gun = 1.0
        if p != onceki: gun *= 1 - maliyet / 2; islem += 1; onceki = p
        if p: gun *= 1 + g; icerde += 1
        deger *= gun; getiriler.append(gun - 1)
        tepe = max(tepe, deger); en_dusuk_dd = min(en_dusuk_dd, deger / tepe - 1)
    n = len(getiriler)
    if n == 0: return None
    ort = sum(getiriler) / n
    sd = math.sqrt(sum((x - ort) ** 2 for x in getiriler) / n) if n > 1 else 0.0
    yil = n / 365
    return dict(gun=n, getiri_pct=round((deger - 1) * 100, 1),
                yillik_pct=round((deger ** (1 / yil) - 1) * 100, 1) if yil > 0 and deger > 0 else None,
                en_buyuk_dusus_pct=round(en_dusuk_dd * 100, 1), sharpe=round(ort / sd * math.sqrt(365), 2) if sd > 0 else None,
                piyasada_pct=round(icerde / n * 100, 1), islem=islem)


def sina(mumlar, maliyet=MALIYET):
    k = [c for _, c in mumlar]
    if len(k) < 400: raise ValueError(f"yetersiz veri ({len(k)} gün)")
    bol = int(len(k) * EGITIM_ORAN)
    ilk = 200                                          # en uzun pencere dolduktan sonra başla (adil kıyas)
    tut = [True] * len(k)
    sonuc = {"tut": dict(egitim=olc(k, tut, ilk, bol, maliyet), sinama=olc(k, tut, bol, len(k), maliyet),
                         tum=olc(k, tut, ilk, len(k), maliyet))}
    for tur, n in DEGISKENLER:
        s = sinyal(k, tur, n)
        sonuc[f"{tur}{n}"] = dict(egitim=olc(k, s, ilk, bol, maliyet), sinama=olc(k, s, bol, len(k), maliyet),
                                  tum=olc(k, s, ilk, len(k), maliyet))
    adaylar = [a for a in sonuc if a != "tut" and sonuc[a]["egitim"]["sharpe"] is not None]
    secilen = max(adaylar, key=lambda a: sonuc[a]["egitim"]["sharpe"])
    s, t = sonuc[secilen]["sinama"], sonuc["tut"]["sinama"]
    daha_iyi_risk = (s["sharpe"] or -9) > (t["sharpe"] or -9) and s["en_buyuk_dusus_pct"] > t["en_buyuk_dusus_pct"]
    return dict(gun=len(k), bas=mumlar[ilk][0], bolum=mumlar[bol][0], bit=mumlar[-1][0], maliyet_pct=maliyet * 100,
                sonuc=sonuc, secilen=secilen, risk_ayarli_kanit=bool(daha_iyi_risk and s["getiri_pct"] > 0))


def rapor(r):
    tarih = lambda ts: time.strftime("%Y-%m-%d", time.gmtime(ts))
    print(f"BTC günlük · {r['gun']} gün · eğitim {tarih(r['bas'])} → {tarih(r['bolum'])} · "
          f"sınama (görülmemiş) {tarih(r['bolum'])} → {tarih(r['bit'])} · maliyet %{r['maliyet_pct']:.1f} gidiş-dönüş\n")
    print(f"{'strateji':<9}{'getiri%':>10}{'yıllık%':>9}{'en büyük düşüş%':>17}{'Sharpe':>8}{'piyasada%':>11}{'işlem':>7}   (SINAMA dönemi)")
    for ad, v in r["sonuc"].items():
        s = v["sinama"]; f = lambda x: "-" if x is None else x
        isaret = "  ← eğitimde seçilen" if ad == r["secilen"] else ""
        print(f"{ad:<9}{s['getiri_pct']:>10}{f(s['yillik_pct']):>9}{s['en_buyuk_dusus_pct']:>17}{f(s['sharpe']):>8}"
              f"{s['piyasada_pct']:>11}{s['islem']:>7}{isaret}")
    print(f"\nSEÇİLEN ({r['secilen']}): " + ("riske göre BTC tutmaktan İYİ (daha yüksek Sharpe, daha küçük düşüş, pozitif getiri)"
                                       if r["risk_ayarli_kanit"] else "görülmemiş dönemde BTC tutmaktan riske göre iyi DEĞİL"))
    t = r["sonuc"]["tut"]["tum"]; s = r["sonuc"][r["secilen"]]["tum"]
    print(f"Tüm dönem: {r['secilen']} getiri %{s['getiri_pct']}, en büyük düşüş %{s['en_buyuk_dusus_pct']} · "
          f"BTC tut getiri %{t['getiri_pct']}, en büyük düşüş %{t['en_buyuk_dusus_pct']}")


def main(argv):
    rapor(sina(gunluk_mumlar()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
