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
| `python yz_veri.py` | N17 etiketli veri kalitesi, temel çizgiler ve kimliksiz CSV |
| `python yz_denetim.py --db ./etiket_kopyasi.db --sinyaller` | N16–N19 salt okunur V1 veri kalitesi, net sonuç ve gölge karar raporu |
| `ETIKET_DB=./etiket_kopyasi.db python yz_model.py` | N18 zamana göre doğrulama (≥500 doğrulanmış etiket) ve kabul edilirse ayrı N19 V1 model dosyası |
| `./nexora yedek` | Veritabanı ve cüzdan listelerinin yedeği (geri yükleme: `python yedek.py --geri DOSYA`) |

## Uygulama

GitHub Actions her gönderimde APK derler (Actions → en üstteki derleme → Artifacts → nexora-apk).

**Önemli sürüm uyarısı (18.11.2026):** Bu build hâlen depodaki **debug keystore** ile imzalanan, yalnızca araştırma/test amaçlı APK'dır. Gerçek para/halka açık dağıtım için güvenilir üretim imzası, HTTPS bağlantısı, gerçek Android cihaz testi ve hukuki kabul gerekir. Koddaki `assembleRelease` görevinin başarılı olması üretim onayı değildir. NEXORA hâlâ paper-only'dir.

- [Android APK kapsamlı denetim raporu](docs/NEXORA_APK_KAPSAMLI_DENETIM_2026-11-18.md)
- [Tailscale HTTPS geçişi ve servis güvenliği](deploy/TLS_HTTPS_GECIS.md)
- `python3 tools/apk_audit/static_gate.py` — ağ, kasalama ve yedekleme regresyon denetimi.


## Sunucuya taşıma (N13)
Telefon kapalıyken de çalışması için: [deploy/TASIMA.md](deploy/TASIMA.md)

## Yapay zekâ seçim hattı (N16–N21)
Ana yol haritasından bağımsız: [docs/YZ_yol_haritasi.md](docs/YZ_yol_haritasi.md)

## Yazı tipi
Logo yazısı: Orbitron (Matt McInerney), SIL Open Font License 1.1. Derleme sırasında Google Fonts deposundan indirilir.
