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

## V1 yerel denetim

`backend` dizininde, yerel bir etiket veritabanı kopyasıyla çalıştırın.

```sh
python3 yz_denetim.py --db ./etiket_kopyasi.db
python3 yz_denetim.py --db ./etiket_kopyasi.db --sinyaller
python3 yz_denetim.py --db ./etiket_kopyasi.db --ufuk 5dk
ETIKET_DB=./etiket_kopyasi.db python3 yz_model.py
```

Denetim SQLite'ı salt okunur açar. Eksik veya boş veritabanı `veri yok` döndürür. Çıktı JSON'dur. `--sinyaller` seçeneği rapor içi sıra numarasıyla sinyalin sınıfını, sabit gerekçesini, model sürümünü ve üç ufkunu gösterir. Olay ve sonuç eşleştirmesi içeride `event_id` ile yapılır. Ham olay kimliği, token, imza, cüzdan, teklif hatası metni ve sırlar rapora çıkmaz. N17 CSV'sinde de bu kimlik alanlarının yerini sıra numarası alır.

### t0 ve etiketler

- `t0`, takipçinin kaynak sinyali tanıdığı ve paper kararını çağırmaya hazır olduğu andır. Ana model bu andaki saat ve algılama gecikmesiyle çalışır. Token bilgisi ve cüzdan teyidi için yalnızca önceki 15 dakikada ölçülmüş ve `t0` öncesinde kayda geçmiş gözlemler kullanılabilir. Eşit zamanlı ve sonradan tamamlanan kayıtlar teyide girmez. Tarihi kanıtlanmamış cüzdan CSV'si, o sinyal için daha sonra alınan teklifler ve paper kararı ana modele girmez. Paper sonucu yalnızca eşleştirilmiş karşılaştırmada ve `bot_kopyaladi` dahil ablation deneyinde kullanılır.
- Giriş ve geri satış teklifleri `t0`'dan sonra en çok 120 saniyede tamamlanmalıdır. 5 dk, 30 dk ve kaynak satışı için son teklif toleransları sırasıyla 120, 300 ve 120 saniyedir. Satış görülmeden 24 saat dolarsa kaynak etiketi `UNKNOWN` olur. Kaydedilmiş satış vadesi yeniden başlatmada korunur. Alış sırasında veya öncesinde gözlenen satış da `UNKNOWN` olur.
- Net USDC, aynı ham token miktarının çıkış teklifinden girişte kaydedilmiş USDC tutarı ile iki bacak için toplam 0,02 USDC ağ ücreti düşülerek hesaplanır. Alış/satış teklifleri rota maliyetini, fiyat etkisini ve gözlenen gecikmedeki fiyatı taşır. Hemen geri satış kaybı, gecikme ve likidite ayrıca raporlanır. Round-trip kaybı ikinci kez düşülmez. Rota hatası, tutarsız teklif veya eksik gözlem sıfır getiri ya da tam zarar olarak işlenmez.
- Dört politika aynı kayıt kümesinde gösterilir. Bunlar hepsini kopyalama, kayıtlı bot kararı, alım yapmama ve gölge aday seçimidir. Sinyal başına net ölçümde bilinen alım yapmama kararı sıfır katkı sağlar. Bilinmeyen seçim veya bilinmeyen seçili getiri varsa tam toplam ve sinyal başına değer `null` kalır. Bilinen işlemlerin ortalaması ayrıca verilir. Bot karşılaştırması kaydedilmiş kararı kullanır ve portföyü yeniden oynatmaz.

### Zamana göre doğrulama ve kabul

- İlk %70 geliştirme, son %30 sabit sınama dönemidir. Sınırdaki eşit zamanlar birlikte sınamaya alınır. Eğitimden, sonucu sınama başlangıcında hâlâ açık olan kayıtlar ve sınamayla aynı token veya işlem imzasından bağlı aileler çıkarılır. Geliştirme bölümünde arındırılmış geçmişle üç genişleyen ileri pencere çalıştırılır. Ölçekler, eksik değer medyanları ve seçim eşiği her seferinde yalnızca o pencerenin eğitim örneklerine dayanır.
- Sınamada hem token ailesi hem UTC günü bloklarıyla, aynı bloklar üzerinden eşleştirilmiş %95 bootstrap aralıkları hesaplanır. Modelin işlem başına ortalama artışı ve alım yapmamaya veya hepsini kopyalamaya göre sinyal başına net farkı pozitif destek gerektirir. Botla karşılaştırma aynı sonucu ve kayıtlı bot kararı bilinen sinyalleri kullanır. Sınamada bu ortak kümenin kapsamı en az %50 olmalıdır. Brier skoru eğitimdeki sabit kazanma tahminini geçmeli ve beş kutulu ağırlıklı kalibrasyon hatası en çok 0,15 olmalıdır. Üç ileri pencerenin her birinde hepsini kopyalama ve alım yapmama tabanlarına göre net fark pozitif olmalıdır.
- Eğitim için en az 500 doğrulanmış sonuç ve olgunlaşmış etiketlerde en az %90 başarı gerekir. %90 sınırı test dönemine de uygulanır. Veri genelinde en az 14 UTC gün ve 30 token ailesi, son sınamada en az 5 gün ve 20 aile gerekir. Her iki kümede en az 5 cüzdan aranır. En büyük gün ve cüzdan payı %40, en büyük token ailesi payı %20 ile sınırlıdır. Model seçimlerinin en az 3 güne ve 5 aileye dağılması gerekir. Rapor bu blokların sayısını ve yoğunlaşmalarını verir. Bu sayılar bağımlılığı incelemek için kullanılan analiz birimlerini gösterir.
- Kaynak ufkunda kabul edilen lojistik model, ayrı `yz_model_v1.json` dosyasına atomik olarak yazılır ve yalnızca gelecekteki N19 sinyallerinin gölge raporunda kullanılır. `YZ_ZORLA=1` deneme modunda dosya üretilmez. `--ufuk` denetimde incelenen doğrulama hedefini seçer. N19 olasılıklarının kalibrasyon hedefi kaynak satışı olarak kalır. Gölge raporu sürüm başına net sonucu, kalibrasyonu ve seçim kaymasını ölçer, mevcut 14 gün ve 100 etiket eşiğini gösterir.
- Önceki `yz_model.json` N20 biçimi ve eski gölge tablosu okunabilir. V1 alanları ve `golge_karar_v1` tablosu yalnızca N16 etiket yazıcısı açılırken eklenir. Salt okunur denetim eski kayıtları değiştirmez ve zaman kaynağı kanıtlanamayan kayıtları V1 kabul örneği saymaz. Üretim geçişi, bir kopyada eski okuyucular ve yazıcılar doğrulandıktan sonra ayrıca değerlendirilir.

Teklif ölçümü gerçekleşmiş dolumu, kapasiteyi veya piyasa etkisinin daha büyük tutarlarda nasıl değişeceğini kanıtlamaz. Kuyruk sınırlarından önce elenen sinyaller bu SQLite raporunun kapsamı dışındadır. İlk görülen tokenlarda geçmiş t0 özelliklerinin az gelmesi ve bilinmeyen sonuçların seçilim etkisi, gerçek veriyle ölçülmesi gereken sınırlardır.
