"""Deney masası (yalnızca ölçüm): etiket motorunun gerçek tekliflerle ölçtüğü sinyalleri farklı kurallarla YENİDEN OYNATIR.

Her sinyal için elimizde: giriş anı, kaynak sattığında çıkış anı, ücret dahil getiri (%), al-sat kaybı (%) ve cüzdan var.
Bir kural seti (pozisyon sayısı, büyüklük, cüzdan başına sınır, al-sat sınırı, kadro) bu sinyaller üzerinde zaman sırasıyla
uygulanır; yer yoksa sinyal kaçırılır, varsa pozisyon kaynak çıkışına kadar tutulur. Böylece ayarlar AYNI piyasa
koşullarında karşılaştırılır. Ek API isteği yok; paper defterine ve canlı kopyalamaya dokunmaz.

Sınırlar: yalnızca kaynak çıkışı ölçülmüş sinyaller (açık kalanlar ve 24 saati aşanlar dışarıda); getiri $5'lık teklifle
ölçüldü (büyük pozisyonda fiyat etkisi biraz daha yüksek olur); kadro kararı her an yalnızca O ANA KADAR kapanmış
ölçümlerle verilir (geleceği görmez)."""
import os, sqlite3, time
from statistics import median

from nexora import kadro as K


def sinyaller(etiket_db, now=None, gun=14):
    """[(giris_ts, cikis_ts, cuzdan, token, getiri_pct, al_sat_kaybi_pct)], giriş zamanına göre sıralı."""
    now = now if now is not None else time.time()
    if not etiket_db or not os.path.exists(etiket_db): return []
    c = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True, timeout=10)
    try:
        rows = c.execute("""SELECT o.ts, s.ts, o.wallet, o.token, s.getiri_pct, o.al_sat_kaybi_pct FROM etiket_olay o
            JOIN etiket_sonuc s ON s.event_id=o.event_id WHERE s.ufuk='kaynak' AND s.getiri_pct IS NOT NULL AND o.ts >= ?
            ORDER BY o.ts""", (now - gun * 86400,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        c.close()
    return [(a, max(a, b), w, t, float(g), r) for a, b, w, t, g, r in rows]


def _seviye(gecmis, aktif=False):
    """O ana kadar kapanmış ölçümlerden kadro kararı: (kopyalanir_mi, seviye). aktif: başlangıçta kopyalanan cüzdan
    (gerçekte olduğu gibi terfi beklemez; ortalaması 8 ölçümden sonra eksiye düşerse kopyalanmaz)."""
    n = len(gecmis)
    if n == 0: return aktif, "yeni"
    ort, med = sum(gecmis) / n, median(gecmis)
    m = dict(n=n, ort=ort, medyan=med)
    if n >= K.DUSUR_N and ort < 0: return False, "yeni"
    if n >= K.TERFI_N and ort >= K.TERFI_ORT and med > 0: return True, K.seviye(m)
    return aktif, K.seviye(m)


def simule(sinyal, max_poz=16, oran=0.025, seviyeler=None, cuzdan_siniri=2, rt_max=3.0, kadro=False, toplam_risk=0.40,
           sermaye=100.0, aktif=()):
    """Kural setini oynatır. seviyeler: {seviye: (cüzdan başına poz, oran)} verilirse büyüklük/sınır seviyeden gelir.
    kadro=True: cüzdan yalnızca o ana kadarki ölçümüyle terfi koşulunu sağlıyorsa kopyalanır."""
    nakit, acik, gecmis = sermaye, [], {}
    olcum = []                    # kadro ölçümü: kopyalansın kopyalanmasın HER sinyalin sonucu, çıkış anında görünür olur
    islem = kacan = 0; sonuc = []
    zirve = dusus = 0.0; gercek = 0.0

    def kapat(t):
        nonlocal nakit, gercek, zirve, dusus
        for o in [o for o in olcum if o[0] <= t]:
            gecmis.setdefault(o[1], []).append(o[2]); olcum.remove(o)
        kalan = []
        for p in sorted(acik, key=lambda p: p["cikis"]):
            if p["cikis"] <= t:
                kz = p["maliyet"] * p["g"] / 100
                nakit += p["maliyet"] + kz; gercek += kz; sonuc.append(kz)
                zirve = max(zirve, gercek); dusus = max(dusus, zirve - gercek)
            else:
                kalan.append(p)
        acik[:] = kalan

    for giris, cikis, w, tok, g, rt in sinyal:
        kapat(giris)
        olcum.append((cikis, w, g))
        if rt is not None and rt > rt_max: continue
        if kadro == "gevsek":                 # herkes kopyalanır; yalnızca ölçülmüş kötüler (8+ ölçüm, ortalama < 0) düşer
            gg = gecmis.get(w, [])
            if len(gg) >= K.DUSUR_N and sum(gg) / len(gg) < 0: continue
            sv = "normal"
        elif kadro:
            ok, sv = _seviye(gecmis.get(w, []), w in aktif)
            if not ok: continue
        else:
            sv = "normal"
        if any(p["t"] == tok for p in acik): continue
        sinir, pay = (seviyeler[sv] if seviyeler else (cuzdan_siniri, oran))
        ozkaynak = nakit + sum(p["maliyet"] for p in acik)
        boyut = ozkaynak * pay
        if (len(acik) >= max_poz or sum(1 for p in acik if p["w"] == w) >= sinir
                or sum(p["maliyet"] for p in acik) + boyut > toplam_risk * ozkaynak + 1e-9 or boyut > nakit):
            kacan += 1; continue
        nakit -= boyut; acik.append(dict(t=tok, w=w, maliyet=boyut, g=g, cikis=cikis)); islem += 1
    kapat(float("inf"))
    return dict(islem=islem, kacan=kacan, kz=round(gercek, 2), kazanan=round(100 * sum(1 for v in sonuc if v > 0) / len(sonuc)) if sonuc else 0,
                dusus=round(dusus, 2))


SEVIYE_SIMDI = dict(kanitlanmis=(4, 0.035), normal=(2, 0.025), yeni=(1, 0.015))
SEVIYE_BUYUK = dict(kanitlanmis=(3, 0.06), normal=(2, 0.045), yeni=(1, 0.025))

# "aktif" anahtarı: deney, o anki kopyalanan cüzdan listesiyle başlar (masa() doldurur)
DENEYLER = [
    ("Eski: 8x%5, al-sat<=%6, herkes", dict(max_poz=8, oran=0.05, rt_max=6.0)),
    ("8x%5, al-sat<=%3, herkes", dict(max_poz=8, oran=0.05, rt_max=3.0)),
    ("16x%2.5, al-sat<=%3, herkes", dict(max_poz=16, oran=0.025, rt_max=3.0)),
    ("10x%4, al-sat<=%3, herkes", dict(max_poz=10, oran=0.04, rt_max=3.0)),
    ("Şimdiki: 16 poz, seviye, %3, kadro", dict(max_poz=16, seviyeler=SEVIYE_SIMDI, rt_max=3.0, kadro=True, aktif="liste")),
    ("Kadro + büyük seviye (6/4.5/2.5), 10 poz", dict(max_poz=10, seviyeler=SEVIYE_BUYUK, rt_max=3.0, kadro=True, aktif="liste")),
    ("8x%5, %3, kadro", dict(max_poz=8, oran=0.05, rt_max=3.0, kadro=True, aktif="liste")),
    ("10x%4, %3, kötüler düşer", dict(max_poz=10, oran=0.04, rt_max=3.0, kadro="gevsek")),
    ("8x%5, %3, kötüler düşer", dict(max_poz=8, oran=0.05, rt_max=3.0, kadro="gevsek")),
    ("Yer sınırsız 40x%1, %3, herkes", dict(max_poz=40, oran=0.01, rt_max=3.0, cuzdan_siniri=40)),
]


def aktif_liste(liste_yolu="wallets.txt", izle_yolu="izle_listesi.txt"):
    """Şu an kopyalanan cüzdanlar (takip listesi eksi izlenenler)."""
    iz = set(K._oku(izle_yolu))
    return {w for w in K._oku(liste_yolu) if w not in iz}


def masa(etiket_db=None, now=None, gun=14, deneyler=DENEYLER, aktif=None):
    s = sinyaller(etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db"), now, gun)
    aktif = aktif_liste() if aktif is None else set(aktif)
    out = []
    for ad, cfg in deneyler:
        cfg = dict(cfg)
        if cfg.get("aktif") == "liste": cfg["aktif"] = aktif
        out.append(dict(ad=ad, **simule(s, **cfg)))
    return dict(sinyal=len(s), gun=gun, sonuclar=out)
