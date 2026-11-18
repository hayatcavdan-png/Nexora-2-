# NEXORA Telegram yerel köprü görünümü (T12)

## Kanıt ve mevcut durum (18.11.2026)
Kullanıcının Termux çıktısında:
- `nexora_tg_bridge` Python dinleyici CALISIYOR, 2/2 kanaldan bildirim alındı
- `nexora_tg_status` (T8) JSON güncelleyici CALISIYOR
- `nexora_tg_t10` eşleştirici CALISIYOR
- `t7_status.json` ve `t9_nexora_bridge.json` GUNCEL
- 5 metadata bildirimi, `social_ai_transfer=false`, dosyalar mode=600

Bu kanıt yalnızca **yerel kanal erişimi ve bildirim meta-verisi** içindir. NEXORA HTTP `/admin/social-radar` 0/5 gerçek yetkili kaynak olarak kalır.

## Android UI V1 eklemesi
`YerelTelegramKoprusu.kt` sadece yönetici tarafındaki `SosyalRadarEkrani` gösterildiğinde **aynı Android cihazında**, 20 saniyede bir `http://127.0.0.1:18991/status` adresini 1,6 saniye timeout ile okur.

- Bağlantı yalnızca `LOCAL_METADATA_ONLY` ve `social_ai_transfer=false`, `live_verified=false` alanları doğrulanınca gösterilir.
- 2 kaynak kimliği ve handle birebir eşleştirilir.
- `updated_at` 90 saniyeden eskiyse veya üç tmux worker aktif değilse kart "Bağlı değil" gösterir.
- Bu sayılar sunucu 0/5 sayaçlarına **asla eklenmez**; işlem, AI/ML model filtresi, token mint veya gölge sonuçlarına kaynak olmaz.
- API anahtarı, Telegram telefonu, oturum dosyası, özel sohbetler ve mesaj metni APK'ya geçmez.
- T12'de ayrı bir Termux HTTP hizmeti kurulmadıkça kart "Bağlı değil" gösterir; GitHub CI başarısı gerçek yerel bağlantı değildir.
- Ekran kapalıyken Android'de arka plan sorgusu yapılmaz.

## T12 yerel servis gereksinimleri
- Yalnızca `127.0.0.1:18991` bağlanabilir; diğer ağ arayüzlerine bağlanma.
- Sadece `GET /status`, 16 KB'dan kısa, sadece kaynak ID/handle, sayım, son güncelleme saati ve 3 işlem çalışma durumu. JSON; `Cache-Control: no-store`.
- `t9_nexora_bridge.json` kontrollü tam yol, boyut sınırı, tip/kaynak doğrulaması, 90 saniye tazelik, bozuk dosyada 503.
- Diğer işlemleri başlatma, değiştirme veya kapatma; ana SQLite, `server.py`, `deploy/guncelle.sh`, prod servisler ve API kimlik bilgilerine erişme.
- Yalnızca kanal metadatası var. Yerel portta kimlik doğrulaması olmadığından **telefondaki diğer uygulamalar** da bu iki kanalın adını ve sayısını okuyabilir; hassas değer gösterilmez, kullanıcı bu sınırı bilmelidir.
- `tmux` işlem adı kontrolü worker'ın gerçekten sağlıklı çalıştığının kesin kanıtı değildir; tazelikle birlikte kullanılmalıdır.

## Platform politikası
Telegram API Terms §1.5 (https://core.telegram.org/api/terms) Telegram içeriğinden AI/ML modelini geliştirme/dağıtma faaliyetlerini kısıtlar. Bu tasarımda içerik alınmaz veya modele verilmez. İleride izin/lisans değerlendirmesi ve operatör onayı olmadan bu koruma kaldırılmaz.

## Kabul kapısı
1. Backend regresyon ve Social AI testlerinin tamamı geçti
2. Android release derlemesi geçti
3. Termux T12 loopback endpoint yanıtı `mode=LOCAL_METADATA_ONLY` ve `social_ai_transfer=false`
4. Android aynı telefonda yerel 2/2 kartı ve bağımsız 0/5 gerçek Social Radar sayacı gösteriyor (cihaz testi gerekli)
5. Termux durdurulursa, dosya eskiyse veya üç işlemden biri düşerse kart "Bağlı değil" göstermeli

Üretim dağıtımı ve main merge bu PR'ın kapsamında değildir.
