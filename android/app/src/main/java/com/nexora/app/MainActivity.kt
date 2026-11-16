package com.nexora.app

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.*
import org.json.JSONObject

class MainActivity : androidx.fragment.app.FragmentActivity() {   // BiometricPrompt FragmentActivity ister
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(0xFF05080F.toInt()))
        setContent { MaterialTheme(colorScheme = NxRenkler) { Surface(color = Nx.Zemin) { App() } } }
    }
}

private val ANA_SEKMELER = setOf("ana", "kesfet", "portfoy", "karne", "profil")
private val ALT_EKRAN = mapOf("rapor" to "Günlük Rapor", "yol" to "Yol Haritası", "takip" to "Takip Edilen Cüzdanlar", "uye" to "Hesabım", "hazir" to "Hazırlık Karnesi")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App() {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val sp = remember { ctx.getSharedPreferences("nx", Context.MODE_PRIVATE) }
    var url by remember { mutableStateOf(sp.getString("url", "http://127.0.0.1:8000")!!) }
    var key by remember { mutableStateOf(Kasa.oku(sp, "key").trim()) }
    var ekran by rememberSaveable { mutableStateOf("ana") }
    var durdurOnay by remember { mutableStateOf(false) }
    var acilis by rememberSaveable { mutableStateOf(true) }
    LaunchedEffect(Unit) { Gorunum.sade = sp.getBoolean("sade", false) }
    val v = remember { Veri() }
    var yenileniyor by remember { mutableStateOf(false) }

    // ekran durumları
    var gizle by remember { mutableStateOf(sp.getBoolean("gizle", false)) }
    var aralik by rememberSaveable { mutableStateOf("1G") }
    var kesfetSekme by rememberSaveable { mutableIntStateOf(0) }
    var eko by rememberSaveable { mutableStateOf("tumu") }
    var radarArama by rememberSaveable { mutableStateOf("") }
    var radarSira by rememberSaveable { mutableIntStateOf(0) }
    var favoriler by remember { mutableStateOf(sp.getStringSet("favori", emptySet())!!.toSet()) }
    var dnaAdres by rememberSaveable { mutableStateOf("") }
    var dnaSonuc by remember { mutableStateOf<JSONObject?>(null) }
    var dnaHata by remember { mutableStateOf("") }
    var dnaYukleniyor by remember { mutableStateOf(false) }
    var portfoySekme by rememberSaveable { mutableIntStateOf(0) }
    var seciliToken by rememberSaveable { mutableStateOf("") }
    var islemSonuc by remember { mutableStateOf("") }
    var islemMesgul by remember { mutableStateOf(false) }

    // kilit
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

    // bildirim
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

    suspend fun yukleSessiz() {
        if (key.isEmpty()) return
        try {
            withContext(Dispatchers.IO) { v.yukle(url, key) }
            v.bagli = true; v.hata = ""; v.guncelleme = System.currentTimeMillis() / 1000.0
        } catch (e: Exception) {
            v.bagli = false
            v.hata = when {
                e.message?.contains("401") == true -> "API anahtarı sunucudakiyle aynı değil."
                url.contains("127.0.0.1") -> "Sunucuya bağlanılamadı: adres hâlâ telefonun kendisi (127.0.0.1)."
                else -> "Sunucuya bağlanılamadı. Tailscale açık mı?"
            }
        }
    }
    fun yenile() = scope.launch { yukleSessiz() }
    // Gösterge her durumda kapanabilsin diye en az 600 ms sürer (anında biten yenileme göstergeyi askıda bırakıyordu).
    fun cekYenile() = scope.launch {
        yenileniyor = true
        val bas = System.currentTimeMillis()
        yukleSessiz()
        val kalan = 600 - (System.currentTimeMillis() - bas)
        if (kalan > 0) delay(kalan)
        yenileniyor = false
    }
    fun mesaj(m: String) = android.widget.Toast.makeText(ctx, m, android.widget.Toast.LENGTH_LONG).show()
    fun komut(path: String) = scope.launch {
        try { withContext(Dispatchers.IO) { api(url, key, path, true) }; yukleSessiz() }
        catch (e: Exception) { v.hata = "Komut gönderilemedi: ${e.message}"; mesaj("Komut gönderilemedi: ${e.message}") }
    }
    fun riskKaydet(j: JSONObject) = scope.launch {
        try {
            withContext(Dispatchers.IO) { api(url, key, "/ayarlar", true, j.toString()) }
            yukleSessiz(); mesaj("Risk ayarı kaydedildi")
        } catch (e: Exception) { v.hata = "Kaydedilemedi: ${e.message}"; mesaj("Kaydedilemedi: ${e.message}") }
    }
    fun modelKapat() = scope.launch {
        try {
            withContext(Dispatchers.IO) { api(url, key, "/model-filtre", true, "{\"acik\": false}") }
            yukleSessiz(); mesaj("Yapay zekâ filtresi kapatıldı")
        } catch (e: Exception) { v.hata = "Kapatılamadı: ${e.message}"; mesaj("Kapatılamadı: ${e.message}") }
    }
    fun yedekIndir() = scope.launch {
        try {
            val yer = withContext(Dispatchers.IO) {
                api(url, key, "/yedek", true)
                val (ad, veri) = Yedek.indir(url, key)
                Yedek.kaydet(ctx, ad, veri).also { sp.edit().putString("yedek_son_ad", ad).apply() }
            }
            mesaj("Yedek kaydedildi: $yer")
        } catch (e: Exception) {
            val neden = if (e.message?.contains("404") == true) "sunucu güncel değil (sudo bash /opt/nexora/deploy/guncelle.sh)" else e.message
            v.hata = "Yedek indirilemedi: $neden"; mesaj("Yedek indirilemedi: $neden")
        }
    }
    fun dnaAnaliz() = scope.launch {
        dnaYukleniyor = true; dnaHata = ""
        try {
            val r = withContext(Dispatchers.IO) {
                api(url, key, "/cuzdan-dna", true, JSONObject().put("adres", dnaAdres.trim()).toString(), zamanAsimi = 90_000)
            }
            dnaSonuc = JSONObject(r)
        } catch (e: Exception) {
            dnaHata = when {
                e.message?.contains("429") == true -> "Günlük analiz sınırı doldu (Helius kredisi korunuyor)."
                e.message?.contains("404") == true -> "Sunucu güncel değil: sudo bash /opt/nexora/deploy/guncelle.sh"
                else -> "Analiz yapılamadı: ${e.message}"
            }
        }
        dnaYukleniyor = false
    }
    fun manuelIslem(token: String, yon: String, usdTutar: Double?) = scope.launch {
        islemMesgul = true; islemSonuc = ""
        try {
            val g = JSONObject().put("token", token).put("yon", yon); if (usdTutar != null) g.put("usd", usdTutar)
            val r = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/manuel", true, g.toString(), zamanAsimi = 45_000) })
            islemSonuc = "${r.str("decision")}: ${r.str("reason")}"
            yukleSessiz()
        } catch (e: Exception) {
            islemSonuc = if (e.message?.contains("404") == true) "Sunucu güncel değil: sudo bash /opt/nexora/deploy/guncelle.sh"
                         else "İşlem yapılamadı: ${e.message}"
        }
        islemMesgul = false
    }
    LaunchedEffect(key, url) { while (true) { yukleSessiz(); delay(15_000) } }
    BackHandler(enabled = ekran != "ana") { ekran = when { ekran == "hazir" -> "karne"; ekran in ALT_EKRAN || ekran == "bot" -> "profil"; else -> "ana" } }

    if (acilis) { AcilisEkrani { acilis = false }; return }
    if (kilitli) { Box(Modifier.fillMaxSize()) { AiArkaplan(); KilitEkrani(sp) { kilitli = false } }; return }

    if (durdurOnay) {
        AlertDialog(
            onDismissRequest = { durdurOnay = false },
            icon = { IkonKalkan(Nx.Kirmizi, 32.dp) },
            title = { Text("NEXORA Shield · Acil durdurma") },
            text = { Text("Bot yeni alım yapmayı durduracak. Açık pozisyonlar yerinde kalır. Emin misiniz?") },
            confirmButton = { TextButton({ durdurOnay = false; komut("/acil-durdur") }) { Text("Durdur", color = Nx.Kirmizi) } },
            dismissButton = { TextButton({ durdurOnay = false }) { Text("Vazgeç") } },
            containerColor = Nx.Yuzey2, shape = RoundedCornerShape(24.dp),
        )
    }

    val menuSecili = when { ekran in ANA_SEKMELER -> ekran; ekran == "takip" -> "kesfet"; ekran == "hazir" -> "karne"; else -> "profil" }
    Box(Modifier.fillMaxSize()) {
    AiArkaplan()
    Scaffold(containerColor = Color.Transparent, bottomBar = { AltMenu2(menuSecili) { ekran = it } }) { pad ->
        PullToRefreshBox(isRefreshing = yenileniyor, onRefresh = { cekYenile() }, modifier = Modifier.padding(pad).fillMaxSize()) {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                if (ekran == "ana") item(key = "ust") { AnaUstBaslik({ ekran = it }) }
                if (ekran in ALT_EKRAN) item(key = "alt_bas") {
                    SayfaBasligi(ALT_EKRAN[ekran]!!, when (ekran) { "takip" -> "Analiz ve takip durumu"; "uye" -> "Üyelik, davet ve bağlantılar"; "hazir" -> "Gerçek paraya geçiş ölçütleri"; else -> "NEXORA" }, geri = { ekran = if (ekran == "hazir") "karne" else "profil" })
                }
                val bagliDegil = !v.bagli && v.guncelleme == 0.0
                if (v.hata.isNotEmpty() && !(bagliDegil && ekran == "ana")) item(key = "hata") { Text(v.hata, color = Nx.Kirmizi, fontSize = 13.sp) }
                if (bagliDegil && ekran == "ana") item(key = "baglan") {
                    BaglanKarti(url, key, v.hata) { u, k ->
                        url = u; key = k
                        sp.edit().putString("url", u).apply(); Kasa.yaz(sp, "key", k)
                        cekYenile()
                    }
                } else when (ekran) {
                    "ana" -> anaSayfa(v, gizle, { gizle = !gizle; sp.edit().putBoolean("gizle", gizle).apply() }, aralik, { aralik = it },
                                      { ekran = it }, eko, { eko = it }, { mesaj(it) }, { durdurOnay = true })
                    "karne" -> karne(v) { ekran = it }
                    "kesfet" -> {
                        item(key = "k_sekme") {
                            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(50)).background(Nx.Yuzey2).padding(4.dp),
                                horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                listOf("Token Radar", "Wallet DNA", "Takip").forEachIndexed { i, ad -> Hap(ad, kesfetSekme == i, Modifier.weight(1f)) { kesfetSekme = i } }
                            }
                        }
                        when (kesfetSekme) {
                            0 -> tokenRadar(v, radarArama, { radarArama = it }, radarSira, { radarSira = it }, favoriler,
                                    { t -> favoriler = if (t in favoriler) favoriler - t else favoriler + t; sp.edit().putStringSet("favori", favoriler).apply() },
                                    { t -> seciliToken = t.token; portfoySekme = 0; ekran = "portfoy" })
                            1 -> walletDna(v, dnaAdres, { dnaAdres = it; dnaSonuc = null }, dnaYukleniyor, dnaSonuc, dnaHata) { dnaAnaliz() }
                            else -> takipListesi(v)
                        }
                    }
                    "takip" -> takipListesi(v)
                    "bot" -> {
                        autoPilot(v, { ekran = "profil" }, { riskKaydet(it) }, { komut("/devam") }, { durdurOnay = true }, { modelKapat() })
                        item(key = "bot_ayrinti") { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { BotEkrani(v, { durdurOnay = true }, { komut("/devam") }) } }
                        items(v.sinyaller, key = { "s_" + it.ts + it.token + it.yon }) { SinyalKarti(it) }
                    }
                    "portfoy" -> portfoy(v, { ekran = "ana" }, portfoySekme, { portfoySekme = it }, { t -> manuelIslem(t, "sell", null); mesaj("Kapatma isteği gönderildi") }) {
                        IslemFormu(v, seciliToken, { seciliToken = it }, { t, y, u -> manuelIslem(t, y, u) }, islemSonuc, islemMesgul)
                    }
                    "profil" -> profil(v, { ekran = it }) {
                        AyarlarEkrani(v, url, key, bildirim, { acik ->
                            if (acik && android.os.Build.VERSION.SDK_INT >= 33 &&
                                androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.POST_NOTIFICATIONS) !=
                                android.content.pm.PackageManager.PERMISSION_GRANTED) {
                                izinIste.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                            } else bildirimAyarla(acik)
                        }, { riskKaydet(it) }, { yedekIndir() }) { u, k ->
                            url = u; key = k
                            sp.edit().putString("url", u).apply(); Kasa.yaz(sp, "key", k)
                            yenile()
                        }
                        KilitAyari(sp)
                        GorunumAyari(sp)
                    }
                    "hazir" -> item(key = "hazir") { HazirlikEkrani(v) }
                    "uye" -> item(key = "uye") { UyeEkrani(url, key, sp) }
                    "rapor" -> item(key = "rapor") { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { RaporEkrani(v) } }
                    "yol" -> {
                        item(key = "yol_ozet") {
                            val ort = if (v.asamalar.isEmpty()) 0 else v.asamalar.sumOf { it.yuzde } / v.asamalar.size
                            NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
                                Text("Genel ilerleme %$ort", color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                                Text("${v.asamalar.count { it.durum == "ileri" }} ileri · ${v.asamalar.count { it.durum == "devam" }} devam ediyor · " +
                                     "${v.asamalar.count { it.durum == "baslamadi" }} başlamadı", color = Nx.Soluk, fontSize = 13.sp)
                                if (v.asamaGuncelleme.isNotEmpty()) Text(v.asamaGuncelleme, color = Nx.Soluk, fontSize = 11.sp)
                            }
                        }
                        items(v.asamalar, key = { "a_" + it.kod }) { AsamaKarti(it) }
                    }
                }
                if (v.guncelleme > 0) item(key = "son") {
                    Text("Son güncelleme ${saat(v.guncelleme)} · aşağı çekerek yenileyin", color = Nx.Soluk, fontSize = 11.sp,
                         modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
    }
}

fun androidx.compose.foundation.lazy.LazyListScope.takipListesi(v: Veri) {
    item(key = "t_ozet") { CuzdanOzeti(v) }
    if (v.cuzdanlar.isEmpty()) item(key = "t_bos") { Text("Cüzdan analizi bulunamadı: sunucuda cuzdan_analiz.py çalıştırın.", color = Nx.Soluk) }
    itemsIndexed(v.cuzdanlar, key = { _, c -> "c_" + c.adres }) { i, c -> CuzdanKarti(i + 1, c) }
}

@Composable
fun AnaUstBaslik(git: (String) -> Unit) {
    var menu by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box {
            IconButton({ menu = true }) { Icon(Icons.Filled.Menu, "Menü", tint = Nx.Metin) }
            DropdownMenu(menu, { menu = false }, containerColor = Nx.Yuzey2) {
                DropdownMenuItem({ Text("Günlük Rapor") }, { menu = false; git("rapor") })
                DropdownMenuItem({ Text("Yol Haritası") }, { menu = false; git("yol") })
                DropdownMenuItem({ Text("Takip Edilen Cüzdanlar") }, { menu = false; git("takip") })
                DropdownMenuItem({ Text("Ayarlar") }, { menu = false; git("profil") })
            }
        }
        Box(Modifier.weight(1f), contentAlignment = Alignment.Center) { Logo(24.sp) }
        Box {
            IconButton({ git("rapor") }) { Icon(Icons.Filled.Notifications, "Rapor", tint = Nx.Metin) }
            Box(Modifier.align(Alignment.TopEnd).padding(top = 10.dp, end = 10.dp).size(8.dp).clip(CircleShape).background(Nx.Mor))
        }
    }
}


/** Bağlantı yokken Ana Sayfa'da yalnızca bu kart görünür (sıfır bakiye gibi yanıltıcı değerler gösterilmez). */
@Composable
fun BaglanKarti(url: String, key: String, hata: String, kaydet: (String, String) -> Unit) {
    var u by remember(url) { mutableStateOf(if (url.contains("127.0.0.1")) "http://100.105.213.95:8000" else url) }
    var k by remember(key) { mutableStateOf(key) }
    Column {
    NexoKonusuyor(if (hata.isEmpty()) "Merhaba! Ben Nexo, NEXORA'nın yapay zekâ robotu. Sunucuya bağlanınca işe koyuluyorum."
                  else "Sunucuya ulaşamadım. Tailscale açık mı? Adresi ve anahtarı bir kontrol edelim.",
                  if (hata.isEmpty()) NexoIfade.KIRPMA else NexoIfade.DUSUN, Modifier.fillMaxWidth().padding(bottom = 12.dp),
                  poz = if (hata.isEmpty()) NexoPoz.SELAM else NexoPoz.SERBEST)
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
        Text("Sunucuya bağlan", color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Text("Bakiye, bot ve işlemler sunucudan gelir. Telefonda Tailscale açık olmalı.", color = Nx.Soluk, fontSize = 13.sp)
        OutlinedTextField(u, { u = it }, label = { Text("Sunucu adresi") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp))
        OutlinedTextField(k, { k = it }, label = { Text("API anahtarı") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp), visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation())
        Button({ kaydet(u.trim(), k.trim()) }, enabled = u.isNotBlank() && k.isNotBlank(), colors = NxButonRenk(),
            modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) {
            NexoYuz(30.dp, NexoIfade.KIRPMA); Text(" Bağlan", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
        Text("Anahtar sunucuda: sudo grep NEXORA_API_KEY /etc/nexora.env", color = Nx.Soluk, fontSize = 11.sp)
    }
    }
}
