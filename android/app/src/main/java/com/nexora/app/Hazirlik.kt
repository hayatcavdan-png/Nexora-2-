package com.nexora.app

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Gerçek paraya geçiş karnesi: ölçülebilir ölçütler. Hiçbir durumda "gerçek emre geç" demez; son kararı ayrı onay verir. */
@Composable
fun HazirlikEkrani(v: Veri) {
    val h = v.hazirlik
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (h == null) { BilgiKutusu("Karne sunucudan bekleniyor. Sunucu güncel değilse: sudo bash /opt/nexora/deploy/guncelle.sh"); return@Column }
        val sonuc = h.optString("sonuc")
        val ifade = when (sonuc) { "teknik_tamam" -> NexoIfade.SEVINC; "gecmedi" -> NexoIfade.ENDISE; else -> NexoIfade.ODAK }
        NexoKonusuyor(h.optString("aciklama"), ifade, Modifier.fillMaxWidth(), poz = NexoPoz.KAVUS)
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Text("${h.optInt("gecen")} / ${h.optInt("toplam")} ölçüt geçti", color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text("Sanal (paper) verisinden hesaplanır; küçük örneklemde sonuç \"bekliyor\" kalır.", color = Nx.Soluk, fontSize = 12.sp)
        }
        val o = h.optJSONArray("olcutler")
        if (o != null) for (i in 0 until o.length()) {
            val x = o.getJSONObject(i)
            val d = x.optString("durum")
            val renk = when (d) { "gecti" -> Nx.Nane; "gecmedi" -> Nx.Kirmizi; else -> Nx.Kehribar }
            NeonKart(Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(x.optString("ad"), color = Nx.Metin, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    Etiket(when (d) { "gecti" -> "geçti"; "gecmedi" -> "geçmedi"; else -> "bekliyor" }, renk)
                }
                val deger = if (x.isNull("deger")) "—" else x.optString("deger")
                Text("Şu an: $deger   ·   Hedef: ${x.optString("hedef")}", color = Nx.Soluk, fontSize = 12.sp)
            }
        }
        NeonKart(Modifier.fillMaxWidth()) {
            Text("Elle onay gerektirenler", color = Nx.Metin, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            val m = h.optJSONArray("manuel")
            if (m != null) for (i in 0 until m.length()) Text("• " + m.getString(i), color = Nx.Soluk, fontSize = 12.sp)
        }
    }
}
