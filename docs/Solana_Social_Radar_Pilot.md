# NEXORA Solana Social Radar Pilot

Pilot, Social AI V1’in mint doğrulaması, Helius kanıtı, risk sınıflandırması ve maliyet sonrası gölge ölçümünü beş kaynaklı, salt okunur bir raporda kullanır. Canlı izleme varsayılan olarak kapalıdır. CLI, yerel fixture dosyasını okur ve JSON üretir. [GitHub görevi #4](https://github.com/hayatcavdan-png/Nexora-2-/issues/4)

## Çevrimdışı çalıştırma

```sh
cd backend
python3 -m nexora.social_ai.radar source-status
python3 -m nexora.social_ai.radar source-status --fixture tests/fixtures/social_radar.json
python3 -m nexora.social_ai.radar report --fixture tests/fixtures/social_radar.json
python3 -m unittest discover -s tests -p 'test_social*.py'
```

Fixture’da Ansem paylaşımı, KOLscope iletimi ve Lookonchain yeniden paylaşımı bir olaydır. Önceden gözlemlenmiş bağımsız Solana Early Trending paylaşımı, yayın sırası ve zincir koşulları sağlandığında ikinci sosyal teyidi verir. Bubblemaps örneğindeki iki cüzdanın alımı, Helius fixture’ındaki iki işlem ile doğrulanır. Örnekte ilk üç ufukta `AVANTAJ YOK`, 60 dakikada çıkış yetersizliği nedeniyle `UNKNOWN` elde edilir. Dış veri API çağrısı ve maliyeti 0’dır.

## Kaynaklar ve erişim

| Kaynak | Rol | Gerçek veri için gereken erişim | Canlı veri doğrulandı mı? |
| --- | --- | --- | --- |
| Telegram `@solearlytrending` | Trend keşfi | Kanal yöneticisinin onayı, yetkili bot ve sabit kanal kimliği veya izinli yerel export | Hayır |
| Telegram `@KOLscope` | KOL iletimi | Kanal yöneticisinin onayı, yetkili bot ve sabit kanal kimliği veya izinli yerel export | Hayır |
| X `@blknoiz06` (Ansem) | Influencer sinyali | Yetkili X API v2 uygulaması, bearer, okuma kredisi/kotası ve operatörce doğrulanmış sabit kullanıcı kimliği | Hayır |
| X `@lookonchain` | Zincir raporu | Yetkili X API v2 uygulaması, bearer, okuma kredisi/kotası ve operatörce doğrulanmış sabit kullanıcı kimliği | Hayır |
| X `@bubblemaps` | Cüzdan ilişkisi ve risk özeti | Yetkili X API v2 uygulaması, bearer, okuma kredisi/kotası ve operatörce doğrulanmış sabit kullanıcı kimliği | Hayır |

`source-status`, erişim kipini (`MOCK`, `LIVE_AUTHORIZED`, `UNAVAILABLE`), kimlik durumunu (`verified`, `unverified`, `blocked`), izin kapsamını, son denetimi, son gözlemi, gecikmeyi ve kota sayacını verir. `trust_status` sabit kaynak kimliğinin doğrulanmasını ifade eder. `live_verified` ancak adaptör geçerli bir gerçek paylaşımı kabul ederse `true` olur. Kimlik uyuşmazlığı veya yetki reddi `ERISIM_YOK`, gecikme ya da tamamlanmamış sayfa dizisi `VERI_GECIKTI`, yerel veya sağlayıcı kotası `KOTA`, doğrulanamayan sağlayıcı durumu `UNKNOWN` verir. Erişilemeyen kaynakların kapsama ve örnek sayıları `null` kalır.

### İzinli adaptör arayüzü

- `AuthorizedSources` yalnızca çağıranın açıkça verdiği `LiveOptions(SOCIAL_LIVE_ENABLED=True, ...)`, `Credentials` ve kaynak başına `SourceGrant(read_allowed=True, ...)` ile çağrı yapabilir. `read()` yerel anlık görüntüyü okur. `poll()` açıkça çağrıldığında sağlayıcı denetler. Kimlik bilgileri çalışma zamanında çağıran tarafından verilir.
- X, her sorgu turunda güncel handle’ı kayıtlı sayısal kimlikle karşılaştırır ve dönen her paylaşımın yazar kimliğini denetler. Varsayılan yöntem kullanıcı zaman akışıdır. `x_recent_search=True` ile kaynağa özgü recent search seçilebilir. Bir çağrıda en fazla 10 paylaşım alınır. Başarıyla tamamlanan sayfa dizisinden sonra `since_id` ilerler. Bir sayfa anahtarı geçersizleşirse son tamamlanmış imleçten devam edilir. Sağlayıcı hatasında `Retry-After` veya artan bekleme uygulanır. [X v2 kullanıcı gönderileri](https://docs.x.com/x-api/users/get-posts), [Recent Search](https://docs.x.com/x-api/posts/search-recent-posts), [Alan seçimi](https://docs.x.com/x-api/fundamentals/fields)
- Telegram, `getMe`, `getChat` ve `getChatMember` ile sabit kanal kimliğini, handle’ı ve botun yönetici/kurucu üyeliğini doğrular. `ingest_telegram()`, `X-Telegram-Bot-Api-Secret-Token` başlığıyla doğrulanmış `channel_post` teslimlerini kabul eder. Kurulacak webhook alıcısı bu başlığı ve ayrıştırılmış güncellemeyi metoda geçirir. Telegram geçici hata bildirirse erişim durumu `KOTA` veya `UNKNOWN` olur. Teslimat geçmişi, webhook kurulumu ve erişim değişikliklerinin işletimi dağıtım katmanının sorumluluğundadır. [Telegram Bot API](https://core.telegram.org/bots/api)
- Canlı durumda imleç, 60 saniyelik kontrol önbelleği, 24 saatlik normalize olay önbelleği ve günlük sayaçlar bellektedir. Yerel tavan kaynak başına UTC günde 48 istektir. X ayrıca tüm X kaynaklarını kapsayan ve varsayılanı 0 USD olan günlük tahmini harcama sınırı kullanır. Hesap kimliği veya yetki denetimi başarısız olduğunda kaynak önbelleği temizlenir.
- Varsayımsal örnek, üç X kaynağının her biri için günde dört kullanıcı sorgusu ve ardından on gönderili bir sayfa varsayar. Günlük 12 kullanıcı okuması × 0,010 USD ve 120 gönderi okuması × 0,005 USD, günlük **0,72 USD** ve 30 günde **21,60 USD** eder. Hesap, sağlayıcının faturalandırma deduplikasyonundan doğabilecek indirimleri hesaba katmaz. Telegram Bot API okuma tarafında bu örneğe ek birim maliyet konulmamıştır. [X API tarifesi](https://docs.x.com/x-api/getting-started/pricing), [Telegram Bot Platformu](https://core.telegram.org/bots/)

## Fixture ve kanıt kuralları

- `as_of` raporun UTC Unix saniyesi cinsinden kesim zamanıdır. `sources` her kaynak için `status`, `authorized`, `expected_account_id`, `account` (`id`, `username`), `last_checked`, isteğe bağlı `coverage_from` ve `controller` taşır. `items` satırlarında `fetched_at`, `observed_at` ve sağlayıcı biçiminde `post` bulunur. Telegram’ın izinli yerel export’u bu sözleşmeye göre `channel_post` nesnelerine normalize edilir. Export saati, daha eski bir ilk gözlem varmış gibi geriye yazılmaz. `controller` aynı kişiye veya kuruluşa bağlı hesapları ortak kimliğe bağlayan, operatörce denetlenen metadata’dır. `providers`, V1 ile aynı `token_profile`, `helius`, `jupiter`, `dex` ve `quotes` kanıt biçimini kullanır. [V1 fixture sözleşmesi](Solana_Social_AI_V1.md)
- Yerel grup birleştirme, sağlayıcıya ait repost/forward ve düzenleme kimliklerini, KOLscope’un tekil X gönderi bağlantısını, 15 dakikalık aynı metin veya aynı denetlenmiş kontrol grubu tekrarını kullanır. İlk doğrulanmış gözlem gölge olayının saatidir. Daha sonra görülen iletimler dağılım ve kaynak atfını açıklayabilir. Kararlar yalnızca ilk gözlem saatinde bilinen kanıta dayanır. İletimler sosyal teyit oyu vermez. 120 saniyede en az üç hesapta görülen kopya yayılımı bot benzeri koordinasyon bulgusudur. Bulgular, bir hesabın gerçekten bot olduğunu kanıtlamaz.
- Gözlem, yayın ve çekim saatleri ayrı tutulur. Tek tam Solana adresi, gözlem öncesinde edinilmiş kanonik profil ve geçerli SPL mint hesabıyla doğrulanır. `mint:` veya `CA:` etiketleri minti, `wallet:` veya `cüzdan:` cüzdan iddialarını ayırır. Ad ve sembol tek başına eşleme girdisi oluşturmaz. Cüzdan iddiaları, aynı mint için gözlem öncesinde edinilmiş Helius alım kanıtı ve varsa küme bilgisiyle sınanır. Geç kanıt, eksik likidite veya belirsiz risk işareti ayrı gerekçelerle gösterilir.
- Ham paylaşım, özel Telegram URL’si ve ham hesap/cüzdan kimliği rapor ve normalize önbellekten çıkarılır. Kimlik ve metin karşılaştırmaları özetlerle yapılır. Bağlantılar izlenmez. Canlı sağlayıcının bildirmediği ücretli görünürlük veya yanıltıcılık `UNKNOWN` kalır. Fixture’daki `paid` ve `misleading` alanları sentetik ek açıklamalardır.
- `ufuk_ozeti`, zamanında görülmüş tekil olayların 5, 15, 30 ve 60 dakika maliyet sonrası sonucunu tümünü kopyala, işlem yapma ve sosyal filtre politikalarında karşılaştırır. V1 ölçülebilir net farkın işaretinden `AVANTAJ YOK` sonucunu çıkarır. Eksik veya doğrulanmamış olumlu fark `UNKNOWN` kalır. Bu sürüm dış kanıt için yeni istek açmaz.

## Rapor ve APK kartı sözleşmesi

`SocialRadar`, kaynak ve zincir kanıtı okuyucularından `source_status()` ve `report()` üretir. JSON kökünde `schema_version=1`, `as_of`, `mod`, `read_only`, `durum`, `sources`, `olaylar`, `kaynak_performansi`, `ufuk_ozeti` ve `avantaj` bulunur. Erişim modu ve kota kartı, her kaynak için `sources[].status`, `access_mode`, `last_seen`, `lag_seconds` ve `retry_at` değerlerini gösterir. Olay kartı ilk kaynak, üç zaman damgası, mint durumu, risk sınıfı, gerekçeler, zincir kanıtı ve dört ufkun net USDC sonucunu gösterir. Bilinmeyen değerler kartta `UNKNOWN` olarak gösterilir.

Kaynak performansı, gözlem gecikmesi medyanını, tekil olay ve tekrar sayılarını, kaynağın bilinen kapsama aralığı içinde ilk gözleme katkısını, yanlış mint ve belirsizlik oranlarını ve iki tabana göre net farkı verir. Ekonomik sonuç ilk gözleyen kaynağa atanır. Yanlış mint oranının paydası kanıtla sınanmış mintlerdir. 30 dakika erken uyarı doğruluğu, maliyet sonrası pozitif sonucu gösteren uyarıların ölçüsüdür. Yüzde sadece bütün uyarılar ölçüldüğünde ve en az 10 farklı mint bulunduğunda yayımlanır. Takipçi sayısı, etkileşim veya kanalın getiri beyanı başarı metriğine girmez.

Gelecekte isteğe bağlı ve kapalı varsayılanlı `GET /admin/social-radar`, mevcut sunucunun `kurucu` rolüyle önceden hazırlanmış bu raporu okuyabilir. Özellik kapalıysa 404, kimlik yoksa 401, üye rolü varsa 403 tasarlanmıştır. Rapor yoksa 200 yanıtında `durum=UNKNOWN` ve boş olay listesi gösterilir. Rota, Android kartı ve dağıtımı pilotun bu uygulamasında devreye alınmamıştır. Kalıcı imleç ve kota deposu, gerçek kaynak izinleri ve canlı örneklem doğrulaması sonraki entegrasyona kalır.
