"""Zarar kesme eşiği sınaması (SALT OKUNUR). "%12 zarar kesme kazandırıyor mu, kaybettiriyor mu?" sorusunu kendi
kopya verimizle yanıtlar.

Yöntem:
- Zarar kesme kuralı devreye girmeden ÖNCE kapanan pozisyonlar (kural yokken kaynak cüzdanla birlikte çıkılan) kullanılır;
  her birinin ömrü boyunca 2 dakikada bir gerçek satış teklifiyle ölçülen en kötü anı (min_pct) bilinir.
- Her eşik X için: pozisyonun en kötü anı -X'e indiyse sonuç -(X + kayma) sayılır (zarar kesme orada satardı);
  inmediyse gerçek sonucu korunur. Kayma, kural devredeyken gerçekleşen zarar kesme satışlarından ölçülür
  (ör. %12 eşiğinde ortalama %-16 ile çıkıldıysa kayma 4 puan).
- 'Yok' satırı: hiç zarar kesme olmadan gerçek sonuç. 'Kurtarılırdı': kesilip de sonunda kârla kapanmış pozisyon sayısı.
Sınır: ölçüm 2 dakikada bir; arada daha derine inip dönen fiyatı görmez. Geçmiş sonuç garanti değildir.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.stop_sinama"""
import sqlite3, sys

ESIKLER = (8, 10, 12, 15, 20, 25, 30, 40, 50)


def kayma_olc(sonrasi, kural=12.0):
    """Kural devredeyken eşiğin altında kapananların ortalama ek kaybı (puan). Veri yoksa 3."""
    v = [-(p / c * 100) - kural for c, p, _ in sonrasi if c and p is not None and p / c * 100 <= -kural]
    return round(max(0.0, sum(v) / len(v)), 2) if v else 3.0


def sina(oncesi, kayma, esikler=ESIKLER):
    """oncesi: [(cost, pnl, min_pct)]. Dönüş: [dict(esik, kesilen, kurtarilirdi, toplam, ort_pct, kazanma)]."""
    out = []
    for e in (None,) + tuple(esikler):
        top = n_kes = kurtar = kaz = 0; rs = []
        for c, p, mn in oncesi:
            if not c or p is None: continue
            r = p / c * 100
            if e is not None and mn is not None and mn <= -e:
                n_kes += 1; kurtar += int(p > 0); r = -(e + kayma)
            rs.append(r); top += r * c / 100; kaz += int(r > 0)
        n = len(rs)
        out.append(dict(esik=e, n=n, kesilen=n_kes, kurtarilirdi=kurtar, toplam=round(top, 2),
                        ort_pct=round(sum(rs) / n, 2) if n else None, kazanma=round(kaz * 100 / n, 1) if n else None))
    return out


def main(argv):
    db = sqlite3.connect("file:nexora_paper.db?mode=ro", uri=True)
    ilk = db.execute("SELECT MIN(ts) FROM trades WHERE side='sell' AND decision='KOPYALANDI' AND reason LIKE '%zarar kesme%'").fetchone()[0]
    if ilk is None:
        print("Zarar kesme ile kapanan işlem yok; kural öncesi/sonrası ayrılamıyor."); return 0
    oncesi = db.execute("SELECT cost, pnl, min_pct FROM pos_iz WHERE closed_ts IS NOT NULL AND closed_ts < ?", (ilk,)).fetchall()
    sonrasi = db.execute("SELECT cost, pnl, min_pct FROM pos_iz WHERE closed_ts IS NOT NULL AND closed_ts >= ?", (ilk,)).fetchall()
    kayma = kayma_olc(sonrasi)
    print(f"Kural öncesi {len(oncesi)} pozisyon üzerinde sınama · ölçülen zarar kesme kayması {kayma} puan "
          f"(kural sonrası {len(sonrasi)} pozisyondan)\n")
    print(f"{'eşik':<7}{'kesilen':>8}{'kurtarılırdı':>13}{'toplam $':>10}{'ort %':>8}{'kazanma %':>11}")
    for s in sina(oncesi, kayma):
        f = lambda x: "-" if x is None else x
        print(f"{('yok' if s['esik'] is None else '%' + str(s['esik'])):<7}{s['kesilen']:>8}{s['kurtarilirdi']:>13}"
              f"{s['toplam']:>10}{f(s['ort_pct']):>8}{f(s['kazanma']):>11}")
    son = [(c, p) for c, p, _ in sonrasi if c and p is not None]
    print(f"\nKural devredeyken gerçekleşen: {len(son)} pozisyon, toplam {round(sum(p for _, p in son), 2)} $")
    print("Not: 'kurtarılırdı' = kesilecek ama sonunda kârla kapanmış pozisyon. En iyi eşik, toplamı en yüksek olandır.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
