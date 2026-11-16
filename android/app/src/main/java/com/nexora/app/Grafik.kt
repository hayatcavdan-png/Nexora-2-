package com.nexora.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Portföy değer eğrisi: noktadan noktaya çizgi, altı yarı saydam dolgu, son nokta vurgulu. */
@Composable
fun DegerGrafigi(noktalar: List<Nokta2>, baslangic: Double, modifier: Modifier = Modifier) {
    if (noktalar.size < 2) {
        Box(modifier.fillMaxWidth().height(140.dp), contentAlignment = Alignment.Center) {
            Text("İlk işlemler kapandıkça grafik burada oluşacak.", color = Nx.Soluk, fontSize = 13.sp)
        }
        return
    }
    val degerler = noktalar.map { it.deger } + baslangic
    var min = degerler.min(); var max = degerler.max()
    if (max - min < 0.5) { val orta = (max + min) / 2; min = orta - 0.25; max = orta + 0.25 }
    val pay = (max - min) * 0.12; min -= pay; max += pay
    val t0 = noktalar.first().ts; val t1 = noktalar.last().ts.coerceAtLeast(t0 + 1)
    val sonDeger = noktalar.last().deger
    val renk = if (sonDeger >= baslangic) Nx.Yesil else Nx.Kirmizi
    // çizgi soldan sağa akarak çizilir (aralık ya da veri değişince yeniden)
    val ilerleme = remember(t0, noktalar.size) { Animatable(0f) }
    LaunchedEffect(t0, noktalar.size) { ilerleme.animateTo(1f, tween(1100, easing = FastOutSlowInEasing)) }

    Column(modifier) {
        Row(Modifier.fillMaxWidth()) {
            Column(Modifier.height(150.dp).padding(end = 6.dp), verticalArrangement = Arrangement.SpaceBetween) {
                Text(usd(max - pay), color = Nx.Soluk, fontSize = 10.sp)
                Text(usd(min + pay), color = Nx.Soluk, fontSize = 10.sp)
            }
            Canvas(Modifier.weight(1f).height(150.dp)) {
                val w = size.width; val h = size.height
                fun x(ts: Double) = ((ts - t0) / (t1 - t0) * w).toFloat()
                fun y(v: Double) = (h - (v - min) / (max - min) * h).toFloat()
                for (i in 0..3) {
                    val yy = h * i / 3f
                    drawLine(Nx.Cizgi, Offset(0f, yy), Offset(w, yy), strokeWidth = 1f)
                }
                val by = y(baslangic)
                drawLine(Nx.Soluk.copy(alpha = 0.5f), Offset(0f, by), Offset(w, by), strokeWidth = 1.5f,
                    pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(8f, 8f)))
                val cizgi = Path(); val alan = Path()
                noktalar.forEachIndexed { i, p ->
                    val px = x(p.ts); val py = y(p.deger)
                    if (i == 0) { cizgi.moveTo(px, py); alan.moveTo(px, h); alan.lineTo(px, py) }
                    else { cizgi.lineTo(px, py); alan.lineTo(px, py) }
                }
                alan.lineTo(x(noktalar.last().ts), h); alan.close()
                val p = ilerleme.value
                clipRect(right = w * p) {
                    drawPath(alan, Brush.verticalGradient(listOf(renk.copy(alpha = 0.35f), renk.copy(alpha = 0f))))
                    drawPath(cizgi, renk.copy(alpha = 0.35f), style = Stroke(width = 12f, cap = StrokeCap.Round))   // neon parıltı
                    drawPath(cizgi, renk, style = Stroke(width = 4f, cap = StrokeCap.Round))
                }
                if (p > 0.98f) {
                    val son = noktalar.last()
                    drawCircle(renk.copy(alpha = 0.3f), radius = 12f, center = Offset(x(son.ts), y(son.deger)))
                    drawCircle(androidx.compose.ui.graphics.Color.White, radius = 6f, center = Offset(x(son.ts), y(son.deger)))
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(start = 40.dp, top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(gunAy(t0) + " " + saat(t0).take(5), color = Nx.Soluk, fontSize = 10.sp)
            Text("şimdi", color = Nx.Soluk, fontSize = 10.sp)
        }
    }
}
