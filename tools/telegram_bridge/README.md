# NEXORA Telegram köprüsü — metadata-only

**GitHub kaynak kodu:** `tools/telegram_bridge/` ve `backend/nexora/social_ai/telegram_bridge.py`.

Bu bileşen T5/T8/T10/T12 **yerel durum** işlevinin yeniden kurulabilir kod temsili içindir, **canlı token tespiti değildir**. Telefonun Termux'unda zaten etkin olan dinleyici, T8, T10 ve HTTP sunucusu **değiştirilmedi**. Bu dosyaları olduğu gibi çalıştırmak, mevcut dinleyiciyle çakışabilir. Kullanıcının açık talimatı olmadan mevcut servisi kapatmayın.

- `telegram_listener.py` Telethon **opsiyonel** dinleyicidir; sadece iki kanalın kullanıcı hesabında olup olmadığını ve gelen yeni mesajların **ID/saat** bilgisini yazdırır. Mesaj gövdesini okumaz.
- `metadata_worker.py` T6 bildirim kayıtlarını **yalnızca ID/kanal/saat** olarak ayrıştırır ve T8/T10 JSON dosyalarını özel izinlerle yeniler. Mevcut telefon T8/T10 işlemleriyle aynı dosyalara yazacağından **yan yana çalıştırılmaz**.
- `local_status_http.py` T10'un `t9_nexora_bridge.json` dosyasını okuyan ve yalnızca `127.0.0.1:18991/status` üzerinden çok sınırlı anonim metadata döndüren HTTP hizmetidir. İlk sürüm Termux T12 ile aynı portu kullandığı için **ikisini aynı anda çalıştırmayın**.
- `backend/nexora/social_ai/telegram_bridge.py` iki kaynak, eski veri, tip/şema doğrulaması ve güvenli alan filtresini uygular.
- `backend/tests/test_telegram_bridge.py` ve `backend/tests/test_telegram_metadata_worker.py` hiçbir Telegram hesabı veya internet gerektirmeyen sentetik güvenlik testlerini içerir.

## Veri gizliliği ve sınır

`Telegram API ID`, `API Hash`, `*.session`, `*.session-journal`, yedekler, Telegram mesajları, token metni ve özel sohbet bilgileri **repo dışında** tutulur. Yerel API, telefon içindeki diğer uygulamalardan da okunabildiğinden yalnızca zararsız kanal adı/sayım döndürür. Üretim Social Radar `0/5` ile yerel Telegram bağlantısı `2/2` birbirinden farklıdır.

Telegram API kullanım şartları nedeniyle metinleri otomatik AI sinyali olarak işlemeyin; önce platform izni/lisansın kapsamını ayrıca doğrulayın. NEXORA'nın gerçek token doğrulama ve paper araştırma hattı **izinli on-chain/DEX kaynakları veya kullanıcı girdiği mint** ile ayrı çalışır.

## Durum

Bu Python dosyaları GitHub'da yer alıyor fakat **Termux çalışan servislerine otomatik dağıtılmadı**. Kapsam dışı: Telegram mesajından token ismi/CA çıkarma; otomatik canlı Helius/DEX besleme; gerçek emir.
