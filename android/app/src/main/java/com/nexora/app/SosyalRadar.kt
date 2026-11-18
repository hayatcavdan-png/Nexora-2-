package com.nexora.app

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * NEXORA Social Radar - yalnızca kurucu için salt okunur ekran.
 * Sunucuda /admin/social-radar bulunmuyorsa bağlantı bekleniyor gösterir.
 * Demo veri, fiyat tahmini, alım emri veya otomatik bildirim üretmez.
 */
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

private fun kaynakBul(kaynaklar: JSONArray?, kaynak: SosyalKaynak): JSONObject? {
    if (kaynaklar == null) return null
    for (i in 0 until kaynaklar.length()) {
        val satir = kaynaklar.optJSONObject(i) ?: continue
        val kimlik = satir.optString("source_id", satir.optString("id"))
        val hesap = satir.optString("handle").trim().removePrefix("@")
        if (kimlik == kaynak.kimlik || hesap.equals(kaynak.hesap, ignoreCase = true)) return satir
    }
    return null
}

@Composable
fun SosyalRadarEkrani(url: String, key: String) {
    var veri by remember(url, key) { mutableStateOf<JSONObject?>(null) }
    var hata by remember(url, key) { mutableStateOf("") }
    var yukleniyor by remember { mutableStateOf(false) }
    var yenile by remember { mutableIntStateOf(0) }

    // Ekran açıldığında ve kullanıcı istediğinde tek okuma isteği.
    // Otomatik tarama veya ücretli sosyal API isteği Android içinde yapılmaz.
    LaunchedEffect(url, key, yenile) {
        yukleniyor = true
        try {
            veri = withContext(Dispatchers.IO) {
                JSONObject(api(url, key, "/admin/social-radar", zamanAsimi = 12_000))
            }
            hata = ""
        } catch (e: Exception) {
            veri = null
            hata = when {
                e.message?.contains("404") == true -> "Sosyal Radar sunucuya henüz eklenmedi."
                e.message?.contains("403") == true -> "Bu ekran yalnızca kurucu yetkisiyle okunabilir."
                e.message?.contains("401") == true -> "Sosyal Radar için giriş yapmanız gerekiyor."
                else -> "Sosyal Radar verisine erişilemiyor; canlı sinyal doğrulanamadı."
            }
        } finally {
            yukleniyor = false
        }
    }

    val kaynaklar = veri?.optJSONArray("sources") ?: veri?.optJSONArray("kaynaklar")
    val uyarilar = veri?.optJSONArray("alerts") ?: veri?.optJSONArray("uyarilar")
    val bagliSayisi = SOSYAL_KAYNAKLAR.count {
        val k = kaynakBul(kaynaklar, it)
        k != null && k.optBoolean("live_verified", false)
    }

    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
        Text("NEXORA Social AI", color = Nx.Metin, fontSize = 23.sp, fontWeight = FontWeight.Bold)
        Text("Solana sosyal sinyalleri • zincir teyidi • manipülasyon analizi",
            color = Nx.Soluk, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Etiket("Gölge araştırma", Nx.Camgobegi)
            Etiket(bagliSayisi.toString() + "/5 kaynak", if (bagliSayisi > 0) Nx.Yesil else Nx.Sari)
        }
        Text(
            "Sosyal paylaşım tek başına alım sinyali değildir. Bu ekran hiçbir işlemi başlatmaz ve AI filtresini açmaz.",
            color = Nx.Soluk, fontSize = 12.sp
        )
        OutlinedButton(onClick = { yenile++ }, enabled = !yukleniyor) {
            Text(if (yukleniyor) "Kontrol ediliyor..." else "Kaynakları yenile")
        }
    }

    if (hata.isNotBlank()) {
        Kart(Modifier.fillMaxWidth()) {
            Text("Canlı bağlantı bekleniyor", color = Nx.Sari, fontWeight = FontWeight.SemiBold)
            Text(hata, color = Nx.Soluk, fontSize = 13.sp)
            Text("Beş kaynak yalnızca izleme kataloğudur; aşağıda gösterilmeleri mesajlarının okunduğu anlamına gelmez.",
                color = Nx.Soluk, fontSize = 12.sp)
        }
    }

    if (veri != null && !veri!!.optBoolean("live_enabled", false)) {
        Kart(Modifier.fillMaxWidth()) {
            Text("Gerçek zamanlı sosyal veri henüz etkin değil", color = Nx.Sari, fontWeight = FontWeight.SemiBold)
            Text("Sunucu durumu: " + veri!!.optString("snapshot_status", "UNKNOWN"),
                color = Nx.Soluk, fontSize = 12.sp)
            Text("Kaynak bağlantısı doğrulanmadan sosyal uyarı gösterilmez.",
                color = Nx.Soluk, fontSize = 12.sp)
        }
    }

    Text("İzlenen kaynaklar", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
    SOSYAL_KAYNAKLAR.forEach { kaynak ->
        val k = kaynakBul(kaynaklar, kaynak)
        val dogrulandi = k?.optBoolean("live_verified", false) == true
        val durum = when {
            dogrulandi -> "Canlı erişim doğrulandı"
            k?.optString("access_status") == "RATE_LIMITED" -> "Kota sınırı"
            k?.optString("access_status") == "UNAVAILABLE" -> "Erişim yok"
            else -> "Erişim bekleniyor"
        }
        Kart(Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(kaynak.ad, color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                    Text(kaynak.platform + " · @" + kaynak.hesap, color = Nx.Soluk, fontSize = 12.sp)
                }
                Etiket(if (dogrulandi) "Bağlı" else "Bekliyor", if (dogrulandi) Nx.Yesil else Nx.Sari)
            }
            Text(kaynak.amac, color = Nx.Soluk, fontSize = 12.sp)
            Text(durum, color = if (dogrulandi) Nx.Yesil else Nx.Soluk, fontSize = 12.sp)
            val son = k?.optString("last_seen").orEmpty()
            if (son.isNotBlank() && son != "null") Text("Son gözlem: " + son.take(40), color = Nx.Soluk, fontSize = 11.sp)
        }
    }

    Text("Doğrulanmış sosyal uyarılar", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
    if (uyarilar == null || uyarilar.length() == 0) {
        Kart(Modifier.fillMaxWidth()) {
            Text("Henüz doğrulanmış sosyal uyarı yok", color = Nx.Soluk, fontSize = 14.sp)
            Text("Veri kaynağı yetkisi, Solana mint doğrulaması ve ilk gözlem zamanı olmadan sinyal gösterilmez.",
                color = Nx.Soluk, fontSize = 12.sp)
        }
    } else {
        val sayi = minOf(uyarilar.length(), 20)
        for (i in 0 until sayi) {
            val olay = uyarilar.optJSONObject(i) ?: continue
            val sinif = olay.optString("classification", olay.optString("sinif", "BELIRSIZ"))
            val mint = olay.optString("mint", olay.optString("token_mint"))
            val baslik = olay.optString("token_symbol", olay.optString("token", "Solana tokeni"))
            Kart(Modifier.fillMaxWidth()) {
                Text(baslik.take(50), color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                Etiket(sinif.take(36), when (sinif) {
                    "SOSYAL_ERKEN_UYARI" -> Nx.Camgobegi
                    "RISK_VETOSU_ADAYI" -> Nx.Kirmizi
                    else -> Nx.Sari
                })
                Text(if (mint.isBlank()) "Mint doğrulanmadı" else "Mint: " + kisa(mint),
                    color = Nx.Soluk, fontSize = 12.sp)
                Text("Gölge analiz; işlem başlatılmaz.", color = Nx.Soluk, fontSize = 12.sp)
            }
        }
    }
}
