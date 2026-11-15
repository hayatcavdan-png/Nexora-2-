package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Sakin tema (3.9): koyu lacivert zemin, turkuaz vurgu, yumuşak lavanta; neon kenar ve parlak degrade yok. */
object Nx {
    val Zemin = Color(0xFF0A0E17)
    val Yuzey = Color(0xFF151D30)
    val Yuzey2 = Color(0xFF1C2540)
    val Cizgi = Color(0xFF243049)
    val Mor = Color(0xFFB4A0F0)          // lavanta (vurgu 2)
    val Pembe = Color(0xFFF49AC1)
    val Camgobegi = Color(0xFF2DD4BF)    // turkuaz (ana vurgu)
    val Yesil = Color(0xFF4ADE80)
    val Limon = Color(0xFFA3E635)
    val Kirmizi = Color(0xFFF7768E)
    val Sari = Color(0xFFF5C26B)
    val Metin = Color(0xFFF1F5F9)
    val Soluk = Color(0xFF94A3B8)
    val Kahraman = Color(0xFF1E1D3F)     // öne çıkan kart (mor-lacivert)
    val SeciliZemin = Color(0xFF123B3A)  // alt menüde seçili sekme
    val Kenar = Brush.linearGradient(listOf(Cizgi, Cizgi))
    val KenarYesil = Brush.linearGradient(listOf(Color(0xFF1F4D4A), Color(0xFF1F4D4A)))
    val DolguMor = Brush.linearGradient(listOf(Kahraman, Kahraman))
}

val NxRenkler = darkColorScheme(
    primary = Nx.Mor, secondary = Nx.Camgobegi, tertiary = Nx.Pembe,
    background = Nx.Zemin, surface = Nx.Yuzey, surfaceVariant = Nx.Yuzey2,
    onPrimary = Color(0xFF0B1220), onSecondary = Color(0xFF0B1220), onBackground = Nx.Metin, onSurface = Nx.Metin,
    onSurfaceVariant = Nx.Soluk, error = Nx.Kirmizi, outline = Nx.Cizgi,
)

fun kisa(a: String): String = if (a.length > 10) a.take(4) + "…" + a.takeLast(4) else a
fun saat(ts: Double): String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date((ts * 1000).toLong()))
fun gunAy(ts: Double): String = SimpleDateFormat("d MMM", Locale("tr")).format(Date((ts * 1000).toLong()))
fun usd(x: Double): String = String.format(Locale.US, "%.2f", x)
fun isaretli(x: Double): String = (if (x >= 0) "+" else "") + usd(x)
fun yuzde(x: Double, ondalik: Int = 1): String = "%" + String.format(Locale.US, "%.${ondalik}f", x)
fun kzRenk(x: Double): Color = if (x > 0.004) Nx.Yesil else if (x < -0.004) Nx.Kirmizi else Nx.Soluk

/** Neon kenarlı kart. */
@Composable
fun NeonKart(modifier: Modifier = Modifier, kenar: Brush = Nx.Kenar, dolgu: Brush? = null, icerik: @Composable ColumnScope.() -> Unit) {
    val sekil = RoundedCornerShape(24.dp)
    Column(
        modifier
            .clip(sekil)
            .background(dolgu ?: Brush.linearGradient(listOf(Nx.Yuzey, Nx.Yuzey)))
            .border(1.dp, kenar, sekil)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = icerik,
    )
}

/** Sade kart (ince kenar). */
@Composable
fun Kart(modifier: Modifier = Modifier, icerik: @Composable ColumnScope.() -> Unit) {
    val sekil = RoundedCornerShape(20.dp)
    Column(
        modifier.clip(sekil).background(Nx.Yuzey).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        content = icerik,
    )
}

@Composable
fun Etiket(metin: String, renk: Color) {
    Box(
        Modifier.clip(RoundedCornerShape(50)).background(renk.copy(alpha = 0.14f))
            .padding(horizontal = 10.dp, vertical = 4.dp)
    ) { Text(metin, color = renk, fontSize = 12.sp, fontWeight = FontWeight.Medium) }
}

fun kararRengi(karar: String): Color = when {
    karar.startsWith("KOPYALANDI") || karar == "kopyalanabilir" || karar == "aktif" || karar == "ileri" -> Nx.Yesil
    karar.startsWith("REDDED") || karar == "zararda" || karar == "bot" || karar == "bot şüphesi" -> Nx.Kirmizi
    karar == "karantina" || karar == "zayıf" || karar == "devam" -> Nx.Sari
    else -> Nx.Soluk
}

@Composable
fun Baslik(metin: String, alt: String? = null) {
    Column {
        Text(metin, color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
        if (alt != null) Text(alt, color = Nx.Soluk, fontSize = 13.sp)
    }
}

@Composable
fun Satir(sol: String, sag: String, sagRenk: Color = Nx.Metin) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text(sol, color = Nx.Soluk, fontSize = 14.sp, modifier = Modifier.weight(1f))
        Text(sag, color = sagRenk, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun Logo() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            Modifier.size(46.dp).clip(RoundedCornerShape(14.dp)).background(Color(0xFF123B3A))
                .border(1.dp, Nx.Camgobegi.copy(alpha = 0.35f), RoundedCornerShape(14.dp)),
            contentAlignment = Alignment.Center
        ) { Text("N", color = Nx.Camgobegi, fontSize = 24.sp, fontWeight = FontWeight.Bold) }
        Column {
            Text("NEXORA", color = Nx.Metin, fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Text("COMMAND X / SOLANA", color = Nx.Camgobegi, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.5.sp)
        }
    }
}

/** Birincil düğme: beyaz hap, koyu yazı (yorucu olmayan yüksek kontrast). */
@Composable
fun NxButonRenk() = ButtonDefaults.buttonColors(containerColor = Color(0xFFF1F5F9), contentColor = Color(0xFF0B1220))

/** Logo + iki yuvarlak ikon düğmesi. */
@Composable
fun UstBaslik(ikon1: androidx.compose.ui.graphics.vector.ImageVector, eylem1: () -> Unit,
              ikon2: androidx.compose.ui.graphics.vector.ImageVector, eylem2: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) { Logo() }
        for ((ikon, eylem) in listOf(ikon1 to eylem1, ikon2 to eylem2)) {
            Box(Modifier.padding(start = 8.dp).size(44.dp).clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2)
                .clickable { eylem() }, contentAlignment = Alignment.Center) {
                Icon(ikon, null, tint = Nx.Mor, modifier = Modifier.size(22.dp))
            }
        }
    }
}

/** Durum şeridi: PAPER modu ve gerçek emrin kapalı olduğu her ekranda görünür. */
@Composable
fun DurumSeridi(sol: String, solRenk: Color, sag: String) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(14.dp).clip(CircleShape).border(2.dp, solRenk, CircleShape), contentAlignment = Alignment.Center) {
                Box(Modifier.size(6.dp).clip(CircleShape).background(solRenk))
            }
            Text(sol, color = solRenk, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp).weight(1f))
            Text(sag, color = Nx.Soluk, fontSize = 13.sp)
        }
        Box(Modifier.fillMaxWidth().height(2.dp).clip(RoundedCornerShape(1.dp)).background(Nx.Camgobegi))
    }
}

/** Alt menü: yuvarlak karolar; seçili olan turkuaz zeminli. */
@Composable
fun AltMenu(sekmeler: List<Triple<String, String, androidx.compose.ui.graphics.vector.ImageVector>>, secili: String, sec: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().background(Nx.Zemin).padding(horizontal = 12.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        sekmeler.forEach { (id, ad, ikon) ->
            val s = id == secili
            Column(Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(if (s) Nx.SeciliZemin else Nx.Yuzey.copy(alpha = 0.6f))
                .clickable { sec(id) }.padding(vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Icon(ikon, ad, tint = if (s) Nx.Camgobegi else Nx.Soluk, modifier = Modifier.size(22.dp))
                Text(ad, color = if (s) Nx.Camgobegi else Nx.Soluk, fontSize = 11.sp, maxLines = 1)
            }
        }
    }
}

@Composable
fun Nokta(renk: Color) { Box(Modifier.size(8.dp).clip(CircleShape).background(renk)) }
