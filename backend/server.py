"""Bağımlılıksız NEXORA sunucusu (yalnızca Python stdlib).
Çalıştır: NEXORA_API_KEY=gizli123 python server.py"""
import os, json, sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from nexora.core import Paper, CFG
from nexora.live_tracker import latency_from_db
from nexora.rapor import build_report
from nexora import panel

paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
KEY = os.getenv("NEXORA_API_KEY", "").strip()   # baştaki/sondaki boşluk anahtarı bozmasın

def _read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]

def takip_ozeti(limit=50):
    """Takip veritabanını SALT OKUNUR açar: cüzdan durumu, son sinyaller, gecikme."""
    path = os.getenv("TRACKER_DB", "nexora_tracker.db")
    if not os.path.exists(path): return dict(cuzdanlar=[], sinyaller=[], gecikme={})
    active = set(_read_list("wallets.txt")) - set(_read_list("kara_liste.txt"))
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    try:
        cuz = [dict(r) for r in c.execute("SELECT wallet, errors, quarantined, last_error FROM tracker_wallets")
               if not active or r["wallet"] in active]
        sig = [dict(r) for r in c.execute("SELECT * FROM tracker_signals ORDER BY id DESC LIMIT ?", (limit,))]
        for r in sig:
            r.pop("token_delta", None); r.pop("quote", None)
            r.setdefault("source", "poll")
        return dict(cuzdanlar=cuz, sinyaller=sig, gecikme=latency_from_db(c))
    finally:
        c.close()

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _ok(self):
        if not KEY or (self.headers.get("X-API-Key") or "").strip() != KEY:
            self._send(401, {"hata": "yetkisiz"}); return False
        return True
    def do_GET(self):
        if not self._ok(): return
        if self.path == "/durum":
            self._send(200, dict(mod="PAPER", gercek_islem="KAPALI", acil_durdurma=paper.killed(), ayarlar=CFG))
        elif self.path == "/portfoy": self._send(200, paper.portfolio())
        elif self.path == "/islemler": self._send(200, paper.trades())
        elif self.path == "/takip": self._send(200, takip_ozeti())
        elif self.path == "/gecmis": self._send(200, panel.gecmis(os.getenv("NEXORA_DB", "nexora_paper.db")))
        elif self.path == "/cuzdanlar":
            self._send(200, panel.cuzdanlar(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        elif self.path == "/asamalar": self._send(200, panel.asamalar())
        elif self.path == "/rapor":
            self._send(200, build_report(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
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
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", 8000), H)
    except OSError:
        raise SystemExit("8000 portu kullanımda: sunucu zaten başka bir oturumda çalışıyor olabilir.")
    print("NEXORA çalışıyor: http://127.0.0.1:8000  (PAPER modu)")
    srv.serve_forever()
