package com.nexora.app

import android.content.SharedPreferences
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Star as YildizBos
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import java.util.Locale

// ------------------------------------------------------------------ ortak parçalar

fun kisaSayi(x: Double?): String = when {
    x == null -> "—"
    x >= 1e9 -> String.format(Locale.US, "%.2fB", x / 1e9)
    x >= 1e6 -> String.format(Locale.US, "%.1fM", x / 1e6)
    x >= 1e3 -> String.format(Locale.US, "%.1fK", x / 1e3)
    else -> String.format(Locale.US, "%.0f", x)
}

fun degisimMetni(x: Double?): String = if (x == null) "—" else (if (x >= 0) "▲ +" else "▼ ") + String.format(Locale.US, "%.2f%%", x)

@Composable
fun DemoHap() {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Column(Modifier.clip(RoundedCornerShape(14.dp)).border(1.5.dp, Nx.Mor, RoundedCornerShape(14.dp))
            .background(Nx.Kahraman.copy(alpha = 0.6f)).padding(horizontal = 18.dp, vertical = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text("▣ DEMO / PAPER TRADING", color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            Text("Gerçek işlem içermez", color = Nx.Soluk, fontSize = 11.sp)
        }
    }
}

@Composable
fun BilgiKutusu(metin: String) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2).border(1.dp, Nx.Cizgi, RoundedCornerShape(14.dp))
        .padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Outlined.Info, null, tint = Nx.Metin, modifier = Modifier.size(20.dp))
        Text(metin, color = Nx.Soluk, fontSize = 12.sp, lineHeight = 16.sp)
    }
}

@Composable
fun Hap(metin: String, secili: Boolean, modifier: Modifier = Modifier, secRenk: Color = Nx.MorKoyu, tikla: () -> Unit) {
    Box(modifier.tiklaZipla(tikla = tikla).clip(RoundedCornerShape(50)).background(if (secili) secRenk else Nx.Yuzey2)
        .padding(horizontal = 14.dp, vertical = 9.dp), contentAlignment = Alignment.Center) {
        Text(metin, color = if (secili) Nx.UstMetin else Nx.Soluk, fontSize = 13.sp, fontWeight = if (secili) FontWeight.SemiBold else FontWeight.Normal,
             maxLines = 1)
    }
}

@Composable
fun SayfaBasligi(baslik: String, alt: String, ikon: @Composable (() -> Unit)? = null, geri: (() -> Unit)? = null,
                 sag: @Composable (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (geri != null) IconButton(geri) { Icon(Icons.Filled.ArrowBack, "Geri", tint = Nx.Metin) }
        if (ikon != null) ikon()
        Column(Modifier.weight(1f)) {
            Text(baslik, color = Nx.Metin, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text(alt, color = Nx.Soluk, fontSize = 13.sp)
        }
        if (sag != null) sag()
    }
}

@Composable
fun Adim(baslik: String, deger: String, azalt: () -> Unit, artir: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(baslik, color = Nx.Metin, fontSize = 14.sp, modifier = Modifier.weight(1f))
        Row(Modifier.clip(RoundedCornerShape(12.dp)).background(Nx.Yuzey2), verticalAlignment = Alignment.CenterVertically) {
            IconButton(azalt, Modifier.size(40.dp)) { Text("−", color = Nx.Metin, fontSize = 20.sp) }
            Text(deger, color = Nx.Metin, fontSize = 14.sp, modifier = Modifier.widthIn(min = 52.dp), maxLines = 1)
            IconButton(artir, Modifier.size(40.dp)) { Icon(Icons.Filled.Add, "Artır", tint = Nx.Metin) }
        }
    }
}

/** Değer eğrisinden belirli bir andaki değer (o andan önceki son nokta; yoksa başlangıç). */
fun degerAni(noktalar: List<Nokta2>, ts: Double, baslangic: Double): Double =
    noktalar.lastOrNull { it.ts <= ts }?.deger ?: baslangic

private val ARALIKLAR = listOf("1S" to 3600.0, "4S" to 14400.0, "1G" to 86400.0, "7G" to 604800.0, "30G" to 2592000.0)

// ------------------------------------------------------------------ Ana Sayfa

/** Nexo'nun ifadesi, duruşu ve söylediği: bot durumu ve son 24 saatin sonucuna göre. */
fun nexoDurum(v: Veri, d24: Double, kz24: Double): Triple<NexoIfade, NexoPoz, String> {
    val saat = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
    val selam = when (saat) { in 5..11 -> "Günaydın!"; in 12..17 -> "İyi günler!"; in 18..22 -> "İyi akşamlar!"; else -> "Gece nöbetindeyim." }
    val cz = v.takipCuzdanlar.count { it.durum == "aktif" }
    val poz = v.pozisyonlar.size
    return when {
        v.acilDurdurma -> Triple(NexoIfade.UYKU, NexoPoz.SERBEST, "Bot durduruldu, biraz kestiriyorum. Başlatınca hemen nöbete dönerim.")
        d24 > 0.5 -> Triple(NexoIfade.SEVINC, NexoPoz.SEVINC, "Bugün ${isaretli(kz24)} USDC öndeyiz! $poz pozisyonu yakından izliyorum.")
        d24 < -0.5 -> Triple(NexoIfade.ENDISE, NexoPoz.SERBEST, "Bugün biraz geri düştük (${isaretli(kz24)} USDC). Risk sınırları devrede, sakinim.")
        else -> Triple(NexoIfade.GULUS, NexoPoz.SELAM, "$selam $cz öncü cüzdanın her hamlesini yapay zekâ ile tartıyorum" + (if (poz > 0) "; $poz pozisyon açık." else "; uygun sinyal bekliyorum."))
    }
}

fun LazyListScope.anaSayfa(v: Veri, gizle: Boolean, gizleDegis: () -> Unit, aralik: String, aralikSec: (String) -> Unit,
                           git: (String) -> Unit, eko: String, ekoSec: (String) -> Unit, bilgi: (String) -> Unit,
                           durdurIste: () -> Unit = {}) {
    item(key = "eko") { EkosistemSecici(eko, ekoSec, bilgi) }
    item(key = "nexo") {
        val simdi = System.currentTimeMillis() / 1000.0
        val ref = degerAni(v.gecmis, simdi - 86400, v.baslangic)
        val (ifade, poz, metin) = nexoDurum(v, if (ref > 0) (v.toplam - ref) / ref * 100 else 0.0, v.toplam - ref)
        NexoKonusuyor(metin, ifade, Modifier.fillMaxWidth(), poz = poz)
    }
    item(key = "demo") { DemoHap() }
    item(key = "bugun") { BugunKarti(v, durdurIste) { git("portfoy") } }
    item(key = "bakiye") {
        val simdi = System.currentTimeMillis() / 1000.0
        // 24 saatten eski veri yoksa değişim başlangıca göre gösterilir (etiket de buna göre değişir)
        val eskiVar = v.gecmis.isNotEmpty() && v.gecmis.first().ts <= simdi - 86400
        val ref24 = if (eskiVar) degerAni(v.gecmis, simdi - 86400, v.baslangic) else v.baslangic
        val d24 = if (ref24 > 0) (v.toplam - ref24) / ref24 * 100 else 0.0
        val sure = ARALIKLAR.first { it.first == aralik }.second
        val bas = degerAni(v.gecmis, simdi - sure, v.baslangic)
        val pencere = listOf(Nokta2(simdi - sure, bas)) + v.gecmis.filter { it.ts > simdi - sure }
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.Kenar, dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("SANAL PORTFÖY DEĞERİ", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                IconButton(gizleDegis, Modifier.size(28.dp)) {
                    Icon(if (gizle) Icons.Filled.Lock else Icons.Filled.Search, "Gizle", tint = Nx.Soluk, modifier = Modifier.size(18.dp))
                }
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Box(Modifier.weight(1f)) {
                    if (gizle) Text("•••••• USDC", color = Nx.Metin, fontSize = 32.sp, fontWeight = FontWeight.Bold)
                    else SayanSayi(v.toplam, { "${usd(it)} USDC" }) { Text(it, color = Nx.Metin, fontSize = 32.sp, fontWeight = FontWeight.Bold) }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(degisimMetni(d24), color = kzRenk(d24), fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Text(if (eskiVar) "son 24 saat" else "başlangıçtan", color = Nx.Soluk, fontSize = 11.sp)
                }
            }
            Row(Modifier.fillMaxWidth()) {
                Column(Modifier.weight(1f)) {
                    Text("Nakit", color = Nx.Soluk, fontSize = 12.sp)
                    Text(if (gizle) "••••" else "${usd(v.nakit)} USDC", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                }
                Column(Modifier.weight(1f)) {
                    Text("Pozisyonlarda (${v.pozisyonlar.size})", color = Nx.Soluk, fontSize = 12.sp)
                    Text(if (gizle) "••••" else "${usd(v.toplam - v.nakit)} USDC", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Toplam K/Z", color = Nx.Soluk, fontSize = 12.sp)
                    Text(if (gizle) "••••" else isaretli(v.kz), color = kzRenk(v.kz), fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                }
            }
            DegerGrafigi(pencere, bas, Modifier.fillMaxWidth().height(150.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ARALIKLAR.forEach { (ad, _) -> Hap(ad, ad == aralik, Modifier.weight(1f)) { aralikSec(ad) } }
            }
        }
    }
    item(key = "ekosistem") { EkosistemOzeti(v) { git("karne") } }
}

@Composable
fun Kisayol2(baslik: String, alt: String, ikon: @Composable () -> Unit, modifier: Modifier, tikla: () -> Unit) {
    Column(modifier.belir().tiklaZipla(tikla = tikla).clip(RoundedCornerShape(18.dp)).background(Nx.Yuzey.copy(alpha = 0.92f))
        .border(1.dp, Nx.Cizgi, RoundedCornerShape(18.dp)).padding(vertical = 12.dp, horizontal = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        ikon()
        Text(baslik, color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        Text(alt, color = Nx.Soluk, fontSize = 11.sp, maxLines = 1)
    }
}

// ------------------------------------------------------------------ Keşfet: Token Radar

/** Solana dışı ekosistemlerde radar ve sinyal verisi yok: karışık göstermek yerine açıklama. */
fun ekosistemKapsamDisi(eko: String): Boolean = eko != "tumu" && eko != "solana"

fun LazyListScope.tokenRadar(v: Veri, arama: String, aramaDegis: (String) -> Unit, sirala: Int, siralaSec: (Int) -> Unit,
                             favoriler: Set<String>, favoriDegis: (String) -> Unit, tokenSec: (RadarToken) -> Unit, eko: String = "tumu") {
    if (ekosistemKapsamDisi(eko)) {
        item(key = "radar_eko") { BilgiKutusu("Token radarı şimdilik yalnızca Solana öncü cüzdanlarından beslenir. Bu ekosistemin sonuçları için Karne sekmesine bakın.") }
        return
    }
    item(key = "radar_bas") {
        SayfaBasligi("Token Radar", "Takip edilen cüzdanların aldığı token'lar", ikon = { NexoYuz(48.dp, NexoIfade.MERAK) })
    }
    item(key = "radar_ara") {
        OutlinedTextField(arama, aramaDegis, placeholder = { Text("Token ara… (sembol, ad ya da adres)") }, singleLine = true,
            leadingIcon = { Icon(Icons.Filled.Search, null) }, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth())
    }
    item(key = "radar_hap") {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("Trend", "Yeni", "Hacim", "Favoriler ★").forEachIndexed { i, ad -> Hap(ad, sirala == i, Modifier.weight(1f)) { siralaSec(i) } }
        }
    }
    val a = arama.trim().lowercase()
    var liste = v.radar.filter { a.isEmpty() || it.sembol.lowercase().contains(a) || it.ad.lowercase().contains(a) || it.token.lowercase() == a }
    liste = when (sirala) {
        1 -> liste.sortedByDescending { it.ilk }
        2 -> liste.sortedByDescending { it.hacim ?: 0.0 }
        3 -> liste.filter { it.token in favoriler }
        else -> liste.sortedWith(compareByDescending<RadarToken> { it.cuzdan }.thenByDescending { it.alim })
    }
    if (liste.isEmpty()) item(key = "radar_bos") {
        Text(if (sirala == 3) "Favori token yok: listede yıldıza dokunarak ekleyin." else "Son 24 saatte sinyal yok.", color = Nx.Soluk, fontSize = 13.sp)
    }
    items(liste, key = { "r_" + it.token }) { t -> RadarSatiri(t, t.token in favoriler, { favoriDegis(t.token) }) { tokenSec(t) } }
    item(key = "radar_ozet") {
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                IkonRadar(Nx.Camgobegi, 36.dp)
                Column {
                    Text("Radar Özeti", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                    Text(v.radarOzet.ifEmpty { "Veri bekleniyor." }, color = Nx.Soluk, fontSize = 12.sp)
                }
            }
        }
    }
}

private val AVATAR = listOf(Color(0xFF3B82F6), Color(0xFF8B5CF6), Color(0xFFEF4444), Color(0xFF22C55E), Color(0xFFF59E0B), Color(0xFF06B6D4), Color(0xFFEC4899))

@Composable
fun RadarSatiri(t: RadarToken, favori: Boolean, favoriDegis: () -> Unit, tikla: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).clickable(onClick = tikla).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        val renk = AVATAR[(t.token.hashCode() and 0x7fffffff) % AVATAR.size]
        Box(Modifier.size(42.dp).clip(CircleShape).background(renk.copy(alpha = 0.85f)), contentAlignment = Alignment.Center) {
            Text(t.sembol.take(3).uppercase(), color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(t.sembol, color = Nx.Metin, fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (t.kopyalandi) Text("  kopyalandı", color = Nx.Yesil, fontSize = 10.sp)
            }
            Text("${t.ad.ifEmpty { kisa(t.token) }} · ${t.cuzdan} cüzdan, ${t.alim} alım", color = Nx.Soluk, fontSize = 11.sp,
                 maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(degisimMetni(t.degisim), color = if (t.degisim == null) Nx.Soluk else kzRenk(t.degisim), fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Text("Hacim: ${kisaSayi(t.hacim)}", color = Nx.Soluk, fontSize = 11.sp)
        }
        IconButton(favoriDegis, Modifier.size(32.dp)) {
            Icon(if (favori) Icons.Filled.Star else Icons.Outlined.YildizBos, "Favori", tint = if (favori) Nx.Sari else Nx.Soluk)
        }
    }
}

// ------------------------------------------------------------------ Keşfet: Wallet DNA

fun LazyListScope.walletDna(v: Veri, adres: String, adresDegis: (String) -> Unit, yukleniyor: Boolean, sonuc: JSONObject?,
                            hata: String, analiz: () -> Unit) {
    item(key = "dna_bas") { SayfaBasligi("Wallet DNA", "Cüzdan analizi ve risk profili", ikon = { NexoYuz(48.dp, NexoIfade.DUSUN) }) }
    item(key = "dna_giris") {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(adres, adresDegis, placeholder = { Text("Cüzdan adresi (Solana)") }, singleLine = true,
                leadingIcon = { Icon(Icons.Filled.AccountBox, null) }, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth())
            Button(analiz, enabled = !yukleniyor && adres.trim().length >= 32, colors = NxButonRenk(),
                   modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) {
                Text(if (yukleniyor) "Analiz ediliyor… (10-20 sn)" else "Analiz Et", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            }
            if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
            if (v.takipCuzdanlar.isNotEmpty() && sonuc == null) {
                Text("Takip edilenlerden seç:", color = Nx.Soluk, fontSize = 12.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                    v.takipCuzdanlar.take(4).forEach { c -> Hap(kisa(c.adres), false, Modifier.weight(1f)) { adresDegis(c.adres) } }
                }
            }
        }
    }
    if (sonuc != null) item(key = "dna_sonuc") { DnaSonucu(sonuc) }
    item(key = "dna_not") { BilgiKutusu("Her yeni analiz son 200 işlemi okur (~20 Helius kredisi); günde en çok 20 analiz yapılır, sonuçlar 6 saat saklanır.") }
}

@Composable
fun DnaSonucu(s: JSONObject) {
    val puan = if (s.isNull("puan")) null else s.optInt("puan")
    val risk = s.str("risk")
    val riskRenk = when (risk) { "Düşük" -> Nx.Yesil; "Orta" -> Nx.Sari; else -> Nx.Kirmizi }
    NeonKart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Cüzdan Analizi", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Etiket(if (s.optBoolean("onbellek")) "önbellekten" else "yeni analiz", Nx.MorAcik)
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(kisa(s.str("adres")), color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Risk Profili:", color = Nx.Soluk, fontSize = 13.sp)
                    Box(Modifier.clip(RoundedCornerShape(50)).border(1.dp, riskRenk, RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 3.dp)) {
                        Text(risk, color = riskRenk, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
                Text("Karar: ${s.str("karar")}", color = kararRengi(s.str("karar")), fontSize = 13.sp)
            }
            PuanHalkasi((puan ?: 0) / 100f, if ((puan ?: 0) >= 60) Nx.Yesil else if ((puan ?: 0) >= 40) Nx.Sari else Nx.Kirmizi) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(puan?.toString() ?: "—", color = Nx.Metin, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    Text("/100 puan", color = Nx.Soluk, fontSize = 10.sp)
                }
            }
        }
        val k = s.optJSONArray("kontrol")
        if (k != null) for (i in 0 until k.length()) {
            val x = k.getJSONObject(i); val iyi = x.optBoolean("iyi")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(if (iyi) Icons.Filled.Check else Icons.Filled.Warning, null, tint = if (iyi) Nx.Yesil else Nx.Sari, modifier = Modifier.size(18.dp))
                Text("  " + x.str("ad"), color = Nx.Metin, fontSize = 14.sp, modifier = Modifier.weight(1f))
                Text(x.str("deger"), color = if (iyi) Nx.Yesil else Nx.Sari, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
    val m = s.optJSONObject("metrik") ?: JSONObject()
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            IkonDna(Nx.MorAcik, 32.dp)
            Text("Wallet DNA Değerlendirmesi", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        }
        Text(s.str("yorum"), color = Nx.Soluk, fontSize = 13.sp)
        fun d(k: String) = m.dbl(k)
        Satir("Kazanma oranı", d("kazanma_orani")?.let { yuzde(it * 100, 0) } ?: "—")
        Satir("Kâr faktörü", d("kar_faktoru")?.let { String.format(Locale.US, "%.2f", it) } ?: "—")
        Satir("İşlem başı ortalama getiri", d("ort_getiri")?.let { yuzde(it * 100) } ?: "—")
        Satir("Kapanan işlem / swap", "${m.optInt("kapanan")} / ${m.optInt("swap")}")
        Satir("Gerçekleşen K/Z", d("gerceklesen_usd")?.let { "${isaretli(it)} $" } ?: "—", kzRenk(d("gerceklesen_usd") ?: 0.0))
        Satir("En büyük düşüş", d("max_dusus_usd")?.let { "${usd(it)} $" } ?: "—")
        Text("Puan; kazanma oranı, kâr faktörü, ortalama getiri, örnek sayısı ve düşüşten hesaplanır. Yatırım tavsiyesi değildir.",
             color = Nx.Soluk, fontSize = 11.sp)
    }
}

// ------------------------------------------------------------------ Bot: AutoPilot X

private val RISK_ON_AYAR = listOf(
    "Düşük" to mapOf("max_pos_pct" to 0.02, "daily_loss_pct" to 0.015, "max_positions" to 3, "max_roundtrip_loss_pct" to 4.0),
    "Orta" to mapOf("max_pos_pct" to 0.035, "daily_loss_pct" to 0.0225, "max_positions" to 4, "max_roundtrip_loss_pct" to 5.0),
    "Yüksek" to mapOf("max_pos_pct" to 0.05, "daily_loss_pct" to 0.03, "max_positions" to 5, "max_roundtrip_loss_pct" to 6.0),
)

fun LazyListScope.autoPilot(v: Veri, geri: () -> Unit, ayarla: (JSONObject) -> Unit, baslat: () -> Unit, durdurIste: () -> Unit,
                            modelKapat: () -> Unit = {}) {
    val a = v.ayarlar
    val pos = a.optDouble("max_pos_pct", 0.05); val gunluk = a.optDouble("daily_loss_pct", 0.03); val maxp = a.optInt("max_positions", 8)
    item(key = "ap_bas") {
        SayfaBasligi("AutoPilot X", "Öncü cüzdan kopyalama botu", geri = geri,
            sag = { Icon(Icons.Outlined.Info, null, tint = Nx.Soluk) })
    }
    item(key = "ap_kahraman") {
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Nexo(92.dp, if (v.acilDurdurma) NexoIfade.UYKU else NexoIfade.ODAK, if (v.acilDurdurma) NexoPoz.SERBEST else NexoPoz.KAVUS)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("AutoPilot X", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        Etiket("PAPER", Nx.Yesil)
                    }
                    Text("Öncü cüzdanların alımlarını kopyalar; her işlem güvenlik, maliyet ve risk kontrolünden geçer.",
                         color = Nx.Soluk, fontSize = 12.sp)
                    Text(if (v.acilDurdurma) "● Durduruldu" else "● Çalışıyor", color = if (v.acilDurdurma) Nx.Kirmizi else Nx.Yesil, fontSize = 12.sp)
                }
            }
        }
    }
    item(key = "ap_tutar") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("İşlem Başına Tutar (USDC)", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).border(1.dp, Nx.Mor, RoundedCornerShape(14.dp)).padding(14.dp)) {
                Text("${usd(v.toplam * pos)}  (portföyün %${String.format(Locale.US, "%.1f", pos * 100)})", color = Nx.Metin, fontSize = 16.sp)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(0.01, 0.02, 0.03, 0.05).forEach { p ->
                    Hap("%${(p * 100).toInt()}", kotlin.math.abs(pos - p) < 1e-6, Modifier.weight(1f)) { ayarla(JSONObject().put("max_pos_pct", p)) }
                }
            }
        }
    }
    item(key = "ap_risk") {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Risk Seviyesi", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(50)).background(Nx.Yuzey2).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                RISK_ON_AYAR.forEach { (ad, m) ->
                    val secili = kotlin.math.abs(pos - (m["max_pos_pct"] as Double)) < 1e-6 && maxp == m["max_positions"] &&
                                 kotlin.math.abs(gunluk - (m["daily_loss_pct"] as Double)) < 1e-6
                    Hap(ad, secili, Modifier.weight(1f)) { ayarla(JSONObject(m)) }
                }
            }
            Adim("Günlük Zarar Sınırı", "%" + String.format(Locale.US, "%.1f", gunluk * 100),
                { ayarla(JSONObject().put("daily_loss_pct", (gunluk - 0.005).coerceAtLeast(0.005))) },
                { ayarla(JSONObject().put("daily_loss_pct", (gunluk + 0.005).coerceAtMost(0.03))) })
            Adim("Maks. Açık Pozisyon", "$maxp adet",
                { ayarla(JSONObject().put("max_positions", (maxp - 1).coerceAtLeast(1))) },
                { ayarla(JSONObject().put("max_positions", (maxp + 1).coerceAtMost(8))) })
        }
    }
    item(key = "ap_dugme") {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(baslat, enabled = v.acilDurdurma, colors = NxYesilButon(), modifier = Modifier.weight(1f).height(54.dp), shape = RoundedCornerShape(14.dp)) {
                NexoYuz(30.dp, NexoIfade.SEVINC); Text(" Başlat", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            }
            Button(durdurIste, enabled = !v.acilDurdurma, colors = NxGriButon(), modifier = Modifier.weight(1f).height(54.dp), shape = RoundedCornerShape(14.dp)) {
                NexoYuz(30.dp, NexoIfade.UYKU); Text(" Durdur", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
    item(key = "ap_model") {
        val mf = v.modelFiltre
        val acik = mf.optBoolean("acik"); val etkin = mf.optBoolean("etkin")
        NeonKart(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("Yapay Zekâ Filtresi", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                    Text(when {
                        etkin -> "Açık · model ${mf.str("model")} düşük olasılıklı sinyalleri kopyalamıyor"
                        acik -> "Açık ama model yok: filtre uygulanmıyor"
                        else -> "Kapalı · tüm uygun sinyaller kopyalanıyor. Açmak yalnızca sunucuda, gölge sınavından sonra."
                    }, color = Nx.Soluk, fontSize = 12.sp)
                }
                Etiket(if (etkin) "AÇIK" else "KAPALI", if (etkin) Nx.Mor else Nx.Soluk)
            }
            if (acik) {
                Button(modelKapat, colors = NxGriButon(), modifier = Modifier.fillMaxWidth().padding(top = 8.dp), shape = RoundedCornerShape(12.dp)) {
                    Text("Filtreyi kapat (geri al)")
                }
            }
        }
    }
    item(key = "ap_bilgi") { BilgiKutusu("DEMO MOD: Tüm işlemler sanal (paper trading) olarak çalışır. Gerçek emir gönderilmez. Sınırlar yalnızca sıkılaştırılabilir; üst değerler proje kuralıdır.") }
}

// ------------------------------------------------------------------ Portföy

fun LazyListScope.portfoy(v: Veri, geri: () -> Unit, sekme: Int, sekmeSec: (Int) -> Unit, kapat: (String) -> Unit = {}, eko: String = "tumu",
                          islemFormu: @Composable () -> Unit) {
    val poz = if (eko == "tumu") v.pozisyonlar else v.pozisyonlar.filter { it.eko == eko }
    val isl = if (eko == "tumu") v.islemler else v.islemler.filter { it.eko == eko }
    item(key = "pf_bas") { SayfaBasligi("Portföy", "Sanal portföyünü yönet", ikon = { NexoYuz(44.dp, NexoIfade.YILDIZ) }, geri = geri) }
    item(key = "pf_deger") {
        val simdi = System.currentTimeMillis() / 1000.0
        val ref = degerAni(v.gecmis, simdi - 86400, v.baslangic)
        val d24 = if (ref > 0) (v.toplam - ref) / ref * 100 else 0.0
        NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Portföy Değeri (Sanal)", color = Nx.Soluk, fontSize = 12.sp)
                    Text("${usd(v.toplam)} USDC", color = Nx.Metin, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                }
                Box(Modifier.clip(RoundedCornerShape(50)).border(1.dp, kzRenk(d24), RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 4.dp)) {
                    Text(degisimMetni(d24) + " (24s)", color = kzRenk(d24), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }
            }
            Text("Başlangıç: ${usd(v.baslangic)} USDC   |   Kâr/Zarar: ${isaretli(v.kz)} USDC", color = Nx.Soluk, fontSize = 12.sp)
            Text("Nakit ${usd(v.nakit)} + pozisyonlar ${usd(v.toplam - v.nakit)} = ${usd(v.toplam)} USDC", color = Nx.Soluk, fontSize = 12.sp)
            v.defter?.let { d ->
                val tamam = kotlin.math.abs(d.optDouble("nakit_farki", 1.0)) < 0.01 && kotlin.math.abs(d.optDouble("toplam_farki", 1.0)) < 0.01
                Text(if (tamam) "✓ Defter doğrulandı: gerçekleşen ${isaretli(d.optDouble("gerceklesen"))} − alım ücretleri ${usd(d.optDouble("alim_ucreti"))} + açık pozisyonlar ${isaretli(d.optDouble("gerceklesmemis"))}"
                     else "⚠ Defter tutarsız: nakit farkı ${d.optDouble("nakit_farki")}. Sunucuda portfoy_denetim.py çalıştırın.",
                     color = if (tamam) Nx.Yesil else Nx.Kirmizi, fontSize = 12.sp)
                val eb = d.optJSONArray("en_buyuk")
                if (eb != null && eb.length() > 0) {
                    val x = eb.getJSONObject(0)
                    Text("En büyük kapanış: ${kisa(x.str("token"))} ${isaretli(x.optDouble("pnl"))} USDC (${kisa(x.str("wallet"))})", color = Nx.Soluk, fontSize = 12.sp)
                }
                val su = d.optJSONArray("supheli")
                if (su != null && su.length() > 0) {
                    val etki = d.optDouble("supheli_kz", 0.0)
                    Text("⚠ ${su.length()} kapanış tutarsız teklifle açılmış (alışta fiyatlar çelişkiliydi): ${isaretli(etki)} USDC gerçekçi değil. " +
                         "Bunlar hariç portföy ≈ ${usd(v.toplam - etki)} USDC. Bu tür alımlar artık yapılmıyor.", color = Nx.Sari, fontSize = 12.sp)
                }
            }
        }
    }
    item(key = "pf_sekme") {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(50)).background(Nx.Yuzey2).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf("İşlem (Paper)", "Pozisyonlar (${poz.size})", "Geçmiş").forEachIndexed { i, ad -> Hap(ad, sekme == i, Modifier.weight(1f)) { sekmeSec(i) } }
        }
    }
    when (sekme) {
        0 -> item(key = "pf_form") { islemFormu() }
        1 -> {
            if (poz.isEmpty()) item(key = "pf_bos") { Text("Açık pozisyon yok.", color = Nx.Soluk) }
            items(poz, key = { "p_" + it.token }) { p -> PozisyonKarti(p) { kapat(p.token) } }
            item(key = "pf_perf") { PerformansOzeti(v) }
        }
        else -> items(isl, key = { "i_" + it.ts + it.token + it.yon }) { IslemSatiri(it) }
    }
}

@Composable
fun IslemFormu(v: Veri, secili: String, seciliDegis: (String) -> Unit, gonder: (String, String, Double?) -> Unit, sonuc: String, mesgul: Boolean) {
    var yon by remember { mutableStateOf("buy") }
    var tutar by remember { mutableStateOf("") }
    var acik by remember { mutableStateOf(false) }
    val sinir = v.toplam * v.ayarlar.optDouble("max_pos_pct", 0.05)
    val secenek = (v.pozisyonlar.map { it.token to "Açık pozisyon · ${kisa(it.token)}" } +
                   v.radar.map { it.token to "${it.sembol} · ${kisa(it.token)}" }).distinctBy { it.first }
    val ad = secenek.firstOrNull { it.first == secili }?.second ?: if (secili.isEmpty()) "Token seçin" else kisa(secili)
    val pozVar = v.pozisyonlar.any { it.token == secili }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Token", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        Box {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Nx.Yuzey2).clickable { acik = true }.padding(14.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(ad, color = Nx.Metin, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Icon(Icons.Filled.ArrowDropDown, null, tint = Nx.Soluk)
            }
            DropdownMenu(acik, { acik = false }, containerColor = Nx.Yuzey2) {
                if (secenek.isEmpty()) DropdownMenuItem({ Text("Radar boş: önce sinyal gelmeli") }, { acik = false })
                secenek.forEach { (t, etiket) -> DropdownMenuItem({ Text(etiket) }, { seciliDegis(t); acik = false }) }
            }
        }
        Text("İşlem Türü", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Hap("Al (Paper)", yon == "buy", Modifier.weight(1f), secRenk = Nx.Yesil) { yon = "buy" }
            Hap("Sat (Paper)", yon == "sell", Modifier.weight(1f), secRenk = Nx.Kirmizi) { yon = "sell" }
        }
        if (yon == "buy") {
            Text("Tutar (USDC) · en çok ${usd(sinir)}", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
            OutlinedTextField(tutar, { tutar = it.replace(',', '.') }, singleLine = true, shape = RoundedCornerShape(14.dp),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(25, 50, 75, 100).forEach { p -> Hap("%$p", false, Modifier.weight(1f)) { tutar = String.format(Locale.US, "%.2f", sinir * p / 100) } }
            }
        } else {
            Text(if (pozVar) "Pozisyonun tamamı gerçek satış teklifiyle satılır." else "Bu token'da açık pozisyon yok.", color = Nx.Soluk, fontSize = 13.sp)
        }
        Button({ gonder(secili, yon, tutar.toDoubleOrNull()) },
            enabled = !mesgul && secili.isNotEmpty() && (if (yon == "buy") (tutar.toDoubleOrNull() ?: 0.0) > 0 else pozVar),
            colors = if (yon == "buy") NxYesilButon() else ButtonDefaults.buttonColors(containerColor = Nx.Kirmizi, contentColor = Color.White),
            modifier = Modifier.fillMaxWidth().height(54.dp), shape = RoundedCornerShape(14.dp)) {
            Icon(Icons.Filled.PlayArrow, null)
            Text(if (mesgul) " Teklif alınıyor…" else if (yon == "buy") " Sanal Alış Yap (Paper)" else " Sanal Satış Yap (Paper)",
                 fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }
        if (sonuc.isNotEmpty()) Text(sonuc, color = if (sonuc.startsWith("KOPYALANDI")) Nx.Yesil else Nx.Sari, fontSize = 13.sp)
        BilgiKutusu("DEMO MOD: Bu bir kağıt işlem (paper trading) ortamıdır. Elle işlem de kopyalamayla aynı güvenlik, gerçek teklif ve risk kurallarından geçer; gerçek alım-satım yapılmaz.")
    }
}

// ------------------------------------------------------------------ Profil

fun LazyListScope.profil(v: Veri, git: (String) -> Unit, ayarlar: @Composable () -> Unit) {
    item(key = "pr_kart") {
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Column {
                    Logo(28.sp)
                    Text("Paper hesabı · gerçek işlem kapalı", color = Nx.Soluk, fontSize = 12.sp)
                    Text("Sürüm ${BuildConfig.VERSION_NAME}", color = Nx.Soluk, fontSize = 11.sp)
                }
            }
        }
    }
    item(key = "pr_menu") {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (v.kurucu) ProfilSatiri("Otomatik Pilot · Risk · Acil Durdurma", { IkonRobot(Nx.MorAcik) }) { git("bot") }
            ProfilSatiri("Hesabım · Davet · Bağlantılar", { Icon(Icons.Filled.AccountCircle, null, tint = Nx.MorAcik) }) { git("uye") }
            ProfilSatiri("Günlük Rapor", { Icon(Icons.Filled.DateRange, null, tint = Nx.MorAcik) }) { git("rapor") }
            ProfilSatiri("Yol Haritası", { Icon(Icons.Filled.List, null, tint = Nx.MorAcik) }) { git("yol") }
            if (v.kurucu) ProfilSatiri("Takip Edilen Cüzdanlar", { IkonDna(Nx.MorAcik) }) { git("takip") }
            if (v.kurucu) ProfilSatiri("Sistem Sağlığı · Canlı tutarlılık", { IkonKalkan(Nx.MorAcik) }) { git("sistem") }
            if (v.kurucu) ProfilSatiri("Hyperliquid Takibi · Yapay zekâ analizi", { IkonRobot(Nx.MorAcik) }) { git("hl") }
        }
    }
    item(key = "pr_ayar") { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { ayarlar() } }
}

@Composable
fun ProfilSatiri(baslik: String, ikon: @Composable () -> Unit, tikla: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Nx.Yuzey).border(1.dp, Nx.Cizgi, RoundedCornerShape(16.dp))
        .clickable(onClick = tikla).padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        ikon()
        Text(baslik, color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Text("›", color = Nx.Soluk, fontSize = 22.sp)
    }
}

// ------------------------------------------------------------------ alt menü

data class Sekme(val id: String, val ad: String, val ikon: @Composable (Color) -> Unit)

@Composable
fun AltMenu2(secili: String, sec: (String) -> Unit) {
    // Her sekmede Nexo'nun ayrı bir ifadesi: seçilen büyür, parlar ve altında ışık yanar.
    val sekmeler = listOf(
        Triple("ana", "Ana Sayfa", NexoIfade.GULUS), Triple("kesfet", "Keşfet", NexoIfade.MERAK), Triple("portfoy", "Portföy", NexoIfade.YILDIZ),
        Triple("karne", "Karne", NexoIfade.ODAK), Triple("profil", "Profil", NexoIfade.HAVALI),
    )
    Column(Modifier.fillMaxWidth().background(Nx.Zemin.copy(alpha = 0.94f))) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(Nx.KenarParlak))
        Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 6.dp)) {
            sekmeler.forEach { (id, ad, ifade) ->
                val s = id == secili
                val olcek by androidx.compose.animation.core.animateFloatAsState(if (s) 1.22f else 0.86f,
                    androidx.compose.animation.core.spring(dampingRatio = 0.42f, stiffness = 380f), label = "sekme")
                val solukluk by androidx.compose.animation.core.animateFloatAsState(if (s) 1f else 0.5f, label = "sekmeA")
                Column(Modifier.weight(1f).tiklaZipla { sec(id) }.padding(vertical = 2.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(1.dp)) {
                    NexoYuz(34.dp, ifade, Modifier.graphicsLayer { scaleX = olcek; scaleY = olcek; alpha = solukluk; translationY = if (s) -4f else 0f })
                    Text(ad, color = if (s) Nx.Nane else Nx.Soluk, fontSize = 11.sp, fontWeight = if (s) FontWeight.Bold else FontWeight.Normal, maxLines = 1)
                    Box(Modifier.size(width = if (s) 18.dp else 0.dp, height = 3.dp).clip(RoundedCornerShape(50)).background(Nx.KenarParlak))
                }
            }
        }
    }
}
