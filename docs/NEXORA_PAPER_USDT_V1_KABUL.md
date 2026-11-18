# NEXORA Social Mint → 100 USDT paper önizlemesi (V1)

Durum: **ÇEVRİMDIŞI ARAŞTIRMA / DRAFT PR #15**. Bu çalışmada canlı erken token tespiti, gerçek Helius sorgusu, piyasa verisi veya canlı emir yoktur. `main` ve üretim servisleri değiştirilmedi.

## Hangi iş gerçekten yapıldı?

- `backend/nexora/social_ai/paper_usdt.py`: Doğrudan Solana mint adresi (CA) ve operatörün sağladığı **çevrimdışı kanıt örneği** ile salt okunur test; mint biçimi, RPC mint hesabı, SPL/Token-2022 yetkileri, likidite ve USDT alım/satım kotasyonlarını kontrol eder.
- Başlangıç 100 USDT, sanal token başına üst sınır toplam maliyet 5 USDT. Ücretler ayrıdır; USDC otomatik USDT sayılmaz. Bir test dosyasındaki yinelenen sinyal aynı pozisyonu iki kez açamaz.
- `observed_at` (t0) kararında yalnızca t0 öncesi **ölçülmüş ve alınmış** kanıtlar geçerli. 5, 15, 30 ve 60. dakikalarda erken satış fiyatı kullanılamaz; vade gelmediyse PENDING, süresi içinde kanıt bulunmazsa UNKNOWN. Gerçek getiri garantisi yok.
- `GET /admin/social-paper`: Yalnızca kurucu/kurucu API anahtarı, `no-store`; varsayılan durumda `NOT_CONFIGURED` ve 0 aday. İsteğe bağlı `SOCIAL_PAPER_FIXTURE` dosyası okunursa sonuçlar **OFFLINE_PAPER_ONLY** olarak döndürülür. Üretim veritabanına yazılmaz. Kötü dosya güvenli boş yanıt üretir.
- `SosyalPaperPreview.kt`: Sosyal AI kurucu ekranında **100 USDT · Sanal Token Araştırması** kartı. APK yoksa 404, izinsizse 401/403 mesajlarını gösterir. Telegram 2/2 yerel kartı ve gerçek Sosyal Radar 0/5 ayrı kalır.
- `backend/tests/test_social_paper_usdt.py`, `backend/tests/test_social_paper_http.py`: tamamen çevrimdışı testler.

## Güvenlik ve veri sınırı

- Telegram T5/T8/T10/T12 dinleyicisi ve iki kanalın yalnızca **metadata** durumu korunur. Bu bildirimlerden token çıkarılmaz ve AI'ya Telegram metni verilmez.
- `source=manual_mint` veya uygun izinli bağımsız `licensed_feed` **fixture** girdisi dışında sosyal sinyal kabul edilmez.
- `permission_verified=true` yalnızca test dosyasındaki iddiadır; gerçek lisans denetimi **yapıldığı anlamına gelmez**.
- `PAPER_ELIGIBLE` sadece çevrimdışı kanıt örneğinin filtreden geçtiğini gösterir. Gerçek alışveriş kotasyonu, emir, paper ticaret defteri, hesap bakiyesi muhasebesi veya zincir erişimi **değildir**.
- Güncelleme ile prod API'nin yeni sürüme geçtiği iddia edilmez; mevcut ekranda 404 devam edebilir.

## Operatör için güvenli örnek

```sh
cd backend
PYTHONPATH=. python -B -m unittest -v tests.test_social_paper_usdt tests.test_social_paper_http
```

İsteğe bağlı, *kendi ürettiğiniz gizli bilgi içermeyen küçük test dosyasında* şema:

```json
{"schema_version": 1, "candidates": []}
```

Bu dosya `SOCIAL_PAPER_FIXTURE` ile geçici, ayrı **test** HTTP sürecinde belirtilebilir. Değişken olmadan API boş dönmelidir. Gizli anahtar veya Telegram oturum bilgisi dosyada bulunmamalıdır.

## Sonraki kapılar

1. Github Actions'ta yeni commit'in full-backend, sosyal ve Android APK testlerinin sonucu
2. Gerçek cihazda Android UI testi; kurucu 200, üye 403, anonim 401
3. Ayrı onayla yetkili **on-chain/DEX** kaynak bağlantısı, kota ve RPC tazeliği testleri
4. İzinli, güncel gerçek kotasyonlarla sanal fiyat markalama ve *ayrı* kalıcı paper defteri; restart idempotency
5. Yetkili üretim dağıtım kararı; canlının 0/5 durumu yalnızca gerçek erişim kanıtı ile değişebilir
