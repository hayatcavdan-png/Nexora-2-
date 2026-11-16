package com.nexora.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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

private val AmblemRenk = listOf(Color(0xFFC4A8FF), Color(0xFF8B5CF6), Color(0xFF5B5BF6), Color(0xFF3B82F6), Color(0xFF22D3EE))

/** N amblemi: öne eğik, keskin kenarlı, mor→mavi→turkuaz degrade, hafif parıltı. */
@Composable
fun Amblem(boyut: Dp, modifier: Modifier = Modifier) {
    Canvas(modifier.size(boyut)) {
        val w = size.width; val h = size.height
        fun p(x: Float, y: Float) = Offset(x * w / 100f, y * h / 100f)
        val yol = Path().apply {
            moveTo(p(6f, 94f).x, p(6f, 94f).y)
            listOf(p(24f, 6f), p(42f, 6f), p(63.5f, 62f), p(73f, 6f), p(94f, 6f), p(76f, 94f), p(58f, 94f), p(36.5f, 38f), p(27f, 94f))
                .forEach { lineTo(it.x, it.y) }
            close()
        }
        val firca = Brush.linearGradient(AmblemRenk, start = p(0f, 0f), end = p(100f, 100f))
        drawPath(yol, firca, alpha = 0.22f, style = Stroke(width = w * 0.14f, join = StrokeJoin.Round))
        drawPath(yol, firca, alpha = 0.35f, style = Stroke(width = w * 0.06f, join = StrokeJoin.Round))
        drawPath(yol, firca)
        drawPath(yol, Color.White.copy(alpha = 0.45f), style = Stroke(width = w * 0.012f, join = StrokeJoin.Miter))
    }
}

/** Kılıç darbesi biçiminde, ateş kızılı X: iki sivri uçlu bıçak, ortası akkor, kenarları koyu kızıl. */
@Composable
fun AtesX(genislik: Dp, yukseklik: Dp, modifier: Modifier = Modifier) {
    Canvas(modifier.size(genislik, yukseklik)) {
        bicak(Offset(size.width * 0.06f, size.height * 0.02f), Offset(size.width * 0.96f, size.height * 0.98f), 0.135f, 0.42f)
        bicak(Offset(size.width * 0.92f, size.height * 0.0f), Offset(size.width * 0.04f, size.height * 1.0f), 0.115f, 0.58f)
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
    drawPath(yol, Color(0xFFFF2A00), alpha = 0.28f, style = Stroke(width = W * 1.4f, join = StrokeJoin.Round))
    drawPath(yol, ates)
    val c0 = a + d * 0.22f; val c1 = a + d * 0.8f
    drawLine(Color(0xFFFFF1C2).copy(alpha = 0.8f), c0, c1, strokeWidth = W * 0.12f, cap = StrokeCap.Round)
}

/** NEXORA yazısı (X ateş kızılı) ve altında COMMAND X. */
@Composable
fun NexoraYazi(boy: TextUnit = 30.sp, altYazi: Boolean = true, modifier: Modifier = Modifier) {
    val yogunluk = LocalDensity.current
    val harf = TextStyle(fontFamily = Orbitron, fontWeight = FontWeight.Black, fontSize = boy, color = Color.White,
                         letterSpacing = (boy.value * 0.06f).sp)
    val xYuk = with(yogunluk) { (boy * 0.78f).toDp() }
    val xGen = with(yogunluk) { (boy * 0.86f).toDp() }
    Column(modifier, horizontalAlignment = Alignment.Start) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("NE", style = harf)
            AtesX(xGen, xYuk, Modifier.padding(horizontal = with(yogunluk) { (boy * 0.04f).toDp() }))
            Text("ORA", style = harf)
        }
        if (altYazi) Row(verticalAlignment = Alignment.CenterVertically) {
            Text("COMMAND", style = TextStyle(fontFamily = Orbitron, fontWeight = FontWeight.Bold, fontSize = boy * 0.36f,
                letterSpacing = (boy.value * 0.22f).sp,
                brush = Brush.linearGradient(listOf(Color(0xFF22D3EE), Color(0xFF3B82F6), Color(0xFF8B5CF6)))))
            Text("X", style = TextStyle(fontFamily = Orbitron, fontWeight = FontWeight.Black, fontSize = boy * 0.56f,
                fontStyle = FontStyle.Italic, brush = Brush.linearGradient(listOf(Color(0xFF6D5BFF), Color(0xFFB45CFF), Color(0xFF8B5CF6)))))
        }
    }
}

/** Küçük başlık logosu: amblem + yazı. */
@Composable
fun Logo(boy: TextUnit = 22.sp) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Amblem(with(LocalDensity.current) { (boy * 1.7f).toDp() })
        NexoraYazi(boy)
    }
}
