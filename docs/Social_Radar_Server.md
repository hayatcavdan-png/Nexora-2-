# Social Radar — read-only sunucu adaptörü

`GET /admin/social-radar` NEXORA'nın mevcut `kurucu` rol denetiminden geçer.
Üye için 403, geçerli kimlik yoksa 401 döner. Yanıtlara `Cache-Control: no-store` eklenir.

İlk açılışta `SOCIAL_RADAR_SNAPSHOT` tanımlı değildir ve uç nokta beş
kaynağı `live_verified=false`, `alerts=[]` ve
`snapshot_status=BAGLANTI_BEKLENIYOR` olarak gösterir.
Bu, bağlantının çalıştığı ama gerçek sosyal veri olmadığı anlamına gelir.

Bir sonraki **ayrı ve açıkça yetkilendirilmiş** aşamada, bir veri işçisi
izinli X/Telegram ve diğer kaynaklarla gerçek gözlem yapıp SocialRadar.report()
sözleşmesinde `schema_version=1, mod=GOZLEM, read_only=true` olan
snapshot üretebilir. Ancak bu PR **işçi başlatmaz**, API çağrısı yapmaz,
üretim DB'ye yazmaz, ücretli veri toplamaz.

Varsayılan `SOCIAL_LIVE_ENABLED=0` iken bir snapshot yolu ayarlanırsa
`CANLI_IZLEME_KAPALI`, beş kapalı kaynak ve boş uyarı listesi döner.
İleride açıkça onaylanan `SOCIAL_LIVE_ENABLED=1` yapılandırmasında sunucu
yalnızca `SOCIAL_RADAR_SNAPSHOT` ile belirtilen normal JSON dosyasını
salt okunur açar. Boyut sınırı 2 MB'dir.
Geçerli snapshot son 15 dakika içinde üretilmiş olmalı; `MOCK` ve
eski kayıtlar canlı olarak kabul edilmez. Bir kaynak ancak
`status=OK`, `access_mode=LIVE_AUTHORIZED`,
`trust_status=verified`, `enabled=true`,
`live_verified=true` kanıt bayraklarının hepsi, benzersiz kaynak kimliği
ve son 15 dakikada snapshot kesiminden önce yapılmış bir kontrol varsa bağlı sayılır.
Buradaki bayraklar operatörün kontrollü snapshot üreticisi tarafından
doldurulmalıdır; tek başına sosyal verinin bağımsız doğruluğunu kanıtlamaz.

API, son 24 saat içindeki zamanında görülmüş ve `VERIFIED` mint kanıtı olan
en yeni 20 uyarıyı döndürür. Her kayıtta `shadow_results` altında
`5dk`, `15dk`, `30dk` ve `60dk` sonuçları bulunur. Eksik ölçümler
`UNKNOWN`, vadesi gelmeyenler `PENDING` ve doğrulanmış ölçümler `OK`
olarak döner. Yalnızca `OK` için net USDC ve getiri yüzdesi sayısaldır.
API kontrollü gerekçe kodlarını ve sayısal ölçüm özetlerini döndürür.

**Not:** `SOCIAL_RADAR_SNAPSHOT` özel anahtar veya hassas içerik değil,
yalnızca operatörün güvenli konuma koyduğu doğrulanmış JSON raporu
göstermelidir. Sağlayıcı kimlik doğrulaması ve gerçek data-gathering henüz
bağlanmadı. Bu uç noktanın derleme/test ve sunucuya dağıtımı ayrıca
incelenmelidir.
