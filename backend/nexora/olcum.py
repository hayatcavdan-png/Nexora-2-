"""N16 teklif ölçümünün zaman ve maliyet sözleşmesi."""
import math
import sqlite3
from pathlib import Path

UCRET = 0.01                              # USDC / bacak
UFUKLAR = {"5dk": (300, 120), "30dk": (1800, 300)}
KAYNAK_ZAMAN_ASIMI = 86400
KAYNAK_TOLERANS = 120
TUTARSIZ_ESIK = -2.0
IZLENEN = "cüzdan yalnızca izleniyor"
TEYIT_SN = 900
GIRIS_TOLERANS = 120


def sayi(v):
    try:
        x = float(v)
        return x if math.isfinite(x) and not isinstance(v, bool) else None
    except (TypeError, ValueError, OverflowError):
        return None


def pozitif(v):
    x = sayi(v)
    return x if x is not None and x > 0 else None


def zaman(v):
    x = pozitif(v)
    return x if x is not None and x < 253402300800 else None


def ham_miktar(v):
    if isinstance(v, str) and v.isascii() and v.isdecimal() and len(v) <= 20:
        v = int(v)
    return v if type(v) is int and 0 < v < 2**64 else None


def salt_okunur(yol):
    return sqlite3.connect(Path(yol).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def eski_getiri_kosulu(db, ad):
    """Eski özet okuyucuları için, hata sütunu bulunmayan ilk SQLite şemasıyla da çalışır."""
    x = f"{ad}.getiri_pct"
    hata = f"{ad}.hata IS NULL AND " if db and any(r[1] == "hata" for r in db.execute("PRAGMA table_info(etiket_sonuc)")) else ""
    return f"{hata}typeof({x}) IN ('real','integer') AND abs({x}) < 1e30"


def net_getiri(giris, cikis, ucret=2 * UCRET):
    """Teklif miktarları fiyat etkisini ve al-sat kaybını içerir. Yalnızca ağ ücreti ayrıca düşülür."""
    giris, cikis, ucret = pozitif(giris), pozitif(cikis), sayi(ucret)
    if giris is None or cikis is None or ucret is None or ucret < 0 or max(giris, cikis, ucret) > (2**64 - 1) / 1e6:
        return None
    net = sayi(cikis - giris - ucret)
    if net is None:
        return None
    oran = sayi(net / giris * 100)
    return (net, round(oran, 4)) if oran is not None else None


def tutar_gecerli(olay):
    rt = sayi(olay.get("al_sat_kaybi_pct"))
    return (pozitif(olay.get("giris_usdc")) is not None and ham_miktar(olay.get("qty_raw")) is not None
            and rt is not None and TUTARSIZ_ESIK <= rt < 100 and olay.get("durum") != "giris_yok")


def etiket_sonucu(olay, sonuc, ufuk, now):
    """(Sabit durum kodu, net USDC, getiri %). Eski satırlarda zaman kaynağı doğrulanamaz."""
    t0 = zaman(olay.get("ts"))
    if t0 is None or t0 > now:
        return "geçersiz sinyal zamanı", None, None
    if olay.get("hata") == "geç giriş":
        return "geç giriş", None, None
    if not tutar_gecerli(olay):
        return "giriş teklifi eksik veya tutarsız", None, None
    if sonuc is None:
        son = sum(UFUKLAR[ufuk]) if ufuk in UFUKLAR else KAYNAK_ZAMAN_ASIMI + KAYNAK_TOLERANS
        return ("bekliyor" if now < t0 + son else "etiket eksik"), None, None

    hata = sonuc.get("hata") or ""
    if isinstance(hata, str) and hata.startswith("satılamadı"):
        return "satış yolu hatası", None, None
    if isinstance(hata, str) and "zaman aşımı" in hata:
        return "kaynak zaman aşımı", None, None
    if hata in ("kaçırıldı", "girişten önce satış"):
        return hata, None, None
    if hata:
        return "geçersiz çıkış", None, None
    cikis_ts = pozitif(sonuc.get("ts"))
    giris_ts = pozitif(olay.get("giris_ts"))
    rt_ts = pozitif(olay.get("roundtrip_ts"))
    vade = t0 + UFUKLAR[ufuk][0] if ufuk in UFUKLAR else pozitif(olay.get("kaynak_vade"))
    tol = UFUKLAR[ufuk][1] if ufuk in UFUKLAR else KAYNAK_TOLERANS
    yeni = olay.get("olcum_v") == 1
    if yeni and (giris_ts is None or rt_ts is None or not t0 <= giris_ts <= rt_ts <= t0 + GIRIS_TOLERANS):
        return "geç giriş", None, None
    if cikis_ts is None or not (rt_ts or t0) <= cikis_ts <= now:
        return "geçersiz çıkış zamanı", None, None
    if vade is not None and not vade <= cikis_ts <= vade + tol:
        return "kaçırıldı", None, None
    if ufuk == "kaynak" and (cikis_ts > t0 + KAYNAK_ZAMAN_ASIMI + tol
                             or (yeni and (vade is None or not (rt_ts or t0) < vade <= t0 + KAYNAK_ZAMAN_ASIMI))):
        return "kaynak zamanı doğrulanamadı", None, None
    if ufuk == "kaynak" and not yeni and vade is None and cikis_ts >= t0 + KAYNAK_ZAMAN_ASIMI:
        return "kaynak zamanı doğrulanamadı", None, None
    kayitli = sayi(sonuc.get("getiri_pct"))
    if kayitli is None:
        return "geçersiz çıkış", None, None
    ucret = sayi(olay.get("ucret_usdc")) if yeni else 2 * UCRET
    net = net_getiri(sayi(olay.get("giris_usdc")), sayi(sonuc.get("cikis_usdc")), ucret)
    if net is None or (yeni and abs(net[1] - kayitli) > 0.0001):
        return "geçersiz çıkış", None, None
    return ("OK" if yeni else "eski kayıt", *net)


def politika(kararlar, netler):
    """Sabit teklif tutarlarıyla sinyal başına net. Bilinmeyen seçili sonuçlar toplamı belirsiz bırakır."""
    secili = [net for sec, net in zip(kararlar, netler) if sec is True]
    bilinen = [net for net in secili if net is not None]
    karar_eksik = sum(sec is None for sec in kararlar)
    sonuc_eksik = len(secili) - len(bilinen)
    toplam = None if karar_eksik or sonuc_eksik else sum(bilinen)
    return dict(secili=len(secili), bilinen=len(bilinen), unknown_karar=karar_eksik, unknown_sonuc=sonuc_eksik,
                olculen_islem_ort_usdc=round(sum(bilinen) / len(bilinen), 5) if bilinen else None,
                toplam_usdc=round(toplam, 5) if toplam is not None else None,
                sinyal_basi_usdc=round(toplam / len(netler), 5) if toplam is not None and netler else None)
