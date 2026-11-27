"""Takip eden zarar durdurma (trailing stop) sınaması (SALT OKUNUR). "Zirveden %X geri düşünce sat" kuralı olsaydı ne olurdu?

Kâr alma sınaması (kar_al_sinama) sabit eşiğin büyük kazananları kestiğini gösterdi (27.11). Takip eden stop büyük
kazananı kesmez: fiyat yükseldikçe çıkış seviyesi de yükselir. Sınamak için fiyatın SIRALI yolu gerekir; bu yüzden
27.11'den itibaren her açık pozisyonun 2 dakikalık gerçek satış teklifi ölçümü pos_yol tablosuna yazılır.

Yöntem:
- Kural (X, A): pozisyon en az %A kâr gördükten sonra (A=0: hemen), değeri zirvesinden %X düşünce satılır.
  Değer oranı: (1 + pct/100) / (1 + zirve/100) − 1 ≤ −X/100. Karar yalnızca o ana kadar görülen ölçümlere dayanır.
- Tetiklenirse sonuç: tetikleyen ölçümdeki getiri − kayma (varsayılan 1 puan). Tetiklenmezse gerçek sonucu korunur.
- Yalnızca yolu kaydedilmiş (27.11 sonrası açılan) kapanmış pozisyonlar kullanılır.
- Aşırı uyum kontrolü: zamanca ilk yarıda en iyi (X, A) seçilir, görülmemiş ikinci yarıda sınanır.
Geçmiş sonuç garanti değildir.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.iz_sinama [--kayma 1]"""
import sqlite3, sys

GERI = (10, 15, 20, 25, 30, 40)
AKTIF = (0, 10, 20, 30)
EN_AZ = 30


def sonuc(gercek_pct, yol, geri, aktif, kayma):
    """yol: [pct] zaman sırasıyla. Dönüş: (getiri, tetiklendi_mi)."""
    if geri is None: return gercek_pct, False
    zirve = None
    for p in yol:
        if zirve is not None and zirve >= aktif and (1 + p / 100) / (1 + zirve / 100) - 1 <= -geri / 100:
            return p - kayma, True
        zirve = p if zirve is None else max(zirve, p)
    return gercek_pct, False


def sina(poz, kayma=1.0, kurallar=None):
    """poz: [(cost, pnl, closed_ts, yol)]. Dönüş: [dict(geri, aktif, n, tetik, toplam, ort_pct, kazanma)]."""
    kurallar = kurallar or [(None, None)] + [(g, a) for a in AKTIF for g in GERI]
    out = []
    for g, a in kurallar:
        rs = []; top = tetik = kaz = 0
        for c, p, _, yol in poz:
            if not c or p is None: continue
            r, t = sonuc(p / c * 100, yol, g, a, kayma)
            tetik += t; rs.append(r); top += r * c / 100; kaz += int(r > 0)
        n = len(rs)
        out.append(dict(geri=g, aktif=a, n=n, tetik=tetik, toplam=round(top, 2),
                        ort_pct=round(sum(rs) / n, 2) if n else None, kazanma=round(kaz * 100 / n, 1) if n else None))
    return out


def ileri_sinama(poz, kayma=1.0):
    s = sorted([x for x in poz if x[0] and x[1] is not None], key=lambda x: x[2] or 0)
    if len(s) < EN_AZ: return None
    a, b = s[:len(s) // 2], s[len(s) // 2:]
    en = max((x for x in sina(a, kayma) if x["geri"] is not None), key=lambda x: x["toplam"])
    iki = sina(b, kayma, [(None, None), (en["geri"], en["aktif"])])
    return dict(secilen=(en["geri"], en["aktif"]), ilk=en, ikinci=iki[1], yok_ikinci=iki[0])


def oku(db):
    poz = []
    for iz, c, p, ts in db.execute("""SELECT id, cost, pnl, closed_ts FROM pos_iz WHERE closed_ts IS NOT NULL
                                      AND id IN (SELECT DISTINCT iz_id FROM pos_yol)"""):
        yol = [r[0] for r in db.execute("SELECT pct FROM pos_yol WHERE iz_id=? ORDER BY ts", (iz,))]
        poz.append((c, p, ts, yol))
    return poz


def main(argv):
    a = argv[1:]; kayma = 1.0
    if "--kayma" in a: kayma = float(a[a.index("--kayma") + 1])
    db = sqlite3.connect("file:nexora_paper.db?mode=ro", uri=True)
    poz = oku(db)
    print(f"Fiyat yolu kayıtlı {len(poz)} kapanmış pozisyon · kayma {kayma} puan")
    if len(poz) < EN_AZ:
        print(f"Henüz yetersiz: en az {EN_AZ} pozisyon gerekir (yol kaydı 27.11'de başladı). Birkaç gün sonra yeniden çalıştırın.")
        return 0
    print(f"\n{'kural':<22}{'tetik':>7}{'toplam $':>10}{'ort %':>8}{'kazanma %':>11}")
    f = lambda x: "-" if x is None else x
    for s in sorted(sina(poz, kayma), key=lambda x: -x["toplam"])[:15]:
        ad = "yok" if s["geri"] is None else f"zirveden %{s['geri']} (≥%{s['aktif']})"
        print(f"{ad:<22}{s['tetik']:>7}{s['toplam']:>10}{f(s['ort_pct']):>8}{f(s['kazanma']):>11}")
    yok = sina(poz, kayma, [(None, None)])[0]
    print(f"(kuralsız: {yok['toplam']} $)")
    w = ileri_sinama(poz, kayma)
    if w:
        g, ak = w["secilen"]
        print(f"\nİLERİ SINAMA: ilk yarıda seçilen 'zirveden %{g}, ≥%{ak} kârdan sonra' → görülmemiş ikinci yarıda "
              f"{w['ikinci']['toplam']} $ (kuralsız {w['yok_ikinci']['toplam']} $, {w['ikinci']['n']} pozisyon)")
    print("Not: karar ileri sınamaya göre verilir; tablo en iyiden kötüye sıralıdır (aşırı uyum içerebilir).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
