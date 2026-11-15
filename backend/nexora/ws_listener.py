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

    def run_once(self, stop=None):
        ws = self.connect(self.url, timeout=self.ping_every)
        try:
            pending, subs = {}, {}
            for i, w in enumerate(self.wallets, 1):
                pending[i] = w
                ws.send_text(json.dumps({"jsonrpc": "2.0", "id": i, "method": "logsSubscribe",
                    "params": [{"mentions": [w]}, {"commitment": self.commitment}]}))
            self.connected = True
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
                p = msg.get("params") or {}
                w = subs.get(p.get("subscription"))
                v = ((p.get("result") or {}).get("value")) or {}
                sig = v.get("signature")
                if not w or not isinstance(sig, str) or v.get("err") is not None:
                    continue
                try:
                    self.on_signature(w, sig)
                except Exception as e:            # tek işlem hatası dinleyiciyi durdurmaz
                    self.log(f"İşlem hatası {sig[:8]}…: {type(e).__name__}")
        finally:
            self.connected = False
            ws.close()

    def run_forever(self, stop):
        delay = 1
        while not stop.is_set():
            start = time.time()
            try:
                self.run_once(stop)
            except (WSClosed, OSError, ValueError) as e:
                self.log(f"WebSocket koptu ({type(e).__name__}: {str(e)[:80]}), {delay} sn sonra yeniden bağlanılacak")
            if time.time() - start > 60: delay = 1
            stop.wait(delay)
            delay = min(delay * 2, 60)
