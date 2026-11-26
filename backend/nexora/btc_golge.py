"""BTC öngörü GÖLGE portföyleri (PAPER içinde PAPER). Her tahmin yönteminin gerçek kâr/zararını canlı ölçer.

İsabet oranı kaçırılan fırsatı ve işlem maliyetini görmez; bu yüzden her yöntem kendi 100 $'lık sanal portföyüyle
aynı kurallarla (portföyün en fazla %50'si BTC'de, %3 zarar kes, taraf başı %0,1 maliyet) işlem yapar:
  - kural:       basit kural YUKARI -> gir, ASAGI -> çık
  - yz_her:      Gemini YUKARI (güvenden bağımsız) -> gir, ASAGI -> çık; YZ yanıtı yoksa değişiklik yok
  - topluluk:    kanıtlı göstergeler/duygu YUKARI -> gir, ASAGI -> çık (kanıt yoksa hiç girmez)
Asıl portföy (temkinli kurallar, Jupiter teklifi) ve BTC'yi tutmak ayrıca raporlanır.
Fiyat: son kapanmış saatlik mumun kapanışı. Gerçek emir yok."""

SEMA = """CREATE TABLE IF NOT EXISTS btc_golge(ad TEXT PRIMARY KEY, nakit REAL, adet REAL, maliyet REAL,
  islem INTEGER DEFAULT 0, kapanan INTEGER DEFAULT 0, kazanan INTEGER DEFAULT 0, bas_ts REAL, son_fiyat REAL,
  bas_fiyat REAL);"""
YONTEMLER = ("kural", "yz_her", "topluluk")
BASLANGIC = 100.0
POZ_ORAN = 0.5
MALIYET_TARAF = 0.001
ZARAR_KES_PCT = 3.0


def kur(db):
    db.executescript(SEMA)


def _hedef(yontem, kural_yon, tahmin, t_yon):
    """True: pozisyonda ol, False: çık, None: değişiklik yok."""
    yon = {"kural": kural_yon, "yz_her": (tahmin or {}).get("yon"), "topluluk": t_yon}[yontem]
    if yon == "YUKARI": return True
    if yon == "ASAGI": return False
    return None


def adim(db, fiyat, now, kural_yon, tahmin, t_yon):
    """Her gölge portföyü bu turun fiyatıyla günceller. Dönüş: {ad: değer}."""
    kur(db); out = {}
    for ad in YONTEMLER:
        r = db.execute("SELECT nakit, adet, maliyet, islem, kapanan, kazanan FROM btc_golge WHERE ad=?", (ad,)).fetchone()
        if r is None:
            db.execute("INSERT INTO btc_golge(ad, nakit, adet, maliyet, bas_ts, son_fiyat, bas_fiyat) VALUES(?,?,?,?,?,?,?)",
                       (ad, BASLANGIC, 0.0, 0.0, now, fiyat, fiyat))
            nakit, adet, maliyet, islem, kapanan, kazanan = BASLANGIC, 0.0, 0.0, 0, 0, 0
        else:
            nakit, adet, maliyet, islem, kapanan, kazanan = r
        hedef = _hedef(ad, kural_yon, tahmin, t_yon)
        if adet > 0:
            gelir = adet * fiyat * (1 - MALIYET_TARAF)
            if (gelir - maliyet) / maliyet * 100 <= -ZARAR_KES_PCT: hedef = False
            if hedef is False:
                nakit += gelir; kapanan += 1; kazanan += int(gelir > maliyet); adet = maliyet = 0.0; islem += 1
        elif hedef is True:
            boyut = min(nakit, (nakit + adet * fiyat) * POZ_ORAN)
            if boyut >= 1.0:
                adet = boyut * (1 - MALIYET_TARAF) / fiyat; maliyet = boyut; nakit -= boyut; islem += 1
        db.execute("UPDATE btc_golge SET nakit=?, adet=?, maliyet=?, islem=?, kapanan=?, kazanan=?, son_fiyat=? WHERE ad=?",
                   (nakit, adet, maliyet, islem, kapanan, kazanan, fiyat, ad))
        out[ad] = round(nakit + adet * fiyat, 2)
    db.commit()
    return out


def karne(db):
    kur(db)
    out = []
    for ad, nakit, adet, islem, kapanan, kazanan, bas_ts, f, bf in db.execute(
            "SELECT ad, nakit, adet, islem, kapanan, kazanan, bas_ts, son_fiyat, bas_fiyat FROM btc_golge ORDER BY ad"):
        deger = nakit + adet * (f or 0)
        out.append(dict(ad=ad, deger=round(deger, 2), kz_pct=round((deger / BASLANGIC - 1) * 100, 2), islem=islem,
                        kapanan=kapanan, kazanma_pct=round(kazanan * 100 / kapanan, 1) if kapanan else None,
                        pozisyonda=adet > 0, bas_ts=bas_ts,
                        tut_pct=round((f / bf - 1) * 100, 2) if f and bf else None))   # aynı başlangıçtan BTC'yi tutmak
    return out
