package com.nexora.app

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

/** Pure-JVM tests: no phone, network, wallet or real API token required. */
class AgGuvenligiTest {
    private fun rejected(base: String, path: String = "/durum") {
        try {
            AgGuvenligi.endpoint(base, path)
            fail("Unsafe URL accepted: $base")
        } catch (_: IllegalArgumentException) {
            // Expected: no credential-bearing connection may be constructed.
        }
    }

    @Test
    fun trustedHttpsIsAllowed() {
        assertEquals(
            "https://nexora.example.ts.net/durum",
            AgGuvenligi.endpoint("https://nexora.example.ts.net/", "/durum").toString()
        )
    }

    @Test
    fun onDeviceTermuxLoopbackWorksWithoutTls() {
        assertEquals(
            "http://127.0.0.1:8000/durum",
            AgGuvenligi.endpoint("http://127.0.0.1:8000", "/durum").toString()
        )
        assertEquals(
            "http://localhost:8000/durum",
            AgGuvenligi.endpoint("http://localhost:8000", "/durum").toString()
        )
    }

    @Test
    fun privateLanOrTailscaleIpCannotReceivePlaintextSecret() {
        rejected("http://100.105.213.95:8000")
        rejected("http://192.168.1.20:8000")
        rejected("http://10.0.0.2:8000")
        rejected("http://example.com:8000")
        rejected("http://localhost.evil.example")
    }

    @Test
    fun credentialsFragmentsAndRedirectStylePathsAreRejected() {
        rejected("https://admin:password@nexora.example")
        rejected("https://nexora.example/other-api")
        rejected("https://nexora.example?token=secret")
        rejected("https://nexora.example/#secret")
        rejected("ftp://nexora.example")
        rejected("https://nexora.example", "//attacker.example")
        rejected("https://nexora.example", "/durum#secret")
    }
}
