# NEXORA — Strateji Laboratuvarı otomatik karar kapısı (V1)

**Dal:** `codex/nexora-strategy-lab-seven-tools-v1` (PR #16, taslak).  
**Uygulama türü:** otomatik **sanal alım ve sanal satış sinyalleri**; gerçek para emri değil.  
**İlk dağıtım:** mevcut sunucu, telefon APK'sı, aktif Termux süreci, üretim SQLite'ı veya `main` otomatik değişmez.

## Yedi araç nasıl en iyi kullanılabilir?

1. **Raydium SDK V2 / Orca Whirlpools:** Likidite havuzlarının varlığını, yapısını, gelişimini **salt okunur** analiz et. Havuz bulunması doğrudan satın alma onayı değildir. Mevcut V1 yalnızca mint bazlı havuz sorgular; canlı otomatik emir girişi değildir.
2. **solana-py:** Helius/Solana RPC üzerinden mint hesabı, yetki ve risk delili doğrula. Doğrulanamayan mint geçemez. Anahtar/signer kullanılmaz.
3. **VectorBT:** Geçmiş mumlarda birçok stratejiyi ileriye bakma hatası olmadan simüle et; eğitim/test dönemlerini ayır. Bir tokenın canlı getirisi ispatlanmaz.
4. **DuckDB:** Cüzdan, havuz, maliyet ve sanal strateji sonuçlarını büyük veri analiziyle karşılaştır. Üretim SQLite dosyası bu modülce açılmaz.
5. **QuantStats:** Komisyon sonrasındaki sanal portföyde maksimum düşüş, risk ve tutarlılığı ölç. Eksik örnekle Sharpe veya başarı ilan edilmez.
6. **Lightweight Charts:** Kurucuya özel Android `Keşfet → Lab` sayfasında aday, strateji ve sanal sermaye grafiğini sun. Gerçekleşmemiş sonucu gerçek kâr diye göstermemelidir.

## Çalışan kod entegrasyonu

```text
Jupiter yeni havuz adayı
  → Helius mint + dağılım denetimi
  → Jupiter iki yönlü alış/satış kotasyonu
  → auto_decision.entry_signal (yeni, zorunlu, fail-closed)
  → auto_paper.cycle (en fazla bir aday/tur, kaliteye göre sırala)
  → bağımsız 100 USDT paper_watch JSON defteri
  → sosyal paper worker 5 / 15 / 30 / 60 dakika kotasyonları
  → auto_decision.exit_signal (STOP / TAKE / TIME / HOLD / UNAVAILABLE)
  → ayrı sanal rapor: **gerçek emir YOK**
```

Otomatik paper girişinde zorunlu kanıtlar:
- Jupiter/Helius'tan `READ_ONLY_RESEARCH` + `RESEARCH_CANDIDATE`; quote-only, imzasız ve gerçek işlem yapılmamış olması;
- 30 saniyeden eski olmayan iki yönlü kotasyon;
- **en az 20.000 USD** gözlenen likidite;
- **en fazla %8** alış/satış rotası kayıp tahmini;
- iki tarafta da **en fazla %2** fiyat etkisi;
- miktarın, USDT karşılığının ve round-trip oranının birbiriyle tutarlı olması;
- USDT, USDC ve WSOL'un yeni memecoin gibi otomatik alıma girmemesi.

Bir turda **en fazla 1 yeni sanal çalışma** açılır. Mevcut 100 USDT başlangıç bakiyesi, **4 USDT** sanal giriş, 5 eşzamanlı çalışmayla sınırlandırma, tekrar-mint engeli, özel 0600 dosya modu ve kayıt kilidi korunur.

İzlenen satış teklifinde: giriş maliyetine göre tamponlu sanal net getiri **−%8** veya altındaysa `STOP_LOSS`, **+%16** veya üstündeyse `TAKE_PROFIT`, 60 dakika geçtiyse `TIME_LIMIT` sanal SAT sinyali verilir. Geçerli çıkış kotasyonu yoksa `EXIT_UNAVAILABLE` denir; **satış yapılmış gibi gösterilmez**. Mevcut dört bağımsız 5/15/30/60 dk karşı-olgusal araştırma sonucu ve bakiye muhasebesi değişmez.

Bu eşikler **başlangıç araştırma parametreleridir**; kazandırdığı ispatlanmış değerler değildir. Gerçek stop-loss slippage, frontrunning, MEV, kopan RPC veya likidite kaybından dolayı gerçekleşmeyebilir.

## Canlı emir için ayrı kabul kapısı

Bu dalda `sendTransaction`, Jupiter `execute`, özel anahtar, imza veya transfer kodu **eklenmedi**. Mevcut `backend/nexora/emir.py` modülü imzasız teklif hazırlama/simülasyon işlevindedir. Gerçek otomatik alım-satım, bu sistemin **ayrı bir dağıtım ve kabul aşaması** olacaktır.

Önerilen sıra:
1. Risk kapısıyla **ağsız/sentetik** test; GitHub Actions.
2. Elde edilen gerçek kotasyonlarla **ayrı** 100 USDT sanal portföy; sürekli gözlem, tekrar eden olay denetimi, yeterli örnek sayısı, işlemler sonrası maliyet/düşüş istatistiği.
3. Gerçek cihazda kurucu oturumu, anlık izleme, durdurma düğmesi, risk limiti ve zincirden gerçekleşme uzlaştırma testleri.
4. Ancak ayrı yetki ve belirli limitlerle, küçük tutarlı gerçek işlem modunun açılması değerlendirilebilir. Bir backtest veya SDK import testi gerçek işlem güvenliği için yeterli değildir.

## Etkinleştirme ve müdahale sınırları

`tools/strategy_lab/auto_paper.py` mevcut davranışındaki gibi varsayılan **kapalıdır**. Ayrı operatör ortamında `NEXORA_LAB_AUTO_PAPER=1`, `SOCIAL_RESEARCH_LIVE_ENABLED=1`, `SOCIAL_PAPER_WATCH_ENABLED=1` ve mutlak `SOCIAL_PAPER_WATCH_PATH` ile, Helius/Jupiter anahtarları güvenli ortam değişkenlerinden verilirse başlatılabilir. Bu belgede anahtarlar ve herhangi bir fon aktarımı yoktur.

**Bağımsız paper çıkış kotasyonları** `tools/social_paper/worker.py` ile takip edilir. CI, canlı sağlayıcı ve gerçek telefonda çalıştırma yerine ağsız sentetik testler yapar.

**Başarı kriteri:** Sonuçlar yalnızca olumlu işlemleri değil, reddedilmiş sinyalleri, likidite kaybını, kaçırılan kotasyonları, komisyonu, tazelik sorununu ve stop kaymasını da ölçmelidir. `AUTO_BUY/SELL` sinyalinin üretilmesi, getirinin gerçekleştiğini kanıtlamaz.
