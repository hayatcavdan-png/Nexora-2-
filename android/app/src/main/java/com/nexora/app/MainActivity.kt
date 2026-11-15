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
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

fun api(base: String, key: String, path: String, post: Boolean = false): String {
    val c = URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("X-API-Key", key)
    if (post) { c.requestMethod = "POST"; c.doOutput = true; c.outputStream.write("{}".toByteArray()) }
    if (c.responseCode != 200) error("HTTP ${c.responseCode}")
    return c.inputStream.bufferedReader().readText()
}

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
    var url by remember { mutableStateOf(sp.getString("url", "http://192.168.1.10:8000")!!) }
    var key by remember { mutableStateOf(sp.getString("key", "")!!) }
    var tab by remember { mutableIntStateOf(0) }
    var durum by remember { mutableStateOf("—") }
    var portfoy by remember { mutableStateOf("—") }
    var islemler by remember { mutableStateOf(listOf<String>()) }
    var hata by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    fun yenile() = scope.launch {
        sp.edit().putString("url", url).putString("key", key).apply()
        try {
            withContext(Dispatchers.IO) {
                val d = JSONObject(api(url, key, "/durum"))
                val p = JSONObject(api(url, key, "/portfoy"))
                val t = JSONArray(api(url, key, "/islemler"))
                durum = "Mod: ${d.getString("mod")} | Gerçek işlem: ${d.getString("gercek_islem")}\n" +
                        "Acil durdurma: ${if (d.getBoolean("acil_durdurma")) "AKTİF" else "kapalı"}"
                portfoy = "Nakit: %.2f USDC\nToplam değer: %.2f USDC\nK/Z: %.2f USDC\nAçık pozisyon: %d".format(
                    p.getDouble("cash"), p.getDouble("equity"), p.getDouble("pnl"), p.getJSONArray("positions").length())
                islemler = (0 until t.length()).map {
                    val x = t.getJSONObject(it)
                    "${x.getString("side").uppercase()} ${x.getString("token")} → ${x.getString("decision")} (${x.getString("reason")})"
                }
            }
            hata = ""
        } catch (e: Exception) { hata = "Bağlantı hatası: ${e.message}" }
    }
    fun komut(path: String) = scope.launch {
        try { withContext(Dispatchers.IO) { api(url, key, path, true) }; yenile() }
        catch (e: Exception) { hata = "Hata: ${e.message}" }
    }

    LaunchedEffect(Unit) { while (true) { if (key.isNotEmpty()) yenile(); delay(10_000) } }

    Scaffold(bottomBar = {
        NavigationBar {
            listOf("Durum", "Portföy", "İşlemler").forEachIndexed { i, s ->
                NavigationBarItem(selected = tab == i, onClick = { tab = i }, label = { Text(s) }, icon = {})
            }
        }
    }) { pad ->
        Column(Modifier.padding(pad).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("NEXORA 2.0", style = MaterialTheme.typography.headlineMedium)
            if (hata.isNotEmpty()) Text(hata, color = MaterialTheme.colorScheme.error)
            when (tab) {
                0 -> {
                    Text(durum)
                    OutlinedTextField(url, { url = it }, label = { Text("Sunucu adresi") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(key, { key = it }, label = { Text("API anahtarı") }, modifier = Modifier.fillMaxWidth())
                    Button({ yenile() }) { Text("Yenile / Bağlan") }
                    Button({ komut("/acil-durdur") }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        modifier = Modifier.fillMaxWidth()) { Text("ACİL DURDUR") }
                    OutlinedButton({ komut("/devam") }, modifier = Modifier.fillMaxWidth()) { Text("Devam ettir") }
                }
                1 -> Text(portfoy)
                else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) { items(islemler) { Text(it) } }
            }
        }
    }
}
