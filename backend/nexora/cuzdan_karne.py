"""Cüzdan karnesi (SALT OKUNUR). Kopya işlemde her kaynak cüzdanın kapanmış pozisyonlarından MALİYET SONRASI
beklenen getiriyi ve bunun şanstan ayrışıp ayrışmadığını ölçer. Hiçbir listeyi değiştirmez; yalnızca öneri yazar.

Ölçüler (pozisyon başına getiri r = pnl / maliyet):
- n, toplam $, ortalama getiri %, kazanma %, t = ort / (std / √n).
- Hüküm: n < 10 'az veri'; t ≤ -2 'kanıtlı zarar'; t ≥ 2 'kanıtlı kâr'; aksi 'belirsiz'.
- Defterde gerçekleşen K/Z (pnl) alış bacağının ağ ücretini içermez (portfoy_denetim de bunu ayrıca düşer);
  karne her pozisyondan alış ücretini (CFG net_fee_usd) düşerek NAKİT etkisini gösterir.
- Ek maliyet senaryosu: paper defteri Jupiter teklifindeki kaymayı içerir ama gerçek işlemdeki öncelik ücreti, başarısız
  işlem ve gecikme fiyat kaybını tam içermez. --ek X ile her pozisyondan X $ daha düşülerek sonuç yeniden hesaplanır.
Ayrıca: alımlardaki al-sat (gidiş-dönüş) kaybı dağılımı ve haftalık toplam gidişat.

Sunucuda:  cd /opt/nexora/backend && sudo -u nexora python3 -m nexora.cuzdan_karne [gün=0 (hepsi)] [--ek 0.10]"""
import math, re, sqlite3, statistics, sys, time

AZ_VERI = 10
T_ESIK = 2.0
RT = re.compile(r"al-sat kaybı %(-?[\d.]+)")


def istatistik(getiriler):
    """getiriler: yüzde listesi. dict(n, ort, std, t, kazanma)."""
    n = len(getiriler)
    if n == 0: return dict(n=0, ort=None, std=None, t=None, kazanma=None)
    ort = sum(getiriler) / n
    std = statistics.stdev(getiriler) if n > 1 else 0.0
    t = ort / (std / math.sqrt(n)) if n > 1 and std > 0 else None
    return dict(n=n, ort=ort, std=std, t=t, kazanma=sum(g > 0 for g in getiriler) / n * 100)


def hukum(st):
    if st["n"] < AZ_VERI: return "az veri"
    if st["t"] is not None and st["t"] <= -T_ESIK: return "kanıtlı zarar"
    if st["t"] is not None and st["t"] >= T_ESIK: return "kanıtlı kâr"
    return "belirsiz"


def karne(satirlar, ek=0.0, alis_ucreti=None):
    """satirlar: [(wallet, cost, pnl, closed_ts)]. Dönüş: (cüzdan satırları t'ye göre artan, genel).
    alis_ucreti: pozisyon başına düşülecek alış ağ ücreti (varsayılan CFG net_fee_usd)."""
    if alis_ucreti is None:
        from nexora.core import CFG
        alis_ucreti = CFG["net_fee_usd"]
    ek = ek + alis_ucreti
    grup = {}
    for w, cost, pnl, _ in satirlar:
        if not cost or cost <= 0 or pnl is None: continue
        grup.setdefault(w, []).append(((pnl - ek) / cost * 100, pnl - ek))
    out = []
    for w, v in grup.items():
        st = istatistik([g for g, _ in v])
        out.append(dict(wallet=w, toplam=round(sum(p for _, p in v), 2), hukum=hukum(st), **_yuvarla(st)))
    out.sort(key=lambda d: (d["t"] if d["t"] is not None else 0.0, d["toplam"]))
    hepsi = [((p - ek) / c * 100) for _, c, p, _ in satirlar if c and c > 0 and p is not None]
    g = istatistik(hepsi)
    genel = dict(toplam=round(sum(p - ek for _, c, p, _ in satirlar if c and c > 0 and p is not None), 2), hukum=hukum(g),
                 **_yuvarla(g))
    return out, genel


def haftalik(satirlar, now=None):
    now = now or time.time(); h = {}
    for _, c, p, ts in satirlar:
        if p is None or not ts: continue
        k = int((now - ts) // (7 * 86400))
        if k < 8: h.setdefault(k, []).append(p)
    return [dict(hafta_once=k, n=len(v), toplam=round(sum(v), 2)) for k, v in sorted(h.items())]


def alsat_kaybi(nedenler):
    v = sorted(float(m.group(1)) for r in nedenler if r and (m := RT.search(r)))
    if not v: return None
    return dict(n=len(v), ort=round(sum(v) / len(v), 2), medyan=round(v[len(v) // 2], 2), p90=round(v[min(len(v) - 1, int(len(v) * 0.9))], 2))


def _yuvarla(st):
    r = lambda x, n=2: None if x is None else round(x, n)
    return dict(n=st["n"], ort=r(st["ort"]), std=r(st["std"]), t=r(st["t"]), kazanma=r(st["kazanma"], 1))


def liste(yol):
    try:
        return {l.split()[0] for l in open(yol) if l.strip() and not l.lstrip().startswith("#")}
    except OSError:
        return set()


def main(argv):
    gun = 0.0; ek = 0.0; a = argv[1:]
    if "--ek" in a:
        i = a.index("--ek"); ek = float(a[i + 1]); del a[i:i + 2]
    if a: gun = float(a[0])
    db = sqlite3.connect("file:nexora_paper.db?mode=ro", uri=True)
    bas = time.time() - gun * 86400 if gun else 0
    satir = db.execute("SELECT wallet, cost, pnl, closed_ts FROM pos_iz WHERE closed_ts IS NOT NULL AND closed_ts > ?", (bas,)).fetchall()
    if not satir:
        print("Kapanmış pozisyon yok."); return 0
    izle, kara = liste("wallets.txt"), liste("kara_liste.txt")
    cuz, genel = karne(satir, ek)
    print(f"{'Tüm geçmiş' if not gun else f'Son {gun:g} gün'} · {genel['n']} kapanmış pozisyon"
          + (f" · senaryo: pozisyon başına +{ek} $ ek maliyet" if ek else ""))
    print(f"GENEL: toplam {genel['toplam']} $ · ort. getiri %{genel['ort']} · kazanma %{genel['kazanma']} · t {genel['t']} "
          f"-> {genel['hukum'].upper()}\n")
    print(f"{'cüzdan':<12}{'n':>5}{'toplam$':>9}{'ort%':>8}{'kaz%':>7}{'t':>7}  hüküm           liste")
    for d in cuz:
        durum = "kara" if d["wallet"] in kara else ("izleniyor" if d["wallet"] in izle else "-")
        f = lambda x: "-" if x is None else x
        print(f"{d['wallet'][:10]:<12}{d['n']:>5}{d['toplam']:>9}{f(d['ort']):>8}{f(d['kazanma']):>7}{f(d['t']):>7}  "
              f"{d['hukum']:<15}  {durum}")
    oner = [d for d in cuz if d["hukum"] == "kanıtlı zarar" and d["wallet"] in izle]
    print("\nÖNERİ (otomatik uygulanmaz):")
    if oner:
        for d in oner: print(f"  kara listeye al: {d['wallet']}  ({d['n']} pozisyon, {d['toplam']} $, t {d['t']})")
    else:
        print("  izlenen cüzdanlarda kanıtlı zarar yok")
    iyi = [d for d in cuz if d["hukum"] == "kanıtlı kâr"]
    print(f"  kanıtlı kârlı cüzdan sayısı: {len(iyi)}" + (": " + ", ".join(d["wallet"][:10] for d in iyi) if iyi else ""))
    print("\nHaftalık gidişat (0 = bu hafta):", ", ".join(f"{h['hafta_once']}: {h['toplam']} $ ({h['n']})" for h in haftalik(satir)))
    k = alsat_kaybi([r[0] for r in db.execute("SELECT reason FROM trades WHERE side='buy' AND decision='KOPYALANDI' AND ts > ?", (bas,))])
    if k:
        print(f"Alımlarda gidiş-dönüş (al-sat) kaybı: ort %{k['ort']} · medyan %{k['medyan']} · en kötü %10 dilim ≥ %{k['p90']} ({k['n']} alım)")
    print("\nNot: t ≈ 2 eşiği tek tek cüzdanlar için; çok cüzdan sınandığından şansa bağlı birkaç 'kanıtlı' sonuç beklenebilir.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
