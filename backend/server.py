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
_kasa = []
def kasa():
    """Borsa anahtarları için şifreleme kasası (ilk kullanımda yüklenir; anahtar dosyası KASA_ANAHTAR)."""
    if not _kasa:
        from nexora.kasa import Kasa
        _kasa.append(Kasa())
    return _kasa[0]
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
    def _send(self, code, obj, *, private=False):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        if private: self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
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

    # ---- Rol ayrımı. kurucu: API anahtarı ya da rolü 'kurucu' olan üye oturumu. uye: herhangi bir geçerli üye oturumu.
    # Üye yalnızca UYE_GET listesindeki okumaları ve kendi /uye/* işlemlerini yapabilir; geri kalan her şey kurucuya aittir.
    # Yetki SUNUCUDA denetlenir: uygulama kurcalansa bile üye kurucu işlemi yapamaz.
    UYE_GET = {"/durum", "/portfoy", "/islemler", "/gecmis", "/olaylar", "/radar", "/uye/ben", "/uye/borsa", "/uye/bakiye"}
    ACIK_POST = {"/uye/kayit", "/uye/giris", "/uye/sifre-unut", "/uye/sifre-sifirla", "/uye/cikis"}

    def _yetki(self):
        if KEY and (self.headers.get("X-API-Key") or "").strip() == KEY: return "kurucu"
        u = uyelik.uye((self.headers.get("X-Oturum") or "").strip())
        if not u: return None
        return "kurucu" if u.get("rol") == "kurucu" else "uye"

    def _izin(self, yol, post, *, private=False):
        """Bu isteğe izin var mı? Yoksa yanıtı gönderir ve (False, None) döner."""
        if post and yol in self.ACIK_POST: return True, self._yetki()
        y = self._yetki()
        if y is None: self._send(401, {"hata": "yetkisiz"}, private=private); return False, None
        if y == "kurucu" or (post and yol.startswith("/uye/")) or (not post and yol in self.UYE_GET): return True, y
        self._send(403, {"hata": "bu işlem yalnızca kurucu içindir"}, private=private); return False, y

    @staticmethod
    def _cuzdansiz(o):
        """Üyeye giden veride kaynak cüzdan adresleri gizlenir (takip listesi kurucunundur)."""
        if isinstance(o, list): return [H._cuzdansiz(x) for x in o]
        if isinstance(o, dict): return {k: ("gizli" if k == "wallet" and v else H._cuzdansiz(v)) for k, v in o.items()}
        return o

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
            if yol == "/uye/sifre-unut":                    # şifre sıfırlama kodu e-postayla gider; hesap var/yok aynı yanıt
                from nexora import eposta as _ep
                def _kod_yolla(alici, kod):
                    try:
                        _ep.gonder(alici, "NEXORA şifre sıfırlama kodu",
                                   f"Şifre sıfırlama kodunuz: {kod}\n\n30 dakika geçerlidir. Bu isteği siz yapmadıysanız bu e-postayı yok sayın.")
                    except (_ep.EpostaHatasi, OSError, RuntimeError) as e:
                        print(f"[nexora] sıfırlama e-postası gönderilemedi: {type(e).__name__}", flush=True)   # kod ve adres loglanmaz
                uyelik.sifre_sifirla_iste(d.get("eposta"), _kod_yolla)
                self._send(200, {"ok": True}); return
            if yol == "/uye/sifre-sifirla":
                self._send(200, {"oturum": uyelik.sifre_sifirla(d.get("eposta"), d.get("kod"), d.get("yeni"))}); return
            if yol == "/uye/cikis": uyelik.cikis((self.headers.get("X-Oturum") or "").strip()); self._send(200, {"ok": True}); return
            u = self._uye()
            if not u: return
            if yol == "/uye/parola":                         # N35: parola değiştir; tüm oturumlar kapanır, bu cihaza yeni oturum verilir
                tok = uyelik.parola_degistir(u["id"], d.get("eski"), d.get("yeni"))
                self._send(200, {"oturum": tok}); return
            if yol == "/uye/oturumlari-kapat":               # N35: tüm oturumları kapat (kayıp cihaz için)
                uyelik.tum_oturumlari_kapat(u["id"]); self._send(200, {"ok": True}); return
            if yol == "/uye/portfoy":
                uyelik.portfoy_baslat(u["id"], d.get("baslangic"), paper.equity())
                self._send(200, uyelik.uye_bakiye(u["id"], paper.equity(), KOMISYON_PCT)); return
            if yol == "/uye/borsa":                          # N29: borsa API anahtarı bağla/kaldır (yalnızca okuma)
                if d.get("sil"): self._send(200, dict(borsalar=uyelik.borsa_sil(u["id"], d.get("borsa")))); return
                from nexora import borsa_hesap
                self._send(200, dict(borsalar=uyelik.borsa_bagla(u["id"], d.get("borsa"), d.get("api_key"), d.get("api_secret"),
                                                                 d.get("passphrase"), kasa(), borsa_hesap.Istemci))); return
            if yol == "/uye/baglanti":
                if d.get("sil"): uyelik.baglanti_sil(u["id"], d.get("tur"))
                else: uyelik.baglanti_kaydet(u["id"], d.get("tur"), d.get("adres"))
                self._send(200, uyelik.profil(u))
        except UyelikHatasi as e: self._send(400, {"hata": str(e)})
        except PermissionError as e: self._send(429, {"hata": str(e)})
        except ValueError: self._send(500, {"hata": "sunucu kasası okunamadı"})        # ayrıntı (anahtar vb.) yanıta yazılmaz

    def do_GET(self):
        parts = urlsplit(self.path)
        social_radar = parts.path == "/admin/social-radar"
        social_paper = parts.path == "/admin/social-paper"
        izin, yetki = self._izin(parts.path, False, private=social_radar or social_paper)
        if not izin: return
        if social_paper:
            from nexora.social_ai.paper_usdt import from_file
            try:
                preview = from_file(os.getenv("SOCIAL_PAPER_FIXTURE", ""), now=_time.time())
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                preview = dict(
                    schema_version=1, read_only=True, mode="OFFLINE_PAPER_ONLY",
                    real_order=False, social_ai_transfer=False, currency="USDT",
                    initial_cash_usdt="100", remaining_cash_usdt="100",
                    positions=0, results=[], snapshot_status="SNAPSHOT_ERROR"
                )
            self._send(200, preview, private=True)
            return
        if social_radar:
            from nexora.social_ai.radar.api import dashboard
            self._send(200, dashboard(os.getenv("SOCIAL_RADAR_SNAPSHOT", ""),
                                      live_enabled=os.getenv("SOCIAL_LIVE_ENABLED") == "1"), private=True)
            return
        if yetki == "uye":                                  # üye: sınırlı ve cüzdansız görünüm
            if parts.path == "/durum":
                self._send(200, dict(mod="PAPER", gercek_islem="KAPALI", acil_durdurma=paper.killed(), takip_nabiz=paper.son_nabiz(),
                                     rol="uye")); return
            if parts.path == "/portfoy": self._send(200, self._cuzdansiz(paper.portfolio())); return
            if parts.path == "/islemler": self._send(200, self._cuzdansiz(paper.trades())); return
        if parts.path == "/yedek/son": self._yedek_gonder(); return
        if parts.path == "/borsa":                          # Platform 2 (borsa) paper portföyü
            from nexora import borsa_liste
            yol = os.getenv("BORSA_DB", "nexora_borsa.db")
            if not os.path.exists(yol):
                self._send(200, dict(acik=False, liste=len(borsa_liste.yukle()), mesaj="borsa platformu henüz işlem yapmadı")); return
            bp = Paper(yol); p = bp.portfolio()
            self._send(200, dict(acik=True, liste=len(borsa_liste.yukle()), nakit=p["cash"], toplam=p["equity"], kz=p["pnl"],
                                 pozisyonlar=p["positions"], islemler=bp.trades(30))); return
        if parts.path == "/ekosistemler":                  # N23: ekosistem başına özet
            from nexora import ekosistem, piyasa
            dbs = [os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("BORSA_DB", "nexora_borsa.db")] + \
                  [f"nexora_strateji_{st.ad}.db" for st in piyasa.STRATEJILER] + ["nexora_bnb.db", "nexora_base.db"]
            self._send(200, dict(ekosistemler=[e for e in ekosistem.ozet(dbs) if e["aktif"]])); return   # TON rafta
        if parts.path == "/strateji":                       # Platform 2 · piyasa stratejileri karnesi
            from nexora import piyasa
            out = []
            for st in piyasa.STRATEJILER:
                yol = f"nexora_strateji_{st.ad}.db"
                if os.path.exists(yol): out.append(piyasa.ozet(Paper(yol), st))
                else: out.append(dict(ad=st.ad, aciklama=st.aciklama, bos=True))
            try: durum = json.load(open("piyasa_durum.json"))
            except (OSError, ValueError): durum = None
            self._send(200, dict(stratejiler=out, durum=durum)); return
        if parts.path == "/bildirim":                      # N32: borsada listesiz token sinyalleri (yalnızca bildirim)
            from nexora.bildirim import Bildirim
            self._send(200, dict(son=Bildirim(os.getenv("BILDIRIM_DB", "nexora_bildirim.db")).son(20))); return
        if parts.path == "/kanit":                         # kanıt karnesi: hangi kaynak gerçekten kazandırıyor
            from nexora.kanit import karne as _kanit
            self._send(200, _kanit(yon_db=os.getenv("YONLENDIRICI_DB", "nexora_yonlendirici.db"))); return
        if parts.path == "/yonlendirici":                  # N28: kaynak ağırlıklı yönlendirici (paper)
            from nexora.yonlendirici import Yonlendirici, kaynaklar
            self._send(200, Yonlendirici(os.getenv("YONLENDIRICI_DB", "nexora_yonlendirici.db")).durum(kaynaklar())); return
        if parts.path == "/hazirlik":
            from nexora import hazirlik as _hz
            from nexora.etiket import ozet as _et
            self._send(200, _hz.hazirlik(os.getenv("NEXORA_DB", "nexora_paper.db"), _et(os.getenv("ETIKET_DB", "nexora_etiket.db")))); return
        if parts.path == "/uye/ben":
            u = self._uye()
            if u: self._send(200, uyelik.profil(u))
            return
        if parts.path == "/uye/borsa":                      # N30: bağlı borsalar; ?bakiye=1 ile gerçek bakiye (yalnızca okuma)
            u = self._uye()
            if not u: return
            if parse_qs(parts.query).get("bakiye") == ["1"]:
                from nexora import borsa_hesap, piyasa
                import requests as _rq
                s_ = _rq.Session()
                self._send(200, uyelik.borsa_bakiye(u["id"], kasa(), borsa_hesap.Istemci,
                                                    lambda b: {**(piyasa.borsa_fiyatlari(s_, borsa_hesap.BORSALAR[b]["ad"]) or {}),
                                                               **borsa_hesap.fiat_kurlari(s_, b)}))
            else:
                self._send(200, dict(borsalar=uyelik.borsalar(u["id"])))
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
        if parts.path == "/teshis":                         # strateji teşhisi (yalnızca kurucu; UYE_GET'te yok)
            from nexora import teshis
            try: gun = min(14.0, max(1.0, float(parse_qs(parts.query).get("gun", ["3"])[0])))
            except ValueError: gun = 3.0
            self._send(200, dict(metin=teshis.rapor(GUN=gun), gun=gun, ozet=teshis.gunluk_ozet(gun=1.0))); return
        if parts.path == "/olaylar":
            try: son = float(parse_qs(parts.query).get("son", ["0"])[0])
            except ValueError: son = 0.0
            self._send(200, panel.olaylar(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db"), son,
                                          kesif_path="kesif_son.json", ozet=True))
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
        path = urlsplit(self.path).path
        token_research = path == "/admin/token-discovery"
        izin, _ = self._izin(path, True, private=token_research)
        if not izin: return
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            self._send(400, {"hata": "gecersiz istek boyutu"}, private=token_research); return
        if token_research and not 0 <= n <= 2048:
            self._send(413, {"hata": "istek siniri"}, private=True); return
        raw = self.rfile.read(n) if n else b"{}"
        if token_research:
            try:
                from nexora.social_ai.recent_research import research_manual, research_recent
                data = json.loads(raw)
                if not isinstance(data, dict): raise ValueError("JSON nesnesi gerekli")
                mode = data.get("mode", "recent")
                enabled = os.getenv("SOCIAL_RESEARCH_LIVE_ENABLED") == "1"
                if mode == "manual":
                    mint = data.get("mint")
                    if not isinstance(mint, str) or len(mint) > 64:
                        raise ValueError("gecersiz mint")
                    result = research_manual(mint, enabled=enabled)
                elif mode == "recent":
                    limit = data.get("limit", 2)
                    if type(limit) is not int or not 1 <= limit <= 3:
                        raise ValueError("limit 1 ile 3 arasi olmali")
                    result = research_recent(enabled=enabled, limit=limit)
                else:
                    raise ValueError("bilinmeyen analiz modu")
                self._send(200, result, private=True)
            except (ValueError, TypeError):
                self._send(400, {"hata": "gecersiz token arastirma istegi"}, private=True)
            except Exception as exc:
                self._send(503, {"hata": f"arastirma saglayicisi: {type(exc).__name__}"}, private=True)
            return
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
