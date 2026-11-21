package com.nexora.app

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Strateji teşhisi (yalnızca kurucu): sunucudaki strateji_teshis raporunun aynısı, telefondan. Salt okunur. */
@Composable
fun TeshisKarti(url: String, key: String) {
    var gun by remember { mutableIntStateOf(3) }
    var metin by remember { mutableStateOf("") }
    var ozet by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    var yukleniyor by remember { mutableStateOf(false) }
    var tetik by remember { mutableIntStateOf(0) }
    LaunchedEffect(gun, tetik) {
        yukleniyor = true; hata = ""
        try {
            val d = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/teshis?gun=$gun", zamanAsimi = 20_000) })
            metin = d.optString("metin"); ozet = d.optJSONObject("ozet")
        } catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e
            hata = if (e.message?.contains("403") == true) "Teşhis yalnızca kurucuya açık." else "Teşhis alınamadı: ${e.message}"
        }
        yukleniyor = false
    }
    NeonKart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Strateji teşhisi", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            TextButton({ tetik++ }, enabled = !yukleniyor) { Text(if (yukleniyor) "…" else "Yenile", color = Nx.Nane) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(1, 3, 7, 14).forEach { g -> Hap("$g gün", gun == g, Modifier.weight(1f)) { gun = g } }
        }
        ozet?.let { o ->
            Text("Son 24 saat", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            SatirKV("Gerçekleşen K/Z", String.format(java.util.Locale.US, "%+.2f $", o.optDouble("gerceklesen")))
            SatirKV("Açık pozisyon", "${o.optInt("acik_poz")} · " + String.format(java.util.Locale.US, "%+.2f $", o.optDouble("acik_kz")))
            SatirKV("Alım / satış (kazanan)", "${o.optInt("alim")} / ${o.optInt("satis")} (${o.optInt("kazanan")})")
            SatirKV("Reddedilen (yer/risk sınırı)", "${o.optInt("red")} (${o.optInt("red_slot")})")
        }
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
        if (metin.isNotEmpty()) Box(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            Text(metin, color = Nx.Metin, fontSize = 10.sp, fontFamily = FontFamily.Monospace, lineHeight = 14.sp)
        }
        Text("Rapor yalnızca okur; hiçbir ayarı değiştirmez. [3] kopyalasaydık getirisi, [4] cüzdan bazında sonuç, " +
             "[5] reddedilenlerin gölge sonucu, [8]/[9] token türü, [10] deney masası, [13] çıkış deneyi, [14] token yaşı, " +
             "[15] teyit bağımsızlığı, [16] Hyperliquid ölçümüdür. Yorum için aşağıdaki yapay zekâ kartını kullanın.", color = Nx.Soluk, fontSize = 11.sp)
    }
}
