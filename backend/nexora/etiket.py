"""N16 · Sinyal etiketleme motoru (yalnızca ölçüm; işlem yapmaz, paper defterine dokunmaz).

Takipteki her kaynak ALIM'ı için:
  1) Algılama anını (t0) ve daha önce alınmış özellikleri saklar. Alış/geri satış teklifleri ile token bilgisine
     ölçüm anının damgasını koyar. Sonradan gelen alanlar t0 özelliklerine katılmaz.
  2) Sonuç etiketleri: aynı token miktarının 5 dk ve 30 dk sonra, ve kaynak cüzdan sattığında (en geç 24 saat)
     gerçek satış teklifiyle USDC karşılığı; iki bacak ağ ücreti düşülmüş getiri.

Ayrı veritabanı (nexora_etiket.db). Canlı kopyalama öncelikli: teklif hattı boşken çalışır. Aynı cüzdan+token için
30 dk içinde tek örnek alınır; günlük üst sınır ETIKET_GUNLUK. Geç kalınan ufuklar 'kaçırıldı' olarak işaretlenir
(geç alınmış bir 5 dk etiketi yanıltıcı olur)."""
import heapq, json, os, queue, sqlite3, threading, time
from collections import defaultdict

from nexora.constants import USDC_MINT
from nexora.market import QuoteError
from nexora.model_kapisi import GOLGE_V1_SEMA, golge_v1_yaz, golge_yaz
from nexora.ozellik import TOKEN_ALANLARI
from nexora.olcum import (GIRIS_TOLERANS, IZLENEN, KAYNAK_TOLERANS, KAYNAK_ZAMAN_ASIMI, TEYIT_SN,
                          UFUKLAR, UCRET, etiket_sonucu, ham_miktar, net_getiri, pozitif,
                          salt_okunur, sayi, tutar_gecerli)

ETIKET_USD = float(os.getenv("ETIKET_USD", "5"))
GUNLUK = int(os.getenv("ETIKET_GUNLUK", "400"))
GOLGE_GUNLUK = int(os.getenv("ETIKET_GOLGE_GUNLUK", "300"))   # gölge havuz/izlenen sinyaller için ayrı sınır: kopyalanan sinyali dışarıda bırakmaz
TEKRAR_SN = 1800
HEDEF = 500

SEMA = """
CREATE TABLE IF NOT EXISTS etiket_olay(event_id TEXT PRIMARY KEY, ts REAL, wallet TEXT, token TEXT, sig TEXT, block_time REAL,
  gecikme_sn REAL, karar TEXT, gerekce TEXT, saat_utc INTEGER, gun INTEGER, giris_usdc REAL, qty_raw TEXT, giris_etki REAL,
  al_sat_kaybi_pct REAL, tb_yas_sn REAL, tb_likidite REAL, tb_mcap REAL, tb_sahip REAL, tb_organik REAL, tb_top_pct REAL,
  tb_dev_pct REAL, tb_sus INTEGER, cuzdan TEXT, durum TEXT, hata TEXT);
CREATE INDEX IF NOT EXISTS etiket_olay_wt ON etiket_olay(wallet, token, ts);
CREATE INDEX IF NOT EXISTS etiket_olay_token_ts ON etiket_olay(token, ts);
CREATE TABLE IF NOT EXISTS etiket_sonuc(event_id TEXT, ufuk TEXT, ts REAL, cikis_usdc REAL, getiri_pct REAL, sapma_sn REAL,
  hata TEXT, PRIMARY KEY(event_id, ufuk));
CREATE TABLE IF NOT EXISTS etiket_kaynak_satis(event_id TEXT PRIMARY KEY, wallet TEXT, token TEXT, ts REAL, block_time REAL);
CREATE INDEX IF NOT EXISTS etiket_satis_wt ON etiket_kaynak_satis(wallet, token, ts);
CREATE INDEX IF NOT EXISTS etiket_satis_ts ON etiket_kaynak_satis(ts);
"""

YENI_SUTUNLAR = {
    "teyit": "INTEGER", "olcum_v": "INTEGER", "kayit_ts": "REAL", "karar_ts": "REAL", "giris_ts": "REAL",
    "roundtrip_ts": "REAL", "token_ts": "REAL", "kaynak_vade": "REAL", "ucret_usdc": "REAL",
    "t0_token_ts": "REAL", "t0_token": "TEXT",
}


def getiri(cikis_usdc, giris=ETIKET_USD):
    sonuc = net_getiri(giris, cikis_usdc)
    return sonuc[1] if sonuc is not None else None


class Etiketci:
    def __init__(self, db_path, quoter, bilgi=None, cuzdanlar=None, clock=time.time, sleep=time.sleep, model=None, golge_model=None):
        self.db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SEMA)
        self.db.execute(GOLGE_V1_SEMA)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            mevcut = {r["name"] for r in self.db.execute("PRAGMA table_info(etiket_olay)")}
            for ad, tip in YENI_SUTUNLAR.items():
                if ad not in mevcut:
                    self.db.execute(f"ALTER TABLE etiket_olay ADD COLUMN {ad} {tip}")
        self.quoter, self.bilgi, self.cuzdanlar = quoter, bilgi, cuzdanlar or {}
        self.model, self.golge_model = model, golge_model
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.yeni = queue.Queue(maxsize=500)
        self.plan = []                                  # (vade, event_id, ufuk)
        self._yukle()

    # --- girişler (takip iş parçacıklarından çağrılır; teklif beklemez) -------------------------------------
    def sinyal(self, event_id, wallet, token, side, sig, block_time, gecikme, karar, gerekce, *, t0=None):
        karar_ts = self.clock()
        t0 = karar_ts if t0 is None else t0
        if side == "sell":
            self.kaynak_satti(wallet, token, event_id, t0, block_time)
        elif side == "buy":
            try:
                self.yeni.put_nowait((event_id, wallet, token, sig, block_time, gecikme, karar, gerekce, t0, karar_ts))
            except queue.Full:
                pass

    def kaynak_satti(self, wallet, token, event_id=None, ts=None, block_time=None):
        ts = self.clock() if ts is None else ts
        block_time = pozitif(block_time)
        with self.lock, self.db:
            self.db.execute("DELETE FROM etiket_kaynak_satis WHERE ts < ?", (self.clock() - KAYNAK_ZAMAN_ASIMI,))
            self.db.execute("INSERT OR IGNORE INTO etiket_kaynak_satis VALUES(?,?,?,?,?)",
                            (event_id, wallet, token, ts, block_time))
            rows = self.db.execute("""SELECT event_id, wallet, token, ts, block_time, kaynak_vade FROM etiket_olay
                WHERE wallet=? AND token=? AND durum='izleniyor' AND ts<=? AND ts>=?
                AND (kaynak_vade IS NULL OR kaynak_vade>?)
                AND NOT EXISTS (SELECT 1 FROM etiket_sonuc s WHERE s.event_id=etiket_olay.event_id AND s.ufuk='kaynak')""",
                (wallet, token, ts, ts - KAYNAK_ZAMAN_ASIMI, ts)).fetchall()
            for r in rows:
                vade = self._kaynak_vadesi(r)
                if vade is not None and (r["kaynak_vade"] is None or vade < r["kaynak_vade"]):
                    self.db.execute("UPDATE etiket_olay SET kaynak_vade=? WHERE event_id=?", (vade, r["event_id"]))
                    heapq.heappush(self.plan, (vade, r["event_id"], "kaynak"))

    def _kaynak_vadesi(self, o):
        return self.db.execute("""SELECT MIN(ts) FROM etiket_kaynak_satis
            WHERE wallet=? AND token=? AND ts BETWEEN ? AND ?
            AND (block_time IS NULL OR ? IS NULL OR block_time>?)""",
            (o["wallet"], o["token"], o["ts"], o["ts"] + KAYNAK_ZAMAN_ASIMI,
             pozitif(o["block_time"]), pozitif(o["block_time"]))).fetchone()[0]

    def _planla(self, o, var=()):
        for u, (gec, _) in UFUKLAR.items():
            if u not in var:
                heapq.heappush(self.plan, (o["ts"] + gec, o["event_id"], u))
        if "kaynak" not in var:
            vade = o["kaynak_vade"]
            if vade is None:
                heapq.heappush(self.plan, (o["ts"] + KAYNAK_ZAMAN_ASIMI, o["event_id"], "kaynak_asim"))
            else:
                heapq.heappush(self.plan, (vade, o["event_id"], "kaynak"))

    def _yukle(self):
        """Yeniden başlatmada bekleyen ufukları ve kaydedilmiş kaynak satışını planlar."""
        for r in self.db.execute("SELECT event_id, ts, kaynak_vade FROM etiket_olay WHERE durum='izleniyor'"):
            var = {x[0] for x in self.db.execute("SELECT ufuk FROM etiket_sonuc WHERE event_id=?", (r["event_id"],))}
            self._planla(r, var)

    def _bekle_bos(self, en_cok=30):
        """Canlı kopyalama öncelikli: teklif hattı boşalana kadar bekle (en çok 'en_cok' sn)."""
        bas = self.clock()
        while hasattr(self.quoter, "bos") and not self.quoter.bos() and self.clock() - bas < en_cok:
            self.sleep(0.5)

    def _teklif(self, i, o, tutar):
        q = self.quoter.quote(i, o, tutar)
        if not isinstance(q, dict) or ham_miktar(q.get("out_amount")) is None:
            raise QuoteError("geçersiz teklif")
        if "in_amount" in q and ham_miktar(q["in_amount"]) != tutar:
            raise QuoteError("tutarsız teklif")
        return q

    def _giris(self, item):
        event_id, wallet, token, sig, bt, gecikme, karar, gerekce, t0, karar_ts = item
        with self.lock:
            if self.db.execute("SELECT 1 FROM etiket_olay WHERE event_id=?", (event_id,)).fetchone():
                return None
            if self.db.execute("SELECT 1 FROM etiket_olay WHERE wallet=? AND token=? AND ts > ?",
                               (wallet, token, t0 - TEKRAR_SN)).fetchone():
                return "tekrar"
            gun_bas = t0 - (t0 % 86400)
            izlenen = gerekce == IZLENEN
            n = self.db.execute("""SELECT COUNT(*) FROM etiket_olay WHERE ts>=? AND ts<?
                AND (COALESCE(gerekce,'') = ?) = ?""", (gun_bas, gun_bas + 86400, IZLENEN, int(izlenen))).fetchone()[0]
            if n >= (GOLGE_GUNLUK if izlenen else GUNLUK):
                return "sinir"
            teyit = 1 + self.db.execute("""SELECT COUNT(DISTINCT wallet) FROM etiket_olay
                WHERE token=? AND wallet!=? AND ts>=? AND ts<? AND kayit_ts<?""",
                (token, wallet, t0 - TEYIT_SN, t0, t0)).fetchone()[0]
            once = self.db.execute("""SELECT * FROM etiket_olay WHERE token=? AND olcum_v=1
                AND token_ts>=? AND token_ts<? AND kayit_ts<? ORDER BY token_ts DESC, event_id LIMIT 1""",
                (token, t0 - TEYIT_SN, t0, t0)).fetchone()
        g = time.gmtime(t0)
        satir = dict(event_id=event_id, ts=t0, wallet=wallet, token=token, sig=sig, block_time=bt, gecikme_sn=gecikme,
                     karar=karar, gerekce=gerekce, saat_utc=g.tm_hour, gun=g.tm_wday, cuzdan=json.dumps(self.cuzdanlar.get(wallet) or {}),
                     teyit=teyit, olcum_v=1, karar_ts=karar_ts, ucret_usdc=2 * UCRET)
        if once is not None:
            snapshot = {k: sayi(once[k]) for k in TOKEN_ALANLARI}
            if snapshot["tb_yas_sn"] is not None:
                snapshot["tb_yas_sn"] += t0 - once["token_ts"]
            satir.update(t0_token_ts=once["token_ts"], t0_token=json.dumps(snapshot))
        tutar = int(round(ETIKET_USD * 1e6))
        hata = "alış teklifi yok"
        try:
            self._bekle_bos()
            if self.clock() > t0 + GIRIS_TOLERANS:
                hata = "geç giriş"
                raise QuoteError(hata)
            q = self._teklif(USDC_MINT, token, tutar)
            qty = ham_miktar(q["out_amount"])
            satir.update(giris_usdc=tutar / 1e6, giris_ts=self.clock(), qty_raw=str(qty),
                         giris_etki=sayi(q.get("price_impact_pct")))
            hata = "geri satış teklifi yok"
            self._bekle_bos()
            if self.clock() > t0 + GIRIS_TOLERANS:
                hata = "geç giriş"
                raise QuoteError(hata)
            back = self._teklif(token, USDC_MINT, qty)
            satir.update(roundtrip_ts=self.clock(),
                         al_sat_kaybi_pct=round((1 - ham_miktar(back["out_amount"]) / tutar) * 100, 4))
            if not t0 <= satir["giris_ts"] <= satir["roundtrip_ts"] <= t0 + GIRIS_TOLERANS:
                hata = "geç giriş"
                raise QuoteError(hata)
            if not tutar_gecerli(satir):
                hata = "teklif tutarsız"
                raise QuoteError(hata)
            satir["durum"] = "izleniyor"
        except QuoteError:
            satir.update(durum="giris_yok", hata=hata)
        if self.bilgi is not None and satir["durum"] == "izleniyor":
            try:
                self._bekle_bos()
                b = self.bilgi.fetch(token, now=self.clock())
                satir["token_ts"] = self.clock()
                for ad in ("yas_sn", "likidite", "mcap", "sahip", "organik", "top_pct", "dev_pct", "sus"):
                    satir["tb_" + ad] = sayi(b.get(ad))
            except Exception:
                pass
        with self.lock, self.db:
            satir.update(kayit_ts=self.clock(), kaynak_vade=self._kaynak_vadesi(satir))
            k = ",".join(satir)
            cur = self.db.execute(f"INSERT OR IGNORE INTO etiket_olay({k}) VALUES({','.join('?' * len(satir))})",
                                  tuple(satir.values()))
            if not cur.rowcount:
                return None
            golge_v1_yaz(self.db, satir, self.golge_model)
            if satir["durum"] == "izleniyor" and self.model is not None:
                try:
                    k = self.model.olasilik(satir)
                    if k is not None:
                        golge_yaz(self.db, event_id, t0, k)
                except Exception:
                    pass
        if satir["durum"] == "izleniyor":
            with self.lock:
                self._planla(satir)
        return satir["durum"]

    def _cikis(self, vade, event_id, ufuk):
        now = self.clock()
        with self.lock:
            o = self.db.execute("SELECT * FROM etiket_olay WHERE event_id=?", (event_id,)).fetchone()
            ad = "kaynak" if ufuk in ("kaynak", "kaynak_asim") else ufuk
            if not o or self.db.execute("SELECT 1 FROM etiket_sonuc WHERE event_id=? AND ufuk=?", (event_id, ad)).fetchone():
                return None
            if ((ufuk == "kaynak" and o["kaynak_vade"] != vade)
                    or (ufuk == "kaynak_asim" and o["kaynak_vade"] is not None)):
                return None
        tol = UFUKLAR[ufuk][1] if ufuk in UFUKLAR else KAYNAK_TOLERANS
        sonuc = dict(event_id=event_id, ufuk=ad, cikis_usdc=None, getiri_pct=None, hata=None)
        olcum_ts = None
        giris, qty = pozitif(o["giris_usdc"]), ham_miktar(o["qty_raw"])
        ucret = sayi(o["ucret_usdc"]) if o["olcum_v"] == 1 else 2 * UCRET
        if ufuk == "kaynak_asim":
            sonuc["hata"] = "zaman aşımı (kaynak 24 sa satmadı)"
        elif ufuk == "kaynak" and vade <= (o["roundtrip_ts"] or o["ts"]):
            sonuc["hata"] = "girişten önce satış"
        elif giris is None or qty is None or ucret is None or ucret < 0:
            sonuc["hata"] = "geçersiz giriş"
        elif now - vade > tol:
            sonuc["hata"] = "kaçırıldı"
        else:
            try:
                self._bekle_bos(10)
                if self.clock() - vade > tol:
                    sonuc["hata"] = "kaçırıldı"
                else:
                    q = self._teklif(o["token"], USDC_MINT, qty)
                    olcum_ts = self.clock()
                    if not vade <= olcum_ts <= vade + tol:
                        sonuc["hata"] = "kaçırıldı"
                    else:
                        cikis = ham_miktar(q["out_amount"]) / 1e6
                        net = net_getiri(giris, cikis, ucret)
                        if net is None:
                            sonuc["hata"] = "geçersiz çıkış"
                        else:
                            sonuc.update(cikis_usdc=cikis, getiri_pct=net[1])
            except QuoteError:
                sonuc["hata"] = "satılamadı: satış teklifi yok veya geçersiz"
        olcum_ts = self.clock() if olcum_ts is None else olcum_ts
        sonuc.update(ts=olcum_ts, sapma_sn=round(olcum_ts - vade, 1))
        with self.lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO etiket_sonuc VALUES(:event_id,:ufuk,:ts,:cikis_usdc,:getiri_pct,:sapma_sn,:hata)", sonuc)
            n = self.db.execute("SELECT COUNT(*) FROM etiket_sonuc WHERE event_id=?", (event_id,)).fetchone()[0]
            if n >= len(UFUKLAR) + 1:
                self.db.execute("UPDATE etiket_olay SET durum='tamam' WHERE event_id=?", (event_id,))
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
    try:
        c = salt_okunur(db_path)
        c.row_factory = sqlite3.Row
        try:
            c.execute("BEGIN")
            olay = {r["event_id"]: dict(r) for r in c.execute("SELECT * FROM etiket_olay")}
            say = dict(c.execute("SELECT durum, COUNT(*) FROM etiket_olay GROUP BY durum").fetchall())
            uf = {}
            getiriler = defaultdict(list)
            now = time.time()
            for s in c.execute("SELECT * FROM etiket_sonuc"):
                u = s["ufuk"]
                if s["event_id"] in olay and u in (*UFUKLAR, "kaynak"):
                    _, _, g = etiket_sonucu(olay[s["event_id"]], dict(s), u, now)
                    getiriler[u].append(g)
            for u, sonuc in getiriler.items():
                g = [x for x in sonuc if x is not None]
                uf[u] = dict(n=len(sonuc), etiketli=len(g), unknown=len(sonuc) - len(g),
                             ort_getiri=round(sum(g) / len(g), 2) if g else None, kazanan=sum(x > 0 for x in g))
            tam = uf.get("kaynak", {}).get("etiketli", 0)
        finally:
            c.close()
    except sqlite3.Error:
        return None
    toplam = sum(say.values())
    return dict(toplam=toplam, izleniyor=say.get("izleniyor", 0), tamam=say.get("tamam", 0), giris_yok=say.get("giris_yok", 0),
                etiketli=tam, hedef=hedef, ilerleme_pct=round(min(100.0, tam / hedef * 100), 1), ufuklar=uf)
