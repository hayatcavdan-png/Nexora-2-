"""BTC öngörü (PAPER). Saat başı: Binance BTC/USDT 1 saatlik mumlarından özellikler -> Gemini yön tahmini (YUKARI/ASAGI/BELIRSIZ)
-> Solana üzerinde cbBTC için Jupiter teklifiyle SANAL al/sat. Gerçek emir YOK, imza YOK, cüzdan YOK.

Varsayılan KAPALI: BTC_ONGORU=1 ve GEMINI_API_KEY gerekir. Ayrı veritabanı (nexora_btc.db); kopyalama motoruna dokunmaz.
Her tahmin kaydedilir ve UFUK_SN sonra gerçekleşen fiyatla puanlanır. Aynı anda basit bir kural (4 saatlik yön + 24 saat
ortalamasına göre konum) da puanlanır; YZ bu kuralı ve BTC'yi tutmayı yenemezse sistem kanıtlanmış sayılmaz.
Güvenlik: YZ yanıtı okunamazsa ya da ağ hatası olursa alım yapılmaz; zarar kes kuralı YZ'den bağımsız çalışır.
BTC son 4 saatte DUSUS_KAPISI'ndan fazla düştüyse YZ 'yukarı' dese bile alım yapılmaz (rejim kapısı)."""
import json, math, os, re, sys, time

import requests

from nexora import yz_xai
from nexora.constants import USDC_MINT

BTC_MINT = os.getenv("BTC_MINT", "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij")   # Coinbase Wrapped BTC (Solana)
BTC_DEC, USDC_DEC = 8, 6
CUZDAN = "yz_btc"                       # trades/positions tablosunda kaynak adı (gerçek cüzdan değil)
KLINE_URL = "https://api.binance.com/api/v3/klines"
UFUK_SN = 4 * 3600                      # tahmin ufku: 4 saat sonra puanlanır
POZ_ORAN = 0.5                          # portföyün en fazla yarısı BTC'de
NAKIT_REZERV = 1.0
MIN_GUVEN = 60                          # YZ güveni bunun altındaysa işlem yok
ZARAR_KES_PCT = 3.0                     # YZ'den bağımsız: pozisyon %3 zarardaysa satılır
DUSUS_KAPISI = -2.0                     # BTC 4 saatte %2'den fazla düştüyse alım yok
MAKS_ETKI_PCT = 1.0                     # cbBTC teklifinde izin verilen fiyat etkisi
YONLER = ("YUKARI", "ASAGI", "BELIRSIZ")

SEMA = """CREATE TABLE IF NOT EXISTS btc_tahmin(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, fiyat REAL, yon TEXT, guven INTEGER,
  gerekce TEXT, kural_yon TEXT, ozellik TEXT, karar TEXT, karar_neden TEXT, hedef_ts REAL, sonuc_fiyat REAL, sonuc_pct REAL,
  isabet INTEGER, kural_isabet INTEGER, model TEXT, hata TEXT);"""


def acik():
    return os.getenv("BTC_ONGORU") == "1"


# ---------------------------------------------------------------- veri
def mumlar(s=None, limit=72, baslangic_ms=None, timeout=15):
    """BTC/USDT 1 saatlik mumlar: [(acilis_ts, kapanis_ts, kapanis_fiyat, yuksek, dusuk)] (saniye). Hata: istisna."""
    s = s or requests.Session()
    params = {"symbol": "BTCUSDT", "interval": "1h", "limit": limit}
    if baslangic_ms is not None: params["startTime"] = int(baslangic_ms)
    r = s.get(KLINE_URL, params=params, timeout=timeout)
    r.raise_for_status()
    out = []
    for m in r.json():
        try:
            a, y, d, k, kts = m[0] / 1000, float(m[2]), float(m[3]), float(m[4]), m[6] / 1000
        except (TypeError, ValueError, IndexError):
            continue
        if k > 0 and y >= d > 0: out.append((a, kts, k, y, d))
    return out


def gecmis_mumlar(bas_ts, bit_ts, s=None):
    """[bas_ts, bit_ts] aralığının tüm 1 saatlik mumları (1000'lik sayfalarla)."""
    s = s or requests.Session()
    out, imlec = [], int(bas_ts * 1000)
    while imlec < bit_ts * 1000:
        parca = mumlar(s, limit=1000, baslangic_ms=imlec)
        if not parca: break
        out.extend(parca)
        yeni = int(parca[-1][0] * 1000) + 3600_000
        if yeni <= imlec: break
        imlec = yeni
    return out


def degisim_at(mum, ts, sn):
    """`ts` anında (o ana kadar kapanmış son mum) son `sn` saniyedeki % değişim; veri yoksa None."""
    kapanmis = [m for m in mum if m[1] <= ts]
    if not kapanmis: return None
    son = kapanmis[-1]
    eski = [m for m in kapanmis if m[1] <= son[1] - sn + 1]
    if not eski or son[1] - eski[-1][1] < sn * 0.9: return None
    return (son[2] / eski[-1][2] - 1) * 100


def ozellikler(mum):
    """Son mumlardan sayısal özet (yüzdeler 2 haneli). En az 25 mum gerekir."""
    if len(mum) < 25: raise ValueError("yetersiz mum")
    k = [m[2] for m in mum]
    r = lambda n: round((k[-1] / k[-1 - n] - 1) * 100, 2)
    getiriler = [(k[i] / k[i - 1] - 1) * 100 for i in range(len(k) - 24, len(k))]
    ort = sum(getiriler) / len(getiriler)
    oynak = math.sqrt(sum((g - ort) ** 2 for g in getiriler) / len(getiriler))
    sma24 = sum(k[-24:]) / 24
    y24, d24 = max(m[3] for m in mum[-24:]), min(m[4] for m in mum[-24:])
    return dict(fiyat=round(k[-1], 2), r1=r(1), r4=r(4), r24=r(24), r48=r(48) if len(k) > 48 else None,
                oynaklik_1s=round(oynak, 2), sma24_sapma=round((k[-1] / sma24 - 1) * 100, 2),
                aralik_konum=round((k[-1] - d24) / (y24 - d24) * 100, 1) if y24 > d24 else 50.0)


def kural_yon(oz):
    """Kıyas kuralı (YZ'siz): 4 saatlik yön ve 24 saat ortalamasının üstü/altı aynı yöndeyse o yön."""
    if oz["r4"] > 0 and oz["sma24_sapma"] > 0: return "YUKARI"
    if oz["r4"] < 0 and oz["sma24_sapma"] < 0: return "ASAGI"
    return "BELIRSIZ"


# ---------------------------------------------------------------- YZ
def istem(oz):
    return ("Sen temkinli bir piyasa analistisin. Aşağıda BTC/USDT'nin 1 saatlik mumlarından hesaplanmış özet var "
            "(r1/r4/r24/r48: son 1/4/24/48 saatteki % değişim; oynaklik_1s: son 24 saatlik saatlik getirilerin standart sapması; "
            "sma24_sapma: fiyatın 24 saatlik ortalamaya göre % farkı; aralik_konum: 24 saatlik dip-zirve aralığında yüzde konum). "
            "Önümüzdeki 4 saat için BTC'nin yönünü tahmin et. Emin değilsen BELIRSIZ de; yanlış güven zararlıdır. "
            "YALNIZCA şu JSON'u döndür, başka metin yazma: "
            '{"yon": "YUKARI|ASAGI|BELIRSIZ", "guven": 0-100 arası tam sayı, "gerekce": "en fazla 25 kelime Türkçe"}'
            "\n\nVERİ:\n" + json.dumps(oz, ensure_ascii=False, sort_keys=True))


def yanit_coz(metin):
    """Model metninden {'yon','guven','gerekce'}; geçersizse None (işlem yapılmaz)."""
    if not metin: return None
    m = re.search(r"\{.*\}", metin, re.S)
    if not m: return None
    try: d = json.loads(m.group(0))
    except ValueError: return None
    yon = str(d.get("yon", "")).strip().upper().replace("Ş", "S").replace("İ", "I")
    try: guven = int(round(float(d.get("guven"))))
    except (TypeError, ValueError): return None
    if yon not in YONLER or not 0 <= guven <= 100: return None
    return dict(yon=yon, guven=guven, gerekce=str(d.get("gerekce", ""))[:200])


def yz_tahmin(oz, post=None):
    """(tahmin|None, model, hata)."""
    anahtar = os.getenv("GEMINI_API_KEY", "")
    if not anahtar and post is None: return None, yz_xai.MODEL, "GEMINI_API_KEY yok"
    try:
        y = yz_xai.gemini_cagir(istem(oz), anahtar, post=post)
    except Exception as e:                                  # ağ/HTTP: bu tur işlem yok
        return None, yz_xai.MODEL, f"{type(e).__name__}: {str(e)[:120]}"
    t = yanit_coz(yz_xai.metin_cek(y))
    return t, y.get("model", yz_xai.MODEL), (None if t else "yanıt okunamadı")


# ---------------------------------------------------------------- karar (saf)
def karar(oz, tahmin, poz_var, poz_pct=None, killed=False):
    """('al'|'sat'|'bekle', neden). Saf fonksiyon: ağ ve veritabanı yok."""
    if poz_var and poz_pct is not None and poz_pct <= -ZARAR_KES_PCT:
        return "sat", f"zarar kes (%{poz_pct:.2f})"
    if tahmin is None:
        return "bekle", "YZ tahmini yok"
    guclu = tahmin["guven"] >= MIN_GUVEN
    if poz_var:
        if tahmin["yon"] == "ASAGI" and guclu: return "sat", f"YZ aşağı (güven {tahmin['guven']})"
        return "bekle", "pozisyon korunuyor"
    if killed: return "bekle", "acil durdurma açık"
    if tahmin["yon"] != "YUKARI" or not guclu: return "bekle", f"YZ {tahmin['yon']} (güven {tahmin['guven']})"
    if oz["r4"] <= DUSUS_KAPISI: return "bekle", f"rejim kapısı: BTC 4 saatte %{oz['r4']:.2f}"
    return "al", f"YZ yukarı (güven {tahmin['guven']})"


# ---------------------------------------------------------------- puanlama
def _isabet(yon, pct):
    if yon == "YUKARI": return int(pct > 0)
    if yon == "ASAGI": return int(pct < 0)
    return None


def puanla(db, mum, now):
    """Ufku dolmuş tahminleri, hedef zamana kadar kapanmış son mumun fiyatıyla puanlar."""
    n = 0
    for r in db.execute("SELECT id, fiyat, yon, kural_yon, hedef_ts FROM btc_tahmin WHERE sonuc_fiyat IS NULL AND hedef_ts <= ?", (now,)).fetchall():
        kap = [m for m in mum if m[1] <= r[4] + 60]
        if not kap or kap[-1][1] < r[4] - 3600: continue      # o ana ait mum elde yok
        f = kap[-1][2]; pct = (f / r[1] - 1) * 100
        db.execute("UPDATE btc_tahmin SET sonuc_fiyat=?, sonuc_pct=?, isabet=?, kural_isabet=? WHERE id=?",
                   (f, round(pct, 3), _isabet(r[2], pct), _isabet(r[3], pct), r[0]))
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- çalıştırma
def _poz(paper):
    return paper.position(BTC_MINT)


def calistir(paper, quoter, s=None, post=None, now=None, durum_yolu="btc_durum.json"):
    """Bir tur. Dönüş: dict(durum, karar, neden, tahmin, ...)."""
    if not acik(): return dict(durum="kapali")
    now = now or time.time()
    db = paper.db
    db.executescript(SEMA)
    try:
        mum = mumlar(s)
        oz = ozellikler(mum)
    except Exception as e:
        return dict(durum="hata", hata=f"BTC verisi alınamadı: {type(e).__name__}")
    puanla(db, mum, now)
    if paper._get("kiyas_fiyat") is None:
        paper._set("kiyas_fiyat", oz["fiyat"]); paper._set("kiyas_ts", now); db.commit()

    pos = _poz(paper); poz_pct = None
    if pos:
        try:
            q = quoter.quote(BTC_MINT, USDC_MINT, int(pos["qty_raw"]))
            gelir = q["out_amount"] / 10 ** USDC_DEC
            paper.mark_price(BTC_MINT, gelir / pos["qty"])
            poz_pct = (gelir - 0.01 - pos["cost"]) / pos["cost"] * 100
        except Exception:
            pass                                             # teklif yoksa bu tur zarar kes ölçülemez

    tahmin, model, hata = yz_tahmin(oz, post=post)
    k_yon = kural_yon(oz)
    k, neden = karar(oz, tahmin, bool(pos), poz_pct, paper.killed())
    sonuc = None
    if k == "al":
        p = paper.portfolio()
        boyut = round(min(p["cash"] - NAKIT_REZERV, p["equity"] * POZ_ORAN), 2)
        if boyut < 1.0:
            k, neden = "bekle", "yetersiz nakit"
        else:
            try:
                q = quoter.quote(USDC_MINT, BTC_MINT, int(boyut * 10 ** USDC_DEC))
                etki = q.get("price_impact_pct")
                if etki is not None and etki > MAKS_ETKI_PCT:
                    k, neden = "bekle", f"fiyat etkisi yüksek (%{etki:.2f})"
                else:
                    sonuc = paper.record_buy(f"btc:{int(now)}:al", CUZDAN, BTC_MINT, boyut, q["out_amount"], BTC_DEC, note=neden)
            except Exception as e:
                k, neden = "bekle", f"alış teklifi yok: {type(e).__name__}"
    elif k == "sat":
        try:
            q = quoter.quote(BTC_MINT, USDC_MINT, int(pos["qty_raw"]))
            sonuc = paper.record_sell(f"btc:{int(now)}:sat", CUZDAN, BTC_MINT, q["out_amount"] / 10 ** USDC_DEC, note=neden)
        except Exception as e:
            k, neden = "bekle", f"satış teklifi yok, pozisyon açık kaldı: {type(e).__name__}"

    db.execute("""INSERT INTO btc_tahmin(ts,fiyat,yon,guven,gerekce,kural_yon,ozellik,karar,karar_neden,hedef_ts,model,hata)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (now, oz["fiyat"], tahmin and tahmin["yon"], tahmin and tahmin["guven"], tahmin and tahmin["gerekce"], k_yon,
                json.dumps(oz), k, neden, now + UFUK_SN, model, hata))
    db.commit()
    d = dict(durum="ok", karar=k, neden=neden, tahmin=tahmin, kural_yon=k_yon, ozellik=oz, hata=hata,
             islem=(sonuc or {}).get("decision"))
    try:
        with open(durum_yolu + ".tmp", "w") as f: json.dump(dict(d, ts=now), f, ensure_ascii=False)
        os.replace(durum_yolu + ".tmp", durum_yolu)
    except OSError:
        pass
    return d


def ozet(paper, son=12):
    """API/ekran için karne: portföy, BTC tutma kıyası, YZ ve kural isabeti, son tahminler ve işlemler."""
    db = paper.db
    db.executescript(SEMA)
    p = paper.portfolio()
    son_t = [dict(r) for r in db.execute("SELECT ts, fiyat, yon, guven, gerekce, kural_yon, karar, karar_neden, sonuc_pct, isabet, "
                                         "kural_isabet, hata FROM btc_tahmin ORDER BY id DESC LIMIT ?", (son,))]
    def oran(sutun, kosul=""):
        r = db.execute(f"SELECT COUNT(*), SUM({sutun}) FROM btc_tahmin WHERE {sutun} IS NOT NULL {kosul}").fetchone()
        return dict(n=r[0], isabet_pct=round(r[1] * 100 / r[0], 1) if r[0] else None)
    kiyas_f = paper._get("kiyas_fiyat")
    guncel = son_t[0]["fiyat"] if son_t else None
    kap = [t for t in paper.trades(500) if t["decision"] == "KOPYALANDI" and t["side"] == "sell"]
    pnl = [t["pnl"] or 0 for t in kap]
    return dict(
        acik=acik(), mod="PAPER", varlik="cbBTC (Solana)",
        toplam=round(p["equity"], 2), kz=round(p["pnl"], 2), kz_pct=round(p["pnl"] / paper.start_cash * 100, 2),
        nakit=round(p["cash"], 2),
        pozisyon=[dict(maliyet=round(x["cost"], 2), deger=round(x["qty"] * x["last_price"], 2)) for x in p["positions"]],
        btc_tut_pct=round((guncel / float(kiyas_f) - 1) * 100, 2) if kiyas_f and guncel else None,
        btc_fiyat=guncel,
        yz=oran("isabet"), yz_guclu=oran("isabet", f"AND guven >= {MIN_GUVEN}"), kural=oran("kural_isabet"),
        kapanan=len(pnl), kazanma_pct=round(sum(x > 0 for x in pnl) * 100 / len(pnl), 1) if pnl else None,
        son_tahmin=son_t[0] if son_t else None, tahminler=son_t,
        islemler=[dict(ts=t["ts"], yon=t["side"], pnl=t["pnl"], neden=t["reason"]) for t in paper.trades(20)
                  if t["decision"] == "KOPYALANDI"],
        kurallar=dict(ufuk_saat=UFUK_SN // 3600, min_guven=MIN_GUVEN, zarar_kes_pct=ZARAR_KES_PCT, dusus_kapisi_pct=DUSUS_KAPISI,
                      poz_oran_pct=int(POZ_ORAN * 100)))


def main():
    if not acik():
        print("BTC öngörü kapalı (BTC_ONGORU=1 ve GEMINI_API_KEY gerekli).", flush=True); return 0
    from nexora import gizle as _gizle
    _gizle.kur()
    from nexora.core import Paper
    from nexora.market import JupiterQuoter
    paper = Paper(os.getenv("BTC_DB", "nexora_btc.db"), ekosistem="btc", dagit=False)
    d = calistir(paper, JupiterQuoter())
    t = d.get("tahmin") or {}
    print(f"BTC öngörü: {d.get('durum')} · karar {d.get('karar')} ({d.get('neden')}) · YZ {t.get('yon')} {t.get('guven')} · "
          f"kural {d.get('kural_yon')} · hata {d.get('hata')}", flush=True)
    return 0 if d.get("durum") != "hata" else 1


if __name__ == "__main__":
    sys.exit(main())
