"""N18 · Seçim modeli (yalnızca standart kütüphane).

Lojistik regresyon (L2), özellikler eğitim kümesine göre standartlaştırılır; eksik değer eğitim medyanı + eksiklik
göstergesiyle doldurulur. Doğrulama ZAMANA GÖREDİR: ilk %70 ile eğitilir, son %30'da sınanır (karıştırma yok).
Seçim eşiği yalnızca eğitim kümesinde belirlenir. Kabul: sınamada seçilenlerin maliyet sonrası ortalama getirisi
'hepsini kopyala'dan büyük VE farkın %95 bootstrap güven aralığının alt sınırı sıfırın üstünde VE (20.11) yürüyen
sınama dilimlerinin çoğunda olumlu VE etiketleri karıştırılmış modellere karşı p < 0,1."""
import json, math, random, time

from nexora.ozellik import OZELLIKLER

EN_AZ_ORNEK = 500


def _sig(z): return 1 / (1 + math.exp(-max(-35, min(35, z))))


def _medyan(v):
    v = sorted(v); n = len(v)
    return 0.0 if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


class Model:
    def __init__(self, ozellikler=OZELLIKLER, l2=1.0, adim=0.1, tur=400):
        self.oz, self.l2, self.adim, self.tur = list(ozellikler), l2, adim, tur

    def _hazirla(self, X):
        satir = []
        for o in X:
            v = []
            for k in self.oz:
                x = o.get(k)
                v.append(((self.medyan[k] if x is None else x) - self.ort[k]) / self.std[k])
                v.append(1.0 if x is None else 0.0)
            satir.append(v)
        return satir

    def egit(self, X, y_getiri):
        self.medyan = {k: _medyan([o[k] for o in X if o.get(k) is not None]) for k in self.oz}
        dol = {k: [self.medyan[k] if o.get(k) is None else o[k] for o in X] for k in self.oz}
        self.ort = {k: sum(v) / len(v) for k, v in dol.items()}
        self.std = {k: (math.sqrt(sum((x - self.ort[k]) ** 2 for x in v) / len(v)) or 1.0) for k, v in dol.items()}
        A = self._hazirla(X); y = [1.0 if g > 0 else 0.0 for g in y_getiri]
        n, d = len(A), len(A[0])
        self.w, self.b = [0.0] * d, math.log((sum(y) + 1) / (n - sum(y) + 1))
        for _ in range(self.tur):
            gw, gb = [0.0] * d, 0.0
            for a, t in zip(A, y):
                e = _sig(self.b + sum(wi * ai for wi, ai in zip(self.w, a))) - t
                gb += e
                for j in range(d): gw[j] += e * a[j]
            self.b -= self.adim * gb / n
            self.w = [wi - self.adim * (g / n + self.l2 * wi / n) for wi, g in zip(self.w, gw)]
        return self

    def olasilik(self, X):
        return [_sig(self.b + sum(wi * ai for wi, ai in zip(self.w, a))) for a in self._hazirla(X)]

    def agirliklar(self):
        """Standartlaştırılmış etki (eksiklik göstergeleri hariç), büyükten küçüğe."""
        return sorted(((k, round(self.w[2 * i], 4)) for i, k in enumerate(self.oz)), key=lambda x: -abs(x[1]))

    @classmethod
    def yukle(cls, d):
        """kaydet() çıktısından modeli kurar. Eksik/bozuk alan ValueError verir."""
        try:
            m = cls(ozellikler=d["ozellikler"])
            m.w, m.b = [float(x) for x in d["w"]], float(d["b"])
            m.medyan, m.ort, m.std = dict(d["medyan"]), dict(d["ort"]), dict(d["std"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"model dosyası bozuk: {e}") from None
        if len(m.w) != 2 * len(m.oz): raise ValueError("model ağırlık sayısı tutarsız")
        return m

    def kaydet(self, yol, meta):
        with open(yol, "w") as f:
            json.dump(dict(surum=1, olusturma=time.time(), ozellikler=self.oz, w=self.w, b=self.b, medyan=self.medyan,
                           ort=self.ort, std=self.std, **meta), f, ensure_ascii=False, indent=1)


def _esik_sec(p, y, en_az_kapsam=0.2):
    """Eğitim kümesinde seçilenlerin ortalama getirisini en yükselten olasılık eşiği (en az %20 kapsam)."""
    en_iyi = (sum(y) / len(y), 0.0)
    for e in sorted(set(round(x, 3) for x in p)):
        s = [g for pi, g in zip(p, y) if pi >= e]
        if len(s) >= en_az_kapsam * len(y) and sum(s) / len(s) > en_iyi[0]: en_iyi = (sum(s) / len(s), e)
    return en_iyi[1]


def _fark(egt, sin, y_egt=None):
    """Eğitimde öğrenilen model + eşikle sınamada (seçilen ort − hepsi ort). Seçilen yoksa None."""
    X = [o for *_, o, _ in egt]; y = y_egt if y_egt is not None else [g for *_, g in egt]
    m = Model().egit(X, y); esik = _esik_sec(m.olasilik(X), y)
    ys = [g for *_, g in sin]; sec = [g for p, g in zip(m.olasilik([o for *_, o, _ in sin]), ys) if p >= esik]
    return (sum(sec) / len(sec) - sum(ys) / len(ys), len(sec)) if sec and ys else (None, 0)


ILERI_KESIMLER = (0.5, 0.6, 0.7, 0.8)    # yürüyen sınama: her kesimde o ana kadarki veriyle eğit, sonraki dilimde sına
ARALIK_SN = 3600                          # eğitim sonu ile sınama başı arası boşluk: sonucu henüz belli olmayan sinyal sızmasın
SAHTE_TUR = 20                            # etiketleri karıştırılmış (anlamsız) modeller: gerçek fark bunları geçmeli


def ileri_sinama(veri, kesimler=ILERI_KESIMLER, aralik_sn=ARALIK_SN):
    """Yürüyen (walk-forward) sınama: her dilim için dict(kesim, egitim, sinama, fark, secilen)."""
    n, out = len(veri), []
    for i, c in enumerate(kesimler):
        k = int(n * c); son = int(n * kesimler[i + 1]) if i + 1 < len(kesimler) else n
        egt = veri[:k]
        if not egt: continue
        sin = [v for v in veri[k:son] if v[0] >= egt[-1][0] + aralik_sn]
        if len(sin) < 10: continue
        f, ns = _fark(egt, sin)
        out.append(dict(kesim=c, egitim=len(egt), sinama=len(sin), fark=None if f is None else round(f, 3), secilen=ns))
    return out


def sahte_sinama(egt, sin, gercek_fark, tur=None, tohum=11):
    """Etiketler karıştırılarak eğitilen modellerin kaçı gerçek farka ulaştı (p değeri; küçük iyi)."""
    if gercek_fark is None: return None
    tur = SAHTE_TUR if tur is None else tur
    rnd = random.Random(tohum); y = [g for *_, g in egt]; ulasan = 0
    for _ in range(tur):
        k = y[:]; rnd.shuffle(k)
        f, _ = _fark(egt, sin, k)
        if f is not None and f >= gercek_fark: ulasan += 1
    return round((ulasan + 1) / (tur + 1), 3)


def degerlendir(veri, egitim_orani=0.7, bootstrap=1000, tohum=7, zorla=False, saglamlik=True):
    """veri: ozellik.veri_seti çıktısı (zamana göre sıralı). Sonuç sözlüğü ve (kabul edilirse) model döner."""
    n = len(veri)
    if n < EN_AZ_ORNEK and not zorla:
        return dict(karar="yetersiz veri", n=n, gerekli=EN_AZ_ORNEK), None
    k = int(n * egitim_orani)
    egt, sin = veri[:k], veri[k:]
    X, y = [o for *_, o, _ in egt], [g for *_, g in egt]
    Xs, ys = [o for *_, o, _ in sin], [g for *_, g in sin]
    m = Model().egit(X, y)
    esik = _esik_sec(m.olasilik(X), y)
    ps = m.olasilik(Xs)
    sec = [g for p, g in zip(ps, ys) if p >= esik]
    hepsi = sum(ys) / len(ys)
    secili = sum(sec) / len(sec) if sec else None
    rnd = random.Random(tohum); farklar = []
    idx = list(range(len(ys)))
    for _ in range(bootstrap):
        o = [rnd.choice(idx) for _ in idx]
        s = [ys[i] for i in o if ps[i] >= esik]
        if s: farklar.append(sum(s) / len(s) - sum(ys[i] for i in o) / len(o))
    farklar.sort()
    alt = farklar[int(0.025 * len(farklar))] if farklar else None
    ust = farklar[int(0.975 * len(farklar)) - 1] if farklar else None
    brier = sum((p - (1.0 if g > 0 else 0.0)) ** 2 for p, g in zip(ps, ys)) / len(ys)
    taban = sum(1 for g in y if g > 0) / len(y)
    brier_taban = sum((taban - (1.0 if g > 0 else 0.0)) ** 2 for g in ys) / len(ys)
    kalib = []
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        b = [(p, g) for p, g in zip(ps, ys) if lo <= p < lo + 0.2 or (lo == 0.8 and p == 1.0)]
        if b: kalib.append(dict(aralik=f"{lo:.1f}-{lo + 0.2:.1f}", n=len(b), tahmin=round(sum(p for p, _ in b) / len(b), 3),
                               gercek=round(sum(1 for _, g in b if g > 0) / len(b), 3)))
    # Kopyalanan cüzdanların sinyalleri (gölge/izlenen hariç): canlı filtre yalnızca bunlara uygulanır
    kp = [(p, g) for p, g, x in zip(ps, ys, Xs) if x.get("bot_kopyaladi") is not None]
    kp_sec = [g for p, g in kp if p >= esik]
    kopya = dict(n=len(kp), hepsi=round(sum(g for _, g in kp) / len(kp), 3) if kp else None, secilen=len(kp_sec),
                 secili=round(sum(kp_sec) / len(kp_sec), 3) if kp_sec else None)
    kabul = secili is not None and secili > hepsi and alt is not None and alt > 0
    ileri, p_sahte = [], None
    if saglamlik:
        # Sağlamlık (20.11): tek bir bölmede şans eseri iyi çıkmak yetmez. Yürüyen sınamada dilimlerin çoğunda seçilenler
        # 'hepsi'nden iyi olmalı VE etiketleri karıştırılmış modeller gerçek farka nadiren ulaşmalı (p < 0,1).
        ileri = ileri_sinama(veri)
        p_sahte = sahte_sinama(egt, sin, None if secili is None else secili - hepsi)
        olumlu = sum(1 for x in ileri if x["fark"] is not None and x["fark"] > 0)
        if kabul and ileri and olumlu * 2 <= len(ileri): kabul = False
        if kabul and p_sahte is not None and p_sahte >= 0.1: kabul = False
    sonuc = dict(karar="avantaj var" if kabul else "avantaj bulunamadı", n=n, egitim=len(egt), sinama=len(sin),
                 esik=esik, secilen=len(sec), sinama_hepsi_ort=round(hepsi, 3), sinama_secili_ort=None if secili is None else round(secili, 3),
                 fark_guven_araligi=None if alt is None else [round(alt, 3), round(ust, 3)],
                 brier=round(brier, 4), brier_taban=round(brier_taban, 4), kalibrasyon=kalib, agirliklar=m.agirliklar()[:10], kopya=kopya,
                 ileri=ileri, p_sahte=p_sahte)
    return sonuc, (m if kabul else None)
