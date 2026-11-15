"""Bağımlılıksız NEXORA sunucusu (yalnızca Python stdlib).
Çalıştır: NEXORA_API_KEY=gizli123 python server.py"""
import os, json, sqlite3
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from nexora.core import Paper, CFG
from nexora.live_tracker import latency_from_db
from nexora.rapor import build_report
from nexora import panel
from nexora import gizle as _gizle
_gizle.kur()
import glob, yedek

paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
KEY = os.getenv("NEXORA_API_KEY", "").strip()
# Telefonda yalnızca bu cihazdan erişilir. Sunucuda (N13) özel ağ adresi verilir: NEXORA_HOST=100.x.y.z
HOST = os.getenv("NEXORA_HOST", "127.0.0.1")
PORT = int(os.getenv("NEXORA_PORT", "8000"))   # baştaki/sondaki boşluk anahtarı bozmasın

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
    def _yedek_gonder(self):
        dosyalar = sorted(glob.glob(os.path.join("yedekler", "nexora_*.tar.gz")))
        if not dosyalar: self._send(404, {"hata": "yedek yok"}); return
        yol = dosyalar[-1]
        b = open(yol, "rb").read()
        self.send_response(200); self.send_header("Content-Type", "application/gzip")
        self.send_header("X-Yedek-Ad", os.path.basename(yol)); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if not self._ok(): return
        parts = urlsplit(self.path)
        if parts.path == "/yedek/son": self._yedek_gonder(); return
        if parts.path == "/karar-izi":
            ev = (parse_qs(parts.query).get("olay") or [""])[0]
            d = paper.karar_izi(ev) if ev else None
            self._send(200 if d else 404, d or {"hata": "kayıt yok"}); return
        if parts.path == "/olaylar":
            try: son = float(parse_qs(parts.query).get("son", ["0"])[0])
            except ValueError: son = 0.0
            self._send(200, panel.olaylar(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db"), son))
            return
        if self.path == "/durum":
            self._send(200, dict(mod="PAPER", gercek_islem="KAPALI", acil_durdurma=paper.killed(), ayarlar=paper.ayarlar()["gecerli"],
                                 takip_nabiz=paper.son_nabiz()))
        elif self.path == "/portfoy": self._send(200, paper.portfolio())
        elif self.path == "/islemler": self._send(200, paper.trades())
        elif self.path == "/takip": self._send(200, takip_ozeti())
        elif self.path == "/gecmis": self._send(200, panel.gecmis(os.getenv("NEXORA_DB", "nexora_paper.db")))
        elif self.path == "/cuzdanlar":
            self._send(200, panel.cuzdanlar(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        elif self.path == "/asamalar": self._send(200, panel.asamalar())
        elif self.path == "/saglik":
            self._send(200, panel.saglik(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        elif self.path == "/ayarlar": self._send(200, paper.ayarlar())
        elif self.path == "/rapor":
            self._send(200, build_report(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        else: self._send(404, {"hata": "yok"})
    def do_POST(self):
        if not self._ok(): return
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if self.path == "/acil-durdur": paper.set_kill(True); self._send(200, {"acil_durdurma": True})
        elif self.path == "/devam": paper.set_kill(False); self._send(200, {"acil_durdurma": False})
        elif self.path == "/yedek":
            try:
                y = yedek.yedekle()
                self._send(200, {"ad": os.path.basename(y), "boyut": os.path.getsize(y)})
            except OSError as e:
                self._send(500, {"hata": f"yedek alınamadı: {e}"})
        elif self.path == "/ayarlar":
            try:
                self._send(200, paper.ayar_degistir(json.loads(raw or b"{}")))
            except ValueError as e:
                self._send(400, {"hata": str(e)})
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
    if HOST not in ("127.0.0.1", "localhost") and len(KEY) < 16:
        raise SystemExit("Dışarıya açık adreste en az 16 karakterlik NEXORA_API_KEY gerekir.")
    try:
        srv = ThreadingHTTPServer((HOST, PORT), H)
    except OSError:
        raise SystemExit(f"{PORT} portu kullanımda: sunucu zaten başka bir oturumda çalışıyor olabilir.")
    print(f"NEXORA çalışıyor: http://{HOST}:{PORT}  (PAPER modu)")
    srv.serve_forever()
