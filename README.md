# NEXORA 2.0

Solana akıllı cüzdan kopyalama araştırması. **Yalnızca paper (sanal) işlem; gerçek işlem kodu yok.**

## Telefonda (Termux) çalıştırma

```
cd ~/nexora_build/nexora_2
./nexora kur       # bir kez: Helius, sunucu ve (isteğe bağlı) Jupiter anahtarları
./nexora baslat    # sunucu + canlı takip arka planda; çökerse kendiliğinden yeniden başlar
./nexora durum     # çalışıyor mu, son günlük satırları
./nexora log takip # canlı günlük (çıkmak: CTRL+C); 'sunucu' da olur
./nexora durdur
```

Anahtarlar `~/.nexora_env` dosyasında, yalnızca sizin okuyabileceğiniz izinle durur; depoya girmez.

## Araçlar (backend klasöründe)

| Komut | Ne yapar |
|---|---|
| `python cuzdan_tarama.py` | Cüzdanları etkinliğe göre ayırır (pasif, bot, aday) |
| `python cuzdan_analiz.py` | Adayların gerçekleşmiş kârlılığı; `wallets_onerilen.txt` |
| `python takip_kaybi.py` | Kopyaladığımız işlemlerde kaynağa göre giriş/çıkış kaybı |
| `python gunluk_rapor.py` | Günlük paper raporu |
| `python golge_rapor.py` | Reddedilen alımlara girseydik ne olurdu |
| `python zarar_kesme.py` | Kopyalanan pozisyonlarda %10/20/30/50 zararda satsaydık ne olurdu |
| `python token_filtre.py` | Token yaşı, likidite, organik skor ve sahip payına göre sonuçlar |
| `python cuzdan_kesif.py` | Kaynakların aldığı token'ları onlardan önce alan yeni aday cüzdanlar (~100 Helius kredisi) |
| `./nexora yedek` | Veritabanı ve cüzdan listelerinin yedeği (geri yükleme: `python yedek.py --geri DOSYA`) |

## Uygulama

GitHub Actions her gönderimde APK derler (Actions → en üstteki derleme → Artifacts → nexora-apk).

## Sunucuya taşıma (N13)
Telefon kapalıyken de çalışması için: [deploy/TASIMA.md](deploy/TASIMA.md)
