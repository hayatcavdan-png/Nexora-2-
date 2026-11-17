"""Platform 2 deney masası (N22): borsa stratejilerini GEÇMİŞ 1 dakikalık fiyatlarla aynı koşullarda karşılaştırır.

Binance'in herkese açık mum verisi (anahtar yok) en hacimli USDT çiftleri için indirilir ve borsa_mum.db'de saklanır
(sonraki çalıştırmalar yalnızca eksik dakikaları çeker). Her strateji ayrı 100 $'lık sanal portföyde, canlı motorla aynı
kurallarla oynatılır: pozisyon başına %5, en fazla 8 pozisyon, aynı coin'e çıkıştan sonra bekleme, her bacakta ücret+kayma.
Kıyas: aynı dönemde BTC tutmak. Gerçek emir yok; canlı stratejilere dokunmaz.

Çalıştır (backend klasöründe):  python3 borsa_deney.py [gün=7] [coin=60]"""
import os, sqlite3, sys, time
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


def indir(s, syms, gun, db=DB, now=None, uyku=0.15, yaz=print):
    """Eksik dakikaları indirir; {sembol: [(ts_sn, kapanış)]} döner."""
    now = int(now or time.time())
    bas = int(now - gun * 86400) // 60 * 60
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE IF NOT EXISTS mum(sembol TEXT, ts INTEGER, kapanis REAL, PRIMARY KEY(sembol, ts))")
    hata_gosterildi = False
    for i, sym in enumerate(syms, 1):
        son = c.execute("SELECT MAX(ts) FROM mum WHERE sembol=?", (sym,)).fetchone()[0]
        t = int(max(bas, (son or 0) + 60))
        while t < now - 60:
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
    out = {}
    for sym in syms:
        out[sym] = c.execute("SELECT ts, kapanis FROM mum WHERE sembol=? AND ts>=? ORDER BY ts", (sym, bas)).fetchall()
    c.close()
    yaz(f"  Toplam {sum(len(v) for v in out.values())} dakikalık mum ({sum(1 for v in out.values() if len(v) > 300)} coin yeterli veriyle)")
    return out


# ---------------------------------------------------------------- göstergeler (dakika indeksiyle, O(n))
def gostergeler(seri):
    """seri [(ts, fiyat)] -> {ts: dict(p, r15, r60, r240, z60, z240)}; r: yüzde değişim, z: önceki pencerenin zirvesi."""
    ts = [t for t, _ in seri]; p = [x for _, x in seri]; idx = {t: i for i, t in enumerate(ts)}
    def r(i, dk):
        j = idx.get(ts[i] - dk * 60)
        return (p[i] / p[j] - 1) * 100 if j is not None and p[j] > 0 else None
    def kayan_max(pencere):
        out, q = [None] * len(p), deque()
        for i in range(len(p)):
            if i > 0:                                  # zirve: şimdiki dakika HARİÇ önceki pencere
                while q and p[q[-1]] <= p[i - 1]: q.pop()
                q.append(i - 1)
            while q and ts[q[0]] < ts[i] - pencere * 60: q.popleft()
            out[i] = p[q[0]] if q and ts[i] - ts[0] >= pencere * 60 * 0.9 else None
        return out
    z60, z240 = kayan_max(60), kayan_max(240)
    return {ts[i]: dict(p=p[i], r15=r(i, 15), r60=r(i, 60), r240=r(i, 240), z60=z60[i], z240=z240[i]) for i in range(len(p))}


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
    ("dip alım (canlı): 1 sa -%6 ve dönüş, %4 / %6 / 12 sa", dict(giris=_dip, kar_al=4, zarar_kes=6, sure_dk=720)),
]


def simule(veri, giris, kar_al=None, zarar_kes=None, iz=None, sure_dk=240, bekleme_dk=360, max_poz=8, oran=0.05, sermaye=100.0):
    """veri: {sembol: {ts: gösterge}}. Dönüş: işlem, kazanma, ortalama getiri, K/Z ($), en büyük düşüş ($)."""
    zaman = sorted({t for g in veri.values() for t in g})
    nakit, acik, son_cikis, getiriler = sermaye, {}, {}, []
    gercek = zirve = dusus = 0.0
    for t in zaman:
        for sym in list(acik):                                       # 1) çıkışlar
            x = veri[sym].get(t)
            if not x: continue
            pz = acik[sym]; pz["zirve"] = max(pz["zirve"], x["p"])
            r = (x["p"] / pz["giris"] - 1) * 100
            neden = ((kar_al is not None and r >= kar_al) or (zarar_kes is not None and r <= -zarar_kes)
                     or (iz is not None and pz["zirve"] > pz["giris"] and (1 - x["p"] / pz["zirve"]) * 100 >= iz)
                     or t - pz["ts"] >= sure_dk * 60)
            if neden:
                net = x["p"] * (1 - MALIYET) / (pz["giris"] * (1 + MALIYET)) - 1
                kz = pz["boyut"] * net; nakit += pz["boyut"] + kz; gercek += kz; getiriler.append(net * 100)
                zirve = max(zirve, gercek); dusus = max(dusus, zirve - gercek)
                son_cikis[sym] = t; del acik[sym]
        for sym, g in veri.items():                                  # 2) girişler
            if len(acik) >= max_poz: break
            x = g.get(t)
            if not x or sym in acik or t - son_cikis.get(sym, -1e18) < bekleme_dk * 60 or not giris(x): continue
            ozk = nakit + sum(p["boyut"] for p in acik.values()); boyut = ozk * oran
            if boyut > nakit: continue
            nakit -= boyut; acik[sym] = dict(giris=x["p"], ts=t, zirve=x["p"], boyut=boyut)
    for sym, pz in acik.items():                                     # dönem sonu: açık kalanlar son fiyatla değerlenir
        son = veri[sym][max(veri[sym])]["p"]
        net = son * (1 - MALIYET) / (pz["giris"] * (1 + MALIYET)) - 1
        gercek += pz["boyut"] * net; getiriler.append(net * 100)
    n = len(getiriler)
    return dict(islem=n, kazanma=round(100 * sum(1 for v in getiriler if v > 0) / n) if n else 0,
                ort=round(sum(getiriler) / n, 2) if n else 0.0, kz=round(gercek, 2), dusus=round(dusus, 2))


def rapor(ham, gun):
    veri = {sym: gostergeler(seri) for sym, seri in ham.items() if len(seri) > 300}
    L = [f"== BORSA DENEY MASASI: son {gun:g} gün, {len(veri)} coin, 100$ (pozisyon %5, en fazla 8) =="]
    btc = ham.get("BTCUSDT") or []
    if len(btc) > 1: L.append(f"Kıyas: BTC tutmak %{(btc[-1][1] / btc[0][1] - 1) * 100:+.2f}  (100$ -> {100 * btc[-1][1] / btc[0][1]:.2f}$)")
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
    print(rapor(indir(s, syms, gun), gun))
