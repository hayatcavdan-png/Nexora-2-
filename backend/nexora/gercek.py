"""N12 · Kontrollü GERÇEK pilot (22.11.2026, kullanıcı: "Solana'da sistem hazır değilse hazırla. Gerekirse gerçek para ile deneme
yapılabilir"; emanet modeli YOK: yalnızca kurucunun kendi pilot cüzdanı).

Ne yapar: paper karar motoru bir Solana alımını KOPYALADI dediğinde, pilot cüzdan aynı token'ı SABİT küçük bir USDC tutarıyla
gerçekten alır; paper o pozisyonu kapattığında (kaynak sattı / 24 sa / kaynakta token kalmadı / elle) pilot da tamamını satar.
Akış: Jupiter /swap/v2/order (USDC->token) -> yapı denetimi -> zincir simülasyonu -> Ed25519 imza -> Jupiter /swap/v2/execute.

ÇİFT KİLİT: (1) ortam değişkeni GERCEK_ISLEM=1 ve (2) gercek_ayar.json'da acik=true (gercek_pilot.py ac ... ile, onay ifadesiyle).
İkisinden biri yoksa hiçbir emir gönderilmez. Satışlar, alımlar kapalıyken de yapılır (açık riski kapatmak için).
SINIRLAR (alım öncesi, hepsi zorunlu): acil durdurma kapalı; açık gerçek pozisyon < en_fazla_poz; açıktaki maliyet + bu işlem
<= butce_usd; bugünkü gerçekleşen zarar < gunluk_zarar_usd; toplam gerçekleşen zarar < durdurma_usd (aşılırsa pilot KENDİNİ kapatır).
Güçlendirme (ek alım) kopyalanmaz. Paper'da karşılığı kalmayan gerçek pozisyon bakım turunda satılır (uzlaştırma).
Anahtar: pilot_cuzdan.py'nin ürettiği dosya (PILOT_ANAHTAR, izin 600); anahtar asla loglanmaz, hata metnine konmaz."""
import base64, json, os, queue, sqlite3, threading, time

import requests

from nexora.constants import USDC_MINT
from nexora.ed25519 import acik_anahtar, b58, imzala
from nexora.emir import EmirHatasi, EmirHazirlayici, cozumle, denetle

EXECUTE_URL = "https://api.jup.ag/swap/v2/execute"
AYAR = "gercek_ayar.json"
VARSAYILAN = dict(acik=False, islem_usd=20.0, butce_usd=100.0, en_fazla_poz=5, gunluk_zarar_usd=15.0, durdurma_usd=40.0, kayma_bps=None)
SINIRLAR = dict(islem_usd=(5.0, 200.0), butce_usd=(10.0, 2000.0), en_fazla_poz=(1, 8), gunluk_zarar_usd=(1.0, 500.0), durdurma_usd=(1.0, 1000.0))

SEMA = """
CREATE TABLE IF NOT EXISTS gercek_islem(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, event_id TEXT, yon TEXT, token TEXT,
  usd REAL, miktar_raw TEXT, imza TEXT, durum TEXT, kod INTEGER, hata TEXT, sure_ms INTEGER, kz REAL);
CREATE TABLE IF NOT EXISTS gercek_poz(token TEXT PRIMARY KEY, event_id TEXT, acilis_ts REAL, maliyet_usd REAL, miktar_raw TEXT,
  satis_deneme INTEGER DEFAULT 0, son_deneme REAL);
CREATE INDEX IF NOT EXISTS gercek_islem_ts ON gercek_islem(ts);
"""


class GercekHata(RuntimeError):
    pass


def ayar_oku(yol=AYAR):
    d = dict(VARSAYILAN)
    try: d.update(json.load(open(yol)))
    except (OSError, ValueError): pass
    return d


def ayar_yaz(d, yol=AYAR):
    for k, (a, b) in SINIRLAR.items():
        if k in d and d[k] is not None and not a <= float(d[k]) <= b: raise GercekHata(f"{k} {a}–{b} arasında olmalı")
    if d.get("islem_usd", 0) > d.get("butce_usd", 0): raise GercekHata("işlem tutarı bütçeden büyük olamaz")
    with open(yol + ".tmp", "w") as f: json.dump(d, f, indent=1)
    os.replace(yol + ".tmp", yol)


def anahtar_yukle(yol):
    """Pilot anahtar dosyası (Solana CLI biçimi, 64 bayt). Dönüş: (tohum, adres). İçerik hata metnine konmaz."""
    try:
        b = bytes(json.load(open(yol)))
    except (OSError, ValueError, TypeError):
        raise GercekHata("pilot anahtar dosyası okunamadı") from None
    if len(b) != 64 or acik_anahtar(b[:32]) != b[32:]: raise GercekHata("pilot anahtar dosyası bozuk")
    return b[:32], b58(b[32:])


def imzali(tx_b64, tohum, adres):
    """Jupiter işlemini pilot anahtarla imzalar: yalnızca 0. imza yuvası (ücret ödeyen = biz). Önce yapı denetimi."""
    sorun, c = denetle(tx_b64, adres)
    if sorun: raise GercekHata("işlem denetimi: " + "; ".join(sorun))
    ham = bytearray(c["ham"]); bas = len(ham) - len(c["mesaj"]) - 64 * c["imza_sayisi"]
    ham[bas:bas + 64] = imzala(tohum, bytes(c["mesaj"]))
    return base64.b64encode(bytes(ham)).decode()


class GercekPilot:
    def __init__(self, paper, helius=None, anahtar_yolu=None, db_yol="nexora_gercek.db", ayar_yolu=AYAR, session=None,
                 api_key=None, saat=time.time, hazirlayici=None, simule=True):
        self.paper, self.ayar_yolu, self.saat, self.simule_et = paper, ayar_yolu, saat, simule
        self.s = session or requests.Session()
        self.api_key = os.getenv("JUPITER_API_KEY", "") if api_key is None else api_key
        self.h = hazirlayici or EmirHazirlayici(helius, api_key=self.api_key, session=self.s)
        self.tohum, self.adres = anahtar_yukle(anahtar_yolu or os.getenv("PILOT_ANAHTAR", "/var/lib/nexora/pilot.json"))
        self.db = sqlite3.connect(db_yol, timeout=30, check_same_thread=False); self.db.row_factory = sqlite3.Row
        self.db.executescript(SEMA); self.db.commit()
        self.kilit = threading.Lock(); self.q = queue.Queue(); self._is = None

    # ---- durum
    def ayar(self): return ayar_oku(self.ayar_yolu)

    def etkin(self):
        return os.getenv("GERCEK_ISLEM") == "1" and bool(self.ayar().get("acik"))

    def gun_kz(self, now=None):
        now = now or self.saat(); bas = now - now % 86400
        r = self.db.execute("SELECT COALESCE(SUM(kz),0) FROM gercek_islem WHERE yon='sell' AND durum='tamam' AND ts>=?", (bas,)).fetchone()
        return float(r[0])

    def toplam_kz(self):
        return float(self.db.execute("SELECT COALESCE(SUM(kz),0) FROM gercek_islem WHERE yon='sell' AND durum='tamam'").fetchone()[0])

    def ozet(self):
        a = self.ayar(); poz = [dict(r) for r in self.db.execute("SELECT * FROM gercek_poz")]
        son = [dict(r) for r in self.db.execute("SELECT * FROM gercek_islem ORDER BY id DESC LIMIT 15")]
        sat = self.db.execute("SELECT COUNT(*), SUM(kz>0) FROM gercek_islem WHERE yon='sell' AND durum='tamam'").fetchone()
        hata = self.db.execute("SELECT COUNT(*) FROM gercek_islem WHERE durum!='tamam'").fetchone()[0]
        return dict(etkin=self.etkin(), ortam=os.getenv("GERCEK_ISLEM") == "1", ayar=a, adres=self.adres, acik_poz=poz,
                    acik_maliyet=round(sum(p["maliyet_usd"] for p in poz), 2), kapanan=sat[0], kazanan=sat[1] or 0,
                    toplam_kz=round(self.toplam_kz(), 2), bugun_kz=round(self.gun_kz(), 2), basarisiz=hata, son=son)

    # ---- sınırlar
    def alim_engeli(self, token):
        a = self.ayar()
        if os.getenv("GERCEK_ISLEM") != "1": return "GERCEK_ISLEM=1 değil"
        if not a.get("acik"): return "pilot kapalı"
        if self.paper.killed(): return "acil durdurma açık"
        if self.db.execute("SELECT 1 FROM gercek_poz WHERE token=?", (token,)).fetchone(): return "bu token'da gerçek pozisyon var"
        n, mal = self.db.execute("SELECT COUNT(*), COALESCE(SUM(maliyet_usd),0) FROM gercek_poz").fetchone()
        if n >= int(a["en_fazla_poz"]): return "gerçek pozisyon sınırı dolu"
        if mal + float(a["islem_usd"]) > float(a["butce_usd"]) + 1e-9: return "bütçe dolu"
        if -self.gun_kz() >= float(a["gunluk_zarar_usd"]): return "günlük gerçek zarar sınırı"
        if -self.toplam_kz() >= float(a["durdurma_usd"]):
            a["acik"] = False; ayar_yaz(a, self.ayar_yolu)
            return "toplam zarar durdurma sınırına ulaştı: pilot KENDİNİ kapattı"
        return None

    # ---- yürütme
    def _kaydet(self, **k):
        k.setdefault("ts", self.saat())
        cols = ", ".join(k); self.db.execute(f"INSERT INTO gercek_islem({cols}) VALUES({', '.join('?' * len(k))})", tuple(k.values()))
        self.db.commit()

    def _calistir(self, giris, cikis, miktar_raw):
        """order -> (simülasyon) -> imza -> execute. Dönüş: execute yanıtı (dict). Hata: GercekHata."""
        try:
            o = self.h.hazirla(giris, cikis, int(miktar_raw), self.adres, kayma_bps=self.ayar().get("kayma_bps"))
        except EmirHatasi as e:
            raise GercekHata(f"order: {e}") from None
        if not o.get("transaction"): raise GercekHata(f"order: {o.get('hata') or 'işlem yok'}")
        if self.simule_et:
            try:
                sm = self.h.simule(o["transaction"])
            except Exception as e:
                raise GercekHata(f"simülasyon: {str(e)[:80]}") from None
            if not sm["basarili"]: raise GercekHata(f"simülasyon başarısız: {str(sm['hata'])[:80]}")
        imz = imzali(o["transaction"], self.tohum, self.adres)
        h = {"Content-Type": "application/json"}
        if self.api_key: h["x-api-key"] = self.api_key
        try:
            r = self.s.post(EXECUTE_URL, json=dict(signedTransaction=imz, requestId=o["request_id"]), headers=h, timeout=60)
            d = r.json()
        except (requests.RequestException, ValueError):
            raise GercekHata("execute bağlantı/yanıt hatası (işlem durumu belirsiz: imza kontrol edilecek)") from None
        if not isinstance(d, dict): raise GercekHata("execute yanıtı geçersiz")
        return d

    def al(self, event_id, token):
        engel = self.alim_engeli(token)
        if engel: return dict(durum="atlandi", neden=engel)
        a = self.ayar(); usd = float(a["islem_usd"]); t0 = time.time()
        with self.kilit:
            try:
                d = self._calistir(USDC_MINT, token, int(round(usd * 1e6)))
            except GercekHata as e:
                self._kaydet(event_id=event_id, yon="buy", token=token, usd=usd, durum="hata", hata=str(e)[:200],
                             sure_ms=int((time.time() - t0) * 1000)); return dict(durum="hata", neden=str(e))
            ok = d.get("code") == 0 and d.get("status") == "Success"
            harcanan = int(d.get("totalInputAmount") or d.get("inputAmountResult") or 0) / 1e6 or usd
            miktar = str(d.get("totalOutputAmount") or d.get("outputAmountResult") or "0")
            self._kaydet(event_id=event_id, yon="buy", token=token, usd=round(harcanan, 6), miktar_raw=miktar, imza=d.get("signature"),
                         durum="tamam" if ok else "basarisiz", kod=d.get("code"), hata=None if ok else str(d.get("error"))[:200],
                         sure_ms=int((time.time() - t0) * 1000))
            if ok and int(miktar) > 0:
                self.db.execute("INSERT OR REPLACE INTO gercek_poz(token, event_id, acilis_ts, maliyet_usd, miktar_raw) VALUES(?,?,?,?,?)",
                                (token, event_id, self.saat(), harcanan, miktar)); self.db.commit()
            return dict(durum="tamam" if ok else "basarisiz", kod=d.get("code"), imza=d.get("signature"))

    def sat(self, event_id, token):
        p = self.db.execute("SELECT * FROM gercek_poz WHERE token=?", (token,)).fetchone()
        if not p: return dict(durum="atlandi", neden="gerçek pozisyon yok")
        t0 = time.time()
        with self.kilit:
            self.db.execute("UPDATE gercek_poz SET satis_deneme=satis_deneme+1, son_deneme=? WHERE token=?", (self.saat(), token))
            self.db.commit()
            try:
                d = self._calistir(token, USDC_MINT, int(p["miktar_raw"]))
            except GercekHata as e:
                self._kaydet(event_id=event_id, yon="sell", token=token, durum="hata", hata=str(e)[:200],
                             sure_ms=int((time.time() - t0) * 1000)); return dict(durum="hata", neden=str(e))
            ok = d.get("code") == 0 and d.get("status") == "Success"
            gelen = int(d.get("totalOutputAmount") or d.get("outputAmountResult") or 0) / 1e6
            kz = round(gelen - p["maliyet_usd"], 6) if ok else None
            self._kaydet(event_id=event_id, yon="sell", token=token, usd=round(gelen, 6), miktar_raw=p["miktar_raw"],
                         imza=d.get("signature"), durum="tamam" if ok else "basarisiz", kod=d.get("code"),
                         hata=None if ok else str(d.get("error"))[:200], sure_ms=int((time.time() - t0) * 1000), kz=kz)
            if ok: self.db.execute("DELETE FROM gercek_poz WHERE token=?", (token,)); self.db.commit()
            return dict(durum="tamam" if ok else "basarisiz", kod=d.get("code"), kz=kz)

    def bakim(self, now=None):
        """Uzlaştırma: paper'da açık pozisyonu kalmayan gerçek pozisyonları satar (başarısız satışlar 2 dk arayla yeniden)."""
        now = now or self.saat(); out = []
        acik = {p["token"] for p in self.paper.portfolio()["positions"]}
        for p in self.db.execute("SELECT * FROM gercek_poz").fetchall():
            if p["token"] in acik: continue
            if p["son_deneme"] and now - p["son_deneme"] < 120: continue
            out.append((p["token"], self.sat(f"uzlastirma:{p['token']}:{int(now)}", p["token"])))
        return out

    # ---- karar motorundan bildirim (ağ işini takip döngüsünü bekletmeden arka planda yapar)
    def bildir(self, event_id, token, yon, ek=False):
        if yon == "buy" and (ek or not self.etkin()): return
        if yon == "sell" and not self.db.execute("SELECT 1 FROM gercek_poz WHERE token=?", (token,)).fetchone(): return
        self.q.put((event_id, token, yon))
        if self._is is None or not self._is.is_alive():
            self._is = threading.Thread(target=self._dongu, daemon=True); self._is.start()

    def _dongu(self):
        while True:
            try: event_id, token, yon = self.q.get(timeout=300)
            except queue.Empty: return
            try:
                r = (self.al if yon == "buy" else self.sat)(event_id, token)
                print(f"  GERÇEK {yon} {token[:6]}…: {r}", flush=True)
            except Exception as e:                                   # pilot hatası takibi asla durdurmaz
                print(f"  GERÇEK {yon} hata: {type(e).__name__}", flush=True)
