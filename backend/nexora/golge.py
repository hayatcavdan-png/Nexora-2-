"""Gölge havuz (N3 + N16–N19): kopyalanmayan ama İZLENEN geniş cüzdan havuzu (PAPER, işlem yok).

Neden: geçmiş analizi (cuzdan_analiz) cüzdanın gelecekte bize kazandıracağını iyi tahmin etmiyor (17.11: 59 adaydan 0
kopyalanabilir), ama 'kaynak' ufkundaki gerçek ölçüm (etiket motoru) tahmin değil, gerçekleşen sonuçtur. Gölge havuzdaki
cüzdanların her alımı etiketlenir:
  1) Yapay zekâ: etiketli örnek hızla birikir (N18 seçim modeli ≥500 örnek bekliyor).
  2) Teyit: gölge cüzdanın aynı token'ı alması kopyalanan sinyali 'teyit' eder (önce yalnızca ölçülür; deney masası [10b]).
  3) Terfi adayı: ileriye dönük ölçümde iyi çıkan gölge cüzdan raporlanır (kopyalamaya geçirme kullanıcı onayıyla).
Kopyalama listesine (wallets.txt) dokunmaz. Takip servisi golge_listesi.txt'i okur ve bu cüzdanları 'yalnızca izlenen' sayar."""
import csv, os, time

from nexora import kadro as K

YOL = "golge_listesi.txt"
SINIR = int(os.getenv("GOLGE_SINIRI", "60"))
SESSIZ_GUN = 7
UYGUN = {"zayıf", "yetersiz veri", "eksik veri", "kopyalanabilir"}     # geçmişte kâr etmiş ama kopyalama eşiğini geçememiş


def oku(yol=YOL):
    try: return [l.strip() for l in open(yol) if l.strip() and not l.lstrip().startswith("#")]
    except OSError: return []


def yaz(liste, yol=YOL):
    gecici = yol + ".tmp"
    with open(gecici, "w") as f:
        f.write(f"# Gölge havuz ({time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC): sinyalleri etiketlenir, KOPYALANMAZ.\n")
        f.writelines(w + "\n" for w in liste)
    os.replace(gecici, yol)


def adaylar(analiz_csv="cuzdan_analiz.csv", haric=()):
    """Analiz edilmiş, geçmişte kâr etmiş, bot/hızlı/kullanıcı-dışı olmayan cüzdanlar; en çok gerçekleşen kâr önce."""
    haric = set(haric); out = []
    try:
        with open(analiz_csv, newline="") as f:
            for r in csv.DictReader(f):
                w = r.get("wallet")
                if not w or w in haric or r.get("karar") not in UYGUN: continue
                try: kz = float(r.get("gerceklesen_usd") or 0)
                except ValueError: continue
                if kz > 0: out.append((kz, w))
    except OSError:
        return []
    return [w for _, w in sorted(out, reverse=True)]


def _kayit(yol):
    import json
    try: return json.load(open(yol))
    except (OSError, ValueError): return {}


def doldur(sinir=SINIR, yol=YOL, analiz_csv="cuzdan_analiz.csv", takip_yolu="wallets.txt", kara_yolu="kara_liste.txt",
           tracker_db=None, kayit_yolu="golge_kayit.json", now=None):
    """Sessiz (en az 7 gündür listede, 7 günde alım yok) gölgeleri çıkarır, boş yerleri analizden gelen adaylarla doldurur.
    Dönüş: dict(eklenen, cikan, toplam, degisti)."""
    import json
    now = now if now is not None else time.time()
    mevcut = oku(yol); takip, kara = set(oku(takip_yolu)), set(oku(kara_yolu))
    kayit = _kayit(kayit_yolu)
    for w in mevcut: kayit.setdefault(w, now)
    aktif = K.alim_yapanlar(tracker_db or os.getenv("TRACKER_DB", "nexora_tracker.db"), now, SESSIZ_GUN)
    sessiz = set() if aktif is None else {w for w in mevcut if w not in aktif and now - kayit[w] >= SESSIZ_GUN * 86400}
    cikan = [w for w in mevcut if w in sessiz or w in kara or w in takip]
    kalan = [w for w in mevcut if w not in cikan]
    yeni = adaylar(analiz_csv, haric=set(kalan) | takip | kara | set(cikan))[:max(0, sinir - len(kalan))]
    son = kalan + yeni
    for w in yeni: kayit[w] = now
    kayit = {w: v for w, v in kayit.items() if w in set(son)}
    try:
        with open(kayit_yolu + ".tmp", "w") as f: json.dump(kayit, f)
        os.replace(kayit_yolu + ".tmp", kayit_yolu)
    except OSError:
        pass
    if son != mevcut: yaz(son, yol)
    return dict(eklenen=yeni, cikan=cikan, toplam=len(son), degisti=son != mevcut)


def karne(etiket_db, liste=None, now=None):
    """Gölge cüzdanların ileriye dönük ölçümü (kaynak ufku, 14 gün) ve terfi adayları (kadro terfi kuralı)."""
    liste = oku() if liste is None else liste
    olc = K.olcum(etiket_db, now)
    satir = sorted(((w, olc[w]) for w in liste if w in olc), key=lambda x: -x[1]["ort"] * min(1, x[1]["n"] / K.TERFI_N))
    terfi = [w for w, m in satir if m["n"] >= K.TERFI_N and m["ort"] >= K.TERFI_ORT and m["medyan"] > 0]
    return dict(havuz=len(liste), olculen=len(satir), sinyal=sum(m["n"] for _, m in satir), terfi=terfi, satirlar=satir)
