"""Borsa örtüşme ölçümü: takip sinyallerimizdeki token'ların yüzde kaçı Binance / OKX / KuCoin / MEXC'te işlem görüyor?
Amaç: "borsa API'si (MetaTrader modeli)" yoluna geçilirse bugünkü stratejinin ne kadarının orada çalışacağını sayıyla görmek.
Salt okunur. Emir yok, anahtar yok (Binance ve CoinGecko'nun herkese açık uçları).

  python borsa_ortusme.py               # son 7 gün
  ORTUSME_GUN=30 python borsa_ortusme.py

Yöntem (iki adım, yanlış pozitifi önlemek için):
  1) Token sembolü (Jupiter) Binance spot listesindeki bir varlıkla aynı mı?  -> "sembol eşleşti"
  2) CoinGecko'ya göre BU Solana adresi gerçekten o coin mi ve Binance'te işlem görüyor mu? -> "doğrulandı"
  Aynı sembollü sahte token'lar (ör. sahte 'BONK') 2. adımda elenir. CoinGecko sınırına takılırsa "doğrulanamadı" yazılır."""
import json, os, sqlite3, sys, time
import requests

from nexora.constants import USDC_MINT, WSOL_MINT

GUN = int(os.getenv("ORTUSME_GUN", "7"))
TRACKER = os.getenv("TRACKER_DB", "nexora_tracker.db")
PAPER = os.getenv("NEXORA_DB", "nexora_paper.db")
BINANCE = "https://api.binance.com/api/v3/exchangeInfo"
# Borsa -> (herkese açık spot listesi, CoinGecko pazar kimliği). Liste yalnızca ön eleme içindir; karar CoinGecko adres doğrulamasıdır.
BORSALAR = {
    "Binance": ("https://api.binance.com/api/v3/exchangeInfo", "binance"),
    "OKX": ("https://www.okx.com/api/v5/public/instruments?instType=SPOT", "okex"),
    "KuCoin": ("https://api.kucoin.com/api/v2/symbols", "kucoin"),
    "MEXC": ("https://api.mexc.com/api/v3/exchangeInfo", "mxc"),
}
JUP = "https://lite-api.jup.ag/tokens/v2/search"
GECKO = "https://api.coingecko.com/api/v3/coins/solana/contract/{}"
EN_FAZLA_DOGRULAMA = 25
CIKTI = "borsa_ortusme.json"


def sinyaller(tracker, paper, gun, now):
    """{mint: dict(sinyal, cuzdan, kopya)} — son `gun` gündeki alım sinyalleri."""
    out = {}
    if os.path.exists(tracker):
        c = sqlite3.connect(f"file:{tracker}?mode=ro", uri=True, timeout=5)
        try:
            for t, n, w in c.execute("""SELECT token, COUNT(*), COUNT(DISTINCT wallet) FROM tracker_signals
                                        WHERE UPPER(side)='BUY' AND ts>=? GROUP BY token""", (now - gun * 86400,)):
                if t and t not in (USDC_MINT, WSOL_MINT): out[t] = dict(sinyal=n, cuzdan=w, kopya=0)
        finally:
            c.close()
    if os.path.exists(paper):
        c = sqlite3.connect(f"file:{paper}?mode=ro", uri=True, timeout=5)
        try:
            for t, n in c.execute("""SELECT token, COUNT(*) FROM trades WHERE side='buy' AND decision='KOPYALANDI' AND ts>=?
                                     GROUP BY token""", (now - gun * 86400,)):
                if t in out: out[t]["kopya"] = n
        except sqlite3.OperationalError:
            pass
        finally:
            c.close()
    return out


def binance_varliklar(s):
    r = s.get(BINANCE, timeout=20)
    if r.status_code != 200: raise RuntimeError(f"Binance HTTP {r.status_code}")
    return {x["baseAsset"].upper() for x in r.json().get("symbols", []) if x.get("status") == "TRADING"}


def borsa_varliklari(s, ad):
    """Borsanın spot varlık sembolleri. Hata: None (o borsa 'okunamadı' yazılır, diğerleri sürer)."""
    url = BORSALAR[ad][0]
    try:
        r = s.get(url, timeout=20)
        if r.status_code != 200: return None
        d = r.json()
    except (requests.RequestException, ValueError):
        return None
    if ad in ("Binance", "MEXC"):
        return {x["baseAsset"].upper() for x in d.get("symbols", []) if x.get("baseAsset") and str(x.get("status")) in ("TRADING", "1", "ENABLED")}
    if ad == "OKX":
        return {x["baseCcy"].upper() for x in d.get("data", []) if x.get("baseCcy") and x.get("state", "live") == "live"}
    if ad == "KuCoin":
        return {x["baseCurrency"].upper() for x in d.get("data", []) if x.get("baseCurrency") and x.get("enableTrading", True)}
    return None


def semboller(s, mints, api_key="", bekle=1.1, uyku=time.sleep):
    url, h = ("https://api.jup.ag/tokens/v2/search", {"x-api-key": api_key}) if api_key else (JUP, {})
    out, liste = {}, list(mints)
    for i in range(0, len(liste), 100):
        if i: uyku(bekle)
        try:
            r = s.get(url, params={"query": ",".join(liste[i:i + 100])}, headers=h, timeout=20)
            for x in (r.json() if r.status_code == 200 else []):
                if isinstance(x, dict) and x.get("id"): out[x["id"]] = dict(sembol=(x.get("symbol") or "").upper(), ad=x.get("name") or "")
        except (requests.RequestException, ValueError):
            pass
    return out


def dogrula(s, mint, uyku=time.sleep):
    """CoinGecko: bu adres hangi borsalarda işlem görüyor? set (boş = hiçbirinde) / None (doğrulanamadı)."""
    for deneme in range(2):
        try:
            r = s.get(GECKO.format(mint), params={"tickers": "true", "market_data": "false", "community_data": "false",
                                                  "developer_data": "false", "localization": "false"}, timeout=20)
        except requests.RequestException:
            return None
        if r.status_code == 404: return set()                  # CoinGecko bu adresi tanımıyor: listeli coin değil
        if r.status_code == 429 and deneme == 0: uyku(30); continue
        if r.status_code != 200: return None
        try:
            kimlik = {(t.get("market") or {}).get("identifier") for t in r.json().get("tickers", [])}
            return {ad for ad, (_, gid) in BORSALAR.items() if gid in kimlik}
        except ValueError:
            return None
    return None


def olc(s, tracker=TRACKER, paper=PAPER, gun=GUN, now=None, uyku=time.sleep, api_key=""):
    now = now or time.time()
    sig = sinyaller(tracker, paper, gun, now)
    if not sig: return dict(gun=gun, token=0, sinyal=0, mesaj="bu dönemde alım sinyali yok")
    varlik = {ad: borsa_varliklari(s, ad) for ad in BORSALAR}
    if all(v is None for v in varlik.values()): raise RuntimeError("hiçbir borsanın listesi okunamadı")
    birlesik = set().union(*(v for v in varlik.values() if v))
    sem = semboller(s, sig, api_key, uyku=uyku)
    adaylar = sorted((m for m in sig if sem.get(m, {}).get("sembol") in birlesik), key=lambda m: -sig[m]["sinyal"])
    sonuc = {}
    for i, m in enumerate(adaylar[:EN_FAZLA_DOGRULAMA]):
        if i: uyku(2.5)                                         # CoinGecko herkese açık hız sınırı
        sonuc[m] = dogrula(s, m, uyku)
    for m in adaylar[EN_FAZLA_DOGRULAMA:]: sonuc[m] = None
    top_sig = sum(v["sinyal"] for v in sig.values()); top_kop = sum(v["kopya"] for v in sig.values())
    belirsiz = [m for m, v in sonuc.items() if v is None]
    pay = lambda ms, k: sum(sig[m][k] for m in ms)
    pct = lambda x, n: round(x * 100 / n, 1) if n else None
    borsalar = {}
    for ad in BORSALAR:
        ms = [m for m, v in sonuc.items() if v and ad in v]
        borsalar[ad] = dict(okunamadi=varlik[ad] is None, token=len(ms), sinyal_payi_pct=pct(pay(ms, "sinyal"), top_sig),
                            kopya_payi_pct=pct(pay(ms, "kopya"), top_kop))
    herhangi = [m for m, v in sonuc.items() if v]
    return dict(gun=gun, token=len(sig), sinyal=top_sig, kopya=top_kop, sembol_eslesen=len(adaylar),
                dogrulanamayan=len(belirsiz), borsalar=borsalar,
                herhangi=dict(token=len(herhangi), sinyal_payi_pct=pct(pay(herhangi, "sinyal"), top_sig),
                              kopya_payi_pct=pct(pay(herhangi, "kopya"), top_kop)),
                ust_sinir_pct=pct(pay(herhangi + belirsiz, "sinyal"), top_sig),
                tokenler=[dict(mint=m, sembol=sem[m]["sembol"], sinyal=sig[m]["sinyal"], kopya=sig[m]["kopya"],
                               borsalar="doğrulanamadı" if sonuc[m] is None else (", ".join(sorted(sonuc[m])) or "hiçbiri (aynı sembollü başka token)"))
                          for m in adaylar], ts=now)


def main(argv=(), s=None):
    s = s or requests.Session()
    try:
        r = olc(s, api_key=os.getenv("JUPITER_API_KEY", ""))
    except (RuntimeError, requests.RequestException, ValueError) as e:
        sys.exit(f"Ölçüm yapılamadı: {e}")
    with open(CIKTI, "w") as f: json.dump(r, f, ensure_ascii=False, indent=1)
    if not r.get("token"): print(r.get("mesaj")); return r
    print(f"Borsa örtüşmesi (son {r['gun']} gün): {r['token']} farklı token, {r['sinyal']} alım sinyali, {r['kopya']} kopyalanan alım")
    print("  Sinyallerin ne kadarı bu borsada alınabilirdi (adresle doğrulanmış):")
    for ad, b in r["borsalar"].items():
        if b["okunamadi"]: print(f"   {ad:<8} liste okunamadı"); continue
        print(f"   {ad:<8} %{b['sinyal_payi_pct']:<5} sinyal · {b['token']} token"
              + (f" · kopyalananların %{b['kopya_payi_pct']}'i" if b["kopya_payi_pct"] is not None else ""))
    h = r["herhangi"]
    print(f"   Herhangi biri: %{h['sinyal_payi_pct']} sinyal · {h['token']} token")
    if r["dogrulanamayan"]: print(f"  {r['dogrulanamayan']} token doğrulanamadı; en iyimser üst sınır %{r['ust_sinir_pct']}")
    for t in r["tokenler"][:15]:
        print(f"   {t['sembol']:<10} {t['mint'][:4]}…{t['mint'][-4:]}  sinyal {t['sinyal']:>4}  kopya {t['kopya']:>3}  {t['borsalar']}")
    print(f"Ayrıntı: {CIKTI}")
    return r


if __name__ == "__main__":
    main(sys.argv[1:])
