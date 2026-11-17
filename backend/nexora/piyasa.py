"""Platform 2 · piyasa verisi stratejileri (PAPER): Binance, OKX, KuCoin ve MEXC'teki TÜM USDT çiftleri (BTC, ETH, SOL ve
diğerleri). Her dakika dört borsanın tüm fiyatları tek istekle alınır (herkese açık uçlar, anahtar yok); her coin en hacimli
borsasından izlenir. Her strateji AYRI sanal portföyde (kendi veritabanı) ölçülür; böylece hangisinin işe yaradığı ayrı görülür.

Maliyet modeli: alım en iyi satış fiyatından (ask), satış en iyi alış fiyatından (bid); ek %0.05 kayma ve %0.1 borsa ücreti
(her bacak). Risk kuralları platform 1 ile aynı (pozisyon başına %5, günlük %3 zarar, en fazla 8 pozisyon).
Kıyas: BTC'yi izlemeye başladığımız andan beri tutmak. Gerçek emir YOK."""
import json, math, time
from collections import deque

import requests

KARSI = "USDT"
HARIC = {"USDC", "FDUSD", "TUSD", "DAI", "USDP", "BUSD", "EUR", "TRY", "USDE", "PYUSD", "USD1", "AEUR", "EURI", "XUSD", "USDD",
         "WBTC", "WETH", "STETH", "PAXG", "XAUT"}
KALDIRACLI = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S", "2L", "2S")
MIN_HACIM = 1_000_000              # 24 saat USDT hacmi: altındaki çiftler izlenmez (sığ defter)
MAKS_MAKAS_PCT = 0.3               # alış-satış farkı bundan genişse alım yok
GECMIS_SN = 6 * 3600
KAYMA, UCRET = 0.0005, 0.001


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None


def _ayir(sembol):
    for ayrac in ("-", "_", "/"):
        if ayrac in sembol: return tuple(sembol.split(ayrac, 1))
    return (sembol[:-len(KARSI)], KARSI) if sembol.endswith(KARSI) else (None, None)


def uygun_taban(taban):
    if not taban or taban in HARIC: return False
    return not any(taban.endswith(k) and len(taban) > len(k) + 1 for k in KALDIRACLI)


def borsa_fiyatlari(s, borsa, timeout=15):
    """Tüm USDT çiftleri: {taban: dict(son, bid, ask, hacim)}. Hata: None."""
    try:
        if borsa in ("Binance", "MEXC"):
            url = "https://api.binance.com/api/v3/ticker/24hr" if borsa == "Binance" else "https://api.mexc.com/api/v3/ticker/24hr"
            satirlar = [(x.get("symbol", ""), x.get("lastPrice"), x.get("bidPrice"), x.get("askPrice"), x.get("quoteVolume"))
                        for x in s.get(url, timeout=timeout).json()]
        elif borsa == "OKX":
            d = s.get("https://www.okx.com/api/v5/market/tickers", params={"instType": "SPOT"}, timeout=timeout).json()
            satirlar = [(x.get("instId", ""), x.get("last"), x.get("bidPx"), x.get("askPx"), x.get("volCcy24h")) for x in d.get("data", [])]
        elif borsa == "KuCoin":
            d = s.get("https://api.kucoin.com/api/v1/market/allTickers", timeout=timeout).json()
            satirlar = [(x.get("symbol", ""), x.get("last"), x.get("buy"), x.get("sell"), x.get("volValue"))
                        for x in (d.get("data") or {}).get("ticker", [])]
        else:
            return None
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return None
    out = {}
    for sembol, son, bid, ask, hacim in satirlar:
        taban, karsi = _ayir(str(sembol).upper())
        if karsi != KARSI or not uygun_taban(taban): continue
        son, bid, ask, hacim = _f(son), _f(bid), _f(ask), _f(hacim)
        if not (son and bid and ask and hacim) or ask < bid: continue
        out[taban] = dict(son=son, bid=bid, ask=ask, hacim=hacim)
    return out


def evren(fiyatlar, min_hacim=MIN_HACIM):
    """Her coin için en hacimli borsa: {taban: dict(borsa, son, bid, ask, hacim)}."""
    out = {}
    for borsa, tablo in fiyatlar.items():
        for taban, v in (tablo or {}).items():
            if v["hacim"] >= min_hacim and v["hacim"] > out.get(taban, {}).get("hacim", 0):
                out[taban] = dict(v, borsa=borsa)
    return out


class Gecmis:
    """Coin başına son 6 saatlik dakikalık fiyat örnekleri."""
    def __init__(self, sure=GECMIS_SN):
        self.sure, self.v = sure, {}

    def ekle(self, taban, ts, fiyat):
        d = self.v.setdefault(taban, deque())
        d.append((ts, fiyat))
        while d and ts - d[0][0] > self.sure: d.popleft()

    def degisim(self, taban, sn, now):
        """`sn` saniye önceki fiyata göre % değişim (o kadar geçmiş yoksa None)."""
        d = self.v.get(taban)
        if not d or now - d[0][0] < sn * 0.9: return None
        hedef = now - sn
        eski = next((p for t, p in d if t >= hedef), None)
        return (d[-1][1] / eski - 1) * 100 if eski else None

    def zirve(self, taban, bas, bit):
        return max((p for t, p in self.v.get(taban, ()) if bas <= t < bit), default=None)


class Strateji:
    """Temel: giriş kuralı + çıkış kuralı (kâr al / zarar kes / iz süren durdurma / süre)."""
    ad, aciklama = "temel", ""
    kar_al = zarar_kes = iz = None
    sure_sn = 4 * 3600
    bekleme_sn = 6 * 3600                 # aynı coin'e bu süre içinde yeniden girilmez

    def giris(self, g, taban, v, now): return False

    def cikis(self, poz, v, now):
        """poz: dict(giris_fiyat, giris_ts, zirve). Dönüş: neden ya da None."""
        r = (v["bid"] / poz["giris_fiyat"] - 1) * 100
        if self.kar_al is not None and r >= self.kar_al: return f"kâr al (%{r:.1f})"
        if self.zarar_kes is not None and r <= -self.zarar_kes: return f"zarar kes (%{r:.1f})"
        if self.iz is not None and poz["zirve"] > poz["giris_fiyat"]:
            dusus = (1 - v["bid"] / poz["zirve"]) * 100
            if dusus >= self.iz: return f"iz süren durdurma (zirveden %{dusus:.1f})"
        if now - poz["giris_ts"] >= self.sure_sn: return f"süre doldu (%{r:+.1f})"
        return None


class Momentum(Strateji):
    ad = "momentum"
    aciklama = "15 dakikada %3+ yükselen ve son 1 saatte de artıda olan coin; kâr al %6, zarar kes %3, en fazla 4 saat"
    kar_al, zarar_kes, sure_sn = 6.0, 3.0, 4 * 3600

    def giris(self, g, taban, v, now):
        r15, r60 = g.degisim(taban, 900, now), g.degisim(taban, 3600, now)
        return r15 is not None and r60 is not None and r15 >= 3.0 and r60 >= 3.0


class Trend(Strateji):
    ad = "trend"
    aciklama = "son 1 saatin zirvesini kıran ve 4 saatte artıda olan coin; iz süren durdurma %8, zarar kes %6, en fazla 24 saat"
    # 17.11.2026 (borsa deney masası, 7 gün / 60 coin): iz %3 erken çıkıyordu (+2.22$); iz %8 / zarar %6 en iyisi (+3.44$)
    zarar_kes, iz, sure_sn = 6.0, 8.0, 24 * 3600

    def giris(self, g, taban, v, now):
        r240 = g.degisim(taban, 4 * 3600, now)
        z = g.zirve(taban, now - 3600, now - 60)
        return r240 is not None and r240 > 1.0 and z is not None and v["son"] > z * 1.005


class Dip(Strateji):
    ad = "dip"
    aciklama = "1 saatte %6+ düşüp son 15 dakikada toparlanmaya başlayan coin; kâr al %4, zarar kes %6, en fazla 12 saat"
    kar_al, zarar_kes, sure_sn = 4.0, 6.0, 12 * 3600

    def giris(self, g, taban, v, now):
        r15, r60 = g.degisim(taban, 900, now), g.degisim(taban, 3600, now)
        return r15 is not None and r60 is not None and r60 <= -6.0 and r15 >= 0.5


# 17.11.2026 (kullanıcı onayı, borsa deney masası): momentum iki ayarda da zararda -> durduruldu (sınıf kodda, geçmiş veri korunur);
# yerine dip alım ölçülüyor. Girişler yalnızca hacme göre en büyük EVREN_SAYI coin'de (küçük coin'de makas ve gürültü zarar ettiriyordu).
STRATEJILER = (Trend(), Dip())
EVREN_SAYI = 60


class Motor:
    """Her dakika: fiyatları al, geçmişi güncelle, açık pozisyonların çıkışını, sonra yeni girişleri değerlendir."""
    def __init__(self, portfoyler, s=None, borsalar=("Binance", "OKX", "KuCoin", "MEXC"), durum_dosyasi="piyasa_durum.json",
                 stratejiler=None, evren_sayi=None):
        self.p = portfoyler                  # {strateji adı: Paper}
        self.st = stratejiler or STRATEJILER
        self.evren_sayi = evren_sayi if evren_sayi is not None else EVREN_SAYI
        self.s, self.borsalar, self.durum_dosyasi = s or requests.Session(), borsalar, durum_dosyasi
        self.g = Gecmis(); self.kiyas = None

    def _poz(self, paper, token):
        try: return json.loads(paper._get(f"poz:{token}") or "null")
        except ValueError: return None

    def tur(self, now=None, fiyatlar=None):
        now = now or time.time()
        fiyatlar = fiyatlar if fiyatlar is not None else {b: borsa_fiyatlari(self.s, b) for b in self.borsalar}
        ev = evren(fiyatlar)
        for taban, v in ev.items(): self.g.ekle(taban, now, v["son"])
        if self.kiyas is None and "BTC" in ev: self.kiyas = (now, ev["BTC"]["son"])
        olay = []
        secili = {t for t, _ in sorted(ev.items(), key=lambda kv: -kv[1]["hacim"])[:self.evren_sayi]} if self.evren_sayi else set(ev)
        for st in self.st:
            paper = self.p[st.ad]
            for poz_satir in paper.portfolio()["positions"]:                   # 1) çıkışlar
                token = poz_satir["token"]; taban = token.split(":", 1)[1].split("/")[0]
                v = ev.get(taban); poz = self._poz(paper, token)
                if not v or not poz: continue
                paper.mark_price(token, v["bid"])
                if v["bid"] > poz["zirve"]: poz["zirve"] = v["bid"]; paper._set(f"poz:{token}", json.dumps(poz))
                neden = st.cikis(poz, v, now)
                if neden:
                    r = paper.handle_signal(f"{st.ad}:{token}:{int(now)}:sat", st.ad, token, "sell", v["bid"], v["hacim"], 0)
                    if r.get("decision") == "KOPYALANDI": paper._set(f"son_cikis:{token}", str(now)); olay.append((st.ad, "sat", token, neden))
            for taban, v in ev.items():                                        # 2) girişler (yalnızca en hacimli coin'ler)
                if taban not in secili: continue
                token = f"{v['borsa']}:{taban}/{KARSI}"
                if paper.position(token): continue
                son = float(paper._get(f"son_cikis:{token}") or 0)
                if now - son < st.bekleme_sn: continue
                if (v["ask"] - v["bid"]) / v["ask"] * 100 > MAKS_MAKAS_PCT: continue
                if not st.giris(self.g, taban, v, now): continue
                r = paper.handle_signal(f"{st.ad}:{token}:{int(now)}:al", st.ad, token, "buy", v["ask"], v["hacim"], 0)
                if r.get("decision") == "KOPYALANDI":
                    paper._set(f"poz:{token}", json.dumps(dict(giris_fiyat=v["ask"], giris_ts=now, zirve=v["ask"])))
                    paper._set(f"son_cikis:{token}", str(now))       # aynı coin'e kısa sürede yeniden girmeyi de engeller
                    olay.append((st.ad, "al", token, f"{v['borsa']} {v['ask']:.6g}"))
        durum = dict(ts=now, evren=len(ev), borsalar={b: (None if fiyatlar.get(b) is None else len(fiyatlar[b])) for b in self.borsalar},
                     kiyas_btc_pct=round((ev["BTC"]["son"] / self.kiyas[1] - 1) * 100, 2) if self.kiyas and "BTC" in ev else None,
                     kiyas_bas=self.kiyas[0] if self.kiyas else None)
        try:
            with open(self.durum_dosyasi + ".tmp", "w") as f: json.dump(durum, f)
            import os; os.replace(self.durum_dosyasi + ".tmp", self.durum_dosyasi)
        except OSError:
            pass
        return olay, durum


def ozet(paper, st):
    """Strateji karnesi: değer, K/Z, kapanan işlem, kazanma oranı, ortalama, en iyi/en kötü."""
    p = paper.portfolio()
    kap = [t for t in paper.trades(5000) if t["decision"] == "KOPYALANDI" and t["side"] == "sell"]
    pnl = [t["pnl"] or 0 for t in kap]
    kazanc, kayip = sum(x for x in pnl if x > 0), -sum(x for x in pnl if x < 0)
    return dict(ad=st.ad, aciklama=st.aciklama, toplam=round(p["equity"], 2), kz=round(p["pnl"], 2), acik=len(p["positions"]),
                kapanan=len(kap), kazanma_pct=round(sum(x > 0 for x in pnl) * 100 / len(pnl), 1) if pnl else None,
                ort=round(sum(pnl) / len(pnl), 3) if pnl else None,
                profit_factor=round(kazanc / kayip, 2) if kayip > 0 else None,
                son=[dict(ts=t["ts"], token=t["token"], side=t["side"], pnl=t["pnl"], fiyat=t["price"])
                     for t in paper.trades(8) if t["decision"] == "KOPYALANDI"],
                pozisyonlar=[dict(token=x["token"], maliyet=x["cost"], deger=round(x["qty"] * x["last_price"], 4)) for x in p["positions"]])
