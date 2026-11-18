package com.nexora.app

import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Gizli değerlerin (sunucu API anahtarı, oturum anahtarı) telefonda şifreli saklanması (N35).
 * Anahtar Android Keystore'da üretilir ve cihazdan çıkarılamaz; değerler AES-256-GCM ile şifrelenip
 * SharedPreferences'a "k1:iv:veri" biçiminde yazılır. Eski düz metin değer ilk okumada şifrelenip yeniden yazılır.
 * Keystore kullanılamazsa yeni gizli değer kesinlikle düz metin saklanmaz.
 * Eski düz metin bir kez güvenli şekilde taşınır; anahtar üretilemezse okunmaz.
 */
object Kasa {
    private const val AD = "nexora_kasa_v1"
    private const val ON = "k1:"

    private fun anahtar(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(AD, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        kg.init(KeyGenParameterSpec.Builder(AD, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return kg.generateKey()
    }

    private fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)

    fun sifrele(duz: String): String? = try {
        val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE, anahtar())
        ON + b64(c.iv) + ":" + b64(c.doFinal(duz.toByteArray(Charsets.UTF_8)))
    } catch (e: Exception) { null }

    fun coz(kayit: String): String? {
        if (!kayit.startsWith(ON)) return kayit                     // eski düz metin
        return try {
            val p = kayit.removePrefix(ON).split(":")
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, anahtar(), GCMParameterSpec(128, Base64.decode(p[0], Base64.NO_WRAP)))
            String(c.doFinal(Base64.decode(p[1], Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (e: Exception) { null }                            // çözülemedi (ör. uygulama verisi başka cihaza taşındı)
    }

    /** Okur; düz metin bulursa şifreleyip yerine yazar. Çözülemezse boş döner (kullanıcı anahtarı yeniden girer). */
    fun oku(sp: SharedPreferences, ad: String): String {
        val k = sp.getString(ad, null) ?: return ""
        val d = coz(k) ?: return ""
        if (!k.startsWith(ON) && d.isNotEmpty()) {
            val encrypted = sifrele(d) ?: return ""
            sp.edit().putString(ad, encrypted).apply()
        }
        return d
    }

    /** False means no secret was persisted; an existing encrypted value remains untouched. */
    fun yaz(sp: SharedPreferences, ad: String, deger: String): Boolean {
        if (deger.isEmpty()) { sp.edit().remove(ad).apply(); return true }
        val wrapped = sifrele(deger) ?: return false
        sp.edit().putString(ad, wrapped).apply()
        return true
    }
}
