"""Uygulamanın Keşfet ve Portföy ekranları için sunucu tarafı (gerçek veri):
  radar()          takip edilen cüzdanların son 24 saatte aldığı token'lar + Jupiter token istatistikleri
  cuzdan_dna()     girilen bir cüzdanın gerçek analizi (Helius, ~20 kredi; günlük sınır, önbellek)
  manuel_islem()   elle paper işlem: kopyalama ile aynı güvenlik, teklif ve risk kurallarından geçer"""
import json, math, os, re, sqlite3, threading, time, uuid

ADRES = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
RADAR_ONBELLEK_SN = 120
DNA_GUNLUK = int(os.getenv("DNA_GUNLUK", "20"))
DNA_ONBELLEK_SN = 6 * 3600
_kilit = threading.Lock()
_radar = {"ts": 0, "veri": None}


def _ro(path):
    if not path or not os.path.exists(path): return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5); c.row_factory = sqlite3.Row
    return c


def _f(v):
    try:
        x = float(v); return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def radar(tracker_path, bilgi_getir, now=None, limit=40):
    """bilgi_getir(mints) -> {mint: MintInformation}. 2 dk önbellek."""
    now = now if now is not None else time.time()
    with _kilit:
        if _radar["veri"] is not None and now - _radar["ts"] < RADAR_ONBELLEK_SN: return _radar["veri"]
    c = _ro(tracker_path)
    satir = []
    if c is not None:
        try:
            satir = [dict(r) for r in c.execute("""SELECT token, COUNT(DISTINCT wallet) cuzdan, COUNT(*) alim, MIN(ts) ilk, MAX(ts) son,
                SUM(decision='KOPYALANDI') kopya FROM tracker_signals WHERE side='BUY' AND ts >= ? GROUP BY token
                ORDER BY son DESC LIMIT ?""", (now - 86400, limit))]
        except sqlite3.OperationalError:
            satir = []
        finally:
            c.close()
    try: bilgi = bilgi_getir([r["token"] for r in satir]) if satir else {}
    except Exception: bilgi = {}
    out = []
    for r in satir:
        b = bilgi.get(r["token"]) or {}
        st = b.get("stats24h") or {}
        hacim = (_f(st.get("buyVolume")) or 0) + (_f(st.get("sellVolume")) or 0)
        out.append(dict(token=r["token"], sembol=b.get("symbol") or r["token"][:4], ad=b.get("name") or "",
                        fiyat=_f(b.get("usdPrice")), degisim_24s=_f(st.get("priceChange")), hacim_24s=hacim or None,
                        likidite=_f(b.get("liquidity")), organik=_f(b.get("organicScore")), dogrulanmis=bool(b.get("isVerified")),
                        cuzdan=r["cuzdan"], alim=r["alim"], ilk=r["ilk"], son=r["son"], kopyalandi=bool(r["kopya"])))
    if out:
        en = max(out, key=lambda x: (x["cuzdan"], x["alim"]))
        ozet = (f"Son 24 saatte takip edilen cüzdanlar {len(out)} farklı token aldı. En çok ilgi: {en['sembol']} "
                f"({en['cuzdan']} cüzdan, {en['alim']} alım). {sum(1 for x in out if x['kopyalandi'])} tanesi kopyalandı.")
    else:
        ozet = "Son 24 saatte takip edilen cüzdanlardan alım sinyali yok."
    veri = dict(tokenler=out, ozet=ozet, guncelleme=now)
    with _kilit:
        _radar.update(ts=now, veri=veri)
    return veri


def nexora_puani(m, karar):
    """Şeffaf 0-100 puan (analiz metriklerinden). Yetersiz veride None."""
    if karar in ("swap yok", "yetersiz veri"): return None
    kaz = _f(m.get("kazanma_orani")) or 0; kf = min(_f(m.get("kar_faktoru")) or 0, 3)
    og = max(-0.5, min(0.5, _f(m.get("ort_getiri")) or 0)); n = min((_f(m.get("kapanan")) or 0) / 20, 1)
    dd = min(_f(m.get("dusus_kazanc_orani")) or 0, 1)
    p = kaz * 30 + kf / 3 * 30 + (og + 0.5) * 20 + n * 10 + (1 - dd) * 10
    if karar in ("bot şüphesi", "çok hızlı"): p -= 30
    if karar == "eksik veri": p -= 15
    return int(max(0, min(100, round(p))))


def dna_ozeti(m, karar, gerekce):
    puan = nexora_puani(m, karar)
    dd = _f(m.get("dusus_kazanc_orani")) or 0
    risk = "Yüksek" if karar in ("bot şüphesi", "zararda") or dd > 0.6 else ("Orta" if dd > 0.3 or karar in ("zayıf", "eksik veri", "çok hızlı") else "Düşük")
    swap = int(_f(m.get("swap")) or 0)
    kontrol = [
        dict(ad="Kârlılık geçmişi", deger="İyi" if (_f(m.get("gerceklesen_usd")) or 0) > 0 else "Zayıf", iyi=(_f(m.get("gerceklesen_usd")) or 0) > 0),
        dict(ad="İşlem aktivitesi", deger="Yüksek" if swap >= 50 else ("Orta" if swap >= 10 else "Düşük"), iyi=swap >= 10),
        dict(ad="Veri penceresi", deger=f"{_f(m.get('pencere_gun')) or 0:.1f} gün", iyi=(_f(m.get("pencere_gun")) or 0) >= 3),
        dict(ad="Bot / hacim kalıbı", deger="Var" if karar == "bot şüphesi" else "Düşük", iyi=karar != "bot şüphesi"),
    ]
    return dict(puan=puan, risk=risk, karar=karar, gerekce=gerekce, kontrol=kontrol,
                metrik={k: m.get(k) for k in ("kazanma_orani", "kar_faktoru", "ort_getiri", "kapanan", "gerceklesen_usd",
                                              "medyan_tutma_sn", "max_dusus_usd", "dusus_kazanc_orani", "swap", "token_sayisi")},
                yorum=f"Karar: {karar}. " + (gerekce or ""))


class DnaServisi:
    """Günlük sınırlı, önbellekli cüzdan analizi. analiz_et(adres) -> (metrik, karar, gerekçe)."""
    def __init__(self, db_path, analiz_et, now=time.time):
        self.db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS dna(adres TEXT PRIMARY KEY, ts REAL, veri TEXT)"); self.db.commit()
        self.analiz_et, self.now, self.lock = analiz_et, now, threading.Lock()

    def getir(self, adres, yenile=False):
        if not isinstance(adres, str) or not ADRES.match(adres.strip()): raise ValueError("geçersiz Solana adresi")
        adres = adres.strip(); t = self.now()
        with self.lock:
            r = self.db.execute("SELECT ts, veri FROM dna WHERE adres=?", (adres,)).fetchone()
            if r and not yenile and t - r[0] < DNA_ONBELLEK_SN: return dict(json.loads(r[1]), onbellek=True)
            bugun = self.db.execute("SELECT COUNT(*) FROM dna WHERE ts >= ?", (t - t % 86400,)).fetchone()[0]
            if bugun >= DNA_GUNLUK: raise PermissionError(f"günlük analiz sınırı ({DNA_GUNLUK}) doldu; Helius kredisi korunuyor")
        m, karar, gerekce = self.analiz_et(adres)
        veri = dict(adres=adres, ts=t, **dna_ozeti(m, karar, gerekce))
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO dna VALUES(?,?,?)", (adres, t, json.dumps(veri, ensure_ascii=False))); self.db.commit()
        return dict(veri, onbellek=False)


def manuel_islem(decider, token, yon, usd=None):
    """Elle paper işlem. Kopyalamayla aynı yol: kurallar -> token güvenliği -> gerçek teklif -> kayıt. Cüzdan etiketi MANUEL."""
    if not isinstance(token, str) or not ADRES.match(token.strip()): raise ValueError("geçersiz token adresi")
    if yon not in ("buy", "sell"): raise ValueError("yön 'buy' ya da 'sell' olmalı")
    if yon == "buy":
        try: usd = float(usd)
        except (TypeError, ValueError): raise ValueError("tutar geçersiz")
    ev = f"manuel:{uuid.uuid4().hex[:16]}"
    return dict(olay=ev, **decider.decide(ev, "MANUEL", token.strip(), yon, 0.0, boyut_usd=usd if yon == "buy" else None))
