package com.nexora.app

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

private data class Dugum(val x: Float, val y: Float, val ax: Float, val ay: Float, val faz: Float, val renk: Int)

/**
 * Canlı arka plan: yavaşça gezen sinir ağı düğümleri, aralarında beliren bağlantılar ve bağlantılardan akan sinyaller;
 * arkada iki kutup ışığı lekesi. Tek tuval, tek zaman sayacı: içerik yeniden düzenlenmez, yalnızca bu tuval yeniden çizilir.
 */
@Composable
fun AiArkaplan(modifier: Modifier = Modifier) {
    val t = rememberInfiniteTransition(label = "ag").animateFloat(0f, 1f, infiniteRepeatable(tween(60_000, easing = LinearEasing)), label = "t")
    val dugumler = remember {
        val r = java.util.Random(7)
        List(18) { Dugum(r.nextFloat(), r.nextFloat(), 0.03f + r.nextFloat() * 0.05f, 0.02f + r.nextFloat() * 0.04f, r.nextFloat() * 6.28f, it % 4) }
    }
    Canvas(modifier.fillMaxSize()) {
        val w = size.width; val h = size.height
        val f = (t.value * 2 * PI).toFloat()
        drawRect(Nx.Zemin)
        // kutup ışıkları
        val a1 = Offset(w * (0.2f + 0.15f * sin(f * 2)), h * (0.12f + 0.05f * cos(f * 3)))
        drawCircle(Brush.radialGradient(listOf(Nx.Nane.copy(alpha = 0.16f), Color.Transparent), a1, w * 0.75f), w * 0.75f, a1)
        val a2 = Offset(w * (0.85f + 0.12f * cos(f * 2)), h * (0.5f + 0.12f * sin(f * 3)))
        drawCircle(Brush.radialGradient(listOf(Nx.Lila.copy(alpha = 0.14f), Color.Transparent), a2, w * 0.7f), w * 0.7f, a2)
        val a3 = Offset(w * (0.3f + 0.2f * sin(f * 4)), h * (0.92f + 0.04f * cos(f * 2)))
        drawCircle(Brush.radialGradient(listOf(Nx.Gok.copy(alpha = 0.10f), Color.Transparent), a3, w * 0.6f), w * 0.6f, a3)
        // sinir ağı
        val p = dugumler.map { d -> Offset(w * (d.x + d.ax * sin(f * 6 + d.faz)), h * (d.y + d.ay * cos(f * 5 + d.faz * 1.3f))) }
        val esik = w * 0.34f
        for (i in p.indices) for (j in i + 1 until p.size) {
            val uz = hypot(p[i].x - p[j].x, p[i].y - p[j].y)
            if (uz < esik) {
                val guc = 1f - uz / esik
                drawLine(Nx.AiRenkler[dugumler[i].renk].copy(alpha = 0.16f * guc), p[i], p[j], strokeWidth = 1.5f)
                if ((i + j) % 5 == 0) {                              // bağlantıdan akan sinyal
                    val k = ((t.value * 40f + i * 0.37f) % 1f)
                    val n = Offset(p[i].x + (p[j].x - p[i].x) * k, p[i].y + (p[j].y - p[i].y) * k)
                    drawCircle(Color.White.copy(alpha = 0.55f * guc), 2.5f, n)
                }
            }
        }
        for ((i, o) in p.withIndex()) {
            val renk = Nx.AiRenkler[dugumler[i].renk]
            val nabiz = 0.5f + 0.5f * sin(f * 30 + dugumler[i].faz)
            drawCircle(renk.copy(alpha = 0.10f + 0.08f * nabiz), 9f + 4f * nabiz, o)
            drawCircle(renk.copy(alpha = 0.55f), 3f, o)
        }
    }
}

/** Yapay zekâ çekirdeği: öğrenme ilerlemesi halkası, çevresinde dönen parçacıklar ve model/filtre durumu. */
@Composable
fun AiCekirdekKarti(yz: JSONObject?, modelFiltre: JSONObject, modifier: Modifier = Modifier) {
    val etiketli = yz?.optInt("etiketli", 0) ?: 0
    val hedef = (yz?.optInt("hedef", 500) ?: 500).coerceAtLeast(1)
    val oran = (etiketli.toFloat() / hedef).coerceIn(0f, 1f)
    val dolum by animateFloatAsState(oran, tween(1400, easing = FastOutSlowInEasing), label = "dolum")
    val t = rememberInfiniteTransition(label = "cekirdek").animateFloat(0f, 1f, infiniteRepeatable(tween(6000, easing = LinearEasing)), label = "d")
    val modelVar = !modelFiltre.isNull("model") && modelFiltre.optString("model").isNotEmpty()
    val filtreAcik = modelFiltre.optBoolean("etkin")
    NeonKart(modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.size(92.dp), contentAlignment = Alignment.Center) {
                Canvas(Modifier.fillMaxSize()) {
                    val c = Offset(size.width / 2, size.height / 2); val r = size.width * 0.36f; val kal = size.width * 0.09f
                    val aci = t.value * 360f
                    drawCircle(Brush.radialGradient(listOf(Nx.Nane.copy(alpha = 0.22f), Color.Transparent), c, size.width / 2), size.width / 2, c)
                    drawCircle(Nx.Cizgi, r, c, style = Stroke(kal))
                    rotate(-90f, c) {
                        drawArc(Brush.sweepGradient(Nx.AiRenkler + Nx.AiRenkler.first(), c), 0f, 360f * dolum.coerceAtLeast(0.02f), false,
                            Offset(c.x - r, c.y - r), Size(r * 2, r * 2), style = Stroke(kal, cap = StrokeCap.Round))
                    }
                    for (i in 0..2) {                                   // yörüngede dönen parçacıklar
                        val a = Math.toRadians((aci * (1 + i * 0.5f) + i * 120f).toDouble())
                        val yr = size.width * (0.46f + 0.02f * i)
                        drawCircle(Nx.AiRenkler[i + 1], 3.5f, Offset(c.x + yr * cos(a).toFloat(), c.y + yr * sin(a).toFloat()))
                    }
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    SayanSayi(oran * 100.0, { "%" + it.toInt() }) { Text(it, color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold) }
                }
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Yapay Zekâ Çekirdeği", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    AiRozet()
                }
                Text(if (yz == null) "Öğrenme verisi sunucudan bekleniyor" else "Öğreniyor: $etiketli / $hedef sinyal etiketlendi",
                     color = Nx.Soluk, fontSize = 12.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Etiket(if (modelVar) "Model hazır" else "Model eğitilmedi", if (modelVar) Nx.Nane else Nx.Kehribar)
                    Etiket(if (filtreAcik) "Filtre açık" else "Filtre kapalı", if (filtreAcik) Nx.Nane else Nx.Soluk)
                }
                Text(if (modelVar) "Model her sinyale kârlılık olasılığı veriyor." else "Yeterli veri birikince model eğitilecek; o zamana dek her sinyal ölçülüyor.",
                     color = Nx.Soluk, fontSize = 11.sp, lineHeight = 15.sp)
            }
        }
    }
}
