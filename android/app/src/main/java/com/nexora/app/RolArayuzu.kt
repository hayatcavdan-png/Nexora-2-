package com.nexora.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import java.util.Locale

/**
 * NEXORA Role UI V1 — yalnızca sunucunun bildirdiği role göre sunum.
 * Yetkiler server.py tarafından denetlenir; UI gizleme tek başına yetki değildir.
 *
 * Maskot, açılış ekranı, Nexo animasyonları, Tema.kt ve AltMenu2 değiştirilmez.
 * Kişisel üye bakiyesi /uye/bakiye'den; kurucu istatistikleri genel paper
 * servisinden gelir. Bu iki veri kümesi asla tek bakiye olarak birleştirilmez.
 */

@Composable
private fun RolUstEtiketi(kurucu: Boolean, bagli: Boolean) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(7.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Etiket(if (kurucu) "YÖNETİCİ" else "ÜYE", if (kurucu) Nx.Nane else Nx.Gok)
        Etiket(if (bagli) "Sunucu bağlı" else "Bağlantı yok", if (bagli) Nx.Yesil else Nx.Sari)
    }
}

@Composable
private fun RolVurguKarti(
    ust: String, baslik: String, aciklama: String, kurucu: Boolean,
    icerik: @Composable ColumnScope.() -> Unit = {}
) {
    val renk = if (kurucu) Nx.Nane else Nx.Gok
    val sekil = RoundedCornerShape(24.dp)
    Column(
        Modifier.fillMaxWidth()
            .clip(sekil)
            .background(Brush.linearGradient(listOf(Nx.Kahraman, Nx.Yuzey, Nx.Zemin)))
            .border(1.dp, renk.copy(alpha = 0.45f), sekil)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text(ust, color = renk, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.4.sp)
            Etiket("PAPER", Nx.Gok)
        }
        Text(baslik, color = Nx.Metin, fontSize = 24.sp, fontWeight = FontWeight.Bold,
            lineHeight = 28.sp)
        Text(aciklama, color = Nx.Soluk, fontSize = 13.sp, lineHeight = 19.sp)
        icerik()
    }
}

@Composable
private fun RolMiniIstatistik(ad: String, sayi: String, renk: Color, modifier: Modifier = Modifier) {
    Column(
        modifier.background(Nx.Yuzey2.copy(alpha = 0.65f), RoundedCornerShape(14.dp))
            .padding(horizontal = 10.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(5.dp)
    ) {
        Text(ad, color = Nx.Soluk, fontSize = 11.sp, maxLines = 2)
        Text(sayi, color = renk, fontSize = 20.sp, fontWeight = FontWeight.Bold, maxLines = 1,
            overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun RolKisayol(
    baslik: String, aciklama: String, ikon: ImageVector,
    tikla: () -> Unit, modifier: Modifier = Modifier
) {
    Row(
        modifier.tiklaZipla(tikla = tikla)
            .background(Nx.Yuzey, RoundedCornerShape(17.dp))
            .border(1.dp, Nx.Cizgi, RoundedCornerShape(17.dp))
            .padding(horizontal = 12.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Icon(ikon, null, tint = Nx.Nane, modifier = Modifier.size(24.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(baslik, color = Nx.Metin, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(aciklama, color = Nx.Soluk, fontSize = 11.sp, maxLines = 2, lineHeight = 14.sp)
        }
    }
}

fun LazyListScope.yoneticiAnaPanel(v: Veri, git: (String) -> Unit) {
    item(key = "yonetici_hero") {
        RolVurguKarti(
            ust = "NEXORA / OPERASYON MERKEZİ",
            baslik = "Yönetici paneli",
            aciklama = "Cüzdan izleme, risk kontrolleri ve sosyal analiz tek çalışma alanında.",
            kurucu = true
        ) {
            RolUstEtiketi(kurucu = true, bagli = v.bagli)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RolMiniIstatistik("Takipteki cüzdan",
                    v.takipCuzdanlar.count { it.durum == "aktif" }.toString(), Nx.Nane,
                    Modifier.weight(1f))
                RolMiniIstatistik("Açık paper pozisyon", v.pozisyonlar.size.toString(), Nx.Gok,
                    Modifier.weight(1f))
                RolMiniIstatistik("Son sinyaller", v.sinyaller.size.toString(), Nx.Lila,
                    Modifier.weight(1f))
            }
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Etiket(if (v.acilDurdurma) "Pilot durduruldu" else "Paper takip",
                    if (v.acilDurdurma) Nx.Kirmizi else Nx.Yesil)
                Text("Gerçek emir kapalı", color = Nx.Soluk, fontSize = 11.sp)
            }
        }
    }
    item(key = "yonetici_hizli") {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Hızlı erişim", color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RolKisayol("Pilot ve risk", "İşlem güvenliği", Icons.Filled.Settings,
                    { git("bot") }, Modifier.weight(1f))
                RolKisayol("Sosyal AI", "Kaynak ve uyarılar", Icons.Filled.Search,
                    { git("sosyal") }, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RolKisayol("Cüzdanlar", "Takip ve kalite", Icons.Filled.AccountCircle,
                    { git("takip") }, Modifier.weight(1f))
                RolKisayol("Raporlar", "Paper sonuçları", Icons.Filled.DateRange,
                    { git("rapor") }, Modifier.weight(1f))
            }
        }
    }
}

fun LazyListScope.uyeAnaPanel(v: Veri, git: (String) -> Unit) {
    item(key = "uye_hero") {
        RolVurguKarti(
            ust = "NEXORA / KİŞİSEL ALAN",
            baslik = "Hoş geldiniz",
            aciklama = "Kişisel sanal hesabınızı ve araştırma sonuçlarını tek yerden inceleyin.",
            kurucu = false
        ) {
            RolUstEtiketi(kurucu = false, bagli = v.bagli)
            val b = if (v.bagli && Oturum.deger.isNotBlank()) v.uyeBakiye else null
            Text("KİŞİSEL NET SANAL BAKİYE", color = Nx.Soluk, fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
            Text(b?.dbl("net_bakiye")?.let { "${usd(it)} USDC" } ?: "Veri bekleniyor",
                color = Nx.Metin, fontSize = if (b == null) 19.sp else 30.sp,
                fontWeight = FontWeight.Bold)
            if (b != null) {
                val kar = b.dbl("net_kar")
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    RolMiniIstatistik("Net K/Z",
                        kar?.let { "${isaretli(it)} USDC" } ?: "—",
                        kar?.let { kzRenk(it) } ?: Nx.Soluk,
                        Modifier.weight(1f))
                    RolMiniIstatistik("Başlangıç",
                        b.dbl("baslangic")?.let { "${usd(it)}" } ?: "—",
                        Nx.Gok, Modifier.weight(1f))
                }
            }
            Text("Yalnızca paper/simülasyon. Gerçek fon, getiri garantisi veya emir yok.",
                color = Nx.Soluk, fontSize = 11.sp)
            Button({ git("uye") }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                colors = NxButonRenk(), shape = RoundedCornerShape(13.dp)) {
                Text("Hesap ve detaylar", fontWeight = FontWeight.SemiBold)
            }
        }
    }
    item(key = "uye_nexo") {
        NexoKonusuyor(
            "Sanal hesabını inceleyebilir, Solana tokenlerini keşfedebilir ve paper sonuçlarını takip edebilirsin.",
            NexoIfade.GULUS, Modifier.fillMaxWidth(), poz = NexoPoz.SELAM
        )
    }
    item(key = "uye_kisayollar") {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Keşfet ve takip et", color = Nx.Metin, fontSize = 17.sp,
                fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RolKisayol("Token Radar", "Solana keşfi", Icons.Filled.Search,
                    { git("kesfet") }, Modifier.weight(1f))
                RolKisayol("Karne", "Sistem paper verileri", Icons.Filled.Star,
                    { git("karne") }, Modifier.weight(1f))
            }
            RolKisayol("Hesabım", "Davet, bağlantı ve güvenlik", Icons.Filled.Person,
                { git("uye") }, Modifier.fillMaxWidth())
            BilgiKutusu("Yönetici kontrol ve risk ayarları üye hesabına kapalıdır. Bu ekranda yalnızca kişisel sanal bakiye gösterilir.")
        }
    }
}

fun LazyListScope.uyePortfoyPanel(v: Veri, git: (String) -> Unit) {
    item(key = "uye_portfoy_header") {
        SayfaBasligi("Kişisel portföy", "Komisyon sonrası sanal hesabınız",
            ikon = { NexoYuz(44.dp, NexoIfade.YILDIZ) })
    }
    item(key = "uye_portfoy_kart") {
        RolVurguKarti(
            ust = "ÜYE / SANAL PORTFÖY",
            baslik = (if (v.bagli && Oturum.deger.isNotBlank()) v.uyeBakiye else null)?.dbl("net_bakiye")?.let { "${usd(it)} USDC" } ?: "Bakiye bekleniyor",
            aciklama = "Kişisel performansınız yalnızca katılımınızdan itibaren hesaplanır.",
            kurucu = false
        ) {
            val b = if (v.bagli && Oturum.deger.isNotBlank()) v.uyeBakiye else null
            RolUstEtiketi(kurucu = false, bagli = v.bagli)
            if (b != null) {
                Satir("Başlangıç", b.dbl("baslangic")?.let { "${usd(it)} USDC" } ?: "—")
                val brut = b.dbl("brut_kar")
                Satir("Brüt kâr/zarar", brut?.let { "${isaretli(it)} USDC" } ?: "—",
                    brut?.let { kzRenk(it) } ?: Nx.Soluk)
                Satir("Komisyon", b.dbl("komisyon")?.let { "${usd(it)} USDC" } ?: "—")
                val net = b.dbl("net_kar")
                Satir("Net kâr/zarar", net?.let { "${isaretli(it)} USDC" } ?: "—",
                    net?.let { kzRenk(it) } ?: Nx.Soluk)
            } else {
                Text("Kişisel bakiye bu bağlantıdan henüz alınamadı.",
                    color = Nx.Soluk, fontSize = 13.sp)
            }
            Button({ git("uye") }, modifier = Modifier.fillMaxWidth(),
                colors = NxButonRenk(), shape = RoundedCornerShape(14.dp)) {
                Text("Hesap ayrıntılarını aç")
            }
        }
    }
    item(key = "uye_portfoy_note") {
        BilgiKutusu("Yöneticiye ait ortak paper işlemler, kişisel portföyünüz gibi gösterilmez. Hesabınızda gerçek işlem veya para transferi yapılamaz.")
    }
}

@Composable
fun RolProfilBasligi(v: Veri) {
    RolVurguKarti(
        ust = if (v.kurucu) "NEXORA / YÖNETİM" else "NEXORA / HESABIM",
        baslik = if (v.kurucu) "Kontrol ve ayarlar" else "Üye profili",
        aciklama = if (v.kurucu) "Yetkili işlemler, güvenlik ve sistem bağlantıları."
                   else "Kişisel hesap, bağlantılar ve uygulama tercihleri.",
        kurucu = v.kurucu
    ) {
        RolUstEtiketi(kurucu = v.kurucu, bagli = v.bagli)
        Text("NEXORA ${BuildConfig.VERSION_NAME} · yalnızca paper",
            color = Nx.Soluk, fontSize = 11.sp)
    }
}
