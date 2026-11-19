# NEXORA — 7 Araçlı AI Sinyal Hattı V1

**Çalışma dalı:** `codex/nexora-lab-ai-signals-v1`; PR #18, taslak.  
**Ana sınır:** Salt okunur piyasa verisi → açıklanabilir makine öğrenmesi → **yalnızca** ayrı 100 USDT sanal işlemler. **Gerçek alım-satım, cüzdan imzası, gönderim ve fon yönetimi yoktur.**  
**Ön koşullar:** PR #16 (7 araç) ve PR #17 (APK ağ/kasa güvenliği). İkisi de bu PR'ın altında; `main`, çalışan Termux/Oracle, veritabanları ve anahtarlar değişmedi.

## 1. Sinyal → karar → etki hattı

```text
Jupiter yeni havuz gözlemi (yeni mint doğumu kanıtı değil)
   ↓
Helius finalized mint güvenliği, Jupiter alış VE satış kotasyonu
   ↓
Zorunlu risk kapısı: likidite >= 20k USD, iki yönlü kayıp <= %8,
                    iki yönlü fiyat etkisi <= %2, kotasyon yaşı <= 30sn
   ↓
7 özelliğin girişte mühürlenmesi (gelecekteki satış sonucu YOK)
   ↓
AI modeli: önceden olgunlaşmış sanal çalışma geçmişinden öğrenir
   ├─ yeterli / ileri test geçmedi → gölge izleme, kararı değiştirmez
   └─ ileri test ve risk geçti → sadece yeni sanal alımları önceliklendirir
                                  veya şüphe halinde reddeder
   ↓
Özel 100 USDT paper defteri: tek çalışmada 4 USDT + varsayımsal ücret
   ↓
Girişte sabit çıkış ufku: başlangıçta 5dk, ancak ileri test kanıtı varsa
                        geçmişle seçilen 5/15/30/60dk
   ↓
Her 30sn bağımsız sanal satış kotasyonlarının izlenmesi
   ├─ önceden seçilen ufukta sağlam kotasyon → sanal SAT SİNYALİ
   ├─ satış kotasyonu yok → EXIT_UNAVAILABLE (asla sahte satış/kâr yok)
   └─ diğer ufuklar → birbirinden bağımsız karşı-olgusal araştırma
   ↓
Maliyet sonrası net stres, ileri test ve düşüş ölçümü, kurucuya özel Lab
```

## 2. Yedi aracın görev ayrımı

| Araç | Sinyale katkı | **Sahte güven engeli** |
|---|---|---|
| Raydium SDK V2 | İzole salt-okunur havuz varlığı / kaynak araştırması | Havuz görülmesi token onayı veya likidite garantisi değildir; canlı bağımsız değerlendirme gerektirir |
| Orca Whirlpools | İzole alternatif DEX/havuz gözlemi | Mevcut CLI salt-okunur; yüksek puan tek başına AL değildir |
| solana-py | İsteğe bağlı bağımsız token mint account kontrolü | Ana Helius mint güvenlik kapısının yerine geçemez |
| VectorBT | Tarihsel mumlarda ücret/kayma uygulanmış next-bar-open strateji karşılaştırması | Mumun sonradan bilinen yüksek fiyatıyla geçmiş işlem yaptırılmaz; canlı fırsat puanı değildir |
| DuckDB | Maliyetli/başarılı sanal örneklerde grup/segment değerlendirmesi | SQL gruplaması geleceği tahmin etmez |
| QuantStats | Sanal araştırmanın zirveden düşüşü, günlük bazda Sharpe ve risk ölçümü | Kısa/eksik veriyle risk modeli onaylanmaz |
| Lightweight Charts | APK'da yerel çizim, sanal defter/ileri test/AI doğrulama göstergeleri | Grafik, gerçekleşmiş satış veya kâr kanıtı değildir |

**Doğrudan yeni paper kararına giren kaynaklar** şu anda Jupiter ilk-havuz verisi, Helius mint hesabı ve Jupiter'in **iki yönlü taze kotasyonlarıdır**. Diğer SDK/analitik araçlar isteğe bağlı ayrı modüllerdir; depoda bulunmaları canlı üretimde çalıştıklarını göstermez. Özellikle kullanıcı verisi, X/Telegram reklam köprüsü veya haber spekülasyonu bir kontrolsüz gerçek emir tetikleyemez.

## 3. Gerçek yapay zekâ mekanizması

Bu sürüm bir büyük dil modeli değil, **girişteki 7 sayısal özellik üzerinde örnek benzerliği ile öğrenen, düzenlileştirilmiş istatistiksel makine öğrenmesi** kullanır:

1. Giriş özellikleri (0–1): likidite kalitesi, iki yönlü kayıp kalitesi, alış fiyat etkisi, satış fiyat etkisi, organik puan, ilk yoğun sahiplik ve geliştirici yoğunluğu. Organik/dağılım verisi eksikse **0,5 nötr** kullanılır, onay olduğu iddia edilmez.
2. Model, geçmiş sanal işlemde **girişten önce** kaydedilmiş `lab_pretrade_features`, giriş anında seçilmiş `planned_exit_horizon_min` ve `plan_decided_at` olmadan eğitim örneği kabul etmez.
3. Bir etiket ancak girişten **60dk+120sn** sonra olgun sayılır; yani diğer üç ufkun sonradan oluşan sonuçları ilk kararı etkileyemez.
4. Yalnız girişte seçilmiş **TEK** ufkun satış kotasyonundan `net_usdt` etiketi oluşturulur. Kotasyon eksikse bu **tam maliyet kaybı stres senaryosudur**, gerçekte gerçekleşmiş zarar değildir. Tek aşırı olumlu sonuç 2× giriş maliyeti ile sınırlandırılır.
5. Benzerlik modeli ağırlıklandırılmış uzaklık, geçmiş genel ortalamasına **10 örneklik güven azaltma** ve belirsizlik alt sınırı kullanır. Modelin tahmini **kazanma olasılığı değildir**.
6. Her tarihsel karar anında sadece o ana dek olgunlaşmış eski örneklerle yeniden hesaplama yapılır (walk-forward). En az 30 geçmiş örnek, en az 20 ileri kontrol, en az 10 seçilmiş sanal örnek, ≥%90 geçerli kotasyon, pozitif muhafazakâr stres alt sınırı ve ≤%10 sıralı stres düşüşü gerekir.
7. Bu kapılar geçmeden AI `SHADOW_LEARNING` modundadır. Etkisi sıfırdır: sadece puan ve gözlem üretir. Kapılar geçince `PAPER_FILTER_VALIDATED` yalnız yeni **sanal** adayları önceliklendirir / düşük beklentilileri reddeder. Sağlık ve risk kapıları **daima önce gelir**.

**Seçim yanlılığı uyarısı:** Modelin öğrendiği örnekler, mevcut risk kapısını geçen ve izlenen tokenlarla sınırlıdır. Reddedilen adayların karşı-olgusal sonuçları bilinmediği için bu sistem tüm piyasanın en iyi tokenlarını seçtiğini ispatlayamaz. İleri testten geçmesi bile gerçek zincir icrasını garanti etmez. Geniş alt küme ve farklı piyasa dönemleriyle yeni dış-örnek test gereklidir.

## 4. Sanal AL ve SAT etkisi — kesin ayrım

- **AL:** Model hiçbir koşulda tek başına yeni pozisyon oluşturmaz. `auto_decision.entry_signal` Helius/Jupiter kanıtıyla `OPEN_PAPER_STUDY` verirse bağımsız `paper_watch` defterine **en fazla 1 sanal giriş/tur** kaydedilebilir. 100 USDT toplam, 5 eşzamanlı araştırma ve 4 USDT giriş maliyeti korunur.
- **SAT:** Önceden seçilen ufuktaki satış kotasyonu geçerliyse `precommitted_exit.action=PAPER_SELL_SIGNAL` kaydedilir. Başka ufuk daha çok kazandı diye plan değiştirilmez. Kotasyon/rota yoksa `EXIT_UNAVAILABLE`; stop-loss'in gerçekten dolduğu iddia edilmez.
- **İzleme:** `tools/strategy_lab/ai_paper_runner.py` gerçek fiyat kotasyonlarını en fazla 3/tur yoklar ve ayrı aday araştırmasını varsayılan 180 saniyede bir yapar; 30 saniyelik yoklama 120 saniyelik ufuk pencerelerini izler.
- **Rapor:** `/admin/strategy-lab` yalnız kurucuya toplam örnek, AI mod, ileri test ortalama/stres alt sınırı, sanal SAT/EXIT_UNAVAILABLE sayaçlarını gösterir. Yeni AI raporu mint/cüzdan/gizli anahtarları içermez.

## 5. Etkinleştirme (gelecekte ayrı test ortamında; burada ÇALIŞTIRILMADI)

Var olan iki ayrı opsiyonel worker yerine **tek birleşik worker** kullanılabilir.
Mevcut çalışan worker'ı durdurma veya değiştirerek iki tanesini aynı deftere bağlama.
Operatör açıkça seçene kadar hiçbir zamanlayıcı veya sunucu servisi otomatik başlamaz.

```sh
# YALNIZCA ayrı, test amaçlı ortam; anahtarları komut satırına yazmayın.
# NEXORA_LAB_AUTO_PAPER=1
# SOCIAL_RESEARCH_LIVE_ENABLED=1
# SOCIAL_PAPER_WATCH_ENABLED=1
# Helius/Jupiter anahtarları yalnız özel env dosyasında
# SOCIAL_PAPER_WATCH_PATH=<mevcut özel klasörde mutlak yeni .json>
python -B tools/strategy_lab/ai_paper_runner.py --once
# İsteğe bağlı, açık izinle kalıcı:
# python -B tools/strategy_lab/ai_paper_runner.py --poll-seconds 30 --scan-seconds 180
```

Bu komut mevcut Oracle/Termux üzerinde **çalıştırılmadı**. Üretim servisi, veritabanı ve cüzdan anahtarı erişimi yoktur.

## 6. Test / kabul / eksikler

- `backend/tests/test_strategy_lab_signal_intelligence.py`: gelecek verinin eğitime girmemesi; eski planı sonradan seçememe; eksik kotasyonun stres kaybı; kâr yokken AI filtresi açılmaması; yanıltıcı alanların reddi.
- `backend/tests/test_strategy_lab_ai_runner.py`: önce sanal SAT kotasyonu kontrolü, sonra sanal AL adayı; `scan=False` ise yeni alım yok; riskli snapshot reddi.
- `backend/tests/test_strategy_lab_auto_paper.py`: başlangıç giriş/çıkış planı; mevcut dedup ve güvenlik kontrolleri.
- GitHub Actions backend ve Android testleri; ayrıca APK derlemesi. **CI yalnız sentetik testi doğrular.**
- Gerçek kâr için gerekenler: ileri dönük 30+ günlük veri, gerçek gecikme ve gas/MEV/transaction failure, 5dk altı anlık stop teması, piyasa rejimi değişimi, gizli örneklem, likidite çıkarma ve çıkışsızlık stres testleri. Uygulamayı gerçek fonla işlem yapan sistem gibi lanse etmeyin.

**Üretim kararı:** PR #16, #17 ve #18 `main`e otomatik birleştirilmez; HTTPS taşıması, release imzası, cihaz/sağlayıcı testleri ve kullanıcı onayı ayrı kapılardır.
