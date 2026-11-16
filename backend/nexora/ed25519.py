"""Saf Python Ed25519 (RFC 8032): anahtar türetme ve imza. Solana işlem imzası bu algoritmadır.
Dış bağımlılık yok; sunucuda ek paket kurmadan pilot cüzdan anahtarı üretmek için. Yavaştır (imza ~ms), iş için yeterli.
Gizli anahtar hiçbir zaman loglanmaz ya da döndürülen hata metinlerine konmaz."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
I = pow(2, (P - 1) // 4, P)


def _inv(x): return pow(x, P - 2, P)


def _xrec(y):
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P: x = x * I % P
    if x % 2: x = P - x
    return x


_BY = 4 * _inv(5) % P
_B = (_xrec(_BY), _BY, 1, _xrec(_BY) * _BY % P)      # genişletilmiş koordinatlar (X, Y, Z, T)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % P
    b = (p[1] + p[0]) * (q[1] + q[0]) % P
    c = 2 * p[3] * q[3] * D % P
    d = 2 * p[2] * q[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(s, p):
    q = (0, 1, 1, 0)
    while s:
        if s & 1: q = _add(q, p)
        p = _add(p, p); s >>= 1
    return q


def _enc(p):
    zi = _inv(p[2]); x = p[0] * zi % P; y = p[1] * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _h(*parts): return hashlib.sha512(b"".join(parts)).digest()


def _gizli(seed):
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32: raise ValueError("tohum 32 bayt olmalı")
    h = _h(bytes(seed))
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8; a |= 1 << 254
    return a, h[32:]


def acik_anahtar(seed):
    a, _ = _gizli(seed)
    return _enc(_mul(a, _B))


def imzala(seed, mesaj):
    a, onek = _gizli(seed)
    A = _enc(_mul(a, _B))
    r = int.from_bytes(_h(onek, mesaj), "little") % L
    R = _enc(_mul(r, _B))
    k = int.from_bytes(_h(R, A, mesaj), "little") % L
    return R + ((r + k * a) % L).to_bytes(32, "little")


_ALFABE = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = _ALFABE[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
