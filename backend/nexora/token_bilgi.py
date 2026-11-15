"""Token bilgisi ölçümü (yalnızca ölçüm, karar kuralı DEĞİL): kopyalanan ya da gölgeye alınan her alımda
token'ın yaşı, likiditesi, organik skoru ve sahip yoğunlaşması Jupiter Tokens API v2'den alınıp kaydedilir.
Sonra bu özelliklere göre hangi grupların kazandırdığı ölçülür (rapor: token_filtre.py).

GET https://api.jup.ag/tokens/v2/search?query=<mint>   (x-api-key ile)
GET https://lite-api.jup.ag/tokens/v2/search?query=<mint>   (anahtarsız; kapanırsa hata kaydedilir)
İstekler, alım kararını geciktirmemek için kararın ARDINDAN arka planda ve Jupiter hız sınırı paylaşılarak yapılır."""
import datetime, os, queue, threading, time
import requests

URL_KEY = "https://api.jup.ag/tokens/v2/search"
URL_LITE = "https://lite-api.jup.ag/tokens/v2/search"


class BilgiHatasi(RuntimeError):
    pass


def _ts(v):
    """ISO 8601 ('2026-11-15T20:03:11.123Z') ya da epoch (sn/ms) -> epoch sn."""
    if v is None or isinstance(v, bool): return None
    if isinstance(v, (int, float)): return v / 1000 if v > 1e11 else float(v)
    if isinstance(v, str):
        s = v.strip()
        if s.replace(".", "", 1).isdigit(): return _ts(float(s))
        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def parse(item, now):
    """Jupiter MintInformation -> kaydedilecek alanlar. Yaş: ilk havuz zamanı, yoksa token oluşturulma zamanı."""
    audit = item.get("audit") or {}
    pool = item.get("firstPool") or {}
    created, pooled = _ts(item.get("createdAt")), _ts(pool.get("createdAt"))
    basis = pooled or created
    return dict(
        yas_sn=None if basis is None else max(0.0, now - basis),
        likidite=_num(item.get("liquidity")), mcap=_num(item.get("mcap")),
        sahip=_num(item.get("holderCount")),
        organik=_num(item.get("organicScore")), organik_etiket=item.get("organicScoreLabel"),
        top_pct=_num(audit.get("topHoldersPercentage")), dev_pct=_num(audit.get("devBalancePercentage")),
        sus=1 if "isSus" in audit else 0, launchpad=item.get("launchpad"))


class TokenBilgi:
    def __init__(self, api_key=None, session=None, timeout=8, throttle=None):
        self.api_key = api_key if api_key is not None else os.getenv("JUPITER_API_KEY", "")
        self.session = session or requests.Session()
        self.timeout, self.throttle = timeout, throttle

    def fetch(self, mint, now=None):
        if self.throttle: self.throttle()
        url, headers = (URL_KEY, {"x-api-key": self.api_key}) if self.api_key else (URL_LITE, {})
        try:
            r = self.session.get(url, params={"query": mint}, headers=headers, timeout=self.timeout)
        except requests.RequestException:
            raise BilgiHatasi("bağlantı hatası") from None
        if r.status_code != 200: raise BilgiHatasi(f"HTTP {r.status_code}")
        try:
            d = r.json()
        except ValueError:
            raise BilgiHatasi("yanıt okunamadı") from None
        if not isinstance(d, list): raise BilgiHatasi("yanıt geçersiz")
        item = next((x for x in d if isinstance(x, dict) and x.get("id") == mint), None)
        if item is None: raise BilgiHatasi("token bulunamadı")
        return parse(item, now if now is not None else time.time())


class Toplayici:
    """Arka plan kuyruğu: enqueue() hemen döner; tek işçi iş parçacığı bilgiyi alıp Paper'a yazar."""
    def __init__(self, fetcher, paper, maxsize=200):
        self.fetcher, self.paper = fetcher, paper
        self.q = queue.Queue(maxsize=maxsize)
        self._thread = None

    def enqueue(self, event_id, token):
        try:
            self.q.put_nowait((event_id, token, time.time()))
        except queue.Full:
            pass                                   # ölçüm kaybı kabul edilir; işlem akışı asla beklemez

    def isle(self, item):
        event_id, token, ts = item
        try:
            d = self.fetcher.fetch(token, now=ts)
            self.paper.token_bilgi_kaydet(event_id, token, ts, d)
        except BilgiHatasi as e:
            self.paper.token_bilgi_kaydet(event_id, token, ts, None, hata=str(e))

    def baslat(self):
        def run():
            while True:
                self.isle(self.q.get())
        self._thread = threading.Thread(target=run, daemon=True); self._thread.start()
        return self
