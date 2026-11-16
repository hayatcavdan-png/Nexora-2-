"""Platform 2 (borsa): dört borsada (Binance, OKX, KuCoin, MEXC) spot işlem gören SOLANA token'larının adres listesi.

Kaynak CoinGecko (herkese açık uçlar, anahtar yok):
  /coins/list?include_platform=true      -> coin kimliği -> Solana adresi (mint)
  /exchanges/{borsa}/tickers?page=N      -> borsada işlem gören coin kimlikleri, çift (BONK/USDT), 24 saat hacim
Sonuç borsa_tokenleri.json: {mint: {sembol, coin_id, borsalar: {Binance: {taban, karsi, hacim_usd}}}}.
Yalnızca USDT/USDC karşılıklı çiftler alınır (fiyat USD cinsinden). Günde bir yenilemek yeterli."""
import json, os, time

import requests

GECKO = "https://api.coingecko.com/api/v3"
BORSA_ID = {"Binance": "binance", "OKX": "okex", "KuCoin": "kucoin", "MEXC": "mxc"}
KARSI = ("USDT", "USDC")
DOSYA = os.getenv("BORSA_LISTE", "borsa_tokenleri.json")
EN_COK_SAYFA = 40


def _get(s, yol, params=None, uyku=time.sleep):
    for deneme in range(3):
        r = s.get(GECKO + yol, params=params or {}, timeout=30)
        if r.status_code == 429 and deneme < 2: uyku(40); continue
        if r.status_code != 200: raise RuntimeError(f"CoinGecko {yol} HTTP {r.status_code}")
        return r.json()
    raise RuntimeError("CoinGecko hız sınırı")


def solana_adresleri(s, uyku=time.sleep):
    """coin_id -> (mint, sembol)."""
    out = {}
    for c in _get(s, "/coins/list", {"include_platform": "true"}, uyku):
        m = ((c.get("platforms") or {}).get("solana") or "").strip()
        if m: out[c["id"]] = (m, (c.get("symbol") or "").upper())
    return out


def borsa_ciftleri(s, borsa, uyku=time.sleep, bekle=2.5):
    """Borsadaki USDT/USDC çiftleri: {coin_id: dict(taban, karsi, hacim_usd)} (aynı coin'in en hacimli çifti)."""
    out = {}
    for sayfa in range(1, EN_COK_SAYFA + 1):
        if sayfa > 1: uyku(bekle)
        d = _get(s, f"/exchanges/{BORSA_ID[borsa]}/tickers", {"page": sayfa}, uyku)
        t = d.get("tickers") or []
        for x in t:
            if (x.get("target") or "").upper() not in KARSI or x.get("is_stale") or x.get("is_anomaly"): continue
            cid = x.get("coin_id")
            hacim = float((x.get("converted_volume") or {}).get("usd") or 0)
            if cid and hacim > out.get(cid, {}).get("hacim_usd", -1):
                out[cid] = dict(taban=x["base"].upper(), karsi=x["target"].upper(), hacim_usd=round(hacim, 2))
        if len(t) < 100: break
    return out


def olustur(s=None, uyku=time.sleep, dosya=DOSYA, now=None):
    s = s or requests.Session()
    adres = solana_adresleri(s, uyku)
    liste, hatalar = {}, {}
    for borsa in BORSA_ID:
        uyku(2.5)
        try:
            ciftler = borsa_ciftleri(s, borsa, uyku)
        except (RuntimeError, requests.RequestException, ValueError) as e:
            hatalar[borsa] = str(e)[:120]; continue
        for cid, c in ciftler.items():
            if cid not in adres: continue
            m, sembol = adres[cid]
            t = liste.setdefault(m, dict(sembol=sembol, coin_id=cid, borsalar={}))
            t["borsalar"][borsa] = c
    veri = dict(ts=now or time.time(), token=len(liste), hatalar=hatalar,
                borsa_basina={b: sum(1 for t in liste.values() if b in t["borsalar"]) for b in BORSA_ID}, tokenler=liste)
    gecici = dosya + ".tmp"
    with open(gecici, "w") as f: json.dump(veri, f, ensure_ascii=False)
    os.replace(gecici, dosya)
    return veri


def yukle(dosya=DOSYA):
    """{mint: token} ya da {} (dosya yok/bozuk)."""
    try:
        with open(dosya) as f: return json.load(f).get("tokenler") or {}
    except (OSError, ValueError):
        return {}


def en_iyi_borsa(token, sira=("Binance", "OKX", "KuCoin", "MEXC")):
    """Token'ın en hacimli borsası (eşitlikte sıradaki tercih)."""
    b = token.get("borsalar") or {}
    if not b: return None
    return max(b, key=lambda k: (b[k].get("hacim_usd") or 0, -sira.index(k) if k in sira else -99))
