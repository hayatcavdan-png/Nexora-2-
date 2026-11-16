package com.nexora.app

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/**
 * NEXO: NEXORA'nın robot maskotu. Dağınık koyu saç plakaları, sıcak kahverengi LED gözler, muzip yan gülüş ve
 * çapraz kollar. Tasarım 400×480'lik bir ızgarada çizilir, verilen boyuta ölçeklenir. Hepsi kodla çizilir (görsel dosya yok).
 */
enum class NexoHal { MUTLU, HEYECAN, ENDISE, UYKU, DUSUNUYOR }

private val KABUK = listOf(Color(0xFFFFFFFF), Color(0xFFE6E3F5), Color(0xFFA9A3C9))
private val SAC = listOf(Color(0xFF3A3352), Color(0xFF1E1A2E), Color(0xFF2D2545))
private val GOZ = listOf(Color(0xFFFFD9A0), Color(0xFFE0913A), Color(0xFF7A3E12), Color(0xFF3B1D08))
private val ATES = listOf(Color(0xFFFFB020), Color(0xFFEF4444), Color(0xFF991B1B))

@Composable
fun Nexo(boyut: Dp, hal: NexoHal = NexoHal.MUTLU, selam: Boolean = false, modifier: Modifier = Modifier) {
    val sonsuz = rememberInfiniteTransition(label = "nexo")
    val suzulme by sonsuz.animateFloat(0f, 1f, infiniteRepeatable(tween(2600, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "suz")
    val nabiz by sonsuz.animateFloat(0f, 1f, infiniteRepeatable(tween(1400, easing = LinearEasing), RepeatMode.Reverse), label = "nabiz")
    val el by sonsuz.animateFloat(-1f, 1f, infiniteRepeatable(tween(420, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "el")
    val zz by sonsuz.animateFloat(0f, 1f, infiniteRepeatable(tween(2200, easing = LinearEasing)), label = "zz")
    var kirp by remember { mutableStateOf(1f) }            // 1 = açık göz, 0 = kapalı
    var bakis by remember { mutableStateOf(0f) }
    LaunchedEffect(hal) {
        while (true) {
            delay(2400L + (0..2600).random())
            if (hal != NexoHal.UYKU) {
                for (i in 0..4) { kirp = 1f - i / 4f; delay(16) }
                for (i in 0..4) { kirp = i / 4f; delay(16) }
                if ((0..2).random() == 0) bakis = listOf(-1f, 0f, 1f).random()
            }
        }
    }
    Canvas(modifier.size(boyut, boyut * 1.2f)) {
        val o = size.width / 400f
        withTransform({ scale(o, o, pivot = Offset.Zero); translate(0f, if (hal == NexoHal.UYKU) 6f else -8f * suzulme) }) {
            nexoCiz(hal, nabiz, kirp, bakis, if (selam) el else null, zz)
        }
    }
}

private fun DrawScope.nexoCiz(hal: NexoHal, nabiz: Float, kirp: Float, bakis: Float, el: Float?, zz: Float) {
    // zemin gölgesi
    drawOval(Nx.Mor.copy(alpha = 0.18f + 0.1f * nabiz), Offset(95f, 440f), Size(210f, 26f))
    // gövde
    val govde = Path().apply {
        moveTo(120f, 330f); quadraticBezierTo(120f, 300f, 150f, 296f); lineTo(250f, 296f); quadraticBezierTo(280f, 300f, 280f, 330f)
        lineTo(272f, 420f); quadraticBezierTo(268f, 440f, 248f, 440f); lineTo(152f, 440f); quadraticBezierTo(132f, 440f, 128f, 420f); close()
    }
    drawPath(govde, Brush.verticalGradient(listOf(Color(0xFFF4F2FB), Color(0xFFB8B2D6)), 296f, 440f))
    drawPath(govde, Nx.Mor, style = Stroke(2f))
    // çekirdek (X)
    drawCircle(Brush.radialGradient(listOf(Color.White, Color(0xFFC4B5FD), Color(0x007C3AED)), Offset(200f, 328f), 30f + 8f * nabiz),
        30f + 8f * nabiz, Offset(200f, 328f))
    drawCircle(Color(0xFF0E0B26), 17f, Offset(200f, 328f))
    drawCircle(Nx.Camgobegi, 17f, Offset(200f, 328f), style = Stroke(2f))
    val x = Brush.linearGradient(ATES, Offset(192f, 320f), Offset(208f, 336f))
    drawLine(x, Offset(192f, 320f), Offset(208f, 336f), 5f, StrokeCap.Round)
    drawLine(x, Offset(208f, 320f), Offset(192f, 336f), 5f, StrokeCap.Round)
    // kollar
    if (el == null) {
        kol(Path().apply { moveTo(128f, 330f); quadraticBezierTo(102f, 372f, 150f, 404f); lineTo(250f, 394f) }, Color(0xFFD9D5EE))
        kol(Path().apply { moveTo(272f, 330f); quadraticBezierTo(298f, 372f, 250f, 404f); lineTo(150f, 394f) }, Color(0xFFE9E6F7))
        drawCircle(Nx.Mor, 15f, Offset(252f, 394f)); drawCircle(Nx.MorKoyu, 15f, Offset(148f, 404f))
    } else {
        kol(Path().apply { moveTo(128f, 330f); quadraticBezierTo(108f, 380f, 140f, 410f) }, Color(0xFFD9D5EE))
        drawCircle(Nx.MorKoyu, 15f, Offset(140f, 410f))
        rotate(18f * el, pivot = Offset(276f, 322f)) {          // el sallama
            kol(Path().apply { moveTo(276f, 322f); quadraticBezierTo(318f, 300f, 318f, 252f) }, Color(0xFFE9E6F7))
            drawCircle(Nx.Mor, 17f, Offset(318f, 246f))
        }
    }
    // boyun, kulaklar
    drawRoundRect(Color(0xFF5B5478), Offset(180f, 272f), Size(40f, 28f), CornerRadius(8f))
    for (cx in listOf(86f, 314f)) {
        drawCircle(Brush.radialGradient(KABUK, Offset(cx - 8f, 172f), 34f), 26f, Offset(cx, 182f))
        drawCircle(Nx.Mor, 26f, Offset(cx, 182f), style = Stroke(3f))
        drawCircle(Nx.Camgobegi.copy(alpha = 0.55f + 0.45f * nabiz), 11f, Offset(cx, 182f))
    }
    // kafa
    drawRoundRect(Brush.radialGradient(KABUK, Offset(170f, 140f), 220f), Offset(88f, 78f), Size(224f, 204f), CornerRadius(92f))
    drawRoundRect(Nx.Mor, Offset(88f, 78f), Size(224f, 204f), CornerRadius(92f), style = Stroke(3f))
    // saç: hacimli tepe, öne taranmış perçem, kısa yanlar
    val sac = Path().apply {
        moveTo(92f, 168f); quadraticBezierTo(78f, 104f, 120f, 70f); quadraticBezierTo(150f, 40f, 196f, 42f)
        quadraticBezierTo(236f, 30f, 272f, 52f); quadraticBezierTo(318f, 74f, 314f, 132f); quadraticBezierTo(312f, 154f, 306f, 170f)
        quadraticBezierTo(300f, 140f, 286f, 128f); quadraticBezierTo(292f, 148f, 280f, 156f); quadraticBezierTo(276f, 132f, 258f, 122f)
        quadraticBezierTo(262f, 142f, 246f, 146f); quadraticBezierTo(240f, 124f, 222f, 118f); quadraticBezierTo(222f, 138f, 204f, 140f)
        quadraticBezierTo(200f, 120f, 184f, 116f); quadraticBezierTo(180f, 136f, 160f, 138f); quadraticBezierTo(160f, 120f, 146f, 118f)
        quadraticBezierTo(134f, 138f, 116f, 142f); quadraticBezierTo(104f, 150f, 92f, 168f); close()
    }
    drawPath(sac, Brush.linearGradient(SAC, Offset(90f, 40f), Offset(310f, 170f)))
    val tel = Stroke(3f, cap = StrokeCap.Round)
    drawPath(Path().apply { moveTo(104f, 98f); quadraticBezierTo(118f, 62f, 168f, 52f) }, Nx.Mor.copy(alpha = 0.55f), style = tel)
    drawPath(Path().apply { moveTo(150f, 88f); quadraticBezierTo(180f, 64f, 226f, 66f) }, Nx.Mor.copy(alpha = 0.55f), style = tel)
    drawPath(Path().apply { moveTo(220f, 50f); quadraticBezierTo(262f, 50f, 290f, 80f) }, Nx.Mor.copy(alpha = 0.55f), style = tel)
    drawPath(Path().apply { moveTo(128f, 84f); quadraticBezierTo(150f, 66f, 182f, 64f) }, Color.White.copy(alpha = 0.25f), style = Stroke(4f, cap = StrokeCap.Round))
    // vizör
    drawRoundRect(Brush.verticalGradient(listOf(Color(0xFF1B1640), Color(0xFF0A0820)), 128f, 246f), Offset(114f, 128f), Size(172f, 118f), CornerRadius(54f))
    drawRoundRect(Nx.Camgobegi.copy(alpha = 0.6f), Offset(114f, 128f), Size(172f, 118f), CornerRadius(54f), style = Stroke(2f))
    yuz(hal, kirp, bakis, nabiz)
    if (hal == NexoHal.UYKU) {                                  // Zz
        for (i in 0..1) {
            val t = (zz + i * 0.5f) % 1f
            val px = 300f + 30f * t; val py = 120f - 70f * t
            val a = (1f - t).coerceIn(0f, 1f)
            val s = 14f + 10f * t
            val z = Path().apply { moveTo(px, py); lineTo(px + s, py); lineTo(px, py + s); lineTo(px + s, py + s) }
            drawPath(z, Nx.MorAcik.copy(alpha = a), style = Stroke(4f, cap = StrokeCap.Round, join = StrokeJoin.Round))
        }
    }
    if (hal == NexoHal.HEYECAN) {                               // kıvılcımlar
        for ((cx, cy, r) in listOf(Triple(70f, 110f, 9f), Triple(336f, 96f, 11f), Triple(352f, 236f, 7f))) {
            val k = r * (0.6f + 0.6f * nabiz)
            drawLine(Nx.Sari, Offset(cx - k, cy), Offset(cx + k, cy), 3f, StrokeCap.Round)
            drawLine(Nx.Sari, Offset(cx, cy - k), Offset(cx, cy + k), 3f, StrokeCap.Round)
        }
    }
    if (hal == NexoHal.DUSUNUYOR) {
        for (i in 0..2) drawCircle(Nx.Camgobegi.copy(alpha = if (((nabiz * 3).toInt()) == i) 1f else 0.35f), 6f, Offset(312f + i * 18f, 96f - i * 10f))
    }
}

private fun DrawScope.kol(p: Path, renk: Color) = drawPath(p, renk, style = Stroke(26f, cap = StrokeCap.Round))

private fun DrawScope.yuz(hal: NexoHal, kirp: Float, bakis: Float, nabiz: Float) {
    val camg = Nx.Camgobegi
    val kas = Color(0xFFC4B5FD)
    val gozY = if (hal == NexoHal.DUSUNUYOR) 176f else 184f
    val dx = if (hal == NexoHal.DUSUNUYOR) 6f else 7f * bakis
    if (hal == NexoHal.UYKU) {
        for (cx in listOf(164f, 236f)) drawPath(Path().apply { moveTo(cx - 20f, 186f); quadraticBezierTo(cx, 200f, cx + 20f, 186f) }, kas, style = Stroke(5f, cap = StrokeCap.Round))
        drawCircle(camg.copy(alpha = 0.8f), 7f, Offset(204f, 224f), style = Stroke(4f))
        return
    }
    // kaşlar (endişede içe eğik)
    val egim = if (hal == NexoHal.ENDISE) 8f else 0f
    drawPath(Path().apply { moveTo(140f, 160f - egim); quadraticBezierTo(164f, 148f, 188f, 160f + egim) }, kas, style = Stroke(3f, cap = StrokeCap.Round))
    drawPath(Path().apply { moveTo(212f, 160f + egim); quadraticBezierTo(236f, 148f, 260f, 160f - egim) }, kas, style = Stroke(3f, cap = StrokeCap.Round))
    // gözler (kırpışta dikey basılır)
    val ry = 26f * kirp.coerceAtLeast(0.08f) * (if (hal == NexoHal.HEYECAN) 1.08f else 1f)
    for (cx in listOf(164f, 236f)) {
        val c = Offset(cx + dx, gozY)
        drawOval(Brush.radialGradient(GOZ, Offset(c.x, c.y - 2f), 26f), Offset(c.x - 22f, c.y - ry), Size(44f, ry * 2))
        if (kirp > 0.5f) {
            drawCircle(Color.White, 7f, Offset(c.x - 7f, c.y - 9f))
            drawCircle(Color.White.copy(alpha = 0.7f), 3f, Offset(c.x + 7f, c.y + 10f))
        }
    }
    // yanaklar
    drawOval(Color(0xFFF472B6).copy(alpha = if (hal == NexoHal.HEYECAN) 0.55f else 0.35f), Offset(130f, 209f), Size(20f, 10f))
    drawOval(Color(0xFFF472B6).copy(alpha = if (hal == NexoHal.HEYECAN) 0.55f else 0.35f), Offset(250f, 209f), Size(20f, 10f))
    // ağız
    val agiz = Stroke(5f, cap = StrokeCap.Round)
    when (hal) {
        NexoHal.HEYECAN -> {
            val p = Path().apply { moveTo(176f, 216f); quadraticBezierTo(202f, 250f, 230f, 214f); close() }
            drawPath(p, camg.copy(alpha = 0.9f)); drawPath(p, camg, style = agiz)
        }
        NexoHal.ENDISE -> drawPath(Path().apply { moveTo(180f, 228f); quadraticBezierTo(202f, 216f, 226f, 228f) }, camg, style = agiz)
        NexoHal.DUSUNUYOR -> drawLine(camg, Offset(190f, 224f), Offset(218f, 220f), 5f, StrokeCap.Round)
        else -> {
            drawPath(Path().apply { moveTo(178f, 220f); quadraticBezierTo(202f, 236f, 230f, 214f) }, camg, style = agiz)
            drawLine(camg, Offset(230f, 214f), Offset(235f, 209f), 4f, StrokeCap.Round)
        }
    }
}

/** Maskot + konuşma balonu. Metin harf harf yazılır (daktilo), değişince yeniden başlar. */
@Composable
fun NexoKonusuyor(metin: String, hal: NexoHal, modifier: Modifier = Modifier, boyut: Dp = 104.dp, selam: Boolean = false) {
    var gorunen by remember(metin) { mutableStateOf("") }
    LaunchedEffect(metin) {
        for (i in 1..metin.length) { gorunen = metin.take(i); delay(18) }
    }
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Nexo(boyut, hal, selam)
        Box(Modifier.weight(1f).clip(RoundedCornerShape(topStart = 4.dp, topEnd = 18.dp, bottomEnd = 18.dp, bottomStart = 18.dp))
            .background(Brush.linearGradient(listOf(Color(0xFF241B5E), Color(0xFF161340))))
            .border(1.dp, Nx.KenarParlak, RoundedCornerShape(topStart = 4.dp, topEnd = 18.dp, bottomEnd = 18.dp, bottomStart = 18.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp)) {
            Text(metin, color = Color.Transparent, fontSize = 14.sp, lineHeight = 19.sp)     // yer tutucu: balon zıplamasın
            Text(gorunen, color = Nx.Metin, fontSize = 14.sp, lineHeight = 19.sp, fontWeight = FontWeight.Medium)
        }
    }
}

/** Sayı değişince yumuşakça sayarak geçer. */
@Composable
fun SayanSayi(deger: Double, bicim: (Double) -> String, content: @Composable (String) -> Unit) {
    val a by animateFloatAsState(deger.toFloat(), tween(900, easing = FastOutSlowInEasing), label = "say")
    content(bicim(a.toDouble()))
}
