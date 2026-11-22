"""Geliştirme 3 (PROFIT ENGINE V1): çıkış yöntemlerinin SALT simülasyonu.

Yöntemler (her biri bağımsız, aynı giriş ve aynı fiyat yolu üzerinde karşılaştırılır):
  kaynak   — kaynak cüzdan satınca çık (ulaşma gecikmesi dahil ilk gözlem).
  sure     — MAKS_SN dolunca çık.
  kademe   — KADEME1_PCT kârda yarısını sat; kalanı KADEME2_PCT kârda veya MAKS_SN'de sat (ağırlıklı getiri).
  iz       — zirveden IZ_PCT geri düşünce çık (takip eden zarar durdurma).
  erken    — giriş fiyatının ZARAR_PCT altına inince çık; hiç gözlem yoksa (likidite boşluğu) 'satılamadı'.

KURALLAR
- Her karar yalnızca karar anına kadar gözlenen fiyatlara dayanır (ileriye bakılmaz; test edilir).
- Gözlem olmayan çıkış 'satılamadı' sayılır; kâr/zarar olarak yazılmaz, 'açık' ayrı raporlanır.
- Gerçekleşmemiş kâr ile gerçekleşmiş kâr ayrı alanlarda tutulur.
- Stop-loss seviyesi garanti değildir: tetikleme, ilk gözlemlenen (muhtemelen daha kötü) fiyattan yapılır; bu kayma
  raporda ayrıca görünür (`kayma_pct`).
- Çıkış maliyeti CIKIS_MALIYET_PCT ve giriş maliyeti (girdi tarafından verilir) düşülür.
SALT SİMÜLASYON: işlem açmaz. CIKIS_MOD varsayılan 'kapali'.
"""
import os

KADEME1_PCT = float(os.getenv("CIKIS_KADEME1_PCT", "20"))
KADEME2_PCT = float(os.getenv("CIKIS_KADEME2_PCT", "50"))
IZ_PCT = float(os.getenv("CIKIS_IZ_PCT", "15"))
ZARAR_PCT = float(os.getenv("CIKIS_ZARAR_PCT", "25"))
MAKS_SN = int(os.getenv("CIKIS_MAKS_SN", "86400"))
CIKIS_MALIYET_PCT = float(os.getenv("CIKIS_MALIYET_PCT", "1.0"))
CIKIS_MOD = os.getenv("CIKIS_MOD", "kapali")                 # kapali | rapor


def _ilk(yollar, ts, son_ts=None):
    """ts ve sonrasındaki ilk gözlem (son_ts varsa o sınıra kadar)."""
    for t, p in yollar:
        if t >= ts and (son_ts is None or t <= son_ts): return (t, p)
    return None


def _net(brut_pct, giris_maliyet):
    return round(brut_pct - giris_maliyet - CIKIS_MALIYET_PCT, 3)


def simule(giris_ts, giris_fiyat, yollar, kaynak_satis_ts=None, giris_maliyet_pct=2.0):
    """yollar: giriş sonrası fiyat gözlemleri [(ts, fiyat)] artan sıralı.
    Dönüş: {yontem: dict(durum='kapandi'|'acik'|'satilamadi', cikis_ts, cikis_fiyat, brut_pct, getiri_net, kayma_pct, neden)}"""
    son_ts = giris_ts + MAKS_SN
    out = {}

    def kapat(ad, g, neden, referans=None):
        if g is None:
            out[ad] = dict(durum="satilamadi", cikis_ts=None, cikis_fiyat=None, brut_pct=None, getiri_net=None, kayma_pct=None,
                           neden=neden or "çıkış gözlemi yok")
            return
        t, p = g
        brut = (p / giris_fiyat - 1) * 100
        kayma = None if referans is None else round((p / referans - 1) * 100, 3)
        out[ad] = dict(durum="kapandi", cikis_ts=t, cikis_fiyat=p, brut_pct=round(brut, 3),
                       getiri_net=_net(brut, giris_maliyet_pct), kayma_pct=kayma, neden=neden)

    # kaynak satışı
    if kaynak_satis_ts is None:
        out["kaynak"] = dict(durum="acik", cikis_ts=None, cikis_fiyat=None, brut_pct=None, getiri_net=None, kayma_pct=None,
                             neden="kaynak satış görmedi")
    else:
        kapat("kaynak", _ilk(yollar, kaynak_satis_ts, son_ts), "kaynak sattı", referans=None)

    # süre
    kapat("sure", _ilk(yollar, son_ts), "süre doldu", referans=None)

    # kademeli kâr alma
    h1 = giris_fiyat * (1 + KADEME1_PCT / 100)
    h2 = giris_fiyat * (1 + KADEME2_PCT / 100)
    g1 = next(((t, p) for t, p in yollar if p >= h1 and t <= son_ts), None)
    if g1 is None:
        kapat("kademe", _ilk(yollar, son_ts), "kademe hedefine ulaşmadı; süre doldu")
    else:
        g2 = next(((t, p) for t, p in yollar if t >= g1[0] and p >= h2 and t <= son_ts), None)
        kalan = g2 if g2 else _ilk(yollar, son_ts)
        if kalan is None:
            out["kademe"] = dict(durum="satilamadi", cikis_ts=None, cikis_fiyat=None, brut_pct=None, getiri_net=None,
                                 kayma_pct=None, neden="kalan pozisyon satılamadı")
        else:
            b1 = (g1[1] / giris_fiyat - 1) * 100
            b2 = (kalan[1] / giris_fiyat - 1) * 100
            brut = 0.5 * b1 + 0.5 * b2
            out["kademe"] = dict(durum="kapandi", cikis_ts=kalan[0], cikis_fiyat=kalan[1], brut_pct=round(brut, 3),
                                 getiri_net=_net(brut, giris_maliyet_pct), kayma_pct=None,
                                 neden="yarı %%%d'de, kalan %s" % (KADEME1_PCT, "%%%d'de" % KADEME2_PCT if g2 else "süre sonunda"))

    # takip eden zarar durdurma (iz)
    zirve = giris_fiyat
    iz_g = None
    for t, p in yollar:
        if t > son_ts: break
        zirve = max(zirve, p)
        if p <= zirve * (1 - IZ_PCT / 100):
            iz_g = (t, p, zirve)
            break
    if iz_g:
        t, p, z = iz_g
        kapat("iz", (t, p), f"zirveden %{IZ_PCT:.0f} düşüş", referans=z * (1 - IZ_PCT / 100))
    else:
        kapat("iz", _ilk(yollar, son_ts), "iz durdurma tetiklenmedi; süre doldu")

    # erken zarar çıkışı (likidite boşluğu dahil)
    z_esik = giris_fiyat * (1 - ZARAR_PCT / 100)
    erken = next(((t, p) for t, p in yollar if t <= son_ts and p <= z_esik), None)
    if erken:
        kapat("erken", erken, f"giriş fiyatının %{ZARAR_PCT:.0f} altı", referans=z_esik)
    else:
        kapat("erken", _ilk(yollar, son_ts), "zarar eşiği görülmedi; süre doldu")
    return out


def ozetle(sonuclar):
    """Birden çok pozisyonun sonuçlarından yöntem başına özet. Açık ve satılamayanlar ayrı sayılır, kâr/zarara katılmaz."""
    out = {}
    for y in ("kaynak", "sure", "kademe", "iz", "erken"):
        rows = [r[y] for r in sonuclar if y in r]
        kap = [x for x in rows if x["durum"] == "kapandi" and x["getiri_net"] is not None]
        out[y] = dict(pozisyon=len(rows), kapandi=len(kap),
                      acik=sum(1 for x in rows if x["durum"] == "acik"),
                      satilamadi=sum(1 for x in rows if x["durum"] == "satilamadi"),
                      ort_net=round(sum(x["getiri_net"] for x in kap) / len(kap), 3) if kap else None,
                      kazanma=round(100.0 * sum(1 for x in kap if x["getiri_net"] > 0) / len(kap), 1) if kap else None)
    return out
