"""N17 · Özellik seti ve veri kalitesi.

Kural: özellikler YALNIZCA alım anında (t0) bilinen bilgilerden üretilir. Bu modül yalnızca etiket_olay satırını
okur; sonuç tablosuna (etiket_sonuc) erişmez. Etiketler ayrı bir fonksiyonla, ayrıca okunur.
Sızıntı testleri: tests/test_yz.py (izinli sütun listesi + sonuçları karıştırınca özelliklerin değişmemesi)."""
import json, math, os, sqlite3

# Alım anında bilinen, özellik üretiminde kullanılmasına izin verilen etiket_olay sütunları.
T0_SUTUNLAR = ("event_id", "ts", "wallet", "token", "gecikme_sn", "karar", "gerekce", "saat_utc", "gun", "giris_etki",
               "al_sat_kaybi_pct", "tb_yas_sn", "tb_likidite", "tb_mcap", "tb_sahip", "tb_organik", "tb_top_pct",
               "tb_dev_pct", "tb_sus", "cuzdan", "durum", "teyit")

TUTARSIZ_ESIK = -2.0

OZELLIKLER = ["log_gecikme", "al_sat_kaybi", "giris_etki", "log_likidite", "log_yas_saat", "log_mcap", "log_sahip",
              "organik", "top_pay", "dev_pay", "supheli", "c_kazanma", "c_kar_faktoru", "c_ort_getiri", "c_skor",
              "c_dusus", "c_sifir_tur", "saat_sin", "saat_cos", "bot_kopyaladi", "log_teyit",
              # 20.11 (dış araştırma + teşhis [14]/[15]): cüzdanın giriş hızı, ileriye dönük geçmişi, teyidin bağımsızlığı
              "c_hiz_log", "c_gecmis_n_log", "c_gecmis_ort", "teyit_bagimsiz_log", "teyit_ayni_blok"]
GECMIS_OZ = ("c_hiz_log", "c_gecmis_n_log", "c_gecmis_ort", "teyit_bagimsiz_log", "teyit_ayni_blok")
GECMIS_EN_AZ = 3              # c_gecmis_ort için en az bu kadar sonuçlanmış önceki sinyal
AYNI_BLOK_SN = 1.0


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _log(v, olcek=1.0):
    x = _f(v)
    return None if x is None or x < 0 else math.log1p(x / olcek)


def ozellikler(satir):
    """Tek bir etiket_olay satırından özellik sözlüğü (eksik değer: None)."""
    izinsiz = set(satir) - set(T0_SUTUNLAR) - {"sig", "block_time", "giris_usdc", "qty_raw", "hata"}
    if izinsiz: raise ValueError(f"t0 dışı sütun özelliğe giremez: {sorted(izinsiz)}")
    try: c = json.loads(satir.get("cuzdan") or "{}")
    except ValueError: c = {}
    saat = _f(satir.get("saat_utc"))
    kf = _f(c.get("kar_faktoru"))
    return dict(
        log_gecikme=_log(satir.get("gecikme_sn")), al_sat_kaybi=_f(satir.get("al_sat_kaybi_pct")), giris_etki=_f(satir.get("giris_etki")),
        log_likidite=_log(satir.get("tb_likidite"), 1000), log_yas_saat=_log(satir.get("tb_yas_sn"), 3600),
        log_mcap=_log(satir.get("tb_mcap"), 1000), log_sahip=_log(satir.get("tb_sahip")),
        organik=_f(satir.get("tb_organik")), top_pay=_f(satir.get("tb_top_pct")), dev_pay=_f(satir.get("tb_dev_pct")),
        supheli=_f(satir.get("tb_sus")),
        c_kazanma=_f(c.get("kazanma_orani")), c_kar_faktoru=None if kf is None else min(kf, 10.0), c_ort_getiri=_f(c.get("ort_getiri")),
        c_skor=_f(c.get("skor")), c_dusus=_f(c.get("dusus_kazanc_orani")), c_sifir_tur=_f(c.get("sifir_tur_orani")),
        saat_sin=None if saat is None else math.sin(2 * math.pi * saat / 24),
        saat_cos=None if saat is None else math.cos(2 * math.pi * saat / 24),
        # gölge havuz/izlenen cüzdan: bot kuralları hiç sorulmadı -> bilinmiyor (0 yazmak 'izlenen' bilgisini sızdırırdı)
        bot_kopyaladi=None if satir.get("gerekce") == "cüzdan yalnızca izleniyor" else (1.0 if satir.get("karar") == "KOPYALANDI" else 0.0),
        log_teyit=_log(satir.get("teyit")),                     # 15 dk içinde aynı token'ı alan farklı cüzdan sayısı (t0'da bilinir)
    )


def gecmis_ozellikler(c, wallet, token, ts, block_time=None, ufuk="kaynak", pencere=900):
    """Yalnızca t0'dan ÖNCE bilinenlerden: cüzdanın önceki sinyallerindeki medyan token yaşı (giriş hızı), sonucu t0'dan
    önce belli olmuş önceki sinyallerinin sayısı ve ortalama getirisi (ileriye dönük ölçüm), son 15 dk'da aynı token'ı
    alan diğer cüzdanlardan farklı zamanda (bağımsız) ve aynı blokta (bağlı olabilir) alanların sayısı.
    Eğitim (veri_seti) ve canlı gölge karar (model_kapisi) AYNI fonksiyonu kullanır: eğitim/canlı farkı olmaz."""
    yas = [r[0] for r in c.execute("""SELECT tb_yas_sn FROM etiket_olay WHERE wallet=? AND ts<? AND tb_yas_sn IS NOT NULL
                                      ORDER BY ts DESC LIMIT 50""", (wallet, ts))]
    yas.sort()
    hiz = None if not yas else math.log1p(max(0.0, yas[len(yas) // 2]) / 3600)
    g = [r[0] for r in c.execute("""SELECT s.getiri_pct FROM etiket_sonuc s JOIN etiket_olay o ON o.event_id = s.event_id
                                    WHERE o.wallet=? AND o.ts<? AND s.ufuk=? AND s.ts<? AND s.getiri_pct IS NOT NULL
                                    ORDER BY o.ts DESC LIMIT 30""", (wallet, ts, ufuk, ts))]
    bag, ayni = set(), set()
    for w, bt in c.execute("""SELECT wallet, block_time FROM etiket_olay WHERE token=? AND wallet!=? AND ts>=? AND ts<=?""",
                           (token, wallet, ts - pencere, ts)):
        (ayni if bt is not None and block_time is not None and abs(bt - block_time) <= AYNI_BLOK_SN else bag).add(w)
    return dict(c_hiz_log=hiz, c_gecmis_n_log=math.log1p(len(g)),
                c_gecmis_ort=None if len(g) < GECMIS_EN_AZ else max(-100.0, min(200.0, sum(g) / len(g))),
                teyit_bagimsiz_log=math.log1p(len(bag - ayni)), teyit_ayni_blok=float(len(ayni)))


def _teyit_doldur(olaylar, db_path, pencere=900):
    """'teyit' sütunu eklenmeden önceki satırlar için aynı tanımla geriye doldurur: o ana kadar (t0 dahil, öncesi 15 dk)
    aynı token'ı alan farklı cüzdan sayısı. Yalnızca geçmiş satırlar kullanılır (sızıntı yok)."""
    eksik = [o for o in olaylar.values() if o.get("teyit") is None]
    if not eksik: return
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try: tum = c.execute("SELECT ts, wallet, token FROM etiket_olay").fetchall()
    finally: c.close()
    tok = {}
    for ts, w, t in tum: tok.setdefault(t, []).append((ts, w))
    for o in eksik:
        o["teyit"] = 1 + len({w for ts, w in tok.get(o["token"], ()) if w != o["wallet"] and o["ts"] - pencere <= ts <= o["ts"]})


def veri_seti(db_path, ufuk="kaynak"):
    """[(ts, event_id, wallet, özellikler, getiri_pct)] zamana göre sıralı; yalnızca etiketi olan örnekler."""
    if not os.path.exists(db_path): return []
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        sutunlar = ", ".join(T0_SUTUNLAR)
        olaylar = {r["event_id"]: dict(r) for r in c.execute(f"SELECT {sutunlar}, block_time FROM etiket_olay WHERE durum != 'giris_yok'")}
        etiket = {r["event_id"]: r["getiri_pct"] for r in c.execute(
            "SELECT event_id, getiri_pct FROM etiket_sonuc WHERE ufuk=? AND getiri_pct IS NOT NULL", (ufuk,))}
        # Tutarsız teklifle (al-sat 'kazancı' > %2) başlayan örnekler dışarıda: etiketleri gerçekleşemeyecek kârla şişer.
        _teyit_doldur(olaylar, db_path)
        out = []
        for e, o in olaylar.items():
            if e not in etiket or (o.get("al_sat_kaybi_pct") is not None and o["al_sat_kaybi_pct"] < TUTARSIZ_ESIK): continue
            oz = ozellikler(o); oz.update(gecmis_ozellikler(c, o["wallet"], o["token"], o["ts"], o.get("block_time"), ufuk))
            out.append((o["ts"], e, o["wallet"], oz, etiket[e]))
    finally:
        c.close()
    out.sort(key=lambda x: x[0])
    return out


TEMEL_CIZGILER = {
    "hepsini kopyala": lambda o: True,
    "botun kararı (şu anki kurallar)": lambda o: o["bot_kopyaladi"] == 1.0,
    "al-sat ≤%6 ve likidite ≥50 bin $": lambda o: (o["al_sat_kaybi"] is not None and o["al_sat_kaybi"] <= 6
                                                    and o["log_likidite"] is not None and o["log_likidite"] >= math.log1p(50)),
    "organik skor ≥30": lambda o: o["organik"] is not None and o["organik"] >= 30,
}


def temel_cizgiler(veri):
    out = []
    for ad, kural in TEMEL_CIZGILER.items():
        g = [y for _, _, _, o, y in veri if kural(o)]
        out.append(dict(yontem=ad, n=len(g), ort_getiri=round(sum(g) / len(g), 3) if g else None,
                        kazanan_pct=round(100 * sum(1 for y in g if y > 0) / len(g), 1) if g else None))
    return out


def kalite(veri):
    n = len(veri)
    eksik = {k: round(100 * sum(1 for *_, o, _ in veri if o[k] is None) / n, 1) for k in OZELLIKLER} if n else {}
    cuz = {}
    for _, _, w, _, _ in veri: cuz[w] = cuz.get(w, 0) + 1
    gun = {}
    for ts, *_ in veri:
        g = int(ts // 86400); gun[g] = gun.get(g, 0) + 1
    return dict(n=n, kazanan_pct=round(100 * sum(1 for *_, y in veri if y > 0) / n, 1) if n else None,
                eksik_pct=eksik, cuzdan_sayisi=len(cuz), en_cok_cuzdan_payi=round(100 * max(cuz.values()) / n, 1) if n else None,
                gun_sayisi=len(gun))
