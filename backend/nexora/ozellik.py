"""N17 · Özellik seti ve veri kalitesi.

Kural: özellikler YALNIZCA alım anında (t0) bilinen bilgilerden üretilir. Bu modül yalnızca etiket_olay satırını
okur; sonuç tablosuna (etiket_sonuc) erişmez. Etiketler ayrı bir fonksiyonla, ayrıca okunur.
Sızıntı testleri: tests/test_yz.py (izinli sütun listesi + sonuçları karıştırınca özelliklerin değişmemesi)."""
import json
import math
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from nexora.olcum import (IZLENEN, TEYIT_SN, UFUKLAR, etiket_sonucu, pozitif, salt_okunur, sayi as _f, zaman)

# Alım anında bilinen, özellik üretiminde kullanılmasına izin verilen etiket_olay sütunları.
T0_SUTUNLAR = ("event_id", "ts", "wallet", "token", "gecikme_sn", "karar", "gerekce", "saat_utc", "gun", "giris_etki",
               "al_sat_kaybi_pct", "tb_yas_sn", "tb_likidite", "tb_mcap", "tb_sahip", "tb_organik", "tb_top_pct",
               "tb_dev_pct", "tb_sus", "cuzdan", "durum", "teyit")

OZELLIKLER = ["log_gecikme", "al_sat_kaybi", "giris_etki", "log_likidite", "log_yas_saat", "log_mcap", "log_sahip",
              "organik", "top_pay", "dev_pay", "supheli", "c_kazanma", "c_kar_faktoru", "c_ort_getiri", "c_skor",
              "c_dusus", "c_sifir_tur", "saat_sin", "saat_cos", "bot_kopyaladi", "log_teyit"]


def _log(v, olcek=1.0):
    x = _f(v)
    return None if x is None or x < 0 else math.log1p(x / olcek)


def ozellikler(satir):
    """Tek bir etiket_olay satırından özellik sözlüğü (eksik değer: None)."""
    izinsiz = set(satir) - set(T0_SUTUNLAR) - {"sig", "block_time", "giris_usdc", "qty_raw", "hata"}
    if izinsiz: raise ValueError(f"t0 dışı sütun özelliğe giremez: {sorted(izinsiz)}")
    try: c = json.loads(satir.get("cuzdan") or "{}")
    except (TypeError, ValueError): c = {}
    if not isinstance(c, dict): c = {}
    saat = _f(satir.get("saat_utc"))
    if saat is not None and not 0 <= saat < 24: saat = None
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


def bot_karari(olay):
    if olay.get("gerekce") == IZLENEN:
        return None
    return {"KOPYALANDI": 1.0, "REDDEDİLDİ": 0.0}.get(olay.get("karar"))


TOKEN_ALANLARI = ("tb_yas_sn", "tb_likidite", "tb_mcap", "tb_sahip", "tb_organik", "tb_top_pct", "tb_dev_pct", "tb_sus")


def t0_ozellikler(olay):
    """N18/N19 girdisi. Kaynak zamanı kanıtlanmış verileri ve algılama anındaki alanları kullanır."""
    t0 = zaman(olay.get("ts"))
    alan = {}
    if t0 is not None and olay.get("olcum_v") == 1:
        gecikme = _f(olay.get("gecikme_sn"))
        alan.update(gecikme_sn=gecikme if gecikme is not None and 0 <= gecikme < 1e9 else None,
                    saat_utc=time.gmtime(t0).tm_hour, teyit=olay.get("teyit"))
        once = pozitif(olay.get("t0_token_ts"))
        if once is not None and t0 - TEYIT_SN <= once < t0:
            try:
                anlik = json.loads(olay.get("t0_token") or "{}")
            except (ValueError, TypeError):
                anlik = {}
            if isinstance(anlik, dict):
                alan.update({k: anlik.get(k) for k in TOKEN_ALANLARI})
    o = ozellikler(alan)
    o["bot_kopyaladi"] = None
    return o


@dataclass
class Sinyal:
    olay: dict
    etiketler: dict
    golge: dict | None

    @property
    def ts(self):
        return zaman(self.olay.get("ts"))

    @property
    def token(self):
        return self.olay.get("token")

    @property
    def wallet(self):
        return self.olay.get("wallet")


def sinyalleri_oku(db_path):
    """Aynı SQLite okuma anında olayları ID üzerinden sonuç ve N19 kaydıyla birleştirir."""
    if not db_path or not Path(db_path).exists():
        return [], 0
    c = salt_okunur(db_path)
    c.row_factory = sqlite3.Row
    try:
        c.execute("BEGIN")
        tablolar = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "etiket_olay" not in tablolar:
            sahipsiz = c.execute("SELECT COUNT(*) FROM etiket_sonuc").fetchone()[0] if "etiket_sonuc" in tablolar else 0
            return [], sahipsiz
        olaylar = {r["event_id"]: Sinyal(dict(r), {}, None)
                   for r in c.execute("SELECT * FROM etiket_olay ORDER BY ts, event_id") if r["event_id"]}
        bagimsiz = 0
        if "etiket_sonuc" in tablolar:
            for r in c.execute("SELECT * FROM etiket_sonuc"):
                if r["event_id"] in olaylar and r["ufuk"] in (*UFUKLAR, "kaynak"):
                    olaylar[r["event_id"]].etiketler[r["ufuk"]] = dict(r)
                else:
                    bagimsiz += 1
        if "golge_karar_v1" in tablolar:
            for r in c.execute("SELECT * FROM golge_karar_v1"):
                if r["event_id"] in olaylar:
                    olaylar[r["event_id"]].golge = dict(r)
        return list(olaylar.values()), bagimsiz
    finally:
        c.close()


@dataclass
class Ornek:
    sinyal: Sinyal
    ozellik: dict
    cikis_ts: float
    net: float
    getiri: float
    bot: float | None

    @property
    def ts(self):
        return self.sinyal.ts

    @property
    def token(self):
        return self.sinyal.token

    @property
    def wallet(self):
        return self.sinyal.wallet


def ornekler(sinyaller, ufuk, now):
    veri = []
    for s in sinyaller:
        durum, net, _ = etiket_sonucu(s.olay, s.etiketler.get(ufuk), ufuk, now)
        if durum == "OK" and s.wallet and s.token:
            karar_ts = pozitif(s.olay.get("karar_ts"))
            bot = bot_karari(s.olay) if karar_ts is not None and s.ts <= karar_ts <= _f(s.olay["giris_ts"]) else None
            veri.append(Ornek(s, t0_ozellikler(s.olay), _f(s.etiketler[ufuk]["ts"]), net,
                              net / _f(s.olay["giris_usdc"]) * 100, bot))
    return veri


def veri_seti(db_path, ufuk="kaynak"):
    """N17 dışa aktarımının beş alanlı satır sözleşmesi."""
    sinyaller, _ = sinyalleri_oku(db_path)
    return [(r.ts, r.sinyal.olay["event_id"], r.wallet, dict(r.ozellik, bot_kopyaladi=r.bot), r.getiri)
            for r in ornekler(sinyaller, ufuk, time.time())]


def cesitlilik(veri, aile=None):
    def dagilim(anahtar):
        sayi = Counter(k for r in veri if (k := anahtar(r)) is not None)
        return dict(n=len(sayi), en_buyuk_pay=round(max(sayi.values(), default=0) / len(veri), 4) if veri else None)

    d = dict(gun=dagilim(lambda r: int(r.ts // 86400) if r.ts is not None else None),
             token=dagilim(lambda r: r.token or None), cuzdan=dagilim(lambda r: r.wallet or None))
    if aile is not None:
        d["token_ailesi"] = dagilim(lambda r: aile.get(r.token))
    return d


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


def aileler(sinyaller):
    """Aynı token veya aynı işlem imzasıyla bağlı olayların bileşenleri."""
    ust, imzalar = {}, {}

    def kok(t):
        while ust[t] != t:
            ust[t] = ust[ust[t]]
            t = ust[t]
        return t

    for s in sinyaller:
        if not s.token:
            continue
        ust.setdefault(s.token, s.token)
        sig = s.olay.get("sig")
        if sig:
            once = imzalar.setdefault(sig, s.token)
            ust[kok(s.token)] = kok(once)
    return {t: kok(t) for t in ust}
