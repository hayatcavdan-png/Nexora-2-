"""Hyperliquid PAPER kopya motoru (27.11.2026, kullanıcı onayı: 'Onay veriyorum'). GERÇEK İŞLEM YOK: cüzdan, anahtar,
imza, yatırım yok. Yalnızca gölge ölçümün (hl.Olcer, hl_sinyal tablosu) gördüğü sinyalleri sanal bir hesapta kopyalar.

Kurallar (kendi risk kurallarımız; trader'ın kaldıracı KOPYALANMAZ):
- Uygun trader: son 14 günde en az MIN_OLCUM ölçüm, açıklar şu anki fiyatla dahil toplam ortalama > 0 ve kapanan
  ölçümlerin (fonlama dahil net) ortalaması > 0. Karar, sinyalin geldiği andaki geçmişe göre verilir (geleceği görmez).
- Trader long açarsa long, short açarsa short; trader kapatınca (ya da 7 gün zaman aşımında) kapatılır.
- Teminat = toplam varlığın POZ_PCT'si, kaldıraç KALDIRAC (pozisyon büyüklüğü = teminat × kaldıraç).
- Aynı anda en fazla MAKS_POZ pozisyon; aynı coin'de ikinci pozisyon açılmaz.
- Tasfiye: fiyat girişe göre (1/kaldıraç − bakım payı) kadar ters giderse teminatın tamamı kaybedilir.
- Maliyet: giriş/çıkış emir defterinden (yoksa orta fiyat + kayma), taker ücreti iki taraf, saatlik fonlama.
Hesap 100 $ ile başlar; memecoin defterinden ayrıdır (aynı nexora_hl.db içinde hlp_* tabloları)."""
import math, os, sqlite3, time

from nexora.hl import TAKER_PCT

BASLANGIC = float(os.getenv("HLP_BASLANGIC", "100"))
POZ_PCT = float(os.getenv("HLP_POZ_PCT", "0.05"))
KALDIRAC = float(os.getenv("HLP_KALDIRAC", "3"))
MAKS_POZ = int(os.getenv("HLP_MAKS_POZ", "5"))
MIN_OLCUM = int(os.getenv("HLP_MIN_OLCUM", "30"))
PENCERE_GUN = 14
KAYMA_PCT = 0.02            # defter fiyatı yoksa orta fiyata eklenen kayma (%)
BAKIM_PCT = 1.0             # tasfiye eşiğinden düşülen bakım teminatı payı (%)
BAYAT_SN = 600              # servis kesintisinden sonra eski sinyaller kopyalanmaz

SEMA = """
CREATE TABLE IF NOT EXISTS hlp_poz(id INTEGER PRIMARY KEY AUTOINCREMENT, sinyal_id INTEGER UNIQUE, wallet TEXT, coin TEXT,
  yon INTEGER, acilis_ts REAL, giris_px REAL, teminat REAL, buyukluk REAL, kaldirac REAL, durum TEXT DEFAULT 'acik',
  kapanis_ts REAL, cikis_px REAL, ucret REAL, fonlama REAL, pnl REAL, anlik_pnl REAL, neden TEXT);
CREATE TABLE IF NOT EXISTS hlp_durum(k TEXT PRIMARY KEY, v REAL);
CREATE TABLE IF NOT EXISTS hlp_atla(sinyal_id INTEGER PRIMARY KEY, ts REAL, wallet TEXT, coin TEXT, neden TEXT);
"""


def acik_mi():
    return os.getenv("HL_PAPER", "1") != "0"


def tasfiye_esigi(kaldirac=KALDIRAC):
    """Girişe göre ters fiyat hareketi (kesir) bu eşiğe ulaşınca teminat biter."""
    return 1.0 / kaldirac - BAKIM_PCT / 100


def trader_ozet(rows):
    """rows: bir trader'ın hl_sinyal satırları. dict(n, toplam_ort, kapanan_ort, kapanan_n)."""
    g = [r["getiri_net_pct"] if r["getiri_net_pct"] is not None else r["getiri_pct"]
         for r in rows if r["durum"] == "kapandi" and r["getiri_pct"] is not None]
    a = [r["anlik_pct"] for r in rows if r["durum"] == "acik" and r["anlik_pct"] is not None]
    ort = lambda v: sum(v) / len(v) if v else None
    return dict(n=len(g) + len(a), kapanan_n=len(g), toplam_ort=ort(g + a), kapanan_ort=ort(g))


def uygun(oz):
    return oz["n"] >= MIN_OLCUM and (oz["toplam_ort"] or 0) > 0 and (oz["kapanan_ort"] or 0) > 0


class HlPaper:
    def __init__(self, db, saat=time.time):
        """db: hl.Olcer'in sqlite bağlantısı (row_factory = sqlite3.Row)."""
        self.db, self.saat = db, saat
        self.db.executescript(SEMA)
        if self._al("nakit") is None:
            son = self.db.execute("SELECT COALESCE(MAX(id), 0) FROM hl_sinyal").fetchone()[0]
            self._yaz("nakit", BASLANGIC); self._yaz("son_sinyal", son); self._yaz("baslangic_ts", saat())
        self.db.commit()

    def _al(self, k):
        r = self.db.execute("SELECT v FROM hlp_durum WHERE k=?", (k,)).fetchone()
        return None if r is None else r[0]

    def _yaz(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO hlp_durum VALUES(?,?)", (k, v))

    def _acik(self):
        return self.db.execute("SELECT * FROM hlp_poz WHERE durum='acik'").fetchall()

    def varlik(self):
        return self._al("nakit") + sum(p["teminat"] + (p["anlik_pnl"] or 0) for p in self._acik())

    def _trader(self, wallet, now):
        rows = self.db.execute("SELECT durum, getiri_pct, getiri_net_pct, anlik_pct FROM hl_sinyal WHERE wallet=? AND giris_ts>=?",
                               (wallet, now - PENCERE_GUN * 86400)).fetchall()
        return trader_ozet(rows)

    def _atla(self, sg, now, neden):
        self.db.execute("INSERT OR IGNORE INTO hlp_atla VALUES(?,?,?,?,?)", (sg["id"], now, sg["wallet"], sg["coin"], neden))

    def _giris(self, sg):
        if sg["giris_defter"]: return sg["giris_defter"]
        return sg["giris_px"] * (1 + sg["yon"] * KAYMA_PCT / 100)

    def _yeni(self, now):
        acilan = 0; son = int(self._al("son_sinyal") or 0)
        for sg in self.db.execute("SELECT * FROM hl_sinyal WHERE id>? ORDER BY id", (son,)).fetchall():
            son = sg["id"]
            if now - sg["giris_ts"] > BAYAT_SN: self._atla(sg, now, "bayat sinyal (servis kesintisi)"); continue
            if not uygun(self._trader(sg["wallet"], sg["giris_ts"])):
                continue                                   # uygun olmayan trader: sessizce geç (çoğunluk)
            acik = self._acik()
            if len(acik) >= MAKS_POZ: self._atla(sg, now, f"en fazla {MAKS_POZ} pozisyon"); continue
            if any(p["coin"] == sg["coin"] for p in acik): self._atla(sg, now, "aynı coin'de açık pozisyon var"); continue
            teminat = round(self.varlik() * POZ_PCT, 4); buyukluk = teminat * KALDIRAC
            ucret = buyukluk * TAKER_PCT / 100
            if teminat < 1.0 or self._al("nakit") < teminat + ucret: self._atla(sg, now, "yetersiz nakit"); continue
            self.db.execute("""INSERT INTO hlp_poz(sinyal_id, wallet, coin, yon, acilis_ts, giris_px, teminat, buyukluk, kaldirac,
                               ucret, fonlama, anlik_pnl) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                            (sg["id"], sg["wallet"], sg["coin"], sg["yon"], now, self._giris(sg), teminat, buyukluk, KALDIRAC,
                             ucret, -ucret))
            self._yaz("nakit", self._al("nakit") - teminat - ucret); acilan += 1
        self._yaz("son_sinyal", son)
        return acilan

    def _kapat(self, p, px, now, fon_pct, neden, tasfiye=False):
        hareket = p["yon"] * (px / p["giris_px"] - 1)
        cikis_ucret = p["buyukluk"] * (1 + hareket) * TAKER_PCT / 100
        fon = p["buyukluk"] * (fon_pct or 0.0) / 100
        brut = p["buyukluk"] * hareket + fon - cikis_ucret
        geri = 0.0 if tasfiye else max(0.0, p["teminat"] + brut)   # izole teminat: kayıp teminatla sınırlı; tasfiyede kalan pay da gider
        pnl = geri - p["teminat"] - p["ucret"]
        self.db.execute("""UPDATE hlp_poz SET durum='kapandi', kapanis_ts=?, cikis_px=?, ucret=?, fonlama=?, pnl=?, anlik_pnl=?,
                           neden=? WHERE id=?""", (now, px, p["ucret"] + cikis_ucret, fon, round(pnl, 6), round(pnl, 6), neden, p["id"]))
        self._yaz("nakit", self._al("nakit") + geri)

    def _guncelle(self, ortalar, now):
        kapanan = tasfiye = 0
        for p in self._acik():
            sg = self.db.execute("SELECT * FROM hl_sinyal WHERE id=?", (p["sinyal_id"],)).fetchone()
            if sg is not None and sg["durum"] == "kapandi":
                px = sg["cikis_defter"] or sg["cikis_px"] * (1 - p["yon"] * KAYMA_PCT / 100)
                self._kapat(p, px, now, sg["fonlama_pct"], "trader kapattı" if "kaynak" in (sg["neden"] or "") else (sg["neden"] or "kapandı"))
                kapanan += 1; continue
            mid = ortalar.get(p["coin"])
            if not mid: continue
            hareket = p["yon"] * (mid / p["giris_px"] - 1)
            if hareket <= -tasfiye_esigi(p["kaldirac"]):
                px = p["giris_px"] * (1 - p["yon"] * tasfiye_esigi(p["kaldirac"]))
                self._kapat(p, px, now, None, f"TASFİYE ({p['kaldirac']:.0f}x)", tasfiye=True); tasfiye += 1; continue
            self.db.execute("UPDATE hlp_poz SET anlik_pnl=? WHERE id=?", (round(p["buyukluk"] * hareket - p["ucret"], 6), p["id"]))
        return kapanan, tasfiye

    def adim(self, ortalar, now=None):
        """Bir tur: önce kapanan/tasfiye, sonra yeni sinyaller. Dönüş: dict(acilan, kapanan, tasfiye, varlik)."""
        if not acik_mi(): return dict(durum="kapali")
        now = now or self.saat()
        kapanan, tasfiye = self._guncelle(ortalar, now)
        acilan = self._yeni(now)
        self.db.commit()
        return dict(acilan=acilan, kapanan=kapanan, tasfiye=tasfiye, varlik=round(self.varlik(), 4))


def _istat(v):
    n = len(v)
    if n == 0: return dict(n=0, toplam=0.0, ort=None, kazanma=None, t=None)
    ort = sum(v) / n
    sd = math.sqrt(sum((x - ort) ** 2 for x in v) / (n - 1)) if n > 1 else 0.0
    return dict(n=n, toplam=round(sum(v), 4), ort=round(ort, 4), kazanma=round(100 * sum(x > 0 for x in v) / n),
                t=round(ort / (sd / math.sqrt(n)), 2) if n > 1 and sd > 0 else None)


def ozet(db_yol, now=None):
    """Uygulama/rapor için salt okunur özet. Tablolar yoksa None."""
    now = now or time.time()
    if not os.path.exists(db_yol): return None
    c = sqlite3.connect(f"file:{db_yol}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='hlp_durum'").fetchone(): return None
        d = {r["k"]: r["v"] for r in c.execute("SELECT k, v FROM hlp_durum")}
        poz = [dict(r) for r in c.execute("SELECT * FROM hlp_poz ORDER BY id DESC")]
        atla = [dict(r) for r in c.execute("SELECT neden, COUNT(*) n FROM hlp_atla GROUP BY neden ORDER BY n DESC")]
        cz = {}
        for r in c.execute("SELECT wallet, durum, getiri_pct, getiri_net_pct, anlik_pct FROM hl_sinyal WHERE giris_ts>=?",
                           (now - PENCERE_GUN * 86400,)):
            cz.setdefault(r["wallet"], []).append(r)
    finally:
        c.close()
    acik = [p for p in poz if p["durum"] == "acik"]; kap = [p for p in poz if p["durum"] == "kapandi"]
    varlik = d.get("nakit", BASLANGIC) + sum(p["teminat"] + (p["anlik_pnl"] or 0) for p in acik)
    uy = []
    for w, rows in cz.items():
        o = trader_ozet(rows)
        if uygun(o): uy.append(dict(wallet=w, n=o["n"], toplam_ort=round(o["toplam_ort"], 3), kapanan_ort=round(o["kapanan_ort"], 3)))
    al = ("coin", "yon", "wallet", "acilis_ts", "kapanis_ts", "giris_px", "cikis_px", "teminat", "buyukluk", "pnl", "anlik_pnl", "neden")
    return dict(mod="PAPER", acik=acik_mi(), baslangic=BASLANGIC, varlik=round(varlik, 2), nakit=round(d.get("nakit", BASLANGIC), 2),
                kz=round(varlik - BASLANGIC, 2), kz_pct=round((varlik / BASLANGIC - 1) * 100, 2), baslangic_ts=d.get("baslangic_ts"),
                kapanan=_istat([p["pnl"] for p in kap]), tasfiye=sum(1 for p in kap if (p["neden"] or "").startswith("TASFİYE")),
                pozisyonlar=[{a: p[a] for a in al} for p in acik], son_kapanan=[{a: p[a] for a in al} for p in kap[:20]],
                uygun=sorted(uy, key=lambda x: -x["toplam_ort"]), atlanan=atla,
                kurallar=dict(kaldirac=KALDIRAC, poz_pct=POZ_PCT * 100, maks_poz=MAKS_POZ, min_olcum=MIN_OLCUM,
                              tasfiye_pct=round(tasfiye_esigi() * 100, 1), taker_pct=TAKER_PCT, pencere_gun=PENCERE_GUN))


def satirlar(r):
    if not r: return ["Hyperliquid paper kopya: henüz başlamadı"]
    k = r["kapanan"]
    L = [f"Hyperliquid PAPER kopya (kaldıraç {r['kurallar']['kaldirac']:.0f}x, pozisyon başı %{r['kurallar']['poz_pct']:.0f} teminat): "
         f"varlık {r['varlik']} $ ({r['kz_pct']:+.2f}%), nakit {r['nakit']} $",
         f"    kapanan {k['n']} · toplam {k['toplam']} $ · ort {k['ort']} $ · kazanma %{k['kazanma']} · t {k['t']} · tasfiye {r['tasfiye']}",
         f"    açık {len(r['pozisyonlar'])} · uygun trader {len(r['uygun'])} (≥{r['kurallar']['min_olcum']} ölçüm, toplam ort > 0)"]
    for p in r["pozisyonlar"]:
        L.append(f"    AÇIK {p['coin']} {'LONG' if p['yon'] > 0 else 'SHORT'} {p['buyukluk']:.2f}$ · anlık {p['anlik_pnl']:+.3f} $ · {p['wallet'][:8]}")
    for a in r["atlanan"]: L.append(f"    atlanan: {a['neden']} ({a['n']})")
    return L
