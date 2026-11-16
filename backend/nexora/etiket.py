"""N16 · Sinyal etiketleme motoru (yalnızca ölçüm; işlem yapmaz, paper defterine dokunmaz).

Takipteki her kaynak ALIM'ı için:
  1) Alım anı özellikleri: gecikme, karar, saat; ETIKET_USD tutarlık gerçek alış teklifi ve hemen geri satış teklifi
     (al-sat maliyeti); token bilgisi (yaş, likidite, organik skor, sahip payı); cüzdanın analiz istatistikleri.
  2) Sonuç etiketleri: aynı token miktarının 5 dk ve 30 dk sonra, ve kaynak cüzdan sattığında (en geç 24 saat)
     gerçek satış teklifiyle USDC karşılığı; iki bacak ağ ücreti düşülmüş getiri.

Ayrı veritabanı (nexora_etiket.db). Canlı kopyalama öncelikli: teklif hattı boşken çalışır. Aynı cüzdan+token için
30 dk içinde tek örnek alınır; günlük üst sınır ETIKET_GUNLUK. Geç kalınan ufuklar 'kaçırıldı' olarak işaretlenir
(geç alınmış bir 5 dk etiketi yanıltıcı olur)."""
from nexora.model_kapisi import golge_yaz
import heapq, json, os, queue, sqlite3, threading, time

from nexora.constants import USDC_MINT
from nexora.market import QuoteError

ETIKET_USD = float(os.getenv("ETIKET_USD", "5"))
UCRET = 0.01
GUNLUK = int(os.getenv("ETIKET_GUNLUK", "400"))
TEKRAR_SN = 1800
UFUKLAR = {"5dk": (300, 120), "30dk": (1800, 300)}          # ufuk: (gecikme sn, tolerans sn)
KAYNAK_ZAMAN_ASIMI = 86400
HEDEF = 500

SEMA = """
CREATE TABLE IF NOT EXISTS etiket_olay(event_id TEXT PRIMARY KEY, ts REAL, wallet TEXT, token TEXT, sig TEXT, block_time REAL,
  gecikme_sn REAL, karar TEXT, gerekce TEXT, saat_utc INTEGER, gun INTEGER, giris_usdc REAL, qty_raw TEXT, giris_etki REAL,
  al_sat_kaybi_pct REAL, tb_yas_sn REAL, tb_likidite REAL, tb_mcap REAL, tb_sahip REAL, tb_organik REAL, tb_top_pct REAL,
  tb_dev_pct REAL, tb_sus INTEGER, cuzdan TEXT, durum TEXT, hata TEXT);
CREATE INDEX IF NOT EXISTS etiket_olay_wt ON etiket_olay(wallet, token, ts);
CREATE TABLE IF NOT EXISTS etiket_sonuc(event_id TEXT, ufuk TEXT, ts REAL, cikis_usdc REAL, getiri_pct REAL, sapma_sn REAL,
  hata TEXT, PRIMARY KEY(event_id, ufuk));
"""


def getiri(cikis_usdc, giris=ETIKET_USD):
    return round((cikis_usdc - giris - 2 * UCRET) / giris * 100, 4)


class Etiketci:
    def __init__(self, db_path, quoter, bilgi=None, cuzdanlar=None, clock=time.time, sleep=time.sleep, model=None):
        self.db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SEMA); self.db.commit()
        self.quoter, self.bilgi, self.cuzdanlar = quoter, bilgi, cuzdanlar or {}
        self.model = model                              # N19: varsa her sinyale gölge model kararı yazılır (işleme dokunmaz)
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.yeni = queue.Queue(maxsize=500)
        self.plan = []                                  # (vade, event_id, ufuk)
        self._yukle()

    # --- girişler (takip iş parçacıklarından çağrılır; asla beklemez) -------------------------------------
    def sinyal(self, event_id, wallet, token, side, sig, block_time, gecikme, karar, gerekce):
        if side == "sell":
            self.kaynak_satti(wallet, token); return
        try:
            self.yeni.put_nowait((event_id, wallet, token, sig, block_time, gecikme, karar, gerekce, self.clock()))
        except queue.Full:
            pass

    def kaynak_satti(self, wallet, token):
        now = self.clock()
        with self.lock:
            rows = self.db.execute("""SELECT o.event_id FROM etiket_olay o WHERE o.wallet=? AND o.token=? AND o.durum='izleniyor'
                AND o.ts >= ? AND NOT EXISTS (SELECT 1 FROM etiket_sonuc s WHERE s.event_id=o.event_id AND s.ufuk='kaynak')""",
                (wallet, token, now - KAYNAK_ZAMAN_ASIMI)).fetchall()
            for r in rows: heapq.heappush(self.plan, (now, r["event_id"], "kaynak"))

    # --- iş ------------------------------------------------------------------------------------------------
    def _yukle(self):
        """Yeniden başlatmada bekleyen ufukları planlar."""
        for r in self.db.execute("SELECT event_id, ts FROM etiket_olay WHERE durum='izleniyor'"):
            var = {x[0] for x in self.db.execute("SELECT ufuk FROM etiket_sonuc WHERE event_id=?", (r["event_id"],))}
            for u, (gec, _) in UFUKLAR.items():
                if u not in var: heapq.heappush(self.plan, (r["ts"] + gec, r["event_id"], u))
            if "kaynak" not in var: heapq.heappush(self.plan, (r["ts"] + KAYNAK_ZAMAN_ASIMI, r["event_id"], "kaynak_asim"))

    def _bekle_bos(self, en_cok=30):
        """Canlı kopyalama öncelikli: teklif hattı boşalana kadar bekle (en çok 'en_cok' sn)."""
        bas = self.clock()
        while hasattr(self.quoter, "bos") and not self.quoter.bos() and self.clock() - bas < en_cok:
            self.sleep(0.5)

    def _giris(self, item):
        event_id, wallet, token, sig, bt, gecikme, karar, gerekce, t0 = item
        with self.lock:
            if self.db.execute("SELECT 1 FROM etiket_olay WHERE event_id=?", (event_id,)).fetchone(): return None
            if self.db.execute("SELECT 1 FROM etiket_olay WHERE wallet=? AND token=? AND ts > ?",
                               (wallet, token, t0 - TEKRAR_SN)).fetchone(): return "tekrar"
            gun_bas = t0 - (t0 % 86400)
            if self.db.execute("SELECT COUNT(*) FROM etiket_olay WHERE ts >= ?", (gun_bas,)).fetchone()[0] >= GUNLUK: return "sinir"
        g = time.gmtime(t0)
        satir = dict(event_id=event_id, ts=t0, wallet=wallet, token=token, sig=sig, block_time=bt, gecikme_sn=gecikme,
                     karar=karar, gerekce=gerekce, saat_utc=g.tm_hour, gun=g.tm_wday, cuzdan=json.dumps(self.cuzdanlar.get(wallet) or {}))
        tutar = int(round(ETIKET_USD * 1e6))
        try:
            self._bekle_bos(); q = self.quoter.quote(USDC_MINT, token, tutar)
            self._bekle_bos(); back = self.quoter.quote(token, USDC_MINT, q["out_amount"])
            satir.update(giris_usdc=ETIKET_USD, qty_raw=str(q["out_amount"]), giris_etki=q.get("price_impact_pct"),
                         al_sat_kaybi_pct=round((1 - back["out_amount"] / tutar) * 100, 4), durum="izleniyor")
        except QuoteError as e:
            satir.update(durum="giris_yok", hata=str(e)[:80])
        if self.bilgi is not None:
            try:
                self._bekle_bos(); b = self.bilgi.fetch(token, now=t0)
                satir.update(tb_yas_sn=b.get("yas_sn"), tb_likidite=b.get("likidite"), tb_mcap=b.get("mcap"), tb_sahip=b.get("sahip"),
                             tb_organik=b.get("organik"), tb_top_pct=b.get("top_pct"), tb_dev_pct=b.get("dev_pct"), tb_sus=b.get("sus"))
            except Exception:
                pass
        with self.lock:
            k = ",".join(satir); self.db.execute(f"INSERT OR IGNORE INTO etiket_olay({k}) VALUES({','.join('?' * len(satir))})",
                                                 tuple(satir.values()))
            self.db.commit()
            if satir["durum"] == "izleniyor" and self.model is not None:
                try:
                    k = self.model.olasilik(satir)
                    if k is not None: golge_yaz(self.db, event_id, t0, k); self.db.commit()
                except Exception:
                    pass                                # gölge karar ölçümdür: hata etiketlemeyi durdurmaz
            if satir["durum"] == "izleniyor":
                for u, (gec, _) in UFUKLAR.items(): heapq.heappush(self.plan, (t0 + gec, event_id, u))
                heapq.heappush(self.plan, (t0 + KAYNAK_ZAMAN_ASIMI, event_id, "kaynak_asim"))
        return satir["durum"]

    def _cikis(self, vade, event_id, ufuk):
        now = self.clock()
        with self.lock:
            o = self.db.execute("SELECT * FROM etiket_olay WHERE event_id=?", (event_id,)).fetchone()
            ad = "kaynak" if ufuk in ("kaynak", "kaynak_asim") else ufuk
            if not o or self.db.execute("SELECT 1 FROM etiket_sonuc WHERE event_id=? AND ufuk=?", (event_id, ad)).fetchone():
                return None
        tol = UFUKLAR[ufuk][1] if ufuk in UFUKLAR else 3600
        sonuc = dict(event_id=event_id, ufuk=ad, ts=now, sapma_sn=round(now - vade, 1), cikis_usdc=None, getiri_pct=None, hata=None)
        if now - vade > tol:
            sonuc["hata"] = "kaçırıldı"
        else:
            try:
                self._bekle_bos(10); q = self.quoter.quote(o["token"], USDC_MINT, int(o["qty_raw"]))
                sonuc.update(cikis_usdc=q["out_amount"] / 1e6, getiri_pct=getiri(q["out_amount"] / 1e6))
            except QuoteError as e:
                sonuc.update(cikis_usdc=0.0, getiri_pct=getiri(0.0), hata=f"satılamadı: {str(e)[:60]}")
        if ufuk == "kaynak_asim" and not sonuc["hata"]: sonuc["hata"] = "zaman aşımı (kaynak 24 sa satmadı)"
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO etiket_sonuc VALUES(:event_id,:ufuk,:ts,:cikis_usdc,:getiri_pct,:sapma_sn,:hata)", sonuc)
            n = self.db.execute("SELECT COUNT(*) FROM etiket_sonuc WHERE event_id=?", (event_id,)).fetchone()[0]
            if n >= len(UFUKLAR) + 1: self.db.execute("UPDATE etiket_olay SET durum='tamam' WHERE event_id=?", (event_id,))
            self.db.commit()
        return sonuc

    def adim(self):
        """Bir tur: önce vadesi gelen çıkışlar (zamana duyarlı), sonra bir yeni sinyal. İş yapıldıysa True."""
        now = self.clock()
        with self.lock:
            hazir = heapq.heappop(self.plan) if self.plan and self.plan[0][0] <= now else None
        if hazir:
            self._cikis(*hazir); return True
        try:
            item = self.yeni.get_nowait()
        except queue.Empty:
            return False
        self._giris(item); return True

    def baslat(self):
        def run():
            while True:
                try:
                    if not self.adim(): self.sleep(1)
                except Exception:
                    self.sleep(5)
        threading.Thread(target=run, daemon=True).start()
        return self


def ozet(db_path, hedef=HEDEF):
    """Rapor ve uygulama için: ilerleme ve ufuk başına ortalama getiri ('hepsini kopyala' temel çizgisi)."""
    if not db_path or not os.path.exists(db_path): return None
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        say = dict(c.execute("SELECT durum, COUNT(*) FROM etiket_olay GROUP BY durum").fetchall())
        uf = {}
        for u, n, ok, ort, kaz in c.execute("""SELECT ufuk, COUNT(*), SUM(getiri_pct IS NOT NULL), AVG(getiri_pct),
                SUM(getiri_pct > 0) FROM etiket_sonuc GROUP BY ufuk"""):
            uf[u] = dict(n=n, etiketli=ok or 0, ort_getiri=round(ort, 2) if ort is not None else None, kazanan=kaz or 0)
        tam = c.execute("""SELECT COUNT(*) FROM etiket_olay o WHERE EXISTS (SELECT 1 FROM etiket_sonuc s
                WHERE s.event_id=o.event_id AND s.ufuk='kaynak' AND s.getiri_pct IS NOT NULL)""").fetchone()[0]
    except sqlite3.OperationalError:
        return None
    finally:
        c.close()
    toplam = sum(say.values())
    return dict(toplam=toplam, izleniyor=say.get("izleniyor", 0), tamam=say.get("tamam", 0), giris_yok=say.get("giris_yok", 0),
                etiketli=tam, hedef=hedef, ilerleme_pct=round(min(100.0, tam / hedef * 100), 1), ufuklar=uf)
