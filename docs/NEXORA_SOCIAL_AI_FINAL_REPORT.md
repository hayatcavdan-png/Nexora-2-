# NEXORA 2.0 Social AI nihai teknik kabul raporu

18 Kasım 2026 UTC

**Sonuç — KISMEN TAMAMLANDI.** İzole HTTP kabul adayı hazır. Yeni commit için GitHub CI ve Android cihaz kabulü bekliyor. Üretim geçişi bu çalışmada uygulanmadı.

## GitHub ve `main` uyumu

- Güncel `main` ucu `3d7690cc3bff0170e49d22bf63e2a1cc2f95d3a4` ve inceleme başlangıcındaki `codex/social-radar-release-review` ucu `55ecc216b325a5708ff7d670f6dc4e910308522d` idi. Dal `main` karşısında 18 ileride, 0 gerideydi. Ortak taban doğrulandı ve ek birleştirme gerekmedi. [GitHub main](https://github.com/hayatcavdan-png/Nexora-2-/commit/3d7690cc3bff0170e49d22bf63e2a1cc2f95d3a4)
- PR #9 açık ve taslak. Uzak uçta GitHub API birleştirme durumunu `clean` bildirdi. Başlangıç commit’inin PR ve push Social Radar işlerinde sosyal test, tam backend ve APK başarılıydı. Ayrı APK iş akışı ile `main` APK çalışması da başarılıydı. [PR #9](https://github.com/hayatcavdan-png/Nexora-2-/pull/9) · [PR CI](https://github.com/hayatcavdan-png/Nexora-2-/actions/runs/44290515232) · [Push CI](https://github.com/hayatcavdan-png/Nexora-2-/actions/runs/44288266985) · [APK CI](https://github.com/hayatcavdan-png/Nexora-2-/actions/runs/44288267121) · [Main APK CI](https://github.com/hayatcavdan-png/Nexora-2-/actions/runs/44261658230)
- Nihai değişiklikler yerel geliştirme dalındaki kabul commit’inde. GitHub HTTPS yazma ön kontrolü hazır kimlik doğrulaması bulunmadığından sonuçlanmadı. Uzak PR ucu başlangıç commit’inde ve yeni yerel commit için GitHub CI **doğrulanmadı**. Birleştirme ve force push yapılmadı.

## Entegrasyon

- **NEXORA AI V1.** N16–N20 zincirinde zaman ve token ailesi ayrımı, ileriye bakma engeli, net maliyet ölçümü, kalibrasyon ve gölge sınıflandırması regresyon paketiyle doğrulandı. V1 gölge dosyası ayrı kalır. Eski etiket tablosu ve gölge kayıtları model kabul testlerinde kapsanır.
- **Solana Social AI ve Radar.** Katalog kimlikleri, yayın ve ilk gözlem zamanı, tekrar ve ilişkili grup denetimleri, resmî profil ve SPL/Token-2022 mint kanıtı, likidite ve yetki riskleri mevcut motorla sınandı. 5/15/30/60 dakika gölge ölçümleri aynı ham miktar, vade ve maliyet sözleşmesini kullanır. Eksik çıkış rotası veya fiyat sıfır kâr olarak yazılmaz. Social AI ve Radar fixture çalıştırmaları sırasıyla 2 ve 3 olay üretti. Her ikisinde dört ufuk vardı, genel avantaj `UNKNOWN`, dış çağrı sayısı ve tahmini API maliyeti sıfırdı.
- **Kurucu API.** `GET /admin/social-radar` mevcut sunucu rol denetiminden geçer. Kurucu yanıtlarına ve 401/403 yanıtlarına `Cache-Control: no-store` eklenir. Kapalı bayraklı sunucu snapshot yolunu açmadan boş yanıt verir. Açık bayrağın sentetik birim testinde 2 MB sınırı, normal dosya kontrolü, snapshot ve kaynak kontrolü için 15 dakikalık tazelik, yinelenen kaynak kimlikleri ve bozuk kayıtların elenmesi doğrulandı. Son 24 saatin en yeni 20 uygun kaydı 30 ve 60 dakikalık olgun ölçümleri taşıyabilir. Yanıt sabit kaynak kimliği, mint, sınıf, izinli gerekçe kodları ve sayısal gölge özetini taşır. Ham gönderi, yazar veya cüzdan kimliği, gizli değer, ham kotasyon ve dosya yolu yanıt alanı değildir.
- **Android.** Keşfet > Sosyal AI sekmesi kurucuya gösterilir. Uygulama katalog kimliğini, üst düzey canlı bayrağı ve kaynak doğrulama alanlarını birlikte denetler. Kaynak kartları, erişim/kota/gecikme durumları, kopyalanabilir tam mint, yerel gözlem zamanı ve risk gerekçeleri eklendi veya tamamlandı. Dört ufuk seçimi sayısal ölçümü, bekleyen vadeyi veya eksik veriyi gösterir. Eski HTTP sunucusundaki 404, 401/403, ağ hatası ve boş veri için ayrı görünüm vardır.

## Test ve HTTP kabul kanıtı

| Kontrol | Bu çalışmada doğrulanan sonuç |
| --- | --- |
| Başlangıç backend regresyonu | 511/511 geçti |
| Nihai tam backend | **515/515 geçti**. 132,796 sn |
| Social AI ve Radar | **62/62 geçti**. Tam paketin alt kümesi. 4,659 sn |
| AI V1 | **12/12 geçti**. Tam paketin alt kümesi. Ayrı çalıştırma 3,324 sn |
| Kurucu API anahtarı ve gerçek test kurucu oturumu | İkisi de **200** ve aynı JSON |
| Geçerli üye oturumu | **403** |
| Anonim istek veya yanlış test anahtarı | **401** |
| Bilinmeyen yol, Radar POST ve eski `main`de kurucu Radar GET | **404** |
| Snapshot tanımsız, canlı bayrağı kapalı | **200**, `BAGLANTI_BEKLENIYOR`, **0/5**, `alerts=[]` |
| Bozuk snapshot yolu tanımlı, canlı bayrağı kapalı | **200**, `CANLI_IZLEME_KAPALI`, **0/5**, `alerts=[]` |
| `/durum` ve `/portfoy` | Hem adayda hem `main` tabanında **200** ve eşleşen üst düzey alanlar |
| Android JSON sözleşmesi | Canlı olmayan HTTP çıktısında beş kimlik, platform ve hesap birebir eşleşti. Sentetik API testinde dört sonuç anahtarı, `PENDING/UNKNOWN/OK`, `null`, sıfır ve negatif ölçümler doğrulandı |

Testler Python 3.13.5 ile temiz ortamda ve bellek SQLite kullanılarak çalıştırıldı. HTTP smoke, `server.py` giriş noktasını her seferinde ayrı geçici Paper ve üyelik SQLite dosyalarıyla çalıştırdı. Portlar aday boş veri için `127.0.0.1:39385`, eski `main` için `127.0.0.1:44669` ve kapalı bayrak denemesi için `127.0.0.1:43511` olarak işletim sisteminden seçildi. Yalnızca bu laboratuvar süreçleri çalıştırılıp kapatıldı. Python ağ denetimi loopback dışındaki hedefleri engelledi. Tam pakette başlangıç çalıştırmasında da görülen kapatılmamış dosya ve SQLite bağlantısı `ResourceWarning` uyarıları vardı.

## Android release APK

- `assembleRelease` başarılı. Kotlin, Java, release lint, R8, kaynak küçültme ve paketleme geçti. Derleme 18 dk 51 sn sürdü. İzole ARM64 laboratuvarında Zulu JDK 17.0.13, Gradle 8.7, Android SDK 34, AGP 8.5.2 ve Kotlin 1.9.24 kullanıldı. x86-64 AAPT2, QEMU kullanıcı modu ile çalıştırıldı.
- Sürüm **5.20.2**, `versionCode=57`. Paket ve uygulama kimliği `com.nexora.app`, giriş etkinliği `com.nexora.app.MainActivity`, en düşük Android API 26 ve hedef API 34. APK'da `arm64-v8a`, `armeabi-v7a`, `x86` ve `x86_64` doğrulandı.
- `apksigner` API 26 tabanında v2 imzasını doğruladı. Depodaki önceki laboratuvar sürümüyle aynı test sertifikasının SHA-256 özeti `33aed552e87f6e4cf327f7a58e3da4bca685e062c1d1fe0ccd4065e78d3f8682`. Artırılan sürüm kodu ve aynı paket/sertifika, önceki aynı imzalı 5.20.1 paketi için statik güncelleme koşullarını karşılıyor.
- ZIP bütünlüğü, `zipalign`, 64 bit yerel kitaplıkların 16 KB ELF ve ZIP hizalaması, DEX'teki Radar yolu, beş kaynak kimliği ve gölge sonuç alanları doğrulandı. AndroidX graphics kitaplığı, Gradle'ın sembol ayırma uyarısından sonra olduğu gibi paketlendi. Laboratuvarda cihaz veya emülatör kurulumu ve ekran gezintisi doğrulanmadı. [Android 16 KB paket denetimi](https://developer.android.com/guide/practices/page-sizes)
- Dosya `/mnt/data/nexora-final-lab/run.Hd3NWrw9/release/nexora-5.20.2-social-ai-release.apk` altında. Boyut **2.217.359 bayt**. APK SHA-256 **`ff72fd87df45a3de404c5370a7f2d456664328ef9d6024ee209f30dae13cf817`**.

Derleme ve doğrulama günlükleri aynı laboratuvar kökündeki `apk-build-retry.log`, `apk-verification-final.log` ve `apk-16k-alignment-final.log` dosyalarında. HTTP kanıtı `smoke.log`, test kanıtı `final-backend/full.log`, `final-social/social.log` ve `final-ai-v1/ai-v1.log` dosyalarında.

## Beş sosyal kaynak

| Katalog kimliği | Kaynak | Laboratuvar durumu |
| --- | --- | --- |
| `solana_early_trending` | Telegram `@solearlytrending` | Erişim yok, bağlı değil |
| `kolscope` | Telegram `@KOLscope` | Erişim yok, bağlı değil |
| `ansem` | X `@blknoiz06` | Erişim yok, bağlı değil |
| `lookonchain` | X `@lookonchain` | Erişim yok, bağlı değil |
| `bubblemaps` | X `@bubblemaps` | Erişim yok, bağlı değil |

Toplam **0/5**. Canlı izleme kapalı. X, Telegram veya Helius için gerçek çağrı yapılmadı. Ücretli API ve gerçek emir kullanılmadı. Paper karar, token güvenliği ve risk kuralları güncel `main` ile aynı. Sentetik ölçümler finansal avantaj veya kârlılık kanıtı sağlamaz.

## Açık kabul noktaları

- Yeni yerel commit için uzak CI sonucu yok. PR #9’daki yeşil kontroller yalnızca uzak başlangıç commit’i için geçerli.
- APK cihaz ve emülatör kabulü ayrı kanıt gerektirir.
- Canlı kaynak erişimi, üretim verisi ve üretim geçişi doğrulanmadı. Sağlayıcı erişimi ileride ayrı yetki ve kapsam gerektirir.

## Yalnızca HTTP için güvenli geçiş ve geri alma planı

1. Son commit’in CI sonucunu ve APK cihaz kabulünü kaydedin. Dağıtım onayı alındıktan sonra söz konusu commit’i ve önceki çalışan HTTP sürümünü ayrı, sürümlü paketler olarak saklayın. Mevcut HTTP komutunu, çalışma dizinini, veri yollarını ve ingress hedefini belirleyin. Gizli yapılandırmayı mevcut servis mekanizması üzerinden aktarın, rapora değer yazmayın.
2. Adayı ikinci loopback portunda ve ayrı geçici SQLite dosyalarıyla prova edin. `SOCIAL_LIVE_ENABLED=0` kullanın, snapshot yolunu boş bırakın. 200/401/403/404, 0/5, boş uyarı, `no-store`, durum ve portföy kontrollerini tekrarlayın. APK’yı aynı izole HTTP örneğine bağlayarak kurucu sekmesini ve dört ufuk seçimini deneyin. Sentetik ve gerçek veriye ayrılan çalışma dizinlerini ve mutlak veri yollarını doğrulayın.
3. Üretim geçişi ayrıca onaylanırsa, mevcut ingress destekliyorsa aday HTTP sürecini farklı loopback hedefinde hazırlayın ve önceki HTTP hedefini geri alma için erişilebilir tutun. Aday aynı HTTP çalışma dizini, veri yolları ve servis izinleriyle çalışmalı. `Paper` ve `Uyelik` açılışında mevcut şema başlatma davranışı bulunduğundan, bu adımdan önce sürüm ve dosya yolu uyumunu yetkili operatör doğrular. Trafik geçişinden önce adaya yazma istekleri gönderilmez. Kontrollü okuma yoklamasından sonra HTTP trafiğini tek hedefe yönlendirin ve önceki hedefteki isteklerin bitmesini bekleyin. Uygun ingress veya güvenli veri yolu eşlemesi yoksa geçişi erteleyin. Bu geçiş takipçi, piyasa, borsa, Base/BNB ve zamanlanmış servislere uygulanmaz. `deploy/guncelle.sh` bu planın parçası değildir.
4. Trafik geçişinden sonra rol cevaplarını, 0/5 sözleşmesini, portföy ve durum yanıtlarını, 5xx oranını ve gecikmeyi önceki sürümle kıyaslayın. Yetki, sağlık, SQLite kilitlenmesi, 5xx veya sözleşme regresyonunda ingress’i önceki HTTP hedefine geri alın. Önceki hedefin sağlık ve rol kontrollerini yeniden çalıştırın. Bu HTTP değişikliği yeni SQLite şeması gerektirmez. Geri alma kod ve trafik yönlendirmesi üzerinden yapılır. Veritabanı dosyasını veya yedeği değiştirmeyin.

Üretim SQLite, anahtarlar ve aktif servisler bu çalışma kapsamında kullanılmadı veya değiştirilmedi.
