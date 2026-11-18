# NEXORA 2.0 — Android APK kapsamlı teknik denetimi

**Tarih:** 18 Kasım 2026  
**İncelenen kaynak dal:** `codex/nexora-strategy-lab-seven-tools-v1` (PR #16, taslak)  
**Güvenlik düzeltme dalı:** `codex/nexora-apk-security-audit-v1` (PR #17, taslak; PR #16 üzerine eklemeli)  
**Üretim değişikliği:** YOK. `main`, çalışan sunucu/Termux, üretim DB, anahtarlar, kullanıcı verileri ve eski yedeklere işlem yapılmadı.

## 1. İnceleme yöntemi ve kanıt sınırı

- GitHub recursive tree envanteri: **302 dosya**, **47 Android** ilgili dosya, **208 backend** dosyası, çalışma araçları ve dağıtım dosyaları (güvenlik düzeltmelerinden önceki kaynak fotoğrafı).
- GitHub Actions'dan **gerçek üretilmiş bir test APK** indirildi ve ZIP içeriği denetlendi: APK **2.310.900 bayt** (yaklaşık **2,31 MB**), SHA-256 `7dcc2ffd09b6e53331068dc79ef1dfbace27044279d34fdeadebb68a213290e3`. APK içinde DEX kodu, Android kaynakları, Kotlin Compose uygulaması, yerel kütüphaneler ve Strategy Lab için `chart.html` ile `lightweight-charts.standalone.production.js` var; ZIP bütünlük kontrolü başarılı.
- `android/app/build.gradle.kts`: `applicationId=com.nexora.app`, `versionCode=57`, `versionName=5.20.2`, `minSdk=26`, `targetSdk=34`, Kotlin/Compose, R8 etkin.
- GitHub Actions `assembleRelease`, Kotlin/JVM ağ regresyon testleri ve Python/Node backend testleri denetleniyor. İmza `android/nexora-debug.keystore` üzerindedir; **üretim imzası olarak kabul edilemez**.
- **Bu inceleme gerçek telefonda açma, ekran kaydı, dokunma testi, emülatör, bağımsız penetrasyon testi veya canlı API denemesi içermez.** Kodun varlığı özelliğin üretimde çalıştığını kanıtlamaz.

## 2. Bütün uygulama ekranları ve iş akışları

| Uygulama alanı | Kod ve kullanıcının gördüğü görev | Mevcut değerlendirme |
|---|---|---|
| Açılış / kimlik | `MainActivity.kt`, `Uye.kt`: açılış animasyonu, sunucu adresi, kurucu anahtarı veya kullanıcı oturumu, parola sıfırlama | Genel yapı var; uzaktan HTTPS geçişi zorunlu; fiziksel cihaz testi gerekli |
| Ana Sayfa | `Bugun.kt`, `Sayfalar.kt`, `Ekranlar.kt`: 100 USDC paper özet, risk, cüzdan takip, AutoPilot/Shield, günlük olaylar | Kısmi veri, sahte 0 gösterimi, eski API sürümü, yüklenme gecikmesi cihazda doğrulanmalı |
| Keşfet | Token Radar, Wallet DNA, cüzdan takip, Sosyal AI, `Keşfet → Lab` | Kurucuya özel ekranları uygulama gizliyor; asıl yetkiyi backend kontrol ediyor |
| Strateji Lab | `StratejiLaboratuvari.kt`, `chart.html`: 7 araç durumları, sanal işlemler, risk ve ileri kâr stresini gösteren yerel grafik | Chart JS APK'da paketli; internet CDN'si gerekmez; gerçek kâr kanıtı değildir |
| Portföy | Açık pozisyon, paper manuel AL/SAT, işlem geçmişi, sanal K/Z | İsteklerde gerçek emir yok; sunucu redleri arayüzde gerçek satış gibi sayılmamalı |
| Karne / rapor | `Karne.kt`, `Teshis.kt`, `Hazirlik.kt`: strateji karşılaştırma, düşüş, başarı, net K/Z, gerçek para hazırlık karnesi | Kârlılık istatistiği ileri ölçüm olmadan başarı iddiasına dönüşmemeli |
| Profil / ayarlar | `Uye.kt`, `Kilit.kt`, `Kasa.kt`, `Yedek.kt`: kullanıcı girişi, borsa salt-okuma bağlantıları, PIN/biyometri, bildirim, yedek | Kimlik bilgisi, TLS ve korunmamış yerel yedek başlıca riskler |
| Arka plan | `BildirimServisi.kt`: foreground servis, yaklaşık 30 saniyede olay yoklama, bildirim ve periyodik yedek | Android sürümlerinin foreground servis/pil sınırlamaları cihazda ölçülmeli |
| Denetim / rol | `RolArayuzu.kt`, `Veri.kt`, `backend/server.py`: kurucu ve üye ayrımı | Backend 401/403 denetimi var; belirsiz rolün kurucu sayılması kodda düzeltildi |

**Menü navigasyonu:** Ana Sayfa / Keşfet / Portföy / Karne / Profil. Kurucu keşif alt sekmeleri Token, DNA, Takip, Sosyal AI, Lab. Üyenin kişisel gösterimi ortak paper defterinden ayrılmalı (backend'de `/uye/bakiye` mevcut). Nexo maskot, alt menü animasyonları ve tasarım sistemi değiştirilmedi.

## 3. Risk sicili (bulgu/kanıt/düzeltme)

| ID | Şiddet | Kanıt | PR #17 durumu | Yayın kapısı |
|---|---|---|---|---|
| SEC-01 | **Kritik** | `AndroidManifest.xml` uzakta `usesCleartextTraffic=true`, API ve borsa anahtarları HTTP üstünden gidebilir | Kodda uzak HTTPS zorunlu, yalnız cihaz içi localhost HTTP; 30x kimlik aktarımı engellendi | Sunucu için gerçek TLS/Serve doğrulaması + kurucu/üye cihaz testi |
| SEC-02 | **Kritik** | Release APK depoda paylaşılan **debug signing keystore** ile imzalanıyor | **AÇIK**: değiştirilmedi (mevcut APK ile uyumluluğu bozabilir) | Gizli üretim keystore, CI secret, uygulama güncelleme/migrasyon planı, eski sertifika/fingerprint kıyası |
| SEC-03 | **Yüksek** | `Kasa.kt` Keystore arızasında gizli değeri düz metin saklıyordu | Kodda düz metin fallback kapatıldı, başarısızlık görünür | Önceden saklanmış düz metinlerin cihazda kontrollü şifreli taşınması testi |
| SEC-04 | **Yüksek** | `Veri.kt` rol alanı yoksa `kurucu` varsayıyordu | Belirsiz rol => `bilinmiyor`; backend yetki hâlâ asli kontrol | 401,403, rol değişimi, oturum süresi sınaması |
| SEC-05 | **Yüksek** | `Yedek.kt` tüm `tar.gz` dosyasını RAM'de tutuyordu, sonra eski telefon yedeklerini silebiliyordu | `YedekAkis.kt` akış halinde yazar, yeni dosya haricini silmez; eski temizleme kaldırıldı | Kesik bağlantı, disk dolması, büyük yedek ve aynı isimli dosya cihaz testi |
| SEC-06 | **Yüksek** | Telefon `İndirilenler/NEXORA` içinde **şifresiz tar.gz** arşivi kalabilir | **AÇIK**: eski davranış korunuyor, kimlik/özel anahtar yedeğe katılmıyor; dosya yine hassas olabilir | Arşiv şifreleme, uygulama-özel alan/dışa aktarım izni ve geri yükleme güvenliği |
| SEC-07 | **Orta** | Dört–sekiz rakam PIN SHA-256(salt + PIN), 5 hata bekleme süreci sadece Compose `remember` içinde | **AÇIK** | Cihaz yeniden başlatma sonrası deneme sınırlama, güvenli PIN türetme, biyometrik tehdit modeli |
| SEC-08 | **Orta** | Ana ekran `Veri.yukle` yaklaşık 15+ HTTP uç noktasını sırayla her 15 saniyede okuyor | **AÇIK**, sürpriz regresyondan kaçınmak için yeniden yazılmadı | Toplu snapshot, paralel güvenli GET, iptal/timeout, yavaş bağlantı yük testi |
| SEC-09 | **Orta** | `BildirimServisi` foreground 30 saniye yoklama, 6 saat yedek kontrolü | **AÇIK** | Android 12/13/14 izin/pil/servis yaşam döngüsü testi |
| SEC-10 | **Orta** | GitHub CI APK'yı derliyor ancak dokunmatik, erişilebilirlik, gerçek TLS ve ekran görüntüsü testi yapmıyor | JVM transport testleri ve statik güvenlik CI kapısı eklendi | Android emülatör ve gerçek cihaz smoke testleri |
| SEC-11 | **Orta** | Üretim imzası ve Android Keystore migration dışında paket sürümü hâlâ `57 / 5.20.2` | **AÇIK** | İmza uyumluluğu, versionCode yükseltme, dağıtım kanalının seçimi |
| SEC-12 | **Ürün** | Gerçek emir `N11/N12` için hâlâ ayrı aşama, mevcut yapı paper-only | Değiştirilmedi | Gerçek fonlar otomatik etkinleştirilmeyecek; ayrı kabul ve teknik güvenlik |

## 4. Sunucu / zincir / 7 araç

- Kurucu anahtarı `X-API-Key`; üye `X-Oturum`. `backend/server.py` yetki kapısı, yalnız kurucunun yazabileceği uçlar ve üyenin sınırlı GET/POST yol listesi mevcut.
- Sunucu üyelik parolaları `scrypt` ile türetilmiş anahtardan saklanıyor; sunucudaki borsa anahtarları şifreli kasaya aktarılıyor; gerçek emir/çekim modülü otomatik açılmadı.
- Solana Helius/Jupiter iki yönlü teklifleri risk süzgecinden ve 100 USDT bağımsız paper defterinden geçiyor. Kâr motoru sanal sonuçlar üzerinde ileri zaman ayrımı, kotasyon eksikliği stresi ve pozitif alt sınır kullanıyor.
- Raydium SDK V2 / Orca Whirlpools / solana-py / VectorBT / DuckDB / QuantStats / Lightweight Charts modülleri izole araştırma ve gösterim araçlarıdır. Bu, canlı DEX emri veya garantili getiri anlamına gelmez.
- Graph `WebView` yalnız paketli yerel HTML/JS'yi açar; JS açık ama `JavascriptInterface` kullanılmaz; dış navigasyon kısıtlıdır. Grafik ve erişilebilirlik cihazda incelenmeli.
- Sunucu yedek modülü `backend/yedek.py` ayrı `tar.gz` üretir; giriş/çekim anahtarlarını yedeğe katmaz. Sunucu tarafındaki tarihsel retention politikası **değiştirilmedi**. Telefon tarafı ise artık önceden kayıtlı arşivleri otomatik silmez.

## 5. 39 aşamalı projede denetimin yeri

`backend/asamalar.json` dosyasında **N0–N38 toplam 39 aşama** var. Bunlar uygulamanın kendini raporlayan tarihsel durumlarıdır, yeni testten bağımsızdır. Bu audit **yüzdeleri yapay olarak artırmadı**.

| Aşama | Mevcut dosyada | Bu denetimden sonra kabul kapısı |
|---|---|---|
| N14 · Android | %92, devam | Uygulama 5 sekmesi + rol, HTTPS bağlantısı, Android API26/34, bildirim ve yedek smoke |
| N35 · Güvenlik | %80, devam | Release sertifika, HTTPS geçiş, Keystore/PIN, çevrimdışı saldırı ve sır sızıntısı değerlendirmesi |
| N13 · Kesintisiz sunucu | %88, devam | `NEXORA_HOST` gerçek bind doğrulama ve tailnet HTTPS reverse proxy |
| N15 · Çok kullanıcı | %40, devam | Test üyesinin kurucu veri/anahtarlarına erişememesi |
| N10 · İleri test | %55, devam | 30 günlük ileri paper gözlemi, kotasyondan gerçekleşmeye fark |
| N11 · Emir iskeleti | %45, devam | İmzasız simülasyon; gerçek emir yolu ayrı kapı |
| N12 · Gerçek pilot | %0, başlamadı | Gerçek fon veya otomatik emir KAPALI |
| N36 · Hukuk/uyum | %10, devam | KVKK, ürün ve finansal hizmet yükümlülüklerinin hukuki değerlendirilmesi |

## 6. CI ve sahadaki kabul kapıları

1. **Kaynak ve test:** `python3 tools/apk_audit/static_gate.py` (kimlik taşıyan HTTPS, redirect engeli, Android Keystore, role, backup silmeme); `gradle -p android testDebugUnitTest` (güvenli URL birim testi); backend/test/SDK + `assembleRelease`.
2. **Dağıtım**: Yeni APK'yı gerçek sunucuya bağlamadan önce `deploy/TLS_HTTPS_GECIS.md` belgesindeki tailnet Serve ve sertifika geçişini güvenli ayrı ortamda doğrula. Mevcut çalışan HTTP sistemini aniden kapatma.
3. **Kurucu cihaz testi**: ilk açılış, doğru/yanlış HTTPS, API anahtarı, 401/403/429, cüzdan DNA, Keşfet 5 alt sekme, paper AL/SAT (gerçek emirsiz), stop, portföy, rapor, Lab grafik.
4. **Üye cihaz testi**: kayıt, davet, oturum, parola değiştirme/sıfırlama, yalnız kişisel sanal bilanço, kurucuya özel komutların reddi, borsa anahtarı yalnız salt-okunur.
5. **Kesinti / kaynak testi**: uçak modu, TLS sertifika hatası, ekran döndürme, düşük RAM, 2–4 GB yedek, eksik alan, kesilen indirme, bildirim izni reddi, servis yeniden başlama, yavaş/çok çağrılı API.
6. **Gerçek dağıtım**: ayrı **gizli üretim imzası** ve eski debug imzasıyla uyum planı, sürüm numarası, dağıtım kanalı ve geri alma yöntemi. **Bu aşamalar doğrulanmadan public APK yayınlama veya gerçek fon bağlama yok.**

## 7. Çalışma sınırları ve ileri değerlendirme

- **Uygulamanın tüm ekranlarının gerçek cihazda görsel kalitesi hakkında kesin puan verilmedi.** Kaynak ve binary incelendi; gerçek görünüm/erişilebilirlik için telefon üzerinde kanıt gerekli.
- **Yedekleri silmeyin veya üzerine yazmayın:** yedek otomatik temizleme PR #17'de telefon için kaldırıldı; sunucudaki 14 dosyalı otomatik retention varlığını ayrıca göz önünde bulundurun.
- **Düzeltmeleri PR #17 ile koruyun:** PR #16'yı/PR #17'yi `main`e otomatik birleştirmeyin. HTTPS geçişi tamamlanmadan PR #17'yi üretime almak, eski `http://100.x:8000` bağlantısı olan kullanıcıları erişimsiz bırakır.
- **Kârlılık:** Ortaya çıkan uygulama bir araştırma ve 100 USDT sanal işlem sistemidir. Gerçek kârlılık veya yatırım performansı iddia edilmez.

### Referanslar

- PR #16: https://github.com/hayatcavdan-png/Nexora-2-/pull/16
- PR #17: https://github.com/hayatcavdan-png/Nexora-2-/pull/17
- Android security config: https://developer.android.com/privacy-and-security/security-config
- Tailscale Serve: https://tailscale.com/docs/reference/tailscale-cli/serve
