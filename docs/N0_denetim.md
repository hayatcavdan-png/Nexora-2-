# N0 · Eski NEXORA denetimi

Tarih: 16.11.2026 · İncelenen: telefondaki `~/nexora_2` klasörünün salt okunur kopyası (veritabanları, checkpoint, yedek, günlük, CSV ve anahtar dosyaları hariç).
Eski sisteme hiçbir şekilde dokunulmadı: dosya silinmedi, değiştirilmedi, çalıştırılmadı.

## 1. Envanter

| Bölüm | Dosya | Satır | İçerik |
|---|---:|---:|---|
| `nexora/wallets` | 98 | 9.671 | Cüzdan keşfi (wallet hunter), geçmiş tarama, puanlama ve sıralama varyantları |
| `nexora/paper` | 19 | 2.318 | Binance mum (ETHUSDT 15 dk) tabanlı paper araştırma hattı, FIFO eşleştirici |
| `nexora/solana` | 8 | 1.854 | Helius istemcisi, swap çözücü, işlem sınıflandırıcı, geçmiş deposu |
| `nexora/core` | 8 | 864 | Miktar dönüşümü, veritabanı, modeller, günlük maskeleme, çalışma koruması |
| `nexora/data` | 4 | 310 | Binance mum verisi indirme |
| kök + `backend` + `android` | 13 | ~650 | Eski FastAPI iskeleti, eski uygulama, mum tabanlı teknik analiz |
| `nexora/tests` | 223 | 25.344 | 1.271 test (çevrimdışı doğrulamada 1.257 geçti, 14 hata) |

Gizli bilgi taraması: kodda gömülü gerçek anahtar **bulunmadı** (eşleşmeler işlem imzalarıydı; testlerdeki `api-key=test` sahte değer).

## 2. Yeni sisteme taşınanlar (doğrulanmış, kullanımda)

| Eski modül | Yeni sistemde | Not |
|---|---|---|
| `solana/helius_client.py` | `nexora/helius_client.py` | Anahtarsız hata mesajları; salt okunur metod listesi (+ `getSignatureStatuses`) |
| `solana/swap_decoder.py` | `nexora/swap_decoder.py` | USDT adresi düzeltildi; stablecoin filtresi; hesap aç/kapa doğrulaması eklendi |
| `solana/transaction_parser.py` | `nexora/transaction_parser.py` | Olduğu gibi |
| `core/amounts.py` | `nexora/amounts.py` | Olduğu gibi |
| `core/runtime_guard.py` | `nexora/runtime_guard.py` | Gerçek işlem ortam değişkeni açıksa istemciyi durdurur |
| `paper/fifo_matcher.py` | `nexora/fifo_matcher.py` | SOL/WSOL tek kuyruk |
| `wallets/wallet_fifo_adapter.py`, `native_sol_fifo_adapter.py` | aynı adlarla | Cüzdan analizinin temeli |
| **`core/logger.py` (SensitiveDataFilter)** | **`nexora/gizle.py` (bu denetimde eklendi)** | Sunucu ve takip çıktısının tamamı ile veritabanına yazılan hata metinleri maskeleniyor |

## 3. Taşınmayanlar ve neden

| Eski bölüm | Karar | Gerekçe |
|---|---|---|
| `paper/*` mum/ATR hattı, `data/binance_*`, kökteki `shared_analysis`, `momentum_quality`, `reversal_risk`, `candidate_scoring_v2` | Taşınmadı | ETHUSDT mum tabanlı teknik analiz; Solana cüzdan kopyalama amacıyla ilgisiz |
| `wallets/wallet_history_*` (≈45 dosya, checkpoint'li geçmiş tarama) | Ayrı tutuldu | Proje kuralı: geçmiş tarama canlı takipten ayrı kalmalı. Yeni sistem geçmişi istek üzerine `getTransactionsForAddress` ile okuyor |
| `wallets/*ranking*`, `*scoring*` (≈15 varyant) | Taşınmadı | Aynı işi yapan çok sayıda deneysel sıralama; yeni sistemde tek, test edilmiş `wallet_analysis` (karar + skor + bot tespiti + düşüş) var |
| `wallets/wallet_hunter_*` (≈20 dosya) | Fikir alındı | Yeni `cuzdan_kesif.py` daha dar bir yöntemle (erken alıcılar) aynı amaca hizmet ediyor. `account_filter` (program/PDA hesabı eleme) ileride keşif sonuçlarına uygulanabilir |
| eski `backend/` (FastAPI) ve eski `android/` | Yerini aldı | Termux'ta derlenemeyen pydantic bağımlılığı; yeni sunucu yalnızca standart kütüphane |
| `sitecustomize.py` (çevrimdışı koruma) | Not edildi | Geliştirme ortamında ağ ve üretim yolu erişimini kapatan denetim kancası; test ortamı için iyi bir fikir |

## 4. Riskler ve dikkat edilecekler

1. **Bekleyen silme planı (çalıştırılmamış).** `deletion_candidates.json` 868 dosya / 12,9 GB "hemen silinebilir" ve tarayıcı durduktan sonra 2.447 dosya / 8,2 GB "emeklilik" adayı listeliyor. Dosyada "silme komutu çalıştırılmadı" yazıyor. **Onayınız olmadan çalıştırılmamalı.** Silmeden önce eski üretim veritabanının (5,4 GB) yedeği doğrulanmalı.
2. **Yedek şifreleme anahtarı.** Plan `nexora_backups/nexora_age_identity.txt` dosyasını "korunacak" olarak işaretliyor. Bu dosya kaybolursa şifreli eski yedekler açılamaz. Telefon dışında güvenli bir yerde ikinci kopyası olmalı (bana gönderilmemeli).
3. **Eski üretim** `~/tradebot_multi_ai` altında ve ayrı çalışıyor. Yeni sistem ona hiçbir şekilde bağlanmıyor; bu ayrım korunmalı.
4. **Eski testlerde 14 hata** vardı (eksik üretim veritabanı ve süre aşımı kaynaklı; ikisi düzeltilmiş). Eski kod yeniden kullanılacaksa önce bu testler temizlenmeli.
5. Eski ayarlarda `NEXORA_GROK_API_KEY` alanı var: Grok entegrasyonu daha önce de planlanmış, ancak kodu yok.

## 5. Sonuç

Eski sistemin Solana çekirdeği (istemci, çözücü, FIFO) zaten yeni sistemin temelini oluşturuyor. Kalan büyük bölüm ya farklı bir stratejiye (mum tabanlı) ya da yeni sistemde bilinçli olarak ayrı tutulan geçmiş taramaya ait. Bu denetimle bir parça daha (gizli bilgi maskeleme) taşındı. Eski sistemde yeni sistemin kaçırdığı kritik bir özellik bulunmadı; en önemli açık konu, çalıştırılmamış silme planı ve yedek şifreleme anahtarının güvenliği.
