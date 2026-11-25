"""BTC gösterge sınaması (SALT OKUNUR + ağırlık dosyası). Geçmiş 1 saatlik mumlarda her kuralı 4 saatlik ufukta ölçer.

Yöntem (dürüstlük kuralları):
- Geleceği görme yok: t anındaki sinyal yalnızca t'ye kadar kapanmış mumlarla hesaplanır; sonuç t+4 saatin kapanışıdır.
- Eğitim/sınama ayrımı: ağırlıklar ilk %67'de seçilir, son %33'te (görülmemiş veri) değerlendirilir.
- Maliyet dahil: her pozisyon değişiminde gidiş-dönüş maliyetinin yarısı düşülür (varsayılan %0,2 gidiş-dönüş).
- Kıyas: aynı dönemde BTC'yi tutmak. Uzun/nakit (spot cbBTC açığa satılamaz).
- Anlamlılık: 'al' sinyallerinin isabeti, dönemin yükseliş oranına karşı z puanı. Çok kural sınandığı için şans eseri
  'iyi' görünen kuralı elemek üzere eşik kural sayısına göre yükseltilir (Bonferroni, aile hata oranı ALFA). Eşiği
  geçemeyen kuralın ağırlığı 0.
Sonuç btc_agirlik.json'a yazılır; btc_ongoru topluluk skorunu buradan alır. kanit=False ise topluluk BTC tutmayı yenemedi
demektir ve canlı kararda göstergelerin oyu sıfırlanır.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.btc_sinama [gün=90]"""
import json, math, os, sys, time
from statistics import NormalDist

from nexora import btc_gosterge as G

UFUK = 4                 # saat
PENCERE = 400            # gösterge hesabı için geriye bakılan mum (günlük trend için ~16 gün)
MALIYET = 0.002          # gidiş-dönüş (Jupiter cbBTC teklif farkı + ücret için temkinli varsayım)
EGITIM_ORAN = 2 / 3
ALFA = 0.20               # tüm kurallar için birlikte yanlış alarm olasılığı


def z_esik(kural_sayisi=None):
    """Tek yönlü Bonferroni eşiği: 17 kuralda ~2,26."""
    k = kural_sayisi or len(G.KURALLAR)
    return NormalDist().inv_cdf(1 - ALFA / k)


ESIK = 0.2


def ornekler(mum):
    """[(i, sinyaller, getiri_4s)] — getiri t kapanışından t+UFUK kapanışına."""
    out = []
    for i in range(G.EN_AZ_MUM - 1, len(mum) - UFUK):
        g = G.hesapla(mum[max(0, i - PENCERE + 1): i + 1])
        out.append((i, G.sinyaller(g), mum[i + UFUK][2] / mum[i][2] - 1))
    return out


def kural_istatistik(orn, kural):
    """'al' (+1) ve 'çık' (-1) sinyallerinin isabeti, ortalama getirisi ve z puanı."""
    n_hepsi = len(orn)
    baz = sum(r > 0 for _, _, r in orn) / n_hepsi if n_hepsi else 0.5
    al = [r for _, s, r in orn if s[kural] == 1]
    cik = [r for _, s, r in orn if s[kural] == -1]
    isabet = sum(r > 0 for r in al) / len(al) if al else None
    z = None
    if al and 0 < baz < 1:
        z = (isabet - baz) / math.sqrt(baz * (1 - baz) / len(al))
    return dict(n_al=len(al), n_cik=len(cik), isabet_al=_y(isabet), baz_yukari=_y(baz), z=_r(z),
                ort_al_pct=_r(sum(al) / len(al) * 100 if al else None, 4),
                ort_cik_pct=_r(sum(cik) / len(cik) * 100 if cik else None, 4))


def strateji(orn, pozisyon_fn, maliyet=MALIYET):
    """Örtüşmeyen 4 saatlik adımlarla uzun/nakit stratejisi. Dönüş: getiri %, BTC tutma %, işlem sayısı, adım sayısı."""
    deger, tut, poz, islem, adim = 1.0, 1.0, 0, 0, 0
    for j in range(0, len(orn), UFUK):
        _, s, r = orn[j]
        yeni = 1 if pozisyon_fn(s) else 0
        if yeni != poz: deger *= 1 - maliyet / 2; islem += 1; poz = yeni
        if poz: deger *= 1 + r
        tut *= 1 + r; adim += 1
    if poz: deger *= 1 - maliyet / 2
    return dict(getiri_pct=_r((deger - 1) * 100), tut_pct=_r((tut - 1) * 100), islem=islem, adim=adim)


def agirliklar(orn):
    """Kural ağırlığı = 'al' sinyalinin baz oranı üstündeki isabet farkı; z eşiğin altındaysa 0."""
    w, esik = {}, z_esik()
    for k in G.KURALLAR:
        st = kural_istatistik(orn, k)
        w[k] = round(max(0.0, st["isabet_al"] - st["baz_yukari"]), 4) if st["z"] is not None and st["z"] >= esik else 0.0
    return w


def sina(mum, maliyet=MALIYET):
    orn = ornekler(mum)
    if len(orn) < 300: raise ValueError(f"sınama için yetersiz veri ({len(orn)} örnek)")
    b = int(len(orn) * EGITIM_ORAN)
    egitim, sinama = orn[:b], orn[b:]
    w_egitim = agirliklar(egitim)
    topl = lambda s, w=w_egitim: G.topluluk(s, w) >= ESIK
    kurallar = {}
    for k in G.KURALLAR:
        kurallar[k] = dict(egitim=kural_istatistik(egitim, k), sinama=kural_istatistik(sinama, k),
                           strateji_sinama=strateji(sinama, lambda s, k=k: s[k] == 1, maliyet))
    ts = strateji(sinama, topl, maliyet)
    kanit = any(w_egitim.values()) and ts["getiri_pct"] > ts["tut_pct"] and ts["getiri_pct"] > 0
    return dict(
        ts=time.time(), mum=len(mum), ornek=len(orn), egitim_ornek=len(egitim), sinama_ornek=len(sinama),
        ufuk_saat=UFUK, maliyet_pct=maliyet * 100, esik=ESIK, z_esik=round(z_esik(), 2), kural_sayisi=len(G.KURALLAR),
        kurallar=kurallar,
        egitim_agirlik=w_egitim,
        topluluk_sinama=ts,
        kanit=bool(kanit),
        agirlik=agirliklar(orn),              # canlı kullanım: tüm veriyle (sınama sonucu yukarıda ayrı raporlandı)
    )


def _r(x, n=2): return None if x is None else round(x, n)
def _y(x): return None if x is None else round(x * 100, 1)


def yaz(sonuc, yol="btc_agirlik.json"):
    with open(yol + ".tmp", "w") as f: json.dump(sonuc, f, ensure_ascii=False, indent=1)
    os.replace(yol + ".tmp", yol)


def rapor(s):
    print(f"{s['mum']} saatlik mum · {s['ornek']} örnek (eğitim {s['egitim_ornek']}, sınama {s['sinama_ornek']}) · "
          f"ufuk {s['ufuk_saat']} saat · maliyet %{s['maliyet_pct']:.2f} gidiş-dönüş · {s['kural_sayisi']} kural, "
          f"anlamlılık eşiği z ≥ {s['z_esik']}\n")
    print(f"{'kural':<16}{'al n':>6}{'isabet%':>9}{'baz%':>7}{'z':>7}{'strateji%':>11}{'BTC tut%':>10}{'işlem':>7}   (görülmemiş son dönem)")
    for k, v in s["kurallar"].items():
        st, sr = v["sinama"], v["strateji_sinama"]
        f = lambda x: "-" if x is None else x
        print(f"{k:<16}{st['n_al']:>6}{f(st['isabet_al']):>9}{f(st['baz_yukari']):>7}{f(st['z']):>7}"
              f"{sr['getiri_pct']:>11}{sr['tut_pct']:>10}{sr['islem']:>7}")
    t = s["topluluk_sinama"]
    sifirsiz = lambda w: {k: v for k, v in w.items() if v} or "hiçbir kural eşiği geçmedi"
    print(f"\nTopluluk (eğitim ağırlıkları: {sifirsiz(s['egitim_agirlik'])}):")
    print(f"  sınama dönemi getirisi %{t['getiri_pct']} · BTC tutma %{t['tut_pct']} · {t['islem']} işlem")
    print(f"  KANIT: {'VAR, topluluk görülmemiş veride BTC tutmayı ve sıfırı geçti' if s['kanit'] else 'YOK, topluluk BTC tutmayı geçemedi; göstergeler kararlarda oy kullanmaz (YZ yalnızca bilgi olarak görür)'}")
    print(f"  Canlı ağırlıklar (tüm veri): {sifirsiz(s['agirlik'])}")


def main(argv):
    from nexora.btc_ongoru import gecmis_mumlar
    gun = float(argv[1]) if len(argv) > 1 else 90.0
    mum = gecmis_mumlar(time.time() - gun * 86400, time.time())
    mum = [m for m in mum if m[1] <= time.time()]          # yalnızca kapanmış mumlar
    s = sina(mum)
    yaz(s)
    rapor(s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
