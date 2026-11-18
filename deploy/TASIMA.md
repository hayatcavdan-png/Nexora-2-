# NEXORA'yı telefondan sunucuya taşıma (N13)

Amaç: takip ve sunucu telefon kapalıyken de çalışsın. Telefon yalnızca uygulamayı göstersin.
Bu adımlar **ücretli bir sunucu** gerektirir (en küçük Linux sunucu yeterli: 1 CPU, 1 GB RAM, Ubuntu 24.04).
Gerçek işlem yine KAPALIDIR; taşıma yalnızca paper sistemini taşır.

## Güvenlik yaklaşımı
- Sunucu internete port açmaz. Telefon ile sunucu, **Tailscale** özel ağı üzerinden (şifreli WireGuard) konuşur.
- Sunucu anahtarı kurulumda rastgele üretilir (en az 16 karakter zorunlu).
- Helius/Jupiter anahtarları yalnızca `/etc/nexora.env` dosyasındadır (root ve nexora kullanıcısı okuyabilir).
  Yedeklere anahtar girmez.

## Adımlar
1. **Telefonda yedek al** (Termux):
   `cd ~/nexora_build/nexora_2 && ./nexora yedek` → `backend/yedekler/nexora_....tar.gz`
2. **Sunucu kirala** ve SSH ile bağlan. Tailscale kur:
   `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
3. **Telefona Tailscale uygulamasını kur** ve aynı hesapla giriş yap.
4. **Sunucuda kurulum:**
   ```
   git clone https://github.com/hayatcavdan-png/Nexora-2-.git && cd Nexora-2-
   sudo bash deploy/kurulum.sh
   ```
5. **Telefondaki yedeği sunucuya aktar** (Termux: `pkg install openssh`):
   `scp backend/yedekler/nexora_....tar.gz KULLANICI@SUNUCU_TAILSCALE_IP:/tmp/`
   Sunucuda (dosya telefondan yalnızca-sahibi izniyle gelir; bu yüzden önce nexora kullanıcısına devredilir):
   ```
   sudo systemctl stop nexora-takip nexora-sunucu; cd /opt/nexora/backend
   F=$(ls -t /tmp/nexora_*.tar.gz | head -1); sudo install -o nexora -m 600 "$F" gelen.tar.gz && \
   sudo -u nexora python3 yedek.py --geri gelen.tar.gz && sudo rm -f gelen.tar.gz "$F" && \
   sudo systemctl start nexora-sunucu nexora-takip
   ```
   Not: SSH oturumu, telefon ağ değiştirince (mobil veri ↔ Wi-Fi, Tailscale aç/kapa) kopar; yeniden bağlanın.
6. **Telefonda eski sistemi durdur** (yedekten ÖNCE yapın): `./nexora durdur` (ikisi aynı anda çalışırsa Helius kotası iki kat harcanır
   ve iki ayrı paper defteri oluşur).
7. **Uygulamada** Ayarlar → Sunucu adresi: **yeni güvenlik sertleştirmesiyle HTTPS zorunlu**. Önce [TLS/HTTPS geçiş kılavuzunu](TLS_HTTPS_GECIS.md) kullanarak Tailscale Serve ile özel ağda sertifikalı `https://SUNUCU_ADI.tailnet.ts.net` endpointini ayrı doğrulayın. Eski APK'nın `http://SUNUCU_TAILSCALE_IP:8000` bağlantısı sadece geçmiş sürüm davranışıdır; yeni APK uzak HTTP'yi reddeder. Üretim sunucusu kendiliğinden değiştirilmez. API anahtarı:
   `sudo grep NEXORA_API_KEY /etc/nexora.env`

## Günlük kullanım
- Durum: `systemctl status nexora-takip nexora-sunucu`
- Günlük: `journalctl -u nexora-takip -f`
- Yedek: her gece 04:10 otomatik, son 14 tanesi saklanır (`/opt/nexora/backend/yedekler`)
- Güncelleme (testler geçmezse eski sürümde kalır): `sudo bash /opt/nexora/deploy/guncelle.sh`
- Çökme: systemd 5 sn sonra yeniden başlatır. Takip 5 dakika çalışmazsa uygulama "Takip durdu" bildirimi gösterir.
