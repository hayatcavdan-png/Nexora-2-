"""Cüzdan analizi GEÇMİŞİ (N4): her analiz bir anlık görüntü olarak saklanır; böylece bir cüzdanın zamanla
iyileştiği/bozulduğu görülür. Tek seferlik iyi görünen cüzdan ile istikrarlı cüzdan ayrılır.
Veritabanı: DNA_DB (nexora_dna.db), tablo analiz_gecmis. Yalnızca özet metrikler saklanır."""
import json, os, sqlite3, time

ALANLAR = ("gerceklesen_usd", "kapanan", "kazanma_orani", "kar_faktoru", "ort_getiri", "medyan_getiri", "medyan_tutma_sn",
           "kalite_puani", "getiri_guven_alt", "en_iyi_haric_usd", "son_yari_getiri", "son10_getiri", "hizli_satis_orani",
           "max_kayip_serisi", "toplam_usd", "skor", "pencere_gun")
SAKLA_ADET = 60                                    # cüzdan başına en fazla bu kadar görüntü tutulur


def _db(yol):
    c = sqlite3.connect(yol, timeout=10); c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS analiz_gecmis(id INTEGER PRIMARY KEY AUTOINCREMENT, wallet TEXT NOT NULL, ts REAL NOT NULL,
        karar TEXT, gerekce TEXT, veri TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS analiz_gecmis_w ON analiz_gecmis(wallet, ts)")
    return c


def kaydet(yol, rows, now=None):
    """Analiz satırlarını görüntü olarak yazar. Hata/kullanıcı değil satırları da (karar olarak) saklanır."""
    now = now if now is not None else time.time()
    c = _db(yol); n = 0
    try:
        for r in rows:
            if not r.get("wallet"): continue
            veri = {k: r[k] for k in ALANLAR if r.get(k) is not None}
            c.execute("INSERT INTO analiz_gecmis(wallet, ts, karar, gerekce, veri) VALUES(?,?,?,?,?)",
                      (r["wallet"], now, r.get("karar"), (r.get("gerekce") or "")[:300], json.dumps(veri)))
            c.execute("""DELETE FROM analiz_gecmis WHERE wallet=? AND id NOT IN
                         (SELECT id FROM analiz_gecmis WHERE wallet=? ORDER BY ts DESC, id DESC LIMIT ?)""", (r["wallet"], r["wallet"], SAKLA_ADET))
            n += 1
        c.commit()
    finally:
        c.close()
    return n


def gecmis(yol, wallet, limit=30):
    if not os.path.exists(yol): return []
    c = _db(yol)
    try:
        return [dict(ts=r["ts"], karar=r["karar"], gerekce=r["gerekce"], **json.loads(r["veri"] or "{}"))
                for r in c.execute("SELECT * FROM analiz_gecmis WHERE wallet=? ORDER BY ts DESC, id DESC LIMIT ?", (wallet, limit))]
    finally:
        c.close()


def egilim(yol, wallet):
    """Son iki görüntüyü karşılaştırır. Dönüş: None (tek görüntü) ya da durum: 'bozuldu' / 'iyilesti' / 'ayni' ve farklar."""
    g = gecmis(yol, wallet, 2)
    if len(g) < 2: return None
    yeni, eski = g
    iyi = lambda k: k == "kopyalanabilir"
    if iyi(eski["karar"]) and not iyi(yeni["karar"]): durum = "bozuldu"
    elif not iyi(eski["karar"]) and iyi(yeni["karar"]): durum = "iyilesti"
    else:
        dk = (yeni.get("kalite_puani") or 0) - (eski.get("kalite_puani") or 0)
        durum = "bozuldu" if dk <= -20 else ("iyilesti" if dk >= 20 else "ayni")
    return dict(wallet=wallet, durum=durum, onceki_karar=eski["karar"], karar=yeni["karar"], gerekce=yeni["gerekce"],
                kalite=yeni.get("kalite_puani"), onceki_kalite=eski.get("kalite_puani"),
                kz_fark=round((yeni.get("gerceklesen_usd") or 0) - (eski.get("gerceklesen_usd") or 0), 2), gun=round((yeni["ts"] - eski["ts"]) / 86400, 1))


def ozet(yol, wallets):
    """Takip listesi için: her cüzdanın son kararı, kalite puanı, görüntü sayısı ve eğilimi."""
    out = []
    for w in wallets:
        g = gecmis(yol, w, SAKLA_ADET)
        if not g: out.append(dict(wallet=w, goruntu=0)); continue
        e = egilim(yol, w)
        out.append(dict(wallet=w, goruntu=len(g), karar=g[0]["karar"], kalite=g[0].get("kalite_puani"), son_ts=g[0]["ts"],
                        egilim=e["durum"] if e else None, kopyalanabilir_orani=round(sum(x["karar"] == "kopyalanabilir" for x in g) / len(g), 2)))
    return out
