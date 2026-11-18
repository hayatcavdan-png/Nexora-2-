# NEXORA Social Radar sürüm raporu

[Issue #8](https://github.com/hayatcavdan-png/Nexora-2-/issues/8) için `codex/social-radar-release-review` dalı, GitHub uçlarıyla karşılaştırılan `main` (`3d7690c`) ve `codex/social-radar-server-v1` (`87b2599`) commitlerini birleştirir.

## Birleştirme

- `backend/nexora/model.py` ve `backend/yz_model.py` çakışmaları satır düzeyinde birleştirildi. V1 zaman ve token ailesi ayrımı, blok güven aralığı, kalibrasyon ve net USDC ölçümüyle birlikte `main`deki kopyalanan cüzdanların yüzde getirisi raporlandı. Bu alt küme, sınama döneminde bot kararı doğrulanabilen kopyalama kapsamındaki sinyallerden oluşur.
- Eski N19 gölge raporu ve teşhis `[12]` alt kümesi korunur. Kabul alan kaynak ufku V1 modeli ayrı `yz_model_v1.json` dosyasına yazılır. N20 dosyası, filtreyi açma koşulları ve onay mekanizması mevcut model hattında kalır.
- Karar motoru, token güvenlik kuralları, risk ve pozisyon sınırları `main` ile aynıdır. Bunlara %40 toplam açık maliyet tavanı, günlük zarar sınırı ve cüzdan başına limitler dahildir. `GOLGE_TEYIT` varsayılan olarak kapalıdır. Takipçi V1 için sinyal zamanı ve gölge etiketi kaydeder.
- Solana Social AI ve Android **Keşfet > Sosyal AI** ekranı şu beş kaynak kimliğini paylaşır. `solana_early_trending`, `kolscope`, `ansem`, `lookonchain`, `bubblemaps`. Backend bağımlılıklarında `requests>=2.32,<3` bulunur.

## Test kanıtı

| Kontrol | Sonuç |
| --- | --- |
| `python -B -m unittest discover -s backend/tests -q` | 511 test geçti |
| `python -B -m unittest discover -s backend/tests -p 'test_social*.py' -v` | 58 test geçti |
| `gradle -p android assembleRelease --no-daemon` | `BUILD SUCCESSFUL`. Kotlin, release lint, R8 ve paketleme geçti |
| `apksigner verify --verbose app-release.apk` | APK v2 imzası, DEX içindeki radar yolu ve beş kaynak kimliği doğrulandı |
| Kurucu anahtarı ve kurucu oturumu, yerel HTTP | 200, `read_only=true` |
| Kimliksiz veya geçersiz anahtar, üye oturumu | Sırasıyla 401 ve 403 |
| Aynı GET isteği `main` tabanında | Kurucu anahtarı ve kurucu oturumu için 404 |
| Birleşik dalda bilinmeyen yol ve radar POST isteği | 404 |
| Snapshot olmadan kurucu isteği | `BAGLANTI_BEKLENIYOR`, doğrulanmış kaynak 0/5, `alerts=[]` |
| Bozuk veya tarihi geçersiz snapshot kanıtı | Geçersiz kayıtlar uyarı listesinden çıkarıldı |

Backend kontrolleri Python 3.13.5 ile temiz ortam değişkenleri, bellek SQLite veritabanları ve geçici fixture dosyaları kullanılarak çalıştırıldı. Test süreçlerinin Python ağ çağrıları loopback ile sınırlandı. Test çıktısında kapatılmamış dosya ve SQLite bağlantılarına ilişkin `ResourceWarning` uyarıları vardı.

APK, izole ARM64 laboratuvarında Temurin 17.0.13, Gradle 8.7 ve Android SDK 34 ile derlendi. x86_64 AAPT2 aracı QEMU üzerinden çalıştırıldı. APK, deponun test imzasını taşır. Cihaz veya emülatör kurulumu bu doğrulamanın kapsamı dışındaydı. APK SHA-256 değeri `7ebd986eb3ff9b4453ad6a3950968015bdf9479b4f59f79af7f4bca7a6b6bdb8`.

## Ayrı onaydan sonra önerilen dağıtım ve geri alma

1. **Stage.** Sürüm commitini ayrı bir dizinde paketleyin. HTTP sunucusunu ayrı bir loopback portunda, sentetik veritabanlarıyla ve `SOCIAL_RADAR_SNAPSHOT` tanımsız olarak çalıştırın. Test Android istemcisini bu adrese yönlendirin. İzleme ve piyasa süreçleri kendi çalışma dizinlerinde çalışmaya devam etsin.
2. **Smoke testi.** `GET /admin/social-radar` için 401, 403 ve 200 yanıtlarını, `0/5` ile boş uyarı listesini ve yazma isteği için 404'ü doğrulayın. Android'de kurucu görünürlüğünü ve eski sürümün 404 yanıtıyla bağlantı bekleme durumunu kontrol edin. Mevcut durum ve portföy okuma yollarını önceki sürümle karşılaştırın.
3. **Kontrollü geçiş.** Yazılı dağıtım onayından sonra yalnızca ayrı HTTP sunucu servisini sürümlenmiş pakete yönlendirip yeniden başlatın. `nexora-takip`, `nexora-piyasa`, `nexora-bnb` ve `nexora-base` için yeniden başlatma gerekmiyor. `deploy/guncelle.sh` toplu güncelleme yaptığı için bu geçişin dışında kalır. V1 takipçi veya etiket şeması geçişi gerekiyorsa ayrı sürüm kapısında ele alın.
4. **Geri alma.** Yetki, HTTP hata oranı, sağlık veya 0/5 sözleşmesinde regresyon görülürse yalnızca HTTP sunucusunu önceki paket ve yapılandırmasına yönlendirip yeniden başlatın. Önceki sağlık ve yetki yanıtlarını yeniden doğrulayın. Bu sunucu geçişi için veritabanı geri yüklemesi veya takip ve piyasa süreçlerine müdahale gerekmez.

Yerel doğrulama kapsamında üretim veritabanı, API anahtarları, sağlayıcı çağrıları, aktif servisler ve gerçek emirler kullanılmadı.
