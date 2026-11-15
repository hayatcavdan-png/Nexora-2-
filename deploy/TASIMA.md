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
   Sunucuda:
   ```
   sudo systemctl stop nexora-takip nexora-sunucu
   cd /opt/nexora/backend && sudo -u nexora python3 yedek.py --geri /tmp/nexora_....tar.gz
   sudo systemctl start nexora-sunucu nexora-takip
   ```
6. **Telefonda eski sistemi durdur:** `./nexora durdur` (ikisi aynı anda çalışırsa Helius kotası iki kat harcanır
   ve iki ayrı paper defteri oluşur).
7. **Uygulamada** Ayarlar → Sunucu adresi `http://SUNUCU_TAILSCALE_IP:8000`, API anahtarı:
   `sudo grep NEXORA_API_KEY /etc/nexora.env`

## Günlük kullanım
- Durum: `systemctl status nexora-takip nexora-sunucu`
- Günlük: `journalctl -u nexora-takip -f`
- Yedek: her gece 04:10 otomatik, son 14 tanesi saklanır (`/opt/nexora/backend/yedekler`)
- Güncelleme: `cd /opt/nexora && sudo -u nexora git pull && sudo systemctl restart nexora-sunucu nexora-takip`
- Çökme: systemd 5 sn sonra yeniden başlatır. Takip 5 dakika çalışmazsa uygulama "Takip durdu" bildirimi gösterir.
