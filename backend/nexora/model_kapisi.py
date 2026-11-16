"""N19 gölge karar + N20 kontrollü devreye alma (paper).

ModelDosyasi   yz_model.json'u (yalnızca N18'de kabul edilmiş model yazılır) okur; dosya değişince kendiliğinden yeniler.
               Sürüm = dosyanın oluşturma zamanı + özet; her karar bu sürümle kaydedilir.
golge_yaz()    N19: etiketlenen HER sinyal için modelin olasılığı ve "seçerdim/seçmezdim" kararı etiket veritabanına yazılır.
               İşlemlere dokunmaz. Gerçekleşen etiketle karşılaştırma: golge_rapor().
ModelKapisi    N20: paper kopyalamasında filtre. Yalnızca model_filtre.json'da açıkça açıldıysa çalışır.
               Model yoksa/bozuksa filtre UYGULANMAZ (eski davranış: hepsini kopyala) ve durum raporlanır.
               Açmak yalnızca sunucuda komutla (yz_filtre.py ac), kapatmak uygulamadan da yapılabilir (tek dokunuş geri alma).
Gerçek para bu modülden etkilenmez; gerçek emir yalnızca N12 onayıyla."""
import hashlib, json, os, sqlite3, time

from nexora.model import Model
from nexora.ozellik import T0_SUTUNLAR, ozellikler

MODEL_YOLU = "yz_model.json"
FILTRE_YOLU = "model_filtre.json"
GOLGE_SEMA = """CREATE TABLE IF NOT EXISTS golge_karar(event_id TEXT PRIMARY KEY, ts REAL, model_surumu TEXT, olasilik REAL,
  esik REAL, secerdi INTEGER)"""
EN_AZ_GOLGE_GUN = 14
EN_AZ_GOLGE_ETIKET = 100


class ModelDosyasi:
    def __init__(self, yol=MODEL_YOLU):
        self.yol, self._mtime, self._m = yol, None, None

    def yukle(self):
        """(model, esik, surum) ya da None."""
        try:
            mt = os.path.getmtime(self.yol)
        except OSError:
            self._mtime, self._m = None, None; return None
        if mt != self._mtime:
            self._mtime = mt
            try:
                with open(self.yol) as f: ham = f.read()
                d = json.loads(ham)
                surum = f"{int(d.get('olusturma', 0))}-{hashlib.sha256(ham.encode()).hexdigest()[:8]}"
                self._m = (Model.yukle(d), float(d["esik"]), surum)
            except (OSError, ValueError, KeyError, TypeError):
                self._m = None
        return self._m

    def olasilik(self, t0_satir):
        m = self.yukle()
        if m is None: return None
        model, esik, surum = m
        p = model.olasilik([ozellikler({k: v for k, v in t0_satir.items() if k in T0_SUTUNLAR})])[0]
        return dict(olasilik=round(p, 4), esik=esik, surum=surum, secerdi=p >= esik)


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
        try:
            rows = [dict(r) for r in c.execute("""SELECT g.*, s.getiri_pct FROM golge_karar g
                     LEFT JOIN etiket_sonuc s ON s.event_id=g.event_id AND s.ufuk=? AND s.hata IS NULL ORDER BY g.ts""", (ufuk,))]
        except sqlite3.OperationalError:
            return dict(n=0)
    finally:
        c.close()
    if not rows: return dict(n=0)
    et = [r for r in rows if r["getiri_pct"] is not None]
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
