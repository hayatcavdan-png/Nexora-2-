package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Locale

/** Ana ekran · BTC öngörü (PAPER). Sunucu: GET /btc (yalnızca kurucu). YZ tahmini, isabet karnesi ve BTC'yi tutma kıyası. */
@Composable
fun BtcOngoruKarti(url: String, key: String) {
    var veri by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    LaunchedEffect(url, key) {
        try { veri = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/btc", zamanAsimi = 15_000) }); hata = "" }
        catch (e: kotlinx.coroutines.CancellationException) { throw e }
        catch (e: Exception) { hata = if (e.message?.contains("404") == true) "Sunucu güncel değil (/btc yok)." else "Yüklenemedi: ${e.message}" }
    }
    val yuzde = { x: Double? -> if (x == null) "—" else (if (x >= 0) "+" else "") + String.format(Locale("tr"), "%.2f", x) + "%" }
    Column(Modifier.fillMaxWidth().belir().neonIsik(Nx.Kehribar, 22.dp).clip(RoundedCornerShape(22.dp)).background(Nx.Yuzey).padding(16.dp),
           verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("₿ BTC öngörü", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Text("YZ · PAPER", color = Nx.UstMetin, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                 modifier = Modifier.clip(RoundedCornerShape(50)).background(Nx.Kehribar).padding(horizontal = 8.dp, vertical = 3.dp))
        }
        val d = veri
        when {
            hata.isNotEmpty() -> Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
            d == null -> YaziyorNoktalari()
            d.optBoolean("bos") -> Text(d.optString("mesaj", "Henüz veri yok"), color = Nx.Soluk, fontSize = 13.sp)
            else -> {
                val t = d.optJSONObject("son_tahmin")
                val yon = t?.str("yon") ?: ""
                val (ok, renk) = when (yon) { "YUKARI" -> "▲ Yukarı" to Nx.Nane; "ASAGI" -> "▼ Aşağı" to Nx.Kirmizi
                                              "BELIRSIZ" -> "◆ Belirsiz" to Nx.Soluk; else -> "— tahmin yok" to Nx.Soluk }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(ok, color = renk, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    if (t != null && !t.isNull("guven")) Text("güven %${t.optInt("guven")} · 4 saat", color = Nx.Soluk, fontSize = 12.sp)
                }
                val gerekce = t?.str("gerekce") ?: ""
                if (gerekce.isNotEmpty()) Text(gerekce, color = Nx.Metin, fontSize = 13.sp)
                if (t != null) Text("Karar: ${t.str("karar")} · ${t.str("karar_neden")}", color = Nx.Soluk, fontSize = 12.sp)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BtcKutu("Sanal bakiye", "$" + usd(d.optDouble("toplam", 0.0)), Modifier.weight(1f))
                    BtcKutu("K/Z", yuzde(d.dbl("kz_pct")), Modifier.weight(1f), if ((d.dbl("kz_pct") ?: 0.0) >= 0) Nx.Nane else Nx.Kirmizi)
                    BtcKutu("BTC'yi tutmak", yuzde(d.dbl("btc_tut_pct")), Modifier.weight(1f))
                }
                val yz = d.optJSONObject("yz"); val kural = d.optJSONObject("kural")
                val isabet = { o: JSONObject? -> if (o == null || o.optInt("n") == 0) "—" else "%" + String.format(Locale("tr"), "%.1f", o.optDouble("isabet_pct")) + " (${o.optInt("n")})" }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BtcKutu("YZ isabeti", isabet(yz), Modifier.weight(1f))
                    BtcKutu("Basit kural", isabet(kural), Modifier.weight(1f))
                }
                Text("Gerçek para yok. YZ, basit kuralı ve BTC'yi tutmayı yenemezse sistem kanıtlanmış sayılmaz.",
                     color = Nx.Soluk, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun BtcKutu(baslik: String, deger: String, mod: Modifier, renk: Color = Nx.Metin) {
    Column(mod.clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2).padding(horizontal = 10.dp, vertical = 8.dp)) {
        Text(baslik, color = Nx.Soluk, fontSize = 11.sp)
        Text(deger, color = renk, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    }
}
