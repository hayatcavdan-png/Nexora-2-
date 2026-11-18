"""N19 gölge karar + N20 kontrollü devreye alma (paper).

ModelDosyasi   Model JSON'unu okur ve dosya değişince yeniler. Sürüm, oluşturma zamanı ile dosya özetinden oluşur.
golge_v1_yaz() N19: V1 aday sınıfını ve gerekçesini, varsa değerlendirme olasılığını ve model sürümünü kaydeder.
golge_yaz()    Eski model için N19 kayıt biçimini korur. Durum sorgusu golge_rapor() ile yapılır.
ModelKapisi    N20: paper kopyalamasında filtre. Yalnızca model_filtre.json'da açıkça açıldıysa çalışır.
               Model yoksa/bozuksa filtre UYGULANMAZ (eski davranış: hepsini kopyala) ve durum raporlanır.
               Açmak yalnızca sunucuda komutla (yz_filtre.py ac), kapatmak uygulamadan da yapılabilir (tek dokunuş geri alma).
Gerçek para bu modülden etkilenmez; gerçek emir yalnızca N12 onayıyla."""
import hashlib, json, os, sqlite3, time

from nexora.model import Model
from nexora.olcum import GIRIS_TOLERANS, IZLENEN, pozitif, sayi, tutar_gecerli
from nexora.ozellik import T0_SUTUNLAR, ozellikler, t0_ozellikler

MODEL_YOLU = "yz_model.json"
GOLGE_MODEL_YOLU = "yz_model_v1.json"
FILTRE_YOLU = "model_filtre.json"
GOLGE_SEMA = """CREATE TABLE IF NOT EXISTS golge_karar(event_id TEXT PRIMARY KEY, ts REAL, model_surumu TEXT, olasilik REAL,
  esik REAL, secerdi INTEGER)"""
GOLGE_V1_SEMA = """CREATE TABLE IF NOT EXISTS golge_karar_v1(
  event_id TEXT PRIMARY KEY, ts REAL, model_surumu TEXT, olasilik REAL, esik REAL, sinif TEXT, gerekce TEXT)"""
EN_AZ_GOLGE_GUN = 14
EN_AZ_GOLGE_ETIKET = 100


class ModelDosyasi:
    def __init__(self, yol=MODEL_YOLU, *, golge=False):
        self.yol, self._mtime, self._m = yol, None, None
        self.golge = golge
        self._golge_ts = None

    def yukle(self):
        """(model, esik, surum) ya da None."""
        try:
            mt = os.path.getmtime(self.yol)
        except OSError:
            self._mtime, self._m, self._golge_ts = None, None, None
            return None
        if mt != self._mtime:
            self._mtime = mt
            self._golge_ts = None
            try:
                with open(self.yol) as f: ham = f.read()
                d = json.loads(ham)
                if not isinstance(d, dict) or (d.get("golge_v1") is True and not self.golge):
                    raise ValueError("model dosyası geçersiz veya gölgeye özel")
                zaman = sayi(d.get("olusturma", 0))
                esik = sayi(d["esik"])
                if zaman is None or esik is None or not 0 <= esik <= 1:
                    raise ValueError("model tarihi veya eşiği geçersiz")
                surum = f"{int(zaman)}-{hashlib.sha256(ham.encode()).hexdigest()[:8]}"
                model = Model.yukle(d)
                self._m = (model, esik, surum)
                veri_ts = pozitif(d.get("son_veri_ts"))
                if (d.get("golge_v1") is True and d.get("ufuk") == "kaynak" and "bot_kopyaladi" not in model.oz
                        and veri_ts is not None and veri_ts <= zaman):
                    self._golge_ts = zaman
            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                self._m = None
        return self._m

    def olasilik(self, t0_satir):
        m = self.yukle()
        if m is None: return None
        model, esik, surum = m
        p = model.olasilik([ozellikler({k: v for k, v in t0_satir.items() if k in T0_SUTUNLAR})])[0]
        return dict(olasilik=round(p, 4), esik=esik, surum=surum, secerdi=p >= esik)

    def golge_olasilik(self, olay):
        m = self.yukle()
        if m is None or self._golge_ts is None or self._golge_ts > olay["ts"]:
            return None
        model, esik, surum = m
        p = model.olasilik([t0_ozellikler(olay)])[0]
        return dict(olasilik=p, esik=esik, surum=surum, secerdi=p >= esik)


GOLGE_GEREKCELERI = {
    "risk": ("RİSK-RED", "Kayıtlı güvenlik veya maliyet reddi"),
    "veri": ("VERİ-YETERSİZ", "Teklif, likidite veya zaman bilgisi eksik ya da geçersiz"),
    "model": ("VERİ-YETERSİZ", "Sinyal anında doğrulanmış V1 gölge modeli yok"),
    "esik": ("GÖLGE-İZLE", "Olasılık gölge seçimi eşiğinin altında"),
    "izle": ("GÖLGE-İZLE", "Cüzdanın gözlem kaydı"),
    "aday": ("PAPER-ADAY", "Gölge olasılığı seçim eşiğini karşıladı"),
}


def golge_gerekcesi(olay, karar):
    gerekce = olay.get("gerekce")
    if isinstance(gerekce, str) and olay.get("karar") == "REDDEDİLDİ" and gerekce.startswith(
            ("token REDDEDİLDİ:", "fiyat etkisi yüksek", "al-sat kaybı yüksek", "teklif tutarsız")):
        return "risk"
    t0, ts = pozitif(olay.get("ts")), pozitif(olay.get("kayit_ts"))
    gecikme = sayi(olay.get("gecikme_sn"))
    satis = pozitif(olay.get("kaynak_vade"))
    if (t0 is None or ts is None or not t0 <= ts <= t0 + GIRIS_TOLERANS
            or not tutar_gecerli(olay) or pozitif(olay.get("tb_likidite")) is None
            or (satis is not None and satis <= ts)
            or gecikme is None or gecikme < 0 or gecikme >= 1e9
            or (isinstance(gerekce, str) and gerekce.startswith("token BİLİNMİYOR:"))):
        return "veri"
    if gerekce == IZLENEN:
        return "izle"
    if karar is None:
        return "model"
    return "aday" if karar["secerdi"] else "esik"


def golge_v1_yaz(db, olay, model):
    try:
        karar = None if model is None else model.golge_olasilik(olay)
    except Exception:
        karar = None     # Gölge modeli arızalansa da N16 ölçümü kaydedilir.
    kod = golge_gerekcesi(olay, karar)
    karar = karar or {}
    db.execute("INSERT OR IGNORE INTO golge_karar_v1 VALUES(?,?,?,?,?,?,?)",
               (olay["event_id"], olay["kayit_ts"], karar.get("surum"), karar.get("olasilik"),
                karar.get("esik"), GOLGE_GEREKCELERI[kod][0], kod))


def golge_yaz(db, event_id, ts, karar):
    """N19: tek sinyalin gölge kararını etiket veritabanına yazar (db: açık sqlite bağlantısı)."""
    db.execute(GOLGE_SEMA)
    db.execute("INSERT OR IGNORE INTO golge_karar VALUES(?,?,?,?,?,?)",
               (event_id, ts, karar["surum"], karar["olasilik"], karar["esik"], int(karar["secerdi"])))


def golge_rapor(etiket_db, ufuk="kaynak"):
    """Gölge kararlar gerçekleşen etiketle: seçilenlerin ve hepsinin ortalama getirisi, kalibrasyon, kayma işareti."""
    if not os.path.exists(etiket_db): return dict(n=0)
    c = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        rows = None
        for sorgu in ("""SELECT g.*, s.getiri_pct, o.gerekce FROM golge_karar g
                     LEFT JOIN etiket_sonuc s ON s.event_id=g.event_id AND s.ufuk=? AND s.hata IS NULL
                     LEFT JOIN etiket_olay o ON o.event_id=g.event_id ORDER BY g.ts""",
                      """SELECT g.*, s.getiri_pct FROM golge_karar g
                     LEFT JOIN etiket_sonuc s ON s.event_id=g.event_id AND s.ufuk=? AND s.hata IS NULL ORDER BY g.ts"""):
            try: rows = [dict(r) for r in c.execute(sorgu, (ufuk,))]; break
            except sqlite3.OperationalError: continue
        if rows is None: return dict(n=0)
    finally:
        c.close()
    if not rows: return dict(n=0)
    rows = [r for r in rows if sayi(r["ts"]) is not None and sayi(r["olasilik"]) is not None and 0 <= r["olasilik"] <= 1]
    if not rows: return dict(n=0)
    et = [r for r in rows if sayi(r["getiri_pct"]) is not None]
    sec = [r for r in et if r["secerdi"]]
    ort = lambda v: round(sum(v) / len(v), 3) if v else None
    gun = (rows[-1]["ts"] - rows[0]["ts"]) / 86400
    # kayma: son yedi gündeki seçim oranı ile ilk yedi gündeki arasındaki fark
    ilk = [r["secerdi"] for r in rows if r["ts"] < rows[0]["ts"] + 7 * 86400]
    son = [r["secerdi"] for r in rows if r["ts"] > rows[-1]["ts"] - 7 * 86400]
    kayma = None if gun < 14 or not ilk or not son else round(sum(son) / len(son) - sum(ilk) / len(ilk), 3)
    kalib = []
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        b = [r for r in et if lo <= r["olasilik"] < lo + 0.2 or (lo == 0.8 and r["olasilik"] == 1.0)]
        if b: kalib.append(dict(aralik=f"{lo:.1f}-{lo + 0.2:.1f}", n=len(b), tahmin=ort([r["olasilik"] for r in b]),
                               gercek=round(sum(1 for r in b if r["getiri_pct"] > 0) / len(b), 3)))
    return dict(n=len(rows), etiketli=len(et), gun=round(gun, 1), surumler=sorted({r["model_surumu"] for r in rows}),
                secim_orani=round(sum(r["secerdi"] for r in rows) / len(rows), 3),
                hepsi_ort=ort([r["getiri_pct"] for r in et]), secili_ort=ort([r["getiri_pct"] for r in sec]),
                secilmeyen_ort=ort([r["getiri_pct"] for r in et if not r["secerdi"]]), kayma=kayma, kalibrasyon=kalib,
                # kopyalanan cüzdanlar (gölge havuz/izlenen hariç): canlı filtre yalnızca bunlara uygulanır
                kopya=(lambda k: dict(etiketli=len(k), secilen=sum(1 for r in k if r["secerdi"]), hepsi_ort=ort([r["getiri_pct"] for r in k]),
                                      secili_ort=ort([r["getiri_pct"] for r in k if r["secerdi"]]),
                                      secilmeyen_ort=ort([r["getiri_pct"] for r in k if not r["secerdi"]])))(
                    [r for r in et if r.get("gerekce") != "cüzdan yalnızca izleniyor"]),
                yeterli=gun >= EN_AZ_GOLGE_GUN and len(et) >= EN_AZ_GOLGE_ETIKET)


class ModelKapisi:
    """N20: kopyalama filtresi. izin() -> None (filtre devre dışı) ya da karar sözlüğü (secerdi False ise alım yapılmaz)."""
    def __init__(self, model=None, ayar_yolu=FILTRE_YOLU, bilgi=None, cuzdanlar=None, clock=time.time):
        self.model = model or ModelDosyasi()
        self.ayar_yolu, self.bilgi, self.cuzdanlar, self.clock = ayar_yolu, bilgi, cuzdanlar or {}, clock

    def ayar(self):
        try:
            with open(self.ayar_yolu) as f: d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def acik(self): return bool(self.ayar().get("acik"))

    def durum(self):
        a = self.ayar(); m = self.model.yukle()
        return dict(acik=bool(a.get("acik")), acilis=a.get("ts"), model=None if m is None else m[2],
                    esik=None if m is None else m[1], etkin=bool(a.get("acik")) and m is not None)

    def izin(self, wallet, token, gecikme_sn, giris_etki, al_sat_kaybi_pct):
        if not self.acik(): return None
        g = time.gmtime(self.clock())
        satir = dict(wallet=wallet, token=token, gecikme_sn=gecikme_sn, karar="KOPYALANDI", saat_utc=g.tm_hour, gun=g.tm_wday,
                     giris_etki=giris_etki, al_sat_kaybi_pct=al_sat_kaybi_pct, cuzdan=json.dumps(self.cuzdanlar.get(wallet) or {}))
        if self.bilgi is not None:
            try:
                b = self.bilgi.fetch(token, now=self.clock())
                satir.update(tb_yas_sn=b.get("yas_sn"), tb_likidite=b.get("likidite"), tb_mcap=b.get("mcap"), tb_sahip=b.get("sahip"),
                             tb_organik=b.get("organik"), tb_top_pct=b.get("top_pct"), tb_dev_pct=b.get("dev_pct"), tb_sus=b.get("sus"))
            except Exception:
                pass                                          # eksik özellik: model eğitimdeki medyanla doldurur
        return self.model.olasilik(satir)                     # model yoksa None: filtre uygulanmaz


def filtre_ac(golge, ayar_yolu=FILTRE_YOLU, zorla=False, now=None):
    """Filtreyi açar. N19 kabulü (≥14 gün, ≥100 etiketli gölge karar, seçilenler hepsinden iyi, belirgin kayma yok) şart."""
    if not zorla:
        if not golge.get("yeterli"): raise ValueError(f"gölge dönemi yetersiz: {golge.get('gun', 0)} gün, {golge.get('etiketli', 0)} etiketli "
                                                      f"(gerekli {EN_AZ_GOLGE_GUN} gün, {EN_AZ_GOLGE_ETIKET} etiket)")
        if golge.get("secili_ort") is None or golge["secili_ort"] <= (golge.get("hepsi_ort") or 0):
            raise ValueError("gölgede model seçimleri 'hepsini kopyala'dan iyi değil")
        if golge.get("kayma") is not None and abs(golge["kayma"]) > 0.25: raise ValueError(f"model kayması yüksek ({golge['kayma']})")
    _yaz(ayar_yolu, dict(acik=True, ts=now or time.time(), zorla=bool(zorla)))


def filtre_kapat(ayar_yolu=FILTRE_YOLU, kaynak="komut", now=None):
    _yaz(ayar_yolu, dict(acik=False, ts=now or time.time(), kapatan=kaynak))


def _yaz(yol, d):
    tmp = yol + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f)
    os.replace(tmp, yol)
