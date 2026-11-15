package com.nexora.app

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

fun api(base: String, key: String, path: String, post: Boolean = false): String {
    val c = URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("X-API-Key", key)
    if (post) { c.requestMethod = "POST"; c.doOutput = true; c.outputStream.write("{}".toByteArray()) }
    if (c.responseCode != 200) error("HTTP ${c.responseCode}")
    return c.inputStream.bufferedReader().readText()
}

fun kisa(a: String): String = if (a.length > 10) a.take(4) + "…" + a.takeLast(4) else a
fun saat(ts: Double): String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date((ts * 1000).toLong()))
fun JSONObject.str(k: String): String = if (isNull(k)) "" else optString(k, "")
fun usd(x: Double): String = String.format(Locale.US, "%.2f", x)
fun isaretli(x: Double): String = (if (x >= 0) "+" else "") + usd(x)

data class Pozisyon(val token: String, val maliyet: Double, val deger: Double)
data class Sinyal(val ts: Double, val yon: String, val token: String, val cuzdan: String,
                  val gecikme: Double, val kaynak: String, val karar: String, val neden: String)
data class Cuzdan(val adres: String, val durum: String, val hata: String)
data class CuzdanPerf(val adres: String, val ozet: String, val kz: Double, val golge: String)

val YESIL = Color(0xFF4CAF50)
val KIRMIZI = Color(0xFFE57373)

class MainActivity : ComponentActivity() {
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        setContent { MaterialTheme(colorScheme = darkColorScheme()) { Surface { App() } } }
    }
}

@Composable
fun App() {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val sp = remember { ctx.getSharedPreferences("nx", Context.MODE_PRIVATE) }
    var url by remember { mutableStateOf(sp.getString("url", "http://127.0.0.1:8000")!!) }
    var key by remember { mutableStateOf(sp.getString("key", "")!!) }
    var tab by remember { mutableIntStateOf(0) }
    var durum by remember { mutableStateOf("—") }
    var ozet by remember { mutableStateOf("—") }
    var toplamKz by remember { mutableDoubleStateOf(0.0) }
    var pozisyonlar by remember { mutableStateOf(listOf<Pozisyon>()) }
    var sinyaller by remember { mutableStateOf(listOf<Sinyal>()) }
    var cuzdanlar by remember { mutableStateOf(listOf<Cuzdan>()) }
    var gecikme by remember { mutableStateOf("") }
    var islemler by remember { mutableStateOf(listOf<String>()) }
    var hata by remember { mutableStateOf("") }
    var guncelleme by remember { mutableStateOf("") }
    var rBugun by remember { mutableStateOf("") }
    var rKz by remember { mutableDoubleStateOf(0.0) }
    var rGerekce by remember { mutableStateOf(listOf<String>()) }
    var rGolge by remember { mutableStateOf(listOf<String>()) }
    var rGolgeOzet by remember { mutableStateOf("") }
    var rCuzdan by remember { mutableStateOf(listOf<CuzdanPerf>()) }
    var rHata by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    fun yenile() = scope.launch {
        sp.edit().putString("url", url).putString("key", key).apply()
        try {
            withContext(Dispatchers.IO) {
                val d = JSONObject(api(url, key, "/durum"))
                val p = JSONObject(api(url, key, "/portfoy"))
                val t = JSONArray(api(url, key, "/islemler"))
                val tk = JSONObject(api(url, key, "/takip"))
                durum = "Mod: ${d.getString("mod")} | Gerçek işlem: ${d.getString("gercek_islem")}\n" +
                        "Acil durdurma: ${if (d.getBoolean("acil_durdurma")) "AKTİF" else "kapalı"}"
                val pos = p.getJSONArray("positions")
                pozisyonlar = (0 until pos.length()).map {
                    val x = pos.getJSONObject(it)
                    Pozisyon(x.str("token"), x.optDouble("cost", 0.0), x.optDouble("qty", 0.0) * x.optDouble("last_price", 0.0))
                }
                toplamKz = p.getDouble("pnl")
                ozet = "Nakit: ${usd(p.getDouble("cash"))} USDC\nToplam değer: ${usd(p.getDouble("equity"))} USDC\n" +
                       "Açık pozisyon: ${pos.length()}"
                islemler = (0 until t.length()).map {
                    val x = t.getJSONObject(it)
                    val kz = if (x.optDouble("pnl", 0.0) != 0.0) "  K/Z ${isaretli(x.optDouble("pnl", 0.0))}" else ""
                    "${saat(x.optDouble("ts", 0.0))}  ${x.str("side").uppercase()} ${kisa(x.str("token"))} → ${x.str("decision")}$kz\n${x.str("reason")}"
                }
                val ss = tk.getJSONArray("sinyaller")
                sinyaller = (0 until ss.length()).map {
                    val x = ss.getJSONObject(it)
                    Sinyal(x.optDouble("ts", 0.0), x.str("side"), x.str("token"), x.str("wallet"),
                           x.optDouble("latency_s", 0.0), x.str("source"), x.str("decision"), x.str("reason"))
                }
                val cz = tk.getJSONArray("cuzdanlar")
                cuzdanlar = (0 until cz.length()).map {
                    val x = cz.getJSONObject(it)
                    val q = x.optInt("quarantined", 0)
                    Cuzdan(x.str("wallet"), when (q) { 0 -> "aktif"; 2 -> "bot (durduruldu)"; else -> "karantina" }, x.str("last_error"))
                }
                try {
                    val r = JSONObject(api(url, key, "/rapor"))
                    if (!r.optBoolean("hazir", false)) {
                        rHata = r.str("mesaj")
                    } else {
                        val b = r.getJSONObject("bugun")
                        rKz = b.optDouble("gerceklesen_kz", 0.0)
                        rBugun = "${b.optInt("karar")} karar · ${b.optInt("kopyalanan_alim")} alım kopyalandı · " +
                                 "${b.optInt("kapanan")} işlem kapandı · ${b.optInt("reddedilen")} red"
                        val gr = b.getJSONArray("red_gerekceleri")
                        rGerekce = (0 until gr.length()).map { val x = gr.getJSONObject(it); "${x.optInt("adet")} × ${x.str("gerekce")}" }
                        val go = r.getJSONObject("golge")
                        rGolgeOzet = "${go.optInt("toplam")} gölge işlem, ${go.optInt("acik")} açık"
                        val gg = go.getJSONArray("gruplar")
                        rGolge = (0 until gg.length()).map {
                            val x = gg.getJSONObject(it)
                            "${x.str("grup")}: ${x.optInt("kapanan")} kapanan, ${x.optInt("kazanan")} kazanan, " +
                            "K/Z ${isaretli(x.optDouble("toplam_kz", 0.0))} $, ort. ${String.format(Locale.US, "%+.1f", x.optDouble("ort_getiri", 0.0))}%" +
                            (if (x.optInt("satilamadi") > 0) ", satılamadı ${x.optInt("satilamadi")}" else "")
                        }
                        val cw = r.getJSONArray("cuzdanlar")
                        rCuzdan = (0 until cw.length()).map {
                            val x = cw.getJSONObject(it)
                            CuzdanPerf(x.str("wallet"),
                                "${x.optInt("sinyal")} sinyal · ${x.optInt("kopyalanan")} kopyalandı · ${x.optInt("kapanan")} kapandı · ${x.optInt("acik")} açık",
                                x.optDouble("gerceklesen_kz", 0.0),
                                "Gölge: ${x.optInt("golge_kapanan")} kapanan, K/Z ${isaretli(x.optDouble("golge_kz", 0.0))} $")
                        }
                        rHata = ""
                    }
                } catch (e: Exception) { rHata = "Rapor alınamadı (sunucu güncel olmayabilir): ${e.message}" }
                val g = tk.getJSONObject("gecikme")
                gecikme = listOf("ws" to "Anlık", "poll" to "Yoklama").filter { g.has(it.first) }.joinToString("\n") {
                    val o = g.getJSONObject(it.first)
                    "${it.second}: ${o.getInt("n")} sinyal, P50 ${o.getDouble("p50").toInt()} sn, P95 ${o.getDouble("p95").toInt()} sn"
                }
            }
            hata = ""; guncelleme = "Son güncelleme: " + saat(System.currentTimeMillis() / 1000.0)
        } catch (e: Exception) { hata = "Bağlantı hatası: ${e.message}" }
    }
    fun komut(path: String) = scope.launch {
        try { withContext(Dispatchers.IO) { api(url, key, path, true) }; yenile() }
        catch (e: Exception) { hata = "Hata: ${e.message}" }
    }

    LaunchedEffect(Unit) { while (true) { if (key.isNotEmpty()) yenile(); delay(10_000) } }

    Scaffold(bottomBar = {
        NavigationBar {
            listOf("Durum", "Portföy", "Rapor", "Sinyaller", "İşlemler").forEachIndexed { i, s ->
                NavigationBarItem(selected = tab == i, onClick = { tab = i }, label = { Text(s) }, icon = {})
            }
        }
    }) { pad ->
        LazyColumn(Modifier.padding(pad).padding(horizontal = 16.dp).fillMaxSize(),
                   verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Column {
                    Spacer(Modifier.height(12.dp))
                    Text("NEXORA 2.0", style = MaterialTheme.typography.headlineMedium)
                    if (hata.isNotEmpty()) Text(hata, color = MaterialTheme.colorScheme.error)
                    else if (guncelleme.isNotEmpty()) Text(guncelleme, style = MaterialTheme.typography.bodySmall)
                }
            }
            when (tab) {
                0 -> item {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(durum)
                        OutlinedTextField(url, { url = it }, label = { Text("Sunucu adresi") }, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(key, { key = it }, label = { Text("API anahtarı") }, modifier = Modifier.fillMaxWidth())
                        Button({ yenile() }) { Text("Yenile / Bağlan") }
                        Button({ komut("/acil-durdur") }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                            modifier = Modifier.fillMaxWidth()) { Text("ACİL DURDUR") }
                        OutlinedButton({ komut("/devam") }, modifier = Modifier.fillMaxWidth()) { Text("Devam ettir") }
                    }
                }
                1 -> {
                    item {
                        Column {
                            Text(ozet)
                            Text("K/Z: ${isaretli(toplamKz)} USDC", fontWeight = FontWeight.Bold,
                                 color = if (toplamKz >= 0) YESIL else KIRMIZI)
                            Text("Açık pozisyonlar 5 dakikada bir gerçek satış teklifiyle değerlenir.",
                                 style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    items(pozisyonlar) { p ->
                        val kz = p.deger - p.maliyet
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(12.dp)) {
                                Text(kisa(p.token), fontWeight = FontWeight.Bold)
                                Text("Maliyet ${usd(p.maliyet)} → Değer ${usd(p.deger)} USDC")
                                Text("K/Z ${isaretli(kz)} USDC", color = if (kz >= 0) YESIL else KIRMIZI)
                            }
                        }
                    }
                }
                2 -> {
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Bugün", fontWeight = FontWeight.Bold)
                            if (rHata.isNotEmpty()) Text(rHata, color = KIRMIZI)
                            else {
                                Text(rBugun)
                                Text("Kapanan işlemlerin K/Z: ${isaretli(rKz)} USDC", fontWeight = FontWeight.Bold,
                                     color = if (rKz >= 0) YESIL else KIRMIZI)
                                if (rGerekce.isNotEmpty()) {
                                    Text("En sık red gerekçeleri", style = MaterialTheme.typography.bodySmall)
                                    rGerekce.forEach { Text(it) }
                                }
                                Spacer(Modifier.height(6.dp))
                                Text("Gölge işlemler", fontWeight = FontWeight.Bold)
                                Text("Reddedilen alımlara girseydik ne olurdu: kaynak cüzdan sattığında gerçek teklifle hesaplanır.",
                                     style = MaterialTheme.typography.bodySmall)
                                Text(rGolgeOzet)
                                rGolge.forEach { Text(it) }
                                Spacer(Modifier.height(6.dp))
                                Text("Cüzdan bazında (tüm zamanlar)", fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                    items(rCuzdan) { c ->
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(12.dp)) {
                                Text(kisa(c.adres), fontWeight = FontWeight.Bold)
                                Text(c.ozet, style = MaterialTheme.typography.bodySmall)
                                Text("Gerçekleşen K/Z ${isaretli(c.kz)} USDC", color = if (c.kz >= 0) YESIL else KIRMIZI)
                                Text(c.golge, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                3 -> {
                    item {
                        Column {
                            Text("Gecikme", fontWeight = FontWeight.Bold)
                            Text(if (gecikme.isEmpty()) "henüz sinyal yok" else gecikme)
                            Spacer(Modifier.height(6.dp))
                            Text("Cüzdanlar (${cuzdanlar.count { it.durum == "aktif" }}/${cuzdanlar.size} aktif)", fontWeight = FontWeight.Bold)
                            cuzdanlar.forEach { c ->
                                Text("${kisa(c.adres)}  ${c.durum}" + if (c.durum != "aktif" && c.hata.isNotEmpty()) "  (${c.hata})" else "",
                                     color = if (c.durum == "aktif") Color.Unspecified else KIRMIZI)
                            }
                            Spacer(Modifier.height(6.dp))
                            Text("Son sinyaller", fontWeight = FontWeight.Bold)
                        }
                    }
                    items(sinyaller) { s ->
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(12.dp)) {
                                Text("${saat(s.ts)}  ${s.yon} ${kisa(s.token)}", fontWeight = FontWeight.Bold)
                                Text("Cüzdan ${kisa(s.cuzdan)} · ${s.gecikme.toInt()} sn · ${if (s.kaynak == "ws") "anlık" else "yoklama"}",
                                     style = MaterialTheme.typography.bodySmall)
                                Text("${s.karar}: ${s.neden}", color = if (s.karar == "KOPYALANDI") YESIL else Color.Unspecified)
                            }
                        }
                    }
                }
                else -> items(islemler) { Text(it) }
            }
            item { Spacer(Modifier.height(12.dp)) }
        }
    }
}
