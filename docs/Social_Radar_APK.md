# NEXORA APK — Solana Sosyal Radar

## Kapsam
Android Kotlin/Jetpack Compose uygulamasının **Keşfet > Sosyal AI** ekranına beş kaynak eklendi. Kaynak adları yalnızca konfigürasyon referansıdır. Uygulama sosyal platformlardan kendisi veri çekmez, anahtar saklamaz, gerçek veya paper işlem başlatmaz ve model kapısını açmaz.

## API sözleşmesi

`GET /admin/social-radar` mevcut **kurucu** API anahtarını veya kurucu oturumunu kabul eder. Üye için 403, geçerli kimliği olmayan istek için 401 döner. Eski sunucudan 404 geldiğinde Android kaynakları `Erişim bekleniyor` durumunda gösterir.

Aşağıdaki örnek, varsayılan yanıtın tek kaynaklı bir kesitidir.

```json
{
  "schema_version": 1,
  "read_only": true,
  "live_enabled": false,
  "snapshot_status": "BAGLANTI_BEKLENIYOR",
  "sources": [
    {
      "source_id": "solana_early_trending",
      "handle": "@solearlytrending",
      "status": "ERISIM_YOK",
      "access_status": "ERISIM_YOK",
      "live_verified": false,
      "last_seen": null
    }
  ],
  "alerts": []
}
```

Beş `source_id`: `solana_early_trending`, `kolscope`, `ansem`, `lookonchain`, `bubblemaps`.

Android, `schema_version=1` ve `read_only=true` olan yanıtta `sources` ve `alerts` dizilerini okur. Kaynak yalnızca sunucu canlı erişim bildiriyorsa ve katalog kimliği, `status=OK`, `access_status=LIVE_AUTHORIZED`, `live_verified=true` birlikte eşleşiyorsa bağlı görünür. Kart, uyarının Solana mintini (`token_mint`), gözlem zamanını, sınıfını ve gerekçelerini gösterir. 5/15/30/60 dk seçimi, `shadow_results` içindeki ilgili sonuç için ölçümü, bekleme zamanını veya eksik veri durumunu gösterir.

## Durum

`codex/social-radar-release-review` dalı ekranı, uç noktayı ve çevrimdışı Social AI motorunu birlikte içerir. İlk sürümün kaynak sayacı 0/5, uyarı listesi boştur. [Sunucu sözleşmesi](Social_Radar_Server.md) ve [yerel sürüm raporu](Social_Radar_Release_Review.md).

## Kabul
- `Keşfet > Sosyal AI` yalnızca kurucu ekranında görünür.
- Endpoint 404, 401, 403 veya ağ hatasında uygulama çökmez.
- Beş katalog öğesi bulunur, ama erişimi kanıtlanmayanlar bağlı gösterilmez.
- UI üzerinden veri yazma/emir başlatma kontrolü yoktur.
