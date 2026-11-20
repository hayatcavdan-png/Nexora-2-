"""Hyperliquid gölge ölçümü (20.11.2026, kullanıcı onayı: 'Evet hemen başlat'). SALT OKUNUR, İŞLEM YOK, ANAHTAR YOK.

Hyperliquid zincir üstü bir vadeli işlem borsası; her cüzdanın işlemleri resmi, herkese açık 'info' API'sinden okunur.
Amaç: büyük trader'ları kopyalasaydık (gecikmeyle, ücretle) ne olurdu? Memecoin gölge havuzuyla aynı yöntem:
  - Takip edilen cüzdan sıfırdan bir pozisyon açınca (startPosition == 0) sanal pozisyon açılır. Giriş fiyatı, bizim
    gördüğümüz andaki orta fiyat (allMids) + ücret ve kayma; kaynağın kendi fiyatı ayrıca kaydedilir (gecikme maliyeti).
  - Kaynağın pozisyonu sıfıra inince (ya da yön değiştirince) sanal pozisyon o anki orta fiyattan kapanır.
  - Ek ölçüm: 30 dk sonraki orta fiyat (zaman çıkışı karşılaştırması). 7 günde kapanmayan pozisyon zaman aşımıyla kapanır.
  - Kaldıraç kopyalanmaz: getiri kaldıraçsız fiyat değişimidir (yüzde). Fonlama ücreti hesaba katılmaz (rapor bunu yazar).
Takip başlamadan önce açılmış pozisyonlar ölçülmez (yalnızca takipten sonra sıfırdan açılanlar)."""
import json, os, sqlite3, time

import requests

API = os.getenv("HL_API", "https://api.hyperliquid.xyz/info")
LIDER = os.getenv("HL_LIDER", "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard")
UCRET_PCT = float(os.getenv("HL_UCRET_PCT", "0.065"))   # taraf başı: taker %0,045 + kayma/yarım makas %0,02
TAKER_PCT = float(os.getenv("HL_TAKER_PCT", "0.045"))   # emir defteri ölçümünde ücret (kayma defterden gelir)
BOYUT_USD = float(os.getenv("HL_BOYUT_USD", "100"))     # defter ölçümünde varsayılan pozisyon büyüklüğü ($)
DURAKLAR = (3.0, 5.0, 10.0)                              # zarar durdur karşılaştırması (%)
BAYAT_SN = 300                                         # bundan eski dolum yeni giriş açmaz (ilk okuma/kesinti sonrası)
ZAMAN_ASIMI_SN = 7 * 86400
ESIK = 1e-9

SEMA = """
CREATE TABLE IF NOT EXISTS hl_sinyal(id INTEGER PRIMARY KEY AUTOINCREMENT, wallet TEXT, coin TEXT, yon INTEGER,
  kaynak_ts REAL, kaynak_px REAL, giris_ts REAL, giris_px REAL, px_30dk REAL,
  cikis_ts REAL, cikis_px REAL, kaynak_cikis_px REAL, getiri_pct REAL, kaynak_getiri_pct REAL, getiri_30dk_pct REAL,
  durum TEXT DEFAULT 'acik', neden TEXT);
CREATE INDEX IF NOT EXISTS hl_sinyal_acik ON hl_sinyal(wallet, coin, durum);
CREATE TABLE IF NOT EXISTS hl_imlec(wallet TEXT PRIMARY KEY, son_ms INTEGER);
CREATE TABLE IF NOT EXISTS hl_gorulen(tid TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS hl_sayac(wallet TEXT, gun TEXT, dolum INTEGER, acilis INTEGER, PRIMARY KEY(wallet, gun));
"""


class Istemci:
    def __init__(self, s=None, zaman_asimi=15):
        self.s, self.za = s or requests.Session(), zaman_asimi

    def info(self, govde):
        r = self.s.post(API, json=govde, timeout=self.za); r.raise_for_status(); return r.json()

    def ortalar(self):
        return {k: float(v) for k, v in (self.info({"type": "allMids"}) or {}).items()}

    def dolumlar(self, wallet, bas_ms):
        return self.info({"type": "userFillsByTime", "user": wallet, "startTime": int(bas_ms), "aggregateByTime": False}) or []

    def defter(self, coin):
        """Emir defteri: (alışlar, satışlar), her biri [(fiyat, miktar)] en iyiden kötüye."""
        r = self.info({"type": "l2Book", "coin": coin}) or {}
        lv = r.get("levels") or [[], []]
        f = lambda a: [(float(x["px"]), float(x["sz"])) for x in a]
        return f(lv[0]), f(lv[1])

    def fonlama(self, coin, bas_ms, bit_ms):
        return [float(x.get("fundingRate") or 0) for x in
                self.info({"type": "fundingHistory", "coin": coin, "startTime": int(bas_ms), "endTime": int(bit_ms)}) or []]

    def pozisyon(self, wallet, coin):
        """Trader'ın o coin'deki pozisyonu: dict(kaldirac, tasfiye_px, giris_px) ya da None."""
        r = self.info({"type": "clearinghouseState", "user": wallet}) or {}
        for a in r.get("assetPositions") or []:
            p = a.get("position") or {}
            if p.get("coin") == coin:
                lv = p.get("leverage") or {}
                f = lambda v: float(v) if v not in (None, "") else None
                return dict(kaldirac=f(lv.get("value")), tasfiye_px=f(p.get("liquidationPx")), giris_px=f(p.get("entryPx")))
        return None

    def lider(self):
        r = self.s.get(LIDER, timeout=30); r.raise_for_status(); return r.json().get("leaderboardRows") or []


def vwap(seviyeler, usd):
    """Defterde 'usd' büyüklüğünde emrin ortalama dolum fiyatı (defter yetmezse None)."""
    kalan, maliyet, adet = usd, 0.0, 0.0
    for px, sz in seviyeler:
        al = min(kalan, px * sz); maliyet += al; adet += al / px; kalan -= al
        if kalan <= 1e-9: return maliyet / adet
    return None


GOC = ["giris_defter REAL", "cikis_defter REAL", "getiri_defter_pct REAL", "fonlama_pct REAL", "getiri_net_pct REAL",
       "kaldirac REAL", "tasfiye_px REAL", "en_kotu_pct REAL", "en_iyi_pct REAL", "boyut_usd REAL"]


def _perf(row, pencere):
    for ad, d in row.get("windowPerformances") or []:
        if ad == pencere: return {k: float(v or 0) for k, v in d.items()}
    return dict(pnl=0.0, roi=0.0, vlm=0.0)


def sec(satirlar, n=40, en_az_hesap=50_000, en_cok_devir=100.0):
    """Liderlik tablosundan aday: hesap ≥ 50 bin $, haftalık, aylık ve tüm zaman kârı pozitif, aylık getiri
    %5–%1000 arası, aylık hacim / hesap ≤ 100 (piyasa yapıcı/yüksek frekans hariç). Aylık kâra göre sıralı ilk n."""
    out = []
    for r in satirlar:
        try: hesap = float(r.get("accountValue") or 0)
        except ValueError: continue
        w, a, t = _perf(r, "week"), _perf(r, "month"), _perf(r, "allTime")
        if hesap < en_az_hesap or w["pnl"] <= 0 or a["pnl"] <= 0 or t["pnl"] <= 0: continue
        if not (0.05 <= a["roi"] <= 10) or a["vlm"] / hesap > en_cok_devir: continue
        out.append((a["pnl"], (r.get("ethAddress") or "").lower()))
    return [w for _, w in sorted(out, reverse=True) if w.startswith("0x")][:n]


def liste_oku(yol="hl_cuzdanlar.txt"):
    try: return [l.split()[0].lower() for l in open(yol) if l.strip() and not l.lstrip().startswith("#")]
    except OSError: return []


def liste_yaz(cuzdanlar, yol="hl_cuzdanlar.txt"):
    with open(yol + ".tmp", "w") as f:
        f.write(f"# Hyperliquid gölge takip ({time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC): yalnızca ölçülür, İŞLEM YOK.\n")
        f.writelines(w + "\n" for w in cuzdanlar)
    os.replace(yol + ".tmp", yol)


class Olcer:
    def __init__(self, db_yol="nexora_hl.db", istemci=None, saat=time.time):
        self.db = sqlite3.connect(db_yol, timeout=30, check_same_thread=False); self.db.row_factory = sqlite3.Row
        self.db.executescript(SEMA)
        var = {r[1] for r in self.db.execute("PRAGMA table_info(hl_sinyal)")}
        for g in GOC:
            if g.split()[0] not in var: self.db.execute(f"ALTER TABLE hl_sinyal ADD COLUMN {g}")
        self.db.commit()
        self.ist, self.saat = istemci or Istemci(), saat

    def _imlec(self, w, now):
        r = self.db.execute("SELECT son_ms FROM hl_imlec WHERE wallet=?", (w,)).fetchone()
        return r["son_ms"] if r else int((now - 120) * 1000)

    def _acik(self, w, coin):
        return self.db.execute("SELECT * FROM hl_sinyal WHERE wallet=? AND coin=? AND durum='acik'", (w, coin)).fetchone()

    def _defter_px(self, coin, alis):
        """Bizim büyüklüğümüzde gerçek dolum: alışta satış tarafını, satışta alış tarafını yürür."""
        try:
            bid, ask = self.ist.defter(coin)
            return vwap(ask if alis else bid, BOYUT_USD)
        except Exception:
            return None

    def _kapat(self, sg, px, now, kaynak_px=None, neden="kaynak kapattı"):
        g = sg["yon"] * (px / sg["giris_px"] - 1) * 100 - 2 * UCRET_PCT
        kg = None if kaynak_px is None else sg["yon"] * (kaynak_px / sg["kaynak_px"] - 1) * 100
        cd = self._defter_px(sg["coin"], alis=sg["yon"] < 0)          # long kapanışı = satış
        gd = None if not (cd and sg["giris_defter"]) else sg["yon"] * (cd / sg["giris_defter"] - 1) * 100 - 2 * TAKER_PCT
        try:                                                          # saatlik fonlama: oran > 0 iken long öder, short alır
            fon = -sg["yon"] * sum(self.ist.fonlama(sg["coin"], sg["giris_ts"] * 1000, now * 1000)) * 100
        except Exception:
            fon = None
        net = None if gd is None else gd + (fon or 0.0)
        r = lambda v: None if v is None else round(v, 4)
        self.db.execute("""UPDATE hl_sinyal SET durum='kapandi', cikis_ts=?, cikis_px=?, kaynak_cikis_px=?, getiri_pct=?,
                           kaynak_getiri_pct=?, neden=?, cikis_defter=?, getiri_defter_pct=?, fonlama_pct=?, getiri_net_pct=?
                           WHERE id=?""", (now, px, kaynak_px, round(g, 4), r(kg), neden, cd, r(gd), r(fon), r(net), sg["id"]))

    def _ac(self, w, coin, yon, d, px, now):
        gd = self._defter_px(coin, alis=yon > 0)
        try: tp = self.ist.pozisyon(w, coin) or {}
        except Exception: tp = {}
        self.db.execute("""INSERT INTO hl_sinyal(wallet, coin, yon, kaynak_ts, kaynak_px, giris_ts, giris_px, giris_defter, kaldirac,
                           tasfiye_px, boyut_usd, en_kotu_pct, en_iyi_pct) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0)""",
                        (w, coin, yon, d["time"] / 1000, float(d["px"]), now, px, gd, tp.get("kaldirac"), tp.get("tasfiye_px"), BOYUT_USD))

    def _say(self, w, now, acilis):
        gun = time.strftime("%Y-%m-%d", time.gmtime(now))
        self.db.execute("""INSERT INTO hl_sayac VALUES(?,?,1,?) ON CONFLICT(wallet, gun) DO UPDATE SET dolum=dolum+1,
                           acilis=acilis+excluded.acilis""", (w, gun, 1 if acilis else 0))

    def isle(self, w, dolumlar, ortalar, now):
        """Bir cüzdanın yeni dolumlarını zaman sırasıyla işler. Dönüş: (açılan, kapanan)."""
        acilan = kapanan = 0; son = self._imlec(w, now)
        for d in sorted(dolumlar, key=lambda x: (x.get("time", 0), str(x.get("tid")))):
            tid = str(d.get("tid") or d.get("hash", "") + str(d.get("time")))
            son = max(son, int(d.get("time", 0)))
            if self.db.execute("SELECT 1 FROM hl_gorulen WHERE tid=?", (tid,)).fetchone(): continue
            self.db.execute("INSERT INTO hl_gorulen VALUES(?)", (tid,))
            coin = d.get("coin") or ""
            if not coin or coin.startswith("@") or "/" in coin: continue      # spot değil, yalnızca vadeli
            try:
                bas = float(d["startPosition"]); sz = float(d["sz"]) * (1 if d.get("side") == "B" else -1)
            except (KeyError, TypeError, ValueError):
                continue
            yeni = bas + sz; mid = ortalar.get(coin)
            acik = self._acik(w, coin)
            if acik is not None and (abs(yeni) <= ESIK or (yeni > 0) != (acik["yon"] > 0)):
                if mid: self._kapat(acik, mid, now, float(d["px"])); kapanan += 1
            yeni_acilis = abs(yeni) > ESIK and (abs(bas) <= ESIK or (bas > 0) != (yeni > 0))
            self._say(w, now, yeni_acilis)
            if yeni_acilis and mid and now - d.get("time", 0) / 1000 <= BAYAT_SN and self._acik(w, coin) is None:
                self._ac(w, coin, 1 if yeni > 0 else -1, d, mid, now); acilan += 1
        self.db.execute("INSERT OR REPLACE INTO hl_imlec VALUES(?,?)", (w, son + 1))
        self.db.commit()
        return acilan, kapanan

    def zamanli(self, ortalar, now):
        """30 dk fiyatı ve 7 gün zaman aşımı."""
        for sg in self.db.execute("SELECT * FROM hl_sinyal WHERE durum='acik'").fetchall():
            mid = ortalar.get(sg["coin"])
            if not mid: continue
            h = sg["yon"] * (mid / sg["giris_px"] - 1) * 100             # en kötü / en iyi an (zarar durdur karşılaştırması)
            if h < (sg["en_kotu_pct"] or 0) or h > (sg["en_iyi_pct"] or 0):
                self.db.execute("UPDATE hl_sinyal SET en_kotu_pct=MIN(COALESCE(en_kotu_pct,0),?), en_iyi_pct=MAX(COALESCE(en_iyi_pct,0),?) WHERE id=?",
                                (round(h, 4), round(h, 4), sg["id"]))
            if sg["px_30dk"] is None and now - sg["giris_ts"] >= 1800:
                g = sg["yon"] * (mid / sg["giris_px"] - 1) * 100 - 2 * UCRET_PCT
                self.db.execute("UPDATE hl_sinyal SET px_30dk=?, getiri_30dk_pct=? WHERE id=?", (mid, round(g, 4), sg["id"]))
            if now - sg["giris_ts"] >= ZAMAN_ASIMI_SN: self._kapat(sg, mid, now, None, "zaman aşımı (7 gün)")
        self.db.commit()

    def tur(self, cuzdanlar):
        """Bir yoklama turu: tüm cüzdanların yeni dolumları. Dönüş: dict(acilan, kapanan, hata)."""
        now = self.saat(); ortalar = self.ist.ortalar(); acilan = kapanan = hata = 0
        for w in cuzdanlar:
            try:
                a, k = self.isle(w, self.ist.dolumlar(w, self._imlec(w, now)), ortalar, now); acilan += a; kapanan += k
            except (requests.RequestException, ValueError):
                hata += 1
        self.zamanli(ortalar, now)
        return dict(acilan=acilan, kapanan=kapanan, hata=hata)


def _md(v):
    v = sorted(v); n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def rapor(db_yol="nexora_hl.db", now=None, gun=14):
    """Kapanan ölçümler: genel ve cüzdan bazında getiri, kaynağın kendi getirisi, gecikme maliyeti, 30 dk karşılaştırması."""
    now = now or time.time()
    if not os.path.exists(db_yol): return None
    c = sqlite3.connect(f"file:{db_yol}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in c.execute("SELECT * FROM hl_sinyal WHERE giris_ts>=?", (now - gun * 86400,))]
        say = [dict(r) for r in c.execute("SELECT wallet, SUM(dolum) d, SUM(acilis) a, COUNT(*) g FROM hl_sayac GROUP BY wallet")]
    finally:
        c.close()
    kap = [r for r in rows if r["durum"] == "kapandi" and r["getiri_pct"] is not None]
    gec = [r["yon"] * (r["giris_px"] / r["kaynak_px"] - 1) * 100 for r in rows if r["kaynak_px"]]
    oz = lambda g: dict(n=len(g), ort=round(sum(g) / len(g), 3) if g else None, medyan=None if not g else round(_md(g), 3),
                        pozitif=round(100 * sum(x > 0 for x in g) / len(g)) if g else None)
    cz = {}
    for r in kap: cz.setdefault(r["wallet"], []).append(r["getiri_pct"])
    return dict(acik=sum(1 for r in rows if r["durum"] == "acik"), kapanan=len(kap),
                biz=oz([r["getiri_pct"] for r in kap]),
                kaynak=oz([r["kaynak_getiri_pct"] for r in kap if r["kaynak_getiri_pct"] is not None]),
                dk30=oz([r["getiri_30dk_pct"] for r in kap if r["getiri_30dk_pct"] is not None]),
                gecikme_pct=None if not gec else round(_md(gec), 4),
                cuzdan=sorted(((w, oz(g)) for w, g in cz.items()), key=lambda x: -(x[1]["ort"] or 0)),
                yogun=[(s["wallet"], round(s["d"] / max(1, s["g"]))) for s in say if s["d"] / max(1, s["g"]) > 200],
                **_ek(rows, kap, oz))


def _ek(rows, kap, oz):
    """Gerçekçi ölçüm (20.11): defterden dolum, fonlama, net; kaldıraç dilimleri; zarar durdur karşılaştırması."""
    kayma = [r["yon"] * (r["giris_defter"] / r["giris_px"] - 1) * 100 for r in rows if r.get("giris_defter") and r.get("giris_px")]
    def dilim(k):
        if k is None: return "bilinmiyor"
        return "≤3x" if k <= 3 else ("3–10x" if k <= 10 else ">10x")
    kd = {}
    for r in kap: kd.setdefault(dilim(r.get("kaldirac")), []).append(r["getiri_net_pct"] if r.get("getiri_net_pct") is not None else r["getiri_pct"])
    durak = []
    for d in DURAKLAR:
        g = [(-d - 2 * UCRET_PCT) if (r.get("en_kotu_pct") or 0) <= -d else r["getiri_pct"] for r in kap]
        durak.append(dict(durak=d, tetik=sum(1 for r in kap if (r.get("en_kotu_pct") or 0) <= -d), **oz(g)))
    return dict(defter=oz([r["getiri_defter_pct"] for r in kap if r.get("getiri_defter_pct") is not None]),
                net=oz([r["getiri_net_pct"] for r in kap if r.get("getiri_net_pct") is not None]),
                fonlama=oz([r["fonlama_pct"] for r in kap if r.get("fonlama_pct") is not None]),
                kayma_pct=None if not kayma else round(_md(kayma), 4),
                kaldirac={k: oz(v) for k, v in sorted(kd.items())},
                duraklar=durak, boyut_usd=BOYUT_USD)


def satirlar(r):
    if not r: return ["[16] Hyperliquid gölge ölçümü: henüz veri yok (nexora-hl servisi)"]
    f = lambda o: "—" if o["ort"] is None else f"n={o['n']} ort %{o['ort']:+.2f} med %{o['medyan']:+.2f} poz %{o['pozitif']}"
    L = [f"[16] Hyperliquid gölge (kaldıraçsız, ücret dahil, fonlama hariç): açık {r['acik']}, kapanan {r['kapanan']}",
         f"    biz (gördüğümüz an orta fiyat): {f(r['biz'])}",
         f"    kaynağın kendisi: {f(r['kaynak'])}",
         f"    30 dk'da çıksaydık: {f(r['dk30'])}",
         f"    gecikme maliyeti medyan %{r['gecikme_pct']}" if r["gecikme_pct"] is not None else "    gecikme maliyeti: —"]
    L.append(f"    emir defterinden ({r.get('boyut_usd', BOYUT_USD):.0f}$, taker %{TAKER_PCT}): {f(r['defter'])}" if r.get("defter") else "    emir defteri: —")
    if r.get("net"): L.append(f"    fonlama dahil NET: {f(r['net'])} · fonlama ort {f(r['fonlama'])}")
    if r.get("kayma_pct") is not None: L.append(f"    giriş kayması medyan (defter − orta fiyat) %{r['kayma_pct']}")
    for k, o in (r.get("kaldirac") or {}).items(): L.append(f"    trader kaldıracı {k}: {f(o)}")
    for x in r.get("duraklar") or []: L.append(f"    zarar durdur %{x['durak']:.0f} olsaydı: tetiklenen {x['tetik']} · {f(x)}")
    for w, o in r["cuzdan"][:8]:
        L.append(f"    {w[:6]}…{w[-4:]} {f(o)}")
    if r["yogun"]: L.append(f"    günde 200+ dolum (yüksek frekans olabilir): {len(r['yogun'])} cüzdan")
    return L


def ekran(db_yol="nexora_hl.db", liste_yolu="hl_cuzdanlar.txt", now=None, gun=14):
    """Uygulama ekranı için: özet, trader tablosu (kapanan + açık), son 25 ölçüm."""
    now = now or time.time()
    r = rapor(db_yol, now, gun)
    out = dict(ozet=r, liste=len(liste_oku(liste_yolu)), cuzdanlar=[], son=[], ucret_pct=UCRET_PCT)
    if r is None: return out
    c = sqlite3.connect(f"file:{db_yol}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        rows = [dict(x) for x in c.execute("SELECT * FROM hl_sinyal WHERE giris_ts>=? ORDER BY giris_ts DESC", (now - gun * 86400,))]
    finally:
        c.close()
    cz = {}
    for x in rows:
        m = cz.setdefault(x["wallet"], dict(wallet=x["wallet"], acik=0, g=[], k=[]))
        if x["durum"] == "acik": m["acik"] += 1
        elif x["getiri_pct"] is not None:
            m["g"].append(x["getiri_pct"])
            if x["kaynak_getiri_pct"] is not None: m["k"].append(x["kaynak_getiri_pct"])
    for m in cz.values():
        g, k = m.pop("g"), m.pop("k")
        m.update(n=len(g), ort=round(sum(g) / len(g), 3) if g else None, medyan=round(_md(g), 3) if g else None,
                 pozitif=round(100 * sum(v > 0 for v in g) / len(g)) if g else None, kaynak_ort=round(sum(k) / len(k), 3) if k else None)
    out["cuzdanlar"] = sorted(cz.values(), key=lambda m: (-(m["n"] > 0), -(m["ort"] or 0), -m["acik"]))
    out["son"] = [dict(wallet=x["wallet"], coin=x["coin"], yon="long" if x["yon"] > 0 else "short", giris_ts=x["giris_ts"],
                       durum=x["durum"], getiri_pct=x["getiri_pct"], kaynak_getiri_pct=x["kaynak_getiri_pct"],
                       gecikme_pct=round(x["yon"] * (x["giris_px"] / x["kaynak_px"] - 1) * 100, 4) if x["kaynak_px"] else None)
                  for x in rows[:25]]
    return out


def cuzdan_detay(db_yol, wallet, now=None, gun=30):
    """Bir trader'ın tüm ölçümleri (uygulama detay sayfası)."""
    now = now or time.time(); wallet = (wallet or "").lower()
    if not os.path.exists(db_yol) or not wallet.startswith("0x"): return dict(wallet=wallet, olcumler=[], ozet=None)
    c = sqlite3.connect(f"file:{db_yol}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in c.execute("SELECT * FROM hl_sinyal WHERE wallet=? AND giris_ts>=? ORDER BY giris_ts DESC",
                                           (wallet, now - gun * 86400))]
    finally:
        c.close()
    kap = [r for r in rows if r["durum"] == "kapandi" and r["getiri_pct"] is not None]
    g = [r.get("getiri_net_pct") if r.get("getiri_net_pct") is not None else r["getiri_pct"] for r in kap]
    k = [r["kaldirac"] for r in rows if r.get("kaldirac")]
    ozet = dict(n=len(kap), acik=len(rows) - len(kap), ort=round(sum(g) / len(g), 3) if g else None,
                medyan=round(_md(g), 3) if g else None, pozitif=round(100 * sum(x > 0 for x in g) / len(g)) if g else None,
                kaldirac_medyan=_md(k), tutma_dk_medyan=_md([(r["cikis_ts"] - r["giris_ts"]) / 60 for r in kap if r.get("cikis_ts")]))
    al = ("coin", "yon", "giris_ts", "cikis_ts", "durum", "getiri_pct", "getiri_net_pct", "kaynak_getiri_pct", "fonlama_pct",
          "kaldirac", "en_kotu_pct", "en_iyi_pct", "neden")
    return dict(wallet=wallet, ozet=ozet, olcumler=[{a: r.get(a) for a in al} for r in rows[:60]])
