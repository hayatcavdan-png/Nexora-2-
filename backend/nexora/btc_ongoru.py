"""BTC öngörü (PAPER). Saat başı: Binance BTC/USDT 1 saatlik mumlarından özellikler -> Gemini yön tahmini (YUKARI/ASAGI/BELIRSIZ)
-> Solana üzerinde cbBTC için Jupiter teklifiyle SANAL al/sat. Gerçek emir YOK, imza YOK, cüzdan YOK.

Varsayılan KAPALI: BTC_ONGORU=1 ve GEMINI_API_KEY gerekir. Ayrı veritabanı (nexora_btc.db); kopyalama motoruna dokunmaz.
Her tahmin kaydedilir ve UFUK_SN sonra gerçekleşen fiyatla puanlanır. Aynı anda basit bir kural (4 saatlik yön + 24 saat
ortalamasına göre konum) da puanlanır; YZ bu kuralı ve BTC'yi tutmayı yenemezse sistem kanıtlanmış sayılmaz.
Güvenlik: YZ yanıtı okunamazsa ya da ağ hatası olursa alım yapılmaz; zarar kes kuralı YZ'den bağımsız çalışır.
BTC son 4 saatte DUSUS_KAPISI'ndan fazla düştüyse YZ 'yukarı' dese bile alım yapılmaz (rejim kapısı).
Göstergeler (RSI, MACD, Bollinger, EMA, ATR, hacim) btc_gosterge'de hesaplanır; btc_sinama'nın geçmiş sınamasında isabeti
kanıtlanan kurallar ağırlık alır (btc_agirlik.json) ve 'topluluk' skoru oluşturur. YZ bu göstergeleri ve sınama karnesini
görür; topluluk YZ'ye karşı çıkıyorsa alım yapılmaz. YZ, topluluk ve basit kural ayrı ayrı puanlanır."""
import json, math, os, re, sys, time

import requests

from nexora import btc_duygu as D, btc_golge, btc_gosterge as G, btc_haber, yz_xai
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
TOPLULUK_ESIK = 0.2                     # topluluk skoru bu eşiği aşınca yön sayılır
AGIRLIK_YOLU = os.getenv("BTC_AGIRLIK", "btc_agirlik.json")
EK_GOSTERGE = ("bb_genislik_yuzdelik", "bb_genislik_yuzdelik_onceki", "stok_k", "stok_d", "cci20", "adx14", "pdi", "mdi",
               "donchian_ust_pct", "donchian_alt_pct", "supertrend", "obv_egim", "vwap_sapma", "vwap_egim", "mfi14",
               "trend4s_sapma", "trend4s_egim", "trend1g_sapma", "trend1g_egim")

SEMA = """CREATE TABLE IF NOT EXISTS btc_tahmin(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, fiyat REAL, yon TEXT, guven INTEGER,
  gerekce TEXT, kural_yon TEXT, ozellik TEXT, karar TEXT, karar_neden TEXT, hedef_ts REAL, sonuc_fiyat REAL, sonuc_pct REAL,
  isabet INTEGER, kural_isabet INTEGER, model TEXT, hata TEXT);"""
GOC = ("ALTER TABLE btc_tahmin ADD COLUMN topluluk_yon TEXT", "ALTER TABLE btc_tahmin ADD COLUMN topluluk_skor REAL",
       "ALTER TABLE btc_tahmin ADD COLUMN topluluk_isabet INTEGER", "ALTER TABLE btc_tahmin ADD COLUMN haber_yon TEXT",
       "ALTER TABLE btc_tahmin ADD COLUMN haber_isabet INTEGER", "ALTER TABLE btc_tahmin ADD COLUMN uzman_yon TEXT",
       "ALTER TABLE btc_tahmin ADD COLUMN uzman_isabet INTEGER", "ALTER TABLE btc_tahmin ADD COLUMN duygu TEXT")
SINYAL_YON = {1: "YUKARI", -1: "ASAGI", 0: "BELIRSIZ"}


def sema_kur(db):
    db.executescript(SEMA)
    var = {r[1] for r in db.execute("PRAGMA table_info(btc_tahmin)")}
    for g in GOC:
        if g.split()[5] not in var: db.execute(g)
    db.commit()


def acik():
    return os.getenv("BTC_ONGORU") == "1"


# ---------------------------------------------------------------- veri
def mumlar(s=None, limit=500, baslangic_ms=None, timeout=15):
    """BTC/USDT 1 saatlik mumlar: [(acilis_ts, kapanis_ts, kapanis_fiyat, yuksek, dusuk, hacim)] (saniye). Hata: istisna.
    Son eleman henüz kapanmamış mum olabilir; çağıran kapanış zamanına göre süzer."""
    s = s or requests.Session()
    params = {"symbol": "BTCUSDT", "interval": "1h", "limit": limit}
    if baslangic_ms is not None: params["startTime"] = int(baslangic_ms)
    r = s.get(KLINE_URL, params=params, timeout=timeout)
    r.raise_for_status()
    out = []
    for m in r.json():
        try:
            a, y, d, k, h, kts = m[0] / 1000, float(m[2]), float(m[3]), float(m[4]), float(m[5]), m[6] / 1000
        except (TypeError, ValueError, IndexError):
            continue
        if k > 0 and y >= d > 0: out.append((a, kts, k, y, d, h))
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
    """Son KAPANMIŞ mumlardan sayısal özet + teknik göstergeler (2 haneli). En az G.EN_AZ_MUM mum gerekir."""
    if len(mum) < G.EN_AZ_MUM: raise ValueError("yetersiz mum")
    g = G.hesapla(mum)
    y = lambda x, n=2: None if x is None else round(x, n)
    k = [m[2] for m in mum]
    r = lambda n: round((k[-1] / k[-1 - n] - 1) * 100, 2)
    getiriler = [(k[i] / k[i - 1] - 1) * 100 for i in range(len(k) - 24, len(k))]
    ort = sum(getiriler) / len(getiriler)
    oynak = math.sqrt(sum((g - ort) ** 2 for g in getiriler) / len(getiriler))
    sma24 = sum(k[-24:]) / 24
    y24, d24 = max(m[3] for m in mum[-24:]), min(m[4] for m in mum[-24:])
    return dict(fiyat=round(k[-1], 2), r1=r(1), r4=r(4), r24=r(24), r48=r(48) if len(k) > 48 else None,
                oynaklik_1s=round(oynak, 2), sma24_sapma=round((k[-1] / sma24 - 1) * 100, 2),
                aralik_konum=round((k[-1] - d24) / (y24 - d24) * 100, 1) if y24 > d24 else 50.0,
                rsi14=y(g["rsi14"], 1), macd_hist_pct=y(g["macd_hist_pct"], 4), macd_hist_onceki_pct=y(g["macd_hist_onceki_pct"], 4),
                bb_b=y(g["bb_b"]), ema_fark_pct=y(g["ema_fark_pct"], 3), ema50_sapma=y(g["ema50_sapma"]),
                ema50_egim=y(g["ema50_egim"], 3), atr_pct=y(g["atr_pct"], 3), hacim_oran=y(g["hacim_oran"]),
                **{a: y(g[a], 4) for a in EK_GOSTERGE})


def agirlik_yukle(yol=None):
    """btc_sinama çıktısı (yoksa ya da bozuksa None)."""
    try:
        with open(yol or AGIRLIK_YOLU) as f: d = json.load(f)
        return d if isinstance(d.get("agirlik"), dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def topluluk_hesap(oz, sinama, ek_sinyal=None):
    """(sinyaller, skor, yön). Teknik ve duygu kuralları ayrı sınanır; yalnızca KANIT bulunan grubun ağırlıkları oy
    kullanır. Sınama yoksa ya da kanıt yoksa skor 0 (YZ yine de değerleri ve karneyi görür)."""
    sinyal = dict(G.sinyaller(oz), **(ek_sinyal or {}))
    sinama = sinama or {}
    agirlik = dict(sinama.get("agirlik") or {}) if sinama.get("kanit") else {}
    duygu = sinama.get("duygu") or {}
    if duygu.get("kanit"): agirlik.update(duygu.get("agirlik") or {})
    skor = round(G.topluluk(sinyal, agirlik), 3)
    return sinyal, skor, G.yon(skor, TOPLULUK_ESIK)


def kural_yon(oz):
    """Kıyas kuralı (YZ'siz): 4 saatlik yön ve 24 saat ortalamasının üstü/altı aynı yöndeyse o yön."""
    if oz["r4"] > 0 and oz["sma24_sapma"] > 0: return "YUKARI"
    if oz["r4"] < 0 and oz["sma24_sapma"] < 0: return "ASAGI"
    return "BELIRSIZ"


# ---------------------------------------------------------------- YZ
def sinama_ozeti(sinama):
    """YZ'ye verilecek kısa karne: kural başına görülmemiş dönemdeki 'al' isabeti, baz oran ve z puanı."""
    if not sinama: return None
    return dict(kanit=sinama.get("kanit"), ufuk_saat=sinama.get("ufuk_saat"),
                kurallar={k: dict(isabet_al=v["sinama"]["isabet_al"], baz=v["sinama"]["baz_yukari"], z=v["sinama"]["z"],
                                  n=v["sinama"]["n_al"]) for k, v in (sinama.get("kurallar") or {}).items()},
                agirlik=sinama.get("agirlik"),
                duygu=None if not sinama.get("duygu") or sinama["duygu"].get("yetersiz") else dict(
                    kanit=sinama["duygu"].get("kanit"),
                    kurallar={k: dict(isabet_al=v["sinama"]["isabet_al"], baz=v["sinama"]["baz_yukari"], z=v["sinama"]["z"],
                                      n=v["sinama"]["n_al"]) for k, v in (sinama["duygu"].get("kurallar") or {}).items()}))


def istem(oz, sinyal=None, skor=None, sinama=None, duygu=None):
    ek = {}
    if duygu: ek["piyasa_duygusu"] = {k: v for k, v in duygu.items() if k != "kaynaklar"}
    if sinyal is not None: ek["gosterge_sinyalleri"] = sinyal
    if skor is not None: ek["topluluk_skoru"] = skor
    karne = sinama_ozeti(sinama)
    if karne: ek["gecmis_sinama"] = karne
    return ("Sen temkinli bir piyasa analistisin. Aşağıda BTC/USDT'nin 1 saatlik KAPANMIŞ mumlarından hesaplanmış veri var.\n"
            "Alanlar: r1/r4/r24/r48 son 1/4/24/48 saatteki % değişim; oynaklik_1s saatlik getirilerin std sapması; "
            "sma24_sapma fiyatın 24 saatlik ortalamaya % farkı; aralik_konum 24 saatlik dip-zirve aralığında % konum; "
            "rsi14 (30 altı aşırı satım, 70 üstü aşırı alım); macd_hist_pct ve macd_hist_onceki_pct MACD(12,26,9) histogramı "
            "(fiyatın %'si); bb_b Bollinger %B (0 alt bant, 1 üst bant); ema_fark_pct EMA9'un EMA21'e % farkı; "
            "ema50_sapma ve ema50_egim uzun trend; atr_pct ortalama gerçek aralık; hacim_oran son saat hacmi / 24 saat ortalaması; "
            "bb_genislik_yuzdelik Bollinger bant genişliğinin son 100 saatteki yüzdelik sırası (düşük = sıkışma); "
            "stok_k/stok_d Stokastik(14,3); cci20 Emtia Kanal Endeksi (±100 dışı aşırı); adx14 trend gücü (25 üstü güçlü) ve "
            "pdi/mdi yön göstergeleri; donchian_ust_pct/donchian_alt_pct fiyatın önceki 20 saatlik zirve/dibe % uzaklığı "
            "(pozitif üst = kırılım); supertrend (10,3) yönü; obv_egim son 12 saatte hacim ağırlıklı alıcı(+)/satıcı(-) baskısı; "
            "vwap_sapma/vwap_egim 24 saatlik hacim ağırlıklı ortalamaya göre konum ve eğim; mfi14 Para Akışı Endeksi; "
            "trend4s_* 4 saatlik mumlarda EMA21'e göre trend; trend1g_* günlük mumlarda EMA7'ye göre trend.\n"
            "piyasa_duygusu (varsa): fonlama_pct Binance vadeli fonlama oranı (yüksek = kalabalık long); ls_oran/ls_yuzdelik "
            "tüm hesapların long/short oranı ve son 7 gündeki yüzdeliği (aşırı uçlar genelde tersine döner); buyuk_oran ve "
            "buyuk_degisim_4s_pct Binance'teki en büyük trader'ların pozisyon long/short oranı ve 4 saatlik değişimi; "
            "oi_degisim_4s_pct açık pozisyon değişimi; taker_4s agresif alış/satış hacim oranı; korku_acgozluluk 0-100 "
            "(sosyal medya dahil endeks; 25 altı aşırı korku, 75 üstü aşırı açgözlülük); uzman_hl Hyperliquid'de sürekli kârlı "
            "seçilmiş trader'ların şu anki BTC pozisyonları (net_oran +1 hepsi long, -1 hepsi short); haber son 24 saatin "
            "haber ve sosyal medya özeti (duygu -2..+2, arama tabanlı yorum: tek başına karar gerekçesi yapma).\n"
            "gosterge_sinyalleri her kuralın oyu (+1 yukarı, -1 aşağı, 0 fikir yok); topluluk_skoru geçmiş sınamada kanıtlanan "
            "kuralların ağırlıklı oyu (-1..+1, 0 = kanıtlı fikir yok). gecmis_sinama, kuralların GÖRÜLMEMİŞ geçmiş veride 4 saatlik "
            "'al' isabeti (isabet_al) ile o dönemin yükseliş oranını (baz) ve anlamlılığını (z) gösterir: isabeti baz oranı "
            "geçmeyen kurala güvenme.\n"
            "Görev: önümüzdeki 4 saat için BTC'nin yönünü tahmin et. Kanıt zayıfsa ya da göstergeler çelişiyorsa BELIRSIZ de; "
            "yanlış güven zararlıdır. Güveni, sınamada kanıtlanmış kuralların sana katılıp katılmadığına göre ayarla.\n"
            "YALNIZCA şu JSON'u döndür, başka metin yazma: "
            '{"yon": "YUKARI|ASAGI|BELIRSIZ", "guven": 0-100 arası tam sayı, "gerekce": "en fazla 25 kelime Türkçe"}'
            "\n\nVERİ:\n" + json.dumps(dict(oz, **ek), ensure_ascii=False, sort_keys=True))


_TR = str.maketrans({"Ş": "S", "Ğ": "G", "İ": "I", "Ü": "U", "Ö": "O", "Ç": "C"})   # 'AŞAĞI' -> 'ASAGI'
YZ_DENEME = 2                           # 5xx / ağ hatasında bir kez daha dene


def yanit_coz(metin):
    """Model metninden {'yon','guven','gerekce'}; geçersizse None (işlem yapılmaz)."""
    if not metin: return None
    m = re.search(r"\{.*\}", metin, re.S)
    if not m: return None
    try: d = json.loads(m.group(0))
    except ValueError: return None
    if not isinstance(d, dict): return None
    d = {str(k).lower().replace("ü", "u").replace("ö", "o").replace("ç", "c"): v for k, v in d.items()}   # 'güven' -> 'guven'
    yon = str(d.get("yon", "")).strip().upper().translate(_TR).replace("̇", "")
    yon = {"YUKSELIS": "YUKARI", "DUSUS": "ASAGI", "YATAY": "BELIRSIZ", "NOTR": "BELIRSIZ"}.get(yon, yon)
    try: guven = int(round(float(str(d.get("guven")).replace("%", "").replace(",", ".").strip())))
    except (TypeError, ValueError): return None
    if yon not in YONLER or not 0 <= guven <= 100: return None
    return dict(yon=yon, guven=guven, gerekce=str(d.get("gerekce", ""))[:200])


def yz_tahmin(oz, post=None, sinyal=None, skor=None, sinama=None, duygu=None):
    """(tahmin|None, model, hata)."""
    anahtar = os.getenv("GEMINI_API_KEY", "")
    if not anahtar and post is None: return None, yz_xai.MODEL, "GEMINI_API_KEY yok"
    metin_istem, hata = istem(oz, sinyal, skor, sinama, duygu), None
    yedek = os.getenv("YZ_MODEL_YEDEK")                    # 503'te ikinci denemede başka model (isteğe bağlı)
    for deneme in range(YZ_DENEME):
        try:
            y = yz_xai.gemini_cagir(metin_istem, anahtar, post=post, model=yedek if deneme and yedek else None)
        except Exception as e:                              # ağ/HTTP (ör. 503): bekle, bir kez daha dene
            hata = f"{type(e).__name__}: {str(e)[:120]}"
            if deneme + 1 < YZ_DENEME and post is None: time.sleep(10)
            continue
        ham = yz_xai.metin_cek(y)
        t = yanit_coz(ham)
        if t: return t, y.get("model", yz_xai.MODEL), None
        hata = "yanıt okunamadı: " + (ham or "")[:80].replace("\n", " ")
    return None, yz_xai.MODEL, hata


# ---------------------------------------------------------------- karar (saf)
def karar(oz, tahmin, poz_var, poz_pct=None, killed=False, skor=0.0):
    """('al'|'sat'|'bekle', neden). Saf fonksiyon: ağ ve veritabanı yok.
    skor: kanıtlı göstergelerin topluluk skoru; YZ'ye karşı çıkarsa alım yok, aşağı derse (YZ güçlü yukarı değilse) satış."""
    if poz_var and poz_pct is not None and poz_pct <= -ZARAR_KES_PCT:
        return "sat", f"zarar kes (%{poz_pct:.2f})"
    if tahmin is None:
        return "bekle", "YZ tahmini yok"
    guclu = tahmin["guven"] >= MIN_GUVEN
    if poz_var:
        if tahmin["yon"] == "ASAGI" and guclu: return "sat", f"YZ aşağı (güven {tahmin['guven']})"
        if skor <= -TOPLULUK_ESIK and not (tahmin["yon"] == "YUKARI" and guclu):
            return "sat", f"göstergeler aşağı (skor {skor:+.2f})"
        return "bekle", "pozisyon korunuyor"
    if killed: return "bekle", "acil durdurma açık"
    if tahmin["yon"] != "YUKARI" or not guclu: return "bekle", f"YZ {tahmin['yon']} (güven {tahmin['guven']})"
    if oz["r4"] <= DUSUS_KAPISI: return "bekle", f"rejim kapısı: BTC 4 saatte %{oz['r4']:.2f}"
    if skor <= -TOPLULUK_ESIK: return "bekle", f"göstergeler YZ'ye karşı (skor {skor:+.2f})"
    return "al", f"YZ yukarı (güven {tahmin['guven']}, gösterge skoru {skor:+.2f})"


# ---------------------------------------------------------------- puanlama
def _isabet(yon, pct):
    if yon == "YUKARI": return int(pct > 0)
    if yon == "ASAGI": return int(pct < 0)
    return None


def puanla(db, mum, now):
    """Ufku dolmuş tahminleri, hedef zamana kadar kapanmış son mumun fiyatıyla puanlar."""
    n = 0
    for r in db.execute("SELECT id, fiyat, yon, kural_yon, hedef_ts, topluluk_yon, haber_yon, uzman_yon FROM btc_tahmin "
                        "WHERE sonuc_fiyat IS NULL AND hedef_ts <= ?", (now,)).fetchall():
        kap = [m for m in mum if m[1] <= r[4] + 60]
        if not kap or kap[-1][1] < r[4] - 3600: continue      # o ana ait mum elde yok
        f = kap[-1][2]; pct = (f / r[1] - 1) * 100
        db.execute("UPDATE btc_tahmin SET sonuc_fiyat=?, sonuc_pct=?, isabet=?, kural_isabet=?, topluluk_isabet=?, "
                   "haber_isabet=?, uzman_isabet=? WHERE id=?",
                   (f, round(pct, 3), _isabet(r[2], pct), _isabet(r[3], pct), _isabet(r[5], pct), _isabet(r[6], pct),
                    _isabet(r[7], pct), r[0]))
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- çalıştırma
def _poz(paper):
    return paper.position(BTC_MINT)


def calistir(paper, quoter, s=None, post=None, now=None, durum_yolu="btc_durum.json", agirlik_yolu=None, duygu_fn=None,
             haber_post=None):
    """Bir tur. Dönüş: dict(durum, karar, neden, tahmin, ...)."""
    if not acik(): return dict(durum="kapali")
    now = now or time.time()
    db = paper.db
    sema_kur(db)
    try:
        mum = [m for m in mumlar(s) if m[1] <= now]          # yalnızca kapanmış mumlar (yarım hacim/fiyat yok)
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

    sinama = agirlik_yukle(agirlik_yolu)
    duygu, d_sinyal = {}, {}
    try:
        if duygu_fn is not None: duygu = duygu_fn(now, oz["r4"])
        elif s is None: duygu = D.topla(None, now, oz["r4"])[0]       # canlı: Binance vadeli, Korku-Açgözlülük, HL
    except Exception:
        duygu = {}
    haber, haber_hata = btc_haber.getir(paper, now, post=haber_post)
    if haber: duygu["haber"] = {k: haber[k] for k in ("duygu", "ozet", "olaylar") if k in haber}
    if duygu: d_sinyal = D.sinyaller(duygu)
    sinyal, skor, t_yon = topluluk_hesap(oz, sinama, d_sinyal)
    tahmin, model, hata = yz_tahmin(oz, post=post, sinyal=sinyal, skor=skor, sinama=sinama, duygu=duygu or None)
    if haber_hata and not hata: hata = haber_hata
    k_yon = kural_yon(oz)
    k, neden = karar(oz, tahmin, bool(pos), poz_pct, paper.killed(), skor)
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

    db.execute("""INSERT INTO btc_tahmin(ts,fiyat,yon,guven,gerekce,kural_yon,ozellik,karar,karar_neden,hedef_ts,model,hata,
                  topluluk_yon,topluluk_skor,haber_yon,uzman_yon,duygu) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (now, oz["fiyat"], tahmin and tahmin["yon"], tahmin and tahmin["guven"], tahmin and tahmin["gerekce"], k_yon,
                json.dumps(dict(oz, sinyal=sinyal)), k, neden, now + UFUK_SN, model, hata, t_yon, skor,
                SINYAL_YON[d_sinyal["haber"]] if haber else None,
                SINYAL_YON[d_sinyal["uzman_hl"]] if (duygu.get("uzman_hl") or {}).get("n") else None,
                json.dumps(duygu, ensure_ascii=False) if duygu else None))
    db.commit()
    try:
        golge = btc_golge.adim(db, oz["fiyat"], now, k_yon, tahmin, t_yon)
    except Exception:
        golge = None                                         # gölge ölçümü asıl turu asla durdurmaz
    d = dict(durum="ok", karar=k, neden=neden, tahmin=tahmin, kural_yon=k_yon, topluluk_yon=t_yon, topluluk_skor=skor,
             golge=golge,
             duygu=duygu, haber=haber,
             sinyal=sinyal, sinama_var=sinama is not None, ozellik=oz, hata=hata, islem=(sonuc or {}).get("decision"))
    try:
        with open(durum_yolu + ".tmp", "w") as f: json.dump(dict(d, ts=now), f, ensure_ascii=False)
        os.replace(durum_yolu + ".tmp", durum_yolu)
    except OSError:
        pass
    return d


def ozet(paper, son=12, agirlik_yolu=None):
    """API/ekran için karne: portföy, BTC tutma kıyası, YZ / topluluk / kural isabeti, sınama, son tahminler ve işlemler."""
    db = paper.db
    sema_kur(db)
    p = paper.portfolio()
    son_t = [dict(r) for r in db.execute("SELECT ts, fiyat, yon, guven, gerekce, kural_yon, karar, karar_neden, sonuc_pct, isabet, "
                                         "kural_isabet, topluluk_yon, topluluk_skor, topluluk_isabet, hata FROM btc_tahmin ORDER BY id DESC LIMIT ?", (son,))]
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
        topluluk=oran("topluluk_isabet"), sinama=_sinama_karti(agirlik_yukle(agirlik_yolu)),
        haber=oran("haber_isabet"), uzman=oran("uzman_isabet"), duygu_son=_son_duygu(db),
        golge=btc_golge.karne(db),
        kapanan=len(pnl), kazanma_pct=round(sum(x > 0 for x in pnl) * 100 / len(pnl), 1) if pnl else None,
        son_tahmin=son_t[0] if son_t else None, tahminler=son_t,
        son_gecerli=next((t for t in son_t if t.get("yon")), None),
        islemler=[dict(ts=t["ts"], yon=t["side"], pnl=t["pnl"], neden=t["reason"]) for t in paper.trades(20)
                  if t["decision"] == "KOPYALANDI"],
        kurallar=dict(ufuk_saat=UFUK_SN // 3600, min_guven=MIN_GUVEN, zarar_kes_pct=ZARAR_KES_PCT, dusus_kapisi_pct=DUSUS_KAPISI,
                      poz_oran_pct=int(POZ_ORAN * 100)))


def _sinama_karti(s):
    if not s: return None
    t = s.get("topluluk_sinama") or {}
    d = s.get("duygu") or {}
    dt = d.get("topluluk_sinama") or {}
    return dict(ts=s.get("ts"), kanit=s.get("kanit"), getiri_pct=t.get("getiri_pct"), tut_pct=t.get("tut_pct"),
                islem=t.get("islem"), agirlik=s.get("agirlik"), ornek=s.get("ornek"),
                duygu_kanit=d.get("kanit"), duygu_getiri_pct=dt.get("getiri_pct"), duygu_tut_pct=dt.get("tut_pct"),
                duygu_ornek=d.get("ornek"), duygu_yetersiz=bool(d.get("yetersiz")))


def _son_duygu(db):
    r = db.execute("SELECT duygu FROM btc_tahmin WHERE duygu IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if not r: return None
    try: d = json.loads(r[0])
    except ValueError: return None
    u = d.get("uzman_hl") or {}; h = d.get("haber") or {}
    return dict(fonlama_pct=d.get("fonlama_pct"), ls_oran=d.get("ls_oran"), buyuk_oran=d.get("buyuk_oran"),
                korku_acgozluluk=d.get("korku_acgozluluk"), uzman_long=u.get("long"), uzman_short=u.get("short"),
                uzman_net=u.get("net_oran"), haber_duygu=h.get("duygu"), haber_ozet=h.get("ozet"))


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
