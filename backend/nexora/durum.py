"""Pozisyon durum makinesi (N1). Her pozisyon her an tek bir durumdadır; yalnızca izinli geçişler yapılabilir.

  (yok) -> ACIK            alım kaydedildi
  ACIK -> KAPANIYOR        kaynak sattı, satış teklifi isteniyor
  KAPANIYOR -> KAPANDI     satış kaydedildi (son durum, geri dönüş yok)
  KAPANIYOR -> TAKILDI     satış teklifi alınamadı (çıkış yolu yok)
  KAPANIYOR -> ACIK        satış kurallarda durdu (ör. bayat sinyal); pozisyon açık kaldı
  ACIK -> TAKILDI          art arda TAKILMA_ESIGI değerlemede teklif alınamadı
  TAKILDI -> ACIK          teklif yeniden alınabildi
  TAKILDI -> KAPANIYOR     kaynak sattı, yeniden satış deneniyor

Gerçek işlem aşamasında (N11) GONDERILDI/ONAYLANDI gibi ara durumlar bu tabloya eklenecek."""

ACIK, KAPANIYOR, KAPANDI, TAKILDI = "ACIK", "KAPANIYOR", "KAPANDI", "TAKILDI"
GECISLER = {
    None: {ACIK},
    ACIK: {KAPANIYOR, TAKILDI},
    KAPANIYOR: {KAPANDI, TAKILDI, ACIK},
    TAKILDI: {ACIK, KAPANIYOR},
    KAPANDI: set(),
}
TAKILMA_ESIGI = 3


class GecersizGecis(ValueError):
    pass


def dogrula(eski, yeni):
    if yeni not in GECISLER.get(eski, set()):
        raise GecersizGecis(f"geçersiz durum geçişi: {eski} -> {yeni}")
