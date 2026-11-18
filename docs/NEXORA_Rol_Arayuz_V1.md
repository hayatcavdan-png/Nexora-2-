# NEXORA — Yönetici ve Üye Arayüz V1

## Tasarım kararı
Var olan NEXORA Android Jetpack Compose uygulamasını yeniden yazmak yerine mevcut
koyu lacivert, nane/gök mavisi/lila tasarım dilini koruyup iki rolün işini ayırıyoruz.

### Yönetici (kurucu)
- **Operasyon merkezi**: takipteki cüzdan, açık paper pozisyon, son sinyal
  sayısı ve takip/durdurma durumu yalnızca sunucudan gelen verilerle gösterilir.
- **Hızlı erişim**: Pilot ve risk, Sosyal AI, cüzdanlar, günlük rapor.
- Mevcut Solana radar, Nexo asistanı, paper grafik, karne, risk ve acil durdurma
  ekranları korunur.

### Üye
- **Kişisel alan**: net sanal bakiye, başlangıç ve net kâr/zarar
  `GET /uye/bakiye` ile ayrı yüklenir.
- **Kişisel portföy**: ortak kurucu paper portföyü yerine yalnızca üyenin
  kendi komisyon sonrası sanal bilançosunu gösterir.
- **Keşfet ve Karne**: veri olan alanlara salt okunur erişim; ortak sistem
  karnesi kişisel performans gibi etiketlenmez.
- Üye sayfasında otomatik pilot, risk ayarı, acil durdurma ve manuel paper
  işlem kontrolü yoktur.

## Koruma
- `Mascot` / `Nexo` çizim veya animasyon koduna müdahale yok.
- `Tema.kt` animasyon, `AltMenu2` seçili büyüme/opacity animasyonları,
  açılış ekranı ve mevcut navigasyon semantiği korunur.
- Yeni kartlar var olan `Nx` renkleri ve `tiklaZipla` tıklama efektini kullanır.
- Sunucu kimlik doğrulaması aynı kalır; yalnızca UI saklamak yetki kontrolü sayılmaz.
- X/Telegram erişimi, canlı sinyaller, gerçek emir veya deploy açılmaz.

## Doğrulama
1. Android release APK Gradle derlemesi.
2. Kurucu ile ana sayfa, pilot, cüzdanlar, sosyal radar, rapor ve profil geçişleri.
3. Üye ile kişisel bakiye, portföy, hesap, keşfet, karne ve profil geçişleri.
4. Üye sayfasında kurucu kontrolleri yok; ortak paper servisi kişisel bakiye gibi görünmez.
5. Bağlantı yoksa sahte kişisel tutar üretilmez.
6. Nexo animasyonu/mascotu ve alt menü hareketleri görsel/işlevsel olarak aynı kalır.

Bu sürüm rol bazlı ekran düzenidir. API ve canlı sunucu değiştirilmez;
`main`e birleştirme ve üretim güncellemesi ayrıca onaylanmalıdır.
