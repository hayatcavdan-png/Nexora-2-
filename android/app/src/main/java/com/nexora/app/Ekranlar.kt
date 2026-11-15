package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale

// ---------------------------------------------------------------- Ana Panel
@Composable
fun AnaPanel(v: Veri, anahtarVar: Boolean, git: (String) -> Unit, durdurIste: () -> Unit, devam: () -> Unit) {
    if (!anahtarVar) {
        NeonKart(Modifier.fillMaxWidth()) {
            Text("Sunucuya bağlanın", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Text("Ayarlar › Bağlantı bölümünden sunucu adresini ve API anahtarını girin.", color = Nx.Soluk, fontSize = 14.sp)
            Button({ git("ayarlar") }, colors = ButtonDefaults.buttonColors(containerColor = Nx.Mor)) { Text("Ayarlara git") }
        }
        return
    }
    // Bakiye kartı
    NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.size(52.dp).clip(RoundedCornerShape(14.dp)).background(Nx.Kenar), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Star, null, tint = Color.White, modifier = Modifier.size(28.dp))
            }
            Column {
                Text("Sanal bakiye (paper)", color = Nx.Soluk, fontSize = 14.sp)
                Text("${usd(v.toplam)} USDC", color = Nx.Metin, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            }
        }
        val bugunKz = v.rapor?.optJSONObject("bugun")?.optDouble("gerceklesen_kz", 0.0) ?: 0.0
        val toplamYuzde = if (v.baslangic > 0) v.kz / v.baslangic * 100 else 0.0
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MiniKutu("Bugünkü K/Z", "${isaretli(bugunKz)}", "USDC, kapanan", kzRenk(bugunKz), Modifier.weight(1f))
            MiniKutu("Toplam K/Z", isaretli(v.kz), "(${if (toplamYuzde >= 0) "+" else ""}${yuzde(toplamYuzde, 2)})", kzRenk(v.kz), Modifier.weight(1f))
            val b = v.basariOrani
            MiniKutu("Başarı oranı", if (b == null) "—" else yuzde(b), "${v.kapananlar.size} kapanan işlem", Nx.Camgobegi, Modifier.weight(1f))
        }
    }
    // Bot durumu
    NeonKart(Modifier.fillMaxWidth(), kenar = if (v.acilDurdurma) Brush.linearGradient(listOf(Nx.Kirmizi, Nx.Pembe)) else Nx.KenarYesil) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(46.dp).clip(CircleShape).background(Brush.linearGradient(listOf(Nx.Camgobegi, Nx.Mor))), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Face, null, tint = Color.White)
            }
            Column(Modifier.weight(1f)) {
                Text("NEXORA Kopyalama Botu", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Paper (sanal)", color = Nx.Soluk, fontSize = 13.sp)
                    Nokta(if (v.acilDurdurma) Nx.Kirmizi else Nx.Yesil)
                    Text(if (v.acilDurdurma) "Durduruldu" else "Aktif", color = if (v.acilDurdurma) Nx.Kirmizi else Nx.Yesil, fontSize = 13.sp)
                }
            }
            Switch(checked = !v.acilDurdurma, onCheckedChange = { acik -> if (acik) devam() else durdurIste() },
                colors = SwitchDefaults.colors(checkedTrackColor = Nx.Yesil, uncheckedTrackColor = Nx.Kirmizi.copy(alpha = 0.5f)))
        }
    }
    // Kısayollar
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Kisayol("Akıllı\nCüzdanlar", Icons.Filled.Person, Modifier.weight(1f)) { git("cuzdanlar") }
        Kisayol("Günlük\nRapor", Icons.Filled.DateRange, Modifier.weight(1f)) { git("rapor") }
        Kisayol("Yol\nHaritası", Icons.Filled.Star, Modifier.weight(1f)) { git("yol") }
        Kisayol("Sistem\nDurumu", Icons.Filled.Build, Modifier.weight(1f)) { git("sinyaller") }
    }
    // Performans
    Kart(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Portföy performansı", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, modifier = Modifier.weight(1f))
            val yz = if (v.baslangic > 0) v.kz / v.baslangic * 100 else 0.0
            Etiket((if (yz >= 0) "+" else "") + yuzde(yz, 2), kzRenk(v.kz))
        }
        DegerGrafigi(v.gecmis, v.baslangic, Modifier.fillMaxWidth())
        Text("Kesikli çizgi: başlangıç sermayesi (${usd(v.baslangic)} USDC)", color = Nx.Soluk, fontSize = 11.sp)
    }
    // Canlı takip
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(42.dp).clip(CircleShape).background(Brush.linearGradient(listOf(Nx.Mor, Nx.Camgobegi))), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Notifications, null, tint = Color.White)
            }
            Column(Modifier.weight(1f)) {
                val aktif = v.takipCuzdanlar.count { it.durum == "aktif" }
                Text("Canlı takip: $aktif cüzdan", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                Text(if (v.gecikmeP50 == null) "henüz anlık sinyal yok"
                     else "Sinyal gecikmesi ${v.gecikmeP50!!.toInt()} sn (P95 ${v.gecikmeP95?.toInt() ?: 0} sn)", color = Nx.Soluk, fontSize = 13.sp)
            }
            Etiket("${v.pozisyonlar.size} açık", Nx.Camgobegi)
        }
    }
}

@Composable
fun MiniKutu(baslik: String, deger: String, alt: String, renk: Color, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(Nx.Zemin.copy(alpha = 0.6f)).border(1.dp, Nx.Cizgi, RoundedCornerShape(14.dp)).padding(10.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text(baslik, color = Nx.Soluk, fontSize = 12.sp, maxLines = 1)
        Text(deger, color = renk, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 1)
        Text(alt, color = renk.copy(alpha = 0.8f), fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun Kisayol(metin: String, ikon: ImageVector, modifier: Modifier, tikla: () -> Unit) {
    Column(modifier.clip(RoundedCornerShape(16.dp)).background(Nx.DolguMor).border(1.dp, Nx.Kenar, RoundedCornerShape(16.dp))
        .clickable(onClick = tikla).padding(vertical = 12.dp, horizontal = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Icon(ikon, null, tint = Nx.Camgobegi, modifier = Modifier.size(26.dp))
        Text(metin, color = Nx.Metin, fontSize = 12.sp, lineHeight = 14.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
    }
}

// ---------------------------------------------------------------- Bot / Sinyaller
@Composable
fun BotEkrani(v: Veri, durdurIste: () -> Unit, devam: () -> Unit) {
    NeonKart(Modifier.fillMaxWidth()) {
        Text("Bot çalışma zinciri", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
        listOf("Canlı cüzdan takibi (anlık)", "Swap çözme ve stablecoin filtresi", "Token güvenliği (basım/dondurma yetkisi)",
               "Gerçek Jupiter teklifi ve al-sat maliyeti", "Risk kuralları ve paper işlem").forEach {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Filled.CheckCircle, null, tint = Nx.Yesil, modifier = Modifier.size(18.dp))
                Text(it, color = Nx.Metin, fontSize = 14.sp)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.Info, null, tint = Nx.Soluk, modifier = Modifier.size(18.dp))
            Text("Yapay zekâ (Grok) sosyal filtresi: yakında", color = Nx.Soluk, fontSize = 14.sp)
        }
    }
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Nokta(if (v.acilDurdurma) Nx.Kirmizi else Nx.Yesil)
            Column(Modifier.weight(1f)) {
                Text("Bot durumu", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                Text(if (v.acilDurdurma) "Durduruldu: yeni alım yapılmıyor" else "Çalışıyor (paper)",
                     color = if (v.acilDurdurma) Nx.Kirmizi else Nx.Yesil, fontSize = 13.sp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(durdurIste, enabled = !v.acilDurdurma, modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = Nx.Kirmizi)) { Text("ACİL DURDUR") }
            OutlinedButton(devam, enabled = v.acilDurdurma, modifier = Modifier.weight(1f)) { Text("Devam ettir", color = Nx.Camgobegi) }
        }
    }
    Kart(Modifier.fillMaxWidth()) {
        Text("Strateji ayarları", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        val a = v.ayarlar
        Satir("İşlem modu", "Paper (sanal)")
        Satir("Başlangıç sermayesi", "${usd(a.optDouble("start_cash", 100.0))} USDC")
        Satir("İşlem başına risk", yuzde(a.optDouble("max_pos_pct", 0.05) * 100))
        Satir("En fazla açık pozisyon", a.optInt("max_positions", 5).toString())
        Satir("Cüzdan başına pozisyon", a.optInt("max_positions_per_wallet", 2).toString())
        Satir("Günlük zarar sınırı", yuzde(a.optDouble("daily_loss_pct", 0.03) * 100))
        Satir("Al-sat kaybı sınırı", yuzde(a.optDouble("max_roundtrip_loss_pct", 6.0)))
        Satir("Sinyal tazelik sınırı", "${a.optInt("max_signal_age_s", 10)} sn")
        Text("Ayarları uygulamadan değiştirme: yakında", color = Nx.Soluk, fontSize = 12.sp)
    }
    Baslik("Son sinyaller", if (v.gecikmeP50 == null) null else "${v.gecikmeN} anlık sinyal · P50 ${v.gecikmeP50!!.toInt()} sn · P95 ${v.gecikmeP95?.toInt() ?: 0} sn")
}

@Composable
fun SinyalKarti(s: Sinyal) {
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Etiket(if (s.yon == "BUY") "ALIM" else "SATIM", if (s.yon == "BUY") Nx.Camgobegi else Nx.Pembe)
            Text(kisa(s.token), color = Nx.Metin, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text(saat(s.ts), color = Nx.Soluk, fontSize = 12.sp)
        }
        Text("Cüzdan ${kisa(s.cuzdan)} · ${s.gecikme.toInt()} sn · ${if (s.kaynak == "ws") "anlık" else "yoklama"}", color = Nx.Soluk, fontSize = 12.sp)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Etiket(s.karar, kararRengi(s.karar))
            Text(s.neden, color = Nx.Metin, fontSize = 13.sp, modifier = Modifier.weight(1f))
        }
    }
}

// ---------------------------------------------------------------- Cüzdanlar
@Composable
fun CuzdanOzeti(v: Veri) {
    val o = v.cuzdanOzet
    NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Sayac("Taranan", o.optInt("taranan").toString())
            Sayac("Analiz", o.optInt("analiz").toString())
            Sayac("Kopyalanabilir", o.optInt("kopyalanabilir").toString(), Nx.Yesil)
            Sayac("Kara liste", o.optInt("kara_liste").toString(), Nx.Kirmizi)
        }
        Text("Sıralama, son 200 işlemin gerçekleşmiş kârlılığına göre. Kaynak cüzdanın getirisi bizim getirimiz değildir; aşağıdaki \"paper\" satırı bizim sonucumuzdur.",
             color = Nx.Soluk, fontSize = 12.sp)
    }
}

@Composable
fun Sayac(ad: String, deger: String, renk: Color = Nx.Metin) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(deger, color = renk, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(ad, color = Nx.Soluk, fontSize = 11.sp)
    }
}

@Composable
fun CuzdanKarti(sira: Int, c: CuzdanSatiri) {
    val madalya = when (sira) { 1 -> Color(0xFFFACC15); 2 -> Color(0xFFCBD5E1); 3 -> Color(0xFFF59E0B); else -> Nx.Soluk }
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(30.dp).clip(CircleShape).border(1.5.dp, madalya, CircleShape), contentAlignment = Alignment.Center) {
                Text("$sira", color = madalya, fontWeight = FontWeight.Bold, fontSize = 13.sp)
            }
            Text(kisa(c.adres), color = Nx.Metin, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket(c.durum, kararRengi(c.durum))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Mini("Kazanma", c.kazanma?.let { yuzde(it * 100, 0) } ?: "—")
            Mini("Kâr faktörü", c.karFaktoru?.let { String.format(Locale.US, "%.2f", it) } ?: "—")
            Mini("İşlem başı", c.ortGetiri?.let { yuzde(it * 100, 0) } ?: "—")
            Mini("Tutma", c.tutmaSn?.let { sureMetni(it) } ?: "—")
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Etiket(c.karar, kararRengi(c.karar))
            Text("kaynak K/Z ${c.kaynakKz?.let { isaretli(it) } ?: "—"} $", color = Nx.Soluk, fontSize = 12.sp)
        }
        Text("Paper: ${c.paperKopyalanan} kopyalandı · ${c.paperKapanan} kapandı · ${c.paperAcik} açık · K/Z ${isaretli(c.paperKz)} USDC",
             color = kzRenk(c.paperKz).takeIf { c.paperKapanan > 0 } ?: Nx.Soluk, fontSize = 12.sp)
        if (c.takipTur > 0) {
            fun p(x: Double?) = x?.let { (if (it >= 0) "+" else "") + yuzde(it * 100) } ?: "—"
            val kotu = (c.takipGiris ?: 0.0) + (c.takipCikis ?: 0.0) > 0.10
            Text("Takip kaybı (${c.takipTur} tur): giriş ${p(c.takipGiris)} · çıkış ${p(c.takipCikis)}",
                 color = if (kotu) Nx.Sari else Nx.Soluk, fontSize = 12.sp)
            Text("Kaynak ortalama ${p(c.takipKaynak)} · bizim ortalama ${p(c.takipBizim)}", color = Nx.Soluk, fontSize = 12.sp)
        }
    }
}

fun sureMetni(sn: Int): String = when {
    sn < 120 -> "$sn sn"
    sn < 7200 -> "${sn / 60} dk"
    sn < 172800 -> "${sn / 3600} sa"
    else -> "${sn / 86400} gün"
}

@Composable
fun Mini(ad: String, deger: String) {
    Column {
        Text(ad, color = Nx.Soluk, fontSize = 11.sp)
        Text(deger, color = Nx.Metin, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

// ---------------------------------------------------------------- İşlemler
@Composable
fun PerformansOzeti(v: Veri) {
    val k = v.kapananlar
    NeonKart(Modifier.fillMaxWidth()) {
        Text("Performans özeti", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
        Satir("Kapanan işlem", k.size.toString())
        Satir("Kârlı işlem", k.count { it.kz > 0 }.toString(), Nx.Yesil)
        Satir("Zararlı işlem", k.count { it.kz <= 0 }.toString(), Nx.Kirmizi)
        Satir("Başarı oranı", v.basariOrani?.let { yuzde(it) } ?: "—")
        Satir("Gerçekleşen K/Z", "${isaretli(k.sumOf { it.kz })} USDC", kzRenk(k.sumOf { it.kz }))
        Satir("Toplam K/Z (açıklar dahil)", "${isaretli(v.kz)} USDC", kzRenk(v.kz))
    }
}

@Composable
fun PozisyonKarti(p: Pozisyon) {
    val kz = p.deger - p.maliyet
    val yz = if (p.maliyet > 0) kz / p.maliyet * 100 else 0.0
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(40.dp).clip(CircleShape).background(Brush.linearGradient(listOf(Nx.Mor, Nx.Camgobegi))), contentAlignment = Alignment.Center) {
                Text(p.token.take(1), color = Color.White, fontWeight = FontWeight.Bold)
            }
            Column(Modifier.weight(1f)) {
                Text("${kisa(p.token)} / USDC", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                Text("Uzun (paper) · ${kisa(p.cuzdan)}", color = Nx.Soluk, fontSize = 12.sp)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("${isaretli(kz)} USDC", color = kzRenk(kz), fontWeight = FontWeight.SemiBold)
                Text((if (yz >= 0) "+" else "") + yuzde(yz, 2), color = kzRenk(kz), fontSize = 12.sp)
            }
        }
        Text("Maliyet ${usd(p.maliyet)} → güncel değer ${usd(p.deger)} USDC", color = Nx.Soluk, fontSize = 12.sp)
    }
}

@Composable
fun IslemSatiri(i: Islem) {
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Etiket(if (i.yon == "buy") "ALIM" else "SATIM", if (i.yon == "buy") Nx.Camgobegi else Nx.Pembe)
            Text(kisa(i.token), color = Nx.Metin, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            if (i.karar == "KOPYALANDI" && i.yon == "sell") Text("${isaretli(i.kz)} USDC", color = kzRenk(i.kz), fontWeight = FontWeight.SemiBold)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Etiket(i.karar, kararRengi(i.karar))
            Text("${gunAy(i.ts)} ${saat(i.ts)}", color = Nx.Soluk, fontSize = 12.sp)
        }
        Text(i.neden, color = Nx.Soluk, fontSize = 13.sp)
    }
}

// ---------------------------------------------------------------- Rapor
@Composable
fun RaporEkrani(v: Veri) {
    val r = v.rapor
    if (r == null || !r.optBoolean("hazir", false)) {
        Kart(Modifier.fillMaxWidth()) {
            Text(r?.str("mesaj")?.ifEmpty { null } ?: "Rapor alınamadı (sunucu güncel olmayabilir).", color = Nx.Soluk)
        }
        return
    }
    val b = r.getJSONObject("bugun")
    NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
        Text("Bugün · ${r.str("gun")}", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Sayac("Karar", b.optInt("karar").toString())
            Sayac("Kopyalanan", b.optInt("kopyalanan_alim").toString(), Nx.Yesil)
            Sayac("Kapanan", b.optInt("kapanan").toString(), Nx.Camgobegi)
            Sayac("Red", b.optInt("reddedilen").toString(), Nx.Kirmizi)
        }
        val kz = b.optDouble("gerceklesen_kz", 0.0)
        Satir("Kapanan işlemlerin K/Z", "${isaretli(kz)} USDC", kzRenk(kz))
    }
    val gr = b.getJSONArray("red_gerekceleri")
    if (gr.length() > 0) Kart(Modifier.fillMaxWidth()) {
        Text("En sık red gerekçeleri", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        val enCok = (0 until gr.length()).maxOf { gr.getJSONObject(it).optInt("adet") }.coerceAtLeast(1)
        for (i in 0 until gr.length()) {
            val x = gr.getJSONObject(i)
            Text(x.str("gerekce"), color = Nx.Metin, fontSize = 13.sp)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                LinearProgressIndicator(progress = { x.optInt("adet").toFloat() / enCok }, modifier = Modifier.weight(1f).height(6.dp),
                    color = Nx.Mor, trackColor = Nx.Cizgi)
                Text("${x.optInt("adet")}", color = Nx.Soluk, fontSize = 12.sp)
            }
        }
    }
    val go = r.getJSONObject("golge"); val gg = go.getJSONArray("gruplar")
    Kart(Modifier.fillMaxWidth()) {
        Text("Gölge işlemler", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        Text("Maliyet nedeniyle reddedilen alımlara girseydik ne olurdu: kaynak cüzdan sattığında gerçek teklifle hesaplanır.",
             color = Nx.Soluk, fontSize = 12.sp)
        Satir("Toplam / açık", "${go.optInt("toplam")} / ${go.optInt("acik")}")
        for (i in 0 until gg.length()) {
            val x = gg.getJSONObject(i)
            Satir("${x.str("grup")} (${x.optInt("kapanan")} kapanan)", "${isaretli(x.optDouble("toplam_kz", 0.0))} $", kzRenk(x.optDouble("toplam_kz", 0.0)))
        }
        Text("20 kapanan örnekten önce eşik kararı verilmez.", color = Nx.Soluk, fontSize = 11.sp)
    }
    val z = r.optJSONObject("zarar_kesme")
    if (z != null) Kart(Modifier.fillMaxWidth()) {
        Text("Zarar kesme ölçümü", color = Nx.Metin, fontWeight = FontWeight.SemiBold)
        Text("Kopyalanan pozisyon eşik kadar zarara düştüğünde satsaydık ne olurdu? Yalnızca ölçüm; işlem kuralı değişmedi.",
             color = Nx.Soluk, fontSize = 12.sp)
        val gercek = z.optDouble("gercek_kz", 0.0)
        Satir("Kapanan / açık pozisyon", "${z.optInt("kapanan")} / ${z.optInt("acik")}")
        Satir("Gerçekleşen K/Z", "${isaretli(gercek)} $", kzRenk(gercek))
        val es = z.optJSONArray("esikler")
        if (es != null) for (i in 0 until es.length()) {
            val x = es.getJSONObject(i)
            val fark = x.optDouble("fark", 0.0)
            Satir("%${x.optInt("esik")} zarar kes · ${x.optInt("tetiklenen")} tetik (${x.optInt("korudu")} korudu, ${x.optInt("kacirdi")} kaçırdı)",
                  "${isaretli(fark)} $", kzRenk(fark))
        }
        Text("Sağdaki değer, gerçekleşene göre fark. 20 kapanan pozisyondan önce karar verilmez.", color = Nx.Soluk, fontSize = 11.sp)
    }
}

// ---------------------------------------------------------------- Yol haritası
@Composable
fun AsamaKarti(a: Asama) {
    val renk = kararRengi(a.durum)
    val durumMetni = when (a.durum) { "ileri" -> "İleri aşamada"; "devam" -> "Devam ediyor"; else -> "Başlamadı" }
    val vurgulu = a.durum == "devam"
    val sekil = RoundedCornerShape(16.dp)
    Column(Modifier.fillMaxWidth().clip(sekil).background(if (vurgulu) Nx.DolguMor else Brush.linearGradient(listOf(Nx.Yuzey, Nx.Yuzey)))
        .border(1.dp, if (vurgulu) Nx.Kenar else Brush.linearGradient(listOf(Nx.Cizgi, Nx.Cizgi)), sekil).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(if (a.durum == "baslamadi") Icons.Filled.Lock else Icons.Filled.CheckCircle, null, tint = renk, modifier = Modifier.size(22.dp))
            Column(Modifier.weight(1f)) {
                Text("${a.kod} · ${a.ad}", color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            }
            Etiket(durumMetni, renk)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LinearProgressIndicator(progress = { a.yuzde / 100f }, modifier = Modifier.weight(1f).height(6.dp), color = renk, trackColor = Nx.Cizgi)
            Text(yuzde(a.yuzde.toDouble(), 0), color = Nx.Metin, fontSize = 12.sp)
        }
        Text("Yapılan: ${a.yapilan}", color = Nx.Soluk, fontSize = 12.sp)
        if (a.eksik.isNotEmpty()) Text("Eksik: ${a.eksik}", color = Nx.Soluk, fontSize = 12.sp)
    }
}

// ---------------------------------------------------------------- Ayarlar
@Composable
fun AyarlarEkrani(v: Veri, url: String, key: String, bildirim: Boolean, bildirimDegis: (Boolean) -> Unit,
                  kaydet: (String, String) -> Unit) {
    var u by remember(url) { mutableStateOf(url) }
    var k by remember(key) { mutableStateOf(key) }
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(Icons.Filled.Settings, null, tint = Nx.Camgobegi)
            Text("Sunucu bağlantısı", color = Nx.Metin, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket(if (v.bagli) "bağlı" else "bağlı değil", if (v.bagli) Nx.Yesil else Nx.Kirmizi)
        }
        OutlinedTextField(u, { u = it }, label = { Text("Sunucu adresi") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(k, { k = it }, label = { Text("API anahtarı") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation())
        Button({ kaydet(u.trim(), k.trim()) }, colors = ButtonDefaults.buttonColors(containerColor = Nx.Mor), modifier = Modifier.fillMaxWidth()) {
            Text("Kaydet ve bağlan")
        }
        if (v.eksikUclar.isNotEmpty()) Text("Sunucu eski sürümde olabilir; okunamayan: ${v.eksikUclar.joinToString()}", color = Nx.Sari, fontSize = 12.sp)
    }
    Kart(Modifier.fillMaxWidth()) {
        AyarSatiri(Icons.Filled.Warning, "Risk yönetimi", "Bot ekranında görüntülenir · değiştirme yakında")
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(Icons.Filled.Notifications, null, tint = Nx.Mor)
            Column(Modifier.weight(1f)) {
                Text("Bildirimler", color = Nx.Metin, fontSize = 15.sp)
                Text("Kopyalanan alım, kapanan pozisyon, zarar sınırı, bot uyarısı · 30 sn'de bir kontrol",
                     color = Nx.Soluk, fontSize = 12.sp)
            }
            Switch(checked = bildirim, onCheckedChange = bildirimDegis,
                colors = SwitchDefaults.colors(checkedTrackColor = Nx.Yesil))
        }
        AyarSatiri(Icons.Filled.Lock, "Güvenlik (kilit / biyometrik)", "Yakında")
        AyarSatiri(Icons.Filled.Person, "Solana cüzdan bağlantısı", "Gerçek işlem aşamasında (N12), açık onayınızla")
    }
    Kart(Modifier.fillMaxWidth()) {
        AyarSatiri(Icons.Filled.Info, "Hakkında", "NEXORA 3.2 · yalnızca paper (sanal) işlem · gerçek işlem kapalı")
    }
}

@Composable
fun AyarSatiri(ikon: ImageVector, baslik: String, alt: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(ikon, null, tint = Nx.Mor)
        Column(Modifier.weight(1f)) {
            Text(baslik, color = Nx.Metin, fontSize = 15.sp)
            Text(alt, color = Nx.Soluk, fontSize = 12.sp)
        }
    }
}
