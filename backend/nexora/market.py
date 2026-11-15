"""Jupiter Swap API v2 ile salt okunur fiyat teklifi (işlem oluşturulmaz: taker gönderilmez).
GET https://api.jup.ag/swap/v2/order  — anahtar isteğe bağlı (x-api-key).
Anahtarsız: 0.5 istek/sn, ücretsiz anahtarla 1 istek/sn. Hız sınırı burada uygulanır."""
import os, threading, time
import requests

ORDER_URL = "https://api.jup.ag/swap/v2/order"

class QuoteError(RuntimeError):
    pass

class JupiterQuoter:
    def __init__(self, api_key=None, session=None, min_interval=None, timeout=8,
                 clock=time.monotonic, sleep=time.sleep):
        self.api_key = api_key if api_key is not None else os.getenv("JUPITER_API_KEY", "")
        self.session = session or requests.Session()
        self.min_interval = min_interval if min_interval is not None else (1.05 if self.api_key else 2.1)
        self.timeout, self.clock, self.sleep = timeout, clock, sleep
        self._lock, self._last = threading.Lock(), None

    def _throttle(self):
        with self._lock:
            now = self.clock()
            if self._last is not None:
                wait = self.min_interval - (now - self._last)
                if wait > 0: self.sleep(wait); now = self.clock()
            self._last = now

    def quote(self, input_mint, output_mint, amount_raw):
        if isinstance(amount_raw, bool) or not isinstance(amount_raw, int) or amount_raw <= 0:
            raise QuoteError("miktar geçersiz")
        self._throttle()
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        params = {"inputMint": input_mint, "outputMint": output_mint, "amount": str(amount_raw), "swapMode": "ExactIn"}
        try:
            r = self.session.get(ORDER_URL, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException:
            raise QuoteError("Jupiter bağlantı hatası") from None
        if r.status_code == 429: raise QuoteError("Jupiter hız sınırı (429)")
        if r.status_code == 400: raise QuoteError("rota yok")
        if r.status_code != 200: raise QuoteError(f"Jupiter HTTP {r.status_code}")
        try:
            d = r.json()
        except ValueError:
            raise QuoteError("Jupiter yanıtı okunamadı") from None
        if not isinstance(d, dict): raise QuoteError("Jupiter yanıtı geçersiz")
        out, inn = d.get("outAmount"), d.get("inAmount")
        if not (isinstance(out, str) and out.isdigit() and int(out) > 0): raise QuoteError("rota yok")
        if not (isinstance(inn, str) and inn.isdigit()) or int(inn) != amount_raw:
            raise QuoteError("teklif miktarı tutarsız")
        if d.get("inputMint", input_mint) != input_mint or d.get("outputMint", output_mint) != output_mint:
            raise QuoteError("teklif token'ları tutarsız")
        # Jupiter USD fiyatını bilmediği token'larda (yeni token'lar) inUsdValue/outUsdValue 0 olur ve
        # priceImpact yapay olarak -100 döner. O durumda etki BİLİNMİYOR sayılır (None); karar, token
        # miktarlarına dayanan al-sat kaybı ölçüsüne bırakılır.
        def usd(k):
            v = d.get(k)
            return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        in_usd, out_usd = usd("inUsdValue"), usd("outUsdValue")
        impact = d.get("priceImpact")
        if isinstance(impact, bool) or not isinstance(impact, (int, float)):
            pct = d.get("priceImpactPct")                       # eski alan: ondalık oran
            try: impact = float(pct) * 100
            except (TypeError, ValueError): impact = None
        if (in_usd is not None and in_usd <= 0) or (out_usd is not None and out_usd <= 0):
            impact = None
        return dict(in_amount=int(inn), out_amount=int(out),
                    price_impact_pct=None if impact is None else abs(float(impact)),
                    in_usd=in_usd, out_usd=out_usd, router=d.get("router"), fee_bps=d.get("feeBps"))
