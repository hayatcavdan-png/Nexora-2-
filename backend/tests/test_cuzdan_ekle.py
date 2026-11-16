import csv, io, os, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cuzdan_ekle as ce

A = "7" * 43
B = "8" * 43
C = "9" * 43
D = "A" * 43


class Test(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def yaz(self, ad, satirlar):
        with open(os.path.join(self.d, ad), "w") as f: f.write("\n".join(satirlar) + "\n")

    def analiz(self, cuzdanlar):
        with open(os.path.join(self.d, "cuzdan_analiz.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "karar", "gerceklesen_usd", "kapanan", "kazanma_orani", "kar_faktoru", "skor"])
            w.writeheader()
            for c, k in cuzdanlar: w.writerow(dict(wallet=c, karar=k, gerceklesen_usd=10, kapanan=12, kazanma_orani=0.6, kar_faktoru=2, skor=0.5))

    def calis(self, *arg):
        with redirect_stdout(io.StringIO()): return ce.main(list(arg), kok=self.d)

    def test_secim_kurallari(self):
        ekle, atla = ce.secim([A, B, C, "xx", A], [B], {C}, {A: {}, B: {}}, en_fazla=5, sinir=25)
        self.assertEqual(ekle, [A])
        nedenler = dict(atla)
        self.assertEqual(nedenler[B], "zaten takipte")
        self.assertEqual(nedenler[C], "kara listede")
        self.assertEqual(nedenler["xx"], "geçersiz adres")

    def test_sinirlar(self):
        ekle, _ = ce.secim([A, B, C], [], set(), {A: {}, B: {}, C: {}}, en_fazla=2, sinir=25)
        self.assertEqual(ekle, [A, B])
        ekle, _ = ce.secim([A, B], [D], set(), {A: {}, B: {}}, en_fazla=5, sinir=2)
        self.assertEqual(ekle, [A])

    def test_kuru_calisma_dosyaya_dokunmaz(self):
        self.yaz("wallets.txt", [D]); self.yaz("wallets_onerilen.txt", ["# başlık", A])
        self.analiz([(A, "kopyalanabilir")])
        self.assertEqual(self.calis(), [A])
        self.assertEqual(ce.oku(os.path.join(self.d, "wallets.txt")), [D])

    def test_uygula_ve_geri(self):
        self.yaz("wallets.txt", [D]); self.yaz("wallets_onerilen.txt", [A, B])
        self.analiz([(A, "kopyalanabilir"), (B, "zararda")])
        self.calis("--uygula")
        self.assertEqual(ce.oku(os.path.join(self.d, "wallets.txt")), [D, A])
        self.calis("--geri")
        self.assertEqual(ce.oku(os.path.join(self.d, "wallets.txt")), [D])


if __name__ == "__main__":
    unittest.main()
