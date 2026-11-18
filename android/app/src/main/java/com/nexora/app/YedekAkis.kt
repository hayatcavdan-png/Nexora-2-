package com.nexora.app

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.content.ContentUris
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection

/**
 * Bounded-memory NEXORA backup download.
 *
 * Never rewrites or prunes an existing backup. Only an incomplete file created
 * by this invocation may be cleaned up after a failed download. The legacy
 * Yedek.indir()/kaydet() API is kept for compatibility but not used by the
 * new manual and scheduled backup flows.
 *
 * NOTE: The server currently provides a plain tar.gz, not an encrypted
 * archive; user-visible Downloads exports are not a secure secret vault.
 */
object YedekAkis {
    private const val FOLDER = "NEXORA"
    private const val MAX_BYTES = 4L * 1024L * 1024L * 1024L
    private val NAME = Regex("nexora_\\d{8}_\\d{6}\\.tar\\.gz")

    private fun copyLimited(source: InputStream, target: OutputStream) {
        val buffer = ByteArray(65536)
        var total = 0L
        while (true) {
            val n = source.read(buffer)
            if (n < 0) break
            total += n
            if (total > MAX_BYTES) error("Yedek güvenli boyut sınırını aştı.")
            target.write(buffer, 0, n)
        }
        target.flush()
    }

    private fun saveNew(ctx: Context, name: String, connection: HttpURLConnection): String {
        if (Build.VERSION.SDK_INT >= 29) {
            val resolver = ctx.contentResolver
            val collection = MediaStore.Downloads.EXTERNAL_CONTENT_URI
            val folder = Environment.DIRECTORY_DOWNLOADS + "/" + FOLDER + "/"
            val selection = "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?"
            resolver.query(collection, arrayOf(MediaStore.MediaColumns._ID),
                           selection, arrayOf(folder, name), null)?.use { rows ->
                if (rows.moveToFirst()) return "İndirilenler/$FOLDER/$name (zaten var, dokunulmadı)"
            }
            val data = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, "application/gzip")
                put(MediaStore.MediaColumns.RELATIVE_PATH, folder)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val destination = resolver.insert(collection, data)
                ?: error("Yedek dosyası oluşturulamadı.")
            var saved = false
            try {
                connection.inputStream.use { input ->
                    val output = resolver.openOutputStream(destination)
                        ?: error("Yedek dosyası açılamadı.")
                    output.use { copyLimited(input, it) }
                }
                val done = ContentValues().apply {
                    put(MediaStore.MediaColumns.IS_PENDING, 0)
                }
                check(resolver.update(destination, done, null, null) > 0) {
                    "Yedek dosyası tamamlanamadı."
                }
                saved = true
                return "İndirilenler/$FOLDER/$name"
            } finally {
                // Only the incomplete artifact we created; prior files stay intact.
                if (!saved) resolver.delete(destination, null, null)
            }
        }

        val folder = File(ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                          ?: ctx.filesDir, FOLDER)
        check(folder.isDirectory || folder.mkdirs()) { "Yedek klasörü oluşturulamadı." }
        val destination = File(folder, name)
        if (destination.exists()) return destination.absolutePath + " (zaten var, dokunulmadı)"
        val partial = File.createTempFile(".nexora-backup-", ".part", folder)
        var committed = false
        try {
            connection.inputStream.use { input ->
                FileOutputStream(partial).use { output -> copyLimited(input, output) }
            }
            if (destination.exists()) return destination.absolutePath
            check(partial.renameTo(destination)) { "Yedek dosyası tamamlanamadı." }
            committed = true
            return destination.absolutePath
        } finally {
            if (!committed) partial.delete()
        }
    }

    fun indirKaydet(ctx: Context, base: String, key: String): Pair<String, String> {
        require(key.isNotBlank()) { "Yedek için kurucu API anahtarı gerekiyor." }
        val connection = AgGuvenligi.endpoint(base, "/yedek/son")
            .openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = false
        connection.useCaches = false
        connection.connectTimeout = 10000
        connection.readTimeout = 60000
        try {
            connection.setRequestProperty("X-API-Key", key.trim())
            val status = connection.responseCode
            if (status != 200) {
                error(if (status == 404) "Sunucuda henüz yedek yok." else "HTTP $status")
            }
            val name = connection.getHeaderField("X-Yedek-Ad")
            require(name != null && NAME.matches(name)) { "Sunucu yedek adı geçersiz." }
            val claimed = connection.contentLengthLong
            require(claimed < 0 || claimed <= MAX_BYTES) {
                "Sunucu yedeği güvenli boyut sınırını aşıyor."
            }
            return name to saveNew(ctx, name, connection)
        } finally {
            connection.disconnect()
        }
    }
}
