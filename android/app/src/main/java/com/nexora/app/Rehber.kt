package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 5.24.0 sade düzen: beş sekme, her biri tek bir soruyu cevaplar. */
data class SekmeTanim(val id: String, val ad: String, val soru: String, val icerik: String)

fun sekmeler(kurucu: Boolean) = listOf(
    SekmeTanim("ana", "Özet", "Durum ne?", "Sanal portföy değeri, bugün olanlar, hızlı geçişler"),
    SekmeTanim("kesfet", "Takip", "Kimi takip ediyoruz?",
        if (kurucu) "Solana cüzdanları, Hyperliquid trader'ları, token'lar, cüzdan analizi" else "Takip edilen cüzdanların aldığı token'lar"),
    SekmeTanim("portfoy", "İşlemler", "Elimizde ne var?", "Açık pozisyonlar ve işlem geçmişi"),
    SekmeTanim("karne", "Sonuçlar", "Kazanıyor muyuz?", "Kâr/zarar, canlı ile ölçüm karşılaştırması, ayrıntılı rapor"),
    SekmeTanim("profil", "Yönetim", "Nasıl yönetirim?",
        if (kurucu) "Bot ve risk ayarları, acil durdurma, sistem sağlığı, hesap, ayarlar" else "Hesap, yol haritası, ayarlar"),
)

/** Özet sekmesinin başlığı: logo, 'sanal para' etiketi, rehber ve rapor düğmeleri. */
@Composable
fun OzetUstBaslik(rehberAc: () -> Unit, rapor: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        IconButton(rehberAc) { Icon(Icons.Filled.Info, "NEXORA nedir?", tint = Nx.Metin) }
        Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
            Logo(24.sp)
            Text("Sanal para ile deneme · gerçek işlem yok", color = Nx.Soluk, fontSize = 11.sp)
        }
        IconButton(rapor) { Icon(Icons.Filled.Notifications, "Günlük rapor", tint = Nx.Metin) }
    }
}

/** İlk açılışta görünen rehber: NEXORA ne yapar, hangi sekmede ne var. Kapatılabilir, (i) ile yeniden açılır. */
@Composable
fun NexoraRehberi(kurucu: Boolean, git: (String) -> Unit, kapat: () -> Unit) {
    NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            NexoYuz(36.dp, NexoIfade.GULUS)
            Spacer(Modifier.width(10.dp))
            Text("NEXORA ne yapar?", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        }
        Text("Başarılı kripto cüzdanlarını ve trader'ları izler, aldıklarını SANAL parayla kopyalar ve sonucu gerçek fiyatlarla ölçer. " +
             "Amaç: gerçek paraya geçmeden önce bu yöntemin kâr ettirip ettirmediğini kanıtlamak. Gerçek para ve gerçek emir yoktur.",
             color = Nx.Metin, fontSize = 13.sp, lineHeight = 19.sp)
        Text("Alttaki 5 sekme, 5 soruyu cevaplar:", color = Nx.Soluk, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
        sekmeler(kurucu).forEach { s ->
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { git(s.id) }.padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.width(86.dp)) {
                    Text(s.ad, color = Nx.Nane, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                }
                Column(Modifier.weight(1f)) {
                    Text(s.soru, color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text(s.icerik, color = Nx.Soluk, fontSize = 11.sp)
                }
                Text("›", color = Nx.Soluk, fontSize = 20.sp)
            }
        }
        TextButton(kapat, modifier = Modifier.align(Alignment.End)) { Text("Anladım", color = Nx.Nane) }
    }
}

/** Özet'te dört büyük soru düğmesi: tek dokunuşla ilgili sekmeye. */
@Composable
fun HizliSorular(kurucu: Boolean, git: (String) -> Unit) {
    val l = buildList {
        add(Triple("Kimi takip ediyoruz?", "Takip", "kesfet"))
        add(Triple("Elimizde ne var?", "İşlemler", "portfoy"))
        add(Triple("Kazanıyor muyuz?", "Sonuçlar", "karne"))
        add(if (kurucu) Triple("Sistem çalışıyor mu?", "Sistem sağlığı", "sistem") else Triple("Hesabım", "Yönetim", "uye"))
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        l.chunked(2).forEach { satir ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                satir.forEach { (soru, nerede, hedef) ->
                    Column(Modifier.weight(1f).clip(RoundedCornerShape(18.dp)).background(Nx.Yuzey.copy(alpha = 0.92f))
                        .border(1.dp, Nx.Cizgi, RoundedCornerShape(18.dp)).clickable { git(hedef) }.padding(14.dp)) {
                        Text(soru, color = Nx.Metin, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                        Text("$nerede ›", color = Nx.Nane, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

/** Her ana sekmenin üstünde: sekme adı ve hangi soruyu cevapladığı. */
@Composable
fun SekmeBasligi(id: String, kurucu: Boolean, geri: (() -> Unit)? = null) {
    val s = sekmeler(kurucu).first { it.id == id }
    SayfaBasligi(s.ad, s.soru + " " + s.icerik, geri = geri)
}

/** Yönetim sekmesinde grup başlığı. */
@Composable
fun GrupBasligi(ad: String) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 6.dp)) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(Nx.Nane))
        Spacer(Modifier.width(8.dp))
        Text(ad.uppercase(), color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.Bold)
    }
}
