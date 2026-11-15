package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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

object Nx {
    val Zemin = Color(0xFF080917)
    val Yuzey = Color(0xFF111329)
    val Yuzey2 = Color(0xFF181B38)
    val Cizgi = Color(0xFF2A2E5A)
    val Mor = Color(0xFFA855F7)
    val Pembe = Color(0xFFEC4899)
    val Camgobegi = Color(0xFF22D3EE)
    val Yesil = Color(0xFF22C55E)
    val Kirmizi = Color(0xFFF43F5E)
    val Sari = Color(0xFFF59E0B)
    val Metin = Color(0xFFE8EAFF)
    val Soluk = Color(0xFF8B90B8)
    val Kenar = Brush.linearGradient(listOf(Mor, Pembe, Camgobegi))
    val KenarYesil = Brush.linearGradient(listOf(Camgobegi, Yesil))
    val DolguMor = Brush.linearGradient(listOf(Color(0x33A855F7), Color(0x1122D3EE)))
}

val NxRenkler = darkColorScheme(
    primary = Nx.Mor, secondary = Nx.Camgobegi, tertiary = Nx.Pembe,
    background = Nx.Zemin, surface = Nx.Yuzey, surfaceVariant = Nx.Yuzey2,
    onPrimary = Color.White, onSecondary = Color.Black, onBackground = Nx.Metin, onSurface = Nx.Metin,
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
    val sekil = RoundedCornerShape(20.dp)
    Column(
        modifier
            .clip(sekil)
            .background(dolgu ?: Brush.linearGradient(listOf(Nx.Yuzey, Nx.Yuzey)))
            .border(1.dp, kenar, sekil)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        content = icerik,
    )
}

/** Sade kart (ince kenar). */
@Composable
fun Kart(modifier: Modifier = Modifier, icerik: @Composable ColumnScope.() -> Unit) {
    val sekil = RoundedCornerShape(16.dp)
    Column(
        modifier.clip(sekil).background(Nx.Yuzey).border(1.dp, Nx.Cizgi, sekil).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
        content = icerik,
    )
}

@Composable
fun Etiket(metin: String, renk: Color) {
    Box(
        Modifier.clip(RoundedCornerShape(50)).background(renk.copy(alpha = 0.16f))
            .border(1.dp, renk.copy(alpha = 0.6f), RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 3.dp)
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
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(
            Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(Nx.Kenar),
            contentAlignment = Alignment.Center
        ) { Text("N", color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Black) }
        Column {
            Text(buildAnnotatedString {
                withStyle(SpanStyle(color = Nx.Mor)) { append("NEX") }
                withStyle(SpanStyle(color = Nx.Camgobegi)) { append("ORA") }
            }, fontSize = 24.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            Text("SOLANA KOPYALAMA ARAŞTIRMASI", color = Nx.Soluk, fontSize = 10.sp, letterSpacing = 1.5.sp)
        }
    }
}

@Composable
fun Nokta(renk: Color) { Box(Modifier.size(8.dp).clip(CircleShape).background(renk)) }
