# NEXORA Solana Social AI V1

N21'in çevrimdışı araştırma modülü, gözlem anındaki sosyal ve zincir kanıtlarını birleştirir. Yöneticinin gölge raporunda erken uyarı, izleme, risk vetosu adayı veya belirsizlik gösterir. Tek giriş noktası sentetik JSON dosyasını okuyup JSON yazan CLI'dır. Etiketleyici, karar kapısı, paper, sunucu ve Android akışlarıyla çalışma zamanı bağlantısı yoktur. [Issue #3](https://github.com/hayatcavdan-png/Nexora-2-/issues/3)

## Sentetik örneği çalıştırma

Depo kökünden çalıştırın.

```sh
cd backend
python3 -m nexora.social_ai --fixture tests/fixtures/social_ai_v1.json
python3 -m unittest discover -s tests -p 'test_social_ai.py'
```

Örnekte yayın ve gözlem arasında iki bağımsız Helius alıcı grubu vardır. X paylaşımından sonra yayımlanan Telegram paylaşımı daha erken gözlenir ve ikinci bağımsız sosyal grubu sağlar. X olayı `SOSYAL_ERKEN_UYARI`, Telegram olayı `GOLGE_IZLE` sınıfındadır. Erken uyarının 5/15/30 dakika maliyet sonrası sonuçları sırasıyla −0,12, −0,22 ve −0,32 USDC'dir. Bu üç ufukta işlem yapmama tabanı geçilemediği için sonuç `AVANTAJ YOK` olur. 60. dakikada çıkış rotası kullanılamaz. Bu ufuk ve genel özet `UNKNOWN` kalır. N16'nın ayrı saatindeki 5 dakika sonucu −0,22 USDC'dir. Dış çağrı sayısı 0 ve tahmini dış API maliyeti 0 USD'dir.

## Fixture sözleşmesi

Üst düzey `as_of` raporun bilgi kesim anını, `providers` ise sağlayıcıları taşır. Her sağlayıcı `{"status":"OK","items":[…]}` biçimindedir. Eksik veya geçersiz sağlayıcı `UNKNOWN`, kota kesintisi `RATE_LIMITED` olur. `OK` boş liste, örnek aralığında kapsama olduğu ve kayıt bulunmadığı anlamına gelir. Mock durumları bütün tekrar oynatma için geçerlidir. Tüm saatler UTC Unix saniyesidir.

| Sağlayıcı | Sentetik kayıtlar |
| --- | --- |
| `x`, `telegram`, `token_profile` (`kind=event`) | Kaynak ve yazar kimliği, `published_at`, `observed_at`, `fetched_at`, metin, isteğe bağlı tam `token_mint`, etkileşim sayaçları. Telegram için `authorized=true` ve kanal kimliği gerekir. Sadece `public=true` olan doğrulanabilir genel mesaj bağlantısı gösterilir. |
| `token_profile` (`kind=profile`) | Tam `mint`, `canonical`, resmî hesaplar ve influencer kimlikleri, `measured_at` ve `fetched_at`. Her hesap kaynak ve kaynak kimliğiyle kayıtlıdır. Sembol ve isim eşleme girdisi olarak kullanılmaz. |
| `helius` (`kind=mint`, `kind=trade`) | Mint hesabı için program, tip, kurulma durumu, mint/freeze yetkileri, varsa Token-2022 uzantıları ve ölçüm/çekim saatleri. İşlem için mint, imza, cüzdan, ilişki grubu, yön, `block_time` ve `fetched_at`. |
| `jupiter`, `dex` | Tam mint için `liquidity_usdc`, `measured_at` ve `fetched_at`. Örnekte Jupiter Tokens V2 ve DEX Screener'dan gelecek alanların ortak biçimi kullanılır. |
| `quotes` | Aynı mint ve ham miktar için yön, ölçüm/çekim anı, rotanın uygulanabilirliği, USDC, kayma ve fiyat etkisi baz puanları ile ayrı ağ ücreti. |
| `n16` | Her satırda sentetik N16 `olay` kaydı ve `etiketler` sözlüğü. N16 olayının ve her etiketinin kendi `event_id` değeri korunur. |

Sosyal olayın ham metni ve hesap bilgisi JSON çıktısında tutulmaz. Deduplikasyon ve eşleme için kaynak kapsamlı kimlik özeti, normalize metnin SHA-256 özeti ve sağlayıcının fixture kanıt referansı kullanılır. Yalnızca izin verilen etkileşim sayaçları taşınır. Genel mesaj URL'leri sabit alan adlarından oluşturulur ve sorgu parametreleri atılır. Deterministik kimlik özetleri takma kimliktir. Gerçek veri entegrasyonunda sözlük eşlemesine karşı anahtarlı özet, sağlayıcının saklama/silme koşulları ve erişim denetimi ayrıca tasarlanmalıdır.

## Karar ve ölçüm

- `t0`, paylaşımın ilk geçerli gözlemidir. `published_at ≤ fetched_at ≤ observed_at ≤ as_of` aranır. Yayın gecikmesi 15 dakikayı aşan veya aynı olay kimliğinde ilk gözlemde çelişen kayıtlar raporda reddedilen olay olarak sayılır. Mint profili, mint hesabı ve likidite için önceki 15 dakika içindeki kayıtlar kullanılır ve çekim zamanı kesin olarak `t0` öncesinde olmalıdır.
- Tek, geçerli 32 baytlık base58 adres; aynı mint için resmî profil ve uygun SPL mint hesabıyla doğrulanır. Birden fazla adres, sembol/ad, eksik resmî kayıt ve taklit adres `UNRESOLVED` verir. Hesap iddiaları profilin kayıtlı kaynak kimlikleriyle denetlenir. Ücretli görünürlük, yanıltıcı içerik ve doğrudan sahte hesap işaretleri güvenilir fixture açıklamalarından gelir. Eksik açıklama `UNKNOWN` kalır. Metin veri olarak ayrıştırılır ve herhangi bir yürütme yetkisi taşımaz.
- Tekrar eden metin ve 120 saniyede en az üç farklı hesabın metin veya hesap grubu ortaklığı koordinasyon bulgusudur. Erken uyarı için yayından gözleme kadar erişilebilen en az iki bağımsız alıcı grubu ile en az iki bağımsız sosyal grup gerekir. Sosyal grup hesabına ana paylaşım ve `olay.published_at < teyit.published_at ≤ teyit.fetched_at ≤ teyit.observed_at < olay.observed_at` koşulunu karşılayan teyitler girer. Daha eski paylaşımlar, son 15 dakikada gözlemlendiyse tekrar ve koordinasyon taramasında kullanılabilir. İmza tekrarları tek kayıt olur. İlişkili cüzdanlar, ilişkili sosyal hesaplar ve kopya metinler bağımsız oy biriktiremez. Bir cüzdanın birden çok gruba bağlanması o grupların teyidini düşürür. Jupiter ve DEX için ayrı ayrı 10.000 USDC likidite tabanı kullanılır. Yetki, yetersiz likidite veya sosyal risk bulgusu veto adayı üretebilir. Bu eşikler sentetik araştırma varsayımlarıdır.
- Zincir raporu yayın öncesini, yayın–gözlem arasını ve her gözlem sonrası ufku ayrı tutar. Her bölüm blok zamanı, çekim zamanı ve veri kesimini gösterir. Geç gelen veri önceki kararı veya daha erken sona eren bir zincir ufkunu değiştiremez.
- Gölge simülasyonu gözlemi izleyen ilk 120 saniyede azami 5 USDC giriş kotasyonu arar. 5 ve 15 dakika çıkış toleransı 120, 30 ve 60 dakika toleransı 300 saniyedir. Aynı ham token miktarı için vade içinde bilgiye ilk erişilen kotasyon kullanılır. Kotasyonun USDC değeri rota ücretini, fiyat etkisini ve kayma sınırını içerir. Ağ ücretleri ayrıca düşülür. Satış yapılamadığında, veri eksik kaldığında veya pencere henüz olgunlaşmadığında net sonuç `UNKNOWN` kalır. Ölçülen değerler gerçekleşmiş dolum veya büyük tutarda piyasa kapasitesi kanıtı oluşturmaz.
- N16 bağı, aynı mint, Helius alış imzası ve blok zamanı eşleştiğinde 15 dakikalık gözlem komşuluğunda kurulur. Etiketler N16'nın kendi `t0`, vade ve ücret sözleşmesiyle yeniden denetlenir. N16'nın 5 dk, 30 dk ve kaynak satışı etiketleri ayrı referanstır. Gölge raporu 15 ve 60 dakika değerlerini sadece kendi kotasyonlarından ölçer. CLI N16 için sentetik dışa aktarımı bellekte okur ve SQLite bağlantısı kurmaz.
- Ufuk özetinde erken uyarı seçimi, bütün olaylar ve işlem yapmama tabanı aynı olay kümesinde sinyal başına maliyet sonrası net USDC ile karşılaştırılır. Değerlendirme için her olayın kararı ve net sonucu ile en az bir seçilen ve bir seçilmeyen olay gerekir. Erken uyarı seçimi iki tabandan birini geçemezse o ufukta `AVANTAJ YOK` yazılır. Veri eksikse veya her iki fark da pozitifse ufuk `UNKNOWN` kalır. `avantaj_gerekcesi` eksik karşılaştırma ile doğrulanmamış pozitif farkı ayırt eder. Genel özet, dört ufkun tamamı `AVANTAJ YOK` sonucunu verdiğinde aynı sonucu gösterir. Aynı mintin çakışan olay pencereleri kotasyon paylaşabilir. Gerçek bir A/B sınamasında bu olaylar bağımlı örnek olarak gruplanmalıdır.

## Gelecek entegrasyon tasarımı

Aşağıdaki kotalar ilk gölge pilotu için örnek üst sınırlardır. Gerçek erişim planı, saklama koşulları ve maliyet kullanıcı onayıyla belirlenecektir. Bu sürümde hiçbir sağlayıcı etkin değildir.

| Sağlayıcı | Erişim ve önbellek | Önerilen günlük üst sınır |
| --- | --- | --- |
| X | Resmî API ve izinli sorgular. Sorgu imlecini sakla, aynı olay kimliğini en az 15 dakika yeniden isteme. | 48 sorgu |
| Telegram | Yalnızca yöneticinin izin verdiği kanallardaki bot güncellemeleri. Kanal ve mesaj kimliğiyle deduplike et. | 48 çağrı |
| Helius | Mevcut salt okunur takip altyapısındaki gözlemleri paylaş. Mint hesabını ve imzayı en az 15 dakika önbellekle. | 100 ek RPC |
| Jupiter Tokens V2 ve DEX Screener | Tam mint anahtarıyla grupla, batch desteklenen yerde kullan. Likidite/metadata için en çok beş dakikalık TTL uygula. | Sağlayıcı başına 48 çağrı |
| Jupiter teklif ölçümü | Eşleştirilmiş, en fazla 10 olay, her olay için tek giriş ve dört çıkış. Zaman veya miktar uyuşmayan kotasyonu tekrar kullanma. | 50 kotasyon |

Sağlayıcı kotası ve yerel günlük tavanlardan düşük olanı uygulanır. 429'da `Retry-After` veya artan bekleme süresi kullanılır. Bütçe bittiğinde alanlar `UNKNOWN` kalır. Maliyet hesabı X, Telegram, Helius kredi/çağrı ve piyasa/teklif isteklerini ayrı tutar. Her birim için onaylı tarife ile öngörülen tüketim çarpılır ve varsa sabit abonelik ayrı gösterilir. İlk etkinleşmede aylık ücretli tavan varsayılanı 0 USD'dir. Kimlik bilgileri gelecekte servis düzeyinde verilir, rapora ve loga girmez.

Gelecekteki LLM rolü, sınırlandırılmış metinden olay ve risk özeti üretmektir. Sahte kimlik veya mint kararı doğrulanabilir kaynaklara dayanır. Model çıktısı, yayımlanmış raporda kaynak kanıtı ve belirsizlikle gösterilir. Salt okunur gölge A/B değerlendirmesi ve kullanıcı onayı, herhangi bir filtre entegrasyonunun ön koşuludur.

APK sosyal radar kartı için olası arayüz, yönetici yetkili ve sayfalı `GET /admin/social-radar` uç noktasından önceden hazırlanmış rapor okuyabilir. Kart sınıfı, mint teyidini, gerekçeleri, kanıtları, veri yaşını, sağlayıcı kesintisini, masraf tahminini ve dört ufku gösterir. Raporun saatini ve `UNKNOWN` durumlarını açıkça gösteren salt okunur bir ayrıntı görünümü yeterlidir.

## Dosyalar

- `backend/nexora/social_ai/` sağlayıcı sınırı, olay normalizasyonu, mint eşleme, zincir özeti, risk, gölge ölçümü ve CLI.
- `backend/tests/test_social_ai.py` ve `backend/tests/fixtures/social_ai_v1.json` deterministik testler ve çalıştırılabilir örnek.
- `docs/YZ_yol_haritasi.md` N21'den bu uygulama ve tasarıma bağlantı.
