package com.nexora.app

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

/**
 * NEXO: NEXORA'nın yapay zekâ robotu. Nane yeşili gövde, dağınık lacivert saç, kehribar LED gözler, göğsünde ateş X.
 * Kollar yerine havada süzülen eller: her pozda ayrı hareket eder. Tamamı kodla çizilir (görsel dosya yok).
 * Kafa 200×200, tüm beden 200×270 birimlik ızgarada çizilir ve istenen boyuta ölçeklenir.
 */
enum class NexoIfade { GULUS, KIRPMA, MERAK, ODAK, YILDIZ, SEVINC, ENDISE, UYKU, DUSUN, HAVALI }
enum class NexoPoz { KAVUS, SELAM, SEVINC, SERBEST }

private val GOVDE = listOf(Color(0xFF7DFFE0), Color(0xFF22E3B0), Color(0xFF0C9C86))
private val SAC = listOf(Color(0xFF6A78C4), Color(0xFF2C3570), Color(0xFF171C40))
private val GOZ = listOf(Color(0xFFFFE9B8), Color(0xFFFFB13D), Color(0xFFB45A12))
private val ATES = listOf(Color(0xFFFFD27A), Color(0xFFFF4D00), Color(0xFFC40000))
private val LED = Color(0xFFFFC24D)
private val EKRAN_KOYU = Color(0xFF0B1326)
private val YUVARLAK_GOZLU = setOf(NexoIfade.GULUS, NexoIfade.MERAK, NexoIfade.ENDISE, NexoIfade.DUSUN, NexoIfade.ODAK)

private fun yol(ciz: Path.() -> Unit) = Path().apply(ciz)

private fun yildizYolu(cx: Float, cy: Float, r: Float, kol: Int, ic: Float): Path = yol {
    for (i in 0 until kol * 2) {
        val rr = if (i % 2 == 0) r else r * ic
        val a = PI / kol * i - PI / 2
        val x = cx + rr * cos(a).toFloat(); val y = cy + rr * sin(a).toFloat()
        if (i == 0) moveTo(x, y) else lineTo(x, y)
    }
    close()
}

private fun DrawScope.led(p: Path, w: Float = 5f) = drawPath(p, LED, style = Stroke(w, cap = StrokeCap.Round, join = StrokeJoin.Round))

private fun DrawScope.yuvarlakGoz(cx: Float, cy: Float, r: Float = 13f, dx: Float = 0f, dy: Float = 0f) {
    drawCircle(Brush.radialGradient(GOZ, Offset(cx - r * 0.16f, cy - r * 0.28f), r * 1.4f), r, Offset(cx, cy))
    drawCircle(Color.White, r * 0.3f, Offset(cx - r * 0.32f + dx, cy - r * 0.36f + dy))
    drawCircle(Color.White.copy(alpha = 0.7f), r * 0.13f, Offset(cx + r * 0.36f + dx, cy + r * 0.4f + dy))
}

private fun DrawScope.nexoYuzCiz(ifade: NexoIfade, kapali: Boolean) {
    val l = 76f; val r = 124f; val y = 104f
    val kirpik = kapali && ifade in YUVARLAK_GOZLU
    fun kapaliGoz(cx: Float) = led(yol { moveTo(cx - 12f, y + 1f); quadraticBezierTo(cx, y + 9f, cx + 12f, y + 1f) })
    val dolgunAgiz = yol { moveTo(82f, 123f); quadraticBezierTo(100f, 148f, 119f, 123f); close() }
    when (ifade) {
        NexoIfade.GULUS -> {
            if (kirpik) { kapaliGoz(l); kapaliGoz(r) } else { yuvarlakGoz(l, y); yuvarlakGoz(r, y) }
            led(yol { moveTo(84f, 128f); quadraticBezierTo(100f, 140f, 118f, 125f) })
            drawLine(LED, Offset(118f, 125f), Offset(122f, 121f), 4f, StrokeCap.Round)
        }
        NexoIfade.KIRPMA -> {
            yuvarlakGoz(l, y)
            led(yol { moveTo(r - 12f, y + 3f); quadraticBezierTo(r, y - 11f, r + 12f, y + 3f) })
            drawPath(dolgunAgiz, LED)
        }
        NexoIfade.MERAK -> {
            if (kirpik) { kapaliGoz(l); kapaliGoz(r) } else { yuvarlakGoz(l, y - 2f, 16f); yuvarlakGoz(r, y + 1f, 10f) }
            led(yol { moveTo(l - 14f, y - 24f); quadraticBezierTo(l, y - 32f, l + 14f, y - 26f) }, 4f)
            drawOval(LED, Offset(96f, 125f), Size(12f, 14f), style = Stroke(4f))
        }
        NexoIfade.ODAK -> {
            for (cx in listOf(l, r)) {
                yuvarlakGoz(cx, y + 2f)
                drawRect(EKRAN_KOYU, Offset(cx - 16f, y - 14f), Size(32f, 13f))
            }
            led(yol { moveTo(l - 15f, y - 3f); lineTo(l + 15f, y + 1f) })
            led(yol { moveTo(r - 15f, y + 1f); lineTo(r + 15f, y - 3f) })
            led(yol { moveTo(86f, 130f); quadraticBezierTo(102f, 134f, 116f, 126f) })
        }
        NexoIfade.YILDIZ -> {
            drawPath(yildizYolu(l, y, 15f, 5, 0.45f), LED); drawPath(yildizYolu(r, y, 15f, 5, 0.45f), LED)
            drawPath(dolgunAgiz, LED)
        }
        NexoIfade.SEVINC -> {
            for (cx in listOf(l, r)) led(yol { moveTo(cx - 13f, y + 4f); quadraticBezierTo(cx, y - 12f, cx + 13f, y + 4f) })
            drawPath(yol { moveTo(80f, 122f); quadraticBezierTo(100f, 152f, 120f, 122f); close() }, LED)
        }
        NexoIfade.ENDISE -> {
            if (kirpik) { kapaliGoz(l); kapaliGoz(r) } else { yuvarlakGoz(l, y + 2f, 12f); yuvarlakGoz(r, y + 2f, 12f) }
            led(yol { moveTo(l - 13f, y - 15f); lineTo(l + 10f, y - 22f) }, 4f)
            led(yol { moveTo(r + 13f, y - 15f); lineTo(r - 10f, y - 22f) }, 4f)
            led(yol { moveTo(86f, 134f); quadraticBezierTo(94f, 126f, 100f, 132f); quadraticBezierTo(106f, 138f, 114f, 130f) })
        }
        NexoIfade.UYKU -> {
            kapaliGoz(l); kapaliGoz(r)
            drawCircle(LED, 5f, Offset(100f, 131f), style = Stroke(4f))
        }
        NexoIfade.DUSUN -> {
            if (kirpik) { kapaliGoz(l); kapaliGoz(r) } else { yuvarlakGoz(l, y, 13f, 3f, -3f); yuvarlakGoz(r, y, 13f, 3f, -3f) }
            led(yol { moveTo(90f, 131f); lineTo(112f, 128f) })
        }
        NexoIfade.HAVALI -> {
            val gozluk = yol {
                moveTo(52f, 92f); lineTo(148f, 92f); lineTo(148f, 104f); quadraticBezierTo(148f, 120f, 132f, 120f); lineTo(118f, 120f)
                quadraticBezierTo(106f, 120f, 103f, 108f); lineTo(97f, 108f); quadraticBezierTo(94f, 120f, 82f, 120f); lineTo(68f, 120f)
                quadraticBezierTo(52f, 120f, 52f, 104f); close()
            }
            drawPath(gozluk, Brush.linearGradient(Nx.AiRenkler, Offset(52f, 92f), Offset(148f, 120f)))
            drawLine(Color.White.copy(alpha = 0.6f), Offset(60f, 98f), Offset(78f, 98f), 3f, StrokeCap.Round)
            drawLine(Color.White.copy(alpha = 0.6f), Offset(110f, 98f), Offset(128f, 98f), 3f, StrokeCap.Round)
            led(yol { moveTo(84f, 132f); quadraticBezierTo(100f, 142f, 118f, 128f) })
        }
    }
    if (ifade != NexoIfade.HAVALI) {
        val yanak = Color(0xFFFF7AA8).copy(alpha = if (ifade == NexoIfade.SEVINC || ifade == NexoIfade.YILDIZ) 0.7f else 0.45f)
        drawOval(yanak, Offset(50f, 119.5f), Size(16f, 9f)); drawOval(yanak, Offset(134f, 119.5f), Size(16f, 9f))
    }
}

/** Kafa (200×200 ızgara). nabiz 0..1: kulak ışıkları ve kıvılcım; kivilcim=false ise yapay zekâ kıvılcımı çizilmez. */
private fun DrawScope.nexoKafaCiz(ifade: NexoIfade, kapali: Boolean, nabiz: Float, kivilcim: Boolean) {
    val govde = Brush.linearGradient(GOVDE, Offset(32f, 48f), Offset(168f, 172f))
    for (cx in listOf(30f, 170f)) {
        drawCircle(Brush.linearGradient(GOVDE, Offset(cx - 13f, 97f), Offset(cx + 13f, 123f)), 13f, Offset(cx, 110f))
        drawCircle(LED.copy(alpha = 0.5f + 0.5f * nabiz), 5.5f, Offset(cx, 110f))
    }
    drawRoundRect(govde, Offset(32f, 48f), Size(136f, 124f), CornerRadius(50f))
    drawPath(yol { moveTo(48f, 70f); quadraticBezierTo(60f, 54f, 84f, 52f) }, Color.White.copy(alpha = 0.55f), style = Stroke(5f, cap = StrokeCap.Round))
    drawRoundRect(Brush.verticalGradient(listOf(Color(0xFF101B33), Color(0xFF060B18)), 74f, 156f), Offset(46f, 74f), Size(108f, 82f), CornerRadius(34f))
    drawRoundRect(Color(0xFF0A6F60), Offset(46f, 74f), Size(108f, 82f), CornerRadius(34f), style = Stroke(2f))
    nexoYuzCiz(ifade, kapali)
    val sac = yol {
        moveTo(34f, 86f); quadraticBezierTo(24f, 44f, 62f, 30f); quadraticBezierTo(70f, 16f, 96f, 22f); quadraticBezierTo(112f, 8f, 134f, 20f)
        quadraticBezierTo(160f, 20f, 168f, 46f); quadraticBezierTo(178f, 62f, 168f, 84f); quadraticBezierTo(164f, 66f, 150f, 62f)
        quadraticBezierTo(152f, 74f, 142f, 80f); quadraticBezierTo(138f, 64f, 122f, 60f); quadraticBezierTo(124f, 72f, 112f, 76f)
        quadraticBezierTo(108f, 62f, 92f, 60f); quadraticBezierTo(92f, 72f, 78f, 76f); quadraticBezierTo(76f, 66f, 64f, 66f)
        quadraticBezierTo(50f, 70f, 34f, 86f); close()
    }
    drawPath(sac, Brush.linearGradient(SAC, Offset(30f, 10f), Offset(170f, 86f)))
    drawPath(sac, Color(0xFF8C9DF0).copy(alpha = 0.7f), style = Stroke(1.6f))
    val tel = Stroke(3f, cap = StrokeCap.Round)
    drawPath(yol { moveTo(50f, 52f); quadraticBezierTo(62f, 34f, 86f, 32f) }, Color(0xFFB4C0FF).copy(alpha = 0.75f), style = tel)
    drawPath(yol { moveTo(100f, 30f); quadraticBezierTo(122f, 24f, 142f, 36f) }, Color(0xFFB4C0FF).copy(alpha = 0.75f), style = tel)
    if (kivilcim) {
        val ai = Brush.linearGradient(Nx.AiRenkler, Offset(146f, 8f), Offset(186f, 50f))
        rotate(40f * nabiz - 20f, pivot = Offset(160f, 22f)) { drawPath(yildizYolu(160f, 22f, 9f + 5f * nabiz, 4, 0.38f), ai) }
        drawPath(yildizYolu(178f, 44f, 3f + 3f * (1f - nabiz), 4, 0.38f), ai)
    }
}

private fun DrawScope.el(x: Float, y: Float) {
    drawCircle(Brush.linearGradient(GOVDE, Offset(x - 13f, y - 13f), Offset(x + 13f, y + 13f)), 13f, Offset(x, y))
    drawCircle(Color.White.copy(alpha = 0.45f), 4f, Offset(x - 3f, y - 4f))
}

/** Gövde ve eller (200×270 ızgara). f: 0..2π döngü açısı. */
private fun DrawScope.nexoGovdeCiz(poz: NexoPoz, f: Float) {
    drawOval(Nx.Nane.copy(alpha = 0.14f + 0.08f * (0.5f + 0.5f * sin(f))), Offset(44f, 248f), Size(112f, 16f))
    drawRoundRect(Color(0xFF0A6F60), Offset(88f, 166f), Size(24f, 16f), CornerRadius(5f))
    val g = yol {
        moveTo(62f, 196f); quadraticBezierTo(62f, 178f, 80f, 176f); lineTo(120f, 176f); quadraticBezierTo(138f, 178f, 138f, 196f)
        lineTo(132f, 232f); quadraticBezierTo(130f, 244f, 118f, 244f); lineTo(82f, 244f); quadraticBezierTo(70f, 244f, 68f, 232f); close()
    }
    drawPath(g, Brush.linearGradient(GOVDE, Offset(62f, 176f), Offset(138f, 244f)))
    drawCircle(LED.copy(alpha = 0.25f + 0.2f * (0.5f + 0.5f * sin(f * 2))), 17f, Offset(100f, 206f))
    drawCircle(Color(0xFF071022), 13f, Offset(100f, 206f)); drawCircle(LED, 13f, Offset(100f, 206f), style = Stroke(2f))
    val x = Brush.linearGradient(ATES, Offset(94f, 200f), Offset(106f, 212f))
    drawLine(x, Offset(94f, 200f), Offset(106f, 212f), 4f, StrokeCap.Round); drawLine(x, Offset(106f, 200f), Offset(94f, 212f), 4f, StrokeCap.Round)
    val s = sin(f * 2)
    when (poz) {
        NexoPoz.KAVUS -> { el(82f, 228f + 1.5f * s); el(118f, 226f - 1.5f * s) }
        NexoPoz.SELAM -> { el(44f, 214f + 2f * s); rotate(18f * sin(f * 4), pivot = Offset(140f, 196f)) { el(166f, 168f) } }
        NexoPoz.SEVINC -> { val z = 12f * abs(sin(f * 3)); el(34f, 172f - z); el(166f, 172f - z) }
        NexoPoz.SERBEST -> { el(44f, 214f + 3f * s); el(156f, 214f - 3f * s) }
    }
}

/** Tam beden, canlı Nexo: süzülür, göz kırpar, elleri oynar, kıvılcımı döner; ifadeye göre ek efektler. */
@Composable
fun Nexo(boyut: Dp, ifade: NexoIfade = NexoIfade.GULUS, poz: NexoPoz = NexoPoz.KAVUS, modifier: Modifier = Modifier) {
    val t = rememberInfiniteTransition(label = "nexo").animateFloat(0f, 1f, infiniteRepeatable(tween(4000, easing = LinearEasing)), label = "t")
    var kapali by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { while (true) { delay(2200L + (0..2800).random()); kapali = true; delay(130); kapali = false } }
    Canvas(modifier.size(boyut, boyut * 1.35f)) {
        val o = size.width / 200f
        val f = (t.value * 2 * PI).toFloat()
        val nabiz = 0.5f + 0.5f * sin(f * 2)
        val ziplama = if (poz == NexoPoz.SEVINC) -8f * abs(sin(f * 3)) else 0f
        withTransform({ scale(o, o, pivot = Offset.Zero); translate(0f, (if (ifade == NexoIfade.UYKU) 5f else -5f * sin(f)) + ziplama) }) {
            nexoGovdeCiz(poz, f)
            nexoKafaCiz(ifade, kapali, nabiz, kivilcim = ifade != NexoIfade.UYKU)
            when (ifade) {
                NexoIfade.UYKU -> for (i in 0..1) {
                    val k = (t.value * 2f + i * 0.5f) % 1f
                    val px = 160f + 22f * k; val py = 40f - 34f * k; val b = 8f + 8f * k
                    drawPath(yol { moveTo(px, py); lineTo(px + b, py); lineTo(px, py + b); lineTo(px + b, py + b) },
                        Nx.Gok.copy(alpha = 1f - k), style = Stroke(3f, cap = StrokeCap.Round, join = StrokeJoin.Round))
                }
                NexoIfade.SEVINC, NexoIfade.YILDIZ -> for ((i, c) in listOf(Nx.Kehribar, Nx.Pembe, Nx.Gok, Nx.Nane).withIndex()) {
                    val k = (t.value * 3f + i * 0.25f) % 1f
                    val a = i * 1.7f + 0.4f
                    drawPath(yildizYolu(100f + cos(a) * (60f + 60f * k), 90f + sin(a) * (40f + 50f * k) - 30f * k, 6f * (1f - k) + 2f, 4, 0.4f), c.copy(alpha = 1f - k))
                }
                NexoIfade.DUSUN -> for (i in 0..2) drawCircle(Nx.Gok.copy(alpha = if (((t.value * 12).toInt() % 3) == i) 1f else 0.3f), 4f, Offset(150f + i * 13f, 18f - i * 6f))
                NexoIfade.ENDISE -> {
                    val k = (t.value * 2f) % 1f
                    drawPath(yol { moveTo(160f, 66f + 16f * k); quadraticBezierTo(153f, 78f + 16f * k, 160f, 82f + 16f * k); quadraticBezierTo(167f, 78f + 16f * k, 160f, 66f + 16f * k) },
                        Nx.Gok.copy(alpha = 1f - k))
                }
                else -> {}
            }
        }
    }
}

/** Yalnızca kafa: düğme, sekme ve başlıklar için hafif (animasyonsuz) sürüm. Her yerde farklı bir ifade kullanılır. */
@Composable
fun NexoYuz(boyut: Dp, ifade: NexoIfade, modifier: Modifier = Modifier) {
    Canvas(modifier.size(boyut)) {
        val o = size.width / 200f
        withTransform({ scale(o, o, pivot = Offset.Zero); translate(0f, 10f) }) { nexoKafaCiz(ifade, false, 0.7f, kivilcim = false) }
    }
}

/** Akan yapay zekâ geçişli yazı (nane→gök→lila→pembe). */
@Composable
fun AiYazi(metin: String, boy: TextUnit = 12.sp, agirlik: FontWeight = FontWeight.Bold, modifier: Modifier = Modifier) {
    val t by rememberInfiniteTransition(label = "aiYazi").animateFloat(0f, 400f, infiniteRepeatable(tween(3200, easing = LinearEasing)), label = "k")
    Text(metin, modifier, style = TextStyle(fontSize = boy, fontWeight = agirlik, letterSpacing = 1.sp,
        brush = Brush.linearGradient(Nx.AiRenkler + Nx.AiRenkler.first(), Offset(t, 0f), Offset(t + 200f, 0f), TileMode.Repeated)))
}

/** "AI" rozeti: akan kenarlı hap. */
@Composable
fun AiRozet(metin: String = "AI", boy: TextUnit = 11.sp) {
    Box(Modifier.clip(RoundedCornerShape(50)).background(Nx.Zemin.copy(alpha = 0.6f)).aiKenar(50.dp, 1.2.dp).padding(horizontal = 8.dp, vertical = 2.dp)) {
        AiYazi(metin, boy, FontWeight.Black)
    }
}

/** Maskot + konuşma balonu. Balonun başında "NEXO AI" rozeti; metin harf harf yazılır. */
@Composable
fun NexoKonusuyor(metin: String, ifade: NexoIfade, modifier: Modifier = Modifier, boyut: Dp = 96.dp, poz: NexoPoz = NexoPoz.KAVUS) {
    var gorunen by remember(metin) { mutableStateOf("") }
    LaunchedEffect(metin) { for (i in 1..metin.length) { gorunen = metin.take(i); delay(16) } }
    val sekil = RoundedCornerShape(topStart = 6.dp, topEnd = 20.dp, bottomEnd = 20.dp, bottomStart = 20.dp)
    Row(modifier.belir(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Nexo(boyut, ifade, poz)
        Column(Modifier.weight(1f).clip(sekil).background(Brush.linearGradient(listOf(Color(0xFF12243C), Color(0xFF0B1626))))
            .aiKenar(20.dp, 1.2.dp).padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AiYazi("NEXO AI", 11.sp, FontWeight.Black)
                if (gorunen.length < metin.length) YaziyorNoktalari()
            }
            Box {
                Text(metin, color = Color.Transparent, fontSize = 14.sp, lineHeight = 19.sp)     // yer tutucu: balon zıplamasın
                Text(gorunen, color = Nx.Metin, fontSize = 14.sp, lineHeight = 19.sp, fontWeight = FontWeight.Medium)
            }
        }
    }
}

/** Yapay zekâ "düşünüyor" noktaları. */
@Composable
fun YaziyorNoktalari() {
    val t by rememberInfiniteTransition(label = "nokta").animateFloat(0f, 3f, infiniteRepeatable(tween(900, easing = LinearEasing)), label = "n")
    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        for (i in 0..2) Box(Modifier.size(5.dp).clip(RoundedCornerShape(50)).background(Nx.Nane.copy(alpha = if (t.toInt() == i) 1f else 0.3f)))
    }
}

/** Sayı değişince yumuşakça sayarak geçer. */
@Composable
fun SayanSayi(deger: Double, bicim: (Double) -> String, content: @Composable (String) -> Unit) {
    val a by animateFloatAsState(deger.toFloat(), tween(900, easing = FastOutSlowInEasing), label = "say")
    content(bicim(a.toDouble()))
}
