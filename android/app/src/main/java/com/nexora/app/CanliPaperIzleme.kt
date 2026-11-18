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
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Only quote-based 100 USDT research; NO exchange orders or real PnL. */
@Composable
fun CanliPaperIzlemeKarti(url: String, key: String) {
    val session = if (key.isBlank()) Oturum.deger else ""
    val scope = rememberCoroutineScope()
    var result by remember(url, key, session) { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var refresh by remember { mutableIntStateOf(0) }

    LaunchedEffect(url, key, session, refresh) {
        error = ""
        try {
            result = withContext(Dispatchers.IO) {
                JSONObject(api(url, key, "/admin/social-paper-watch",
                    zamanAsimi = 12_000, oturum = session))
            }
            require(result?.optString("mode") == "QUOTE_PAPER_RESEARCH")
            require(result?.opt("real_order") == false)
            require(result?.opt("social_ai_transfer") == false)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            result = null
            error = when {
                e.message?.startsWith("HTTP 404") == true ->
                    "Sanal araştırma defteri henüz sunucuda yok."
                e.message?.startsWith("HTTP 403") == true ->
                    "Yalnızca kurucu bu defteri okuyabilir."
                else -> "Sanal araştırma defterine erişilemiyor."
            }
        }
    }

    Kart(Modifier.fillMaxWidth()) {
        Text("100 USDT · Süreli Sanal İzleme", color = Nx.Metin,
            fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Etiket("PAPER ARAŞTIRMA / EMİR YOK", Nx.Sari)
        Text("Sanal başlangıç 100 USDT; işlem başına 4 USDT + varsayımsal ücret ve %1 kayma. Dört vade birbirinden bağımsız satış senaryosudur; sonuçlar gerçek kazanç değildir.",
            color = Nx.Soluk, fontSize = 12.sp)
        OutlinedButton(
            enabled = !busy,
            onClick = {
                scope.launch {
                    busy = true
                    try {
                        val refreshed = withContext(Dispatchers.IO) {
                            JSONObject(api(url, key, "/admin/social-paper-watch-refresh",
                                true, "{}", zamanAsimi = 45_000, oturum = session))
                        }
                        require(refreshed.optString("mode") == "QUOTE_PAPER_RESEARCH")
                        require(refreshed.opt("real_order") == false)
                        result = refreshed
                        error = ""
                    } catch (e: Exception) {
                        error = if (e.message?.startsWith("HTTP 429") == true)
                            "Araştırma hız sınırı: çok sık yenileme." else
                            "Ölçüm yenilenemedi; henüz sonuç uydurulmadı."
                    } finally {
                        busy = false
                    }
                }
            }
        ) { Text(if (busy) "Ölçülüyor…" else "Olgunlaşan vadeleri ölç") }
        if (error.isNotBlank()) Text(error, color = Nx.Sari, fontSize = 12.sp)
        val data = result
        if (data != null) {
            val reason = data.optString("snapshot_status")
            if (reason != "ISOLATED_PAPER_RESEARCH") {
                Text("Defter durumu: " + reason, color = Nx.Sari, fontSize = 12.sp)
            }
            Text("Araştırmaya ayrılabilir: " +
                data.optString("available_research_cash_usdt") + " USDT",
                color = Nx.Metin, fontWeight = FontWeight.SemiBold)
            val rows = data.optJSONArray("entries")
            for (i in 0 until minOf(rows?.length() ?: 0, 10)) {
                val item = rows?.optJSONObject(i) ?: continue
                HorizontalDivider()
                Text("Token #" + (i + 1), color = Nx.Metin,
                    fontWeight = FontWeight.SemiBold)
                SelectionContainer {
                    Text(item.optString("mint"), color = Nx.Soluk, fontSize = 11.sp)
                }
                Text("Sanal ayrılan tutar: " +
                    item.optString("reserved_cost_usdt") + " USDT",
                    color = Nx.Soluk, fontSize = 12.sp)
                val horizons = item.optJSONObject("horizons")
                for (m in listOf(5, 15, 30, 60)) {
                    val step = horizons?.optJSONObject(m.toString() + "dk")
                    val status = step?.optString("status") ?: "UNKNOWN"
                    val text = when (status) {
                        "OK" -> (step?.optString("net_usdt") ?: "?") + " USDT (varsayımsal)"
                        "PENDING" -> "Zamanı gelmedi / bekliyor"
                        else -> "Ölçüm yok"
                    }
                    Text(m.toString() + " dk: " + text,
                        color = if (status == "OK") Nx.Yesil else Nx.Soluk,
                        fontSize = 12.sp)
                }
            }
        }
    }
}
