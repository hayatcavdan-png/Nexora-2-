package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Ekosistem: kimlik, görünen ad, açık mı, açık değilse hangi aşamada (yol haritası kodu). */
data class Ekosistem(val id: String, val ad: String, val acik: Boolean, val asama: String)

val EKOSISTEMLER = listOf(
    Ekosistem("tumu", "Tümü", true, ""),
    Ekosistem("solana", "Solana", true, ""),
    Ekosistem("bnb", "BNB", true, ""),
    Ekosistem("base", "Base", true, ""),
)

/** Ana sayfanın üstünde tek sıra: açık olmayan ekosistemler soluk ve "yakında"; dokununca aşaması söylenir. */
@Composable
fun EkosistemSecici(secili: String, sec: (String) -> Unit, bilgi: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        EKOSISTEMLER.forEach { e ->
            val s = e.id == secili
            Row(Modifier.alpha(if (e.acik) 1f else 0.55f).clip(RoundedCornerShape(50))
                .background(if (s) Nx.Nane.copy(alpha = 0.18f) else Nx.Yuzey)
                .border(1.dp, if (s) Nx.Nane else Nx.Cizgi, RoundedCornerShape(50))
                .clickable {
                    if (e.acik) sec(e.id)
                    else bilgi("${e.ad}: yol haritasında ${e.asama}. Önce paper modda test edilecek, sonra açılacak.")
                }
                .padding(horizontal = 14.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(e.ad, color = if (s) Nx.Nane else Nx.Metin, fontSize = 13.sp, fontWeight = if (s) FontWeight.Bold else FontWeight.Normal)
                if (!e.acik) Text("  yakında", color = Nx.Soluk, fontSize = 10.sp)
            }
        }
    }
}

/** Ana sayfa: ekosistemlerin tek bakışta durumu (sunucudaki /ekosistemler'den; yoksa yerel tahmin). Dokununca Karne açılır. */
@Composable
fun EkosistemOzeti(v: Veri, karneyeGit: () -> Unit) {
    NeonKart(Modifier.fillMaxWidth().clickable(onClick = karneyeGit)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("EKOSİSTEMLER", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text("Karne ›", color = Nx.Nane, fontSize = 12.sp)
        }
        val e = v.ekosistemler
        if (e == null) {
            EkoSatir("Solana · öncü cüzdanlar", "aktif", Nx.Nane, "${isaretli(v.kz)} USDC · ${v.pozisyonlar.size} pozisyon")
            EkoSatir("BNB Chain · Base · TON", "yakında", Nx.Kehribar, "sunucu güncellemesi bekleniyor")
            return@NeonKart
        }
        for (i in 0 until e.length()) {
            val x = e.getJSONObject(i)
            val aktif = x.optBoolean("aktif")
            val alt = if (aktif) "${isaretli(x.optDouble("kz", 0.0))} USDC gerçekleşen · ${x.optInt("kapanan")} kapanan · ${x.optInt("acik")} açık" +
                                 (if (x.optInt("cuzdan") > 0) " · ${x.optInt("cuzdan")} cüzdan" else "")
                      else "yol haritasında ${x.optString("asama")} · paper testten sonra"
            EkoSatir(x.optString("ad"), if (aktif) "aktif" else "yakında", if (aktif) Nx.Nane else Nx.Kehribar, alt)
        }
    }
}

@Composable
private fun EkoSatir(ad: String, durum: String, renk: androidx.compose.ui.graphics.Color, alt: String) {
    Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(ad, color = Nx.Metin, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Text(alt, color = Nx.Soluk, fontSize = 12.sp)
        }
        Etiket(durum, renk)
    }
}

/** Karne sekmesi: zararlar dahil, her kaynağın şeffaf paper sonucu. Pazarlamanın dayanağı burası. */
fun LazyListScope.karne(v: Veri, git: (String) -> Unit) {
    item(key = "kr_bas") { SayfaBasligi("Karne", "Zararlar dahil, gerçek fiyatlarla paper sonuçları", ikon = { NexoYuz(44.dp, NexoIfade.DUSUN) }) }
    item(key = "kr_solana") {
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("SOLANA · ÖNCÜ CÜZDANLAR", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                Etiket("paper", Nx.Gok)
            }
            Text("${isaretli(v.kz)} USDC", color = kzRenk(v.kz), fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Mini("Değer", usd(v.toplam))
                Mini("Kapanan", "${v.kapananlar.size}")
                Mini("Başarı", v.basariOrani?.let { yuzde(it, 0) } ?: "—")
                Mini("Açık", "${v.pozisyonlar.size}")
            }
            v.maxDusus?.let { Text("En büyük düşüş %${String.format(java.util.Locale.US, "%.1f", it)}", color = Nx.Soluk, fontSize = 12.sp) }
        }
    }
    item(key = "kr_hazir") {
        val h = v.hazirlik
        NeonKart(Modifier.fillMaxWidth().clickable { git("hazir") }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Gerçek para hazırlığı", color = Nx.Metin, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(h?.optString("aciklama") ?: "Karne sunucudan bekleniyor", color = Nx.Soluk, fontSize = 12.sp, lineHeight = 16.sp)
                }
                if (h != null) Text("${h.optInt("gecen")}/${h.optInt("toplam")}", color = Nx.Nane, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
    item(key = "kr_kanit") { KanitKarti(v) }
    item(key = "kr_yon") { YonlendiriciKarti(v) }
    item(key = "kr_strateji") { StratejiKarti(v) }
    item(key = "kr_borsa") { BorsaKarti(v) }
    item(key = "kr_yz") { AiCekirdekKarti(v.yz, v.modelFiltre) }
    item(key = "kr_not") {
        BilgiKutusu("Tüm sonuçlar sanal (paper) işlemlerdir; gerçek para kullanılmaz. Geçmiş sonuçlar gelecekteki kazancı garanti etmez. Gerçek işlem yalnızca kullanıcının kendi hesabında, kendi onayıyla açılır.")
    }
}
