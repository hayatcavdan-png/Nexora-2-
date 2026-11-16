"""EVM bağdaştırıcısı (N24 BNB Chain, N25 Base): salt okunur zincir verisi, swap çözme, fiyat teklifi, token güvenliği.

- Zincir verisi: JSON-RPC (yalnızca okuma yöntemleri; işlem GÖNDERME yöntemi listede YOK).
- Swap çözme: işlem makbuzundaki ERC-20 Transfer olaylarından cüzdanın net token değişimi + işlemle gönderilen yerel coin.
  Tek bir "karşı" olmayan token artıp karşı varlık (yerel coin, sarılmış yerel coin, stablecoin) azaldıysa ALIM; tersi SATIM.
- Fiyat: KyberSwap toplayıcısı (herkese açık uç, anahtar yok).
- Güvenlik: GoPlus token güvenlik API'si (honeypot, alım/satım vergisi, satılamama, kara liste, likidite).
Hiçbir yerde özel anahtar yok; emir gönderilmez."""
import time

import requests

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
WITHDRAWAL = "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65"   # WETH/WBNB unwrap
YEREL = "yerel"                                                                      # zincirin yerel coin'i (BNB/ETH)

ZINCIRLER = {
    "bnb": dict(ad="BNB Chain", zincir_id=56, rpc_env="BNB_RPC_URL", rpc="https://bsc-dataseed.bnbchain.org", kyber="bsc", goplus="56",
                sarili="0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", usd="0x55d398326f99059ff775485246999027b3197955", usd_ondalik=18,
                karsi={"0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", "0x55d398326f99059ff775485246999027b3197955",
                       "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", "0xe9e7cea3dedca5984780bafc599bd69add087d56",
                       "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409"}),
    "base": dict(ad="Base", zincir_id=8453, gezgin="https://base.blockscout.com", gezgin2="https://api.routescan.io/v2/network/mainnet/evm/8453/etherscan/api", rpc_env="BASE_RPC_URL", rpc="https://mainnet.base.org", kyber="base", goplus="8453",
                 sarili="0x4200000000000000000000000000000000000006", usd="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", usd_ondalik=6,
                 karsi={"0x4200000000000000000000000000000000000006", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                        "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2", "0x50c5725949a6f0c72e6c4a641f24049a917db0cb",
                        "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"}),
}


class EvmHatasi(RuntimeError):
    pass


def _adr(konu):
    """32 baytlık olay konusundan adres."""
    return "0x" + konu[-40:].lower()


def _konu(adres):
    return "0x" + "0" * 24 + adres.lower()[2:]


class EvmRpc:
    YONTEMLER = {"eth_chainId", "eth_blockNumber", "eth_getLogs", "eth_getTransactionByHash", "eth_getTransactionReceipt",
                 "eth_getBlockByNumber", "eth_call", "eth_getCode", "eth_getBalance"}

    HIZ = ("request limit", "rate limit", "too many requests", "exceeded the rate", "capacity")

    def __init__(self, url, session=None, timeout=15, uyku=time.sleep):
        self.url, self.s, self.timeout, self._id, self.uyku = url, session or requests.Session(), timeout, 0, uyku

    def call(self, yontem, params):
        """Hız sınırında (HTTP 429 ya da 'request limit' vb.) bekleyip 3 kez yeniden dener; aşılamazsa 'RPC hız sınırı'."""
        if yontem not in self.YONTEMLER: raise ValueError("bu RPC yöntemi izinli salt okunur listede değil")
        for deneme in range(4):
            self._id += 1
            try:
                r = self.s.post(self.url, json=dict(jsonrpc="2.0", id=self._id, method=yontem, params=params), timeout=self.timeout)
                d = r.json() if r.status_code != 429 else {"error": {"message": "too many requests"}}
            except (requests.RequestException, ValueError) as e:
                raise EvmHatasi(f"RPC bağlantı hatası: {type(e).__name__}") from None
            hata = d.get("error") if isinstance(d, dict) else None
            mesaj = str(hata.get("message", hata) if isinstance(hata, dict) else hata or "")
            if hata and any(h in mesaj.lower() for h in self.HIZ):
                if deneme < 3: self.uyku(1.5 * 2 ** deneme); continue
                raise EvmHatasi("RPC hız sınırı (düğüm anahtarı gerekebilir)")
            if hata: raise EvmHatasi(f"RPC: {mesaj[:300]}")
            if not isinstance(d, dict) or "result" not in d: raise EvmHatasi("RPC yanıtı boş")
            return d["result"]

    def blok(self):
        return int(self.call("eth_blockNumber", []), 16)

    def blok_zamani(self, n):
        b = self.call("eth_getBlockByNumber", [hex(n), False]) or {}
        return int(b.get("timestamp", "0x0"), 16)

    def ondalik(self, token, _onbellek={}):
        k = (self.url, token)
        if k not in _onbellek:
            v = self.call("eth_call", [{"to": token, "data": "0x313ce567"}, "latest"])
            _onbellek[k] = int(v, 16) if v and v != "0x" else 18
        return _onbellek[k]

    def cuzdan_islemleri(self, cuzdanlar, bas, son):
        """[bas, son] bloklarında cüzdanlara gelen/giden ERC-20 transferlerinin işlem karmaları: {karma: (blok, cüzdan)}."""
        konular = [_konu(w) for w in cuzdanlar]
        out = {}
        for filtre, yer in (([TRANSFER, None, konular], 2), ([TRANSFER, konular], 1)):
            for l in self.call("eth_getLogs", [{"fromBlock": hex(bas), "toBlock": hex(son), "topics": filtre}]) or []:
                t = l.get("topics") or []
                if len(t) != 3: continue                          # ERC-721 vb. atlanır
                out.setdefault(l["transactionHash"], (int(l["blockNumber"], 16), _adr(t[yer])))
        return out


def yerel_fark(rpc, cuzdan, blok, tx, makbuz):
    """Cüzdanın bu bloktaki yerel coin (BNB/ETH) değişimi, ödenen işlem ücreti geri eklenmiş: olay kaydı bırakmayan
    yerel coin ödemelerini (ör. PancakeSwap v4'te BNB'ye satış) görmek için. Düğüm eski bakiyeyi veremezse None."""
    try:
        once = int(rpc.call("eth_getBalance", [cuzdan, hex(blok - 1)]), 16)
        sonra = int(rpc.call("eth_getBalance", [cuzdan, hex(blok)]), 16)
    except (EvmHatasi, TypeError, ValueError):
        return None
    fark = sonra - once
    if (tx.get("from") or "").lower() == cuzdan.lower():
        try: fark += int(makbuz.get("gasUsed") or "0x0", 16) * int(makbuz.get("effectiveGasPrice") or tx.get("gasPrice") or "0x0", 16)
        except (TypeError, ValueError): pass
    return fark


def coz(tx, makbuz, cuzdan, zincir, yerel=None):
    """İşlemden cüzdanın swap'ı: dict(yon, token, miktar_raw, karsi, karsi_raw) ya da None (swap değil/belirsiz).
    `yerel`: bakiyeden ölçülen yerel coin değişimi (olaylarda karşılık görünmeyen işlemler için, isteğe bağlı)."""
    if not isinstance(makbuz, dict) or makbuz.get("status") not in ("0x1", 1): return None
    w = cuzdan.lower(); karsi = ZINCIRLER[zincir]["karsi"]; sarili = ZINCIRLER[zincir]["sarili"]
    d = {}
    for l in makbuz.get("logs") or []:
        t = l.get("topics") or []
        if not t: continue
        adres = (l.get("address") or "").lower()
        if t[0] == TRANSFER and len(t) == 3:
            v = int(l.get("data") or "0x0", 16)
            if _adr(t[2]) == w: d[adres] = d.get(adres, 0) + v
            if _adr(t[1]) == w: d[adres] = d.get(adres, 0) - v
        elif t[0] == WITHDRAWAL and adres == sarili:             # sarılı coin açıldı: yerel coin büyük olasılıkla cüzdana gitti
            d[YEREL] = d.get(YEREL, 0) + int(l.get("data") or "0x0", 16)
    if (tx.get("from") or "").lower() == w and int(tx.get("value") or "0x0", 16) > 0:
        d[YEREL] = d.get(YEREL, 0) - int(tx["value"], 16)
    tokenler = [a for a, v in d.items() if v != 0 and a not in karsi and a != YEREL]
    karsilar = [a for a, v in d.items() if v != 0 and (a in karsi or a == YEREL)]
    if not karsilar and yerel:                                   # olaylarda karşılık yok: bakiyeden ölçülen yerel coin
        d[YEREL] = yerel; karsilar = [YEREL]
    if len(tokenler) != 1 or not karsilar: return None
    tk = tokenler[0]; k = max(karsilar, key=lambda a: abs(d[a]))
    if d[tk] > 0 and d[k] < 0: return dict(yon="buy", token=tk, miktar_raw=d[tk], karsi=k, karsi_raw=-d[k])
    if d[tk] < 0 and d[k] > 0: return dict(yon="sell", token=tk, miktar_raw=-d[tk], karsi=k, karsi_raw=d[k])
    return None


class KyberTeklif:
    URL = "https://aggregator-api.kyberswap.com/{}/api/v1/routes"

    def __init__(self, zincir, session=None, timeout=12, istemci="nexora-paper"):
        self.z, self.s, self.timeout, self.istemci = ZINCIRLER[zincir], session or requests.Session(), timeout, istemci

    def teklif(self, giris, cikis, miktar_raw):
        try:
            r = self.s.get(self.URL.format(self.z["kyber"]), params={"tokenIn": giris, "tokenOut": cikis, "amountIn": str(int(miktar_raw))},
                           headers={"x-client-id": self.istemci}, timeout=self.timeout)
            d = r.json()
        except (requests.RequestException, ValueError) as e:
            raise EvmHatasi(f"KyberSwap bağlantı hatası: {type(e).__name__}") from None
        rs = ((d or {}).get("data") or {}).get("routeSummary") if isinstance(d, dict) else None
        if r.status_code != 200 or not rs or not rs.get("amountOut"):
            raise EvmHatasi(f"KyberSwap teklif yok: {str((d or {}).get('message') if isinstance(d, dict) else r.status_code)[:80]}")
        return dict(cikis_raw=int(rs["amountOut"]), giris_usd=float(rs.get("amountInUsd") or 0), cikis_usd=float(rs.get("amountOutUsd") or 0))


def dexscreener_likidite(s, zincir, token, timeout=12):
    """DexScreener (herkese açık, anahtarsız): token'ın bu zincirdeki çiftlerinin toplam USD likiditesi. Hata: None."""
    hedef = {"bnb": "bsc", "base": "base"}[zincir]
    try:
        d = s.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=timeout).json()
        ciftler = d.get("pairs") or [] if isinstance(d, dict) else []
        return round(sum(float((p.get("liquidity") or {}).get("usd") or 0) for p in ciftler if p.get("chainId") == hedef), 2)
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return None


class GoPlus:
    URL = "https://api.gopluslabs.io/api/v1/token_security/{}"
    MAKS_VERGI = 0.05

    def __init__(self, zincir, session=None, timeout=12):
        self.z, self.s, self.timeout, self._onbellek = ZINCIRLER[zincir], session or requests.Session(), timeout, {}
        self.zincir, self.son_ham = zincir, None

    def kontrol(self, token, now=None):
        """dict(uygun, gerekceler, likidite_usd). Servis yanıt vermezse UYGUN DEĞİL sayılır (bilinmeyen = alınmaz)."""
        now = now or time.time(); token = token.lower()
        o = self._onbellek.get(token)
        if o and now - o[0] < 1800: return o[1]
        try:
            d = self.s.get(self.URL.format(self.z["goplus"]), params={"contract_addresses": token}, timeout=self.timeout).json()
            x = ((d or {}).get("result") or {}).get(token)
        except (requests.RequestException, ValueError, AttributeError):
            x = None
        if not x: return dict(uygun=False, gerekceler=["güvenlik bilgisi alınamadı"], likidite_usd=0.0)
        self.son_ham = x
        g = []
        bir = lambda k: str(x.get(k) or "0") == "1"
        if bir("is_honeypot"): g.append("honeypot (satılamaz)")
        if bir("cannot_sell_all"): g.append("tamamı satılamıyor")
        if bir("is_blacklisted"): g.append("kara liste özelliği")
        if bir("transfer_pausable"): g.append("transfer durdurulabilir")
        if bir("owner_change_balance"): g.append("sahip bakiyeleri değiştirebilir")
        for ad, k in (("alım", "buy_tax"), ("satım", "sell_tax")):
            try: v = float(x.get(k) or 0)
            except ValueError: v = 1.0
            if v > self.MAKS_VERGI: g.append(f"{ad} vergisi %{v * 100:.0f}")
        lik = 0.0
        for dex in x.get("dex") or []:
            try: lik += float(dex.get("liquidity") or 0)
            except (TypeError, ValueError, AttributeError): pass
        if lik <= 0:                                             # GoPlus likidite vermezse ikinci kaynak
            lik = dexscreener_likidite(self.s, self.zincir, token) or 0.0
        sonuc = dict(uygun=not g, gerekceler=g or ["geçti"], likidite_usd=round(lik, 2))
        self._onbellek[token] = (now, sonuc)
        return sonuc


def coz_tam(rpc, tx, makbuz, cuzdan, zincir, blok):
    """coz(); karşılık görünmeyen tek token hareketinde yerel coin bakiyesine bakıp yeniden dener."""
    r = coz(tx, makbuz, cuzdan, zincir)
    if r is not None or not isinstance(makbuz, dict) or makbuz.get("status") not in ("0x1", 1): return r
    w = cuzdan.lower(); karsi = ZINCIRLER[zincir]["karsi"]
    hareket = {(l.get("address") or "").lower() for l in makbuz.get("logs") or []
               if (l.get("topics") or [None])[0] == TRANSFER and len(l.get("topics")) == 3 and w in (_adr(l["topics"][1]), _adr(l["topics"][2]))}
    if len(hareket - karsi) != 1 or hareket & karsi: return None  # tek token, karşı varlık olayı yok: bakiye denemeye değer
    f = yerel_fark(rpc, cuzdan, blok, tx, makbuz)
    return coz(tx, makbuz, cuzdan, zincir, yerel=f) if f else None


def gezgin_islemleri(s, zincir, cuzdan, bas_blok, en_cok_sayfa=20, timeout=20, tani=None):
    """Herkese açık ücretsiz gezginlerden cüzdanın ERC-20 transferlerinin işlem karmaları: {karma: blok}.
    Sıra: Blockscout, olmazsa Routescan (Etherscan uyumlu). İkisi de yanıt vermezse None.
    `tani` (dict) verilirse her gezginin sonucu yazılır (deneme aracı için: HTTP kodu ya da hata türü)."""
    z = ZINCIRLER[zincir]
    for ad, taban, oku in (("blockscout", z.get("gezgin"), _blockscout), ("routescan", z.get("gezgin2"), _routescan)):
        if not taban: continue
        try:
            out = oku(s, taban, cuzdan.lower(), bas_blok, en_cok_sayfa, timeout)
            if tani is not None: tani[ad] = "tamam"
            return out
        except (requests.RequestException, ValueError, EvmHatasi) as e:
            if tani is not None: tani[ad] = str(e)[:120] or type(e).__name__
    return None


_BASLIK = {"User-Agent": "Mozilla/5.0 (NEXORA salt-okunur analiz)", "Accept": "application/json"}


def _blockscout(s, taban, w, bas_blok, en_cok_sayfa, timeout):
    out, params = {}, {"type": "ERC-20"}
    for _ in range(en_cok_sayfa):
        r = s.get(f"{taban}/api/v2/addresses/{w}/token-transfers", params=params, timeout=timeout, headers=_BASLIK)
        if r.status_code == 404: return out                 # gezgin adresi hiç görmemiş: geçmiş boş
        if r.status_code != 200: raise EvmHatasi(f"HTTP {r.status_code}")
        d = r.json()
        if not isinstance(d, dict): raise EvmHatasi("beklenmeyen yanıt")
        eski = False
        for x in d.get("items") or []:
            try: blok = int(x.get("block_number") or x.get("block") or 0)
            except (TypeError, ValueError): continue
            karma = x.get("transaction_hash") or x.get("tx_hash")
            if blok < bas_blok: eski = True; continue
            if karma: out.setdefault(karma, blok)
        sonraki = d.get("next_page_params")
        if eski or not sonraki: break
        params = dict({"type": "ERC-20"}, **{k: v for k, v in sonraki.items() if v is not None})
    return out


def _routescan(s, taban, w, bas_blok, en_cok_sayfa, timeout):
    out = {}
    for sayfa in range(1, en_cok_sayfa + 1):
        r = s.get(taban, params=dict(module="account", action="tokentx", address=w, startblock=bas_blok, endblock=99999999,
                                     page=sayfa, offset=1000, sort="desc"), timeout=timeout, headers=_BASLIK)
        if r.status_code != 200: raise EvmHatasi(f"HTTP {r.status_code}")
        d = r.json(); sonuc = d.get("result") if isinstance(d, dict) else None
        if not isinstance(sonuc, list):
            if "no transactions" in str(d.get("message", "") if isinstance(d, dict) else "").lower(): return out
            raise EvmHatasi(f"yanıt: {str(sonuc or d)[:80]}")
        for x in sonuc:
            try: blok = int(x.get("blockNumber") or 0)
            except (TypeError, ValueError): continue
            if blok >= bas_blok and x.get("hash"): out.setdefault(x["hash"], blok)
        if len(sonuc) < 1000: break
    return out
