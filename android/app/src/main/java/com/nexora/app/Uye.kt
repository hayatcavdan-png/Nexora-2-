package com.nexora.app

import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Locale

/**
 * Hesabım: giriş/kayıt, davet kodu, bağlantılar ve komisyon sonrası SANAL bakiye.
 * Cüzdan özel anahtarı / seed ASLA istenmez (Phantom için yalnızca herkese açık adres). Borsa API anahtarı (N29) yalnızca
 * para çekme izni KAPALI ise sunucu tarafından kabul edilir, sunucuda şifreli saklanır ve şimdilik yalnızca bakiye okunur.
 * Gizli alanlar gönderildikten sonra ekrandan silinir; cihazda saklanmaz.
 * Oturum anahtarı yalnızca bu cihazda (SharedPreferences) tutulur.
 */
@Composable
fun UyeEkrani(url: String, key: String, sp: SharedPreferences) {
    val scope = rememberCoroutineScope()
    var oturum by remember { mutableStateOf(Kasa.oku(sp, "oturum")) }
    var profil by remember { mutableStateOf<JSONObject?>(null) }
    var bakiye by remember { mutableStateOf<JSONObject?>(null) }
    var mesaj by remember { mutableStateOf("") }
    var mesgul by remember { mutableStateOf(false) }
    var kayitModu by remember { mutableStateOf(false) }
    var eposta by remember { mutableStateOf("") }
    var parola by remember { mutableStateOf("") }
    var davet by remember { mutableStateOf("") }
    var borsalar by remember { mutableStateOf<org.json.JSONArray?>(null) }
    var gercek by remember { mutableStateOf<JSONObject?>(null) }
    var sifirla by remember { mutableStateOf(false) }                 // şifre sıfırlama: e-postadaki kodla yeni parola
    var kod by remember { mutableStateOf("") }

    fun cagri(yol: String, post: Boolean = false, govde: JSONObject = JSONObject(), basari: (String) -> Unit) = scope.launch {
        mesgul = true; mesaj = ""
        try { basari(withContext(Dispatchers.IO) { api(url, key, yol, post, govde.toString(), 15_000, oturum) }) }
        catch (e: Exception) {
            val m = e.message ?: ""
            if (m.contains("401") && oturum.isNotEmpty() && m.contains("oturum")) {            // süre doldu
                oturum = ""; sp.edit().remove("oturum").apply(); profil = null; bakiye = null
                mesaj = "Oturum süresi doldu, tekrar giriş yapın."
            } else mesaj = if (m.contains("404")) "Sunucu güncel değil: sudo bash /opt/nexora/deploy/guncelle.sh" else m.removePrefix("HTTP ").substringAfter(": ", m)
        }
        mesgul = false
    }
    fun yukle() {
        cagri("/uye/ben") { profil = JSONObject(it) }
        cagri("/uye/bakiye") { bakiye = JSONObject(it) }
        cagri("/uye/borsa") { borsalar = JSONObject(it).optJSONArray("borsalar") }
    }
    fun girisBitti(r: String) {
        oturum = JSONObject(r).optString("oturum"); Kasa.yaz(sp, "oturum", oturum); parola = ""
        yukle()
    }
    LaunchedEffect(oturum) { if (oturum.isNotEmpty() && profil == null) yukle() }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (oturum.isEmpty()) {
            NexoKonusuyor(if (kayitModu) "Hesabını oluştur, davet kodun hazır olsun!" else "Tekrar hoş geldin! Giriş yap.",
                          if (kayitModu) NexoIfade.YILDIZ else NexoIfade.GULUS, Modifier.fillMaxWidth(), poz = NexoPoz.SELAM)
            NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Hap("Giriş", !kayitModu, Modifier.weight(1f)) { kayitModu = false; sifirla = false; mesaj = "" }
                    Hap("Kayıt ol", kayitModu, Modifier.weight(1f)) { kayitModu = true; sifirla = false; mesaj = "" }
                }
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(eposta, { eposta = it.trim() }, label = { Text("E-posta") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                                  keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                OutlinedTextField(parola, { parola = it }, label = { Text(if (sifirla) "Yeni parola (en az 8 karakter)" else if (kayitModu) "Parola (en az 8 karakter)" else "Parola") }, singleLine = true,
                                  modifier = Modifier.fillMaxWidth(), visualTransformation = PasswordVisualTransformation(),
                                  keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                if (sifirla) OutlinedTextField(kod, { kod = it.trim().uppercase(Locale.ROOT) }, label = { Text("E-postadaki 8 karakterli kod") },
                                  singleLine = true, modifier = Modifier.fillMaxWidth())
                if (kayitModu) OutlinedTextField(davet, { davet = it.trim().uppercase(Locale.ROOT) }, label = { Text("Davet kodu (isteğe bağlı)") },
                                  singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(10.dp))
                Button({
                    if (sifirla) cagri("/uye/sifre-sifirla", true, JSONObject().put("eposta", eposta).put("kod", kod).put("yeni", parola)) {
                        sifirla = false; kod = ""; girisBitti(it)
                    } else {
                        val g = JSONObject().put("eposta", eposta).put("parola", parola)
                        if (kayitModu) g.put("davet", davet)
                        cagri(if (kayitModu) "/uye/kayit" else "/uye/giris", true, g) { girisBitti(it) }
                    }
                }, Modifier.fillMaxWidth(),
                    enabled = !mesgul && eposta.isNotEmpty() && parola.isNotEmpty() && (!sifirla || kod.length >= 8), colors = NxButonRenk()) {
                    Text(if (sifirla) "Şifreyi sıfırla" else if (kayitModu) "Hesap oluştur" else "Giriş yap", fontWeight = FontWeight.Bold)
                }
                if (!kayitModu) {
                    TextButton({
                        cagri("/uye/sifre-unut", true, JSONObject().put("eposta", eposta)) {
                            sifirla = true; kod = ""; mesaj = "Bu e-posta kayıtlıysa 8 karakterli bir kod gönderildi. Kodu girip yeni parolanızı belirleyin."
                        }
                    }, enabled = !mesgul && eposta.isNotEmpty()) {
                        Text(if (sifirla) "Kodu yeniden gönder" else "Şifremi unuttum", color = Nx.Nane)
                    }
                    if (sifirla) TextButton({ sifirla = false; kod = ""; mesaj = "" }) { Text("Girişe dön", color = Nx.Soluk) }
                }
                if (mesaj.isNotEmpty()) Text(mesaj, color = Nx.Kirmizi, fontSize = 13.sp)
            }
            BilgiKutusu("Parolanız sunucuda geri döndürülemez biçimde saklanır. Bu uygulama sizden hiçbir zaman cüzdan özel anahtarı ya da seed phrase istemez.")
            return@Column
        }

        val p = profil
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Nexo(64.dp, NexoIfade.HAVALI)
                Column(Modifier.weight(1f)) {
                    Text(p?.optString("eposta") ?: "…", color = Nx.Metin, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    Text("Paper hesabı · gerçek işlem kapalı", color = Nx.Soluk, fontSize = 12.sp)
                }
                TextButton({ cagri("/uye/cikis", true) { oturum = ""; sp.edit().remove("oturum").apply(); profil = null; bakiye = null } }) {
                    Text("Çıkış", color = Nx.Kirmizi)
                }
            }
        }
        if (mesaj.isNotEmpty()) Text(mesaj, color = Nx.Kirmizi, fontSize = 13.sp)

        // ---- komisyon sonrası bakiye (sanal)
        bakiye?.let { b ->
            NeonKart(Modifier.fillMaxWidth(), dolgu = Nx.DolguMor) {
                Text("KİŞİSEL SANAL HESABIN · KOMİSYON SONRASI", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text(para(b.optDouble("net_bakiye")), color = Nx.Metin, fontSize = 30.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                SatirKV("Başlangıç", para(b.optDouble("baslangic")))
                SatirKV("Brüt kâr/zarar", paraIsaretli(b.optDouble("brut_kar")))
                SatirKV("Uygulama komisyonu (%${String.format(Locale.US, "%.0f", b.optDouble("komisyon_pct"))} kâr payı)", "−" + para(b.optDouble("komisyon")))
                SatirKV("Net kâr/zarar", paraIsaretli(b.optDouble("net_kar")))
                if (b.has("getiri_pct")) {
                    SatirKV("Getiri (katılımdan beri)", (if (b.optDouble("getiri_pct") >= 0) "+" else "") + String.format(Locale.US, "%.2f%%", b.optDouble("getiri_pct")))
                    SatirKV("Zirve · zirveden düşüş", para(b.optDouble("zirve")) + " · %" + String.format(Locale.US, "%.1f", b.optDouble("zirveden_dusus_pct")))
                    SatirKV("Katılım", gunAy(b.optDouble("katilim_ts")) + " " + saat(b.optDouble("katilim_ts")).take(5))
                }
                Spacer(Modifier.height(8.dp))
                var yeni by remember { mutableStateOf("") }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(yeni, { yeni = it.filter { c -> c.isDigit() }.take(6) }, label = { Text("Yeni başlangıç (USDC)") }, singleLine = true,
                                      modifier = Modifier.weight(1f), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                    Button({ cagri("/uye/portfoy", true, JSONObject().put("baslangic", yeni.toDouble())) { bakiye = JSONObject(it); yeni = "" } },
                           enabled = !mesgul && yeni.isNotEmpty(), colors = NxGriButon()) { Text("Sıfırla") }
                }
                Text("Hesabın, katıldığın andan itibaren sistemin yüzde getirisini izler. Sıfırlarsan yeni tutarla bugünden başlar (10–100.000).",
                     color = Nx.Soluk, fontSize = 11.sp, lineHeight = 15.sp)
                Spacer(Modifier.height(6.dp))
                Text("Komisyon yalnızca kârdan hesaplanır; zararda 0'dır. Bu bir SANAL gösterimdir: para saklanmaz, tahsilat yapılmaz.",
                     color = Nx.Soluk, fontSize = 11.sp, lineHeight = 15.sp)
            }
        }

        // ---- davet
        p?.let { pr ->
            val kod = pr.optString("davet_kodu")
            val pano = LocalClipboardManager.current
            val ctx = LocalContext.current
            NeonKart(Modifier.fillMaxWidth()) {
                Text("DAVET KODUN", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text(kod, color = Nx.Nane, fontSize = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = 4.sp)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button({ pano.setText(AnnotatedString(kod)); android.widget.Toast.makeText(ctx, "Kod kopyalandı", android.widget.Toast.LENGTH_SHORT).show() },
                           Modifier.weight(1f), colors = NxGriButon()) { Text("Kopyala") }
                    Button({
                        val i = Intent(Intent.ACTION_SEND).setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, "NEXORA AI: yapay zekâ destekli kopya ticaret (paper/demo). Davet kodum: $kod")
                        ctx.startActivity(Intent.createChooser(i, "Davet gönder"))
                    }, Modifier.weight(1f), colors = NxButonRenk()) { Text("Paylaş") }
                }
                Spacer(Modifier.height(8.dp))
                val n = pr.optInt("davet_sayisi")
                Text(if (n == 0) "Henüz davet ettiğin kimse yok." else "$n kişiyi davet ettin:", color = Nx.Metin, fontSize = 13.sp)
                val l = pr.optJSONArray("davetliler")
                if (l != null) for (i in 0 until l.length()) Text("• " + l.getJSONObject(i).optString("eposta"), color = Nx.Soluk, fontSize = 12.sp)
                Text("Davet ödülü yoktur; sayaç yalnızca bilgi amaçlıdır.", color = Nx.Soluk, fontSize = 11.sp)
            }

            // ---- bağlantılar
            Text("Bağlantılar", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            val bl = pr.optJSONArray("baglantilar")
            if (bl != null) for (i in 0 until bl.length()) {
                val b = bl.getJSONObject(i)
                BaglantiKarti(b, mesgul,
                    kaydet = { adres -> cagri("/uye/baglanti", true, JSONObject().put("tur", b.optString("tur")).put("adres", adres)) { profil = JSONObject(it) } },
                    sil = { cagri("/uye/baglanti", true, JSONObject().put("tur", b.optString("tur")).put("sil", true)) { profil = JSONObject(it) } })
            }
            BorsaHesaplari(borsalar, gercek, mesgul,
                bagla = { b, k, g, p, bitti -> cagri("/uye/borsa", true, JSONObject().put("borsa", b).put("api_key", k).put("api_secret", g).put("passphrase", p)) {
                    borsalar = JSONObject(it).optJSONArray("borsalar"); gercek = null; mesaj = "Bağlandı: para çekme izni kapalı doğrulandı."; bitti() } },
                sil = { b -> cagri("/uye/borsa", true, JSONObject().put("borsa", b).put("sil", true)) { borsalar = JSONObject(it).optJSONArray("borsalar"); gercek = null } },
                oku = { cagri("/uye/borsa?bakiye=1") { gercek = JSONObject(it) } })
            GuvenlikKarti(mesgul,
                parolaDegistir = { eski, yeni -> cagri("/uye/parola", true, JSONObject().put("eski", eski).put("yeni", yeni)) {
                    oturum = JSONObject(it).optString("oturum"); Kasa.yaz(sp, "oturum", oturum); mesaj = "Parola değişti. Diğer tüm cihazlarda oturum kapandı." } },
                tumOturumlar = { cagri("/uye/oturumlari-kapat", true) { oturum = ""; sp.edit().remove("oturum").apply(); profil = null; bakiye = null; mesaj = "Tüm oturumlar kapatıldı. Tekrar giriş yapın." } })
            BilgiKutusu("Sistem sunucuları (Helius, Jupiter) sizin adınıza ayrı anahtar gerektirmez. Borsa anahtarınızla şu an yalnızca bakiye okunur; uygulama emir göndermez ve para çekemez.")
        }
    }
}

@Composable
private fun BaglantiKarti(b: JSONObject, mesgul: Boolean, kaydet: (String) -> Unit, sil: () -> Unit) {
    val durum = b.optString("durum")
    val renk = when (durum) { "bağlı" -> Nx.Nane; "kilitli" -> Nx.Kehribar; "sistem kullanıyor" -> Nx.Gok; else -> Nx.Soluk }
    var adres by remember { mutableStateOf("") }
    NeonKart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(b.optString("ad"), color = Nx.Metin, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Etiket(durum, renk)
        }
        Text(b.optString("aciklama"), color = Nx.Soluk, fontSize = 12.sp, lineHeight = 16.sp)
        if (b.optString("tur") == "phantom") {
            val kayitli = if (b.isNull("adres")) "" else b.optString("adres")
            if (kayitli.isNotEmpty()) {
                Text(kayitli.take(6) + "…" + kayitli.takeLast(6), color = Nx.Metin, fontSize = 13.sp)
                TextButton(sil, enabled = !mesgul) { Text("Bağlantıyı kaldır", color = Nx.Kirmizi) }
            } else {
                OutlinedTextField(adres, { adres = it.trim() }, label = { Text("Herkese açık cüzdan adresi") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Button({ kaydet(adres) }, Modifier.fillMaxWidth(), enabled = !mesgul && adres.length >= 32, colors = NxButonRenk()) { Text("Adresi kaydet") }
            }
        }
    }
}

/** N35: parola değiştirme ve tüm oturumları kapatma. Parola değişince diğer cihazların oturumu kapanır. */
@Composable
private fun GuvenlikKarti(mesgul: Boolean, parolaDegistir: (String, String) -> Unit, tumOturumlar: () -> Unit) {
    var acik by remember { mutableStateOf(false) }
    var eski by remember { mutableStateOf("") }
    var yeni by remember { mutableStateOf("") }
    Text("Güvenlik", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold)
    NeonKart(Modifier.fillMaxWidth()) {
        if (!acik) {
            Button({ acik = true }, Modifier.fillMaxWidth(), enabled = !mesgul, colors = NxGriButon()) { Text("Parolamı değiştir") }
        } else {
            OutlinedTextField(eski, { eski = it }, label = { Text("Mevcut parola") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
            OutlinedTextField(yeni, { yeni = it }, label = { Text("Yeni parola (en az 8 karakter)") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button({ acik = false; eski = ""; yeni = "" }, Modifier.weight(1f), colors = NxGriButon()) { Text("Vazgeç") }
                Button({ parolaDegistir(eski, yeni); eski = ""; yeni = ""; acik = false }, Modifier.weight(1f),
                    enabled = !mesgul && eski.isNotEmpty() && yeni.length >= 8, colors = NxButonRenk()) { Text("Değiştir") }
            }
        }
        TextButton(tumOturumlar, enabled = !mesgul) { Text("Tüm cihazlardaki oturumları kapat", color = Nx.Kirmizi) }
        Text("Kayıp bir cihazınız varsa oturumları kapatın. Borsa anahtarlarınız silinmez.", color = Nx.Soluk, fontSize = 11.sp)
    }
}

/** N29/N30: borsa hesapları. Her borsa için bağla/kaldır; bağlı borsaların GERÇEK bakiyesi yalnızca okunur. */
@Composable
private fun BorsaHesaplari(liste: org.json.JSONArray?, gercek: JSONObject?, mesgul: Boolean,
                           bagla: (String, String, String, String, () -> Unit) -> Unit, sil: (String) -> Unit, oku: () -> Unit) {
    Text("Borsa hesaplarım", color = Nx.Metin, fontSize = 18.sp, fontWeight = FontWeight.Bold)
    if (liste == null) { Text("Sunucudan bekleniyor…", color = Nx.Soluk, fontSize = 12.sp); return }
    BilgiKutusu("Borsada yeni bir API anahtarı oluşturun: OKUMA açık, PARA ÇEKME KAPALI. Mümkünse IP kısıtı ekleyin. " +
                "Çekim izni açık anahtar reddedilir ve saklanmaz. Paranız her zaman kendi borsa hesabınızda kalır.")
    var acik by remember { mutableStateOf("") }
    for (i in 0 until liste.length()) {
        val b = liste.getJSONObject(i); val id = b.optString("borsa")
        NeonKart(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(b.optString("ad"), color = Nx.Metin, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                Etiket(if (b.optBoolean("bagli")) "bağlı" else "bağlı değil", if (b.optBoolean("bagli")) Nx.Nane else Nx.Soluk)
            }
            if (b.optBoolean("bagli")) {
                Text("Anahtar " + b.optString("maske"), color = Nx.Metin, fontSize = 13.sp)
                val iz = b.optJSONObject("izin")
                if (iz != null) {
                    Text("Para çekme: KAPALI ✓ · İşlem izni: ${if (iz.optBoolean("islem")) "var" else "yok"}" +
                         (if (iz.isNull("ip_kisitli")) "" else " · IP kısıtı: ${if (iz.optBoolean("ip_kisitli")) "var" else "yok"}"),
                         color = Nx.Soluk, fontSize = 12.sp)
                    if (!iz.isNull("ip_kisitli") && !iz.optBoolean("ip_kisitli"))
                        Text("Öneri: anahtara IP kısıtı ekleyin (sunucu adresi).", color = Nx.Kehribar, fontSize = 12.sp)
                }
                TextButton({ sil(id) }, enabled = !mesgul) { Text("Bağlantıyı kaldır", color = Nx.Kirmizi) }
            } else if (acik != id) {
                Button({ acik = id }, Modifier.fillMaxWidth(), enabled = !mesgul, colors = NxGriButon()) { Text("Bağla") }
            } else {
                var k by remember(id) { mutableStateOf("") }
                var g by remember(id) { mutableStateOf("") }
                var p by remember(id) { mutableStateOf("") }
                var onay by remember(id) { mutableStateOf(false) }
                val parolaGerekli = b.optBoolean("parola_gerekli")
                OutlinedTextField(k, { k = it.trim() }, label = { Text("API anahtarı") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(g, { g = it.trim() }, label = { Text("Gizli anahtar (secret)") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                if (parolaGerekli) OutlinedTextField(p, { p = it.trim() }, label = { Text("API parolası (passphrase)") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(onay, { onay = it })
                    Text("Bu anahtarda para çekme izni KAPALI", color = Nx.Metin, fontSize = 13.sp)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button({ acik = ""; k = ""; g = ""; p = "" }, Modifier.weight(1f), colors = NxGriButon()) { Text("Vazgeç") }
                    Button({ bagla(id, k, g, p) { acik = "" }; k = ""; g = ""; p = "" }, Modifier.weight(1f),
                        enabled = !mesgul && onay && k.length >= 8 && g.length >= 8 && (!parolaGerekli || p.isNotEmpty()),
                        colors = NxButonRenk()) { Text("Doğrula ve bağla") }
                }
            }
        }
    }
    val bagliVar = (0 until liste.length()).any { liste.getJSONObject(it).optBoolean("bagli") }
    if (bagliVar) NeonKart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("GERÇEK BAKİYE (yalnızca okuma)", color = Nx.Soluk, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton(oku, enabled = !mesgul) { Text(if (gercek == null) "Oku" else "Yenile", color = Nx.Nane) }
        }
        if (gercek != null) {
            Text(String.format(Locale.US, "≈ %,.2f $", gercek.optDouble("toplam_usd", 0.0)), color = Nx.Metin, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            val bl = gercek.optJSONArray("borsalar")
            if (bl != null) for (i in 0 until bl.length()) {
                val x = bl.getJSONObject(i)
                if (x.has("hata")) { Text("${x.optString("ad")}: ${x.optString("hata")}", color = Nx.Kirmizi, fontSize = 12.sp); continue }
                SatirKV(x.optString("ad"), String.format(Locale.US, "%,.2f $", x.optDouble("toplam_usd", 0.0)))
                val v = x.optJSONArray("varliklar")
                if (v != null) for (j in 0 until minOf(v.length(), 5)) {
                    val a = v.getJSONObject(j)
                    Text("   ${a.optString("varlik")}  ${a.optDouble("miktar")}  ≈ ${String.format(Locale.US, "%,.2f $", a.optDouble("usd"))}", color = Nx.Soluk, fontSize = 12.sp)
                }
                if (x.optInt("degeri_bilinmeyen") > 0) {
                    val adlar = x.optJSONArray("bilinmeyenler")?.let { a -> (0 until a.length()).joinToString(", ") { a.optString(it) } }.orEmpty()
                    Text("   + ${x.optInt("degeri_bilinmeyen")} varlığın değeri bilinmiyor" + (if (adlar.isNotEmpty()) ": $adlar" else ""),
                         color = Nx.Soluk, fontSize = 11.sp)
                }
            }
            Text(gercek.optString("not_"), color = Nx.Soluk, fontSize = 11.sp)
        }
    }
}

@Composable
private fun SatirKV(k: String, v: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(k, color = Nx.Soluk, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(v, color = Nx.Metin, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

private fun para(x: Double) = String.format(Locale.US, "%,.2f USDC", x)
private fun paraIsaretli(x: Double) = (if (x >= 0) "+" else "−") + String.format(Locale.US, "%,.2f", Math.abs(x)) + " USDC"
