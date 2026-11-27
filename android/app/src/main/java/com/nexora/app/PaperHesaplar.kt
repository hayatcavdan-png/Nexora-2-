package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Locale

/** 5.35.0 · Ana sayfa (kurucu): iki ayrı PAPER hesap yan yana (her biri 100 $ ile başladı). Hangi kutuya dokunulursa
 *  ayrıntısı hemen altında açılır; seçim hatırlanır. Solana verisi uygulamada (Veri); Hyperliquid: GET /hl-paper. Gerçek işlem yok. */
@Composable
fun PaperHesaplarKarti(v: Veri, url: String, key: String, gizle: Boolean, gizleDegis: () -> Unit, git: (String) -> Unit,
                       memeDetay: @Composable () -> Unit) {
    val sp = LocalContext.current.getSharedPreferences("nx", android.content.Context.MODE_PRIVATE)
    var secim by remember { mutableStateOf(sp.getString("ana_hesap", "m") ?: "m") }
    val sec = { x: String -> secim = x; sp.edit().putString("ana_hesap", x).apply() }
    var hl by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    LaunchedEffect(url, key, v.guncelleme) {
        try { hl = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/hl-paper", zamanAsimi = 15_000) }); hata = "" }
        catch (e: kotlinx.coroutines.CancellationException) { throw e }
        catch (e: Exception) { hata = if (e.message?.contains("404") == true) "Sunucu güncel değil: guncelle" else "Alınamadı" }
    }
    val tr = Locale("tr")
    val yuzde = { x: Double -> (if (x >= 0) "+" else "") + String.format(tr, "%.2f", x) + "%" }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Paper hesaplar", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Text("SANAL · ayrı ayrı 100 $", color = Nx.UstMetin, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                 modifier = Modifier.clip(RoundedCornerShape(50)).background(Nx.Kehribar).padding(horizontal = 8.dp, vertical = 3.dp))
            IconButton(gizleDegis, Modifier.size(36.dp)) {
                Icon(if (gizle) Icons.Filled.Lock else Icons.Filled.Search, "Gizle", tint = Nx.Soluk, modifier = Modifier.size(18.dp))
            }
        }
        val h = hl
        val bos = h == null || h.optBoolean("bos")
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val memeKz = if (v.baslangic > 0) (v.toplam - v.baslangic) / v.baslangic * 100 else 0.0
            HesapKutusu("Solana memecoin", "Kopya · yalnız alış", if (gizle) "•••• $" else "$" + usd(v.toplam),
                        if (gizle) "••" else yuzde(memeKz), memeKz, "${v.pozisyonlar.size} açık", Nx.Gok, secim == "m",
                        Modifier.weight(1f).fillMaxHeight()) { sec("m") }
            val hlKz = h?.dbl("kz_pct") ?: 0.0
            HesapKutusu("Hyperliquid", "Kopya · long/short",
                        if (bos) (if (hata.isNotEmpty()) "—" else "$100.00") else if (gizle) "•••• $" else "$" + usd(h!!.optDouble("varlik", 100.0)),
                        if (bos) (hata.ifEmpty { "başlıyor" }) else if (gizle) "••" else yuzde(hlKz), hlKz,
                        if (bos) "servis bekleniyor" else "${h!!.optJSONArray("pozisyonlar")?.length() ?: 0} açık · " +
                            "${h.optJSONArray("uygun")?.length() ?: 0} uygun",
                        Nx.Pembe, secim == "h", Modifier.weight(1f).fillMaxHeight()) { sec("h") }
        }
        Column(Modifier.fillMaxWidth().belir().clip(RoundedCornerShape(20.dp)).background(Nx.Yuzey).padding(14.dp),
               verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val meme = secim != "h"
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(if (meme) "Solana memecoin · ayrıntı" else "Hyperliquid · ayrıntı", color = Nx.Metin, fontSize = 15.sp,
                     fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text(if (meme) "Tüm işlemler ›" else "Trader'lar ›", color = Nx.Gok, fontSize = 12.sp,
                     modifier = Modifier.clickable { git(if (meme) "islemler" else "hlana") }.padding(4.dp))
            }
            if (meme) memeDetay()
            else if (!bos) HlOzet(h!!, gizle)
            else Text(if (hata.isNotEmpty()) hata else "Hyperliquid paper hesabı servis ilk turunu tamamlayınca burada görünecek.",
                      color = Nx.Soluk, fontSize = 12.sp)
        }
    }
}

@Composable
private fun HesapKutusu(ad: String, alt: String, bakiye: String, kz: String, kzDeger: Double, durum: String, vurgu: Color,
                        secili: Boolean, mod: Modifier, tikla: () -> Unit) {
    Column(mod.belir().neonIsik(vurgu, 20.dp).clip(RoundedCornerShape(20.dp))
        .border(2.dp, if (secili) vurgu else Color.Transparent, RoundedCornerShape(20.dp))
        .background(Brush.verticalGradient(listOf(vurgu.copy(alpha = 0.16f), Nx.Yuzey)))
        .clickable { tikla() }.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(ad, color = vurgu, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1)
        Text(alt, color = Nx.Soluk, fontSize = 11.sp, maxLines = 1)
        Text(bakiye, color = Nx.Metin, fontSize = 21.sp, fontWeight = FontWeight.Bold, fontFamily = Orbitron, maxLines = 1,
             modifier = Modifier.padding(top = 4.dp))
        Text(kz, color = if (kz.startsWith("+") || kz.startsWith("-")) (if (kzDeger >= 0) Nx.Nane else Nx.Kirmizi) else Nx.Soluk,
             fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        Spacer(Modifier.weight(1f))
        Text(durum + if (secili) "  ▾" else "  ›", color = Nx.Soluk, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Hyperliquid ayrıntısı: kurallar, açık long/short pozisyonlar, son kapananlar. */
@Composable
private fun HlOzet(h: JSONObject, gizle: Boolean) {
    val poz = h.optJSONArray("pozisyonlar"); val son = h.optJSONArray("son_kapanan")
    val kap = h.optJSONObject("kapanan") ?: JSONObject(); val k = h.optJSONObject("kurallar") ?: JSONObject()
    Text("${k.optDouble("kaldirac", 3.0).toInt()}x · pozisyon başı %${k.optDouble("poz_pct", 5.0).toInt()} teminat · " +
         "kapanan ${kap.optInt("n")}" + (if (kap.isNull("kazanma")) "" else " · kazanan %${kap.optInt("kazanma")}") +
         " · tasfiye ${h.optInt("tasfiye")}", color = Nx.Soluk, fontSize = 11.sp)
    if (poz != null && poz.length() > 0) for (i in 0 until poz.length()) PozSatiri(poz.getJSONObject(i), "anlik_pnl", gizle, acik = true)
    else Text(if ((h.optJSONArray("uygun")?.length() ?: 0) == 0)
                  "Açık pozisyon yok. Kopyalanmaya uygun trader henüz yok (≥${k.optInt("min_olcum", 30)} ölçüm ve artı ortalama gerekiyor); ölçüm biriktikçe otomatik başlar."
              else "Açık pozisyon yok. Uygun trader'lar yeni pozisyon açınca kopyalanır.", color = Nx.Soluk, fontSize = 12.sp)
    if (son != null && son.length() > 0) {
        Text("Son kapananlar", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
        for (i in 0 until minOf(son.length(), 3)) PozSatiri(son.getJSONObject(i), "pnl", gizle, acik = false)
    }
}

@Composable
private fun PozSatiri(x: JSONObject, alan: String, gizle: Boolean, acik: Boolean) {
    val long = x.optInt("yon") > 0; val renk = if (long) Nx.Nane else Nx.Kirmizi
    val kz = x.dbl(alan)
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(if (long) "LONG" else "SHORT", color = renk, fontSize = 10.sp, fontWeight = FontWeight.Bold,
             modifier = Modifier.clip(RoundedCornerShape(50)).background(renk.copy(alpha = 0.18f)).padding(horizontal = 7.dp, vertical = 2.dp))
        Column(Modifier.weight(1f)) {
            Text(x.str("coin"), color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
            Text(String.format(Locale.US, "%.2f $", x.optDouble("buyukluk")) + (if (acik) " · açık" else " · " + x.str("neden")),
                 color = Nx.Soluk, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Text(if (kz == null) "—" else if (gizle) "••" else isaretli(kz) + "$", color = if (kz == null) Nx.Soluk else kzRenk(kz),
             fontSize = 13.sp, fontWeight = FontWeight.Bold)
    }
}
