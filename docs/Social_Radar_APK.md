# NEXORA APK — Solana Sosyal Radar

## Kapsam
Android Kotlin/Jetpack Compose uygulamasının **Keşfet > Sosyal AI** ekranına beş kaynak eklendi. Kaynak adları yalnızca konfigürasyon referansıdır. Uygulama sosyal platformlardan kendisi veri çekmez, anahtar saklamaz, gerçek veya paper işlem başlatmaz ve model kapısını açmaz.

## API sözleşmesi — sonraki backend entegrasyonu
`GET /admin/social-radar` sadece mevcut **kurucu** kimlik doğrulamasıyla okunmalıdır. Üyeye asla açılmamalıdır. Sunucu olmayan veya 404 dönen durumda Android kaynakları `Erişim bekleniyor` diye gösterir; sahte uyarı veya fiyat oluşturmaz.

Önerilen salt okunur yanıt:

```json
{
  "live_enabled": false,
  "sources": [
    {
      "source_id": "solana_early_trending",
      "handle": "solearlytrending",
      "access_status": "UNAVAILABLE",
      "live_verified": false,
      "last_seen": null
    }
  ],
  "alerts": []
}
```

Beş `source_id`: `solana_early_trending`, `kolscope`, `ansem`, `lookonchain`, `bubblemaps`.

`live_verified` yalnızca doğru kimliği doğrulanmış ve yetkili sağlayıcıdan erişimi gerçekten test edilmişse `true` olmalıdır. Yanıtta `sources`/`kaynaklar` ve `alerts`/`uyarilar` desteklenir. Uyarıda `classification`/`sinif`, `token_symbol`/`token`, `mint`/`token_mint` alanları bulunabilir. Eksik alanlar otomatik `BELIRSIZ` veya boş biçimde gösterilir.

## Durum
Bu dal **Android arayüz entegrasyonudur**. Uç nokta ayrı `codex/social-radar-server-v1` dalında hazırlanmıştır; bu dal ve Social AI motoru henüz `main`e birleştirilmemiştir. Issue #3 ve #4 içindeki Social AI backend geliştirmeleri şu anda ayrı yerel `codex/solana-social-ai-v1` dalındadır; GitHub'a aktarılıp gerçek, yetkili, salt okunur API uygulanmadan APK canlı sosyal veriye erişemez.

## Kabul
- `Keşfet > Sosyal AI` yalnızca kurucu ekranında görünür.
- Endpoint 404, 401, 403 veya ağ hatasında uygulama çökmez.
- Beş katalog öğesi bulunur, ama erişimi kanıtlanmayanlar bağlı gösterilmez.
- UI üzerinden veri yazma/emir başlatma kontrolü yoktur.
- `main`e merge, sunucu deploy, canlı API çağrısı yok; ayrı taslak PR.
