# NEXORA 2.0 — Yeni Solana token araştırması ve 100 USDT paper-watch V2

**Durum: GitHub draft PR #15 — henüz üretime dağıtılmadı.**

Bu kod, 18 Kasım 2026'da kullanıcının istediği **Telegram erken bildirim → gerçek token araştırması → 100 USDT sanal kârlılık ölçümü** hedefinin *Telegram içeriklerinin otomatik ayrıştırılması hariç* olan güvenli teknik temelidir.

## Ne eklendi?

### 1. Yeni havuz/mint araştırması
- `backend/nexora/social_ai/recent_research.py`: Resmî Jupiter Tokens V2 **`GET /tokens/v2/recent`**. RECENT, token mint tarihi değil **ilk havuz açılış zamanıdır**. Sadece doğrulanması gereken adayları sunar.
- Kullanıcının elle girdiği CA için `GET /tokens/v2/search?query=<mint>`; yalnızca **exact mint** kaydı değerlendirilir. Token adı/sembolünden mint eşlenmez.
- Her uygun aday için Helius RPC `getAccountInfo` ile SPL mint owner, decimals, mint/freeze yetkileri, Token-2022 uzantıları.
- Jupiter token bilgisi likidite ve `audit.topHoldersPercentage`/`audit.devBalancePercentage` sınırları. Bilinmeyen değerler engellenir. Jupiter organik skoru tek başına güvenlik kanıtı değildir.
- Jupiter Swap V2 `GET /swap/v2/order` **taker OLMADAN** iki adet fiyat kontrolü: 4 USDT → token ve aynı miktar token → USDT. `transaction` oluşturma, imzalama, `/execute`, gerçek emir veya özel anahtar YOK. Alım / satış fiyat etkisi maksimum %3, anlık tur kaybı %12; kanıt yoksa blok.
- İşlemler **yalnızca kurucunun isteğiyle**, azami 3 aday, aynı süreç içinde en az 45 saniye istek aralığı, `SOCIAL_RESEARCH_LIVE_ENABLED=1` olmadan hiçbir ağ çağrısı YOK.

**Kaynaklar:**
- Jupiter Token API v2: https://developers.jup.ag/docs/tokens/token-information
- Jupiter Swap API V2: https://developers.jup.ag/docs/swap/order-and-execute
- Solana mint/account: https://solana.com/docs/rpc/http/getaccountinfo
- Solana resmî USDT mint: `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`

### 2. Sanal paper-watch
- `backend/nexora/social_ai/paper_watch.py`: sabit başlangıç 100 USDT, tek token için 4 USDT + **varsayımsal** 0,04 USDT alış ağı ücreti ve %1 slippage tamponu (4,08 USDT sanal araştırma rezervi); çıkışta aynı ağ ücreti ve tampon varsayılır.
- **Tam maliyet ölçümü olmadığı için gerçek PnL değildir.** Sonuçlar yalnızca **fiyat tekliflerine dayanan hipotetik** karşılaştırmadır.
- 5, 15, 30 ve 60. dakika **ayrı satış senaryoları**. `PENDING` → vade geldiğinde izinli quote; 120 saniyelik pencere kaçarsa `UNKNOWN`. Sonradan bugünkü fiyatla eski vade doldurulmaz.
- Aynı mint tekrar araştırma defterine eklenmez; en fazla 5 etkin çalışma. Defter salt JSON, dosya kilidi + atomik 0600 yazım; üretim SQLite'ına dokunmaz. Tüm vadeler bittiğinde yalnızca sanal çalışma rezervi serbest bırakılır, varsayımsal kâr otomatik nakde eklenmez.
- `tools/social_paper/worker.py` ancak operatörün aşağıdaki bayraklarını ayrıca açması ve **elle başlatması** halinde çalışır; otomatik kurulmaz. `--once` tek ölçüm, varsayılan tekrar 30 saniye, tek turda en fazla 3 fiyat teklifi.
- Varsayılan 100 USDT `paper_usdt.py` OFFLINE fixture önizlemesinden ayrı tutulur. Bu yüzden uygulamada iki ayrı araştırma kartı vardır; aynı portföy olarak gösterilmez.

### 3. Kurucuya özel API ve APK
- `POST /admin/token-discovery`: `{"mode":"recent","limit":2,"paper":false}` veya `{"mode":"manual","mint":"...","paper":true}`. `paper=true` olsa bile `SOCIAL_PAPER_WATCH_ENABLED` kapalıysa deftere yazılmaz.
- `GET /admin/social-paper-watch`: özel JSON defterinin **salt okunur** özeti. Kurucu 200, üye 403, anonim 401. `Cache-Control: no-store`.
- `POST /admin/social-paper-watch-refresh`: yalnızca açık bayraklar, geçerli Jupiter API anahtarı ve ayrı state dosyasıyla en fazla 3 vadeyi quote ile günceller. Tekrar basılırsa 45 saniye hız limiti.
- Android `YeniTokenArastirmaKarti` ve `CanliPaperIzlemeKarti`: CA girişi, ilk havuz taraması, sanal izlemeye **isteğe bağlı** ekleme, süresi gelen vadeyi yenileme.
- Telegram T5/T8/T10/T12 **2/2 metadata** ve gerçek Social Radar **0/5 kaynak** statüleri AYRI kalır. `main` ve mevcut çalışan telefon servisleri değiştirilmez.

## Üretimden önce güvenlik kapıları

1. GitHub CI'da Social AI, tam backend ve APK sürümleri PASS; Android cihazda oturum/yetki görünümü ayrıca kontrol edilmeli.
2. API key'ler yalnızca sunucu ortam değişkenlerinde kalmalı; GitHub, APK, JSON, log veya sohbet içine yazılmamalı.
3. **Operatörün açık izni olmadan etkinleştirme yok.** `SOCIAL_RESEARCH_LIVE_ENABLED=1`, `SOCIAL_PAPER_WATCH_ENABLED=1`, `SOCIAL_PAPER_WATCH_PATH=/mutlak/guvenli/ozel/paper-watch.json` ve ilgili sunucu sırları gereklidir. Üst klasör önceden sadece operatöre açık 0700 dizin olmalı.
4. Üretim sunucusuna otomatik deploy/ingress yönlendirmesi veya SQLite migration YOK. Test önce izole süreç ve geçici veri yollarında yapılmalı.
5. Kullanıcının kişisel Telegram üyeliği **otomatik metin ayrıştırma lisansı değildir**. Telegram içerikleri AI'ya gönderilmez, post metinlerinden CA çıkarılmaz. Telegram API lisans koşulları: https://core.telegram.org/api/terms ; https://telegram.org/tos/content-licensing
6. Birinci havuzun yeni olması, tokenın güvenli veya potansiyel kârlı olduğu anlamına gelmez. Helius/Jupiter kanıtlarının gerçek ortamda güncel olduğu henüz doğrulanmadı.
7. 100 USDT sanal araştırma defteri **gerçek para veya gerçek alım satım yapmaz**. Ücretler varsayımsal; onaylanmış bir performans avantajı bulunmuyor.

## İzole test komutları (deploy değildir)

```sh
cd backend
PYTHONPATH=. python -B -m unittest -v tests.test_social_recent_research tests.test_social_recent_http tests.test_social_paper_watch tests.test_social_paper_watch_http
```

Tüm backend için GitHub Actions otomasyonunu kullanın. Sıradaki gerçek cihaz kabulünden önce `main` dalına birleştirmeyin.
