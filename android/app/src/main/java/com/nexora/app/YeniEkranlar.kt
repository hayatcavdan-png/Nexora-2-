package com.nexora.app

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Calendar

/*
 * 5.26.0 · Yeni arayüz (kullanıcı onaylı tasarım, 22.11.2026).
 * Üye: 4 sekme (Ana Sayfa · Cüzdanlar · İşlemler · Profil) + NEXO Asistan. Yalnızca Solana; borsalar üyeye görünmez.
 * Yönetici: Profil'deki turuncu karttan açılan ayrı mod (turuncu şerit). Ölçümler, teşhis, sistem, borsalar burada.
 */

// ------------------------------------------------------------------ ortak parçalar

/** Nabız gibi atan neon ışık + kenar. Kartın DIŞINA taşar; kırpmadan (clip) önce uygulanmalı. */
fun Modifier.neonIsik(renk: Color, kose: Dp = 24.dp): Modifier = composed {
    val t: State<Float> = if (Gorunum.sade) remember { mutableFloatStateOf(0.5f) }
        else rememberInfiniteTransition(label = "neon").animateFloat(0f, 1f, infiniteRepeatable(tween(1300, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "n")
    drawWithContent {
        val k = kose.toPx(); val tv = t.value
        for (i in 1..4) {
            val e = i * 3.dp.toPx()
            drawRoundRect(renk.copy(alpha = (0.08f + 0.14f * tv) / i), Offset(-e, -e), Size(size.width + 2 * e, size.height + 2 * e),
                CornerRadius(k + e), style = Stroke(3.dp.toPx()))
        }
        drawContent()
        val w = 1.5.dp.toPx()
        drawRoundRect(renk.copy(alpha = 0.55f + 0.45f * tv), Offset(w / 2, w / 2), Size(size.width - w, size.height - w), CornerRadius(k), style = Stroke(w))
    }
}

/** Nabız gibi atan küçük nokta ("çalışıyor"). */
@Composable
fun NabizNokta(renk: Color = Nx.Nane, boyut: Dp = 9.dp) {
    val t by rememberInfiniteTransition(label = "nabiz").animateFloat(0f, 1f, infiniteRepeatable(tween(1600, easing = LinearEasing)), label = "t")
    Box(Modifier.size(boyut * 2.4f), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            drawCircle(renk.copy(alpha = 0.55f * (1f - t)), size.minDimension / 2f * (0.4f + 0.6f * t))
            drawCircle(renk, boyut.toPx() / 2f)
        }
    }
}

@Composable
fun IkonCuzdan(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.085f, cap = StrokeCap.Round, join = StrokeJoin.Round)
    drawRoundRect(renk, Offset(w * 0.12f, w * 0.25f), Size(w * 0.76f, w * 0.58f), CornerRadius(w * 0.12f), style = s)
    drawLine(renk, Offset(w * 0.12f, w * 0.42f), Offset(w * 0.88f, w * 0.42f), s.width, StrokeCap.Round)
    drawLine(renk, Offset(w * 0.64f, w * 0.62f), Offset(w * 0.74f, w * 0.62f), s.width, StrokeCap.Round)
}

@Composable
fun IkonAkis(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.085f, cap = StrokeCap.Round, join = StrokeJoin.Round)
    drawPath(Path().apply { moveTo(w * 0.3f, w * 0.82f); lineTo(w * 0.3f, w * 0.18f); moveTo(w * 0.14f, w * 0.34f); lineTo(w * 0.3f, w * 0.18f); lineTo(w * 0.46f, w * 0.34f) }, renk, style = s)
    drawPath(Path().apply { moveTo(w * 0.7f, w * 0.18f); lineTo(w * 0.7f, w * 0.82f); moveTo(w * 0.54f, w * 0.66f); lineTo(w * 0.7f, w * 0.82f); lineTo(w * 0.86f, w * 0.66f) }, renk, style = s)
}

/** Üyenin alt menüsü: dört sekme; seçilen neon camgöbeği yanar, zıplayarak büyür, altında neon çizgi. */
@Composable
fun UyeAltMenu(secili: String, sec: (String) -> Unit) {
    val sekmeler = listOf("ana" to "Ana Sayfa", "cuzdanlar" to "Cüzdanlar", "islemler" to "İşlemler", "profil" to "Profil")
    Column(Modifier.fillMaxWidth().background(Nx.Yuzey)) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(Nx.Cizgi))
        Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 6.dp)) {
            sekmeler.forEach { (id, ad) ->
                val s = id == secili
                val olcek by animateFloatAsState(if (s) 1.15f else 1f, spring(dampingRatio = 0.42f, stiffness = 380f), label = "sk")
                val renk = if (s) Nx.Gok else Color(0xFF8C87AA)
                Column(Modifier.weight(1f).heightIn(min = 52.dp).tiklaZipla { sec(id) }.padding(vertical = 4.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Box(Modifier.graphicsLayer { scaleX = olcek; scaleY = olcek }) {
                        when (id) {
                            "ana" -> Icon(Icons.Filled.Home, null, tint = renk, modifier = Modifier.size(24.dp))
                            "cuzdanlar" -> IkonCuzdan(renk)
                            "islemler" -> IkonAkis(renk)
                            else -> Icon(Icons.Filled.AccountCircle, null, tint = renk, modifier = Modifier.size(24.dp))
                        }
                    }
                    Text(ad, color = renk, fontSize = 11.sp, fontWeight = if (s) FontWeight.Bold else FontWeight.Normal, maxLines = 1)
                    Box(Modifier.size(width = if (s) 20.dp else 0.dp, height = 3.dp).clip(RoundedCornerShape(50)).background(Nx.Gok))
                }
            }
        }
    }
}

/** Yönetici modunun üst şeridi: hangi modda olduğun her an belli. */
@Composable
fun YoneticiSeridi(panelde: Boolean, panel: () -> Unit, donus: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(Nx.Turuncu).padding(start = 8.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        if (!panelde) IconButton(panel) { Icon(Icons.Filled.ArrowBack, "Panele dön", tint = Color(0xFF1A1203)) }
        else Box(Modifier.padding(start = 8.dp, end = 4.dp)) { IkonKalkan(Color(0xFF1A1203), 18.dp) }
        Text(if (panelde) " YÖNETİCİ MODU" else " PANEL", color = Color(0xFF1A1203), fontSize = 13.sp, fontWeight = FontWeight.Black, letterSpacing = 1.5.sp,
             fontFamily = Orbitron, modifier = Modifier.weight(1f))
        TextButton(donus) { Text("Üye görünümü", color = Color(0xFF1A1203), fontWeight = FontWeight.Bold, fontSize = 13.sp) }
    }
}

private fun sembol(v: Veri, token: String, bilinen: String = ""): String =
    bilinen.ifBlank { v.radar.firstOrNull { it.token == token }?.sembol?.takeIf { it.isNotBlank() } ?: kisa(token) }

private val TOKEN_RENK = listOf(Color(0xFFFB923C), Color(0xFF38BDF8), Color(0xFFF472B6), Color(0xFF39FF88), Color(0xFFA78BFA), Color(0xFFFBBF24))
private fun tokenRenk(t: String) = TOKEN_RENK[(t.hashCode() and 0x7fffffff) % TOKEN_RENK.size]

@Composable
private fun TokenRozet(ad: String, boyut: Dp = 42.dp) {
    Box(Modifier.size(boyut).clip(RoundedCornerShape(14.dp)).background(tokenRenk(ad)), contentAlignment = Alignment.Center) {
        Text(ad.take(1).uppercase(), color = Color(0xFF120A1F), fontWeight = FontWeight.Black, fontSize = 17.sp)
    }
}

private fun nedenMetni(r: String): String {
    val k = r.lowercase()
    return when {
        "zarar" in k || "stop" in k -> "Zarar sınırında kapandı"
        "zaman" in k || "süre" in k -> "Süre doldu (24 saat)"
        "kar al" in k || "kâr al" in k || "hedef" in k -> "Kâr hedefinde kapandı"
        else -> "Trader sattı, biz de sattık"
    }
}

private fun onceMetni(ts: Double): String {
    val sn = (System.currentTimeMillis() / 1000.0 - ts).toInt().coerceAtLeast(0)
    return when { sn < 60 -> "az önce"; sn < 3600 -> "${sn / 60} dk önce"; sn < 86400 -> "${sn / 3600} sa önce"; else -> "${sn / 86400} gün önce" }
}

@Composable
fun KucukKutu(baslik: String, deger: String, renk: Color, modifier: Modifier) {
    Column(modifier.belir().clip(RoundedCornerShape(18.dp)).background(Nx.Yuzey).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(baslik, color = Nx.Soluk, fontSize = 12.sp, maxLines = 1)
        Text(deger, color = renk, fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = Orbitron, maxLines = 1)
    }
}

// ------------------------------------------------------------------ Ana Sayfa

private val ARALIK = listOf("1S" to 3600.0, "1G" to 86400.0, "7G" to 604800.0, "30G" to 2592000.0)

fun LazyListScope.uyeAnaSayfa(v: Veri, gizle: Boolean, gizleDegis: () -> Unit, aralik: String, aralikSec: (String) -> Unit,
                             git: (String) -> Unit, nexoMetni: String?, url: String = "", key: String = "") {
    item(key = "u_ust") {
        Row(Modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Logo(20.sp)
                Text(if (v.kurucu && url.isNotBlank()) "Paper kopya işlem" else "Solana kopya işlem", color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.padding(start = 2.dp))
            }
            Box {
                IconButton({ git("islemler") }, Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2)) {
                    Icon(Icons.Filled.Notifications, "İşlemler", tint = Nx.Metin)
                }
                if (v.islemler.any { it.karar == "KOPYALANDI" && System.currentTimeMillis() / 1000.0 - it.ts < 3600 })
                    Box(Modifier.align(Alignment.TopEnd).padding(top = 11.dp, end = 12.dp).size(8.dp).clip(CircleShape).background(Nx.Pembe))
            }
        }
    }
    val ikili = v.kurucu && url.isNotBlank()     // 5.35.0: kurucu ana sayfası iki paper hesap kutusuyla başlar
    if (!ikili) item(key = "u_bakiye") {
        val simdi = System.currentTimeMillis() / 1000.0
        val eskiVar = v.gecmis.isNotEmpty() && v.gecmis.first().ts <= simdi - 86400
        val ref24 = if (eskiVar) degerAni(v.gecmis, simdi - 86400, v.baslangic) else v.baslangic
        val d24 = if (ref24 > 0) (v.toplam - ref24) / ref24 * 100 else 0.0
        val sure = (ARALIK.firstOrNull { it.first == aralik } ?: ARALIK[1]).second
        val bas = degerAni(v.gecmis, simdi - sure, v.baslangic)
        val pencere = listOf(Nokta2(simdi - sure, bas)) + v.gecmis.filter { it.ts > simdi - sure }
        val dalga by rememberInfiniteTransition(label = "dalga").animateFloat(0f, 1f, infiniteRepeatable(tween(4000, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "d")
        Column(Modifier.fillMaxWidth().belir().neonIsik(Nx.Gok, 28.dp).clip(RoundedCornerShape(28.dp)).background(Nx.Menekse)
            .drawWithContent {
                drawCircle(Color(0xFF8B5CF6), size.width * 0.22f, Offset(size.width * 0.92f, size.height * (0.08f - 0.03f * dalga)))
                drawCircle(Color(0xFF6D28D9), size.width * 0.16f, Offset(size.width * 0.72f, size.height * 1.02f))
                drawContent()
            }.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Solana memecoin · sanal bakiye (paper)", color = Color(0xFFEDE9FE), fontSize = 13.sp, modifier = Modifier.weight(1f))
                IconButton(gizleDegis, Modifier.size(32.dp)) {
                    Icon(if (gizle) Icons.Filled.Lock else Icons.Filled.Search, "Gizle", tint = Color(0xFFEDE9FE), modifier = Modifier.size(18.dp))
                }
            }
            if (gizle) Text("•••••• $", color = Color.White, fontSize = 38.sp, fontWeight = FontWeight.Bold)
            else SayanSayi(v.toplam, { "$" + usd(it) }) { Text(it, color = Color.White, fontSize = 38.sp, fontWeight = FontWeight.Bold) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text((if (d24 >= 0) "▲ %" else "▼ %") + String.format(java.util.Locale("tr"), "%.2f", kotlin.math.abs(d24)) + if (eskiVar) " · 24 saat" else " · başlangıçtan",
                     color = if (d24 >= 0) Nx.UstMetin else Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                     modifier = Modifier.clip(RoundedCornerShape(50)).background(if (d24 >= 0) Nx.Nane else Nx.Kirmizi).padding(horizontal = 10.dp, vertical = 5.dp))
                Text("K/Z " + (if (gizle) "••" else isaretli(v.kz) + "$"), color = Color(0xFFEDE9FE), fontSize = 13.sp,
                     modifier = Modifier.clip(RoundedCornerShape(50)).background(Color(0xFF6D28D9)).padding(horizontal = 10.dp, vertical = 5.dp))
            }
            DegerGrafigi(pencere, bas, Modifier.fillMaxWidth().height(150.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ARALIK.forEach { (ad, _) -> Hap(ad, ad == aralik, Modifier.weight(1f), secRenk = Nx.Gok) { aralikSec(ad) } }
            }
        }
    }
    if (ikili) item(key = "u_paper") { PaperHesaplarKarti(v, url, key, gizle, gizleDegis, git) { MemeDetay(v, gizle, aralik, aralikSec, git) } }
    item(key = "u_nexo") {
        val simdi = System.currentTimeMillis() / 1000.0
        val ref = degerAni(v.gecmis, simdi - 86400, v.baslangic)
        val d24 = if (ref > 0) (v.toplam - ref) / ref * 100 else 0.0
        val (ifade, poz, kural) = nexoDurum(v, d24, v.toplam - ref)
        Row(Modifier.fillMaxWidth().belir().neonIsik(Nx.Nane, 22.dp).clip(RoundedCornerShape(22.dp)).background(Nx.Yuzey)
            .clickable { git("asistan") }.padding(start = 4.dp, end = 14.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Nexo(74.dp, ifade, poz)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("NEXO", color = Nx.Metin, fontWeight = FontWeight.Black, fontFamily = Orbitron, fontSize = 15.sp)
                    if (v.acilDurdurma) Text("  durduruldu", color = Nx.Kirmizi, fontSize = 12.sp)
                    else { NabizNokta(Nx.Nane, 7.dp); Text("çalışıyor", color = Nx.Nane, fontSize = 12.sp) }
                }
                Text(nexoMetni ?: kural, color = Color(0xFFDDD9F0), fontSize = 13.sp, lineHeight = 18.sp, maxLines = 5, overflow = TextOverflow.Ellipsis)
                AiYazi("Bana bir şey sor →", 12.sp, FontWeight.SemiBold)
            }
        }
    }
    if (ikili) item(key = "u_btc") { BtcOngoruKarti(url, key) }   // BTC öngörü (PAPER), /btc yalnızca kurucu
    if (!ikili) item(key = "u_kutu") {
        val kapanan = v.kapananlar
        val bugunBas = Calendar.getInstance().apply { set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0) }.timeInMillis / 1000.0
        val bugunKz = kapanan.filter { it.ts >= bugunBas }.sumOf { it.kz }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            KucukKutu("Açık işlem", "${v.pozisyonlar.size}", Nx.Metin, Modifier.weight(1f))
            KucukKutu("Kazanma", v.basariOrani?.let { "%" + it.toInt() } ?: "—", Nx.Nane, Modifier.weight(1f))
            KucukKutu("Bugün", if (gizle) "••" else isaretli(bugunKz), kzRenk(bugunKz), Modifier.weight(1f))
        }
    }
    if (!ikili) item(key = "u_son_bas") {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Son hareketler", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            TextButton({ git("islemler") }) { Text("Tümü", color = Nx.Gok) }
        }
    }
    val son = v.islemler.filter { it.karar == "KOPYALANDI" }.take(3)
    if (!ikili && son.isEmpty()) item(key = "u_son_bos") { BilgiKutusu("Henüz kopyalanan işlem yok. NEXO uygun bir hamle bekliyor.") }
    if (!ikili) items(son, key = { "us_" + it.ts + it.token + it.yon }) { i -> HareketSatiri(v, i) }
}

@Composable
private fun HareketSatiri(v: Veri, i: Islem) {
    val ad = sembol(v, i.token, i.sembol); val sat = i.yon == "sell"
    Row(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(18.dp)).background(Nx.Yuzey).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        TokenRozet(ad, 40.dp)
        Column(Modifier.weight(1f)) {
            Text("$ad " + if (sat) "satıldı" else "alındı", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1)
            Text(onceMetni(i.ts) + if (sat) " · " + nedenMetni(i.neden) else "", color = Nx.Soluk, fontSize = 12.sp, maxLines = 1)
        }
        if (sat) Text(isaretli(i.kz) + "$", color = kzRenk(i.kz), fontWeight = FontWeight.Bold)
        else Text("Açık", color = Nx.MorAcik, fontWeight = FontWeight.SemiBold)
    }
}

// ------------------------------------------------------------------ Cüzdanlar

@Composable
fun KopyaCuzdanlarEkrani(url: String, key: String) {
    var veri by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    var sekme by remember { mutableIntStateOf(0) }
    LaunchedEffect(url, key) {
        try { veri = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/kopya-ozet", zamanAsimi = 25_000) }); hata = "" }
        catch (e: kotlinx.coroutines.CancellationException) { throw e }
        catch (e: Exception) { hata = if (e.message?.contains("40") == true) "Sunucu güncel değil ya da oturum yok (Profil › Hesabım)." else "Yüklenemedi: ${e.message}" }
    }
    val liste = veri?.optJSONArray("kopyalanan")
    val n = liste?.length() ?: 0
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.belir()) {
            Text("Cüzdanlar", color = Nx.Metin, fontSize = 28.sp, fontWeight = FontWeight.Bold)
            Text("Kopyaladığımız Solana trader'ları. Her biri bir karneyle seçildi.", color = Nx.Soluk, fontSize = 14.sp)
        }
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Nx.Yuzey).padding(5.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Hap("Kopyalanan · $n", sekme == 0, Modifier.weight(1f)) { sekme = 0 }
            Hap("Deneniyor · ${veri?.optInt("deneniyor") ?: 0}", sekme == 1, Modifier.weight(1f)) { sekme = 1 }
        }
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
        if (veri == null && hata.isEmpty()) Row(Modifier.fillMaxWidth().padding(24.dp), horizontalArrangement = Arrangement.Center) { YaziyorNoktalari() }
        if (sekme == 1) {
            BilgiKutusu("Deneniyor: karnesi iyi çıkan yeni trader'lar önce gölgede (sanal olarak bile para koymadan) izlenir. " +
                        "Sonuçları iyiyse kopyalananlara eklenir; kötüyse elenir.")
            val dl = veri?.optJSONArray("deneniyor_liste")
            if (dl != null) for (i in 0 until dl.length()) DeneniyorSatiri(dl.getJSONObject(i), i)
        }
        else if (liste != null) {
            if (n == 0) BilgiKutusu("Şu an kopyalanan trader yok.")
            for (i in 0 until n) TraderKarti(liste.getJSONObject(i), i, veri?.optInt("gun") ?: 30)
            Text("Trader adresleri gizlidir; her trader'a kalıcı bir takma ad verilir.", color = Nx.Soluk, fontSize = 11.sp)
        }
    }
}

@Composable
private fun DeneniyorSatiri(x: JSONObject, sira: Int) {
    val ad = x.optString("ad")
    Row(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(18.dp)).background(Nx.Yuzey).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2).border(1.dp, TOKEN_RENK[sira % TOKEN_RENK.size], RoundedCornerShape(14.dp)),
            contentAlignment = Alignment.Center) { Text(ad.takeLast(2), color = TOKEN_RENK[sira % TOKEN_RENK.size], fontWeight = FontWeight.Black, fontSize = 14.sp) }
        Column(Modifier.weight(1f)) {
            Text(ad, color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            val et = x.optJSONArray("etiketler")
            Text(if (et != null && et.length() > 0) (0 until et.length()).joinToString(" · ") { et.getString(it) } else "Gölgede izleniyor",
                 color = Nx.Soluk, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (!x.isNull("trader_kazanma")) Column(horizontalAlignment = Alignment.End) {
            Text("%" + x.optDouble("trader_kazanma").toInt(), color = Nx.Gok, fontWeight = FontWeight.Bold)
            Text("kendi isabeti", color = Nx.Soluk, fontSize = 11.sp)
        }
    }
}

@Composable
private fun TraderKarti(x: JSONObject, sira: Int, gun: Int) {
    val ad = x.optString("ad"); val kz = x.optDouble("kz", 0.0); val kapanan = x.optInt("kapanan")
    val kazanma = if (x.isNull("bizim_kazanma")) null else x.optDouble("bizim_kazanma")
    val dolum = remember { Animatable(0f) }
    LaunchedEffect(kazanma) { dolum.animateTo(((kazanma ?: 0.0) / 100.0).toFloat(), tween(1200, 300 + sira * 120, FastOutSlowInEasing)) }
    Column(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(22.dp)).background(Nx.Yuzey).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(46.dp).clip(RoundedCornerShape(16.dp)).background(TOKEN_RENK[sira % TOKEN_RENK.size]), contentAlignment = Alignment.Center) {
                Text(ad.takeLast(2), color = Color(0xFF120A1F), fontWeight = FontWeight.Black, fontSize = 16.sp)
            }
            Column(Modifier.weight(1f)) {
                Text(ad, color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                Text("$kapanan kapanan işlem · son $gun gün" + if (x.optInt("acik") > 0) " · ${x.optInt("acik")} açık" else "", color = Nx.Soluk, fontSize = 12.sp)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(isaretli(kz) + "$", color = kzRenk(kz), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text("bizim kârımız", color = Nx.Soluk, fontSize = 11.sp)
            }
        }
        val et = x.optJSONArray("etiketler")
        if (et != null && et.length() > 0) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (j in 0 until et.length()) Text(et.getString(j), color = Nx.MorAcik, fontSize = 12.sp,
                modifier = Modifier.clip(RoundedCornerShape(50)).background(Nx.SeciliZemin).padding(horizontal = 10.dp, vertical = 4.dp))
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row { Text("Bizim kazanma oranımız", color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(1f))
                  Text(kazanma?.let { "%" + it.toInt() } ?: "henüz kapanan yok", color = Nx.Metin, fontSize = 12.sp, fontWeight = FontWeight.SemiBold) }
            Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(50)).background(Nx.Cizgi)) {
                Box(Modifier.fillMaxWidth(dolum.value).fillMaxHeight().clip(RoundedCornerShape(50)).background(Brush.horizontalGradient(listOf(Nx.Gok, Nx.Nane))))
            }
        }
        if (kapanan >= 3 && kz < 0)
            Text("İzlemede: zararı sürerse kopyalanan listesinden çıkar.", color = Color(0xFFFDE68A), fontSize = 12.sp,
                 modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Color(0xFF2A1A12)).padding(horizontal = 10.dp, vertical = 8.dp))
    }
}

// ------------------------------------------------------------------ İşlemler

fun LazyListScope.uyeIslemler(v: Veri, filtre: Int, filtreSec: (Int) -> Unit) {
    item(key = "ui_bas") {
        Column(Modifier.belir()) {
            Text("İşlemler", color = Nx.Metin, fontSize = 28.sp, fontWeight = FontWeight.Bold)
            Text("Bot bir trader'ı kopyaladığında burada görürsün. Hepsi sanal para.", color = Nx.Soluk, fontSize = 14.sp)
        }
    }
    item(key = "ui_filtre") {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Tümü", "Açık · ${v.pozisyonlar.size}", "Kapanan").forEachIndexed { i, ad -> Hap(ad, filtre == i, secRenk = Nx.Metin) { filtreSec(i) } }
        }
    }
    if (filtre != 2) {
        if (v.pozisyonlar.isEmpty() && filtre == 1) item(key = "ui_acik_bos") { BilgiKutusu("Şu an açık işlem yok.") }
        items(v.pozisyonlar, key = { "ui_p_" + it.token }) { p -> AcikIslemKarti(v, p) }
    }
    if (filtre != 1) {
        val kapanan = v.kapananlar
        val gunler = kapanan.groupBy { gunEtiketi(it.ts) }
        if (kapanan.isEmpty()) item(key = "ui_kap_bos") { BilgiKutusu("Henüz kapanan işlem yok.") }
        gunler.forEach { (gun, liste) ->
            item(key = "ui_g_$gun") { Text(gun.uppercase(), color = Color(0xFF8C87AA), fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.6.sp,
                                           modifier = Modifier.padding(top = 4.dp)) }
            items(liste, key = { "ui_k_" + it.ts + it.token }) { i -> HareketSatiri(v, i) }
        }
        val hafta = kapanan.filter { System.currentTimeMillis() / 1000.0 - it.ts < 7 * 86400 }
        if (hafta.isNotEmpty()) item(key = "ui_hafta") {
            val t = hafta.sumOf { it.kz }
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Nx.Yuzey2).padding(horizontal = 16.dp, vertical = 14.dp)) {
                Text("Son 7 günde ${hafta.size} işlem", color = Color(0xFFC9C5E0), modifier = Modifier.weight(1f))
                Text(isaretli(t) + "$", color = kzRenk(t), fontWeight = FontWeight.Bold)
            }
        }
    }
}

private fun gunEtiketi(ts: Double): String {
    val c = Calendar.getInstance(); val bugun = c.get(Calendar.YEAR) * 1000 + c.get(Calendar.DAY_OF_YEAR)
    c.timeInMillis = (ts * 1000).toLong(); val o = c.get(Calendar.YEAR) * 1000 + c.get(Calendar.DAY_OF_YEAR)
    return when (bugun - o) { 0 -> "Bugün"; 1 -> "Dün"; else -> gunAy(ts) }
}

@Composable
private fun AcikIslemKarti(v: Veri, p: Pozisyon) {
    val ad = sembol(v, p.token, p.sembol)
    val pct = if (p.maliyet > 0) (p.deger / p.maliyet - 1) * 100 else 0.0
    val akis by rememberInfiniteTransition(label = "akis").animateFloat(0f, 1f, infiniteRepeatable(tween(1000, easing = LinearEasing)), label = "a")
    val simdi = System.currentTimeMillis() / 1000.0
    val kalan = p.acilis?.let { 86400 - (simdi - it) }
    Column(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(22.dp)).background(Nx.Yuzey).border(1.dp, Color(0xFF3B2F73), RoundedCornerShape(22.dp))
        .padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            TokenRozet(ad)
            Column(Modifier.weight(1f)) {
                Text("$ad · açık", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                Text(p.acilis?.let { "Trader aldı, biz de · " + onceMetni(it) } ?: "Açık", color = Nx.Soluk, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Text((if (pct >= 0) "+%" else "−%") + String.format(java.util.Locale("tr"), "%.1f", kotlin.math.abs(pct)), color = kzRenk(pct),
                 fontWeight = FontWeight.Bold, fontFamily = Orbitron, fontSize = 15.sp)
        }
        Canvas(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(50))) {
            drawRect(Nx.Cizgi)
            val dolu = size.width * (0.5f + (pct / 40.0).toFloat()).coerceIn(0.05f, 1f)
            val s = 20.dp.toPx()
            var x = -2 * s + akis * 2 * s
            while (x < dolu) {
                drawRect(Nx.Lila, Offset(x.coerceAtLeast(0f), 0f), Size((minOf(x + s, dolu) - x.coerceAtLeast(0f)).coerceAtLeast(0f), size.height))
                drawRect(Color(0xFF8B5CF6), Offset((x + s).coerceAtLeast(0f), 0f), Size((minOf(x + 2 * s, dolu) - (x + s).coerceAtLeast(0f)).coerceAtLeast(0f), size.height))
                x += 2 * s
            }
        }
        Row {
            Text("Giriş $" + usd(p.maliyet), color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(1f))
            Text("Şimdi $" + usd(p.deger), color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(1f))
            if (kalan != null) Text(if (kalan > 0) "En geç ${(kalan / 3600).toInt()} sa içinde kapanır" else "Kapanıyor", color = Nx.Soluk, fontSize = 12.sp)
        }
    }
}

// ------------------------------------------------------------------ Profil

fun LazyListScope.uyeProfil(v: Veri, url: String, key: String, git: (String) -> Unit) {
    item(key = "up_bas") { ProfilBasi(url, key, v.kurucu) }
    item(key = "up_paket") {
        Column(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(22.dp)).background(Nx.Yuzey2).padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Paketin", color = Nx.Soluk, fontSize = 13.sp, modifier = Modifier.weight(1f))
                Text("Paper mod", color = Nx.MorAcik, fontSize = 12.sp, modifier = Modifier.clip(RoundedCornerShape(50)).background(Nx.SeciliZemin).padding(horizontal = 10.dp, vertical = 4.dp))
            }
            Text("Ücretsiz", color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.Bold, fontFamily = Orbitron)
            Text("Sistemi sanal parayla izliyorsun. Gerçek para kullanılmıyor.", color = Nx.Soluk, fontSize = 13.sp)
        }
    }
    item(key = "up_nexo") {
        Row(Modifier.fillMaxWidth().belir().neonIsik(Nx.Nane, 22.dp).clip(RoundedCornerShape(22.dp)).background(Color(0xFF0E1F17))
            .clickable { git("asistan") }.padding(start = 4.dp, end = 16.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Nexo(54.dp, NexoIfade.KIRPMA, NexoPoz.SELAM)
            Column(Modifier.weight(1f)) {
                Text("NEXO Asistan", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                Text("Yapay zekâ: sonuçlarını sade dille anlatır", color = Nx.Nane, fontSize = 12.sp)
            }
            Icon(Icons.Filled.KeyboardArrowRight, null, tint = Nx.Nane)
        }
    }
    if (v.kurucu) item(key = "up_yon") {
        val t by rememberInfiniteTransition(label = "yon").animateFloat(0f, 1f, infiniteRepeatable(tween(1200), RepeatMode.Reverse), label = "y")
        Row(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(22.dp)).background(Color(0xFF2A1C06))
            .border(1.dp + 1.dp * t, Nx.Turuncu, RoundedCornerShape(22.dp)).clickable { git("yonetici") }.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Nx.Turuncu), contentAlignment = Alignment.Center) { IkonKalkan(Color(0xFF1A1203), 24.dp) }
            Column(Modifier.weight(1f)) {
                Text("Yönetici paneli", color = Color(0xFFFEF3C7), fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                Text("Yalnızca sana görünür", color = Color(0xFFFCD34D), fontSize = 12.sp)
            }
            Icon(Icons.Filled.KeyboardArrowRight, null, tint = Color(0xFFFDE68A))
        }
    }
    item(key = "up_menu") {
        Column(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(22.dp)).background(Nx.Yuzey)) {
            ProfilMenuSatiri("Hesabım ve güvenlik", "Giriş, iki adımlı doğrulama, parola") { git("uye") }
            Box(Modifier.fillMaxWidth().height(1.dp).background(Nx.Cizgi))
            ProfilMenuSatiri("Ayarlar", "Bildirimler, kilit, görünüm, sunucu") { git("ayarlar") }
        }
    }
    item(key = "up_surum") { Text("Sürüm ${BuildConfig.VERSION_NAME} · sanal para (paper) · gerçek işlem kapalı", color = Nx.Soluk, fontSize = 11.sp) }
}

@Composable
private fun ProfilMenuSatiri(baslik: String, alt: String, tikla: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = tikla).heightIn(min = 56.dp).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(baslik, color = Nx.Metin, fontSize = 15.sp)
            Text(alt, color = Nx.Soluk, fontSize = 12.sp)
        }
        Icon(Icons.Filled.KeyboardArrowRight, null, tint = Color(0xFF8C87AA))
    }
}

@Composable
private fun ProfilBasi(url: String, key: String, kurucu: Boolean) {
    var eposta by remember { mutableStateOf("") }
    LaunchedEffect(Oturum.deger) {
        if (Oturum.deger.isNotEmpty()) try {
            eposta = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/uye/ben", oturum = Oturum.deger) }).optString("eposta")
        } catch (e: kotlinx.coroutines.CancellationException) { throw e } catch (e: Exception) { }
    }
    val ad = if (kurucu) "Kurucu" else "Üye"
    Row(Modifier.fillMaxWidth().belir().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Box(Modifier.size(64.dp).neonIsik(Nx.Gok, 22.dp).clip(RoundedCornerShape(22.dp)).background(Nx.Menekse), contentAlignment = Alignment.Center) {
            Text((eposta.firstOrNull() ?: ad.first()).uppercase(), color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Black, fontFamily = Orbitron)
        }
        Column {
            Text(ad, color = Nx.Metin, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Text(eposta.ifEmpty { if (Oturum.deger.isEmpty()) "Hesap girişi yapılmadı" else "…" }, color = Nx.Soluk, fontSize = 13.sp)
        }
    }
}

// ------------------------------------------------------------------ NEXO Asistan

private data class Mesaj(val ben: Boolean, val metin: String)

@Composable
fun AsistanEkrani(url: String, key: String, geri: () -> Unit) {
    val scope = rememberCoroutineScope()
    val mesajlar = remember { mutableStateListOf<Mesaj>() }
    var bekliyor by remember { mutableStateOf(true) }
    var soru by remember { mutableStateOf("") }
    var kalan by remember { mutableStateOf<Int?>(null) }
    LaunchedEffect(url, key) {
        if (mesajlar.isNotEmpty()) return@LaunchedEffect
        val m = try { JSONObject(withContext(Dispatchers.IO) { api(url, key, "/asistan", zamanAsimi = 60_000) }).optString("metin") }
                catch (e: kotlinx.coroutines.CancellationException) { throw e }
                catch (e: Exception) { if (e.message?.contains("40") == true) "Sunucu güncel değil ya da giriş yapılmadı." else "Şu an sunucuya ulaşamadım." }
        mesajlar.add(Mesaj(false, m)); bekliyor = false
    }
    fun sor(s: String) {
        val q = s.trim(); if (q.isEmpty() || bekliyor) return
        mesajlar.add(Mesaj(true, q)); soru = ""; bekliyor = true
        scope.launch {
            val cevap = try {
                val r = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/uye/asistan", true, JSONObject().put("soru", q).toString(), 60_000) })
                if (r.has("kalan")) kalan = r.optInt("kalan")
                r.optString("metin")
            } catch (e: kotlinx.coroutines.CancellationException) { throw e }
              catch (e: Exception) { "Şu an cevap veremedim: ${e.message}" }
            mesajlar.add(Mesaj(false, cevap)); bekliyor = false
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(geri) { Icon(Icons.Filled.ArrowBack, "Geri", tint = Nx.Metin) }
            Text("NEXO Asistan", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold, fontFamily = Orbitron)
        }
        Column(Modifier.fillMaxWidth().belir(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            val h by rememberInfiniteTransition(label = "hale").animateFloat(0f, 1f, infiniteRepeatable(tween(1300), RepeatMode.Reverse), label = "h")
            Box(Modifier.size(170.dp), contentAlignment = Alignment.Center) {
                Canvas(Modifier.fillMaxSize()) {
                    val r = size.minDimension / 2f
                    drawCircle(Brush.radialGradient(listOf(Nx.Nane.copy(alpha = 0.18f + 0.14f * h), Color.Transparent), center, r), r)
                    drawCircle(Nx.Yuzey, r * 0.86f)
                    drawCircle(Nx.Nane.copy(alpha = 0.6f + 0.4f * h), r * 0.86f, style = Stroke(2.dp.toPx()))
                    drawCircle(Nx.Gok.copy(alpha = 0.25f * h), r * 0.86f, style = Stroke(8.dp.toPx()))
                }
                Nexo(104.dp, if (bekliyor) NexoIfade.DUSUN else NexoIfade.KIRPMA, NexoPoz.SELAM)
            }
            Text("Sonuçlarını sade dille anlatırım. Tavsiye vermem, sadece açıklarım.", color = Nx.Soluk, fontSize = 13.sp)
        }
        mesajlar.forEachIndexed { i, m -> Balon(m, i == 0) }
        if (bekliyor) Row(Modifier.clip(RoundedCornerShape(20.dp)).background(Nx.Yuzey).padding(horizontal = 18.dp, vertical = 14.dp)) { YaziyorNoktalari() }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Bu hafta nasıl gitti?", "Neden zarar ettik?").forEach { q ->
                Text(q, color = Color(0xFFA5FAFF), fontSize = 13.sp, modifier = Modifier.neonIsik(Nx.Gok, 50.dp).clip(RoundedCornerShape(50))
                    .clickable { sor(q) }.padding(horizontal = 14.dp, vertical = 10.dp))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(soru, { soru = it.take(300) }, placeholder = { Text("NEXO'ya sor…") }, singleLine = true,
                shape = RoundedCornerShape(16.dp), modifier = Modifier.weight(1f))
            IconButton({ sor(soru) }, enabled = !bekliyor && soru.isNotBlank(),
                modifier = Modifier.size(52.dp).neonIsik(Nx.Nane, 16.dp).clip(RoundedCornerShape(16.dp)).background(Nx.Nane)) {
                Icon(Icons.Filled.Send, "Gönder", tint = Nx.UstMetin)
            }
        }
        if (kalan != null) Text("Bugün $kalan soru hakkın kaldı.", color = Nx.Soluk, fontSize = 11.sp)
    }
}

@Composable
private fun Balon(m: Mesaj, ozet: Boolean) {
    Row(Modifier.fillMaxWidth().belir(), horizontalArrangement = if (m.ben) Arrangement.End else Arrangement.Start) {
        val sekil = if (m.ben) RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp) else RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp)
        Column(Modifier.widthIn(max = 300.dp).clip(sekil).background(if (m.ben) Nx.Menekse else Nx.Yuzey)
            .then(if (m.ben) Modifier else Modifier.border(1.dp, Color(0xFF1F7A4C), sekil)).padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (ozet && !m.ben) Text("GÜNÜN ÖZETİ", color = Nx.Nane, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            var gorunen by remember(m.metin) { mutableStateOf(if (m.ben) m.metin else "") }
            LaunchedEffect(m.metin) { if (!m.ben) for (i in 1..m.metin.length) { gorunen = m.metin.take(i); kotlinx.coroutines.delay(12) } }
            Text(gorunen, color = if (m.ben) Color.White else Color(0xFFE9E6F7), fontSize = 14.sp, lineHeight = 20.sp)
        }
    }
}

// ------------------------------------------------------------------ Yönetici paneli

fun LazyListScope.yoneticiPaneli(v: Veri, url: String, key: String, git: (String) -> Unit) {
    item(key = "yp_bas") {
        Column(Modifier.belir()) {
            Text("Kontrol paneli", color = Nx.Metin, fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Text("Ölçümler, teşhis, sistem ve bot ayarları. Üyeler bu bölümü görmez.", color = Nx.Soluk, fontSize = 13.sp)
        }
    }
    item(key = "yp_durum") {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f).belir().clip(RoundedCornerShape(20.dp)).background(Color(0xFF111B2E)).padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Bot", color = Color(0xFF94A3B8), fontSize = 12.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (v.acilDurdurma) Text("Durduruldu", color = Nx.Kirmizi, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    else { NabizNokta(Nx.Nane, 7.dp); Text("Çalışıyor", color = Nx.Nane, fontWeight = FontWeight.Bold, fontSize = 18.sp) }
                }
                Text("${v.takipCuzdanlar.count { it.durum == "aktif" }} cüzdan takipte", color = Color(0xFF94A3B8), fontSize = 12.sp)
            }
            Column(Modifier.weight(1f).belir().clip(RoundedCornerShape(20.dp)).background(Color(0xFF111B2E)).padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Gerçek pilot", color = Color(0xFF94A3B8), fontSize = 12.sp)
                Text("Kapalı", color = Color(0xFFFCD34D), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text("Sunucuda: gercek_pilot.py durum", color = Color(0xFF94A3B8), fontSize = 12.sp)
            }
        }
    }
    if (v.bagli) item(key = "yp_tut") { TutarlilikKarti(url, key) }
    item(key = "yp_grid") {
        val araclar = listOf(
            Triple("karne", "Sonuçlar", "Karne ve ölçümler"), Triple("rapor", "Teşhis", "Günlük rapor + YZ"), Triple("sistem", "Sistem", "Servisler"),
            Triple("bot", "Bot ve risk", "Acil durdurma"), Triple("takip", "Cüzdan analizi", "Takip listesi"), Triple("kesfet", "Keşif", "Hyperliquid, token, DNA"),
            Triple("portfoy", "Paper işlem", "Elle al-sat"), Triple("yol", "Aşamalar", "Yol haritası"), Triple("hazir", "Hazırlık", "Gerçek paraya geçiş"))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            araclar.chunked(3).forEach { satir ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    satir.forEach { (id, ad, alt) ->
                        Column(Modifier.weight(1f).belir().tiklaZipla { git(id) }.clip(RoundedCornerShape(18.dp)).background(Color(0xFF111B2E))
                            .border(1.dp, Color(0xFF1E293B), RoundedCornerShape(18.dp)).heightIn(min = 92.dp).padding(10.dp),
                            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp, Alignment.CenterVertically)) {
                            Box(Modifier.size(10.dp).clip(CircleShape).background(Nx.Turuncu))
                            Text(ad, color = Color(0xFFF1F5F9), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                            Text(alt, color = Color(0xFF94A3B8), fontSize = 10.sp, maxLines = 2, lineHeight = 13.sp)
                        }
                    }
                }
            }
        }
    }
    if (v.asamalar.isNotEmpty()) item(key = "yp_asama") {
        Column(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(20.dp)).background(Color(0xFF111B2E)).clickable { git("yol") }.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Süren aşamalar", color = Color(0xFF94A3B8), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            v.asamalar.filter { it.durum == "devam" }.sortedByDescending { it.yuzde }.take(4).forEach { a ->
                val dolum = remember { Animatable(0f) }
                LaunchedEffect(a.yuzde) { dolum.animateTo(a.yuzde / 100f, tween(1100, easing = FastOutSlowInEasing)) }
                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row { Text(a.ad, color = Color(0xFFF1F5F9), fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                          Text("%${a.yuzde}", color = Color(0xFF94A3B8), fontSize = 13.sp) }
                    Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(50)).background(Color(0xFF1E293B))) {
                        Box(Modifier.fillMaxWidth(dolum.value).fillMaxHeight().clip(RoundedCornerShape(50)).background(Nx.Turuncu))
                    }
                }
            }
        }
    }
}


/** 5.35.0 · Ana sayfa Solana memecoin ayrıntısı (eski büyük kartın içeriği): değişim, K/Z, grafik, aralık, kutular, son hareketler. */
@Composable
fun MemeDetay(v: Veri, gizle: Boolean, aralik: String, aralikSec: (String) -> Unit, git: (String) -> Unit) {
    val simdi = System.currentTimeMillis() / 1000.0
    val eskiVar = v.gecmis.isNotEmpty() && v.gecmis.first().ts <= simdi - 86400
    val ref24 = if (eskiVar) degerAni(v.gecmis, simdi - 86400, v.baslangic) else v.baslangic
    val d24 = if (ref24 > 0) (v.toplam - ref24) / ref24 * 100 else 0.0
    val sure = (ARALIK.firstOrNull { it.first == aralik } ?: ARALIK[1]).second
    val bas = degerAni(v.gecmis, simdi - sure, v.baslangic)
    val pencere = listOf(Nokta2(simdi - sure, bas)) + v.gecmis.filter { it.ts > simdi - sure }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text((if (d24 >= 0) "▲ %" else "▼ %") + String.format(java.util.Locale("tr"), "%.2f", kotlin.math.abs(d24)) + if (eskiVar) " · 24 saat" else " · başlangıçtan",
             color = if (d24 >= 0) Nx.UstMetin else Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold,
             modifier = Modifier.clip(RoundedCornerShape(50)).background(if (d24 >= 0) Nx.Nane else Nx.Kirmizi).padding(horizontal = 10.dp, vertical = 5.dp))
        Text("K/Z " + (if (gizle) "••" else isaretli(v.kz) + "$"), color = Color(0xFFEDE9FE), fontSize = 13.sp,
             modifier = Modifier.clip(RoundedCornerShape(50)).background(Color(0xFF6D28D9)).padding(horizontal = 10.dp, vertical = 5.dp))
    }
    DegerGrafigi(pencere, bas, Modifier.fillMaxWidth().height(130.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        ARALIK.forEach { (ad, _) -> Hap(ad, ad == aralik, Modifier.weight(1f), secRenk = Nx.Gok) { aralikSec(ad) } }
    }
    val bugunBas = Calendar.getInstance().apply { set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0) }.timeInMillis / 1000.0
    val bugunKz = v.kapananlar.filter { it.ts >= bugunBas }.sumOf { it.kz }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        MiniKutu("Açık işlem", "${v.pozisyonlar.size}", Nx.Metin, Modifier.weight(1f))
        MiniKutu("Kazanma", v.basariOrani?.let { "%" + it.toInt() } ?: "—", Nx.Nane, Modifier.weight(1f))
        MiniKutu("Bugün", if (gizle) "••" else isaretli(bugunKz), kzRenk(bugunKz), Modifier.weight(1f))
    }
    Text("Son hareketler", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    val son = v.islemler.filter { it.karar == "KOPYALANDI" }.take(3)
    if (son.isEmpty()) Text("Henüz kopyalanan işlem yok. NEXO uygun bir hamle bekliyor.", color = Nx.Soluk, fontSize = 12.sp)
    son.forEach { HareketSatiri(v, it) }
}

@Composable
private fun MiniKutu(baslik: String, deger: String, renk: Color, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2).padding(horizontal = 10.dp, vertical = 8.dp)) {
        Text(baslik, color = Nx.Soluk, fontSize = 11.sp, maxLines = 1)
        Text(deger, color = renk, fontSize = 17.sp, fontWeight = FontWeight.Bold, fontFamily = Orbitron, maxLines = 1)
    }
}
