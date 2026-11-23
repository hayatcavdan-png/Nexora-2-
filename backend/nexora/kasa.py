"""Sunucu tarafı gizli değer kasası (N35): kullanıcıların ileride bağlayacağı borsa API anahtarları gibi değerler
veritabanına YALNIZCA şifreli yazılır.

Yalnızca Python standart kütüphanesi (sunucuya paket kurulmaz):
  - Ana anahtar: 32 rastgele bayt, dosyada (varsayılan backend/kasa.key, izin 600). Git'e ve yedeklere girmez.
  - Alt anahtarlar: HMAC-SHA256 ile türetilir (şifreleme ve doğrulama için ayrı).
  - Şifreleme: HMAC-SHA256 tabanlı sayaç kipi (her kayıtta rastgele 16 bayt nonce); ardından şifreli metin
    üzerinde HMAC-SHA256 etiketi (önce şifrele, sonra doğrula). Etiket tutmazsa değer ASLA çözülmez.
  - Biçim: "v1:" + base64(nonce | şifreli | etiket). Kayıt bağlamı (ör. üye kimliği + alan adı) etikete katılır:
    bir üyenin şifreli değeri başka üyenin satırına kopyalanırsa çözülmez.
Ana anahtar kaybolursa şifreli değerler geri alınamaz (kullanıcılar anahtarlarını yeniden bağlar); bu bilinçli bir tercihtir."""
from .dosya import json_oku, metin_oku, bayt_oku
import base64, hashlib, hmac, os, secrets

ON = "v1:"
NONCE, ETIKET = 16, 32


class KasaHatasi(ValueError):
    pass


def _turet(ana, ad):
    return hmac.new(ana, b"nexora-kasa/" + ad, hashlib.sha256).digest()


def _akis(k, nonce, n):
    out, sayac = bytearray(), 0
    while len(out) < n:
        out += hmac.new(k, nonce + sayac.to_bytes(8, "big"), hashlib.sha256).digest()
        sayac += 1
    return bytes(out[:n])


class Kasa:
    def __init__(self, yol=None, ana=None):
        if ana is None:
            yol = yol or os.getenv("KASA_ANAHTAR", "kasa.key")
            ana = self._yukle_ya_da_olustur(yol)
        if not isinstance(ana, (bytes, bytearray)) or len(ana) != 32: raise KasaHatasi("ana anahtar 32 bayt olmalı")
        self._sif, self._dog = _turet(bytes(ana), b"sifre"), _turet(bytes(ana), b"dogrula")

    @staticmethod
    def _yukle_ya_da_olustur(yol):
        if os.path.exists(yol):
            ham = bayt_oku(yol).strip()
            try:
                ana = bytes.fromhex(ham.decode())
            except ValueError:
                raise KasaHatasi("kasa anahtar dosyası bozuk") from None
            if len(ana) != 32: raise KasaHatasi("kasa anahtar dosyası bozuk")
            return ana
        ana = secrets.token_bytes(32)
        fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)       # yarışta üzerine yazmaz
        with os.fdopen(fd, "w") as f: f.write(ana.hex() + "\n")
        return ana

    def sifrele(self, duz, baglam=""):
        if not isinstance(duz, str) or not duz: raise KasaHatasi("şifrelenecek değer boş")
        nonce = secrets.token_bytes(NONCE)
        veri = duz.encode()
        sifreli = bytes(a ^ b for a, b in zip(veri, _akis(self._sif, nonce, len(veri))))
        etiket = hmac.new(self._dog, baglam.encode() + b"\0" + nonce + sifreli, hashlib.sha256).digest()
        return ON + base64.b64encode(nonce + sifreli + etiket).decode()

    def coz(self, kayit, baglam=""):
        if not isinstance(kayit, str) or not kayit.startswith(ON): raise KasaHatasi("şifreli kayıt değil")
        try:
            ham = base64.b64decode(kayit[len(ON):], validate=True)
        except (ValueError, TypeError):
            raise KasaHatasi("şifreli kayıt bozuk") from None
        if len(ham) < NONCE + ETIKET + 1: raise KasaHatasi("şifreli kayıt bozuk")
        nonce, sifreli, etiket = ham[:NONCE], ham[NONCE:-ETIKET], ham[-ETIKET:]
        beklenen = hmac.new(self._dog, baglam.encode() + b"\0" + nonce + sifreli, hashlib.sha256).digest()
        if not hmac.compare_digest(etiket, beklenen): raise KasaHatasi("doğrulama başarısız (değiştirilmiş ya da başka kayda ait)")
        return bytes(a ^ b for a, b in zip(sifreli, _akis(self._sif, nonce, len(sifreli)))).decode()


def maskele(deger, goster=4):
    """Ekranda gösterim: yalnızca son birkaç karakter ('••••••3f6g')."""
    return "••••••" + deger[-goster:] if isinstance(deger, str) and len(deger) > goster else "••••"
