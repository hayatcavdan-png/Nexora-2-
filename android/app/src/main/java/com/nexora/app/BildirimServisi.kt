package com.nexora.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import org.json.JSONObject

/** Sunucunun /olaylar akışını 30 sn'de bir yoklar ve yeni olayları bildirim olarak gösterir. */
class BildirimServisi : Service() {
    private val kapsam = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var gorev: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        kanallariKur(this)
        val surekli = NotificationCompat.Builder(this, KANAL_SERVIS)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("NEXORA izleniyor")
            .setContentText("Yeni işlem ve uyarılar bildirilecek")
            .setOngoing(true)
            .setContentIntent(uygulamayiAc(this))
            .build()
        val tur = if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0
        ServiceCompat.startForeground(this, 1, surekli, tur)
        if (gorev?.isActive != true) gorev = kapsam.launch { dongu() }
        return START_STICKY
    }

    override fun onDestroy() {
        kapsam.cancel()
        super.onDestroy()
    }

    private suspend fun dongu() {
        val sp = getSharedPreferences("nx", Context.MODE_PRIVATE)
        if (!sp.contains("bildirim_son")) {
            sp.edit().putString("bildirim_son", (System.currentTimeMillis() / 1000.0).toString()).apply()
        }
        var hataBas = 0L          // ilk başarısız denemenin zamanı (0: sorun yok)
        var uyarildi = false
        while (true) {
            try {
                val url = sp.getString("url", "http://127.0.0.1:8000")!!
                val key = Kasa.oku(sp, "key")
                val oturum = if (key.isEmpty()) Kasa.oku(sp, "oturum") else ""      // 5.25.1: anahtar yoksa üye oturumu (iki adımlı girişle)
                val son = sp.getString("bildirim_son", "0")!!
                if (key.isNotEmpty() || oturum.isNotEmpty()) {
                    val r = JSONObject(api(url, key, "/olaylar?son=$son", oturum = oturum))
                    val arr = r.getJSONArray("olaylar")
                    var enSon = son.toDoubleOrNull() ?: 0.0
                    for (i in 0 until arr.length()) {
                        val e = arr.getJSONObject(i)
                        goster(e.optString("id"), e.optString("baslik"), e.optString("metin"), e.optString("tur"))
                        enSon = maxOf(enSon, e.optDouble("ts", enSon))
                    }
                    sp.edit().putString("bildirim_son", enSon.toString()).apply()
                    try { Yedek.otomatik(this, url, key, oturum) } catch (e: Exception) { /* yedek bir sonraki denemede */ }
                    if (uyarildi) goster("baglanti_geri", "Sunucuya yeniden bağlanıldı", "NEXORA tekrar izleniyor.", "bilgi")
                    hataBas = 0L; uyarildi = false
                }
            } catch (e: Exception) {
                // Sunucu kapalı ya da ağ yok. 5 dakika sürerse bir kez uyar (Termux kapanmış olabilir).
                val simdi = System.currentTimeMillis()
                if (hataBas == 0L) hataBas = simdi
                if (!uyarildi && simdi - hataBas >= 5 * 60_000L) {
                    goster("baglanti", "Sunucuya ulaşılamıyor",
                        "5 dakikadır bağlantı yok. Termux kapanmış olabilir: cd ~/nexora_build/nexora_2 && ./nexora baslat", "risk")
                    uyarildi = true
                }
            }
            delay(30_000)
        }
    }

    private fun goster(id: String, baslik: String, metin: String, tur: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS) !=
            android.content.pm.PackageManager.PERMISSION_GRANTED) return
        val n = NotificationCompat.Builder(this, KANAL_OLAY)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(baslik)
            .setContentText(metin)
            .setStyle(NotificationCompat.BigTextStyle().bigText(metin))
            .setPriority(if (tur == "risk" || tur == "bot") NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(uygulamayiAc(this))
            .build()
        NotificationManagerCompat.from(this).notify(id.hashCode(), n)
    }

    companion object {
        const val KANAL_OLAY = "nexora_olay"
        const val KANAL_SERVIS = "nexora_servis"

        fun kanallariKur(ctx: Context) {
            if (Build.VERSION.SDK_INT >= 26) {
                val nm = ctx.getSystemService(NotificationManager::class.java)
                nm.createNotificationChannel(NotificationChannel(KANAL_OLAY, "İşlem ve uyarılar", NotificationManager.IMPORTANCE_HIGH))
                nm.createNotificationChannel(NotificationChannel(KANAL_SERVIS, "Arka plan izleme", NotificationManager.IMPORTANCE_LOW))
            }
        }

        fun uygulamayiAc(ctx: Context): PendingIntent =
            PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

        fun baslat(ctx: Context) = ContextCompat.startForegroundService(ctx, Intent(ctx, BildirimServisi::class.java))
        fun durdur(ctx: Context) { ctx.stopService(Intent(ctx, BildirimServisi::class.java)) }
    }
}
