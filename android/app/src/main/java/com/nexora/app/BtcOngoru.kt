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
                val son = d.optJSONObject("son_tahmin")
                val gecerli = d.optJSONObject("son_gecerli")
                val sonBos = son != null && (son.str("yon") ?: "").isEmpty()
                val t = if (sonBos && gecerli != null) gecerli else son        // son tur YZ'siz geçtiyse son geçerli tahmini göster
                val yon = t?.str("yon") ?: ""
                val (ok, renk) = when (yon) { "YUKARI" -> "▲ Yukarı" to Nx.Nane; "ASAGI" -> "▼ Aşağı" to Nx.Kirmizi
                                              "BELIRSIZ" -> "◆ Belirsiz" to Nx.Soluk; else -> "— tahmin yok" to Nx.Soluk }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(ok, color = renk, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    if (t != null && !t.isNull("guven")) {
                        val saat = java.text.SimpleDateFormat("HH:mm", Locale("tr")).format(java.util.Date((t.optDouble("ts", 0.0) * 1000).toLong()))
                        Text("güven %${t.optInt("guven")} · 4 saat · $saat", color = Nx.Soluk, fontSize = 12.sp)
                    }
                }
                if (sonBos) {
                    val h = son?.str("hata") ?: ""
                    Text("Son tur YZ yanıtı alınamadı" + (if (h.isNotEmpty()) " (${h.take(60)})" else "") + "; bir sonraki saat yeniden denenecek.",
                         color = Nx.Kehribar, fontSize = 11.sp)
                }
                val gerekce = t?.str("gerekce") ?: ""
                if (gerekce.isNotEmpty()) Text(gerekce, color = Nx.Metin, fontSize = 13.sp)
                if (t != null) {
                    val ty = t.str("topluluk_yon") ?: ""
                    if (ty.isNotEmpty()) {
                        val ad = when (ty) { "YUKARI" -> "yukarı"; "ASAGI" -> "aşağı"; else -> "belirsiz" }
                        Text("Göstergeler: $ad (skor ${String.format(Locale("tr"), "%+.2f", t.optDouble("topluluk_skor", 0.0))})",
                             color = Nx.Soluk, fontSize = 12.sp)
                    }
                    Text("Karar: ${t.str("karar")} · ${t.str("karar_neden")}", color = Nx.Soluk, fontSize = 12.sp)
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BtcKutu("Sanal bakiye", "$" + usd(d.optDouble("toplam", 0.0)), Modifier.weight(1f))
                    BtcKutu("K/Z", yuzde(d.dbl("kz_pct")), Modifier.weight(1f), if ((d.dbl("kz_pct") ?: 0.0) >= 0) Nx.Nane else Nx.Kirmizi)
                    BtcKutu("BTC'yi tutmak", yuzde(d.dbl("btc_tut_pct")), Modifier.weight(1f))
                }
                val yz = d.optJSONObject("yz"); val kural = d.optJSONObject("kural"); val topl = d.optJSONObject("topluluk")
                val isabet = { o: JSONObject? -> if (o == null || o.optInt("n") == 0) "—" else "%" + String.format(Locale("tr"), "%.1f", o.optDouble("isabet_pct")) + " (${o.optInt("n")})" }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BtcKutu("YZ isabeti", isabet(yz), Modifier.weight(1f))
                    BtcKutu("Göstergeler", isabet(topl), Modifier.weight(1f))
                    BtcKutu("Basit kural", isabet(kural), Modifier.weight(1f))
                }
                val hb = d.optJSONObject("haber"); val uz = d.optJSONObject("uzman")
                if ((hb?.optInt("n") ?: 0) > 0 || (uz?.optInt("n") ?: 0) > 0) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BtcKutu("Haber/sosyal", isabet(hb), Modifier.weight(1f))
                    BtcKutu("Uzman traderlar", isabet(uz), Modifier.weight(1f))
                }
                val du = d.optJSONObject("duygu_son")
                if (du != null) {
                    val parca = mutableListOf<String>()
                    if (!du.isNull("korku_acgozluluk")) parca += "Korku-Açgözlülük ${du.optInt("korku_acgozluluk")}"
                    if (!du.isNull("fonlama_pct")) parca += "fonlama %" + String.format(Locale("tr"), "%.4f", du.optDouble("fonlama_pct"))
                    if (!du.isNull("uzman_long")) parca += "uzmanlar ${du.optInt("uzman_long")} long / ${du.optInt("uzman_short")} short"
                    if (parca.isNotEmpty()) Text(parca.joinToString(" · "), color = Nx.Soluk, fontSize = 12.sp)
                    val ho = du.str("haber_ozet") ?: ""
                    if (ho.isNotEmpty()) Text("Haber (${du.optInt("haber_duygu")}): $ho", color = Nx.Metin, fontSize = 12.sp)
                }
                val gl = d.optJSONArray("golge")
                if (gl != null && gl.length() > 0) {
                    val adlar = mapOf("kural" to "Basit kural", "yz_her" to "YZ (her yukarı)", "topluluk" to "Kanıtlı göstergeler")
                    Text("Gölge portföyler (aynı kurallarla sanal 100 $)", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    var tut: Double? = null
                    for (i in 0 until gl.length()) {
                        val g = gl.getJSONObject(i)
                        if (tut == null) tut = g.dbl("tut_pct")
                        val kz = g.optDouble("kz_pct", 0.0)
                        Row(Modifier.fillMaxWidth()) {
                            Text((adlar[g.optString("ad")] ?: g.optString("ad")) + (if (g.optBoolean("pozisyonda")) " · pozisyonda" else ""),
                                 color = Nx.Metin, fontSize = 12.sp, modifier = Modifier.weight(1f))
                            Text(yuzde(kz) + " · ${g.optInt("islem")} işlem", color = if (kz >= 0) Nx.Nane else Nx.Kirmizi, fontSize = 12.sp)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        Text("BTC'yi tutmak (aynı başlangıç)", color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(1f))
                        Text(yuzde(tut), color = Nx.Soluk, fontSize = 12.sp)
                    }
                }
                val sn = d.optJSONObject("sinama")
                Text(if (sn == null) "Gösterge sınaması henüz çalışmadı."
                     else if (sn.optBoolean("kanit")) "Sınama: göstergeler görülmemiş veride ${yuzde(sn.dbl("getiri_pct"))} (BTC tutma ${yuzde(sn.dbl("tut_pct"))}) · kanıt var"
                     else "Sınama: göstergeler BTC tutmayı geçemedi (${yuzde(sn.dbl("getiri_pct"))} / ${yuzde(sn.dbl("tut_pct"))}) · oy kullanmıyor",
                     color = if (sn?.optBoolean("kanit") == true) Nx.Nane else Nx.Soluk, fontSize = 11.sp)
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
