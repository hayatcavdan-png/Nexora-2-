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

/** COMMAND X teması: gece moru zemin, mor/turkuaz vurgu, mor kenarlı kartlar. */
object Nx {
    val Zemin = Color(0xFF07061A)
    val Yuzey = Color(0xFF12112C)
    val Yuzey2 = Color(0xFF1B1940)
    val Cizgi = Color(0xFF2C2860)
    val Mor = Color(0xFF8B5CF6)
    val MorKoyu = Color(0xFF7C3AED)
    val MorAcik = Color(0xFFB79CFF)
    val Pembe = Color(0xFFEC4899)
    val Camgobegi = Color(0xFF22D3EE)
    val Mavi = Color(0xFF3B82F6)
    val Yesil = Color(0xFF22C55E)
    val Limon = Color(0xFF4ADE80)
    val Kirmizi = Color(0xFFEF4444)
    val Sari = Color(0xFFF59E0B)
    val Metin = Color(0xFFF5F3FF)
    val Soluk = Color(0xFF9EA1C9)
    val Kahraman = Color(0xFF1B1546)
    val SeciliZemin = Color(0xFF2A1F63)
    val Kenar = Brush.linearGradient(listOf(Color(0xFF4C3AA8), Color(0xFF2E2A6E)))
    val KenarParlak = Brush.linearGradient(listOf(Color(0xFF8B5CF6), Color(0xFF3B82F6), Color(0xFF22D3EE)))
    val KenarYesil = Brush.linearGradient(listOf(Color(0xFF1F7A52), Color(0xFF1B5E52)))
    val DolguMor = Brush.linearGradient(listOf(Color(0xFF1E1650), Color(0xFF14123A)))
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
        modifier.clip(sekil).background(Nx.Yuzey).border(1.dp, Nx.Cizgi, sekil).padding(16.dp),
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

/** Birincil düğme: beyaz hap, koyu yazı (yorucu olmayan yüksek kontrast). */
@Composable
fun NxButonRenk() = ButtonDefaults.buttonColors(containerColor = Nx.MorKoyu, contentColor = Color.White)

@Composable
fun NxYesilButon() = ButtonDefaults.buttonColors(containerColor = Nx.Yesil, contentColor = Color.White)

@Composable
fun NxGriButon() = ButtonDefaults.buttonColors(containerColor = Color(0xFF26243F), contentColor = Nx.Metin)

@Composable
fun Nokta(renk: Color) { Box(Modifier.size(8.dp).clip(CircleShape).background(renk)) }
