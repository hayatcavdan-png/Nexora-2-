package com.nexora.app

import android.content.Intent
import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * New isolated strategy lab. No WebView bridge to native app, no trading button
 * and no Telegram / promotional channel. Founder-private redacted endpoint only.
 */
@Composable
fun StratejiLaboratuvari(url: String, key: String) {
    val session = if (key.isBlank()) Oturum.deger else ""
    var snapshot by remember(url, key, session) { mutableStateOf<JSONObject?>(null) }
    var problem by remember(url, key, session) { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    var pending by remember { mutableStateOf(true) }

    LaunchedEffect(url, key, session, reload) {
        pending = true
        snapshot = null
        problem = ""
        try {
            val response = withContext(Dispatchers.IO) {
                JSONObject(api(url, key, "/admin/strategy-lab", zamanAsimi = 12_000,
                    oturum = session))
            }
            require(response.optInt("schema_version") == 1)
            require(response.optString("mode") == "PAPER_STRATEGY_LAB")
            require(response.opt("real_order") == false)
            require(response.opt("live_trading") == false)
            require(response.optJSONObject("capabilities") != null)
            require(response.optJSONArray("equity") != null)
            snapshot = response
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            problem = when {
                e.message?.contains("404") == true ->
                    "Sunucuda Strateji Laboratuvarı henüz dağıtılmadı."
                e.message?.contains("401") == true -> "Kurucu girişi gerekiyor."
                e.message?.contains("403") == true -> "Bu bölüm kurucuya özeldir."
                else -> "Strateji laboratuvarına erişilemiyor."
            }
        } finally {
            pending = false
        }
    }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        NeonKart(Modifier.fillMaxWidth(), kenar = Nx.KenarParlak, dolgu = Nx.DolguMor) {
            Text("NEXORA · Strateji Lab", fontSize = 23.sp, color = Nx.Metin,
                fontWeight = FontWeight.Bold)
            Etiket("7 ARAÇ · SANAL / SALT OKUNUR", Nx.Sari)
            Text("Yeni havuz → risk kapısı → sanal strateji → geriye dönük sonuç → grafik",
                color = Nx.Soluk, fontSize = 12.sp)
            Text("Gerçek emir, cüzdan imzası ve otomatik para kullanımı yok.",
                color = Nx.Sari, fontSize = 12.sp)
            OutlinedButton(onClick = { reload++ }, enabled = !pending) {
                Text(if (pending) "Kontrol ediliyor…" else "Laboratuvarı yenile")
            }
        }

        if (problem.isNotBlank()) Kart(Modifier.fillMaxWidth()) {
            Text(problem, color = Nx.Sari)
        }
        val report = snapshot
        if (report != null) {
            val status = report.optString("snapshot_status")
            Kart(Modifier.fillMaxWidth()) {
                Text("Laboratuvar durumu", color = Nx.Metin,
                    fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text(when (status) {
                    "OFFLINE_SNAPSHOT" -> "Doğrulanmış çevrimdışı araştırma raporu"
                    "NOT_CONFIGURED" -> "Henüz veri dosyası bağlı değil; canlı tarama başlatılmadı."
                    else -> "Rapor şu anda kullanılamıyor."
                }, color = Nx.Soluk, fontSize = 12.sp)
                Text("Başlangıç sanal sermaye: 100 USDT",
                    color = Nx.Metin, fontWeight = FontWeight.SemiBold)
            }
            // Dedicated paper automation status: never indicate live order execution.
            report.optJSONObject("auto_paper")?.let { auto ->
                Kart(Modifier.fillMaxWidth()) {
                    Text("Otomatik işlem araştırması", color = Nx.Metin,
                        fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    val state = auto.optString("status")
                    Text(when (state) {
                        "LEDGER_AVAILABLE" -> "Ayrı sanal defter okunabiliyor."
                        "DISABLED" -> "Otomatik sanal araştırma kapalı."
                        "PATH_NOT_CONFIGURED" -> "Bağımsız sanal defter yolu tanımlanmamış."
                        else -> "Sanal defter şu anda okunamıyor."
                    }, color = Nx.Soluk, fontSize = 12.sp)
                    if (state == "LEDGER_AVAILABLE") {
                        Text("Toplam sanal çalışma: " + auto.optInt("total_studies"),
                            color = Nx.Metin, fontSize = 12.sp)
                        Text("Yakın dönem açık çalışma: " +
                            auto.optInt("active_recent_studies"), color = Nx.Soluk, fontSize = 12.sp)
                        Text("Sanal SAT sinyalleri: " +
                            auto.optInt("recent_sell_signals") +
                            " · Çıkış kotasyonu yok: " +
                            auto.optInt("recent_exit_unavailable"),
                            color = Nx.Soluk, fontSize = 12.sp)
                        Text("Kalan araştırma bakiyesi: " +
                            auto.optString("available_research_cash_usdt") + " USDT",
                            color = Nx.Soluk, fontSize = 12.sp)
                        Text("Önceden seçilmiş vadede sanal SAT sinyali: " +
                             auto.optInt("precommitted_sell_quote_signals") +
                             " · Satış kotasyonu bulunamadı: " +
                             auto.optInt("precommitted_exit_unavailable"),
                             color = Nx.Soluk, fontSize = 12.sp)
                    }
                    auto.optJSONObject("profit_research")?.let { guard ->
                        HorizontalDivider()
                        Text("Net Kâr Koruması · İleri Test", color = Nx.Metin,
                            fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        Text("Durum: " + guard.optString("status"),
                            color = Nx.Soluk, fontSize = 12.sp)
                        Text("Olgunlaşmış sanal örnek: " +
                            guard.optInt("mature_samples"),
                            color = Nx.Soluk, fontSize = 12.sp)
                        val chosen = guard.optInt("recommended_horizon_min", 0)
                        Text(if (chosen > 0) "Araştırma çıkış ufku: ${chosen} dk" else
                            "Henüz istatistiksel olarak desteklenen çıkış ufku yok.",
                            color = Nx.Soluk, fontSize = 12.sp)
                        val intake = guard.optJSONObject("intake")
                        if (intake?.optBoolean("allow_new_paper") == false) {
                            Text("Yeni sanal işlemler koruma nedeniyle durduruldu.",
                                color = Nx.Sari, fontSize = 12.sp)
                        }
                        val fw = guard.optJSONObject("forward_stress")
                        if (fw != null && fw.optInt("selected_paper_studies") > 0) {
                            Text("İleri testte seçilen sanal çalışmalar: " +
                                fw.optInt("selected_paper_studies"),
                                color = Nx.Soluk, fontSize = 12.sp)
                            Text("Kayıp ve eksik kotasyon stres sonucu: " +
                                fw.optString("stress_net_usdt") + " USDT",
                                color = Nx.Soluk, fontSize = 12.sp)
                        }
                        Text("Bunlar karşı-olgusal Jupiter teklifleri ve stres " +
                             "varsayımlarıdır; gerçekleşmiş net kâr değildir.",
                            color = Nx.Sari, fontSize = 11.sp)
                    }
                    auto.optJSONObject("ai_signal_research")?.let { ai ->
                        HorizontalDivider()
                        Text("Yapay Zekâ Destekli Sinyal", color = Nx.Metin,
                            fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        val ready = ai.optString("status") == "PAPER_FILTER_VALIDATED"
                        Text(
                            if (ready) "İleri test kapıları geçti · yalnızca sanal sinyal filtresi"
                            else "Gölge öğrenme · geçmiş yeterli değil, kararları değiştirmiyor",
                            color = if (ready) Nx.Nane else Nx.Sari, fontSize = 12.sp
                        )
                        Text("Önceden kaydedilmiş olgun örnek: " +
                             ai.optInt("trained_samples"), color = Nx.Soluk, fontSize = 12.sp)
                        ai.optJSONObject("walk_forward")?.let { walk ->
                            Text("İleri test: " + walk.optInt("walk_forward_checked") +
                                 " değerlendirme · " + walk.optInt("walk_forward_selected") +
                                 " seçilmiş sanal işlem",
                                 color = Nx.Soluk, fontSize = 12.sp)
                            if (!walk.isNull("selected_stress_lower_bound_usdt")) {
                                Text("Stres net alt sınırı: " +
                                     walk.optString("selected_stress_lower_bound_usdt") +
                                     " USDT / sanal deneme",
                                     color = Nx.Soluk, fontSize = 12.sp)
                            }
                        }
                        Text("Makine öğrenmesi çıktısı, kazanma olasılığı veya " +
                             "gerçekleşmiş emir/kâr kanıtı değildir.",
                            color = Nx.Sari, fontSize = 11.sp)
                    }
                    Text("Bunlar gerçekleşmiş işlemler değildir. Defterin bulunması " +
                         "otomatik tarayıcının çalıştığını kanıtlamaz.",
                        color = Nx.Sari, fontSize = 11.sp)
                }
            }
            Kart(Modifier.fillMaxWidth()) {
                Text("Yedi analiz aracı", color = Nx.Metin,
                    fontWeight = FontWeight.Bold, fontSize = 17.sp)
                val names = listOf(
                    "raydium_sdk_v2" to "Raydium · yeni havuz",
                    "orca_whirlpools" to "Orca · Whirlpools",
                    "solana_py" to "solana-py · Solana hesabı",
                    "vectorbt" to "VectorBT · strateji testi",
                    "duckdb" to "DuckDB · veri analizi",
                    "quantstats" to "QuantStats · risk karnesi",
                    "lightweight_charts" to "Lightweight Charts · grafik",
                )
                val tools = report.optJSONObject("capabilities")
                names.forEach { (id, label) ->
                    val statusInfo = tools?.optJSONObject(id)
                    val available = statusInfo?.optBoolean("installed") == true
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(label, color = Nx.Soluk, fontSize = 12.sp,
                            modifier = Modifier.weight(1f))
                        Text(if (available) "Python hazır" else "İsteğe bağlı",
                            color = if (available) Nx.Yesil else Nx.Sari, fontSize = 11.sp)
                    }
                }
                Text("İsteğe bağlı araçlar sunucunun ayrı ortamında yüklenir; durumları gerçek işlem izni değildir.",
                    color = Nx.Soluk, fontSize = 11.sp)
            }

            val metrics = report.optJSONObject("historical_test")
            val optional = report.optJSONObject("optional_reports")
            if (metrics != null) {
                Kart(Modifier.fillMaxWidth()) {
                    Text("100 USDT · Tarihsel strateji testi",
                        color = Nx.Metin, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    Text("Sanal son değer: " + metrics.optString("final_mark_usdt") + " USDT",
                        color = Nx.Metin, fontWeight = FontWeight.SemiBold)
                    Text("Sanal işlem adımları: " + metrics.optInt("trades"),
                        color = Nx.Soluk, fontSize = 12.sp)
                    Text("Maliyet varsayımı: " + metrics.optString("fee_bps") +
                         " baz puan ücret + " + metrics.optString("slippage_bps") +
                         " baz puan fiyat kayması", color = Nx.Soluk, fontSize = 12.sp)
                    Text("Geçmiş çalışma; gerçek alım, satış veya getiri kanıtı değildir.",
                        color = Nx.Sari, fontSize = 11.sp)
                }
            }
            if (optional != null && optional.length() > 0) {
                Kart(Modifier.fillMaxWidth()) {
                    Text("İleri analiz", color = Nx.Metin,
                        fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    optional.optJSONObject("vectorbt")?.let {
                        Text("VectorBT · sanal son değer: " +
                            it.optString("final_equity_usdt") + " USDT",
                            color = Nx.Soluk, fontSize = 12.sp)
                    }
                    optional.optJSONObject("quantstats")?.let {
                        Text("QuantStats · maksimum geri çekilme: %" +
                            it.optString("max_drawdown_pct"),
                            color = Nx.Soluk, fontSize = 12.sp)
                    }
                    optional.optJSONObject("duckdb")?.let {
                        Text("DuckDB · analiz edilen sanal kayıt: " +
                            it.optString("evaluated_rows"),
                            color = Nx.Soluk, fontSize = 12.sp)
                    }
                }
            }
            val ranking = report.optJSONArray("candidates")
            Kart(Modifier.fillMaxWidth()) {
                Text("Araştırılan tokenlar", fontSize = 17.sp,
                    color = Nx.Metin, fontWeight = FontWeight.Bold)
                if (ranking == null || ranking.length() == 0) {
                    Text("Henüz doğrulanmış aday raporu yok.", color = Nx.Soluk)
                } else {
                    for (i in 0 until minOf(ranking.length(), 20)) {
                        val row = ranking.optJSONObject(i) ?: continue
                        HorizontalDivider()
                        SelectionContainer {
                            Text(row.optString("mint"), color = Nx.Metin, fontSize = 11.sp)
                        }
                        val score = row.opt("score")
                        Text("Araştırma puanı: " +
                            if (score is Int) "$score / 100" else "Kanıt yetersiz",
                            color = Nx.Sari, fontSize = 12.sp)
                        Text("Durum: " + row.optString("status"),
                            color = Nx.Soluk, fontSize = 11.sp)
                    }
                }
            }

            val equity = report.optJSONArray("equity")
            Kart(Modifier.fillMaxWidth()) {
                Text("Sanal sermaye grafiği", color = Nx.Metin,
                    fontSize = 17.sp, fontWeight = FontWeight.Bold)
                Text("Gerçekleşmiş kazanç değildir. Geçmiş sentetik değerlerden çizilir.",
                    color = Nx.Soluk, fontSize = 12.sp)
                if (equity != null && equity.length() >= 2) {
                    StratejiLabGrafik(equity)
                } else {
                    Text("Grafik için en az iki doğrulanmış ölçüm gerekli.",
                        color = Nx.Soluk, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun StratejiLabGrafik(equity: JSONArray) {
    val context = LocalContext.current
    val values = remember(equity) {
        JSONArray().apply {
            for (i in 0 until minOf(1000, equity.length())) {
                val row = equity.optJSONObject(i) ?: continue
                val ts = row.optLong("ts", 0)
                val value = row.optDouble("equity", Double.NaN)
                if (ts > 0 && value.isFinite() && value > 0) {
                    put(JSONObject().put("time", ts).put("value", value))
                }
            }
        }.toString()
    }
    AndroidView(modifier = Modifier.fillMaxWidth().height(268.dp), factory = { ctx ->
        WebView(ctx).apply {
            settings.javaScriptEnabled = true
            settings.allowFileAccess = true
            settings.allowContentAccess = false
            settings.domStorageEnabled = false
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView, url: String?) {
                    view.evaluateJavascript("window.renderSeries($values);", null)
                }
                override fun shouldOverrideUrlLoading(
                    view: WebView, request: WebResourceRequest
                ): Boolean {
                    val uri = request.url
                    if (uri.host == "www.tradingview.com" &&
                        uri.scheme == "https" && request.isForMainFrame) {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.tradingview.com/")))
                    }
                    // No other external navigation from graph.
                    return true
                }
            }
            loadUrl("file:///android_asset/strategy_lab/chart.html")
        }
    }, update = { view ->
        view.evaluateJavascript("window.renderSeries && window.renderSeries($values);", null)
    })
}
