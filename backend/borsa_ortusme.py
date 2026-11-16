"""Borsa örtüşme ölçümü: takip sinyallerimizdeki token'ların yüzde kaçı Binance'te işlem görüyor?
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
                                        WHERE side='buy' AND ts>=? GROUP BY token""", (now - gun * 86400,)):
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
    """CoinGecko: bu adres Binance'te işlem görüyor mu? True / False / None (doğrulanamadı)."""
    for deneme in range(2):
        try:
            r = s.get(GECKO.format(mint), params={"tickers": "true", "market_data": "false", "community_data": "false",
                                                  "developer_data": "false", "localization": "false"}, timeout=20)
        except requests.RequestException:
            return None
        if r.status_code == 404: return False                  # CoinGecko bu adresi tanımıyor: listeli coin değil
        if r.status_code == 429 and deneme == 0: uyku(30); continue
        if r.status_code != 200: return None
        try:
            return any((t.get("market") or {}).get("identifier") == "binance" for t in r.json().get("tickers", []))
        except ValueError:
            return None
    return None


def olc(s, tracker=TRACKER, paper=PAPER, gun=GUN, now=None, uyku=time.sleep, api_key=""):
    now = now or time.time()
    sig = sinyaller(tracker, paper, gun, now)
    if not sig: return dict(gun=gun, token=0, sinyal=0, mesaj="bu dönemde alım sinyali yok")
    varlik = binance_varliklar(s)
    sem = semboller(s, sig, api_key, uyku=uyku)
    adaylar = sorted((m for m in sig if sem.get(m, {}).get("sembol") in varlik), key=lambda m: -sig[m]["sinyal"])
    sonuc = {}
    for i, m in enumerate(adaylar[:EN_FAZLA_DOGRULAMA]):
        if i: uyku(2.5)                                         # CoinGecko herkese açık hız sınırı
        sonuc[m] = dogrula(s, m, uyku)
    for m in adaylar[EN_FAZLA_DOGRULAMA:]: sonuc[m] = None
    top_sig = sum(v["sinyal"] for v in sig.values()); top_kop = sum(v["kopya"] for v in sig.values())
    dogru = [m for m, v in sonuc.items() if v]
    belirsiz = [m for m, v in sonuc.items() if v is None]
    pay = lambda ms, k: sum(sig[m][k] for m in ms)
    return dict(gun=gun, token=len(sig), sinyal=top_sig, kopya=top_kop, binance_varlik=len(varlik),
                sembol_eslesen=len(adaylar), dogrulanan=len(dogru), dogrulanamayan=len(belirsiz),
                dogrulanan_sinyal=pay(dogru, "sinyal"), dogrulanan_kopya=pay(dogru, "kopya"),
                sinyal_payi_pct=round(pay(dogru, "sinyal") * 100 / top_sig, 1) if top_sig else 0.0,
                kopya_payi_pct=round(pay(dogru, "kopya") * 100 / top_kop, 1) if top_kop else None,
                ust_sinir_pct=round(pay(dogru + belirsiz, "sinyal") * 100 / top_sig, 1) if top_sig else 0.0,
                tokenler=[dict(mint=m, sembol=sem[m]["sembol"], sinyal=sig[m]["sinyal"], kopya=sig[m]["kopya"],
                               binance={True: "evet", False: "hayır (aynı sembollü başka token)", None: "doğrulanamadı"}[sonuc[m]])
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
    print(f"  Binance spot'ta işlem gören (doğrulanmış): {r['dogrulanan']} token")
    print(f"  Sinyallerin %{r['sinyal_payi_pct']}'i Binance'te alınabilirdi"
          + (f" (kopyalananların %{r['kopya_payi_pct']}'i)" if r["kopya_payi_pct"] is not None else ""))
    if r["dogrulanamayan"]: print(f"  {r['dogrulanamayan']} token doğrulanamadı; en iyimser üst sınır %{r['ust_sinir_pct']}")
    for t in r["tokenler"][:15]:
        print(f"   {t['sembol']:<10} {t['mint'][:4]}…{t['mint'][-4:]}  sinyal {t['sinyal']:>4}  kopya {t['kopya']:>3}  Binance: {t['binance']}")
    print(f"Ayrıntı: {CIKTI}")
    return r


if __name__ == "__main__":
    main(sys.argv[1:])
