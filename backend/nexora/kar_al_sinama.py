"""Kâr alma eşiği sınaması (SALT OKUNUR). "Pozisyon %20 kârdaydı, kaçırdık" sorusunu kendi kopya verimizle yanıtlar:
"kâr %X'e ulaşınca sat" (tamamını ya da yarısını) kuralı olsaydı kapanmış pozisyonlar ne getirirdi?

Yöntem:
- Her kapanmış pozisyonun ömrü boyunca 2 dakikada bir GERÇEK satış teklifiyle ölçülen en iyi anı (max_pct, satış ücreti
  dahil) ve en kötü anı (min_pct) bilinir. Canlı kural da 2 dakikalık ölçümde tetikleneceği için max_pct ≥ X ise kural
  satardı; sonuç X − kayma sayılır (kayma: tetiklendikten sonra satışa kadar fiyatın kaçması, varsayılan 1 puan).
- Yarım: %X'te yarısı satılır, kalan yarı gerçek sonucunu alır.
- Zarar kesme (%40) ile çakışma: hem max ≥ X hem min ≤ −40 olan pozisyonda hangisinin önce olduğu bilinmez;
  TEMKİNLİ sayım zarar kesmenin önce olduğunu varsayar (o pozisyonda kural kazandırmaz). İyimser sayım ayrıca yazılır.
- Aşırı uyum kontrolü: pozisyonlar zamana göre ikiye bölünür; eşik ilk yarıda seçilir, ikinci yarıda (görülmemiş) sınanır.
Sınır: 2 dakikada bir ölçüm; arada yükselip düşen fiyatı görmez (bu, kuralın canlıda da göremeyeceği fiyattır).
Geçmiş sonuç garanti değildir.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.kar_al_sinama [gün=0 (hepsi)] [--kayma 1]"""
import sqlite3, sys, time

ESIKLER = (5, 8, 10, 15, 20, 25, 30, 40, 50, 75, 100)
ZARAR_KESME = 40.0


def sonuc(c, p, mn, mx, esik, yarim, kayma, iyimser):
    """Tek pozisyonun kural altındaki getirisi (%). Dönüş: (getiri, tetiklendi_mi)."""
    r = p / c * 100
    if esik is None or mx is None or mx < esik: return r, False
    if not iyimser and mn is not None and mn <= -ZARAR_KESME: return r, False      # zarar kesme önce olmuş olabilir
    al = esik - kayma
    return ((al + r) / 2 if yarim else al), True


def sina(satirlar, kayma=1.0, yarim=False, iyimser=False, esikler=ESIKLER):
    """satirlar: [(cost, pnl, min_pct, max_pct, closed_ts)]. Dönüş: [dict(esik, n, tetik, kacirilan, toplam, ort_pct, kazanma)]."""
    out = []
    for e in (None,) + tuple(esikler):
        rs = []; top = tetik = kacir = kaz = 0
        for c, p, mn, mx, _ in satirlar:
            if not c or p is None: continue
            r, t = sonuc(c, p, mn, mx, e, yarim, kayma, iyimser)
            tetik += t; kacir += int(t and p / c * 100 > r)          # kural, sonunda daha iyi kapanacak pozisyonu erken sattı
            rs.append(r); top += r * c / 100; kaz += int(r > 0)
        n = len(rs)
        out.append(dict(esik=e, n=n, tetik=tetik, kacirilan=kacir, toplam=round(top, 2),
                        ort_pct=round(sum(rs) / n, 2) if n else None, kazanma=round(kaz * 100 / n, 1) if n else None))
    return out


def ileri_sinama(satirlar, kayma=1.0, yarim=False):
    """Zamana göre ilk yarıda en iyi eşik seçilir, ikinci yarıda sınanır. Dönüş: dict(secilen, ilk, ikinci, yok_ikinci)."""
    s = sorted([x for x in satirlar if x[0] and x[1] is not None], key=lambda x: x[4] or 0)
    if len(s) < 20: return None
    a, b = s[:len(s) // 2], s[len(s) // 2:]
    ilk = [x for x in sina(a, kayma, yarim) if x["esik"] is not None]
    en = max(ilk, key=lambda x: x["toplam"])
    iki = {x["esik"]: x for x in sina(b, kayma, yarim)}
    return dict(secilen=en["esik"], ilk=en, ikinci=iki[en["esik"]], yok_ikinci=iki[None])


def _tablo(baslik, sonuclar):
    print(baslik)
    print(f"{'eşik':<7}{'tetik':>7}{'erken satılan':>15}{'toplam $':>10}{'ort %':>8}{'kazanma %':>11}")
    f = lambda x: "-" if x is None else x
    for s in sonuclar:
        print(f"{('yok' if s['esik'] is None else '%' + str(s['esik'])):<7}{s['tetik']:>7}{s['kacirilan']:>15}"
              f"{s['toplam']:>10}{f(s['ort_pct']):>8}{f(s['kazanma']):>11}")
    print()


def main(argv):
    a = argv[1:]; kayma = 1.0; gun = 0.0
    if "--kayma" in a:
        i = a.index("--kayma"); kayma = float(a[i + 1]); del a[i:i + 2]
    if a: gun = float(a[0])
    db = sqlite3.connect("file:nexora_paper.db?mode=ro", uri=True)
    bas = time.time() - gun * 86400 if gun else 0
    s = db.execute("""SELECT cost, pnl, min_pct, max_pct, closed_ts FROM pos_iz
                      WHERE closed_ts IS NOT NULL AND closed_ts > ? AND max_pct IS NOT NULL""", (bas,)).fetchall()
    if not s:
        print("Ölçümlü kapanmış pozisyon yok."); return 0
    yuksek = sorted((round(r[3], 1) for r in s), reverse=True)
    print(f"{len(s)} kapanmış pozisyon · kayma {kayma} puan · en yüksek anlar: {yuksek[:8]}")
    print(f"%20+ kâr görüp sonunda zararla kapanan: {sum(1 for c, p, _, mx, _ in s if mx >= 20 and c and p is not None and p < 0)}\n")
    _tablo("TAMAMINI SAT (temkinli: zarar kesme önce sayılır)", sina(s, kayma))
    _tablo("YARISINI SAT, kalanı kaynakla çıksın (temkinli)", sina(s, kayma, yarim=True))
    _tablo("TAMAMINI SAT (iyimser: kâr önce sayılır)", sina(s, kayma, iyimser=True))
    for yarim in (False, True):
        w = ileri_sinama(s, kayma, yarim)
        if w:
            print(f"İLERİ SINAMA ({'yarım' if yarim else 'tam'}): ilk yarıda seçilen %{w['secilen']} → görülmemiş ikinci yarıda "
                  f"{w['ikinci']['toplam']} $ (kuralsız {w['yok_ikinci']['toplam']} $, {w['ikinci']['n']} pozisyon)")
    print("\nNot: 'erken satılan' = kural sattı ama pozisyon sonunda daha yüksek kârla kapandı. Karar ileri sınamaya göre verilir.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
