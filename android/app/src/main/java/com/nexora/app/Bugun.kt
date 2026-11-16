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
fun BugunKarti(v: Veri, durdurIste: () -> Unit = {}, pozisyonlaraGit: () -> Unit) {
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
        if (!v.acilDurdurma)
            Text("■ Acil durdur", color = Nx.Kirmizi, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                 modifier = Modifier.padding(top = 6.dp).clip(CircleShape).clickable(onClick = durdurIste).padding(horizontal = 4.dp, vertical = 4.dp))
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


/** N28: yapay zekâ yönlendirici. Kaynakları geçmiş karnelerine göre ağırlıklandıran sanal portföy; her kaynakla kıyas. */
@Composable
fun YonlendiriciKarti(v: Veri) {
    val j = v.yonlendirici ?: return
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("YAPAY ZEKÂ YÖNLENDİRİCİ", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket("paper", Nx.Gok)
        }
        if (j.optBoolean("bos")) { Text("İlk tur bekleniyor (saatlik).", color = Nx.Soluk, fontSize = 12.sp); return@NeonKart }
        val g = j.optDouble("getiri_pct", 0.0)
        Text((if (g >= 0) "+" else "") + yuzde(g, 2), color = kzRenk(g), fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Text("${j.optDouble("olcum_gun")} gün · zirveden düşüş ${yuzde(j.optDouble("zirveden_dusus_pct", 0.0), 2)} · nakitte ${yuzde(100 * j.optDouble("nakit_pay", 1.0), 0)}",
             color = Nx.Soluk, fontSize = 12.sp)
        val a = j.optJSONArray("kaynaklar") ?: return@NeonKart
        for (i in 0 until a.length()) {
            val s = a.getJSONObject(i)
            val kg = if (s.isNull("getiri_pct")) null else s.optDouble("getiri_pct")
            val kr = s.optJSONObject("karne")
            Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(s.optString("ad"), color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text("pay ${yuzde(100 * s.optDouble("pay", 0.0), 0)} · ${kr?.optInt("n") ?: 0} kapanan (14 gün)", color = Nx.Soluk, fontSize = 11.sp)
                }
                Text(kg?.let { (if (it >= 0) "+" else "") + yuzde(it, 2) } ?: "—", color = kg?.let { kzRenk(it) } ?: Nx.Soluk, fontSize = 13.sp)
            }
        }
        Text("Ağırlık önce verilir, getiri sonra ölçülür (geleceğe bakma yok). En az 5 kapanan işlemi ve pozitif karnesi olmayan kaynağa pay verilmez; tek kaynağa en fazla %40. Gerçek para yok.",
             color = Nx.Soluk, fontSize = 11.sp, lineHeight = 14.sp)
    }
}


/** Kanıt karnesi: hangi kaynak GERÇEKTEN kazandırıyor (güven alt sınırıyla; şans eseri kısa seriler ayıklanır). */
@Composable
fun KanitKarti(v: Veri) {
    val j = v.kanit ?: return
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("KANIT KARNESİ", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket("paper", Nx.Gok)
        }
        Text(j.optString("ozet"), color = Nx.Metin, fontSize = 13.sp, lineHeight = 17.sp)
        val a = j.optJSONArray("kaynaklar") ?: return@NeonKart
        for (i in 0 until a.length()) {
            val x = a.getJSONObject(i)
            val d = x.optString("duzey")
            val renk = when (d) { "güçlü" -> Nx.Nane; "umut verici" -> Nx.Gok; "zararda" -> Nx.Kirmizi; else -> Nx.Soluk }
            val ist = x.optJSONObject("islem")
            val n = ist?.optInt("n") ?: 0
            val g = if (x.isNull("portfoy_getiri_pct")) null else x.optDouble("portfoy_getiri_pct")
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(x.optString("ad"), color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text(buildString {
                        append("${x.optDouble("gun")} gün")
                        if (n > 0) append(" · $n kapanan · kazanma ${yuzde(ist!!.optDouble("kazanma_pct"), 0)} · ort. ${yuzde(ist.optDouble("ort"), 2)}")
                        if (g != null) append(" · portföy " + (if (g >= 0) "+" else "") + yuzde(g, 2))
                    }, color = Nx.Soluk, fontSize = 11.sp)
                }
                Etiket(d, renk)
            }
        }
        Text("Güçlü = en az 30 kapanan işlem, 14 gün, ortalama getirinin %95 güven alt sınırı sıfırın üstünde ve kâr faktörü ≥ 1,3. " + j.optString("not_"),
             color = Nx.Soluk, fontSize = 11.sp, lineHeight = 14.sp)
    }
}
