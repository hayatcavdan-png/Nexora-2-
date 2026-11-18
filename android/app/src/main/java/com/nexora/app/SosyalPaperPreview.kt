package com.nexora.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * Kurucuya özel ayrı, çevrimdışı USDT paper önizlemesi.
 * Telegram mesajlarını, gerçek emirleri ve canlı Social Radar verisini işlemez.
 */
@Composable
fun SosyalPaperKarti(url: String, key: String, refresh: Int) {
    val session = if (key.isBlank()) Oturum.deger else ""
    var data by remember(url, key, session) { mutableStateOf<JSONObject?>(null) }
    var message by remember(url, key, session) { mutableStateOf("Kontrol ediliyor…") }

    LaunchedEffect(url, key, session, refresh) {
        message = "Kontrol ediliyor…"
        data = null
        try {
            val payload = withContext(Dispatchers.IO) {
                JSONObject(api(url, key, "/admin/social-paper",
                    zamanAsimi = 12_000, oturum = session))
            }
            require(payload.optInt("schema_version") == 1)
            require(payload.optString("mode") == "OFFLINE_PAPER_ONLY")
            require(payload.optBoolean("read_only") == true)
            require(payload.opt("real_order") == false)
            require(payload.opt("social_ai_transfer") == false)
            require(payload.optString("currency") == "USDT")
            require(payload.optJSONArray("results") != null)
            data = payload
            message = ""
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            message = when {
                e.message?.startsWith("HTTP 404") == true ->
                    "Sunucuda sanal işlem önizlemesi henüz kurulu değil."
                e.message?.startsWith("HTTP 401") == true ->
                    "Sanal işlemleri görmek için kurucu girişi gerekli."
                e.message?.startsWith("HTTP 403") == true ->
                    "Bu alan yalnızca kurucu yetkisiyle görüntülenebilir."
                else -> "Sanal işlem verisine erişilemiyor."
            }
        }
    }

    Kart(Modifier.fillMaxWidth()) {
        Text("100 USDT · Sanal Token Araştırması",
            color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Etiket("OFFLINE / PAPER", Nx.Sari)
        Text("İşlem emri yok. Yalnızca ayrı test dosyasındaki kanıtlar gösterilir; canlı fiyat veya alım kanıtı değildir.",
            color = Nx.Soluk, fontSize = 12.sp)

        if (message.isNotEmpty()) {
            Text(message, color = Nx.Sari, fontSize = 12.sp)
        } else {
            val preview = data
            if (preview != null) {
                val snapshot = preview.optString("snapshot_status")
                val balance = preview.optString("remaining_cash_usdt")
                val count = preview.optInt("positions", 0)
                Text("Kalan sanal nakit: $balance USDT · Aday pozisyon: $count",
                    color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                if (snapshot != "OFFLINE_FIXTURE_ONLY") {
                    Text("Henüz çevrimdışı test dosyası tanımlanmadı.",
                        color = Nx.Sari, fontSize = 12.sp)
                }
                val rows: JSONArray? = preview.optJSONArray("results")
                val shown = minOf(rows?.length() ?: 0, 10)
                for (i in 0 until shown) {
                    val item = rows?.optJSONObject(i) ?: continue
                    val mint = item.optString("mint")
                    val eligible = item.optString("status") == "PAPER_ELIGIBLE"
                    val why = item.optString("reason")
                    HorizontalDivider()
                    Text("Aday ${i + 1}: " + if (eligible) "Sanal değerlendirme uygun" else "Engellendi",
                        color = if (eligible) Nx.Yesil else Nx.Sari,
                        fontWeight = FontWeight.SemiBold)
                    if (mint.length in 32..44) {
                        SelectionContainer { Text(mint, color = Nx.Soluk, fontSize = 12.sp) }
                    }
                    Text("Gerekçe kodu: $why", color = Nx.Soluk, fontSize = 11.sp)
                    if (eligible) {
                        val entry = item.optJSONObject("entry")
                        val cost = entry?.optString("total_cost_usdt") ?: "?"
                        Text("Sanal maliyet: $cost USDT", color = Nx.Metin, fontSize = 12.sp)
                        val horizons = item.optJSONObject("horizons")
                        for (m in listOf(5, 15, 30, 60)) {
                            val result = horizons?.optJSONObject("${m}dk")
                            val status = result?.optString("status") ?: "UNKNOWN"
                            val net = result?.optString("net_usdt") ?: "?"
                            val label = when (status) {
                                "OK" -> "Sanal net: $net USDT"
                                "PENDING" -> "Henüz ölçülmedi"
                                else -> "Kanıt yetersiz"
                            }
                            Text("$m dk · $label", color = Nx.Soluk, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}
