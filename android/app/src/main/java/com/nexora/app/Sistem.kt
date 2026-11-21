package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private fun sistemOnce(ts: Double): String {
    if (ts.isNaN() || ts <= 0) return "—"
    val sn = (System.currentTimeMillis() / 1000.0 - ts).toLong()
    return when { sn < 90 -> "${maxOf(0, sn)} sn önce"; sn < 5400 -> "${sn / 60} dk önce"; sn < 172800 -> "${sn / 3600} sa önce"; else -> "${sn / 86400} gün önce" }
}

private fun sistemTarih(ts: Double) = if (ts.isNaN() || ts <= 0) "—" else SimpleDateFormat("dd.MM HH:mm", Locale.getDefault()).format(Date((ts * 1000).toLong()))


/** Sistem sağlığı (5.22.0, yalnızca kurucu): servisler, sürüm, son çalışma zamanları, günlük zarar sınırı. Salt okunur. */
@Composable
fun SistemEkrani(url: String, key: String) {
    var d by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    var yukleniyor by remember { mutableStateOf(false) }
    var tetik by remember { mutableIntStateOf(0) }
    LaunchedEffect(tetik) {
        yukleniyor = true; hata = ""
        try { d = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/sistem", zamanAsimi = 20_000) }) }
        catch (e: Exception) { hata = if (e.message?.contains("404") == true) "Sunucu güncel değil: guncelle" else "Durum alınamadı: ${e.message}" }
        yukleniyor = false
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val sorun = d?.optInt("sorun") ?: 0
                Nokta(if (d == null) Nx.Soluk else if (sorun == 0) Nx.Yesil else Nx.Kirmizi)
                Spacer(Modifier.width(8.dp))
                Text(if (d == null) "Sistem durumu" else if (sorun == 0) "Tüm servisler çalışıyor" else "$sorun serviste sorun var",
                     color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                TextButton({ tetik++ }, enabled = !yukleniyor) { Text(if (yukleniyor) "…" else "Yenile", color = Nx.Nane) }
            }
            if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
            d?.optJSONObject("surum")?.let { s ->
                SatirKV("Kurulu sürüm", s.optString("kurulan", "—") + " · " + sistemTarih(s.optDouble("ts")))
                if (!s.isNull("mesaj")) Text(s.optString("mesaj"), color = Nx.Soluk, fontSize = 12.sp)
            }
        }
        d?.optJSONObject("paper")?.let { p ->
            if (!p.has("hata")) NeonKart(Modifier.fillMaxWidth(), kenar = if (p.optBoolean("limit_doldu") || p.optBoolean("acil_durdurma")) Nx.KenarParlak else Nx.Kenar) {
                Text("Paper hesap", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                SatirKV("Özkaynak", String.format(Locale.US, "%.2f $", p.optDouble("ozkaynak")))
                SatirKV("Bugünkü kayıp / sınır", String.format(Locale.US, "%%%.2f / %%%.0f", p.optDouble("gunluk_kayip_pct"), p.optDouble("limit_pct")))
                SatirKV("Açık pozisyon", "${p.optInt("acik_poz")}")
                if (p.optBoolean("limit_doldu"))
                    Text("Günlük zarar sınırı doldu: yeni alım yok. 03:00'te (UTC gece yarısı) sıfırlanır.", color = Nx.Kehribar, fontSize = 13.sp)
                if (p.optBoolean("acil_durdurma")) Text("Acil durdurma AÇIK: yeni alım yok.", color = Nx.Kirmizi, fontSize = 13.sp)
            }
        }
        d?.optJSONArray("servisler")?.let { a ->
            NeonKart(Modifier.fillMaxWidth()) {
                Text("Servisler", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                for (i in 0 until a.length()) {
                    val s = a.getJSONObject(i); val dr = s.optString("durum")
                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                        Nokta(when (dr) { "active" -> Nx.Yesil; "activating", "reloading" -> Nx.Kehribar; "bilinmiyor" -> Nx.Soluk; else -> Nx.Kirmizi })
                        Spacer(Modifier.width(8.dp))
                        Text(s.optString("ad"), color = Nx.Metin, fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(when (dr) { "active" -> "çalışıyor"; "inactive" -> "durmuş"; "failed" -> "HATA"; "activating" -> "başlıyor"; else -> dr },
                             color = Nx.Soluk, fontSize = 12.sp)
                    }
                }
                Text("Durmuş bir servis 90 sn'den uzun sürerse bildirim gelir.", color = Nx.Soluk, fontSize = 11.sp)
            }
        }
        d?.optJSONObject("zamanlar")?.let { z ->
            NeonKart(Modifier.fillMaxWidth()) {
                Text("Son çalışma", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                SatirKV("Son Solana sinyali", sistemOnce(z.optDouble("son_sinyal")))
                SatirKV("Son etiketlenen sinyal", sistemOnce(z.optDouble("son_etiket")))
                SatirKV("Hyperliquid son okuma", sistemOnce(z.optDouble("hl_son")))
                SatirKV("Gece keşfi", sistemOnce(z.optDouble("kesif")) + if (z.optString("kesif_durum") == "hata") " · HATA" else "")
                if (!z.isNull("yz_sonuc")) SatirKV("Yapay zekâ sınaması", z.optString("yz_sonuc").removePrefix("Karar: ").take(40))
            }
        }
        d?.optJSONObject("panel")?.let { p ->
            NeonKart(Modifier.fillMaxWidth()) {
                Text("Kaynaklar", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                p.optJSONObject("disk")?.let { SatirKV("Disk", "%${it.optDouble("dolu_pct")} dolu · ${it.optDouble("bos_gb")} GB boş") }
                SatirKV("Paper veritabanı", "${p.optDouble("paper_db_mb")} MB")
                SatirKV("Son yedek", if (p.isNull("son_yedek_once_sn")) "—" else "${p.optLong("son_yedek_once_sn") / 3600} sa önce")
            }
        }
    }
}

/** Canlı defter, ölçümü tutuyor mu? 20.11 çıkış düzeltmesinden beri canlı paper ile aynı dönemin deney masası. */
@Composable
fun TutarlilikKarti(url: String, key: String) {
    var d by remember { mutableStateOf<JSONObject?>(null) }
    var hata by remember { mutableStateOf("") }
    var tetik by remember { mutableIntStateOf(0) }
    LaunchedEffect(tetik) {
        hata = ""
        try { d = JSONObject(withContext(Dispatchers.IO) { api(url, key, "/tutarlilik", zamanAsimi = 30_000) }) }
        catch (e: Exception) { hata = if (e.message?.contains("404") == true) "Sunucu güncel değil: guncelle" else "Alınamadı: ${e.message}" }
    }
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Canlı, ölçümü tutuyor mu?", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            TextButton({ tetik++ }) { Text("Yenile", color = Nx.Nane) }
        }
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
        d?.let { r ->
            val c = r.optJSONObject("canli") ?: JSONObject(); val x = r.optJSONObject("deney") ?: JSONObject()
            Text("Çıkış düzeltmesinden (20.11 16:45) beri · ${r.optDouble("gun")} gün", color = Nx.Soluk, fontSize = 12.sp)
            Row(Modifier.fillMaxWidth().padding(top = 6.dp)) {
                Column(Modifier.weight(1f)) {
                    Text("Canlı paper", color = Nx.Soluk, fontSize = 12.sp)
                    Text(if (c.isNull("toplam_pct")) "—" else String.format(Locale.US, "%+.2f%%", c.optDouble("toplam_pct")),
                         color = if (c.optDouble("toplam_pct", 0.0) >= 0) Nx.Yesil else Nx.Kirmizi, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    Text("${c.optInt("satis")} kapanan · ${c.optInt("kazanan")} kazanan", color = Nx.Soluk, fontSize = 11.sp)
                    Text(String.format(Locale.US, "gerçekleşen %+.2f$ · açık %+.2f$", c.optDouble("gerceklesen"), c.optDouble("acik_kz")), color = Nx.Soluk, fontSize = 11.sp)
                }
                Column(Modifier.weight(1f)) {
                    Text("Deney masası", color = Nx.Soluk, fontSize = 12.sp)
                    Text(String.format(Locale.US, "%+.2f%%", x.optDouble("toplam_pct", 0.0)),
                         color = if (x.optDouble("toplam_pct", 0.0) >= 0) Nx.Yesil else Nx.Kirmizi, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    Text("${x.optInt("islem")} işlem · %${x.optInt("kazanan")} kazanan", color = Nx.Soluk, fontSize = 11.sp)
                    Text("${x.optInt("sinyal")} sonuçlanan sinyal", color = Nx.Soluk, fontSize = 11.sp)
                }
            }
            r.optJSONObject("eslesme")?.let { e ->
                if (e.optInt("n") > 0) {
                    Text("Aynı sinyaller, iki sonuç (${e.optInt("n")} işlem)", color = Nx.Metin, fontSize = 13.sp,
                         fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
                    Text(String.format(Locale.US, "canlı ort %+.1f%% · ölçülen ort %+.1f%% · fark medyan %+.1f%%",
                         e.optDouble("canli_ort"), e.optDouble("olculen_ort"), e.optDouble("fark_medyan")), color = Nx.Soluk, fontSize = 12.sp)
                }
            }
            Text("Deney masası yalnızca sonucu kesinleşmiş (etiketli) sinyalleri oynatır; ilk günlerde canlıdan az işlem görür.",
                 color = Nx.Soluk, fontSize = 11.sp)
            Text(r.optString("yorum"), color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            if (c.optInt("baska_satici") > 0)
                Text("Başka cüzdanın satışı ${c.optInt("baska_satici")} kez pozisyonu kapatmadı (düzeltme çalışıyor).", color = Nx.Soluk, fontSize = 11.sp)
            if (c.optInt("limit_red") > 0)
                Text("Günlük zarar sınırı yüzünden ${c.optInt("limit_red")} alım reddedildi.", color = Nx.Kehribar, fontSize = 11.sp)
        }
    }
}
