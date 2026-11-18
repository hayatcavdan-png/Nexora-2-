package com.nexora.app

import java.net.URI
import java.net.URL
import java.util.Locale

/**
 * Credential-carrying NEXORA API transport.
 *
 * Remote endpoints MUST use HTTPS, including Tailscale/private IP addresses:
 * a private network is not equivalent to end-to-end application TLS.
 * Termux on the SAME phone remains available over loopback HTTP only.
 *
 * Reject credentials in URLs, redirects, query-bearing base URLs and non-root
 * prefixes so a copied/phishing endpoint cannot silently receive API keys.
 */
object AgGuvenligi {
    fun endpoint(base: String, path: String): URL {
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
        require(scheme == "https" || (scheme == "http" && local)) {
            "Uzak sunucu için HTTPS gerekir. Tailscale Serve veya TLS ters vekili kurun."
        }
        return URL(raw.trimEnd('/') + path)
    }
}
