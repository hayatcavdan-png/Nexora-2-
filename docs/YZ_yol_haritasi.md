# Yapay zekâ seçim hattı · N16–N21

Ana yol haritasından (N0–N15) bağımsız bir hattır. Amaç fiyat tahmini **değildir**: takip edilen cüzdanların
sinyallerinden **hangilerinin kopyalanmaya değer olduğunu** veriyle seçmektir. Şimdiye kadarki ölçüm, kopyalama
uygulamasının iyi çalıştığını, kayıpların ise kaynak cüzdanların kötü token seçiminden geldiğini gösterdi.

## Değişmez kurallar
- Model para kararının içinde ancak gölge sınavını geçtikten sonra yer alır; o zaman bile **yalnızca paper** kuralını değiştirir.
- Gerçek para N11/N12 yolundan geçer ve ayrıca açık onay gerektirir. Bu hat o onayın yerine geçmez.
- Dil modelleri (Grok vb.) yalnızca **engelleyebilir** (veto); alım başlatamaz.
- Her aşamanın kabul ölçütü sağlanmadan sonraki aşamaya geçilmez. "Avantaj yok" sonucu geçerli bir sonuçtur.

## Aşamalar

### N16 · Sinyal etiketleme motoru
Takipteki **her** kaynak alımı için, işlem yapmadan:
- alım anındaki özellikler (token yaşı, likidite, organik skor, sahip yoğunlaşması, cüzdan istatistikleri, al-sat maliyeti, saat),
- sonuç etiketleri: 5 dk, 30 dk ve kaynak sattığı anda gerçek Jupiter teklifiyle, maliyet dahil "girseydik ne olurdu".

**Kabul:** ≥ 500 etiketli sinyal · etiketlerin ≥ %90'ı eksiksiz · API kullanımı günlük bütçe içinde.
**Süre:** kurulum 1 tur; veri 2–4 hafta (keşfedilen cüzdanlar eklenirse daha kısa).

### N17 · Özellik seti ve veri kalitesi
- Sızıntı denetimi: hiçbir özellik alım anından sonraki bilgiyi içermemeli (otomatik test).
- Temel çizgiler: "hepsini kopyala", N10'daki basit kurallar (zarar kesme, token filtresi) ve rastgele seçim.
- Veri raporu: sınıf dengesi, eksik değerler, cüzdan/gün dağılımı.

**Kabul:** sızıntı testleri geçer · temel çizgilerin maliyet sonrası sonuçları raporlanır.

### N18 · Seçim modeli
- Küçük ve açıklanabilir modeller: lojistik regresyon, sığ karar ağacı (kara kutu yok).
- Zamana göre doğrulama: eski dönemle eğit, sonraki dönemde sına (karıştırılmış çapraz doğrulama yok).
- Çıktı: sinyal başına "kârlı olma olasılığı" ve hangi özelliğin ne kadar etkilediği.

**Kabul:** sınama döneminde maliyet sonrası getiri "hepsini kopyala"dan iyi · fark bootstrap güven aralığında sıfırın üstünde · olasılıklar kalibre.
Ölçüt sağlanmazsa: rapor "avantaj bulunamadı" der, N19'a geçilmez.

### N19 · Gölge karar
Model en az 2 hafta canlı sinyallere paralel karar verir; işlemlere dokunmaz. Gerçekleşen sonuçla karşılaştırılır.

**Kabul:** gölge sonucu N18 sınamasıyla tutarlı (aynı yönde, makul sapma) · model kayması yok.

### N20 · Kontrollü devreye alma (paper)
- Paper kuralına model filtresi eklenir (ör. olasılık eşiğinin altındaki sinyaller kopyalanmaz).
- Tek dokunuşla geri alma; model kayması ve performans düşüşü uyarısı; model sürümü denetim izine yazılır.

**Kabul:** 2 hafta paper'da beklenen davranış · geri alma denendi.

### N21 · Dil modeli yardımcıları (isteğe bağlı)
- **Sosyal risk vetosu:** token hakkında X/sosyal sinyallerde dolandırıcılık/rug işareti varsa alımı engeller. Gölge A/B ile ölçülür; işe yaramıyorsa kapatılır.
- **Türkçe rapor yorumcusu:** günlük raporu, cüzdan kötüleşmelerini ve anormallikleri açıklar (para kararına girmez).

**Ön koşul:** API anahtarı ve aylık maliyet için sizin onayınız.

## Bağımlılıklar
N16 → N17 → N18 → N19 → N20. N21, N16'dan sonra paralel yürüyebilir.
Ana hatla bağlantı: N10 (eşik kararları) N17'nin temel çizgisi olur; N3 keşfi N16'nın veri hızını artırır; gerçek para yalnızca N12 onayıyla.
