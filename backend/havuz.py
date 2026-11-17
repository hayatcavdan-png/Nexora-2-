"""413 cüzdanlık başlangıç havuzu (cuzdan_tarama.csv) için durum raporu ve analiz/ekleme adımları.

  python3 havuz.py                  # rapor (Helius kredisi HARCAMAZ): tarama durumu, analiz kararları, takipte olanlar
  python3 havuz.py analiz 60        # analiz edilmemiş aday cüzdanlardan 60'ını analiz et (~20 kredi/cüzdan)
  python3 havuz.py ekle             # analizden 'kopyalanabilir' çıkıp takipte olmayanları kadroya ekle (liste sınırına kadar)

Kadro 'herkes' modunda eklenenler doğrudan kopyalanır; takip servisi liste değişince kendini yeniden başlatır."""
import csv, os, sys, tempfile
from collections import Counter

TARAMA, ANALIZ = "cuzdan_tarama.csv", "cuzdan_analiz.csv"
KREDI = 20                                      # cüzdan başına analiz maliyeti (200 işlem)


def _csv(yol):
    try:
        with open(yol, newline="") as f: return {r["wallet"]: r for r in csv.DictReader(f) if r.get("wallet")}
    except OSError:
        return {}


def _liste(yol):
    try: return [l.strip() for l in open(yol) if l.strip() and not l.lstrip().startswith("#")]
    except OSError: return []


def durum():
    tarama, analiz = _csv(TARAMA), _csv(ANALIZ)
    takip, kara = set(_liste("wallets.txt")), set(_liste("kara_liste.txt"))
    havuz = set(tarama)
    analizli = {w: analiz[w] for w in havuz if w in analiz}
    kopya = [w for w, r in analizli.items() if r.get("karar") == "kopyalanabilir"]
    adaylar = [w for w, r in tarama.items() if r.get("durum") == "aday"]
    analizsiz = [w for w in adaylar if w not in analiz and w not in kara]
    return dict(tarama=tarama, analiz=analiz, havuz=havuz, analizli=analizli, takip=takip, kara=kara,
                kopya=kopya, yeni_kopya=[w for w in kopya if w not in takip and w not in kara], analizsiz=analizsiz)


def rapor(d=None):
    d = d or durum()
    L = [f"== HAVUZ: {len(d['havuz'])} cüzdan (cuzdan_tarama.csv) =="]
    L.append("Tarama durumu: " + ", ".join(f"{k} {v}" for k, v in Counter(r.get("durum", "?") for r in d["tarama"].values()).most_common()))
    L.append(f"Analiz edilmiş: {len(d['analizli'])} (cuzdan_analiz.csv toplam {len(d['analiz'])})")
    if d["analizli"]:
        L.append("  Kararlar: " + ", ".join(f"{k} {v}" for k, v in Counter(r.get("karar", "?") for r in d["analizli"].values()).most_common()))
    L.append(f"Kopyalanabilir: {len(d['kopya'])}; bunlardan takipte olmayan: {len(d['yeni_kopya'])}")
    L.append(f"Takipte: {len(d['takip'])} cüzdan; havuzdan takipte olan: {len(d['takip'] & d['havuz'])}")
    L.append(f"Analiz edilmemiş aday: {len(d['analizsiz'])} (hepsi için ~{len(d['analizsiz']) * KREDI} Helius kredisi)")
    iyi = sorted((d["analizli"][w] for w in d["yeni_kopya"]), key=lambda r: -float(r.get("skor") or 0))[:10]
    if iyi:
        L.append("Takipte olmayan en iyi kopyalanabilirler (gerçekleşen K/Z, kapanan, kazanma, medyan tutma):")
        for r in iyi:
            L.append(f"  {r['wallet'][:4]}…{r['wallet'][-4:]}  {float(r.get('gerceklesen_usd') or 0):+.0f}$  "
                     f"{r.get('kapanan')} satış  %{100 * float(r.get('kazanma_orani') or 0):.0f}  {r.get('medyan_tutma_sn')} sn")
    return "\n".join(L)


def analiz_et(n, d=None):
    """Analiz edilmemiş adaylardan en aktif n tanesini analiz eder (cuzdan_analiz.main)."""
    d = d or durum()
    sec = sorted(d["analizsiz"], key=lambda w: -int(float(d["tarama"][w].get("islem_7g") or 0)))[:n]
    if not sec: return "Analiz edilecek aday kalmadı."
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=".") as f:
        f.writelines(w + "\n" for w in sec); yol = f.name
    try:
        import cuzdan_analiz
        print(f"{len(sec)} cüzdan analiz ediliyor (~{len(sec) * KREDI} Helius kredisi)...", flush=True)
        cuzdan_analiz.main(list_path=yol, yaz_oneri=False)
    finally:
        os.remove(yol)
    return rapor()


def ekle(d=None):
    """Takipte olmayan kopyalanabilirleri kadroya ekler (en iyi skor önce; kadro günlük ve liste sınırları geçerli)."""
    d = d or durum()
    from nexora import kadro
    sira = sorted(d["yeni_kopya"], key=lambda w: -float(d["analizli"][w].get("skor") or 0))
    eski = kadro.YENI_GUNLUK
    kadro.YENI_GUNLUK = len(sira)                  # havuz eklemesi tek seferlik: liste sınırı (TAKIP_SINIRI) yine geçerli
    try:
        oz = kadro.uygula(sira)
    finally:
        kadro.YENI_GUNLUK = eski
    return f"Eklenen: {len(oz['eklenen'])} cüzdan; takip listesi: {oz['kopyalanan']} kopyalanan, {oz['izlenen']} izlenen" + \
           ("" if len(oz["eklenen"]) == len(sira) else f" (liste sınırı {kadro.LISTE_SINIRI}: {len(sira) - len(oz['eklenen'])} eklenemedi)")


if __name__ == "__main__":
    komut = sys.argv[1] if len(sys.argv) > 1 else "rapor"
    if komut == "analiz": print(analiz_et(int(sys.argv[2]) if len(sys.argv) > 2 else 20))
    elif komut == "ekle": print(ekle())
    else: print(rapor())
