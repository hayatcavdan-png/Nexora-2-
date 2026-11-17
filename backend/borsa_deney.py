"""Platform 2 deney masası (N22): borsa stratejilerini GEÇMİŞ 1 dakikalık fiyatlarla aynı koşullarda karşılaştırır.

Binance'in herkese açık mum verisi (anahtar yok) en hacimli USDT çiftleri için indirilir ve borsa_mum.db'de saklanır
(sonraki çalıştırmalar yalnızca eksik dakikaları çeker). Her strateji ayrı 100 $'lık sanal portföyde, canlı motorla aynı
kurallarla oynatılır: pozisyon başına %5, en fazla 8 pozisyon, aynı coin'e çıkıştan sonra bekleme, her bacakta ücret+kayma.
Kıyas: aynı dönemde BTC tutmak. Gerçek emir yok; canlı stratejilere dokunmaz.

Çalıştır (backend klasöründe):  python3 borsa_deney.py [gün=7] [coin=60]"""
import os, sqlite3, sys, time
from array import array
from collections import deque

import requests

from nexora.piyasa import uygun_taban, MIN_HACIM, KAYMA, UCRET

KLINE = "https://api.binance.com/api/v3/klines"
TICKER = "https://api.binance.com/api/v3/ticker/24hr"
MALIYET = UCRET + KAYMA + 0.0005          # bacak başına: ücret + kayma + yarım makas tahmini
DB = "borsa_mum.db"


# ---------------------------------------------------------------- veri
def semboller(s, n):
    """24 saat hacmine göre en büyük n USDT çifti (kaldıraçlı/sabit coin hariç)."""
    out = []
    for x in s.get(TICKER, timeout=20).json():
        sym = str(x.get("symbol", ""))
        if not sym.endswith("USDT"): continue
        taban = sym[:-4]
        try: hacim = float(x.get("quoteVolume") or 0)
        except ValueError: continue
        if uygun_taban(taban) and hacim >= MIN_HACIM: out.append((hacim, sym))
    return [sym for _, sym in sorted(out, reverse=True)[:n]]


def indir(s, syms, gun, db=DB, now=None, uyku=0.15, yaz=lambda m: print(m, flush=True)):
    """Eksik dakikaları indirir; {sembol: dakika sayısı} döner (veri belleğe alınmaz, yukle() okur)."""
    now = int(now or time.time())
    bas = int(now - gun * 86400) // 60 * 60
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE IF NOT EXISTS mum(sembol TEXT, ts INTEGER, kapanis REAL, PRIMARY KEY(sembol, ts))")
    hata_gosterildi = False
    for i, sym in enumerate(syms, 1):
        ilk, son = c.execute("SELECT MIN(ts), MAX(ts) FROM mum WHERE sembol=?", (sym,)).fetchone()
        araliklar = [(bas, now - 60)] if son is None else \
            [(bas, ilk)] * (ilk - bas > 120) + [(int(son) + 60, now - 60)]          # geriye eksik günler + yeni dakikalar
        for t, bitis in araliklar:
            t = int(t)
            while t < bitis:
                try:
                    yanit = s.get(KLINE, params=dict(symbol=sym, interval="1m", startTime=t * 1000, limit=1000), timeout=20)
                    r = yanit.json()
                except (requests.RequestException, ValueError) as e:
                    if not hata_gosterildi: yaz(f"  {sym}: istek başarısız ({type(e).__name__}: {str(e)[:100]})"); hata_gosterildi = True
                    break
                if not isinstance(r, list):
                    if not hata_gosterildi:
                        yaz(f"  {sym}: Binance beklenmeyen yanıt verdi (HTTP {getattr(yanit, 'status_code', '?')}): {str(r)[:160]}")
                        hata_gosterildi = True
                    break
                if not r: break
                c.executemany("INSERT OR IGNORE INTO mum VALUES(?,?,?)", [(sym, int(k[0]) // 1000, float(k[4])) for k in r])
                t = int(r[-1][0]) // 1000 + 60
                time.sleep(uyku)
        c.commit()
        if i % 10 == 0: yaz(f"  {i}/{len(syms)} coin indirildi")
    out = {sym: c.execute("SELECT COUNT(*) FROM mum WHERE sembol=? AND ts>=?", (sym, bas)).fetchone()[0] for sym in syms}
    c.close()
    yaz(f"  Toplam {sum(out.values())} dakikalık mum ({sum(1 for v in out.values() if v > 300)} coin yeterli veriyle)")
    return out


# ---------------------------------------------------------------- göstergeler (sıkıştırılmış dizilerle; 14 gün x 60 coin ~ 60 MB)
NAN = float("nan")


def izgara(seri, t0, n):
    """[(ts, fiyat)] -> t0'dan başlayan n dakikalık dizi (eksik dakika NaN)."""
    a = array("d", [NAN]) * n
    for t, p in seri:
        i = (int(t) - t0) // 60
        if 0 <= i < n: a[i] = p
    return a


def _degisim(p, k):
    out = array("d", [NAN]) * len(p)
    for i in range(k, len(p)):
        a, b = p[i], p[i - k]
        if a == a and b == b and b > 0: out[i] = (a / b - 1) * 100
    return out


def _kayan_max(p, w):
    """Önceki w dakikanın zirvesi (şimdiki dakika HARİÇ); pencerenin %90'ı dolmadan NaN."""
    out, q, ilk = array("d", [NAN]) * len(p), deque(), None
    for i in range(len(p)):
        if i > 0 and p[i - 1] == p[i - 1]:
            while q and p[q[-1]] <= p[i - 1]: q.pop()
            q.append(i - 1)
            if ilk is None: ilk = i - 1
        while q and q[0] < i - w: q.popleft()
        if q and ilk is not None and i - ilk >= w * 0.9: out[i] = p[q[0]]
    return out


class Seri:
    """Bir coin'in dakikalık fiyatı ve göstergeleri (aynı ızgarada)."""
    __slots__ = ("p", "r15", "r60", "r240", "z60", "z240")

    def __init__(self, p):
        self.p = p
        self.r15, self.r60, self.r240 = _degisim(p, 15), _degisim(p, 60), _degisim(p, 240)
        self.z60, self.z240 = _kayan_max(p, 60), _kayan_max(p, 240)

    def an(self, i):
        v = lambda a: None if a[i] != a[i] else a[i]
        return dict(p=self.p[i], r15=v(self.r15), r60=v(self.r60), r240=v(self.r240), z60=v(self.z60), z240=v(self.z240))

    def son_fiyat(self):
        for i in range(len(self.p) - 1, -1, -1):
            if self.p[i] == self.p[i]: return self.p[i]
        return None


def yukle(syms, gun, db=DB, now=None):
    """Veritabanından ızgaraya: {sembol: Seri}. Yeterli verisi olmayan coin atlanır."""
    now = int(now or time.time()); t0 = int(now - gun * 86400) // 60 * 60; n = (now - t0) // 60
    c = sqlite3.connect(db); out = {}
    try:
        for sym in syms:
            seri = c.execute("SELECT ts, kapanis FROM mum WHERE sembol=? AND ts>=? ORDER BY ts", (sym, t0)).fetchall()
            if len(seri) > 300: out[sym] = Seri(izgara(seri, t0, n))
    finally:
        c.close()
    return out


# ---------------------------------------------------------------- stratejiler (canlı motorla aynı mantık)
def _momentum(x, esik15=3.0, esik60=3.0):
    return x["r15"] is not None and x["r60"] is not None and x["r15"] >= esik15 and x["r60"] >= esik60

def _trend(x, zirve="z60", r4=1.0, kir=0.5):
    return x["r240"] is not None and x["r240"] > r4 and x[zirve] is not None and x["p"] > x[zirve] * (1 + kir / 100)

def _dip(x, dus60=-6.0):
    return x["r60"] is not None and x["r15"] is not None and x["r60"] <= dus60 and x["r15"] >= 0.5

STRATEJILER = [
    ("momentum (durduruldu): %6 kâr / %3 zarar / 4 sa", dict(giris=_momentum, kar_al=6, zarar_kes=3, sure_dk=240)),
    ("momentum geniş: %10 / %5 / 8 sa", dict(giris=_momentum, kar_al=10, zarar_kes=5, sure_dk=480)),
    ("trend (eski): iz %3 / zarar %4 / 24 sa", dict(giris=_trend, iz=3, zarar_kes=4, sure_dk=1440)),
    ("trend (canlı): iz %8 / zarar %6", dict(giris=_trend, iz=8, zarar_kes=6, sure_dk=1440)),
    ("trend 4 sa kırılım: iz %6 / zarar %6", dict(giris=lambda x: _trend(x, "z240", 2.0, 0.5), iz=6, zarar_kes=6, sure_dk=1440)),
    ("dip alım (durduruldu): 1 sa -%6 ve dönüş, %4 / %6 / 12 sa", dict(giris=_dip, kar_al=4, zarar_kes=6, sure_dk=720)),
]


def simule(veri, giris, kar_al=None, zarar_kes=None, iz=None, sure_dk=240, bekleme_dk=360, max_poz=8, oran=0.05, sermaye=100.0):
    """veri: {sembol: Seri} (aynı ızgara). Dönüş: işlem, kazanma, ortalama getiri, K/Z ($), en büyük düşüş ($)."""
    n = max((len(s.p) for s in veri.values()), default=0)
    nakit, acik, son_cikis, getiriler = sermaye, {}, {}, []
    gercek = zirve = dusus = 0.0
    for i in range(n):
        for sym in list(acik):                                       # 1) çıkışlar
            p = veri[sym].p[i]
            if p != p: continue
            pz = acik[sym]; pz["zirve"] = max(pz["zirve"], p)
            r = (p / pz["giris"] - 1) * 100
            if ((kar_al is not None and r >= kar_al) or (zarar_kes is not None and r <= -zarar_kes)
                    or (iz is not None and pz["zirve"] > pz["giris"] and (1 - p / pz["zirve"]) * 100 >= iz)
                    or i - pz["i"] >= sure_dk):
                net = p * (1 - MALIYET) / (pz["giris"] * (1 + MALIYET)) - 1
                kz = pz["boyut"] * net; nakit += pz["boyut"] + kz; gercek += kz; getiriler.append(net * 100)
                zirve = max(zirve, gercek); dusus = max(dusus, zirve - gercek)
                son_cikis[sym] = i; del acik[sym]
        if len(acik) >= max_poz: continue
        for sym, sr in veri.items():                                 # 2) girişler
            if len(acik) >= max_poz: break
            p = sr.p[i]
            if p != p or sym in acik or i - son_cikis.get(sym, -10 ** 9) < bekleme_dk: continue
            if not giris(sr.an(i)): continue
            ozk = nakit + sum(x["boyut"] for x in acik.values()); boyut = ozk * oran
            if boyut > nakit: continue
            nakit -= boyut; acik[sym] = dict(giris=p, i=i, zirve=p, boyut=boyut)
    for sym, pz in acik.items():                                     # dönem sonu: açık kalanlar son fiyatla değerlenir
        son = veri[sym].son_fiyat() or pz["giris"]
        net = son * (1 - MALIYET) / (pz["giris"] * (1 + MALIYET)) - 1
        gercek += pz["boyut"] * net; getiriler.append(net * 100)
    k = len(getiriler)
    return dict(islem=k, kazanma=round(100 * sum(1 for v in getiriler if v > 0) / k) if k else 0,
                ort=round(sum(getiriler) / k, 2) if k else 0.0, kz=round(gercek, 2), dusus=round(dusus, 2))


def rapor(veri, gun):
    L = [f"== BORSA DENEY MASASI: son {gun:g} gün, {len(veri)} coin, 100$ (pozisyon %5, en fazla 8) =="]
    btc = veri.get("BTCUSDT")
    if btc is not None:
        ilk = next((x for x in btc.p if x == x), None); son = btc.son_fiyat()
        if ilk and son: L.append(f"Kıyas: BTC tutmak %{(son / ilk - 1) * 100:+.2f}  (100$ -> {100 * son / ilk:.2f}$)")
    L.append("strateji / işlem / kazanma / ort. getiri / K/Z / en büyük düşüş")
    for ad, cfg in STRATEJILER:
        r = simule(veri, **cfg)
        L.append(f"  {ad}")
        L.append(f"     {r['islem']:>4} işlem  %{r['kazanma']:<3} ort %{r['ort']:+.2f}  K/Z {r['kz']:+.2f}$  düşüş {r['dusus']:.2f}$")
    L.append("Not: ücret+kayma+makas bacak başına %0.2 varsayıldı; geçmiş performans geleceği garanti etmez.")
    return "\n".join(L)


if __name__ == "__main__":
    gun = float(sys.argv[1]) if len(sys.argv) > 1 else 7.0
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    s = requests.Session()
    syms = semboller(s, n)
    if "BTCUSDT" not in syms: syms.append("BTCUSDT")
    print(f"{len(syms)} coin, {gun:g} gün 1 dakikalık mum indiriliyor (ilk sefer birkaç dakika sürer)...", flush=True)
    simdi = time.time()
    indir(s, syms, gun, now=simdi)
    print("Hesaplanıyor...", flush=True)
    print(rapor(yukle(syms, gun, now=simdi), gun), flush=True)
