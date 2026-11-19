package com.nexora.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import java.net.URI
import java.net.URL
import java.util.Locale

/**
 * Credential-carrying NEXORA API transport.
 *
 * Remote API transport uses HTTPS by default.
 * The existing Tailscale WireGuard peer is a scoped compatibility exception,
 * allowed only while Android reports the VPN transport active.
 * Termux on this phone remains available over loopback HTTP.
 *
 * Reject credentials in URLs, redirects, query-bearing base URLs and non-root
 * prefixes so a copied/phishing endpoint cannot silently receive API keys.
 */
object AgGuvenligi {
    private const val TAILSCALE_IP = "100.105.213.95"
    private const val TAILSCALE_PORT = 8000
    @Volatile private var context: Context? = null

    /** Initialize from Activity and background Service before making requests. */
    fun hazirla(ctx: Context) { context = ctx.applicationContext }

    private fun vpnEtkinMi(): Boolean {
        val ctx = context ?: return false
        return try {
            val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
                ?: return false
            val network = cm.activeNetwork ?: return false
            cm.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
        } catch (_: Exception) { false }
    }

    fun endpoint(base: String, path: String, vpnEtkin: Boolean = vpnEtkinMi()): URL {
        require(path.startsWith("/") && !path.startsWith("//") &&
                !path.contains("#") && !path.contains("\r") && !path.contains("\n")) {
            "API yolu geçersiz."
        }
        val raw = base.trim()
        require(raw.length in 8..512) { "Sunucu adresi geçersiz." }
        val parsed = try { URI(raw) }
                     catch (_: Exception) { throw IllegalArgumentException("Sunucu adresi geçersiz.") }
        val scheme = parsed.scheme?.lowercase(Locale.ROOT)
        val hostname = parsed.host?.lowercase(Locale.ROOT)
        require(hostname != null && parsed.rawUserInfo == null &&
                parsed.rawQuery == null && parsed.rawFragment == null &&
                (parsed.rawPath.isNullOrEmpty() || parsed.rawPath == "/") &&
                parsed.port <= 65535) { "Sunucu adresi geçersiz." }
        val local = hostname == "127.0.0.1" || hostname == "localhost" || hostname == "[::1]"
        val tailnet = scheme == "http" && hostname == TAILSCALE_IP &&
                parsed.port == TAILSCALE_PORT
        require(scheme == "https" || (scheme == "http" && local) || (tailnet && vpnEtkin)) {
            if (tailnet) "Tailscale VPN açık olmalı; bağlantıyı açıp yeniden deneyin."
            else "Uzak sunucu için HTTPS gerekir. Yalnızca tanımlı Tailscale IP'sine HTTP izinlidir."
        }
        return URL(raw.trimEnd('/') + path)
    }
}
