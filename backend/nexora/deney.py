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
           sermaye=100.0, aktif=(), ek_ucret=0.0, gunluk_zarar=None, token_gunluk=None):
    """Kural setini oynatır. seviyeler: {seviye: (cüzdan başına poz, oran)} verilirse büyüklük/sınır seviyeden gelir.
    kadro=True: cüzdan yalnızca o ana kadarki ölçümüyle terfi koşulunu sağlıyorsa kopyalanır.
    ek_ucret: etiket tekliflerinde olmayan, işlem başına sabit maliyet ($; öncelik ücreti + Jito bahşişi). Al ve sat: 2 kez.
    gunluk_zarar: canlıdaki günlük zarar sınırı (ör. 0.03): UTC gün başındaki özkaynağa göre gün içi GERÇEKLEŞEN kayıp bu orana
    ulaşınca o gün yeni alım yok (canlı açık pozisyon değerini de sayar, yani canlı daha sık durur: bu yaklaşık bir alt sınırdır).
    token_gunluk: aynı token'a bir UTC gününde en fazla bu kadar giriş (canlı: 2)."""
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
                kz = p["maliyet"] * p["g"] / 100 - 2 * ek_ucret
                nakit += p["maliyet"] + kz; gercek += kz; sonuc.append(kz)
                zirve = max(zirve, gercek); dusus = max(dusus, zirve - gercek)
            else:
                kalan.append(p)
        acik[:] = kalan

    gun, gun_basi, durdu, tok_gun = None, sermaye, 0, {}
    for sg in sinyal:
        giris, cikis, w, tok, g, rt = sg[:6]
        kat = sg[6] if len(sg) > 6 else 1.0          # güçlendirici: teyitli sinyalde büyüklük çarpanı
        kapat(giris)
        olcum.append((cikis, w, g))
        if rt is not None and rt > rt_max: continue
        bugun = int(giris // 86400)
        if bugun != gun:
            gun, gun_basi, tok_gun = bugun, nakit + sum(p["maliyet"] for p in acik), {}
        if gunluk_zarar is not None and gun_basi > 0 and (gun_basi - nakit - sum(p["maliyet"] for p in acik)) / gun_basi >= gunluk_zarar:
            durdu += 1; continue
        if token_gunluk is not None and tok_gun.get(tok, 0) >= token_gunluk and not any(p["t"] == tok for p in acik):
            continue
        if kadro == "gevsek":                 # herkes kopyalanır; yalnızca ölçülmüş kötüler (8+ ölçüm, ortalama < 0) düşer
            gg = gecmis.get(w, [])
            if len(gg) >= K.DUSUR_N and sum(gg) / len(gg) < 0: continue
            sv = "normal"
        elif kadro:
            ok, sv = _seviye(gecmis.get(w, []), w in aktif)
            if not ok: continue
        else:
            sv = "normal"
        ek = False
        if any(p["t"] == tok for p in acik):
            if kat <= 1.0 or any(p["t"] == tok and p.get("ek") for p in acik): continue
            ek = True                                  # teyit: mevcut pozisyona (kat-1) büyüklüğünde ek parça
        sinir, pay = (seviyeler[sv] if seviyeler else (cuzdan_siniri, oran))
        ozkaynak = nakit + sum(p["maliyet"] for p in acik)
        boyut = ozkaynak * pay * ((kat - 1.0) if ek else kat)
        if ((not ek and (len(acik) - sum(1 for p in acik if p.get("ek")) >= max_poz or sum(1 for p in acik if p["w"] == w) >= sinir))
                or sum(p["maliyet"] for p in acik) + boyut > toplam_risk * ozkaynak + 1e-9 or boyut > nakit):
            kacan += 1; continue
        nakit -= boyut; acik.append(dict(t=tok, w=w, maliyet=boyut, g=g, cikis=cikis, ek=ek)); islem += 1
        if not ek: tok_gun[tok] = tok_gun.get(tok, 0) + 1
    kapat(float("inf"))
    return dict(islem=islem, kacan=kacan, limit_durdu=durdu, kz=round(gercek, 2), kazanan=round(100 * sum(1 for v in sonuc if v > 0) / len(sonuc)) if sonuc else 0,
                dusus=round(dusus, 2))


SEVIYE_SIMDI = dict(kanitlanmis=(4, 0.035), normal=(2, 0.025), yeni=(1, 0.015))
SEVIYE_BUYUK = dict(kanitlanmis=(3, 0.06), normal=(2, 0.045), yeni=(1, 0.025))

# "aktif" anahtarı: deney, o anki kopyalanan cüzdan listesiyle başlar (masa() doldurur)
DENEYLER = [
    ("Eski: 8x%5, al-sat<=%6, herkes", dict(max_poz=8, oran=0.05, rt_max=6.0)),
    ("Şimdiki (18.11): 8x%5, al-sat<=%3, herkes", dict(max_poz=8, oran=0.05, rt_max=3.0)),
    ("16x%2.5, al-sat<=%3, herkes", dict(max_poz=16, oran=0.025, rt_max=3.0)),
    ("Önceki: 10x%4, al-sat<=%3, herkes", dict(max_poz=10, oran=0.04, rt_max=3.0)),
    ("Önceki: 16 poz, seviye, %3, kadro", dict(max_poz=16, seviyeler=SEVIYE_SIMDI, rt_max=3.0, kadro=True, aktif="liste")),
    ("Kadro + büyük seviye (6/4.5/2.5), 10 poz", dict(max_poz=10, seviyeler=SEVIYE_BUYUK, rt_max=3.0, kadro=True, aktif="liste")),
    ("8x%5, %3, kadro", dict(max_poz=8, oran=0.05, rt_max=3.0, kadro=True, aktif="liste")),
    ("10x%4, %3, kötüler düşer", dict(max_poz=10, oran=0.04, rt_max=3.0, kadro="gevsek")),
    ("8x%5, %3, kötüler düşer", dict(max_poz=8, oran=0.05, rt_max=3.0, kadro="gevsek")),
    ("Yer sınırsız 40x%1, %3, herkes", dict(max_poz=40, oran=0.01, rt_max=3.0, cuzdan_siniri=40)),
    # Günlük zarar sınırı (20.11): canlıda %3 sınırı 14 günde 5.531 alımı reddetti; deney masası bunu hiç oynatmıyordu.
    ("Şimdiki + günlük zarar sınırı %3 (canlıdaki gibi)", dict(max_poz=8, oran=0.05, rt_max=3.0, gunluk_zarar=0.03, token_gunluk=2)),
    ("Şimdiki + günlük zarar sınırı %6", dict(max_poz=8, oran=0.05, rt_max=3.0, gunluk_zarar=0.06, token_gunluk=2)),
    ("Şimdiki + günlük sınır yok, token/gün 2", dict(max_poz=8, oran=0.05, rt_max=3.0, token_gunluk=2)),
    # Ücret duyarlılığı (20.11): paper 0,01$/işlem varsayıyor; yoğun anlarda öncelik ücreti + Jito bahşişi daha yüksek.
    # Pozisyon ~5$ olduğundan sabit ücret yüzde olarak büyür: 0,05$ ≈ gidiş-dönüş %2, 0,10$ ≈ %4.
    ("Şimdiki + işlem başı 0,05$ ek ücret", dict(max_poz=8, oran=0.05, rt_max=3.0, ek_ucret=0.05)),
    ("Şimdiki + işlem başı 0,10$ ek ücret", dict(max_poz=8, oran=0.05, rt_max=3.0, ek_ucret=0.10)),
]


def aktif_liste(liste_yolu="wallets.txt", izle_yolu="izle_listesi.txt"):
    """Şu an kopyalanan cüzdanlar (takip listesi eksi izlenenler)."""
    iz = set(K._oku(izle_yolu))
    return {w for w in K._oku(liste_yolu) if w not in iz}


def golge_seti(yol="golge_listesi.txt"):
    return set(K._oku(yol))


def masa(etiket_db=None, now=None, gun=14, deneyler=DENEYLER, aktif=None, golge=None):
    """Kurallar gölge havuz DIŞINDAKİ sinyallerle oynatılır (canlıda kopyalanabilecek olanlar). Gölge havuzun sinyalleri
    varsa ek satır: 'şimdiki kural + gölge havuz da kopyalansaydı'."""
    hepsi = sinyaller(etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db"), now, gun)
    golge = golge_seti() if golge is None else set(golge)
    s = [x for x in hepsi if x[2] not in golge]
    aktif = aktif_liste() if aktif is None else set(aktif)
    out = []
    for ad, cfg in deneyler:
        cfg = dict(cfg)
        if cfg.get("aktif") == "liste": cfg["aktif"] = aktif
        out.append(dict(ad=ad, **simule(s, **cfg)))
    if len(hepsi) > len(s):
        out.append(dict(ad=f"Şimdiki kural + gölge havuz da kopyalansa ({len(hepsi) - len(s)} gölge sinyali)",
                        **simule(hepsi, **MODEL_AYAR)))
    return dict(sinyal=len(s), golge_sinyal=len(hepsi) - len(s), gun=gun, sonuclar=out)


# ---------------------------------------------------------------- Model A / Model B (ALPHA HUNTER X fikirleri, yalnızca ölçüm)
TEYIT_SN = 900          # Model A: aynı token'ı son 15 dakikada alan farklı cüzdan sayısı
GERI_SN = 300           # Model B: sinyalden 5 dakika sonra (etiket motorunun 5 dk ölçümü)
UCRET_PAY = 2 * 0.01 / 5.0   # iki bacak ağ ücreti / 5 $ (etiket getirisindeki ile aynı)


def sinyaller_detay(etiket_db, now=None, gun=14, golge=frozenset()):
    """Kaynak sonucu olan her sinyal: giriş/çıkış zamanı, cüzdan, token, getiri, al-sat kaybı, 5 dk ve kaynak çıkış tutarı,
    ve 15 dk içinde aynı token'ı alan farklı cüzdan sayısı (teyit)."""
    now = now if now is not None else time.time()
    if not etiket_db or not os.path.exists(etiket_db): return []
    c = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True, timeout=10)
    try:
        rows = c.execute("""SELECT o.ts, k.ts, o.wallet, o.token, k.getiri_pct, o.al_sat_kaybi_pct, o.giris_usdc, k.cikis_usdc,
                f.cikis_usdc FROM etiket_olay o
                JOIN etiket_sonuc k ON k.event_id=o.event_id AND k.ufuk='kaynak' AND k.getiri_pct IS NOT NULL
                LEFT JOIN etiket_sonuc f ON f.event_id=o.event_id AND f.ufuk='5dk' AND f.getiri_pct IS NOT NULL
                WHERE o.ts >= ? ORDER BY o.ts""", (now - gun * 86400,)).fetchall()
        alim = c.execute("SELECT ts, wallet, token FROM etiket_olay WHERE ts >= ?", (now - gun * 86400 - TEYIT_SN,)).fetchall()
    except sqlite3.OperationalError:
        rows, alim = [], []
    finally:
        c.close()
    tok = {}
    for ts, w, t in alim: tok.setdefault(t, []).append((ts, w))
    out = []
    for gts, cts, w, t, g, rt, giris, ck, c5 in rows:
        yakin = {ww for ts, ww in tok.get(t, ()) if gts - TEYIT_SN <= ts <= gts}
        n = len(yakin - set(golge)) if w not in golge else len(yakin)    # canlı kural: yalnızca kopyalanan cüzdanlar teyit eder
        out.append(dict(giris=gts, cikis=max(gts, cts), w=w, t=t, g=float(g), rt=rt, usd=giris or 5.0, ck=ck, c5=c5,
                        teyit=max(n, 1), teyit_golge=max(len(yakin), 1), golge=w in golge))
    return out


def model_a(detay, en_az):
    """Yalnızca en az `en_az` farklı cüzdanın 15 dk içinde aldığı token'larda, teyidi tamamlayan sinyalle gir."""
    return [(d["giris"], d["cikis"], d["w"], d["t"], d["g"], d["rt"]) for d in detay if d["teyit"] >= en_az]


def model_b(detay, dusus_pct):
    """Sinyalden 5 dk sonra, fiyat sinyal anına göre en az `dusus_pct` düştüyse gir; kaynak satınca çık.
    Fiyat değişimi ve getiri aynı miktarın satış teklifleriyle (5 dk ve kaynak) yaklaşık hesaplanır."""
    out = []
    for d in detay:
        if not d["c5"] or not d["ck"] or d["cikis"] < d["giris"] + GERI_SN: continue
        rt = d["rt"] or 0.0
        anlik = d["usd"] * (1 - rt / 100)                  # sinyal anında hemen satış değeri
        hareket = (d["c5"] / anlik - 1) * 100 if anlik > 0 else 0.0
        if hareket > -dusus_pct: continue
        g = ((d["ck"] / d["c5"]) * (1 - rt / 100) - 1 - UCRET_PAY) * 100   # 5. dakikada al, kaynak satınca sat
        out.append((d["giris"] + GERI_SN, d["cikis"], d["w"], d["t"], g, rt))
    return out


def guclendirici(detay, kat, en_az=2, alan="teyit"):
    """Her sinyale gir; en az `en_az` cüzdanın 15 dk içinde aldığı token'da büyüklük `kat` (tutuluyorsa ek parça).
    alan='teyit_golge': gölge havuzun alımları da teyit sayılır (girişler yine yalnızca kopyalanan cüzdanlardan)."""
    return [(d["giris"], d["cikis"], d["w"], d["t"], d["g"], d["rt"], kat if d[alan] >= en_az else 1.0) for d in detay]


MODELLER = [
    ("Taban: her sinyal (8x%5, %3)", lambda d: model_a(d, 1)),
    ("Güçlendirici: 2+ cüzdanda 2x", lambda d: guclendirici(d, 2.0)),
    ("Güçlendirici: 2+ cüzdanda 3x", lambda d: guclendirici(d, 3.0)),
    ("Güçlendirici 2x, gölge havuz da teyit eder", lambda d: guclendirici(d, 2.0, alan="teyit_golge")),
    ("Güçlendirici 2x, teyit için 3+ cüzdan (gölge dahil)", lambda d: guclendirici(d, 2.0, en_az=3, alan="teyit_golge")),
    ("Model A: 15 dk'da 2+ cüzdan", lambda d: model_a(d, 2)),
    ("Model A: 15 dk'da 3+ cüzdan", lambda d: model_a(d, 3)),
    ("Model B: 5 dk sonra %3+ düştüyse gir", lambda d: model_b(d, 3.0)),
    ("Model B: 5 dk sonra %8+ düştüyse gir", lambda d: model_b(d, 8.0)),
]
MODEL_AYAR = dict(max_poz=8, oran=0.05, rt_max=3.0)        # 18.11.2026: canlı ayar 8x%5 (kullanıcı onayı)


def modeller(etiket_db=None, now=None, gun=14, golge=None):
    """Girişler yalnızca kopyalanabilecek (gölge dışı) sinyallerden; gölge alımları yalnızca 'teyit_golge'de sayılır."""
    golge = golge_seti() if golge is None else set(golge)
    d = [x for x in sinyaller_detay(etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db"), now, gun, golge) if not x["golge"]]
    return dict(sinyal=len(d), sonuclar=[dict(ad=ad, aday=len(f(d)), **simule(f(d), **MODEL_AYAR)) for ad, f in MODELLER])
