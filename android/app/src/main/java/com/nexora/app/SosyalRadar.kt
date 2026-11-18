package com.nexora.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private data class SosyalKaynak(
    val kimlik: String, val ad: String, val platform: String,
    val hesap: String, val amac: String
)

private val SOSYAL_KAYNAKLAR = listOf(
    SosyalKaynak("solana_early_trending", "Solana Early Trending", "Telegram", "solearlytrending", "Yeni Solana trendleri"),
    SosyalKaynak("kolscope", "KOLscope", "Telegram", "KOLscope", "Influencer çağrıları"),
    SosyalKaynak("ansem", "Ansem", "X", "blknoiz06", "Sosyal anlatı ve paylaşımlar"),
    SosyalKaynak("lookonchain", "Lookonchain", "X", "lookonchain", "Zincir analizi ve büyük işlemler"),
    SosyalKaynak("bubblemaps", "Bubblemaps", "X", "bubblemaps", "İlişkili cüzdan riskleri"),
)
private val SINIFLAR = mapOf(
    "SOSYAL_ERKEN_UYARI" to "Sosyal erken uyarı",
    "RISK_VETOSU_ADAYI" to "Risk vetosu adayı",
    "GOLGE_IZLE" to "Gölge izle",
    "BELIRSIZ" to "Belirsiz",
)
private val UFUKLAR = listOf(5, 15, 30, 60)
private val MINT_BICIMI = Regex("[1-9A-HJ-NP-Za-km-z]{32,44}")
private val SOSYAL_TARIH = DateTimeFormatter.ofPattern("dd.MM HH:mm")
    .withZone(ZoneId.systemDefault())

private fun JSONArray?.satirlar(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

private fun JSONObject?.sayi(alan: String): Double? =
    (this?.opt(alan) as? Number)?.toDouble()?.takeIf { it.isFinite() }

private fun tarih(saniye: Double?): String? =
    saniye?.takeIf { it > 0 && it < 253402300800.0 }?.let {
        SOSYAL_TARIH.format(Instant.ofEpochSecond(it.toLong()))
    }

private fun JSONObject?.dogrulanmisKaynak(): Boolean =
    this != null && opt("live_verified") == true && str("status") == "OK" && str("access_status") == "LIVE_AUTHORIZED"

private fun sonucDurumu(kod: String): String = when (kod) {
    "GIRIS_TEKLIFI_UNKNOWN" -> "Giriş teklifi doğrulanamadı"
    "CIKIS_TEKLIFI_UNKNOWN" -> "Çıkış teklifi doğrulanamadı"
    "CIKIS_YOLU_YOK" -> "Uygulanabilir çıkış yolu yok"
    "TEKLIF_TUTARSIZ" -> "Teklif ölçümü tutarsız"
    else -> "Ölçüm verisi yok"
}

private fun sunucuDurumu(kod: String): String = when (kod) {
    "CANLI_IZLEME_KAPALI" -> "Canlı izleme kapalı."
    "SNAPSHOT_OKUNAMADI" -> "Gözlem dosyası okunamadı."
    "SNAPSHOT_GECERSIZ" -> "Gözlem dosyası geçersiz."
    "SNAPSHOT_ESKI" -> "Gözlem verisi güncel değil."
    "CANLI_KANIT_YOK" -> "Canlı kaynak kanıtı yok."
    "ERISIM_DOGRULANMADI" -> "Kaynak erişimi doğrulanamadı."
    else -> "Kaynak bağlantısı bekleniyor."
}

@Composable
fun SosyalRadarEkrani(url: String, key: String) {
    val oturum = if (key.isBlank()) Oturum.deger else ""
    var veri by remember(url, key, oturum) { mutableStateOf<JSONObject?>(null) }
    var hata by remember(url, key, oturum) { mutableStateOf("") }
    var yukleniyor by remember { mutableStateOf(true) }
    var yenile by remember { mutableIntStateOf(0) }
    var ufuk by remember { mutableIntStateOf(UFUKLAR.first()) }

    LaunchedEffect(url, key, oturum, yenile) {
        yukleniyor = true
        veri = null
        hata = ""
        try {
            veri = withContext(Dispatchers.IO) {
                JSONObject(api(url, key, "/admin/social-radar", zamanAsimi = 12_000, oturum = oturum)).also {
                    require(it.opt("schema_version") == 1 && it.opt("read_only") == true &&
                        it.optJSONArray("sources") != null && it.optJSONArray("alerts") != null)
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            hata = when {
                e.message?.startsWith("HTTP 404") == true -> "Sosyal Radar sunucuya henüz eklenmedi."
                e.message?.startsWith("HTTP 403") == true -> "Bu ekran yalnızca kurucu yetkisiyle okunabilir."
                e.message?.startsWith("HTTP 401") == true -> "Sosyal Radar için giriş yapmanız gerekiyor."
                else -> "Sosyal Radar verisine erişilemiyor."
            }
        } finally {
            yukleniyor = false
        }
    }

    val radar = veri
    val kaynaklar = radar?.optJSONArray("sources").satirlar()
        .groupBy { it.str("source_id") }
    val bagliKaynaklar = SOSYAL_KAYNAKLAR.filter { kaynak ->
        radar?.opt("live_enabled") == true && kaynaklar[kaynak.kimlik]?.singleOrNull().dogrulanmisKaynak()
    }.associateBy { it.kimlik }
    val uyarilar = radar?.optJSONArray("alerts").satirlar().filter {
        it.str("source_id") in bagliKaynaklar && it.str("mint_status") == "VERIFIED" &&
            MINT_BICIMI.matches(it.str("token_mint")) && it.str("classification") in SINIFLAR
    }.take(20)

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Text("NEXORA Social AI", color = Nx.Metin, fontSize = 23.sp, fontWeight = FontWeight.Bold)
            Etiket("${bagliKaynaklar.size}/${SOSYAL_KAYNAKLAR.size} bağlı kaynak",
                if (bagliKaynaklar.isEmpty()) Nx.Sari else Nx.Yesil)
            Text("Solana mint doğrulaması, sosyal riskler ve gölge sonuçları",
                color = Nx.Soluk, fontSize = 13.sp)
            OutlinedButton(onClick = { yenile++ }, enabled = !yukleniyor) {
                Text(if (yukleniyor) "Kontrol ediliyor…" else "Kaynakları yenile")
            }
        }

        val durum = when {
            hata.isNotBlank() -> hata
            radar != null && bagliKaynaklar.isEmpty() -> sunucuDurumu(radar.str("snapshot_status"))
            else -> ""
        }
        if (durum.isNotEmpty()) {
            Kart(Modifier.fillMaxWidth()) {
                Text(durum, color = Nx.Sari, fontSize = 13.sp)
            }
        }

        Text("Sosyal kaynaklar", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        SOSYAL_KAYNAKLAR.forEach { kaynak ->
            val satir = kaynaklar[kaynak.kimlik]?.singleOrNull()
            val bagli = kaynak.kimlik in bagliKaynaklar
            val durumMetni = when {
                bagli -> "Bağlı"
                satir?.str("status") == "KOTA" -> "Kota sınırı"
                satir?.str("status") == "VERI_GECIKTI" -> "Veri gecikti"
                satir?.str("access_status") == "ERISIM_YOK" -> "Erişim yok"
                else -> "Bekliyor"
            }
            Kart(Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(kaynak.ad, color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                        Text("${kaynak.platform} · @${kaynak.hesap}", color = Nx.Soluk, fontSize = 12.sp)
                    }
                    Etiket(durumMetni, if (bagli) Nx.Yesil else Nx.Sari)
                }
                Text(kaynak.amac, color = Nx.Soluk, fontSize = 12.sp)
                if (bagli) {
                    tarih(satir.sayi("last_seen"))?.let {
                        Text("Son gözlem $it", color = Nx.Soluk, fontSize = 11.sp)
                    }
                }
            }
        }

        Text("Sosyal uyarılar ve gölge sonuçları", color = Nx.Metin,
            fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            UFUKLAR.forEach { dakika ->
                Hap("$dakika dk", ufuk == dakika, Modifier.weight(1f)) { ufuk = dakika }
            }
        }
        if (uyarilar.isEmpty()) {
            Kart(Modifier.fillMaxWidth()) {
                Text(if (yukleniyor) "Uyarılar kontrol ediliyor…" else "Doğrulanmış sosyal uyarı yok",
                    color = Nx.Metin, fontSize = 14.sp)
                Text("$ufuk dk için ölçüm verisi yok.", color = Nx.Soluk, fontSize = 12.sp)
            }
        }
        uyarilar.forEach { olay ->
            SosyalUyariKarti(olay, bagliKaynaklar.getValue(olay.str("source_id")), ufuk)
        }
    }
}

@Composable
private fun SosyalUyariKarti(olay: JSONObject, kaynak: SosyalKaynak, ufuk: Int) {
    val sinif = olay.str("classification")
    val sonuc = olay.optJSONObject("shadow_results")?.optJSONObject("${ufuk}dk")
    val net = sonuc.sayi("net_usdc")
    val getiri = sonuc.sayi("return_pct")
    val nedenler = olay.optJSONArray("reason_codes")
    Kart(Modifier.fillMaxWidth()) {
        Text("Solana tokeni", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        SelectionContainer {
            Text(olay.str("token_mint"), color = Nx.Soluk, fontSize = 12.sp)
        }
        val zaman = tarih(olay.sayi("observed_at"))
        Text(listOfNotNull("Mint doğrulandı", kaynak.ad, zaman).joinToString(" · "),
            color = Nx.Soluk, fontSize = 12.sp)
        Etiket(SINIFLAR.getValue(sinif), when (sinif) {
            "RISK_VETOSU_ADAYI" -> Nx.Kirmizi
            "SOSYAL_ERKEN_UYARI" -> Nx.Camgobegi
            else -> Nx.Sari
        })
        if (nedenler != null) {
            for (i in 0 until minOf(nedenler.length(), 10)) {
                val kod = nedenler.optString(i)
                if (kod.isNotEmpty()) {
                    val eksik = kod.endsWith("_UNKNOWN")
                    val neden = kod.removeSuffix("_UNKNOWN").replace('_', ' ')
                        .lowercase(Locale.ROOT).replaceFirstChar { it.titlecase(Locale.ROOT) }
                    Text(if (eksik) "$neden doğrulanamadı" else neden, color = Nx.Soluk, fontSize = 12.sp)
                }
            }
        }
        Text("$ufuk dk gölge sonucu", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        when {
            sonuc?.str("status") == "OK" && net != null && getiri != null -> {
                Text(String.format(Locale.forLanguageTag("tr-TR"), "%+.6f USDC · %+.2f%%", net, getiri),
                    color = Nx.Metin, fontSize = 13.sp)
                Text("Giriş, çıkış ve ağ ücreti dahil teklif ölçümü.", color = Nx.Soluk, fontSize = 12.sp)
            }
            sonuc?.str("status") == "PENDING" -> {
                val vade = tarih(sonuc.sayi("due_at"))
                Text(if (vade == null) "Ölçüm süresi dolmadı" else "Ölçüm zamanı $vade",
                    color = Nx.Sari, fontSize = 12.sp)
            }
            else -> Text(sonucDurumu(sonuc?.str("reason_code").orEmpty()), color = Nx.Soluk, fontSize = 12.sp)
        }
    }
}
