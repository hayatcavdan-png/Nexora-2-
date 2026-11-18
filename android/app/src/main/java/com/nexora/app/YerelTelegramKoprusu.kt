package com.nexora.app

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant

/**
 * Yalnızca aynı Android cihazının Termux loopback hizmetinden alınan anonim
 * Telegram KANAL DURUMU metadatasını gösterir. Kullanıcı/token/mesaj metni,
 * hesap oturumu bu uygulamaya iletilmez. İsteğe bağlı yalnızca sayısal
 * son genel kanal mesaj ID'si, kullanıcı tarafından Telegram'da açılabilir.
 *
 * Bu köprü NEXORA /admin/social-radar canlı kaynak kanıtı DEĞİLDİR.
 * Gerçek Social AI akışı ve paper karar motoru bu veriyi tüketmez.
 */
private const val TG_LOCAL_URL = "http://127.0.0.1:18991/status"

private data class TelegramDurum(
    val kanal1: Int,
    val kanal2: Int,
    val guncel: Boolean,
    val islemlerCalisiyor: Boolean,
    val last1: String?,
    val last2: String?,
)

private fun yerelTelegramOku(): TelegramDurum {
    val connection = (URL(TG_LOCAL_URL).openConnection() as HttpURLConnection)
    connection.requestMethod = "GET"
    connection.connectTimeout = 1600
    connection.readTimeout = 1600
    connection.instanceFollowRedirects = false
    connection.setRequestProperty("Accept", "application/json")
    try {
        require(connection.responseCode == 200) { "Local bridge unavailable" }
        val body = connection.inputStream.use { stream ->
            val limit = ByteArray(16385)
            var used = 0
            while (used < limit.size) {
                val n = stream.read(limit, used, limit.size - used)
                if (n < 0) break
                used += n
            }
            require(used < limit.size) { "Oversized local response" }
            String(limit, 0, used, Charsets.UTF_8)
        }
        val data = JSONObject(body)
        require(data.optInt("schema_version") == 1)
        require(data.optString("mode") == "LOCAL_METADATA_ONLY")
        require(data.opt("social_ai_transfer") == false)
        val stamp = Instant.parse(data.getString("updated_at"))
        val age = Instant.now().epochSecond - stamp.epochSecond
        val recent = age in -5L..90L

        val rows = data.getJSONArray("source_status")
        require(rows.length() == 2)
        var first: Int? = null
        var second: Int? = null
        var last1: String? = null
        var last2: String? = null
        val numericMessageId = Regex("[0-9]{1,22}")
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i)
            require(row.optString("platform") == "telegram")
            require(row.opt("live_verified") == false)
            require(row.opt("social_ai_transfer") == false)
            val countValue = row.opt("metadata_count")
            require(countValue is Int && countValue in 0..1000000)
            val lastRaw = row.opt("last_message_id")
            require(lastRaw == null || (lastRaw is String &&
                numericMessageId.matches(lastRaw) && lastRaw.any { it != '0' }))
            val lastId = lastRaw as? String
            when (row.getString("source_id")) {
                "solana_early_trending" -> {
                    require(row.getString("handle").equals("@solearlytrending", ignoreCase = true))
                    require(first == null)
                    first = countValue
                    last1 = lastId
                }
                "kolscope" -> {
                    require(row.getString("handle").equals("@KOLscope", ignoreCase = true))
                    require(second == null)
                    second = countValue
                    last2 = lastId
                }
                else -> error("Unknown local source")
            }
        }
        require(first != null && second != null)
        val running = data.opt("listener_running") == true &&
            data.opt("updater_running") == true &&
            data.opt("sync_running") == true
        return TelegramDurum(first, second, recent, running, last1, last2)
    } finally {
        connection.disconnect()
    }
}

@Composable
fun YerelTelegramKoprusu() {
    val context = androidx.compose.ui.platform.LocalContext.current
    var status by remember { mutableStateOf<TelegramDurum?>(null) }
    var checked by remember { mutableStateOf(false) }

    // Ekran açıldığında başlar, ekran kapanınca iptal edilir; arka plan servisi değildir.
    LaunchedEffect(Unit) {
        while (true) {
            try {
                status = withContext(Dispatchers.IO) { yerelTelegramOku() }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                status = null
            }
            checked = true
            delay(20_000)
        }
    }

    val active = status?.let { it.guncel && it.islemlerCalisiyor } ?: false
    Kart(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Telegram · yerel köprü", color = Nx.Metin, fontSize = 16.sp,
                fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Etiket(if (active) "2/2 yerel" else if (checked) "Bağlı değil" else "Kontrol",
                if (active) Nx.Yesil else Nx.Sari)
        }
        Text("Yalnızca bu telefondaki Termux dinleyicisinin durumunu gösterir.",
            color = Nx.Soluk, fontSize = 12.sp)
        if (active) {
            Satir("@solearlytrending · bildirim", status!!.kanal1.toString())
            Satir("@KOLscope · bildirim", status!!.kanal2.toString())
            val id1 = status?.last1
            val id2 = status?.last2
            val solanaUrl = "https://t.me/solearlytrending" +
                (if (id1 == null) "" else "/" + id1)
            val kolUrl = "https://t.me/KOLscope" +
                (if (id2 == null) "" else "/" + id2)
            OutlinedButton(onClick = {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(solanaUrl)))
            }) {
                Text(if (id1 == null) "Solana Early · kanalı aç"
                    else "Solana Early · son paylaşımı aç", fontSize = 12.sp)
            }
            OutlinedButton(onClick = {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(kolUrl)))
            }) {
                Text(if (id2 == null) "KOLscope · kanalı aç"
                    else "KOLscope · son paylaşımı aç", fontSize = 12.sp)
            }
            Text("Telegram'da CA'yı kendin kopyalayıp NEXORA'nın araştırma alanına yapıştır.",
                color = Nx.Soluk, fontSize = 11.sp)
            Text("Dinleyici, T8 ve T10 çalışıyor; durum dosyası güncel.",
                color = Nx.Yesil, fontSize = 12.sp)
        } else {
            Text("Termux köprüsü kapalı, verisi eski veya bu cihazda bulunamıyor.",
                color = Nx.Sari, fontSize = 12.sp)
        }
        BilgiKutusu("Bu yalnızca yerel bildirim metadatasıdır. Social Radar'daki 0/5 canlı kaynak sayısına eklenmez. Mesaj metni, token analizi veya AI aktarımı yapılmaz.")
    }
}
