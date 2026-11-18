package com.nexora.app

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** Sunucudaki son yedeği telefona indirir: İndirilenler/NEXORA (Android 10+), eski sürümlerde uygulama klasörü.
 *  Amaç: sunucu kaybolsa bile verinin bir kopyası telefonda kalsın (N13). */
object Yedek {
    private const val KLASOR = "NEXORA"
    // Historical 7-file retention disabled: previous backups are never deleted.

    fun indir(base: String, key: String): Pair<String, ByteArray> {
        val c = AgGuvenligi.endpoint(base, "/yedek/son").openConnection() as HttpURLConnection
        c.instanceFollowRedirects = false
        c.connectTimeout = 10_000; c.readTimeout = 60_000
        c.setRequestProperty("X-API-Key", key.trim())
        if (c.responseCode != 200) error(if (c.responseCode == 404) "sunucuda henüz yedek yok" else "HTTP ${c.responseCode}")
        val ad = c.getHeaderField("X-Yedek-Ad")?.takeIf { Regex("nexora_\\d{8}_\\d{6}\\.tar\\.gz").matches(it) }
            ?: error("yedek adı geçersiz")
        return ad to c.inputStream.use { it.readBytes() }
    }

    /** Kaydeder ve en yeni [SAKLA] yedeği bırakır. Dönen değer: kullanıcıya gösterilecek konum. */
    fun kaydet(ctx: Context, ad: String, veri: ByteArray): String {
        if (Build.VERSION.SDK_INT >= 29) {
            val cr = ctx.contentResolver
            val koleksiyon = MediaStore.Downloads.EXTERNAL_CONTENT_URI
            val yol = Environment.DIRECTORY_DOWNLOADS + "/" + KLASOR + "/"
            val sec = "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?"
            cr.query(koleksiyon, arrayOf(MediaStore.MediaColumns._ID), sec, arrayOf(yol, ad), null)?.use {
                if (it.moveToFirst()) return "İndirilenler/$KLASOR/$ad (zaten vardı)"
            }
            val cv = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, ad)
                put(MediaStore.MediaColumns.MIME_TYPE, "application/gzip")
                put(MediaStore.MediaColumns.RELATIVE_PATH, yol)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val uri = cr.insert(koleksiyon, cv) ?: error("dosya oluşturulamadı")
            cr.openOutputStream(uri)?.use { it.write(veri) } ?: error("dosya yazılamadı")
            cv.clear(); cv.put(MediaStore.MediaColumns.IS_PENDING, 0); cr.update(uri, cv, null, null)
            // Existing backups are never pruned by a download.
            return "İndirilenler/$KLASOR/$ad"
        }
        val dir = File(ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), KLASOR).apply { mkdirs() }
        File(dir, ad).writeBytes(veri)
        // Preserve every existing backup; never delete old files automatically.
        return File(dir, ad).absolutePath
    }

    /** Bildirim servisinden çağrılır: 6 saatte bir bakar, sunucuda yeni bir yedek varsa indirir. */
    fun otomatik(ctx: Context, base: String, key: String) {
        val sp = ctx.getSharedPreferences("nx", Context.MODE_PRIVATE)
        val simdi = System.currentTimeMillis()
        if (simdi - sp.getLong("yedek_deneme", 0L) < 6 * 3600_000L) return
        sp.edit().putLong("yedek_deneme", simdi).apply()
        // Network stream -> file: no full backup in memory and no old-file pruning.
        val (ad, _) = YedekAkis.indirKaydet(ctx, base, key)
        sp.edit().putString("yedek_son_ad", ad).putLong("yedek_son_ts", simdi).apply()
    }
}
