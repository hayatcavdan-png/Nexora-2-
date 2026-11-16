package com.nexora.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Tasarımdaki özel çizgi ikonlar (ince kontur). */
@Composable fun IkonRobot(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.08f, cap = StrokeCap.Round)
    drawRoundRect(renk, Offset(w * 0.16f, w * 0.3f), Size(w * 0.68f, w * 0.5f), CornerRadius(w * 0.16f), style = s)
    drawLine(renk, Offset(w * 0.5f, w * 0.3f), Offset(w * 0.5f, w * 0.14f), w * 0.08f, StrokeCap.Round)
    drawCircle(renk, w * 0.05f, Offset(w * 0.5f, w * 0.11f))
    drawCircle(renk, w * 0.065f, Offset(w * 0.37f, w * 0.53f)); drawCircle(renk, w * 0.065f, Offset(w * 0.63f, w * 0.53f))
    drawLine(renk, Offset(w * 0.08f, w * 0.5f), Offset(w * 0.08f, w * 0.62f), w * 0.08f, StrokeCap.Round)
    drawLine(renk, Offset(w * 0.92f, w * 0.5f), Offset(w * 0.92f, w * 0.62f), w * 0.08f, StrokeCap.Round)
}

@Composable fun IkonRadar(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val c = Offset(w / 2, w / 2); val s = Stroke(w * 0.07f, cap = StrokeCap.Round)
    drawCircle(renk, w * 0.42f, c, style = s); drawCircle(renk, w * 0.27f, c, style = s); drawCircle(renk, w * 0.09f, c)
    drawLine(renk, c, Offset(w * 0.82f, w * 0.2f), w * 0.07f, StrokeCap.Round)
}

@Composable fun IkonDna(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.08f, cap = StrokeCap.Round)
    val a = Path().apply { moveTo(w * 0.28f, w * 0.06f); cubicTo(w * 0.28f, w * 0.4f, w * 0.72f, w * 0.6f, w * 0.72f, w * 0.94f) }
    val b = Path().apply { moveTo(w * 0.72f, w * 0.06f); cubicTo(w * 0.72f, w * 0.4f, w * 0.28f, w * 0.6f, w * 0.28f, w * 0.94f) }
    drawPath(a, renk, style = s); drawPath(b, renk, style = s)
    for (y in listOf(0.2f, 0.8f)) drawLine(renk, Offset(w * 0.34f, w * y), Offset(w * 0.66f, w * y), w * 0.06f, StrokeCap.Round)
}

@Composable fun IkonCubuk(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width
    listOf(0.18f to 0.55f, 0.43f to 0.32f, 0.68f to 0.12f).forEach { (x, y) ->
        drawRoundRect(renk, Offset(w * x, w * y), Size(w * 0.16f, w * (0.88f - y)), CornerRadius(w * 0.04f))
    }
}

@Composable fun IkonKalkan(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.08f, cap = StrokeCap.Round)
    val k = Path().apply {
        moveTo(w * 0.5f, w * 0.06f); lineTo(w * 0.86f, w * 0.2f); cubicTo(w * 0.86f, w * 0.6f, w * 0.7f, w * 0.82f, w * 0.5f, w * 0.94f)
        cubicTo(w * 0.3f, w * 0.82f, w * 0.14f, w * 0.6f, w * 0.14f, w * 0.2f); close()
    }
    drawPath(k, renk, style = s)
    val t = Path().apply { moveTo(w * 0.34f, w * 0.5f); lineTo(w * 0.46f, w * 0.62f); lineTo(w * 0.68f, w * 0.38f) }
    drawPath(t, renk, style = s)
}

@Composable fun IkonGuc(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.1f, cap = StrokeCap.Round)
    drawArc(renk, -60f, 300f, false, Offset(w * 0.16f, w * 0.18f), Size(w * 0.68f, w * 0.68f), style = s)
    drawLine(renk, Offset(w * 0.5f, w * 0.06f), Offset(w * 0.5f, w * 0.46f), w * 0.1f, StrokeCap.Round)
}

@Composable fun IkonCanta(renk: Color, boyut: Dp = 24.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val s = Stroke(w * 0.08f, cap = StrokeCap.Round)
    drawRoundRect(renk, Offset(w * 0.1f, w * 0.3f), Size(w * 0.8f, w * 0.56f), CornerRadius(w * 0.1f), style = s)
    drawRoundRect(renk, Offset(w * 0.34f, w * 0.14f), Size(w * 0.32f, w * 0.18f), CornerRadius(w * 0.06f), style = s)
    drawLine(renk, Offset(w * 0.1f, w * 0.52f), Offset(w * 0.9f, w * 0.52f), w * 0.08f)
}

/** AutoPilot kartlarındaki robot kask avatarı. */
@Composable fun RobotAvatar(boyut: Dp = 72.dp) = Canvas(Modifier.size(boyut)) {
    val w = size.width; val c = Offset(w / 2, w / 2)
    drawCircle(Brush.radialGradient(listOf(Color(0x558B5CF6), Color.Transparent), c, w * 0.6f), w * 0.6f, c)
    drawCircle(Brush.linearGradient(listOf(Color(0xFF2B2F6B), Color(0xFF0E1030)), Offset.Zero, Offset(w, w)), w * 0.42f, c)
    drawCircle(Brush.linearGradient(listOf(Color(0xFF8B5CF6), Color(0xFF22D3EE))), w * 0.42f, c, style = Stroke(w * 0.035f))
    drawRoundRect(Brush.linearGradient(listOf(Color(0xFF3B82F6), Color(0xFF8B5CF6), Color(0xFF22D3EE)), Offset(w * 0.2f, 0f), Offset(w * 0.8f, 0f)),
        Offset(w * 0.2f, w * 0.38f), Size(w * 0.6f, w * 0.22f), CornerRadius(w * 0.11f))
    drawRoundRect(Color.White.copy(alpha = 0.35f), Offset(w * 0.26f, w * 0.41f), Size(w * 0.2f, w * 0.05f), CornerRadius(w * 0.03f))
    drawCircle(Color(0xFFE0F2FE), w * 0.035f, Offset(w * 0.38f, w * 0.49f)); drawCircle(Color(0xFFE0F2FE), w * 0.035f, Offset(w * 0.62f, w * 0.49f))
}

/** Wallet DNA puan halkası. */
@Composable fun PuanHalkasi(oran: Float, renk: Color, boyut: Dp = 96.dp, icerik: @Composable () -> Unit) {
    androidx.compose.foundation.layout.Box(Modifier.size(boyut), contentAlignment = androidx.compose.ui.Alignment.Center) {
        Canvas(Modifier.size(boyut)) {
            val st = Stroke(size.width * 0.08f, cap = StrokeCap.Round)
            drawArc(Color(0xFF26244A), 0f, 360f, false, style = st, topLeft = Offset(st.width / 2, st.width / 2),
                size = Size(size.width - st.width, size.height - st.width))
            drawArc(renk, -90f, 360f * oran.coerceIn(0f, 1f), false, style = st, topLeft = Offset(st.width / 2, st.width / 2),
                size = Size(size.width - st.width, size.height - st.width))
        }
        icerik()
    }
}
