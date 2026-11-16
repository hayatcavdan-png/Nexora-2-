import os, unittest
from nexora import hesap_turu as H

ALF = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
P = 2 ** 255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P


def enc(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = ALF[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def referans(b):
    """Bağımsız kontrol: RFC 8032 nokta açma (karekök hesaplayıp eğri denklemini doğrular)."""
    y = int.from_bytes(b, "little") & ((1 << 255) - 1); isaret = b[31] >> 7
    if y >= P: return False
    u, v = (y * y - 1) % P, (D * y * y + 1) % P
    x = u * pow(v, 3, P) * pow(u * pow(v, 7, P), (P - 5) // 8, P) % P
    if v * x * x % P == (-u) % P: x = x * pow(2, (P - 1) // 4, P) % P
    elif v * x * x % P != u: return False
    if x == 0 and isaret: return False
    return (-x * x + y * y - 1 - D * x * x * y * y) % P == 0


class Fake:
    def __init__(self, hesaplar): self.h, self.cagri = hesaplar, []
    def call(self, m, params):
        self.cagri.append((m, params)); return {"value": [self.h.get(a) for a in params[0]]}


class Test(unittest.TestCase):
    def test_egri_bagimsiz_referansla_ayni(self):
        for _ in range(500):
            b = os.urandom(32)
            self.assertEqual(H.egri_ustunde(enc(b)), referans(b))

    def test_bilinen_adresler(self):
        self.assertTrue(H.egri_ustunde("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"))
        self.assertFalse(H.egri_ustunde("kisa"))
        self.assertFalse(H.egri_ustunde("0OIl" * 11))

    def test_siniflandir(self):
        on, off = [], []
        while len(on) < 4 or len(off) < 1:
            b = os.urandom(32); (on if referans(b) else off).append(enc(b))
        k, prog, ver, bos = on[:4]; pda = off[0]
        cl = Fake({k: dict(owner=H.SISTEM, executable=False), prog: dict(owner="BPFLoaderUpgradeab1e11111111111111111111111", executable=True),
                   ver: dict(owner="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", executable=False)})
        s = H.siniflandir(cl, [k, prog, ver, bos, pda, "BORSA" + k[5:]], bilinen={"BORSA" + k[5:]: "borsa"})
        self.assertEqual({a: t for a, (t, _) in s.items()},
                         {k: "kullanıcı", prog: "program", ver: "program hesabı", bos: "boş", pda: "pda", "BORSA" + k[5:]: "bilinen"})
        self.assertEqual(len(cl.cagri), 1); self.assertEqual(len(cl.cagri[0][1][0]), 4)   # PDA ve bilinen için istek yok

    def test_parcalama_ve_bozuk_yanit(self):
        adresler = []
        while len(adresler) < 5:
            b = os.urandom(32)
            if referans(b): adresler.append(enc(b))
        cl = Fake({a: dict(owner=H.SISTEM) for a in adresler})
        H.siniflandir(cl, adresler, parca=2)
        self.assertEqual(len(cl.cagri), 3)
        class Bozuk:
            def call(self, m, p): return {"value": []}
        with self.assertRaises(ValueError): H.siniflandir(Bozuk(), adresler[:1])

    def test_bilinenler_dosyasi(self):
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "b.txt")
        open(p, "w").write("# başlık\nAAA  # Borsa sıcak cüzdanı\nBBB\n")
        self.assertEqual(H.bilinenler(p), {"AAA": "Borsa sıcak cüzdanı", "BBB": "bilinen hesap"})


    def test_denetim_araci(self):
        import io, tempfile, contextlib, hesap_denetim
        on, off = [], []
        while len(on) < 1 or len(off) < 1:
            b = os.urandom(32); (on if referans(b) else off).append(enc(b))
        p = os.path.join(tempfile.mkdtemp(), "w.txt"); open(p, "w").write(f"# liste\n{on[0]}\n{off[0]}\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            s = hesap_denetim.main([p], client=Fake({on[0]: dict(owner=H.SISTEM)}))
        self.assertEqual((s[on[0]][0], s[off[0]][0]), ("kullanıcı", "pda"))
        self.assertIn("1 kullanıcı cüzdanı", out.getvalue())


if __name__ == "__main__":
    unittest.main()
