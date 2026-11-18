# NEXORA APK — Uzak HTTP'den HTTPS'e korumalı geçiş

**Durum:** Kılavuzdur; bu dosyanın eklenmesi sunucuda hiçbir komut çalıştırmaz.
Yeni APK güvenlik dalında uzaktaki sunucu adresleri `https://` olmak zorundadır.
Aynı Android telefon içindeki Termux'a `http://127.0.0.1:8000` erişimi korunur.

**Önemli:** Mevcut Oracle/Tailscale sunucusunun hangi adreste dinlediği (loopback mi
100.x Tailscale IP mi) burada bilinmiyor. Aşağıdaki sunucu adımlarını mevcut
süreçleri durdurmadan önce doğrulayın. Çalışanları durdurmayın, DB'ye dokunmayın,
anahtarları/çıktılarını herhangi bir sohbet veya GitHub yorumuna yapıştırmayın.

## 1. Salt okunur ön kontrol (sunucu üzerinde)

```sh
sudo systemctl is-active nexora-sunucu
sudo ss -lntp | grep ':8000'
tailscale status
tailscale serve status
```

`127.0.0.1:8000` dinliyorsa Serve hedefi `http://127.0.0.1:8000`
olabilir. Yalnızca `100.x.y.z:8000` dinliyorsa farklı bir hedeftir;
**otomatik olarak loopback kabul etmeyin**. Bu durumda mevcut arayüzü ve
firewall/ACL sınırını kontrol edin; `tailscale serve` hedefi, sunucudan gerçekten
erişilebilen doğru *özel* adrese yönlendirilmelidir. Mümkünse yalnızca loopback
üzerinde çalışan bir uygulama sunucusu tercih edilmelidir; bunun değişmesi ayrıca
planlanmalıdır.

## 2. Serve'ü yalnızca tailnet içinde HTTPS ile sunma

Tailscale yönetim ekranında HTTPS sertifikası özelliğinin etkin olduğundan emin
olun. `tailscale serve --help` ile kurulu sürümün sözdizimini doğrulayın.
Önceden tanımlı bir Serve kuralı varsa onun üzerine izinsiz yazmayın.

**Yalnızca 127.0.0.1:8000 dinleyicisi doğrulanırsa örnek komut:**

```sh
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```

`--bg` Serve kuralının arka planda kalmasını sağlar. Görünen HTTPS FQDN
(`https://cihaz.tailnet.ts.net` benzeri) API uygulamasının yeni adresidir.
Gerçek FQDN'yi, sertifika doğrulamasını ve telefon Tailscale erişimini test edin.

**Funnel çalıştırmayın**: public internete açılması bu geçişin parçası değil.
`tailscale serve reset` gibi tüm Serve kurallarını silebilen komutlar bu
prosedürün parçası değildir.

## 3. Ölçüm ve kabul

* Mevcut sunucuya eski uyumlu APK'nın erişimi devam eder; yeni APK'ya geçmeden
  önce tailnet HTTPS FQDN'sini doğrulayın.
* Telefon Tailscale açıkken HTTPS FQDN üzerinden API key/session testi, yönetici
  ve üye rolü ayrımı, 401/403, bağlantı kesilince kullanıcıya anlaşılır hata,
  canlı paper izleme ve yedek indirme testi yapılır.
* Sertifika adı uyuşmazlığı, kendinden imzalı sertifika veya bağlantı düşmesi
  durumunda **TLS doğrulaması kapatılmaz**; dağıtım durdurulur.
* `main`, üretim DB ve aktif Termux'a otomatik geçiş veya değiştirme yapılmaz.
* Kontroller başarılı olursa önce test APK'sına URL kaydedilir, sonra dağıtım
  planı hazırlanır. Mevcut kullanıcılar için imza uyumluluğu ayrıca kontrol edilir.

## Geri dönüş

Yalnızca bu geçişte yeni eklenen Serve kuralını kaldırmak için kurulu CLI
sürümüne uygun `tailscale serve --https=443 off` komutu değerlendirilebilir.
Önce `tailscale serve status` ile o portun başka uygulamaya ait olmadığını
doğrulayın. Eski sunucu, veritabanları ve eski uyumlu APK aynı kalır.

## Kaynaklar

- https://tailscale.com/docs/reference/tailscale-cli/serve
- https://tailscale.com/docs/features/tailscale-serve
- https://developer.android.com/privacy-and-security/security-config

**Güvenlik notu:** Bir Tailscale ağı uçtan uca şifreli olsa bile,
kimlik bilgilerini Android HTTP URL'lerine göndermeyi engelleyen yeni istemci
politikası ayrı HTTPS uç noktası talep eder. Uzak IP'yi `http://100.x` ile
yazmaya devam etmek yeni APK'da bağlantı hatasıdır; bu kasıtlıdır.
