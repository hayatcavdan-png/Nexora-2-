package com.nexora.app

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

fun api(base: String, key: String, path: String, post: Boolean = false): String {
    val c = URL(base.trim().trimEnd('/') + path).openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("X-API-Key", key.trim())
    if (post) { c.requestMethod = "POST"; c.doOutput = true; c.outputStream.write("{}".toByteArray()) }
    if (c.responseCode != 200) error("HTTP ${c.responseCode}")
    return c.inputStream.bufferedReader().readText()
}

fun JSONObject.str(k: String): String = if (isNull(k)) "" else optString(k, "")
fun JSONObject.dbl(k: String): Double? = if (!has(k) || isNull(k)) null else optDouble(k).takeIf { !it.isNaN() }

data class Pozisyon(val token: String, val cuzdan: String, val maliyet: Double, val deger: Double)
data class Islem(val ts: Double, val yon: String, val token: String, val cuzdan: String, val karar: String,
                 val neden: String, val kz: Double)
data class Sinyal(val ts: Double, val yon: String, val token: String, val cuzdan: String,
                  val gecikme: Double, val kaynak: String, val karar: String, val neden: String)
data class TakipCuzdan(val adres: String, val durum: String, val hata: String)
data class CuzdanSatiri(val adres: String, val takipte: Boolean, val durum: String, val karar: String,
                        val kazanma: Double?, val karFaktoru: Double?, val kaynakKz: Double?, val ortGetiri: Double?,
                        val tutmaSn: Int?, val paperKopyalanan: Int, val paperKapanan: Int, val paperKz: Double, val paperAcik: Int)
data class Asama(val kod: String, val ad: String, val durum: String, val yuzde: Int, val yapilan: String, val eksik: String)
data class Nokta2(val ts: Double, val deger: Double)

/** Sunucudan okunan her şey. Her uç nokta ayrı denenir: eski sunucuda olmayan bir uç diğerlerini bozmaz. */
class Veri {
    var bagli by mutableStateOf(false)
    var hata by mutableStateOf("")
    var guncelleme by mutableStateOf(0.0)

    var acilDurdurma by mutableStateOf(false)
    var ayarlar by mutableStateOf(JSONObject())

    var nakit by mutableStateOf(0.0)
    var toplam by mutableStateOf(0.0)
    var kz by mutableStateOf(0.0)
    var baslangic by mutableStateOf(100.0)
    var pozisyonlar by mutableStateOf(listOf<Pozisyon>())
    var islemler by mutableStateOf(listOf<Islem>())

    var sinyaller by mutableStateOf(listOf<Sinyal>())
    var takipCuzdanlar by mutableStateOf(listOf<TakipCuzdan>())
    var gecikmeP50 by mutableStateOf<Double?>(null)
    var gecikmeP95 by mutableStateOf<Double?>(null)
    var gecikmeN by mutableStateOf(0)

    var gecmis by mutableStateOf(listOf<Nokta2>())
    var cuzdanlar by mutableStateOf(listOf<CuzdanSatiri>())
    var cuzdanOzet by mutableStateOf(JSONObject())
    var asamalar by mutableStateOf(listOf<Asama>())
    var asamaGuncelleme by mutableStateOf("")
    var rapor by mutableStateOf<JSONObject?>(null)
    var eksikUclar by mutableStateOf(listOf<String>())

    /** Kapanan paper işlemlerin özeti. */
    val kapananlar get() = islemler.filter { it.karar == "KOPYALANDI" && it.yon == "sell" }
    val basariOrani: Double? get() = kapananlar.let { k -> if (k.isEmpty()) null else k.count { it.kz > 0 } * 100.0 / k.size }

    fun yukle(url: String, key: String) {
        val eksik = mutableListOf<String>()
        val d = JSONObject(api(url, key, "/durum"))
        acilDurdurma = d.optBoolean("acil_durdurma")
        ayarlar = d.optJSONObject("ayarlar") ?: JSONObject()
        baslangic = ayarlar.optDouble("start_cash", 100.0)

        val p = JSONObject(api(url, key, "/portfoy"))
        nakit = p.optDouble("cash"); toplam = p.optDouble("equity"); kz = p.optDouble("pnl")
        val pos = p.getJSONArray("positions")
        pozisyonlar = (0 until pos.length()).map {
            val x = pos.getJSONObject(it)
            Pozisyon(x.str("token"), x.str("wallet"), x.optDouble("cost", 0.0), x.optDouble("qty", 0.0) * x.optDouble("last_price", 0.0))
        }
        val t = JSONArray(api(url, key, "/islemler"))
        islemler = (0 until t.length()).map {
            val x = t.getJSONObject(it)
            Islem(x.optDouble("ts", 0.0), x.str("side"), x.str("token"), x.str("wallet"), x.str("decision"), x.str("reason"), x.optDouble("pnl", 0.0))
        }

        try {
            val tk = JSONObject(api(url, key, "/takip"))
            val ss = tk.getJSONArray("sinyaller")
            sinyaller = (0 until ss.length()).map {
                val x = ss.getJSONObject(it)
                Sinyal(x.optDouble("ts", 0.0), x.str("side"), x.str("token"), x.str("wallet"),
                       x.optDouble("latency_s", 0.0), x.str("source"), x.str("decision"), x.str("reason"))
            }
            val cz = tk.getJSONArray("cuzdanlar")
            takipCuzdanlar = (0 until cz.length()).map {
                val x = cz.getJSONObject(it)
                TakipCuzdan(x.str("wallet"), when (x.optInt("quarantined", 0)) { 0 -> "aktif"; 2 -> "bot"; else -> "karantina" }, x.str("last_error"))
            }
            val ws = tk.getJSONObject("gecikme").optJSONObject("ws")
            gecikmeP50 = ws?.dbl("p50"); gecikmeP95 = ws?.dbl("p95"); gecikmeN = ws?.optInt("n") ?: 0
        } catch (e: Exception) { eksik += "takip" }

        try {
            val g = JSONObject(api(url, key, "/gecmis")).getJSONArray("noktalar")
            gecmis = (0 until g.length()).map { val x = g.getJSONObject(it); Nokta2(x.optDouble("ts"), x.optDouble("deger")) }
        } catch (e: Exception) { eksik += "geçmiş" }

        try {
            val c = JSONObject(api(url, key, "/cuzdanlar"))
            cuzdanOzet = c.optJSONObject("ozet") ?: JSONObject()
            val arr = c.getJSONArray("cuzdanlar")
            cuzdanlar = (0 until arr.length()).map {
                val x = arr.getJSONObject(it)
                CuzdanSatiri(x.str("wallet"), x.optBoolean("takipte"), x.str("durum"), x.str("karar"),
                    x.dbl("kazanma_orani"), x.dbl("kar_faktoru"), x.dbl("kaynak_kz"), x.dbl("ort_getiri"),
                    x.dbl("medyan_tutma_sn")?.toInt(), x.optInt("paper_kopyalanan"), x.optInt("paper_kapanan"),
                    x.optDouble("paper_kz", 0.0), x.optInt("paper_acik"))
            }
        } catch (e: Exception) { eksik += "cüzdanlar" }

        try {
            val a = JSONObject(api(url, key, "/asamalar"))
            asamaGuncelleme = a.str("guncelleme")
            val arr = a.getJSONArray("rows")
            asamalar = (0 until arr.length()).map {
                val x = arr.getJSONObject(it)
                Asama(x.str("kod"), x.str("ad"), x.str("durum"), x.optInt("yuzde"), x.str("yapilan"), x.str("eksik"))
            }
        } catch (e: Exception) { eksik += "yol haritası" }

        try { rapor = JSONObject(api(url, key, "/rapor")) } catch (e: Exception) { eksik += "rapor" }
        eksikUclar = eksik
    }
}
