# Social Radar — read-only sunucu adaptörü

`GET /admin/social-radar` NEXORA'nın mevcut `kurucu` rol denetiminden geçer.
Üye rolüyle erişim 403'tür; API anahtarı veya kurucu oturumu gerekir.

İlk açılışta `SOCIAL_RADAR_SNAPSHOT` tanımlı değildir ve uç nokta beş
kaynağı `live_verified=false`, `alerts=[]` ve
`snapshot_status=BAGLANTI_BEKLENIYOR` olarak gösterir.
Bu, bağlantının çalıştığı ama gerçek sosyal veri olmadığı anlamına gelir.

Bir sonraki **ayrı ve açıkça yetkilendirilmiş** aşamada, bir veri işçisi
izinli X/Telegram ve diğer kaynaklarla gerçek gözlem yapıp SocialRadar.report()
sözleşmesinde `schema_version=1, mod=GOZLEM, read_only=true` olan
snapshot üretebilir. Ancak bu PR **işçi başlatmaz**, API çağrısı yapmaz,
üretim DB'ye yazmaz, ücretli veri toplamaz.

Sunucu tarafı yalnızca `SOCIAL_RADAR_SNAPSHOT` değişkeniyle belirtilen
JSON dosyasını her GET isteğinde salt okunur açar. En fazla 2 MB okur.
Geçerli snapshot son 15 dakika içinde üretilmiş olmalı; `MOCK` ve
eski kayıtlar canlı olarak kabul edilmez. Bir kaynak ancak
`status=OK`, `access_mode=LIVE_AUTHORIZED`,
`trust_status=verified`, `enabled=true`,
`live_verified=true` kanıt bayraklarının hepsi varsa bağlı sayılır.
Buradaki bayraklar operatörün kontrollü snapshot üreticisi tarafından
doldurulmalıdır; tek başına sosyal verinin bağımsız doğruluğunu kanıtlamaz.

Uyarılar en fazla 20 kayıtla, `VERIFIED` Solana mint ve gözlem zamanı
koşullarıyla sunulur. Ham metin, yazar kimliği ve gizli anahtarlar dışa
aktarılmaz. İstemci sadece görüntüler; otomatik trade/paper kararını etkilemez.

**Not:** `SOCIAL_RADAR_SNAPSHOT` özel anahtar veya hassas içerik değil,
yalnızca operatörün güvenli konuma koyduğu doğrulanmış JSON raporu
göstermelidir. Sağlayıcı kimlik doğrulaması ve gerçek data-gathering henüz
bağlanmadı. Bu uç noktanın derleme/test ve sunucuya dağıtımı ayrıca
incelenmelidir.
