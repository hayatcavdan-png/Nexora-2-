import csv, os, tempfile, unittest
import havuz as H
from nexora import kadro as K

W = {k: k * 43 for k in "ABCDEF"}


class HavuzTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.eski = os.getcwd(); os.chdir(self.d)
        with open("cuzdan_tarama.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "durum", "islem_7g"]); w.writeheader()
            for k, durum, n in (("A", "aday", 50), ("B", "aday", 40), ("C", "aday", 30), ("D", "bot", 999), ("E", "pasif", 0), ("F", "aday", 10)):
                w.writerow(dict(wallet=W[k], durum=durum, islem_7g=n))
        with open("cuzdan_analiz.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "karar", "skor", "gerceklesen_usd", "kapanan", "kazanma_orani", "medyan_tutma_sn"])
            w.writeheader()
            w.writerow(dict(wallet=W["A"], karar="kopyalanabilir", skor=0.3, gerceklesen_usd=120, kapanan=20, kazanma_orani=0.6, medyan_tutma_sn=600))
            w.writerow(dict(wallet=W["B"], karar="kopyalanabilir", skor=0.5, gerceklesen_usd=90, kapanan=15, kazanma_orani=0.5, medyan_tutma_sn=900))
            w.writerow(dict(wallet=W["C"], karar="zararda", skor=0, gerceklesen_usd=-40, kapanan=12, kazanma_orani=0.3, medyan_tutma_sn=300))
        open("wallets.txt", "w").write(W["A"] + "\n")

    def tearDown(self): os.chdir(self.eski)

    def test_rapor(self):
        d = H.durum()
        self.assertEqual(len(d["havuz"]), 6); self.assertEqual(sorted(d["kopya"]), sorted([W["A"], W["B"]]))
        self.assertEqual(d["yeni_kopya"], [W["B"]]); self.assertEqual(d["analizsiz"], [W["F"]])
        r = H.rapor(d)
        self.assertIn("Kopyalanabilir: 2; bunlardan takipte olmayan: 1", r); self.assertIn("~20 Helius", r)

    def test_ekle_kadroya_ekler(self):
        eski = K.MOD
        try:
            K.MOD = "herkes"
            self.assertIn("Eklenen: 1 cüzdan", H.ekle())
            self.assertEqual(K._oku("wallets.txt"), [W["A"], W["B"]])
            self.assertEqual(K.YENI_GUNLUK, 5)                                   # tek seferlik sınır geri alındı
        finally:
            K.MOD = eski


if __name__ == "__main__":
    unittest.main()
