"""EVM cüzdan keşfi (N24, 1. yarı · anahtarsız): yükselen token'ları bulur, her birinin çiftinden İLK dakikalarda token
alan gerçek kullanıcı cüzdanlarını (sözleşme değil) çıkarır. Birden çok yükselen token'ı erken alan cüzdan = aday.

Kaynaklar: DexScreener (öne çıkan ve en yeni token profilleri, çift likiditesi/hacmi/oluşturulma zamanı; anahtarsız),
zincir düğümü (eth_getLogs ile çiftten çıkan Transfer olayları, eth_getCode ile sözleşme ayıklama).
Adayların kârlılık analizi 2. yarıdır (cüzdan işlem geçmişi gerektirir). Salt okunur; emir yok."""
import time
from collections import Counter

import requests

from nexora.evm import TRANSFER, ZINCIRLER, EvmHatasi, _adr, _konu

DS = "https://api.dexscreener.com"
DS_ZINCIR = {"bnb": "bsc", "base": "base"}
GT = "https://api.geckoterminal.com/api/v2/networks/{}/{}"
GT_ZINCIR = {"bnb": "bsc", "base": "base"}


def _iso(v):
    import datetime
    try: return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError): return 0.0


def gt_havuzlari(s, zincir, timeout=15, uyku=time.sleep):
    """GeckoTerminal (anahtarsız): zincirin yükselen ve yeni havuzları -> {token: dict(lik, cift, ts, hacim)}."""
    out = {}
    for i, yol in enumerate(("trending_pools", "trending_pools?page=2", "new_pools", "pools", "pools?page=2")):
        if i: uyku(2.1)                                          # herkese açık hız sınırı (dakikada ~30)
        try:
            d = s.get(GT.format(GT_ZINCIR[zincir], yol), timeout=timeout).json()
        except (requests.RequestException, ValueError):
            continue
        for p in (d or {}).get("data") or [] if isinstance(d, dict) else []:
            a = p.get("attributes") or {}
            tid = ((((p.get("relationships") or {}).get("base_token") or {}).get("data") or {}).get("id") or "")
            tok = tid.split("_", 1)[-1].lower()
            try: lik = float(a.get("reserve_in_usd") or 0); hacim = float((a.get("volume_usd") or {}).get("h24") or 0)
            except (TypeError, ValueError): continue
            if tok.startswith("0x") and lik > out.get(tok, {}).get("lik", -1):
                out[tok] = dict(lik=lik, cift=(a.get("address") or "").lower(), ts=_iso(a.get("pool_created_at")), hacim=hacim)
    return out
SIFIR = "0x" + "0" * 40


def sicak_tokenler(s, zincir, en_fazla=25, min_likidite=50_000, min_hacim=50_000, maks_yas_gun=30, now=None, timeout=15, uyku=time.sleep,
                   istatistik=None):
    """[(token, çift, çift_oluşturma_ts, likidite, hacim24)] — likiditeli, hacimli ve son günlerde açılmış çiftler."""
    now = now or time.time(); hedef = DS_ZINCIR[zincir]
    adresler = []
    for yol in ("/token-boosts/top/v1", "/token-profiles/latest/v1", "/token-boosts/latest/v1"):
        try:
            for x in s.get(DS + yol, timeout=timeout).json() or []:
                if isinstance(x, dict) and x.get("chainId") == hedef and x.get("tokenAddress"):
                    a = x["tokenAddress"].lower()
                    if a not in adresler: adresler.append(a)
        except (requests.RequestException, ValueError, TypeError):
            continue
    out, toplam = [], {}
    def hepsi_ekle(tok, v):                                     # aynı token iki kaynaktan gelirse en likit çift kalır
        if tok not in toplam or v["lik"] > toplam[tok]["lik"]: toplam[tok] = v
    for i in range(0, len(adresler), 30):
        try:
            ciftler = s.get(f"{DS}/tokens/v1/{hedef}/{','.join(adresler[i:i + 30])}", timeout=timeout).json() or []
        except (requests.RequestException, ValueError):
            continue
        en_iyi = {}
        for p in ciftler if isinstance(ciftler, list) else []:
            tok = ((p.get("baseToken") or {}).get("address") or "").lower()
            lik = float((p.get("liquidity") or {}).get("usd") or 0)
            if tok in adresler and lik > en_iyi.get(tok, {}).get("lik", -1):
                en_iyi[tok] = dict(lik=lik, cift=(p.get("pairAddress") or "").lower(), ts=(p.get("pairCreatedAt") or 0) / 1000,
                                  hacim=float((p.get("volume") or {}).get("h24") or 0))
        for tok, v in en_iyi.items(): hepsi_ekle(tok, v)
    n_ds = len(toplam)
    gt = gt_havuzlari(s, zincir, timeout, uyku)
    for tok, v in gt.items(): hepsi_ekle(tok, v)
    if istatistik is not None: istatistik.update(dexscreener=n_ds, geckoterminal=len(gt), toplam=len(toplam))
    karsi = ZINCIRLER[zincir]["karsi"]                         # WETH/USDC gibi karşı varlıklar aday kaynağı değil
    for tok, v in toplam.items():
        if tok in karsi: continue
        if v["lik"] >= min_likidite and v["hacim"] >= min_hacim and v["cift"] and 0 < now - v["ts"] <= maks_yas_gun * 86400:
            out.append((tok, v["cift"], v["ts"], v["lik"], v["hacim"]))
    return sorted(out, key=lambda x: -x[4])[:en_fazla]


def blok_bul(rpc, ts):
    """Zaman damgasına karşılık gelen ilk blok (ikili arama)."""
    hi = rpc.blok(); lo = max(0, hi - 2_000_000)
    if rpc.blok_zamani(lo) > ts: return lo
    while lo < hi:
        m = (lo + hi) // 2
        if rpc.blok_zamani(m) < ts: lo = m + 1
        else: hi = m
    return lo


def _loglar(rpc, filtre, bas, son, en_az=25):
    """eth_getLogs; düğüm aralık/sonuç sınırı derse aralığı ikiye bölerek yeniden dener."""
    try:
        return rpc.call("eth_getLogs", [dict(filtre, fromBlock=hex(bas), toBlock=hex(son))]) or []
    except EvmHatasi as e:
        m = str(e).lower()
        if "hız sınırı" in m or son - bas < en_az or not any(k in m for k in ("limit", "range", "too many", "exceed", "large")): raise
        orta = (bas + son) // 2
        return _loglar(rpc, filtre, bas, orta, en_az) + _loglar(rpc, filtre, orta + 1, son, en_az)


def erken_alicilar(rpc, token, cift, bas_blok, pencere_blok=2400, parca=800):
    """Çiftten token'ı ilk `pencere_blok` blokta alan adresler (çiftin kendisi ve sıfır adres hariç).
    Çift adresinden hiç çıkış yoksa (ör. PancakeSwap v4'te token'lar ortak kasadan çıkar) token'ın o penceredeki
    TÜM alıcılarına bakılır; gönderen = alıcı olanlar atlanır (sözleşmeler sonra ayıklanır)."""
    def tara(konular):
        out = set()
        for b in range(bas_blok, bas_blok + pencere_blok, parca):
            for l in _loglar(rpc, {"address": token, "topics": konular}, b, min(b + parca - 1, bas_blok + pencere_blok)):
                t = l.get("topics") or []
                if len(t) == 3 and t[1] != t[2]: out.add(_adr(t[2]))
        return out
    alicilar = tara([TRANSFER, _konu(cift)])
    if not alicilar: alicilar = tara([TRANSFER])
    return alicilar - {cift, SIFIR}


def kullanici_mi(rpc, adres, _onbellek={}):
    """Sözleşme değil (kodu yok) = gerçek kullanıcı cüzdanı."""
    if adres not in _onbellek:
        try: _onbellek[adres] = (rpc.call("eth_getCode", [adres, "latest"]) or "0x") in ("0x", "0x0")
        except EvmHatasi: return False
    return _onbellek[adres]


def kesfet(rpc, tokenler, en_az=2, bilinen=(), pencere_blok=2400, log=print, gruplar=None):
    say = Counter()
    for tok, cift, ts, lik, hacim in tokenler:
        try:
            b0 = blok_bul(rpc, ts)
            a = erken_alicilar(rpc, tok, cift, b0, pencere_blok)
        except EvmHatasi as e:
            log(f"  {tok[:6]}…{tok[-4:]}: okunamadı ({str(e)[:60]})"); continue
        for w in a: say[w] += 1
        if gruplar is not None: gruplar.append(sorted(a))
        log(f"  {tok[:6]}…{tok[-4:]}  likidite {lik:,.0f} $  hacim {hacim:,.0f} $  erken alıcı {len(a)}")
    bilinen = {b.lower() for b in bilinen}
    adaylar = [w for w, c in say.most_common() if c >= en_az and w not in bilinen and kullanici_mi(rpc, w)]
    return adaylar, say


def bot_adresi_mi(w):
    """Başı sıfırlarla dolu 'vanity' adresler (0x0000…) çoğunlukla ücret tasarrufu yapan botlardır."""
    return w.lower().startswith("0x0000")


def _karisik(g):
    import hashlib
    return sorted(g, key=lambda w: hashlib.sha1(w.encode()).hexdigest())     # alfabetik değil: adres biçimine yanlılık yok


def analiz_adaylari(rpc, gruplar, say, bilinen=(), en_fazla=20):
    """Analiz edilecek adaylar: önce birden çok token'ı erken alanlar, sonra token'lar arasında sırayla tek token'ı erken
    alanlar (her token'dan eşit pay, karışık sırada). Sözleşmeler, bot tipi adresler ve bilinen cüzdanlar atlanır."""
    bilinen = {b.lower() for b in bilinen}; secilen = []
    gruplar = [_karisik(g) for g in gruplar]
    def ekle(w):
        if w not in bilinen and w not in secilen and not bot_adresi_mi(w) and kullanici_mi(rpc, w): secilen.append(w)
    for w, c in say.most_common():
        if c < 2 or len(secilen) >= en_fazla: break
        ekle(w)
    i = 0
    while len(secilen) < en_fazla and any(i < len(g) for g in gruplar):
        for g in gruplar:
            if i < len(g) and len(secilen) < en_fazla: ekle(g[i])
        i += 1
    return secilen


def aktiflik(rpc, w, son, blok_sayisi):
    """Son `blok_sayisi` blokta cüzdanın token hareketi olan farklı işlem sayısı (ucuz ön tarama)."""
    ks = set()
    for konular in ([TRANSFER, None, _konu(w)], [TRANSFER, _konu(w)]):
        for l in _loglar(rpc, {"topics": konular}, son - blok_sayisi, son): ks.add(l.get("transactionHash"))
    return len(ks)
