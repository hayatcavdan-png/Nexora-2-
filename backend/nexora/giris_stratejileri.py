"""Geliştirme 2 (PROFIT ENGINE V1): üç giriş stratejisinin SALT simülasyonu.

  A — Anında: sinyal NEXORA'ya ulaştığında o anki fiyattan giriş.
  B — Beklemeli: WAIT_SN kadar bekle; o ana kadarki fiyatlar hâlâ kabul edilebilirse (aşırı yükseliş yok) giriş.
  C — Geri çekilme: WINDOW_SN içinde fiyat giriş fiyatının GERI_PCT kadar altına inerse o gözlemden giriş;
      inmezse işlem kaçırılmış sayılır.

KURALLAR
- Karar yalnızca karar anına kadar gözlenmiş fiyatlara dayanır (gelecek fiyat asla kullanılmaz; test edilir).
- Üç strateji aynı sinyal, aynı yol (fiyat gözlemleri) ve aynı çıkış fiyatı üzerinde karşılaştırılır.
- Sinyal ulaşma gecikmesi (ulaşma - sinyal) STALE_SN'yi aşarsa sinyal 'bayat' sayılır ve reddedilir.
- Aynı token için DUP_SN içinde ikinci giriş reddedilir (kontrolsüz tekrar alım yok).
- Yetersiz likidite bayrağı (likit=False) varsa üç strateji de reddeder; satılabilirlik doğrulanamayan token alınmaz.
- Maliyet (MALIYET_PCT) her girişte ve çıkışta düşülür.
SALT SİMÜLASYON: hiçbir işlem açmaz, hiçbir ayarı değiştirmez. Varsayılan GIRIS_MOD=kapali; canlıya bağlanmaz.
Eşikler geçmiş veriye uydurulmamalı; deney masasında kullanıcı onayıyla değiştirilir.
"""
import os

WAIT_SN = int(os.getenv("GIRIS_BEKLE_SN", "60"))
WINDOW_SN = int(os.getenv("GIRIS_PENCERE_SN", "300"))
GERI_PCT = float(os.getenv("GIRIS_GERI_PCT", "3.0"))        # C: giriş fiyatının bu kadar altı
ASIRI_PCT = float(os.getenv("GIRIS_ASIRI_PCT", "15.0"))     # B: sinyal fiyatının bu kadar üstü = aşırı pahalı
STALE_SN = int(os.getenv("GIRIS_BAYAT_SN", "20"))
DUP_SN = int(os.getenv("GIRIS_TEKRAR_SN", "900"))
MALIYET_PCT = float(os.getenv("GIRIS_MALIYET_PCT", "2.0"))  # giriş+çıkış toplam tahmini (ücret + kayma)
GIRIS_MOD = os.getenv("GIRIS_MOD", "kapali")                 # kapali | rapor


def _fiyat_ts(yollar, ts):
    """ts anındaki (veya ts'ten önceki en son) gözlem. yollar: [(ts, fiyat)] artan sıralı. Gelecek asla dönmez."""
    son = None
    for t, p in yollar:
        if t <= ts: son = (t, p)
        else: break
    return son


def simule(sinyal_ts, ulasma_ts, sinyal_fiyat, yollar, cikis_fiyat, likit=True, son_giris_ts=None):
    """Tek sinyal için üç stratejinin sonucu.
    yollar: ulasma_ts'ten sonraki fiyat gözlemleri [(ts, fiyat)], artan sıralı (yalnızca geçmiş gözlemler).
    Dönüş: {'A'|'B'|'C': dict(durum, giris_fiyat, giris_ts, gecikme_sn, getiri_net, neden)}."""
    sonuc = {}
    gecikme = ulasma_ts - sinyal_ts
    ortak = None
    if not likit:
        ortak = "likidite yetersiz"
    elif gecikme > STALE_SN:
        ortak = f"bayat sinyal ({gecikme:.0f} sn)"
    elif son_giris_ts is not None and ulasma_ts - son_giris_ts < DUP_SN:
        ortak = "aynı token için kısa süre önce giriş yapıldı"
    for s in ("A", "B", "C"):
        if ortak:
            sonuc[s] = dict(durum="reddedildi", giris_fiyat=None, giris_ts=None, gecikme_sn=gecikme, getiri_net=None, neden=ortak)
            continue
        if s == "A":
            g = _fiyat_ts(yollar, ulasma_ts)
            if g is None or g[0] < ulasma_ts - 120:
                sonuc[s] = _kacir(gecikme, "ulaşma anında fiyat yok")
            else:
                sonuc[s] = _giris(g, gecikme, cikis_fiyat)
        elif s == "B":
            t = ulasma_ts + WAIT_SN
            g = _fiyat_ts(yollar, t)
            if g is None or g[0] < ulasma_ts:
                sonuc[s] = _kacir(gecikme, "bekleme sonunda fiyat yok")
            elif (g[1] / sinyal_fiyat - 1) * 100 > ASIRI_PCT:
                sonuc[s] = _kacir(gecikme, f"aşırı yükseliş (sinyal fiyatının %{ASIRI_PCT:.0f} üstü)")
            else:
                sonuc[s] = _giris(g, gecikme, cikis_fiyat)
        else:
            ref = _fiyat_ts(yollar, ulasma_ts)
            if ref is None:
                sonuc[s] = _kacir(gecikme, "ulaşma anında fiyat yok")
            else:
                hedef = ref[1] * (1 - GERI_PCT / 100)
                giris = None
                for t, p in yollar:
                    if t <= ulasma_ts: continue
                    if t > ulasma_ts + WINDOW_SN: break
                    if p <= hedef:
                        giris = (t, p); break
                sonuc[s] = _giris(giris, gecikme, cikis_fiyat) if giris else _kacir(gecikme, f"geri çekilme olmadı (%{GERI_PCT:.0f})")
    return sonuc


def _kacir(gecikme, neden):
    return dict(durum="kaçırıldı", giris_fiyat=None, giris_ts=None, gecikme_sn=gecikme, getiri_net=None, neden=neden)


def _giris(g, gecikme, cikis_fiyat):
    t, p = g
    getiri = (cikis_fiyat / p - 1) * 100 - MALIYET_PCT if cikis_fiyat else None
    return dict(durum="girdi", giris_fiyat=p, giris_ts=t, gecikme_sn=gecikme,
                getiri_net=None if getiri is None else round(getiri, 3), neden="")


def ozetle(sonuclar):
    """Birden çok sinyalin sonuçlarından strateji başına özet: girdi, kaçırılan, reddedilen, ortalama net getiri, kazanma oranı."""
    out = {}
    for s in ("A", "B", "C"):
        rows = [r[s] for r in sonuclar if s in r]
        girdi = [x for x in rows if x["durum"] == "girdi" and x["getiri_net"] is not None]
        out[s] = dict(sinyal=len(rows),
                      girdi=sum(1 for x in rows if x["durum"] == "girdi"),
                      kacirildi=sum(1 for x in rows if x["durum"] == "kaçırıldı"),
                      reddedildi=sum(1 for x in rows if x["durum"] == "reddedildi"),
                      ort_net=round(sum(x["getiri_net"] for x in girdi) / len(girdi), 3) if girdi else None,
                      kazanma=round(100.0 * sum(1 for x in girdi if x["getiri_net"] > 0) / len(girdi), 1) if girdi else None)
    return out
