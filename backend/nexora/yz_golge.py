"""Gemini gölge kararı (salt okunur kayıt). Her etiketli sinyal için modele "AL" ya da "ATLA" sorulur ve
sonuç golge_llm tablosuna yazılır; gerçek kararla karşılaştırma yalnızca raporda yapılır.

- Sinyal yolunu, kopyalama kararını ve işlemleri ETKİLEMEZ: ayrı toplu iş, çalıştırma başına üst sınırlı.
- Model yalnızca KARAR ANINDA bilinen alanları görür (sonuç alanları sapma/getiri dışarıda bırakılır).
- Açık değilse (YZ_GOLGE=1 ve GEMINI_API_KEY gerekli) hiçbir ağ çağrısı yapılmaz.
"""
import os, sqlite3, time

from nexora import yz_xai

SEMA = """CREATE TABLE IF NOT EXISTS golge_llm(event_id TEXT PRIMARY KEY, ts REAL, model TEXT, oneri TEXT,
  ham TEXT, hata TEXT)"""
ALANLAR = ("karar", "gerekce", "giris_usdc", "giris_etki", "al_sat_kaybi_pct", "tb_yas_sn", "tb_likidite",
           "tb_mcap", "tb_sahip", "tb_organik", "tb_top_pct", "tb_dev_pct", "tb_sus", "saat_utc", "gun")
CALISTIR_UST = 50          # tek çalıştırmada en fazla sinyal (maliyet tavanı)


def acik():
    return os.getenv("YZ_GOLGE") == "1" and bool(os.getenv("GEMINI_API_KEY", ""))


def istem(olay):
    """Karar anı alanları + net soru. Cüzdan/token adresi gönderilmez."""
    satirlar = [f"{a}: {olay.get(a)}" for a in ALANLAR if olay.get(a) is not None]
    return ("Bir kopyalama sistemi bu sinyali aldı. Yalnızca aşağıdaki karar anı bilgilerine göre bu işlemi "
            "kopyalamalı mı? Yanıtın TEK KELİME olsun: AL ya da ATLA.\n" + "\n".join(satirlar))


def oneri_cozumle(metin):
    """İlk kelimeyi AL/ATLA olarak yorumlar; diğerleri 'belirsiz'."""
    if not metin: return "belirsiz"
    ilk = metin.strip().split()[0].strip(".,:;!").upper() if metin.strip() else ""
    return ilk if ilk in ("AL", "ATLA") else "belirsiz"


def calistir(etiket_db, limit=CALISTIR_UST, post=None, now=None):
    """Kayıtsız etiketli sinyalleri işler. Dönüş: dict(islenen, hata, model). Kapalıysa hiçbir şey yapmaz."""
    if not acik() and post is None:
        return {"durum": "kapali", "islenen": 0}
    anahtar = os.getenv("GEMINI_API_KEY", "")
    now = time.time() if now is None else now
    db = sqlite3.connect(etiket_db)
    try:
        db.execute(SEMA)
        db.row_factory = sqlite3.Row
        sec = db.execute(f"""SELECT o.* FROM etiket_olay o LEFT JOIN golge_llm g ON g.event_id=o.event_id
                             WHERE g.event_id IS NULL ORDER BY o.ts LIMIT ?""", (int(limit),)).fetchall()
        islenen = 0
        hata_ilk = None
        for r in sec:
            olay = dict(r)
            try:
                yanit = yz_xai.gemini_cagir(istem(olay), anahtar, post=post)
                ham = yz_xai.metin_cek(yanit)
                model = yanit.get("model", yz_xai.MODEL)
            except Exception as ex:
                # Başarısız çağrı kaydedilmez: sonraki çalıştırmada yeniden denenir.
                # Ardışık hata gelirse döngü durur (kota/anahtar sorununda boşuna çağrı yapılmaz).
                hata_ilk = f"{type(ex).__name__}: {str(ex)[:200]}"
                break
            db.execute("INSERT OR IGNORE INTO golge_llm VALUES(?,?,?,?,?,?)",
                       (olay["event_id"], now, model, oneri_cozumle(ham), (ham or "")[:200], None))
            islenen += 1
        db.commit()
        if hata_ilk:
            return {"durum": "hata", "islenen": islenen, "hata_ilk": hata_ilk, "model": yz_xai.MODEL}
        return {"durum": "ok", "islenen": islenen, "model": yz_xai.MODEL}
    finally:
        db.close()


def rapor(etiket_db, ufuk="kaynak"):
    """Gemini'nin AL dediği sinyallerle gerçek kopyalama kararını yan yana koyar (sonuç: getiri_pct)."""
    db = sqlite3.connect(etiket_db)
    try:
        db.execute(SEMA)
        satir = db.execute(f"""SELECT g.oneri, o.karar, s.getiri_pct FROM golge_llm g
            JOIN etiket_olay o ON o.event_id=g.event_id
            LEFT JOIN etiket_sonuc s ON s.event_id=g.event_id AND s.ufuk=?
            WHERE s.getiri_pct IS NOT NULL""", (ufuk,)).fetchall()
    finally:
        db.close()
    ort = lambda v: round(sum(v) / len(v), 2) if v else None
    al = [g for o, k, g in satir if o == "AL"]
    atla = [g for o, k, g in satir if o == "ATLA"]
    return {"n": len(satir), "gemini_al_n": len(al), "gemini_al_ort": ort(al),
            "gemini_atla_n": len(atla), "gemini_atla_ort": ort(atla), "hepsi_ort": ort([g for *_, g in satir]),
            "yeterli": len(satir) >= 100}


if __name__ == "__main__":                       # zamanlayıcı: python3 -m nexora.yz_golge
    import json
    sonuc = calistir(os.getenv("ETIKET_DB", "nexora_etiket.db"))
    print(json.dumps(sonuc, ensure_ascii=False))
