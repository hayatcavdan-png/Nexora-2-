package com.nexora.app

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.*

class MainActivity : ComponentActivity() {
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        setContent { MaterialTheme(colorScheme = NxRenkler) { Surface(color = Nx.Zemin) { App() } } }
    }
}

private val SEKMELER = listOf(
    Triple("panel", "Ana Panel", Icons.Filled.Home),
    Triple("bot", "Bot", Icons.Filled.Face),
    Triple("cuzdanlar", "Cüzdanlar", Icons.Filled.Person),
    Triple("islemler", "İşlemler", Icons.Filled.List),
    Triple("ayarlar", "Ayarlar", Icons.Filled.Settings),
)
private val ALT_EKRAN = mapOf("rapor" to "Günlük Rapor", "yol" to "Yol Haritası")

@Composable
fun App() {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val sp = remember { ctx.getSharedPreferences("nx", Context.MODE_PRIVATE) }
    var url by remember { mutableStateOf(sp.getString("url", "http://127.0.0.1:8000")!!) }
    var key by remember { mutableStateOf(sp.getString("key", "")!!.trim()) }
    var ekran by remember { mutableStateOf("panel") }
    var islemSekme by remember { mutableIntStateOf(0) }
    var durdurOnay by remember { mutableStateOf(false) }
    val v = remember { Veri() }
    var kilitli by remember { mutableStateOf(Kilit.var_(sp)) }
    val yasam = androidx.compose.ui.platform.LocalLifecycleOwner.current
    DisposableEffect(yasam) {
        var arka = 0L
        val g = androidx.lifecycle.LifecycleEventObserver { _, olay ->
            if (olay == androidx.lifecycle.Lifecycle.Event.ON_STOP) arka = System.currentTimeMillis()
            if (olay == androidx.lifecycle.Lifecycle.Event.ON_START && arka > 0 &&
                System.currentTimeMillis() - arka > 60_000 && Kilit.var_(sp)) kilitli = true
        }
        yasam.lifecycle.addObserver(g)
        onDispose { yasam.lifecycle.removeObserver(g) }
    }
    var bildirim by remember { mutableStateOf(sp.getBoolean("bildirim", false)) }
    fun bildirimAyarla(acik: Boolean) {
        bildirim = acik
        sp.edit().putBoolean("bildirim", acik).apply()
        if (acik) BildirimServisi.baslat(ctx) else BildirimServisi.durdur(ctx)
    }
    val izinIste = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { verildi ->
        bildirimAyarla(verildi)
        if (!verildi) v.hata = "Bildirim izni verilmedi: telefon ayarlarından NEXORA için bildirimlere izin verin."
    }
    LaunchedEffect(Unit) { if (bildirim) BildirimServisi.baslat(ctx) }
    val scope = rememberCoroutineScope()

    fun yenile() = scope.launch {
        if (key.isEmpty()) return@launch
        try {
            withContext(Dispatchers.IO) { v.yukle(url, key) }
            v.bagli = true; v.hata = ""; v.guncelleme = System.currentTimeMillis() / 1000.0
        } catch (e: Exception) {
            v.bagli = false
            v.hata = if (e.message?.contains("401") == true) "API anahtarı sunucudakiyle aynı değil (HTTP 401)"
                     else "Bağlantı hatası: ${e.message}"
        }
    }
    fun komut(path: String) = scope.launch {
        try { withContext(Dispatchers.IO) { api(url, key, path, true) }; yenile() }
        catch (e: Exception) { v.hata = "Komut gönderilemedi: ${e.message}" }
    }
    fun riskKaydet(j: org.json.JSONObject) = scope.launch {
        try {
            withContext(Dispatchers.IO) { api(url, key, "/ayarlar", true, j.toString()) }
            yenile()
            android.widget.Toast.makeText(ctx, "Risk sınırları kaydedildi", android.widget.Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            v.hata = "Kaydedilemedi: ${e.message}"
            android.widget.Toast.makeText(ctx, "Kaydedilemedi: ${e.message}", android.widget.Toast.LENGTH_LONG).show()
        }
    }
    fun yedekIndir() = scope.launch {
        try {
            val yer = withContext(Dispatchers.IO) {
                api(url, key, "/yedek", true)
                val (ad, veri) = Yedek.indir(url, key)
                Yedek.kaydet(ctx, ad, veri).also { sp.edit().putString("yedek_son_ad", ad).apply() }
            }
            android.widget.Toast.makeText(ctx, "Yedek kaydedildi: $yer", android.widget.Toast.LENGTH_LONG).show()
        } catch (e: Exception) {
            val neden = if (e.message?.contains("404") == true) "sunucu güncel değil (sudo bash /opt/nexora/deploy/guncelle.sh)" else e.message
            v.hata = "Yedek indirilemedi: $neden"
            android.widget.Toast.makeText(ctx, "Yedek indirilemedi: $neden", android.widget.Toast.LENGTH_LONG).show()
        }
    }
    LaunchedEffect(Unit) { while (true) { yenile(); delay(10_000) } }
    BackHandler(enabled = ekran != "panel") { ekran = "panel" }

    if (kilitli) { KilitEkrani(sp) { kilitli = false }; return }

    if (durdurOnay) {
        AlertDialog(
            onDismissRequest = { durdurOnay = false },
            title = { Text("Acil durdurma") },
            text = { Text("Bot yeni alım yapmayı durduracak. Açık pozisyonlar yerinde kalır. Emin misiniz?") },
            confirmButton = { TextButton({ durdurOnay = false; komut("/acil-durdur") }) { Text("Durdur", color = Nx.Kirmizi) } },
            dismissButton = { TextButton({ durdurOnay = false }) { Text("Vazgeç") } },
            containerColor = Nx.Yuzey2,
        )
    }

    Scaffold(
        containerColor = Nx.Zemin,
        bottomBar = {
            NavigationBar(containerColor = Nx.Yuzey) {
                SEKMELER.forEach { (id, ad, ikon) ->
                    val secili = ekran == id || (id == "panel" && ekran in ALT_EKRAN)
                    NavigationBarItem(
                        selected = secili, onClick = { ekran = id },
                        icon = { Icon(ikon, ad) }, label = { Text(ad, fontSize = 11.sp, maxLines = 1) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Nx.Camgobegi, selectedTextColor = Nx.Camgobegi,
                            unselectedIconColor = Nx.Soluk, unselectedTextColor = Nx.Soluk,
                            indicatorColor = Nx.Mor.copy(alpha = 0.25f)),
                    )
                }
            }
        },
    ) { pad ->
        LazyColumn(
            Modifier.padding(pad).fillMaxSize().background(Nx.Zemin).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (ekran == "panel") Logo()
                    else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (ekran in ALT_EKRAN) IconButton({ ekran = "panel" }) { Icon(Icons.Filled.ArrowBack, "Geri", tint = Nx.Metin) }
                        Text(ALT_EKRAN[ekran] ?: SEKMELER.first { it.first == ekran }.second,
                             color = Nx.Metin, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                    }
                    if (v.hata.isNotEmpty()) Text(v.hata, color = Nx.Kirmizi, fontSize = 13.sp)
                    else if (v.guncelleme > 0) Text("Son güncelleme ${saat(v.guncelleme)} · PAPER modu · gerçek işlem kapalı",
                                                    color = Nx.Soluk, fontSize = 12.sp)
                }
            }
            when (ekran) {
                "panel" -> item {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        AnaPanel(v, key.isNotEmpty(), { ekran = it }, { durdurOnay = true }, { komut("/devam") })
                    }
                }
                "bot" -> {
                    item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { BotEkrani(v, { durdurOnay = true }, { komut("/devam") }) } }
                    items(v.sinyaller) { SinyalKarti(it) }
                }
                "cuzdanlar" -> {
                    item { CuzdanOzeti(v) }
                    if (v.cuzdanlar.isEmpty()) item {
                        Text("Cüzdan analizi bulunamadı: backend klasöründe cuzdan_analiz.py çalıştırın.", color = Nx.Soluk)
                    }
                    itemsIndexed(v.cuzdanlar) { i, c -> CuzdanKarti(i + 1, c) }
                }
                "islemler" -> {
                    item {
                        TabRow(selectedTabIndex = islemSekme, containerColor = Nx.Yuzey, contentColor = Nx.Camgobegi) {
                            Tab(selected = islemSekme == 0, onClick = { islemSekme = 0 }, text = { Text("Açık pozisyonlar (${v.pozisyonlar.size})") })
                            Tab(selected = islemSekme == 1, onClick = { islemSekme = 1 }, text = { Text("İşlem geçmişi") })
                        }
                    }
                    if (islemSekme == 0) {
                        if (v.pozisyonlar.isEmpty()) item { Text("Açık pozisyon yok.", color = Nx.Soluk) }
                        items(v.pozisyonlar) { PozisyonKarti(it) }
                        item { PerformansOzeti(v) }
                    } else {
                        items(v.islemler) { IslemSatiri(it) }
                    }
                }
                "rapor" -> item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { RaporEkrani(v) } }
                "yol" -> {
                    item {
                        val ort = if (v.asamalar.isEmpty()) 0 else v.asamalar.sumOf { it.yuzde } / v.asamalar.size
                        NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
                            Text("Genel ilerleme %$ort", color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                            Text("${v.asamalar.count { it.durum == "ileri" }} ileri · ${v.asamalar.count { it.durum == "devam" }} devam ediyor · " +
                                 "${v.asamalar.count { it.durum == "baslamadi" }} başlamadı", color = Nx.Soluk, fontSize = 13.sp)
                            if (v.asamaGuncelleme.isNotEmpty()) Text(v.asamaGuncelleme, color = Nx.Soluk, fontSize = 11.sp)
                        }
                    }
                    items(v.asamalar) { AsamaKarti(it) }
                }
                "ayarlar" -> item {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        AyarlarEkrani(v, url, key, bildirim, { acik ->
                            if (acik && android.os.Build.VERSION.SDK_INT >= 33 &&
                                androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.POST_NOTIFICATIONS) !=
                                android.content.pm.PackageManager.PERMISSION_GRANTED) {
                                izinIste.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                            } else bildirimAyarla(acik)
                        }, { riskKaydet(it) }, { yedekIndir() }) { u, k ->
                            url = u; key = k
                            sp.edit().putString("url", u).putString("key", k).apply()
                            yenile()
                        }
                        KilitAyari(sp)
                    }
                }
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}
