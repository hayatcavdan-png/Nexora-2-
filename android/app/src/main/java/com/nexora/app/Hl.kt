package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Hyperliquid trader takibi (N39, yalnızca kurucu): büyük trader'ları kopyalasaydık ne olurdu? Salt okunur gölge ölçüm. */
@Composable
fun HlEkrani(url: String, key: String) {
    var d by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    var yukleniyor by remember { mutableStateOf(false) }
    var tetik by remember { mutableIntStateOf(0) }
    var secili by remember { mutableStateOf("") }
    LaunchedEffect(tetik) {
        yukleniyor = true; hata = ""
        try { d = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/hl", zamanAsimi = 20_000) }) }
        catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e
            hata = when {
                e.message?.contains("403") == true -> "Bu ekran yalnızca kurucuya açık."
                e.message?.contains("404") == true -> "Sunucu güncel değil: guncelle"
                else -> "Veri alınamadı: ${e.message}"
            }
        }
        yukleniyor = false
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Hyperliquid gölge ölçümü", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                TextButton({ tetik++ }, enabled = !yukleniyor) { Text(if (yukleniyor) "…" else "Yenile", color = Nx.Nane) }
            }
            Text("Büyük trader'lar pozisyon açınca, biz gördüğümüz andaki fiyattan girseydik ne olurdu? İşlem yok; kaldıraçsız, " +
                 "ücret dahil, fonlama hariç. Son 14 gün.", color = Nx.Soluk, fontSize = 12.sp)
            if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
            val o = d?.optJSONObject("ozet")
            if (d != null && o == null) Text("Henüz ölçüm yok. Servis (nexora-hl) çalışıyorsa ilk sonuçlar birkaç saat içinde gelir.",
                                             color = Nx.Soluk, fontSize = 13.sp)
            if (o != null) {
                SatirKV("Takip edilen trader", "${d!!.optInt("liste")}")
                SatirKV("Açık / kapanan ölçüm", "${o.optInt("acik")} / ${o.optInt("kapanan")}")
                OzetSatiri("Biz (kopyalasaydık)", o.optJSONObject("biz"))
                OzetSatiri("Trader'ın kendisi", o.optJSONObject("kaynak"))
                OzetSatiri("30 dk'da çıksaydık", o.optJSONObject("dk30"))
                if (!o.isNull("gecikme_pct")) SatirKV("Gecikme maliyeti (medyan)", hlYuzde(o.optDouble("gecikme_pct"), 3))
                Text("Gerçekçi ölçüm", color = Nx.Metin, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
                OzetSatiri("Emir defterinden (${o.optInt("boyut_usd", 100)}$)", o.optJSONObject("defter"))
                OzetSatiri("Fonlama dahil NET", o.optJSONObject("net"))
                if (!o.isNull("kayma_pct") && o.has("kayma_pct")) SatirKV("Giriş kayması (medyan)", hlYuzde(o.optDouble("kayma_pct"), 3))
                o.optJSONObject("kaldirac")?.let { k -> k.keys().forEach { ad -> OzetSatiri("Trader kaldıracı $ad", k.optJSONObject(ad)) } }
                o.optJSONArray("duraklar")?.let { a ->
                    for (i in 0 until a.length()) { val x = a.getJSONObject(i)
                        OzetSatiri("Zarar durdur %${x.optInt("durak")} (${x.optInt("tetik")} tetik)", x) }
                }
                Text("Gecikme ve kayma: artı = bize maliyet, eksi = bizim lehimize.", color = Nx.Soluk, fontSize = 11.sp)
                if (o.optInt("kapanan") < 30) Text("Örneklem küçük: 30 kapanan ölçümden önce karar verilmez.", color = Nx.Kehribar, fontSize = 12.sp)
            }
        }
        YzAnalizKarti(url, key, "hl", tetik)
        d?.optJSONArray("cuzdanlar")?.let { a ->
            if (a.length() > 0) NeonKart(Modifier.fillMaxWidth()) {
                Text("Trader'lar", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Text("adres · kapanan · ort (biz) · trader ort · açık — ayrıntı için dokunun", color = Nx.Soluk, fontSize = 11.sp)
                for (i in 0 until minOf(a.length(), 40)) {
                    val m = a.getJSONObject(i); val w = m.optString("wallet")
                    Row(Modifier.fillMaxWidth().clickable { secili = if (secili == w) "" else w }.padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(w.take(6) + "…" + w.takeLast(4), color = Nx.Metin, fontSize = 12.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.weight(1.3f))
                        Text("${m.optInt("n")}", color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(0.5f))
                        Text(if (m.isNull("ort")) "—" else hlYuzde(m.optDouble("ort")), color = renk(m, "ort"), fontSize = 12.sp, modifier = Modifier.weight(1f))
                        Text(if (m.isNull("kaynak_ort")) "—" else hlYuzde(m.optDouble("kaynak_ort")), color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(1f))
                        Text("${m.optInt("acik")}", color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.weight(0.4f))
                    }
                    if (secili == w) TraderDetay(url, key, w)
                }
            }
        }
        d?.optJSONArray("son")?.let { a ->
            if (a.length() > 0) NeonKart(Modifier.fillMaxWidth()) {
                Text("Son ölçümler", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                val f = SimpleDateFormat("dd.MM HH:mm", Locale.getDefault())
                for (i in 0 until a.length()) {
                    val s = a.getJSONObject(i); val long = s.optString("yon") == "long"
                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.clip(RoundedCornerShape(50)).background(if (long) Nx.Yesil.copy(alpha = 0.18f) else Nx.Kirmizi.copy(alpha = 0.18f))
                            .padding(horizontal = 8.dp, vertical = 2.dp)) {
                            Text(if (long) "LONG" else "SHORT", color = if (long) Nx.Yesil else Nx.Kirmizi, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        }
                        Spacer(Modifier.width(8.dp))
                        Column(Modifier.weight(1f)) {
                            Text(s.optString("coin"), color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                            Text(f.format(Date((s.optDouble("giris_ts") * 1000).toLong())) + " · " + s.optString("wallet").take(6) +
                                 (if (s.isNull("gecikme_pct")) "" else " · gecikme " + hlYuzde(s.optDouble("gecikme_pct"), 3)),
                                 color = Nx.Soluk, fontSize = 11.sp)
                        }
                        Text(if (s.optString("durum") == "acik") "açık" else if (s.isNull("getiri_pct")) "—" else hlYuzde(s.optDouble("getiri_pct")),
                             color = if (s.optString("durum") == "acik") Nx.Soluk else renk(s, "getiri_pct"), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun OzetSatiri(ad: String, o: JSONObject?) {
    if (o == null || o.isNull("ort")) { SatirKV(ad, "—"); return }
    SatirKV(ad, "ort ${hlYuzde(o.optDouble("ort"))} · med ${hlYuzde(o.optDouble("medyan"))} · kazanan %${o.optInt("pozitif")} (n=${o.optInt("n")})")
}

private fun hlYuzde(x: Double, basamak: Int = 2) = String.format(Locale.US, "%+.${basamak}f%%", x)
private fun renk(o: JSONObject, alan: String): Color = if (o.isNull(alan)) Nx.Soluk else if (o.optDouble(alan) >= 0) Nx.Yesil else Nx.Kirmizi

/** Yapay zekâ destekli yorum (salt okunur): sunucu raporu bir dil modeline yorumlatır. Anahtar yoksa kural tabanlı özet. */
@Composable
fun YzAnalizKarti(url: String, key: String, konu: String, dis: Int = 0) {
    var d by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    var yukleniyor by remember { mutableStateOf(false) }
    var istek by remember { mutableIntStateOf(0) }                 // 0: henüz istenmedi
    var yenile by remember { mutableStateOf(false) }               // true: önbelleği atla (yeniden üret)
    LaunchedEffect(istek, dis) {
        if (istek == 0) return@LaunchedEffect
        yukleniyor = true; hata = ""
        try { d = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/yz-analiz?konu=$konu&yenile=${if (yenile) 1 else 0}", zamanAsimi = 75_000) }) }
        catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; hata = if (e.message?.contains("404") == true) "Sunucu güncel değil: guncelle" else "Yorum alınamadı: ${e.message}" }
        yukleniyor = false
    }
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            NexoYuz(28.dp, NexoIfade.DUSUN)
            Spacer(Modifier.width(8.dp))
            Text("Yapay zekâ analizi", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            TextButton({ yenile = d != null; istek++ }, enabled = !yukleniyor) {
                Text(if (yukleniyor) "Düşünüyor…" else if (d == null) "Analiz et" else "Yeniden üret", color = Nx.Nane)
            }
        }
        if (d == null && !yukleniyor && hata.isEmpty())
            Text("Rapordaki rakamları yapay zekâ yorumlar: özet, güçlü ve zayıf yanlar, sonraki adım. Hiçbir ayarı değiştirmez.",
                 color = Nx.Soluk, fontSize = 12.sp)
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
        d?.let { r ->
            if (!r.isNull("uyari") && r.optString("uyari").isNotEmpty()) Text(r.optString("uyari"), color = Nx.Kehribar, fontSize = 12.sp)
            Text(r.optString("metin"), color = Nx.Metin, fontSize = 13.sp, lineHeight = 19.sp)
            val kaynak = when (r.optString("kaynak")) { "yz" -> "yapay zekâ"; "onbellek" -> "yapay zekâ (önbellek)"; else -> "kural tabanlı" }
            Text("Kaynak: $kaynak" + (if (r.isNull("model")) "" else " · ${r.optString("model")}") + " · ${saat(r.optDouble("ts"))}",
                 color = Nx.Soluk, fontSize = 11.sp)
        }
    }
}

/** Trader detayı: son 30 günün tüm ölçümleri (net getiri, kaldıraç, en kötü an). */
@Composable
private fun TraderDetay(url: String, key: String, w: String) {
    var d by remember(w) { mutableStateOf<JSONObject?>(null) }
    var hata by remember(w) { mutableStateOf("") }
    LaunchedEffect(w) {
        try { d = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/hl-cuzdan?w=$w", zamanAsimi = 20_000) }) }
        catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; hata = if (e.message?.contains("404") == true) "Sunucu güncel değil: guncelle" else "Alınamadı: ${e.message}" }
    }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Nx.DolguMor).padding(10.dp),
           verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(w, color = Nx.Soluk, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 12.sp)
        if (d == null && hata.isEmpty()) Text("Yükleniyor…", color = Nx.Soluk, fontSize = 12.sp)
        d?.optJSONObject("ozet")?.let { o ->
            Text("30 gün: ${o.optInt("n")} kapanan, ${o.optInt("acik")} açık · " +
                 (if (o.isNull("ort")) "ort —" else "ort ${hlYuzde(o.optDouble("ort"))} · med ${hlYuzde(o.optDouble("medyan"))} · kazanan %${o.optInt("pozitif")}") +
                 (if (o.isNull("kaldirac_medyan")) "" else " · kaldıraç ~${o.optDouble("kaldirac_medyan").toInt()}x") +
                 (if (o.isNull("tutma_dk_medyan")) "" else " · tutma ~${o.optDouble("tutma_dk_medyan").toInt()} dk"),
                 color = Nx.Metin, fontSize = 12.sp)
        }
        val f = SimpleDateFormat("dd.MM HH:mm", Locale.getDefault())
        d?.optJSONArray("olcumler")?.let { a ->
            for (i in 0 until minOf(a.length(), 20)) {
                val x = a.getJSONObject(i)
                val g = if (!x.isNull("getiri_net_pct")) x.optDouble("getiri_net_pct") else if (!x.isNull("getiri_pct")) x.optDouble("getiri_pct") else Double.NaN
                Row(Modifier.fillMaxWidth()) {
                    Text("${f.format(Date((x.optDouble("giris_ts") * 1000).toLong()))} ${x.optString("coin")} ${if (x.optInt("yon") > 0) "L" else "S"}" +
                         (if (x.isNull("kaldirac")) "" else " ${x.optDouble("kaldirac").toInt()}x") +
                         (if (x.isNull("en_kotu_pct")) "" else " · en kötü ${hlYuzde(x.optDouble("en_kotu_pct"), 1)}"),
                         color = Nx.Soluk, fontSize = 11.sp, modifier = Modifier.weight(1f))
                    Text(if (x.optString("durum") == "acik") "açık" else if (g.isNaN()) "—" else hlYuzde(g),
                         color = if (g.isNaN() || x.optString("durum") == "acik") Nx.Soluk else if (g >= 0) Nx.Yesil else Nx.Kirmizi, fontSize = 11.sp)
                }
            }
        }
    }
}
