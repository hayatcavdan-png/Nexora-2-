package com.nexora.app

import android.content.SharedPreferences
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Kullanıcıyı yanıltan, bilgi değeri olmayan red gerekçeleri (kaynak cüzdan bizim almadığımız token'ı satınca oluşur). */
private val GURULTU = setOf("sahip olunmayan pozisyon satılamaz", "cüzdan yalnızca izleniyor")

/** Ana sayfa: "bugün ne oldu ve şu an neden işlem açılıyor/açılmıyor?" sorusunun tek karttaki cevabı. */
@Composable
fun BugunKarti(v: Veri, pozisyonlaraGit: () -> Unit) {
    val b = v.rapor?.optJSONObject("bugun") ?: return
    val maks = v.ayarlar.optInt("max_positions", 8).coerceAtLeast(1)
    val acik = v.pozisyonlar.size
    val dolu = acik >= maks
    val nedenler = buildList {
        val a = b.optJSONArray("red_gerekceleri")
        if (a != null) for (i in 0 until a.length()) {
            val x = a.getJSONObject(i)
            if (x.optString("gerekce") !in GURULTU) add(x.optString("gerekce") to x.optInt("adet"))
        }
    }
    val simdi = System.currentTimeMillis() / 1000.0
    val enEski = v.pozisyonlar.mapNotNull { it.acilis }.minOrNull()
    val durum = when {
        v.acilDurdurma -> "Acil durdurma açık: yeni alım yapılmıyor." to Nx.Kirmizi
        dolu -> "Tüm yerler dolu: bir pozisyon kapanınca yeni alım açılır." to Nx.Sari
        nedenler.isNotEmpty() -> "Yer var. Bugün en sık red: ${nedenler.first().first} (${nedenler.first().second}×)." to Nx.Soluk
        else -> "Yer var, yeni sinyal bekleniyor." to Nx.Nane
    }
    NeonKart(Modifier.fillMaxWidth().clickable(onClick = pozisyonlaraGit)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("BUGÜN", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text("$acik / $maks pozisyon", color = if (dolu) Nx.Sari else Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            for (i in 0 until maks)
                Box(Modifier.weight(1f).height(6.dp).clip(CircleShape).background(if (i < acik) (if (dolu) Nx.Sari else Nx.Nane) else Nx.Cizgi))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Mini("Alım", "${b.optInt("kopyalanan_alim")}")
            Mini("Kapanan", "${b.optInt("kapanan")}")
            Mini("Günlük K/Z", isaretli(b.optDouble("gerceklesen_kz", 0.0)))
            Mini("Sinyal", "${b.optInt("karar")}")
        }
        Text(durum.first, color = durum.second, fontSize = 12.sp, lineHeight = 16.sp)
        if (enEski != null && simdi - enEski > 86400)
            Text("En eski pozisyon ${sureMetni((simdi - enEski).toInt())} önce açıldı ve bir yeri tutuyor. Dokunup inceleyin.", color = Nx.Sari, fontSize = 12.sp)
        if (nedenler.size > 1)
            Text(nedenler.drop(if (dolu) 0 else 1).take(3).joinToString(" · ") { "${it.second}× ${it.first}" }, color = Nx.Soluk, fontSize = 11.sp)
    }
}

@Composable
fun GorunumAyari(sp: SharedPreferences) {
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f)) {
                Text("Animasyonları azalt", color = Nx.Metin, fontSize = 15.sp)
                Text("Arka plan sabit çizilir: pil tüketimi düşer, kaydırma akıcılaşır.", color = Nx.Soluk, fontSize = 12.sp)
            }
            Switch(Gorunum.sade, { Gorunum.sade = it; sp.edit().putBoolean("sade", it).apply() })
        }
    }
}


/** Platform 2 (borsa): dört borsada listeli token sinyallerinin ayrı paper portföyü. */
@Composable
fun BorsaKarti(v: Veri) {
    val b = v.borsa ?: return
    NeonKart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("PLATFORM 2 · BORSA", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket("paper", Nx.Gok)
        }
        if (!b.optBoolean("acik")) {
            Text("Henüz işlem yok. ${b.optInt("liste")} listeli token izleniyor (Binance, OKX, KuCoin, MEXC).", color = Nx.Soluk, fontSize = 12.sp)
            return@NeonKart
        }
        val kz = b.optDouble("kz", 0.0)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Mini("Değer", usd(b.optDouble("toplam", 0.0)))
            Mini("K/Z", isaretli(kz))
            Mini("Pozisyon", "${b.optJSONArray("pozisyonlar")?.length() ?: 0}")
        }
        val isl = b.optJSONArray("islemler")
        if (isl != null) for (i in 0 until minOf(3, isl.length())) {
            val x = isl.getJSONObject(i)
            val ok = x.optString("decision") == "KOPYALANDI"
            Text("${if (x.optString("side") == "buy") "AL" else "SAT"} ${kisa(x.optString("token"))} · ${if (ok) "yapıldı" else x.optString("reason")}",
                 color = if (ok) Nx.Metin else Nx.Soluk, fontSize = 12.sp, maxLines = 1)
        }
        Text("Borsanın gerçek alış/satış fiyatıyla sanal işlem; gerçek emir yok.", color = Nx.Soluk, fontSize = 11.sp)
    }
}


/** Platform 2 · piyasa stratejileri: dört borsadaki tüm coinler; her strateji ayrı sanal portföy, BTC'yi tutmakla kıyaslı. */
@Composable
fun StratejiKarti(v: Veri) {
    val j = v.strateji ?: return
    val d = j.optJSONObject("durum")
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("PLATFORM 2 · TÜM COİNLER", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket("paper", Nx.Gok)
        }
        if (d != null) {
            val k = if (d.isNull("kiyas_btc_pct")) null else d.optDouble("kiyas_btc_pct")
            Text("${d.optInt("evren")} coin izleniyor (Binance, OKX, KuCoin, MEXC)" + (k?.let { " · BTC'yi tutmak: " + (if (it >= 0) "+" else "") + yuzde(it, 2) } ?: ""),
                 color = Nx.Soluk, fontSize = 12.sp)
        } else Text("Motor henüz çalışmadı. Sunucuda güncelleme gerekiyor.", color = Nx.Soluk, fontSize = 12.sp)
        val a = j.optJSONArray("stratejiler") ?: return@NeonKart
        for (i in 0 until a.length()) {
            val s = a.getJSONObject(i)
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(s.optString("ad").replaceFirstChar { it.uppercase() }, color = Nx.Metin, fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                if (!s.optBoolean("bos")) {
                    val kz = s.optDouble("kz", 0.0)
                    val pct = kz / 100.0 * 100
                    Text("${isaretli(kz)} USDC (" + (if (pct >= 0) "+" else "") + yuzde(pct, 2) + ")", color = kzRenk(kz), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                }
            }
            if (s.optBoolean("bos")) { Text("Henüz işlem yok.", color = Nx.Soluk, fontSize = 12.sp); continue }
            val kaz = if (s.isNull("kazanma_pct")) "—" else yuzde(s.optDouble("kazanma_pct"), 0)
            val pf = if (s.isNull("profit_factor")) "—" else String.format(java.util.Locale.US, "%.2f", s.optDouble("profit_factor"))
            Text("${s.optInt("kapanan")} kapanan · kazanma $kaz · kâr faktörü $pf · ${s.optInt("acik")} açık", color = Nx.Soluk, fontSize = 12.sp)
            Text(s.optString("aciklama"), color = Nx.Soluk, fontSize = 11.sp, lineHeight = 14.sp)
        }
        Text("Borsanın gerçek alış/satış fiyatı, %0.1 işlem ücreti ve kaymayla sanal işlem; gerçek emir yok.", color = Nx.Soluk, fontSize = 11.sp)
    }
}
