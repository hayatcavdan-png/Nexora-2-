# NEXORA — 7 araçlı Strateji Laboratuvarı (V1)

**Geliştirme dalı:** `codex/nexora-strategy-lab-seven-tools-v1`  
**İstek:** Mevcut hiçbir NEXORA bileşenini silmeden 7 aracı ayrı bir strateji araştırma bölümünde toplamak.  
**Durum:** GitHub **taslak PR #16**, üretime kurulmuş veya gerçek para ile işlem yapan uygulama **değil**.

## Araç → entegrasyon haritası

| Araç | Yer | Etkin görev | Çalışma sınırı |
|---|---|---|---|
| Raydium SDK V2 | `tools/strategy_lab/sdk/scan.mjs` | Girilen Solana mint'in Raydium havuzlarını sorgulamak | Node opt-in, **keypair yok**, havuz bulunması risk kapısını geçirmez |
| Orca Whirlpools | aynı Node CLI | Orca on-chain Whirlpool havuzlarını token A/B mint filtreleriyle sorgulamak | SDK opt-in, yalnızca hesap okuma |
| solana-py | `backend/nexora/strategy_lab/integrations.py` | `AsyncClient.get_account_info_json_parsed` ile mint sahibi/yetkileri güvenlik kontrolü | Sadece RPC GET mantığı, transaction/signer yok |
| VectorBT | `integrations.vectorbt_study` | 100 USDT ve geçmiş mum verisiyle işlemlerden **sonraki** mum açılışını kullanan sanal test | Veri dışarıdan sağlanır; canlı kâr ispatı değildir |
| DuckDB | `integrations.duckdb_summary` | Sanal sonuçlar üzerinde bellek içi SQL gruplaması | Üretim SQLite dosyaları açılmaz |
| QuantStats | `integrations.quantstats_summary` | Geçmiş sanal özsermaye serisinde maksimum düşüş ve günlük Sharpe | Veri yetersizse Sharpe belirtilmez |
| Lightweight Charts | `android/app/src/main/assets/strategy_lab/chart.html` | Android `Lab` sekmesinde **yerel** interaktif sanal sermaye çizgisi | JS dağıtımı APK derlemesinde, TradingView lisans atfı zorunlu |

## Yeni bölüm ve uyumluluk

- **APK:** `Keşfet → Lab` sekmesi kurucuya özel görünür. Diğer dört alt sekme, portföy, takip, Sosyal AI, mevcut 100 USDT sanal işlem modülü ve eski API'ler korunur.
- **HTTP:** `GET /admin/strategy-lab` yalnızca kurucunun API anahtarı/oturumu ile; `Cache-Control: no-store`. `STRATEGY_LAB_SNAPSHOT` yoksa sahte veri uydurulmaz, `NOT_CONFIGURED` gösterilir.
- **Çekirdek:** `backend/nexora/strategy_lab/engine.py` 100 USDT başlangıç, 4 USDT sanal giriş, ücret ve fiyat kayması varsayımı. Her sinyal ancak **bir sonraki mumun açılışında** sanal doluma dönüşür; mum içi tepe/diplerden geriye dönük kazanç yaratılmaz. Eksik veriyle puan verilmez.
- **Araç adaptörleri:** `integrations.py` isteğe bağlı importlar kullanır; üretim `backend/requirements.txt` **değişmedi**. Ayrı `backend/requirements-strategy-lab.txt` kullanılabilir. Node SDK da `tools/strategy_lab/sdk/package.json` içinde ayrıdır.
- **Raporlayıcı:** `tools/strategy_lab/run_once.py` yalnızca kullanıcının seçtiği küçük, tarih sıralı OHLC JSON dosyasını işler; var olan çıktı dosyasının üzerine **yazmaz**. Anahtarları/muhatap bilgilerini rapora geçirmez. Özel yazılan `.json` 0600 izinli.
- **Eski Telegram köprüsü:** eklenmez, geri getirilmez, üçüncü taraf kanal reklamı gösterilmez.

## Basit çevrimdışı araştırma örneği

Girdi (örnek, gerçek fiyat veya token verisi değildir):

```json
{
  "schema_version": 1,
  "bars": [
    {"ts": 1800000000, "open": "1.00", "high": "1.03", "low": "0.99", "close": "1.01"},
    {"ts": 1800000060, "open": "1.01", "high": "1.04", "low": "1.00", "close": "1.03"}
  ],
  "candidates": []
}
```

Çevrimdışı raporu elle üretme (sadece *ayrı* test ortamı, üretim dağıtımı değil):

```sh
python -B tools/strategy_lab/run_once.py --input /tmp/ohlc.json --output /tmp/nexora-lab-new.json
```

İleri VectorBT/DuckDB/QuantStats için ayrı Python sanal ortamına `backend/requirements-strategy-lab.txt` yüklenebilir ve `--optional-analytics` seçeneği kullanılabilir. SDK'lar ise `npm install --prefix tools/strategy_lab/sdk` ile **ayrı Node ortamında** kurulabilir. Gerçek RPC sorgusu `NEXORA_SDK_READONLY=1` verilmedikçe başlamaz; kaynak koda API anahtarı yazılmaz.

Kısa başlangıç senaryosu hiçbir sunucuda otomatik çalışmaz; böylece mevcut çalışan NEXORA sistemine, veri tabanlarına ve yedeklerine müdahale etmez.

## En önemli sınırlar

1. **NEXORA bu sürümle otomatik gerçek alım-satım yapmaz.** Fon aktarma, emir imzalama, `sendTransaction`, swap execute, private key veya cüzdan bilgisi yok.
2. Bu sürümde Raydium ve Orca SDK'ları *mint verilince havuz sorgular*. Zincirde yeni havuz oluştuğu anda gerçek zamanlı izleme/erken alarm ve memecoin pump olasılığı **doğrulanmış değildir**. Jupiter ilk havuz keşfi önceki PR #15'te ayrıdır.
3. Havuz sayısı/likiditesi bir tokenın güvenilir veya kârlı olduğunu kanıtlamaz; Helius/yetki/likidite/gerçek satış rotası teyidi gereklidir.
4. Tarihsel VectorBT sonuçları, modelin parametrelerine bağlıdır; yeterli veri olmadan Sharpe/başarı iddiası yok. Slippage ve ağ ücretlerinin *gerçek zamanlı* değeri ölçülmediği müddetçe varsayımdır.
5. TradingView Lightweight Charts lisansı atıf ve bağlantı ister; grafik altındaki atıf **zorunlu lisans bilgisi**, bağımsız kanal reklamı değildir.
6. Raydium SDK V2'nin **GPL-3.0 lisans koşulları** NEXORA'nın olası kapalı kaynak ticari sürümü açısından ayrıca incelenmelidir. Ayrı süreçte kullanmak tüm uyum sorumluluğunu ortadan kaldırmaz.
7. GitHub'da koda eklenmiş olması, telefonun kurulu APK'sının veya sunucunun yükseltildiği anlamına gelmez. Taslak PR birleştirilmeden/doğrulanmadan üretim değişmez.

## Test ve kabul

GitHub Actions `.github/workflows/social-radar-check.yml`:
- Normal Social AI + Strateji Lab birim, HTTP yetki ve create-only dosya testleri
- Tüm eski backend regresyon testleri, ağır bağımlılıklar yokken
- Android APK derlemesi + Lightweight Charts JS'in local olarak paketlenmesi
- İzole Python: VectorBT, DuckDB, QuantStats, solana-py gerçek import ve sentetik smoke testleri
- İzole Node: Raydium SDK V2, Orca Whirlpools import, salt okunur mod ve metadata normalizasyonu

**Başarılı GitHub CI, API anahtarlı üretim ortamının gerçekten çalıştığını veya canlı kârlılığı kanıtlamaz.** Cihaz testi ve operatörün veri kaynağı anahtarlarıyla izolasyon doğrulaması ayrı gereklidir.

## Resmî kaynaklar

- https://github.com/raydium-io/raydium-sdk-V2
- https://orca-so.github.io/whirlpools/
- https://michaelhly.com/solana-py/rpc/async_api/
- https://vectorbt.dev/getting-started/installation/
- https://duckdb.org/docs/
- https://pypi.org/project/quantstats/
- https://tradingview.github.io/lightweight-charts/docs/
