"""BTC rejimi ölçümü (SALT OKUNUR). Kapanmış kopya pozisyonlarını (pos_iz), açıldıkları andaki BTC'nin son 1 ve 4 saatlik
değişimine göre kovalara ayırır: "BTC düşerken açılan alımlar daha mı çok zarar ediyor?" sorusunu GEÇMİŞ veriyle yanıtlar.
Hiçbir ayar, karar ya da işlem değişmez. Kapı önerisi yalnızca rapordur; uygulanması sahip onayı ister.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.btc_rejim [gün=14]"""
import sqlite3, sys, time

from nexora.btc_ongoru import degisim_at, gecmis_mumlar

KOVALAR = ((-1e9, -2.0, "≤ -%2"), (-2.0, -0.5, "-%2 … -%0,5"), (-0.5, 0.5, "-%0,5 … +%0,5"), (0.5, 2.0, "+%0,5 … +%2"),
           (2.0, 1e9, "≥ +%2"))


def kova_analiz(pozlar, mum, sn=4 * 3600):
    """pozlar: [(opened_ts, pnl, cost)]. Dönüş: kova satırları + ölçülemeyen sayısı."""
    tablo = {ad: [] for _, _, ad in KOVALAR}; olcusuz = 0
    for ts, pnl, cost in pozlar:
        r = degisim_at(mum, ts, sn)
        if r is None: olcusuz += 1; continue
        for alt, ust, ad in KOVALAR:
            if alt < r <= ust or (alt == -1e9 and r <= ust): tablo[ad].append((pnl or 0.0, cost or 0.0)); break
    satir = []
    for _, _, ad in KOVALAR:
        v = tablo[ad]; n = len(v)
        toplam = sum(p for p, _ in v); maliyet = sum(c for _, c in v)
        satir.append(dict(kova=ad, n=n, toplam=round(toplam, 2), ort=round(toplam / n, 3) if n else None,
                          kazanma_pct=round(sum(p > 0 for p, _ in v) * 100 / n, 1) if n else None,
                          getiri_pct=round(toplam / maliyet * 100, 2) if maliyet else None))
    return satir, olcusuz


def kapi_karsi_olgu(pozlar, mum, esik=-2.0, sn=4 * 3600):
    """Kapı (BTC 4 saatlik değişim ≤ esik iken alım yok) geçmişte uygulansaydı: atlanacak pozisyonların sayısı ve K/Z'si."""
    atla = [(p or 0.0) for ts, p, _ in pozlar if (r := degisim_at(mum, ts, sn)) is not None and r <= esik]
    return dict(esik=esik, atlanacak=len(atla), atlanacak_kz=round(sum(atla), 2),
                yorum="kapı kaybı azaltırdı" if sum(atla) < 0 else "kapı kârlı işlemleri de keserdi")


def main(argv):
    gun = float(argv[1]) if len(argv) > 1 else 14.0
    db = sqlite3.connect("file:nexora_paper.db?mode=ro", uri=True)
    pozlar = db.execute("SELECT opened_ts, pnl, cost FROM pos_iz WHERE closed_ts IS NOT NULL AND opened_ts > ? ORDER BY opened_ts",
                        (time.time() - gun * 86400,)).fetchall()
    if not pozlar:
        print("Bu aralıkta kapanmış pozisyon yok."); return 0
    mum = gecmis_mumlar(pozlar[0][0] - 6 * 3600, time.time())
    print(f"Son {gun:g} gün · {len(pozlar)} kapanmış pozisyon · {len(mum)} saatlik BTC mumu (Binance)\n")
    for ad, sn in (("BTC son 4 saat", 4 * 3600), ("BTC son 1 saat", 3600)):
        satir, olcusuz = kova_analiz(pozlar, mum, sn)
        print(f"{ad} değişimine göre (ölçülemeyen {olcusuz}):")
        print(f"  {'kova':<16}{'n':>5}{'toplam $':>10}{'ort $':>9}{'kazanma %':>11}{'getiri %':>10}")
        for s in satir:
            f = lambda x, b="": "-" if x is None else f"{x}{b}"
            print(f"  {s['kova']:<16}{s['n']:>5}{f(s['toplam']):>10}{f(s['ort']):>9}{f(s['kazanma_pct']):>11}{f(s['getiri_pct']):>10}")
        print()
    for esik in (-1.0, -2.0, -3.0):
        k = kapi_karsi_olgu(pozlar, mum, esik)
        print(f"Kapı BTC 4s ≤ %{esik:g}: {k['atlanacak']} pozisyon atlanırdı, K/Z'leri {k['atlanacak_kz']} $ ({k['yorum']})")
    print("\nNot: geçmiş örneklem küçükse sonuç kesin değildir; kapı uygulanmadan önce sahip onayı gerekir.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
