"""Kadro: Solana takip listesini KAYNAĞIN değil BİZİM ölçtüğümüz sonuca göre yönetir (PAPER).

Ölçü: etiket motorunun 'kaynak' ufku. Kaynak her alımında aynı token'ı gerçek Jupiter teklifiyle $5'lık alıp kaynak sattığında
gerçek teklifle satsaydık, ağ ücreti düşülmüş getiri ne olurdu? Gecikme ve al-sat kaybı bu ölçünün içindedir.
Cüzdanın kendi geçmiş kârı (cuzdan_analiz) yalnızca adayı bulmak için kullanılır; kopyalama kararı bu ölçüyle verilir.

Kurallar (son PENCERE_GUN gün):
  yeni aday           -> izlemeye alınır (sinyalleri ölçülür, alımları kopyalanmaz); günde en fazla YENI_GUNLUK, liste en fazla LISTE_SINIRI
  izleme -> kopyalama : en az TERFI_N ölçüm, ortalama >= TERFI_ORT %, medyan > 0
  kopyalama -> izleme : en az DUSUR_N ölçüm, ortalama < 0
  izleme -> çıkar     : en az CIKAR_N ölçüm, ortalama <= CIKAR_ORT % (listeye yer açılır; kara listeye EKLENMEZ)
Kara listedeki adreslere dokunulmaz. Dosyalar atomik yazılır; takip servisi dosya değişince kendini yeniden başlatır."""
import os, sqlite3, time
from statistics import median

PENCERE_GUN = 14
TERFI_N, TERFI_ORT = 10, 3.0
DUSUR_N = 8
CIKAR_N, CIKAR_ORT = 10, -3.0
YENI_GUNLUK = 5
LISTE_SINIRI = int(os.getenv("TAKIP_SINIRI", "25"))


def olcum(etiket_db, now=None, gun=PENCERE_GUN):
    """{cüzdan: dict(n, ort, medyan, pozitif)}: 'kaynak' ufku getirileri (yüzde)."""
    now = now if now is not None else time.time()
    if not etiket_db or not os.path.exists(etiket_db): return {}
    c = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True, timeout=10)
    try:
        rows = c.execute("""SELECT o.wallet, s.getiri_pct FROM etiket_olay o JOIN etiket_sonuc s ON s.event_id=o.event_id
                            WHERE s.ufuk='kaynak' AND s.getiri_pct IS NOT NULL AND o.ts >= ?""", (now - gun * 86400,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        c.close()
    g = {}
    for w, v in rows: g.setdefault(w, []).append(float(v))
    return {w: dict(n=len(v), ort=round(sum(v) / len(v), 2), medyan=round(median(v), 2),
                    pozitif=round(sum(1 for x in v if x > 0) / len(v), 2)) for w, v in g.items()}


def karar(liste, izle, olc, adaylar=(), kara=()):
    """Saf karar. liste: wallets.txt (kopyalanan + izlenen), izle: izle_listesi.txt. Dönüş: yeni listeler ve değişiklikler."""
    kara = set(kara)
    liste = [w for w in dict.fromkeys(liste) if w not in kara]
    izle = [w for w in dict.fromkeys(izle) if w in liste]
    iz = set(izle)
    terfi, dusur, cikar, eklenen = [], [], [], []
    for w in liste:
        m = olc.get(w)
        if not m: continue
        if w not in iz:
            if m["n"] >= DUSUR_N and m["ort"] < 0: dusur.append(w)
        elif m["n"] >= TERFI_N and m["ort"] >= TERFI_ORT and m["medyan"] > 0: terfi.append(w)
        elif m["n"] >= CIKAR_N and m["ort"] <= CIKAR_ORT: cikar.append(w)
    yeni_liste = [w for w in liste if w not in cikar]
    yeni_izle = [w for w in izle if w not in terfi and w not in cikar] + dusur
    for w in dict.fromkeys(adaylar):
        if len(eklenen) >= YENI_GUNLUK or len(yeni_liste) >= LISTE_SINIRI: break
        if w in kara or w in yeni_liste: continue
        yeni_liste.append(w); yeni_izle.append(w); eklenen.append(w)
    return dict(liste=yeni_liste, izle=yeni_izle, terfi=terfi, dusur=dusur, cikar=cikar, eklenen=eklenen,
                kopyalanan=len(yeni_liste) - len(yeni_izle), izlenen=len(yeni_izle))


KANIT_N, KANIT_ORT = 15, 5.0


def seviye(m):
    """Kadro ölçümünden cüzdan seviyesi (core.SEVIYELER): kanıtlanmış / normal / yeni."""
    if m and m["n"] >= KANIT_N and m["ort"] >= KANIT_ORT and m["medyan"] > 0: return "kanitlanmis"
    if m and m["n"] >= TERFI_N: return "normal"
    return "yeni"


def seviyeler(olc):
    return {w: seviye(m) for w, m in olc.items()}


def _oku(path):
    try: return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]
    except OSError: return []


def _yaz(path, satirlar, baslik):
    gecici = path + ".tmp"
    with open(gecici, "w") as f:
        f.write(baslik + "\n"); f.writelines(w + "\n" for w in satirlar)
    os.replace(gecici, path)


def uygula(adaylar=(), etiket_db=None, now=None, liste_yolu="wallets.txt", izle_yolu="izle_listesi.txt", kara_yolu="kara_liste.txt"):
    """Ölçer, karar verir, değişiklik varsa dosyaları yazar. Dönüş: karar özeti (bildirim için) ve ölçümler."""
    etiket_db = etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db")
    olc = olcum(etiket_db, now)
    k = karar(_oku(liste_yolu), _oku(izle_yolu), olc, adaylar, _oku(kara_yolu))
    degisti = any(k[x] for x in ("terfi", "dusur", "cikar", "eklenen"))
    if degisti:
        tarih = time.strftime("%Y-%m-%d %H:%M", time.gmtime(now or time.time()))
        _yaz(liste_yolu, k["liste"], f"# Takip listesi (kadro.py, {tarih} UTC). İzle listesindekiler yalnızca ölçülür.")
        _yaz(izle_yolu, k["izle"], f"# Yalnızca izlenen cüzdanlar (kadro.py, {tarih} UTC): sinyalleri ölçülür, kopyalanmaz.")
    ozet = {x: k[x] for x in ("terfi", "dusur", "cikar", "eklenen", "kopyalanan", "izlenen")}
    ozet["olcum"] = {w: olc[w] for w in k["liste"] if w in olc}
    ozet["degisti"] = degisti
    return ozet


if __name__ == "__main__":                       # elle:  python3 -m nexora.kadro   (son keşif önerilerini de izlemeye alır)
    import json
    try: aday = [c["wallet"] for c in json.load(open("kesif_son.json")).get("kopyalanabilir", [])]
    except (OSError, ValueError, KeyError, TypeError): aday = []
    oz = uygula(aday)
    k = lambda w: w[:4] + "…" + w[-4:]
    print(f"Kadro: {oz['kopyalanan']} kopyalanan, {oz['izlenen']} izlenen" + ("" if oz["degisti"] else " (değişiklik yok)"))
    for ad, anahtar in (("Kopyalamaya geçti", "terfi"), ("İzlemeye düştü", "dusur"), ("Listeden çıktı", "cikar"), ("İzlemeye alındı", "eklenen")):
        if oz[anahtar]: print(f"  {ad}: {', '.join(k(w) for w in oz[anahtar])}")
    for w, m in sorted(oz["olcum"].items(), key=lambda x: -x[1]["ort"]):
        print(f"  {k(w)}  n={m['n']:<3} ort %{m['ort']:+.1f}  medyan %{m['medyan']:+.1f}  pozitif %{100 * m['pozitif']:.0f}  [{seviye(m)}]")
