"""BTC günlük trend motoru (PAPER). Kural: son KAPANMIŞ günlük kapanış, son 100 günün basit ortalamasının (SMA100)
üstündeyse portföy cbBTC'de (Solana), altındaysa USDC'de. Fiyatlar Jupiter teklifinden; gerçek emir, imza, cüzdan YOK.

Neden bu kural: btc_trend sınamasında SMA100 2018–2023'te seçildi ve görülmemiş 2023–2026 döneminde BTC tutmaya yakın
getiriyle (%184'e karşı %195) çok daha küçük en büyük düşüş (%-36'ya karşı %-53) ve daha yüksek Sharpe verdi.
Bu geçmiş bir sonuçtur, gelecek garantisi değildir; bu motor aynı kuralı canlı paper'da ölçer.

Varsayılan KAPALI (BTC_TREND=1). Ayrı veritabanı (nexora_btc_trend.db). Günde bir karar: aynı gün için ikinci kez işlem
yapılmaz (yeniden çalıştırmak güvenlidir). Fiyat etkisi > %1 ise ya da teklif alınamazsa işlem ertelenir."""
import json, os, sys, time

import requests

from nexora.btc_ongoru import BTC_DEC, BTC_MINT, KLINE_URL, USDC_DEC
from nexora.constants import USDC_MINT

PENCERE = 100
NAKIT_REZERV = 1.0
MAKS_ETKI_PCT = 1.0
CUZDAN = "trend_sma100"
SEMA = """CREATE TABLE IF NOT EXISTS trend_gun(gun TEXT PRIMARY KEY, ts REAL, kapanis REAL, sma REAL, hedef INTEGER,
  karar TEXT, neden TEXT);"""


def acik():
    return os.getenv("BTC_TREND") == "1"


def gunluk(s=None, limit=PENCERE + 20, now=None):
    """Son kapanmış günlük mumlar [(kapanis_ts_sn, kapanis)]."""
    s = s or requests.Session(); now = now or time.time()
    r = s.get(KLINE_URL, params={"symbol": "BTCUSDT", "interval": "1d", "limit": limit}, timeout=20)
    r.raise_for_status()
    return [(m[6] / 1000, float(m[4])) for m in r.json() if m[6] / 1000 <= now]


def hedef(kapanis):
    """(piyasada_mi, sma, uzaklik_pct). En az PENCERE gün gerekir."""
    if len(kapanis) < PENCERE: raise ValueError("yetersiz günlük veri")
    sma = sum(kapanis[-PENCERE:]) / PENCERE
    return kapanis[-1] > sma, sma, (kapanis[-1] / sma - 1) * 100


def calistir(paper, quoter, s=None, now=None):
    if not acik(): return dict(durum="kapali")
    now = now or time.time(); db = paper.db
    db.executescript(SEMA)
    try:
        g = gunluk(s, now=now)
        icerde, sma, uzak = hedef([c for _, c in g])
    except Exception as e:
        return dict(durum="hata", hata=f"BTC günlük verisi: {type(e).__name__}")
    gun = time.strftime("%Y-%m-%d", time.gmtime(g[-1][0]))
    if paper._get("kiyas_fiyat") is None:
        paper._set("kiyas_fiyat", g[-1][1]); paper._set("kiyas_ts", now); db.commit()
    pos = paper.position(BTC_MINT)
    if pos:                                                   # günlük değerleme
        try:
            q = quoter.quote(BTC_MINT, USDC_MINT, int(pos["qty_raw"]))
            paper.mark_price(BTC_MINT, q["out_amount"] / 10 ** USDC_DEC / pos["qty"])
        except Exception:
            pass
    once = db.execute("SELECT karar FROM trend_gun WHERE gun=?", (gun,)).fetchone()
    if once and once[0] in ("al", "sat", "tut", "nakit"):
        return dict(durum="ok", karar="zaten karar verildi", gun=gun, piyasada=icerde, sma=round(sma, 2), uzaklik_pct=round(uzak, 2))
    karar, neden = ("tut", "trend yukarı, pozisyon korunuyor") if icerde and pos else \
                   ("nakit", "trend aşağı, nakitte kalınıyor") if not icerde and not pos else (None, None)
    try:
        if icerde and not pos:
            p = paper.portfolio(); boyut = round(p["cash"] - NAKIT_REZERV, 2)
            if boyut < 1.0:
                karar, neden = "bekle", "yetersiz nakit"
            else:
                q = quoter.quote(USDC_MINT, BTC_MINT, int(boyut * 10 ** USDC_DEC))
                etki = q.get("price_impact_pct")
                if etki is not None and etki > MAKS_ETKI_PCT:
                    karar, neden = "bekle", f"fiyat etkisi yüksek (%{etki:.2f})"
                else:
                    neden = f"kapanış SMA100'ün %{uzak:.2f} üstünde"
                    paper.record_buy(f"trend:{gun}:al", CUZDAN, BTC_MINT, boyut, q["out_amount"], BTC_DEC, note=neden)
                    karar = "al"
        elif not icerde and pos:
            q = quoter.quote(BTC_MINT, USDC_MINT, int(pos["qty_raw"]))
            neden = f"kapanış SMA100'ün %{abs(uzak):.2f} altında"
            paper.record_sell(f"trend:{gun}:sat", CUZDAN, BTC_MINT, q["out_amount"] / 10 ** USDC_DEC, note=neden)
            karar = "sat"
    except Exception as e:
        karar, neden = "bekle", f"teklif alınamadı, bir sonraki turda denenecek: {type(e).__name__}"
    if karar != "bekle":                                        # 'bekle' kaydedilmez: aynı gün yeniden denenir
        db.execute("INSERT OR REPLACE INTO trend_gun(gun, ts, kapanis, sma, hedef, karar, neden) VALUES(?,?,?,?,?,?,?)",
                   (gun, now, g[-1][1], sma, int(icerde), karar, neden))
        db.commit()
    return dict(durum="ok", karar=karar, neden=neden, gun=gun, piyasada=icerde, sma=round(sma, 2), uzaklik_pct=round(uzak, 2))


def ozet(paper, son=10):
    db = paper.db; db.executescript(SEMA)
    p = paper.portfolio()
    gunler = [dict(gun=r[0], kapanis=r[1], sma=round(r[2], 2), piyasada=bool(r[3]), karar=r[4], neden=r[5])
              for r in db.execute("SELECT gun, kapanis, sma, hedef, karar, neden FROM trend_gun ORDER BY gun DESC LIMIT ?", (son,))]
    kiyas = paper._get("kiyas_fiyat")
    guncel = gunler[0]["kapanis"] if gunler else None
    islem = [t for t in paper.trades(500) if t["decision"] == "KOPYALANDI"]
    return dict(acik=acik(), mod="PAPER", kural="SMA100 (günlük, uzun/nakit)",
                toplam=round(p["equity"], 2), kz_pct=round(p["pnl"] / paper.start_cash * 100, 2),
                btc_tut_pct=round((guncel / float(kiyas) - 1) * 100, 2) if kiyas and guncel else None,
                piyasada=bool(p["positions"]), islem=len(islem), son=gunler[0] if gunler else None, gunler=gunler,
                sinama=dict(donem="2023-03 → 2026-11 (görülmemiş)", getiri_pct=184.2, tut_pct=195.3, dusus_pct=-36.1,
                            tut_dusus_pct=-53.0))


def main():
    if not acik():
        print("BTC trend motoru kapalı (BTC_TREND=1 gerekli).", flush=True); return 0
    from nexora import gizle as _gizle
    _gizle.kur()
    from nexora.core import Paper
    from nexora.market import JupiterQuoter
    paper = Paper(os.getenv("BTC_TREND_DB", "nexora_btc_trend.db"), ekosistem="btc_trend", dagit=False)
    d = calistir(paper, JupiterQuoter())
    print(f"BTC trend: {d.get('durum')} · {d.get('gun')} · karar {d.get('karar')} ({d.get('neden')}) · "
          f"SMA100 uzaklık %{d.get('uzaklik_pct')} · hata {d.get('hata')}", flush=True)
    return 0 if d.get("durum") != "hata" else 1


if __name__ == "__main__":
    sys.exit(main())
