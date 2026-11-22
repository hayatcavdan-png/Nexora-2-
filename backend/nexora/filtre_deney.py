"""Geliştirme 5 (PROFIT ENGINE V1): sinyal filtresinin GÜVENLİ değerlendirme aracı. SALT DENEY; işlem açmaz.

Amaç: bir filtrenin (ör. 'yalnızca X özelliği eşiğin üstündeki sinyallerin kopyalanması') maliyet sonrası net getiriyi
gerçekten artırıp artırmadığını, sızıntısız ve zamana göre ayrılmış (walk-forward) testlerle ölçmek.

KURALLAR (brief'ten)
- Özellikler yalnızca KARAR ANINA kadar bilinen bilgilerden üretilir. ozellik() karar anından sonraki bir alanı
  görürse hata verir (sızıntı koruması; test edilir).
- Eğitim ve test zamana göre ayrılır (walk-forward, genişleyen pencere). Test dönemi eğitimde ASLA kullanılmaz.
- Sonuçlar maliyet sonrası net getiridir (olay kaydındaki 'net' alanı; hesap çağıranın sorumluluğunda).
- Eşik yalnızca eğitim dilimi üzerinde seçilir; test dilimi yalnızca raporlanır (yeniden ayarlanmaz).
- Örneklem yetersizse ya da güven aralığı sıfırı kapsıyorsa: 'MODEL AVANTAJI KANITLANMADI'.
- Model yoksa / eğitim başarısızsa: filtre devreye girmez, TÜM sinyaller geçer ve bu açıkça raporlanır
  (sessizce onaylamak yerine açık bayrak). Dil modelleri işlem yetkisi almaz; bu modül yalnızca sayısal değerlendirir.
- Varsayılan FILTRE_MOD=kapali; canlıya bağlanmaz. Gölge (rapor) modu için yalnızca okuma yapar.
"""
import os, random

MIN_EGITIM = int(os.getenv("FILTRE_MIN_EGITIM", "30"))
MIN_TEST = int(os.getenv("FILTRE_MIN_TEST", "30"))
FOLD = int(os.getenv("FILTRE_FOLD", "4"))
ONYUKLEME = 500
FILTRE_MOD = os.getenv("FILTRE_MOD", "kapali")               # kapali | rapor


class SizintiHatasi(ValueError):
    pass


def ozellik(olay, karar_ts):
    """Karar anında bilinen özellikler. olay: dict(sinyal_ts, ulasma_ts, likidite_usd, kayma_pct, cuzdan_skor, token_yas_sn, ...).
    Karar anından sonra oluşmuş bir zaman damgası varsa SizintiHatasi."""
    for alan in ("ulasma_ts", "sinyal_ts"):
        if olay.get(alan, 0) > karar_ts:
            raise SizintiHatasi(f"{alan} karar anından sonra: sızıntı")
    return dict(
        alim_yasi=karar_ts - olay["sinyal_ts"],
        gecikme=olay["ulasma_ts"] - olay["sinyal_ts"],
        likidite=olay.get("likidite_usd", 0.0),
        kayma=olay.get("kayma_pct", 0.0),
        cuzdan_skor=olay.get("cuzdan_skor", 0.0),
        token_yas=olay.get("token_yas_sn", 0.0),
    )


def walk_forward(olaylar, fold=FOLD):
    """Zamana göre sıralı olaylar; genişleyen eğitim penceresi, her fold'da sonraki dilim test. Dönüş: fold listesi."""
    s = sorted(olaylar, key=lambda o: o["ulasma_ts"])
    n = len(s)
    if n < (fold + 1) * 2: return []
    blok = n // (fold + 1)
    out = []
    for k in range(1, fold + 1):
        egit = s[: blok * k]
        test = s[blok * k: blok * (k + 1)]
        out.append((egit, test))
    return out


def _ortalama(xs):
    return sum(xs) / len(xs) if xs else None


def esik_sec(egitim, ozellik_adi, adaylar=10):
    """Eğitim dilimi üzerinde tek boyutlu eşik: eşik üstündeki olayların ortalama net getirisini maksimize eder.
    Yetersiz eğitim örneğinde None (filtre yok)."""
    if len(egitim) < MIN_EGITIM: return None
    degerler = sorted(o["_f"][ozellik_adi] for o in egitim)
    en_iyi, en_v = None, None
    for i in range(1, adaylar):
        e = degerler[int(len(degerler) * i / adaylar)]
        ust = [o["net"] for o in egitim if o["_f"][ozellik_adi] >= e]
        if len(ust) < MIN_EGITIM // 2: continue
        v = _ortalama(ust)
        if en_v is None or v > en_v: en_iyi, en_v = e, v
    return en_iyi


def degerlendir(olaylar, ozellik_adi="likidite", fold=FOLD, seed=7):
    """Ana değerlendirme. olaylar: dict(sinyal_ts, ulasma_ts, net, ... + özellik alanları).
    Dönüş: dict(durum, karar, folds, baz_ort, filtre_ort, fark_ci, test_n, bayrak)."""
    for o in olaylar:
        o["_f"] = ozellik(o, o["ulasma_ts"])          # karar anı = ulaşma anı
    folds = walk_forward(olaylar, fold)
    if not folds:
        return dict(durum="yetersiz", karar="MODEL AVANTAJI KANITLANMADI (örneklem yetersiz)", folds=[], test_n=0,
                    bayrak="filtre devre dışı: tüm sinyaller geçer", baz_ort=None, filtre_ort=None, fark_ci=None)
    rapor, baz_t, fil_t = [], [], []
    for egit, test in folds:
        e = esik_sec(egit, ozellik_adi)
        if e is None:
            rapor.append(dict(esik=None, test_n=len(test), aciklama="eğitim yetersiz; filtre yok"))
            baz_t += [o["net"] for o in test]; fil_t += [o["net"] for o in test]
            continue
        gecen = [o["net"] for o in test if o["_f"][ozellik_adi] >= e]
        baz = [o["net"] for o in test]
        rapor.append(dict(esik=round(e, 6), test_n=len(test), gecen=len(gecen), baz=round(_ortalama(baz), 4),
                          filtre=round(_ortalama(gecen), 4) if gecen else None))
        baz_t += baz; fil_t += gecen
    fark = []
    rnd = random.Random(seed)
    if fil_t and baz_t:
        for _ in range(ONYUKLEME):
            s1 = [rnd.choice(fil_t) for _ in fil_t]; s2 = [rnd.choice(baz_t) for _ in baz_t]
            fark.append(_ortalama(s1) - _ortalama(s2))
        fark.sort()
        ci = (round(fark[int(0.025 * ONYUKLEME)], 4), round(fark[int(0.975 * ONYUKLEME) - 1], 4))
    else:
        ci = None
    if len(fil_t) < MIN_TEST or ci is None:
        karar = "MODEL AVANTAJI KANITLANMADI (örneklem yetersiz)"; durum = "yetersiz"
    elif ci[0] > 0:
        karar = "AVANTAJ GÖRÜLDÜ: gölge doğrulama gerekli (henüz işlem yetkisi yok)"; durum = "gorulen"
    else:
        karar = "MODEL AVANTAJI KANITLANMADI (güven aralığı sıfırı kapsıyor)"; durum = "kanitlanmadi"
    return dict(durum=durum, karar=karar, folds=rapor, test_n=len(fil_t),
                baz_ort=round(_ortalama(baz_t), 4) if baz_t else None,
                filtre_ort=round(_ortalama(fil_t), 4) if fil_t else None, fark_ci=ci, bayrak=None)
