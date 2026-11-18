# NEXORA Profit Engine V1 — Kâr odaklı, sermaye korumalı araştırma

**Durum:** Geliştirme dalında. Gerçek alım/satım, emir imzalama, fon hareketi, aktif sunucuya dağıtım yok. Mevcut hiçbir dosya silinmedi; `main` değişmedi.

## Amaç ve değerlendirme ölçütü

Maksimize edilmeye çalışılan nicelik **tahmini fiyat artışı değil, gerçek dışı iyimserlikten arındırılmış işlem maliyeti sonrası net beklentidir**. Mevcut Jupiter iki yönlü gözlem defterindeki `net_usdt`, girişteki 4 USDT, alış/satış için varsayımsal komisyonlar ve %1 fiyat kayması tamponu kullanılarak oluşturulur. Bu veriler, zincirde gerçekleştirilmiş işlemler **değildir**. Kaybolan satış rotası veya eksik kotasyon gerçek zarar sayılmaz; ancak ayrı **stres senaryosunda tam maliyet kaybı** varsayılır.

Aday önceki Helius/Jupiter güvenlik filtresini geçmedikçe `auto_decision.entry_signal` sanal alıma izin vermez. Mevcut başlangıç kapıları: gözlenen likidite ≥20.000 USD; iki yönlü al/sat farkı ≤%8; her iki tarafta fiyat etkisi ≤%2; veri yaşı ≤30 saniye; sanal giriş 4 USDT. Sinyal puanı **kazanma olasılığı değildir**. 100 USDT sanal sermaye defteri ve en fazla bir yeni sanal deneme/tur korunur.

## Matematiksel yöntem ve geleceğe bakma yasağı

- Aynı token için izlenen 5, 15, 30 ve 60 dakikalık sonuçlar **alternatif** zaman ufuklarıdır. Dört farklı işlem kabul edilmez.
- Her adayın zaman damgası `t`. Bir eğitim örneği ancak gözlem zamanı + **60 dakika + 120 saniye** ≤ `t` ise kullanılabilir. Bu kapı, sonraki satış kotasyonunu geçmişteki alım kararına sokmaz.
- Her ufuk için *stres neti*: güvenilir zamanda kotasyon varsa `min(net_usdt, 2 × giriş_maliyeti)`; kotasyon yoksa **senaryo varsayımı olarak** `−giriş_maliyeti`. Büyük tek kazançların tüm modeli yanıltmaması için üst sınır vardır; gerçek piyasa getirisi sınırlandırılmış değildir.
- Örneklem ortalaması `m`, popülasyon std sapması `s`, gözlem sayısı `n` için tek yönlü yaklaşık alt sınır `m − 1,64 × s/√n`. Bu sonuç küçük/bağımlı örneklerde güvenilir bir istatistiksel garanti değildir.
- Bir ufkun araştırma için seçilebilir olması adına **en az 30 olgun çalışma**, **%90 geçerli kotasyon oranı** ve **sıfırın üzerinde stres alt sınırı** gerekir. Uygun değilse **NAKİT/BEKLE**, geçmişten en yüksek görülen kazanç otomatik seçilmez.
- Her yeni olgun aday üzerinde ileri-sıra sınaması yapılır: önce yalnızca geçmişte olgunlaşmış verilerle ufuk seçilir; **sonra** o adayın kotasyon çıktısı değerlendirilir. Sinyal seçilmediyse nakitte kalmış varsayılır. Sonuçlar tekil çalışma stres toplamıdır; eşzamanlı portföy doluluk ve gerçek doldurma simülasyonu değildir.
- **PAPER_EDGE_CANDIDATE** yalnızca en az 20 ileri-sıra seçilmiş çalışma, olumlu stres ortalaması, ≥%90 kotasyon kapsamı ve senaryo sıralı maksimum düşüş ≤%10 ile mümkündür. Bu etiket yalnızca **daha fazla sanal doğrulama adayıdır**, canlı emir izni değildir.
- Önceden sabitlenmiş **5 dakikalık güvenlik göstergesi** kullanılır; ufuklar arasında geriye dönük en iyiye bakarak koruma seçilmez. Son 30 olgun örnekte kotasyon kapsamı %70'in altına iner veya stres ortalama kaybı çalışma başına 0,60 USDT'yi aşarsa yeni denemeler **1 saatlik koruma penceresinde** durur. İleri-sıra 20+ seçilmiş çalışmanın stres ortalaması -0,20 USDT'den kötü ise aynı koruma devreye girer.
- Kötü verinin sonsuza kadar sistemi kilitlememesi için koruma bir saat sonra **temkinli araştırma** modunda en fazla bir sanal denemeyle devam edebilir. Bozuk kayıt yapısıysa fail-closed durur.

## Nerede çalışır?

- `backend/nexora/strategy_lab/profit_engine.py`: saf Python, ağsız analiz; özel anahtar, cüzdan imzası, emir yok.
- `tools/strategy_lab/auto_paper.py`: provider'a gitmeden **önce** özel paper defterine bakar; koruma tetiklenirse yeni RPC kotası tüketmez, kayıt açmaz.
- `backend/nexora/strategy_lab/report.py` ve `backend/server.py`: kurucuya özel `GET /admin/strategy-lab` üzerinden yalnızca toplu ileri-sıra ve risk istatistiği; mint adresleri ve sırlar dışarı verilmez.
- `android/app/src/main/java/com/nexora/app/StratejiLaboratuvari.kt`: `Keşfet → Lab` ekranında olgun çalışma sayısı, önerilen ufuk, stres sonucu ve koruma durumu görüntülenir.
- `backend/tests/test_strategy_lab_profit_engine.py`: geleceğe bakma, eksik kotasyon, sentetik iyi/kötü veri, aykırı değer, bozuk kayıt ve koruma testleri.
- `backend/tests/test_strategy_lab_auto_paper.py`: koruma durumunda sağlayıcıya tek çağrı bile yapılmaması test edilir.

## Yapılmayanlar / riskler

Bu modül fiyatı öngörmez; gerçek işlem gerçekleştirmez, gerçek net kâr üretmez, stop-loss garantilemez. İleri-sıra testindeki sanal kotalar gerçek zincir gecikmesi, MEV, kısmi dolum, token freeze, havuz çıkışsızlığı, gas, vergi, piyasa etkisi ve gerçek likidite kaybını bütünüyle kapsamaz. 5/15/30/60 dakikalık dört örneklem, dakika içi kırılmaları ve anlık stop temasını görmez. Dağıtımda ayrı devamlı fiyat takibi, gerçekleşme uzlaştırması, bağlantı kopma güvenliği, limit ve acil durdurma kontrolü gerekir.

**GitHub CI başarıları yalnızca izole test başarısıdır.** Gerçek piyasa sağlayıcılarından gözlenen ve ileriye dönük yeterli örneklem olmadan bir stratejiye "kârlı" denilmez.
