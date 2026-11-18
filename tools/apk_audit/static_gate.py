#!/usr/bin/env python3
"""Fail-closed source-level checks for Android's credential transport.

This is a fast CI regression guard, NOT a mobile security penetration test.
The CI 'assembleRelease' artifact is still signed with a shared DEBUG key,
so a successful check does not approve a public or real-money release.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android/app"
APP = ANDROID / "src/main"
KOTLIN = APP / "java/com/nexora/app"


def read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"Required security file missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def has(text: str, expected: str, context: str) -> None:
    if expected not in text:
        raise AssertionError(f"{context}: required contract absent")


def not_has(text: str, forbidden: str, context: str) -> None:
    if forbidden in text:
        raise AssertionError(f"{context}: insecure fallback reintroduced")


def main() -> None:
    manifest = read(APP / "AndroidManifest.xml")
    config = read(APP / "res/xml/network_security_config.xml")
    transport = read(KOTLIN / "AgGuvenligi.kt")
    api = read(KOTLIN / "Veri.kt")
    vault = read(KOTLIN / "Kasa.kt")
    backup = read(KOTLIN / "YedekAkis.kt")
    legacy = read(KOTLIN / "Yedek.kt")
    gradle = read(ANDROID / "build.gradle.kts")
    for s in ('android:usesCleartextTraffic="false"',
              'android:networkSecurityConfig="@xml/network_security_config"',
              'android:allowBackup="false"'):
        has(manifest, s, "AndroidManifest")
    has(config, '<base-config cleartextTrafficPermitted="false"', "NetworkSecurityConfig")
    for s in ('hostname == "127.0.0.1"', 'hostname == "localhost"',
              'scheme == "https"', 'scheme == "http" && local',
              "parsed.rawUserInfo == null", "parsed.rawQuery == null"):
        has(transport, s, "AgGuvenligi")
    has(api, "AgGuvenligi.endpoint(base, path)", "API transport")
    has(api, "c.instanceFollowRedirects = false", "API redirects")
    has(api, 'else -> "bilinmiyor"', "Role fail-closed")
    has(vault, "val wrapped = sifrele(deger) ?: return false", "Android Keystore")
    not_has(vault, "sifrele(deger) ?: deger", "Android Keystore")
    has(backup, "copyLimited", "Backup stream")
    has(backup, "AgGuvenligi.endpoint(base, \"/yedek/son\")", "Backup HTTPS")
    has(backup, "connection.instanceFollowRedirects = false", "Backup redirects")
    not_has(legacy, "drop(SAKLA)", "Backup deletion")
    not_has(legacy, "for (f in eski", "Backup deletion")
    has(gradle, 'signingConfig = signingConfigs.getByName("debug")',
        "Explicit test-only signer classification")
    testfile = read(ANDROID / "src/test/java/com/nexora/app/AgGuvenligiTest.kt")
    has(testfile, "privateLanOrTailscaleIpCannotReceivePlaintextSecret", "JVM network regression")
    print("APK_SECURITY_STATIC_GATE: PASS")
    print("APK_RELEASE_SIGNER: DEBUG_ONLY / PRODUCTION_BLOCKED")
    print("NETWORK_COMPATIBILITY: REMOTE_HTTP_DISABLED / HTTPS_MIGRATION_REQUIRED")
    print("REAL_DEVICE_SECURITY_TEST: NOT_PERFORMED")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError) as error:
        print(f"APK_SECURITY_STATIC_GATE: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from None
