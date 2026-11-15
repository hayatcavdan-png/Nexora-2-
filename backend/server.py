"""Bağımlılıksız NEXORA sunucusu (yalnızca Python stdlib).
Çalıştır: NEXORA_API_KEY=gizli123 python server.py"""
import os, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from nexora.core import Paper, CFG

paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
KEY = os.getenv("NEXORA_API_KEY", "")

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _ok(self):
        if not KEY or self.headers.get("X-API-Key", "") != KEY:
            self._send(401, {"hata": "yetkisiz"}); return False
        return True
    def do_GET(self):
        if not self._ok(): return
        if self.path == "/durum":
            self._send(200, dict(mod="PAPER", gercek_islem="KAPALI", acil_durdurma=paper.killed(), ayarlar=CFG))
        elif self.path == "/portfoy": self._send(200, paper.portfolio())
        elif self.path == "/islemler": self._send(200, paper.trades())
        else: self._send(404, {"hata": "yok"})
    def do_POST(self):
        if not self._ok(): return
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if self.path == "/acil-durdur": paper.set_kill(True); self._send(200, {"acil_durdurma": True})
        elif self.path == "/devam": paper.set_kill(False); self._send(200, {"acil_durdurma": False})
        elif self.path == "/sinyal":
            try:
                s = json.loads(raw)
                r = paper.handle_signal(s["event_id"], s["wallet"], s["token"], s["side"],
                                        float(s["price"]), float(s["liquidity_usd"]), float(s.get("signal_age_s", 0)))
                self._send(200, r)
            except (KeyError, ValueError, TypeError) as e: self._send(400, {"hata": f"geçersiz: {e}"})
        else: self._send(404, {"hata": "yok"})
    def log_message(self, *a): pass

if __name__ == "__main__":
    if not KEY: raise SystemExit("NEXORA_API_KEY ayarlanmadı")
    print("NEXORA çalışıyor: http://127.0.0.1:8000  (PAPER modu)")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
