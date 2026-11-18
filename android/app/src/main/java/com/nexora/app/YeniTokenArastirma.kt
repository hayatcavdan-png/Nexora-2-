package com.nexora.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** Read-only operator-triggered Solana research. NOT Telegram content ingestion. */
@Composable
fun YeniTokenArastirmaKarti(url: String, key: String) {
    val session = if (key.isBlank()) Oturum.deger else ""
    val scope = rememberCoroutineScope()
    var mint by rememberSaveable { mutableStateOf("") }
    var paperStudy by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf("") }

    fun inspect(mode: String) {
        if (busy) return
        scope.launch {
            busy = true
            result = null
            error = ""
            try {
                val req = JSONObject().put("mode", mode).put("paper", paperStudy)
                if (mode == "manual") {
                    req.put("mint", mint.trim())
                } else {
                    req.put("limit", 2)
                }
                val json = withContext(Dispatchers.IO) {
                    JSONObject(api(url, key, "/admin/token-discovery", true,
                        req.toString(), zamanAsimi = 90_000, oturum = session))
                }
                require(json.optString("mode") == "READ_ONLY_RESEARCH")
                require(json.optBoolean("read_only", true))
                require(json.opt("real_order") == false)
                require(json.opt("social_ai_transfer") == false)
                require(json.optJSONArray("results") != null)
                result = json
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = when {
                    e.message?.startsWith("HTTP 404") == true ->
                        "Sunucu henüz yeni token araştırma API'sini desteklemiyor."
                    e.message?.startsWith("HTTP 401") == true ->
                        "Kurucu oturumuna tekrar giriş gerekiyor."
                    e.message?.startsWith("HTTP 403") == true ->
                        "Yalnızca kurucu bu araştırmayı başlatabilir."
                    else -> "Token araştırmasına erişilemiyor."
                }
            } finally {
                busy = false
            }
        }
    }

    Kart(Modifier.fillMaxWidth()) {
        Text("Yeni Solana Token Araştırması", color = Nx.Metin,
            fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Etiket("MANUEL ONAY / SALT OKUNUR", Nx.Sari)
        Text("Jupiter yeni likidite havuzları → Helius SPL mint ve yetki kontrolü → Jupiter alım/geri satış teklifi. Gerçek emir veya paper pozisyon açılmaz.",
            color = Nx.Soluk, fontSize = 12.sp)
        Text("Telegram kanal takibi bu araştırmadan ayrıdır; mesaj içerikleri okunmaz.",
            color = Nx.Soluk, fontSize = 11.sp)
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Switch(checked = paperStudy, onCheckedChange = { paperStudy = it })
            Spacer(Modifier.width(8.dp))
            Text("Uygun adayı ayrı 100 USDT sanal araştırmaya ekle",
                color = Nx.Soluk, fontSize = 12.sp)
        }
        OutlinedTextField(
            value = mint,
            onValueChange = { if (it.length <= 64) mint = it.trim() },
            label = { Text("Solana kontrat adresi (CA) — elle gir") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                enabled = !busy && mint.isNotBlank(),
                modifier = Modifier.weight(1f),
                onClick = { inspect("manual") }
            ) { Text("CA doğrula", fontSize = 12.sp) }
            Button(
                enabled = !busy,
                modifier = Modifier.weight(1f),
                onClick = { inspect("recent") }
            ) { Text("Yeni havuzları tara", fontSize = 12.sp) }
        }
        if (busy) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text("Salt okunur sağlayıcı kontrolleri sürüyor…",
                color = Nx.Soluk, fontSize = 12.sp)
        }
        if (error.isNotBlank()) {
            Text(error, color = Nx.Sari, fontSize = 12.sp)
        }
        val data = result
        if (data != null) {
            val status = data.optString("status")
            when (status) {
                "DISABLED" -> Text("Canlı araştırma sunucu yöneticisince henüz açılmadı.",
                    color = Nx.Sari, fontSize = 12.sp)
                "HELIUS_KEY_MISSING" -> Text("Helius sunucu anahtarı eksik.",
                    color = Nx.Sari, fontSize = 12.sp)
                "JUPITER_KEY_MISSING" -> Text("Jupiter sunucu anahtarı eksik.",
                    color = Nx.Sari, fontSize = 12.sp)
                "RATE_LIMITED" -> Text("Hız sınırı: yeni araştırma biraz sonra yapılabilir.",
                    color = Nx.Sari, fontSize = 12.sp)
                "OK" -> Text("Araştırma tamamlandı; bunlar alım sinyali değildir.",
                    color = Nx.Yesil, fontSize = 12.sp)
                else -> Text("Sağlayıcı sonucu: " + status,
                    color = Nx.Sari, fontSize = 12.sp)
            }
            val watch = data.optJSONObject("paper_watch")
            if (watch != null) {
                val count = watch.optInt("opened", 0)
                val status = watch.optString("status")
                Text("Sanal araştırma: " + if (count > 0)
                    "$count yeni aday kaydedildi" else status,
                    color = if (count > 0) Nx.Yesil else Nx.Sari, fontSize = 12.sp)
            }
            val rows: JSONArray? = data.optJSONArray("results")
            for (i in 0 until minOf(rows?.length() ?: 0, 3)) {
                val item = rows?.optJSONObject(i) ?: continue
                val valid = item.optString("status") == "RESEARCH_CANDIDATE"
                HorizontalDivider()
                Text(if (valid) "Araştırma adayı — risk kapıları geçti" else
                    "Engellendi / kanıt yetersiz",
                    color = if (valid) Nx.Yesil else Nx.Sari,
                    fontWeight = FontWeight.SemiBold)
                val ca = item.optString("mint")
                if (ca.isNotBlank()) {
                    SelectionContainer {
                        Text(ca, color = Nx.Metin, fontSize = 12.sp)
                    }
                }
                val symbol = item.optString("symbol")
                if (symbol.isNotBlank() && symbol != "null")
                    Text("Sembol: " + symbol.take(32), color = Nx.Soluk, fontSize = 12.sp)
                Text("Gerekçe: " + item.optString("reason"),
                    color = Nx.Soluk, fontSize = 12.sp)
                if (valid) {
                    Text("Likidite: " + item.optString("liquidity_usd") + " USD",
                        color = Nx.Soluk, fontSize = 12.sp)
                    Text("4 USDT anlık çift yönlü fiyat kontrolü: dönüş " +
                        item.optString("immediate_sell_quote_usdt") + " USDT",
                        color = Nx.Metin, fontSize = 12.sp)
                    Text("Anlık tur kaybı: %" + item.optString("quote_roundtrip_pct"),
                        color = Nx.Soluk, fontSize = 12.sp)
                    Text("Ağ ücreti ve gerçekleşme garantisi yok; sanal pozisyon açılmadı.",
                        color = Nx.Sari, fontSize = 11.sp)
                }
            }
        }
    }
}
