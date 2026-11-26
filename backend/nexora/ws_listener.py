"""Solana logsSubscribe ile cüzdan başına anlık imza bildirimi.
Bağlantı koparsa üstel bekleme ile yeniden bağlanır ve aboneliklerini yeniler.
Kaçan işlemleri yoklama (backfill) tamamlar; bu modül yalnızca hızı artırır."""
import json, socket, time
from nexora.ws_client import WSClient, WSClosed

class WSListener:
    def __init__(self, url, wallets, on_signature, connect=WSClient.connect,
                 log=print, ping_every=30, commitment="confirmed"):
        self.url, self.wallets, self.on_signature = url, list(wallets), on_signature
        self.connect, self.log, self.ping_every, self.commitment = connect, log, ping_every, commitment
        self.connected = False
        self.kopma = 0                 # yeniden bağlanma sayısı (sağlık ölçümü)
        self.son_mesaj = None          # son bildirim zamanı
        self.kopuk_bas = None          # bağlantının koptuğu (ya da hiç kurulamadığı) an; bağlanınca None
        self.son_hata = None           # son bağlantı hatası metni (ör. 'HTTP 429')

    def run_once(self, stop=None):
        ws = self.connect(self.url, timeout=self.ping_every)
        try:
            pending, subs = {}, {}
            for i, w in enumerate(self.wallets, 1):
                pending[i] = w
                ws.send_text(json.dumps({"jsonrpc": "2.0", "id": i, "method": "logsSubscribe",
                    "params": [{"mentions": [w]}, {"commitment": self.commitment}]}))
            self.connected = True; self.kopuk_bas = None
            while not (stop and stop.is_set()):
                try:
                    raw = ws.recv()
                except (socket.timeout, TimeoutError):
                    ws.ping(); continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict): continue
                if msg.get("id") in pending:
                    w = pending.pop(msg["id"])
                    if isinstance(msg.get("result"), int):
                        subs[msg["result"]] = w
                    else:
                        self.log(f"Abonelik reddedildi: {w[:4]}…{w[-4:]}")
                    continue
                if msg.get("method") != "logsNotification": continue
                self.son_mesaj = time.time()
                p = msg.get("params") or {}
                w = subs.get(p.get("subscription"))
                v = ((p.get("result") or {}).get("value")) or {}
                sig = v.get("signature")
                if not w or not isinstance(sig, str) or v.get("err") is not None:
                    continue
                try:
                    self.on_signature(w, sig)
                except Exception as e:            # tek işlem hatası dinleyiciyi durdurmaz
                    self.log(f"İşlem hatası {sig[:8]}…: {type(e).__name__}: {str(e)[:160]}")
        finally:
            self.connected = False
            ws.close()

    def run_forever(self, stop, kota_ust=900):
        """Kopunca üstel bekleme (en fazla 60 sn). Sağlayıcı 429 (kota/hız sınırı) dönerse ısrar etmemek için
        bekleme kota_ust'e (15 dk) kadar uzar; kredi bitince her dakika deneyip sınırı uzatmayız, kota açılınca toparlanırız."""
        delay = 1
        while not stop.is_set():
            start = time.time(); kota = False
            try:
                self.run_once(stop)
            except (WSClosed, OSError, ValueError) as e:
                self.kopma += 1
                if self.kopuk_bas is None: self.kopuk_bas = time.time()
                self.son_hata = f"{type(e).__name__}: {str(e)[:120]}"
                kota = "429" in str(e)
                if kota: delay = max(delay, 60)
                self.log(f"WebSocket koptu ({type(e).__name__}: {str(e)[:80]}), {delay} sn sonra yeniden bağlanılacak"
                         + (" (sağlayıcı kota/hız sınırı)" if kota else ""))
            if time.time() - start > 60: delay = 1
            stop.wait(delay)
            delay = min(delay * 2, kota_ust if kota else 60)
