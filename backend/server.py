"""Bağımlılıksız NEXORA sunucusu (yalnızca Python stdlib).
Çalıştır: NEXORA_API_KEY=gizli123 python server.py"""
import os, json, sqlite3
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from nexora.core import Paper, CFG
from nexora.live_tracker import latency_from_db
from nexora.rapor import build_report
from nexora import model_kapisi, panel
from nexora import gizle as _gizle
_gizle.kur()
import glob, yedek, threading, time as _time
from nexora import kesif_api
from nexora.uyelik import Uyelik, UyelikHatasi

_servis = {}
_servis_kilit = threading.Lock()

def servis(ad):
    """Ağa çıkan bileşenler yalnızca ilk kullanımda kurulur (anahtar yoksa ilgili uç nokta hata döner, sunucu çalışır)."""
    with _servis_kilit:
        if ad in _servis: return _servis[ad]
        from nexora.market import JupiterQuoter
        if "quoter" not in _servis: _servis["quoter"] = JupiterQuoter()
        if ad == "bilgi":
            from nexora.token_bilgi import TokenBilgi
            _servis[ad] = TokenBilgi(throttle=_servis["quoter"]._throttle)
        elif ad in ("helius", "decider", "dna"):
            from nexora.helius_client import HeliusClient
            if "helius" not in _servis: _servis["helius"] = HeliusClient(max_retries=2)
            if ad == "decider":
                from nexora.token_safety import TokenSafety
                from nexora.decision import Decider
                _servis[ad] = Decider(paper, _servis["quoter"], TokenSafety(_servis["helius"]))
            elif ad == "dna":
                import cuzdan_analiz
                from nexora.wallet_analysis import analyze, verdict
                fiyat = {"ts": 0, "v": None}
                def analiz_et(adres):
                    if fiyat["v"] is None or _time.time() - fiyat["ts"] > 600:
                        fiyat.update(v=cuzdan_analiz.sol_price(_servis["quoter"]), ts=_time.time())
                    m = analyze(cuzdan_analiz.fetch(_servis["helius"], adres), adres, fiyat["v"])
                    karar, why = verdict(m)
                    return m, karar, "; ".join(why)
                _servis[ad] = kesif_api.DnaServisi(os.getenv("DNA_DB", "nexora_dna.db"), analiz_et)
        return _servis[ad]

paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
uyelik = Uyelik(os.getenv("UYELIK_DB", "nexora_uyelik.db"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "20"))      # uygulama kâr payı (sanal gösterim)
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

def _yz_ozet():
    """Uygulamadaki Yapay Zekâ Çekirdeği kartı için: etiketlenen sinyal sayısı ve hedef."""
    try:
        from nexora.etiket import ozet
        o = ozet(os.getenv("ETIKET_DB", "nexora_etiket.db"))
        return None if o is None else {k: o[k] for k in ("etiketli", "hedef", "ilerleme_pct", "izleniyor")}
    except Exception:
        return None


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

    def _dna(self, adres, yenile):
        try:
            self._send(200, servis("dna").getir(adres, yenile))
        except ValueError as e: self._send(400, {"hata": str(e)})
        except PermissionError as e: self._send(429, {"hata": str(e)})
        except Exception as e: self._send(502, {"hata": f"analiz yapılamadı: {type(e).__name__}"})

    def _uye(self):
        u = uyelik.uye((self.headers.get("X-Oturum") or "").strip())
        if not u: self._send(401, {"hata": "oturum yok veya süresi doldu"})
        return u

    def _uye_islem(self, yol, raw):
        try: d = json.loads(raw or b"{}")
        except ValueError: d = {}
        try:
            if yol == "/uye/kayit": self._send(200, {"oturum": uyelik.kayit(d.get("eposta"), d.get("parola"), d.get("davet"))}); return
            if yol == "/uye/giris": self._send(200, {"oturum": uyelik.giris(d.get("eposta"), d.get("parola"))}); return
            if yol == "/uye/cikis": uyelik.cikis((self.headers.get("X-Oturum") or "").strip()); self._send(200, {"ok": True}); return
            u = self._uye()
            if not u: return
            if yol == "/uye/portfoy":
                uyelik.portfoy_baslat(u["id"], d.get("baslangic"), paper.equity())
                self._send(200, uyelik.uye_bakiye(u["id"], paper.equity(), KOMISYON_PCT)); return
            if yol == "/uye/baglanti":
                if d.get("sil"): uyelik.baglanti_sil(u["id"], d.get("tur"))
                else: uyelik.baglanti_kaydet(u["id"], d.get("tur"), d.get("adres"))
                self._send(200, uyelik.profil(u))
        except UyelikHatasi as e: self._send(400, {"hata": str(e)})
        except PermissionError as e: self._send(429, {"hata": str(e)})

    def do_GET(self):
        if not self._ok(): return
        parts = urlsplit(self.path)
        if parts.path == "/yedek/son": self._yedek_gonder(); return
        if parts.path == "/hazirlik":
            from nexora import hazirlik as _hz
            from nexora.etiket import ozet as _et
            self._send(200, _hz.hazirlik(os.getenv("NEXORA_DB", "nexora_paper.db"), _et(os.getenv("ETIKET_DB", "nexora_etiket.db")))); return
        if parts.path == "/uye/ben":
            u = self._uye()
            if u: self._send(200, uyelik.profil(u))
            return
        if parts.path == "/uye/bakiye":
            if self._uye():
                u = uyelik.uye((self.headers.get("X-Oturum") or "").strip())
                self._send(200, uyelik.uye_bakiye(u["id"], paper.equity(), KOMISYON_PCT))
            return
        if parts.path == "/radar":
            from nexora.token_bilgi import toplu
            self._send(200, kesif_api.radar(os.getenv("TRACKER_DB", "nexora_tracker.db"), lambda ms: toplu(servis("bilgi"), ms)))
            return
        if parts.path == "/cuzdan-dna":
            adres = (parse_qs(parts.query).get("adres") or [""])[0]
            self._dna(adres, False); return
        if parts.path == "/karar-izi":
            ev = (parse_qs(parts.query).get("olay") or [""])[0]
            d = paper.karar_izi(ev) if ev else None
            self._send(200 if d else 404, d or {"hata": "kayıt yok"}); return
        if parts.path == "/olaylar":
            try: son = float(parse_qs(parts.query).get("son", ["0"])[0])
            except ValueError: son = 0.0
            self._send(200, panel.olaylar(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db"), son,
                                          kesif_path="kesif_son.json"))
            return
        if self.path == "/durum":
            self._send(200, dict(mod="PAPER", gercek_islem="KAPALI", acil_durdurma=paper.killed(), ayarlar=paper.ayarlar()["gecerli"],
                                 takip_nabiz=paper.son_nabiz(), model_filtre=model_kapisi.ModelKapisi().durum(), yz=_yz_ozet()))
        elif self.path == "/portfoy": self._send(200, paper.portfolio())
        elif self.path == "/islemler": self._send(200, paper.trades())
        elif self.path == "/takip": self._send(200, takip_ozeti())
        elif self.path == "/gecmis": self._send(200, panel.gecmis(os.getenv("NEXORA_DB", "nexora_paper.db")))
        elif self.path == "/cuzdanlar":
            self._send(200, panel.cuzdanlar(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        elif self.path == "/asamalar": self._send(200, panel.asamalar())
        elif self.path == "/defter":
            import portfoy_denetim
            d = portfoy_denetim.denetle(os.getenv("NEXORA_DB", "nexora_paper.db"))
            self._send(200, {k: d.get(k) for k in ("hazir", "nakit", "nakit_beklenen", "nakit_farki", "pozisyon_degeri", "toplam",
                                                   "toplam_farki", "gerceklesen", "alim_ucreti", "gerceklesmemis", "en_buyuk",
                                                   "supheli", "supheli_kz")})
        elif self.path == "/saglik":
            self._send(200, panel.saglik(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        elif self.path == "/ayarlar": self._send(200, paper.ayarlar())
        elif self.path == "/model-filtre":
            self._send(200, dict(model_kapisi.ModelKapisi().durum(),
                                 golge=model_kapisi.golge_rapor(os.getenv("ETIKET_DB", "nexora_etiket.db"))))
        elif self.path == "/rapor":
            self._send(200, build_report(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db")))
        else: self._send(404, {"hata": "yok"})
    def do_POST(self):
        if not self._ok(): return
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if self.path.startswith("/uye/"): self._uye_islem(self.path, raw); return
        if self.path == "/acil-durdur": paper.set_kill(True); self._send(200, {"acil_durdurma": True})
        elif self.path == "/devam": paper.set_kill(False); self._send(200, {"acil_durdurma": False})
        elif self.path == "/cuzdan-dna":
            try: d = json.loads(raw or b"{}")
            except ValueError: d = {}
            self._dna(d.get("adres", ""), bool(d.get("yenile")))
        elif self.path == "/manuel":
            try:
                d = json.loads(raw or b"{}")
                self._send(200, kesif_api.manuel_islem(servis("decider"), d.get("token", ""), d.get("yon", ""), d.get("usd")))
            except ValueError as e: self._send(400, {"hata": str(e)})
            except Exception as e: self._send(502, {"hata": f"işlem yapılamadı: {type(e).__name__}"})
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
        elif self.path == "/model-filtre":                 # N20: uygulamadan YALNIZCA kapatılabilir (tek dokunuş geri alma)
            try: d = json.loads(raw or b"{}")
            except ValueError: d = {}
            if d.get("acik") is False:
                model_kapisi.filtre_kapat(kaynak="uygulama"); self._send(200, model_kapisi.ModelKapisi().durum())
            else:
                self._send(403, {"hata": "model filtresi yalnızca sunucuda açılır (yz_filtre.py ac)"})
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
