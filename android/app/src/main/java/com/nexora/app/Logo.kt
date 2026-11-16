package com.nexora.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.graphicsLayer
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Orbitron (SIL Open Font License) — derleme sırasında Google Fonts deposundan indirilir. */
val Orbitron = FontFamily(
    Font(R.font.orbitron_black, FontWeight.Black),
    Font(R.font.orbitron_bold, FontWeight.Bold),
    Font(R.font.orbitron_bold, FontWeight.SemiBold),
)

/** N amblemi: sinir ağı düğümleriyle çizilmiş N; nane→gök→lila→pembe geçişi. ilerleme<1 ise çizgi baştan o orana kadar çizilir. */
@Composable
fun Amblem(boyut: Dp, modifier: Modifier = Modifier, ilerleme: Float = 1f) {
    Canvas(modifier.size(boyut)) {
        val k = size.width / 100f
        fun p(x: Float, y: Float) = Offset(x * k, y * k)
        val tam = Path().apply { moveTo(22f * k, 84f * k); lineTo(22f * k, 16f * k); lineTo(78f * k, 84f * k); lineTo(78f * k, 16f * k) }
        val yol = if (ilerleme >= 1f) tam else Path().also { hedef ->
            val olcu = androidx.compose.ui.graphics.PathMeasure(); olcu.setPath(tam, false)
            olcu.getSegment(0f, olcu.length * ilerleme.coerceIn(0f, 1f), hedef, true)
        }
        val firca = Brush.linearGradient(Nx.AiRenkler, start = p(10f, 10f), end = p(90f, 90f))
        drawPath(yol, firca, alpha = 0.22f, style = Stroke(width = 26f * k, cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawPath(yol, firca, style = Stroke(width = 15f * k, cap = StrokeCap.Round, join = StrokeJoin.Round))
        val dugumler = listOf(p(22f, 84f) to 0f, p(22f, 16f) to 0.28f, p(50f, 50f) to 0.5f, p(78f, 84f) to 0.72f, p(78f, 16f) to 1f)
        for ((o, esik) in dugumler) if (ilerleme >= esik) {
            val orta = o == dugumler[2].first
            drawCircle(Nx.Zemin, (if (orta) 4f else 5f) * k, o)
            drawCircle(Color.White, (if (orta) 1.8f else 2.4f) * k, o)
        }
    }
}

/** Kılıç darbesi biçiminde, ateş kızılı X: iki sivri uçlu bıçak, ortası akkor, kenarları koyu kızıl. */
@Composable
fun AtesX(genislik: Dp, yukseklik: Dp, modifier: Modifier = Modifier) {
    Canvas(modifier.size(genislik, yukseklik)) {
        bicak(Offset(size.width * 0.06f, size.height * 0.02f), Offset(size.width * 0.96f, size.height * 0.98f), 0.16f, 0.42f)
        bicak(Offset(size.width * 0.92f, size.height * 0.0f), Offset(size.width * 0.04f, size.height * 1.0f), 0.14f, 0.58f)
    }
}

private fun DrawScope.bicak(a: Offset, b: Offset, kalinlik: Float, darbe: Float) {
    val d = b - a
    val uz = kotlin.math.sqrt(d.x * d.x + d.y * d.y)
    val n = Offset(-d.y / uz, d.x / uz)
    val W = size.width * kalinlik
    val yol = Path().apply {
        moveTo(a.x, a.y)
        val u = a + d * darbe + n * W
        lineTo(u.x, u.y)
        lineTo(b.x, b.y)
        val l = a + d * (darbe + 0.12f) - n * (W * 0.55f)
        lineTo(l.x, l.y)
        close()
    }
    val ates = Brush.linearGradient(
        0f to Color(0xFF5A0000), 0.22f to Color(0xFFC40000), 0.42f to Color(0xFFFF4D00),
        0.52f to Color(0xFFFFD27A), 0.62f to Color(0xFFFF4D00), 0.82f to Color(0xFFC40000), 1f to Color(0xFF5A0000),
        start = a, end = b)
    drawPath(yol, Color(0xFFFF1A00), alpha = 0.16f, style = Stroke(width = W * 2.6f, join = StrokeJoin.Round))
    drawPath(yol, Color(0xFFFF3D00), alpha = 0.32f, style = Stroke(width = W * 1.3f, join = StrokeJoin.Round))
    drawPath(yol, ates)
    val c0 = a + d * 0.22f; val c1 = a + d * 0.8f
    drawLine(Color(0xFFFFF1C2).copy(alpha = 0.8f), c0, c1, strokeWidth = W * 0.12f, cap = StrokeCap.Round)
}

/** NEXORA yazısı: N harfi amblemin kendisi, X ateş kızılı kılıç darbesi. altYazi=true ise altında yapay zekâ sloganı. */
@Composable
fun NexoraYazi(boy: TextUnit = 30.sp, altYazi: Boolean = true, modifier: Modifier = Modifier, amblemliN: Boolean = true) {
    val yogunluk = LocalDensity.current
    val harf = TextStyle(fontFamily = Orbitron, fontWeight = FontWeight.Black, fontSize = boy, color = Nx.Metin,
                         letterSpacing = (boy.value * 0.06f).sp)
    val xYuk = with(yogunluk) { (boy * 1.12f).toDp() }
    val xGen = with(yogunluk) { (boy * 1.18f).toDp() }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (amblemliN) {
                Amblem(with(yogunluk) { (boy * 1.22f).toDp() }, Modifier.padding(end = with(yogunluk) { (boy * 0.10f).toDp() }))
                Text("E", style = harf)
            } else Text("NE", style = harf)
            AtesX(xGen, xYuk, Modifier.padding(horizontal = with(yogunluk) { (boy * 0.04f).toDp() }))
            Text("ORA", style = harf)
        }
        if (altYazi) AiYazi("YAPAY ZEKÂ DESTEKLİ KOPYA TİCARET", boy * 0.3f, FontWeight.Bold)
    }
}

/** Logo: sinir ağı N amblemi + E + ateş X + ORA + akan "AI" rozeti. */
@Composable
fun Logo(boy: TextUnit = 22.sp) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        NexoraYazi(boy, altYazi = false)
        AiRozet("AI", boy * 0.5f)
    }
}

/** Açılış: amblem çizilir, yazı belirir, X kılıç darbesi gibi iner, Nexo selam verir. ~1,9 sn sonra bitti() çağrılır. */
@Composable
fun AcilisEkrani(bitti: () -> Unit) {
    val cizim = remember { Animatable(0f) }
    val yazi = remember { Animatable(0f) }
    val nexo = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        launch { nexo.animateTo(1f, spring(dampingRatio = 0.5f, stiffness = 180f)) }
        cizim.animateTo(1f, tween(700, easing = FastOutSlowInEasing))
        yazi.animateTo(1f, tween(450, easing = FastOutSlowInEasing))
        delay(750)
        bitti()
    }
    Box(Modifier.fillMaxSize()) {
        AiArkaplan()
        Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(18.dp, Alignment.CenterVertically)) {
            Nexo(150.dp, NexoIfade.KIRPMA, NexoPoz.SELAM, Modifier.graphicsLayer { scaleX = nexo.value; scaleY = nexo.value; alpha = nexo.value.coerceIn(0f, 1f) })
            Row(verticalAlignment = Alignment.CenterVertically) {
                Amblem(46.dp, Modifier.padding(end = 4.dp), ilerleme = cizim.value)
                val harf = TextStyle(fontFamily = Orbitron, fontWeight = FontWeight.Black, fontSize = 36.sp, color = Nx.Metin, letterSpacing = 2.sp)
                Text("E", style = harf, modifier = Modifier.graphicsLayer { alpha = yazi.value })
                AtesX(42.dp, 40.dp, Modifier.padding(horizontal = 2.dp).graphicsLayer {
                    val o = 3f - 2f * yazi.value; scaleX = o; scaleY = o; alpha = yazi.value; rotationZ = -40f * (1f - yazi.value) })
                Text("ORA", style = harf, modifier = Modifier.graphicsLayer { alpha = yazi.value })
            }
            Box(Modifier.graphicsLayer { alpha = yazi.value; translationY = 20f * (1f - yazi.value) }) {
                AiYazi("YAPAY ZEKÂ DESTEKLİ KOPYA TİCARET", 12.sp, FontWeight.Bold)
            }
        }
    }
}
