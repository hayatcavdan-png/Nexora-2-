package com.nexora.app

import android.content.SharedPreferences
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.security.MessageDigest
import java.security.SecureRandom

/** PIN kilidi: PIN'in kendisi saklanmaz; rastgele tuz + SHA-256 özeti saklanır. 5 hatalı denemede 30 sn bekleme. */
object Kilit {
    private fun ozet(tuz: String, pin: String): String =
        MessageDigest.getInstance("SHA-256").digest((tuz + pin).toByteArray()).joinToString("") { "%02x".format(it) }

    fun var_(sp: SharedPreferences) = sp.contains("pin_ozet")

    fun ayarla(sp: SharedPreferences, pin: String) {
        val tuz = ByteArray(16).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
        sp.edit().putString("pin_tuz", tuz).putString("pin_ozet", ozet(tuz, pin)).apply()
    }

    fun kaldir(sp: SharedPreferences) { sp.edit().remove("pin_tuz").remove("pin_ozet").apply() }

    fun dogru(sp: SharedPreferences, pin: String): Boolean {
        val tuz = sp.getString("pin_tuz", null) ?: return false
        return MessageDigest.isEqual(ozet(tuz, pin).toByteArray(), (sp.getString("pin_ozet", "") ?: "").toByteArray())
    }

    fun gecerliPin(pin: String) = pin.length in 4..8 && pin.all { it.isDigit() }

    // --- Biyometrik (parmak izi / yüz): PIN'e ek kolaylık; PIN her zaman yedek yöntem olarak kalır ---
    private const val YONTEM = androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
    fun biyometrikDestek(ctx: android.content.Context) =
        androidx.biometric.BiometricManager.from(ctx).canAuthenticate(YONTEM) == androidx.biometric.BiometricManager.BIOMETRIC_SUCCESS
    fun biyometrikAcik(sp: SharedPreferences) = sp.getBoolean("biyometrik", false)

    fun biyometrikSor(akt: androidx.fragment.app.FragmentActivity, basari: () -> Unit) {
        val istem = androidx.biometric.BiometricPrompt(akt, androidx.core.content.ContextCompat.getMainExecutor(akt),
            object : androidx.biometric.BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(r: androidx.biometric.BiometricPrompt.AuthenticationResult) = basari()
            })
        istem.authenticate(androidx.biometric.BiometricPrompt.PromptInfo.Builder()
            .setTitle("NEXORA kilidi").setSubtitle("Parmak izi ya da yüz ile açın")
            .setNegativeButtonText("PIN kullan").setAllowedAuthenticators(YONTEM).build())
    }
}

@Composable
fun KilitEkrani(sp: SharedPreferences, acildi: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val akt = ctx as? androidx.fragment.app.FragmentActivity
    val bio = akt != null && Kilit.biyometrikAcik(sp) && Kilit.biyometrikDestek(ctx)
    LaunchedEffect(Unit) { if (bio) Kilit.biyometrikSor(akt!!, acildi) }
    var pin by remember { mutableStateOf("") }
    var hata by remember { mutableStateOf("") }
    var yanlis by remember { mutableIntStateOf(0) }
    var bekle by remember { mutableLongStateOf(0L) }
    Column(Modifier.fillMaxSize().padding(32.dp), verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
           horizontalAlignment = Alignment.CenterHorizontally) {
        Nexo(120.dp, NexoHal.UYKU)
        Logo()
        Icon(Icons.Filled.Lock, null, tint = Nx.Camgobegi, modifier = Modifier.size(40.dp))
        Text("PIN girin", color = Nx.Metin, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
        OutlinedTextField(pin, { if (it.length <= 8 && it.all(Char::isDigit)) pin = it }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), modifier = Modifier.fillMaxWidth())
        if (hata.isNotEmpty()) Text(hata, color = Nx.Kirmizi, fontSize = 13.sp)
        Button({
            val simdi = System.currentTimeMillis()
            if (simdi < bekle) { hata = "Çok fazla hatalı deneme. ${(bekle - simdi) / 1000 + 1} sn bekleyin."; return@Button }
            if (Kilit.dogru(sp, pin)) { yanlis = 0; acildi() }
            else {
                yanlis++; pin = ""
                if (yanlis >= 5) { bekle = simdi + 30_000; yanlis = 0; hata = "5 hatalı deneme: 30 sn bekleyin." }
                else hata = "PIN yanlış (${5 - yanlis} deneme kaldı)"
            }
        }, colors = NxButonRenk(), modifier = Modifier.fillMaxWidth()) { Text("Aç") }
        if (bio) OutlinedButton({ Kilit.biyometrikSor(akt!!, acildi) }, modifier = Modifier.fillMaxWidth()) { Text("Parmak izi / yüz ile aç") }
        Text("PIN'i unutursanız: telefon Ayarları → Uygulamalar → NEXORA → Verileri temizle (sunucu verisi silinmez; " +
             "adres ve anahtarı yeniden girmeniz gerekir).", color = Nx.Soluk, fontSize = 11.sp)
    }
}

@Composable
fun KilitAyari(sp: SharedPreferences) {
    var acik by remember { mutableStateOf(Kilit.var_(sp)) }
    var pin1 by remember { mutableStateOf("") }
    var pin2 by remember { mutableStateOf("") }
    var mesaj by remember { mutableStateOf("") }
    Kart(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(Icons.Filled.Lock, null, tint = Nx.Mor)
            Column(Modifier.weight(1f)) {
                Text("Uygulama kilidi", color = Nx.Metin, fontSize = 15.sp)
                Text(if (acik) "Açık · açılışta ve 1 dk arka planda kaldıktan sonra PIN sorulur" else "Kapalı",
                     color = Nx.Soluk, fontSize = 12.sp)
            }
            if (acik) TextButton({ Kilit.kaldir(sp); acik = false; mesaj = "Kilit kaldırıldı" }) { Text("Kaldır", color = Nx.Kirmizi) }
        }
        val ctx = androidx.compose.ui.platform.LocalContext.current
        if (acik && Kilit.biyometrikDestek(ctx)) {
            var bio by remember { mutableStateOf(Kilit.biyometrikAcik(sp)) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Parmak izi / yüz ile aç", color = Nx.Metin, fontSize = 15.sp)
                    Text("PIN yedek yöntem olarak kalır", color = Nx.Soluk, fontSize = 12.sp)
                }
                Switch(bio, { bio = it; sp.edit().putBoolean("biyometrik", it).apply() },
                    colors = SwitchDefaults.colors(checkedTrackColor = Nx.Yesil))
            }
        }
        if (!acik) {
            OutlinedTextField(pin1, { if (it.length <= 8 && it.all(Char::isDigit)) pin1 = it }, label = { Text("Yeni PIN (4-8 rakam)") },
                singleLine = true, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), modifier = Modifier.fillMaxWidth())
            OutlinedTextField(pin2, { if (it.length <= 8 && it.all(Char::isDigit)) pin2 = it }, label = { Text("PIN tekrar") },
                singleLine = true, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), modifier = Modifier.fillMaxWidth())
            Button({
                mesaj = when {
                    !Kilit.gecerliPin(pin1) -> "PIN 4-8 rakam olmalı"
                    pin1 != pin2 -> "PIN'ler aynı değil"
                    else -> { Kilit.ayarla(sp, pin1); acik = true; pin1 = ""; pin2 = ""; "Kilit açıldı" }
                }
            }, colors = NxButonRenk(), modifier = Modifier.fillMaxWidth()) { Text("Kilidi aç") }
        }
        if (mesaj.isNotEmpty()) Text(mesaj, color = Nx.Soluk, fontSize = 12.sp)
    }
}
