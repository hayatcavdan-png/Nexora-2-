package com.nexora.app

import androidx.compose.animation.core.*
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.composed
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.Dp
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

/** NEXORA AI teması: mürekkep laciverti zemin, nane yeşili ana renk, yapay zekâ öğelerinde nane→gök→lila→pembe geçişi.
 *  (Mor/Camgobegi adları eski koddan kalma takma adlardır: Mor = nane, Camgobegi = gök mavisi.) */
object Nx {
    val Zemin = Color(0xFF05080F)
    val Yuzey = Color(0xFF0C1524)
    val Yuzey2 = Color(0xFF13203A)
    val Cizgi = Color(0xFF1E3050)
    val Nane = Color(0xFF2DF5C0)
    val Gok = Color(0xFF4FB8FF)
    val Lila = Color(0xFF9B7BFF)
    val Kehribar = Color(0xFFFFC24D)
    val Mor = Nane
    val MorKoyu = Color(0xFF1FD9A8)
    val MorAcik = Color(0xFF8CFFE0)
    val Pembe = Color(0xFFFF5CA8)
    val Camgobegi = Gok
    val Mavi = Color(0xFF3B82F6)
    val Yesil = Color(0xFF2DF5C0)
    val Limon = Color(0xFF8CFFE0)
    val Kirmizi = Color(0xFFFF4D5E)
    val Sari = Kehribar
    val Metin = Color(0xFFF4F8FF)
    val Soluk = Color(0xFF8FA3C8)
    val UstMetin = Color(0xFF03130E)          // nane zemin üstündeki koyu yazı
    val Kahraman = Color(0xFF0E1E33)
    val SeciliZemin = Color(0xFF10303A)
    val AiRenkler = listOf(Nane, Gok, Lila, Pembe)
    val Kenar = Brush.linearGradient(listOf(Color(0xFF1E3A55), Color(0xFF16283F)))
    val KenarParlak = Brush.linearGradient(AiRenkler)
    val KenarYesil = Brush.linearGradient(listOf(Color(0xFF1F7A62), Color(0xFF1B5E52)))
    val DolguMor = Brush.linearGradient(listOf(Color(0xFF0F1D33), Color(0xFF0A1322)))
}

val NxRenkler = darkColorScheme(
    primary = Nx.Mor, secondary = Nx.Camgobegi, tertiary = Nx.Pembe,
    background = Nx.Zemin, surface = Nx.Yuzey, surfaceVariant = Nx.Yuzey2,
    onPrimary = Nx.UstMetin, onSecondary = Nx.UstMetin, onBackground = Nx.Metin, onSurface = Nx.Metin,
    onSurfaceVariant = Nx.Soluk, error = Nx.Kirmizi, outline = Nx.Cizgi,
)

fun kisa(a: String): String = if (a.length > 10) a.take(4) + "…" + a.takeLast(4) else a
fun saat(ts: Double): String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date((ts * 1000).toLong()))
fun gunAy(ts: Double): String = SimpleDateFormat("d MMM", Locale("tr")).format(Date((ts * 1000).toLong()))
fun usd(x: Double): String = String.format(Locale.US, "%.2f", x)
fun isaretli(x: Double): String = (if (x >= 0) "+" else "") + usd(x)
fun yuzde(x: Double, ondalik: Int = 1): String = "%" + String.format(Locale.US, "%.${ondalik}f", x)
fun kzRenk(x: Double): Color = if (x > 0.004) Nx.Yesil else if (x < -0.004) Nx.Kirmizi else Nx.Soluk

/** Kart ilk göründüğünde yumuşakça yükselerek belirir (yalnızca çizim katmanı: yeniden düzen hesaplanmaz). */
fun Modifier.belir(): Modifier = composed {
    val a = remember { Animatable(0f) }
    LaunchedEffect(Unit) { a.animateTo(1f, tween(420, easing = FastOutSlowInEasing)) }
    graphicsLayer { alpha = a.value; translationY = (1f - a.value) * 36f; val s = 0.97f + 0.03f * a.value; scaleX = s; scaleY = s }
}

/** Basınca hafifçe küçülen, bırakınca yaylanan tıklama. */
fun Modifier.tiklaZipla(etkin: Boolean = true, tikla: () -> Unit): Modifier = composed {
    val kaynak = remember { MutableInteractionSource() }
    val basili by kaynak.collectIsPressedAsState()
    val o by animateFloatAsState(if (basili) 0.93f else 1f, spring(dampingRatio = 0.45f, stiffness = 500f), label = "zipla")
    graphicsLayer { scaleX = o; scaleY = o }.clickable(kaynak, LocalIndication.current, enabled = etkin, onClick = tikla)
}

/** Yapay zekâ kenarı: nane→gök→lila→pembe geçişi kenar boyunca sürekli akar (yalnızca çizim aşamasında canlanır). */
fun Modifier.aiKenar(kose: Dp, kalinlik: Dp = 1.5.dp): Modifier = composed {
    val t = rememberInfiniteTransition(label = "aiKenar").animateFloat(0f, 1f, infiniteRepeatable(tween(5000, easing = LinearEasing)), label = "k")
    drawWithContent {
        drawContent()
        val k = t.value * size.width * 2f
        val f = Brush.linearGradient(Nx.AiRenkler + Nx.AiRenkler.first(), Offset(k, 0f), Offset(k + size.width, size.height), TileMode.Repeated)
        val w = kalinlik.toPx()
        drawRoundRect(f, Offset(w / 2, w / 2), Size(size.width - w, size.height - w), CornerRadius(kose.toPx()), style = Stroke(w))
    }
}

/** Neon kenarlı kart. Parlak (yapay zekâ) kenar verilirse kenar akar. */
@Composable
fun NeonKart(modifier: Modifier = Modifier, kenar: Brush = Nx.Kenar, dolgu: Brush? = null, icerik: @Composable ColumnScope.() -> Unit) {
    val sekil = RoundedCornerShape(24.dp)
    val parlak = kenar === Nx.KenarParlak
    Column(
        modifier
            .belir()
            .clip(sekil)
            .background(dolgu ?: Brush.linearGradient(listOf(Nx.Yuzey, Nx.Yuzey)))
            .then(if (parlak) Modifier.aiKenar(24.dp) else Modifier.border(1.dp, kenar, sekil))
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
        modifier.belir().clip(sekil).background(Nx.Yuzey.copy(alpha = 0.92f)).border(1.dp, Nx.Cizgi, sekil).padding(16.dp),
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
fun NxButonRenk() = ButtonDefaults.buttonColors(containerColor = Nx.Nane, contentColor = Nx.UstMetin)

@Composable
fun NxYesilButon() = ButtonDefaults.buttonColors(containerColor = Nx.Nane, contentColor = Nx.UstMetin)

@Composable
fun NxGriButon() = ButtonDefaults.buttonColors(containerColor = Color(0xFF1A2740), contentColor = Nx.Metin)

@Composable
fun Nokta(renk: Color) { Box(Modifier.size(8.dp).clip(CircleShape).background(renk)) }
