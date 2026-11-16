"""Platform 2 (borsa) PAPER motoru: cüzdan sinyali dört borsadan birinde listeli bir token'daysa, işlem o borsanın
GERÇEK en iyi alış/satış fiyatıyla ayrı bir sanal portföyde (nexora_borsa.db) yapılır. Platform 1'den tamamen ayrıdır.

Fiyat: borsanın herkese açık 'en iyi teklif' ucu (anahtar yok). Alımda satış tarafı (ask), satışta alış tarafı (bid) kullanılır.
Likidite yerine çiftin 24 saatlik hacmi verilir (risk kuralları ve kayma modeli aynı). Gerçek emir YOK: borsa API anahtarı
kullanılmaz; gerçek emir ayrıca açık onay ister (N12)."""
import queue, threading, time

import requests

from nexora.borsa_liste import en_iyi_borsa


class FiyatHatasi(RuntimeError):
    pass


def _f(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


class BorsaFiyat:
    """Borsanın en iyi alış/satış fiyatı: (bid, ask)."""
    def __init__(self, session=None, timeout=8):
        self.s, self.timeout = session or requests.Session(), timeout

    def teklif(self, borsa, taban, karsi):
        try:
            if borsa in ("Binance", "MEXC"):
                url = "https://api.binance.com/api/v3/ticker/bookTicker" if borsa == "Binance" else "https://api.mexc.com/api/v3/ticker/bookTicker"
                d = self.s.get(url, params={"symbol": taban + karsi}, timeout=self.timeout).json()
                bid, ask = _f(d.get("bidPrice")), _f(d.get("askPrice"))
            elif borsa == "OKX":
                d = self.s.get("https://www.okx.com/api/v5/market/ticker", params={"instId": f"{taban}-{karsi}"}, timeout=self.timeout).json()
                x = (d.get("data") or [{}])[0]
                bid, ask = _f(x.get("bidPx")), _f(x.get("askPx"))
            elif borsa == "KuCoin":
                d = self.s.get("https://api.kucoin.com/api/v1/market/orderbook/level1", params={"symbol": f"{taban}-{karsi}"},
                               timeout=self.timeout).json()
                x = d.get("data") or {}
                bid, ask = _f(x.get("bestBid")), _f(x.get("bestAsk"))
            else:
                raise FiyatHatasi(f"bilinmeyen borsa {borsa}")
        except (requests.RequestException, ValueError, AttributeError, IndexError) as e:
            raise FiyatHatasi(f"{borsa} fiyatı alınamadı: {type(e).__name__}") from None
        if not bid or not ask or ask < bid: raise FiyatHatasi(f"{borsa} {taban}/{karsi}: geçersiz teklif")
        return bid, ask


class BorsaMotoru:
    """Sinyali alır; token listedeyse kuyruğa koyar ve arka planda karar verir (takip akışını bekletmez)."""
    MAKS_MAKAS_PCT = 3.0                          # alış-satış farkı bundan büyükse alınmaz (sığ defter)

    def __init__(self, paper, liste, fiyat=None, maxsize=200):
        self.paper, self.liste, self.fiyat = paper, liste, fiyat or BorsaFiyat()
        self.q = queue.Queue(maxsize=maxsize)
        self._t = None

    def sinyal(self, event_id, wallet, token, side, yas_sn):
        if token not in self.liste: return False
        try:
            self.q.put_nowait((event_id, wallet, token, side, yas_sn, time.time()))
            return True
        except queue.Full:
            return False

    def karar(self, event_id, wallet, token, side, yas_sn):
        t = self.liste.get(token)
        if not t: return None
        b = en_iyi_borsa(t)
        c = t["borsalar"][b]
        ev = f"borsa:{event_id}"
        try:
            bid, ask = self.fiyat.teklif(b, c["taban"], c["karsi"])
        except FiyatHatasi as e:
            return self.paper.reject(ev, wallet, token, side, str(e)) | dict(borsa=b)
        makas = (ask - bid) / ask * 100
        if side == "buy" and makas > self.MAKS_MAKAS_PCT:
            return self.paper.reject(ev, wallet, token, side, f"borsa makası geniş (%{makas:.1f}, {b})") | dict(borsa=b)
        fiyat = ask if side == "buy" else bid
        r = self.paper.handle_signal(ev, wallet, token, side, fiyat, float(c.get("hacim_usd") or 0), yas_sn)
        return dict(r, borsa=b, cift=f"{c['taban']}/{c['karsi']}", fiyat=fiyat, makas_pct=round(makas, 3))

    def _calis(self):
        while True:
            event_id, wallet, token, side, yas, t0 = self.q.get()
            try:
                self.karar(event_id, wallet, token, side, yas + (time.time() - t0))
            except Exception:
                pass                                  # platform 2 hatası platform 1'i asla etkilemez

    def baslat(self):
        if self._t is None:
            self._t = threading.Thread(target=self._calis, daemon=True); self._t.start()
        return self

    def degerle(self):
        """Açık borsa pozisyonlarını güncel satış (bid) fiyatıyla değerler."""
        for p in self.paper.portfolio()["positions"]:
            t = self.liste.get(p["token"])
            if not t: continue
            b = en_iyi_borsa(t); c = t["borsalar"][b]
            try:
                bid, _ = self.fiyat.teklif(b, c["taban"], c["karsi"])
                self.paper.mark_price(p["token"], bid)
            except (FiyatHatasi, AttributeError):
                pass
