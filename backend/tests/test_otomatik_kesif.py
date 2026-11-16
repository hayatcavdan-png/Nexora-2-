import csv, io, json, os, tempfile, unittest
from contextlib import redirect_stdout
import otomatik_kesif as O
from nexora import panel

A, B = "7" * 43, "8" * 43


class Test(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.eski = os.getcwd(); os.chdir(self.d)
        open("wallets.txt", "w").write("9" * 43 + "\n")

    def tearDown(self): os.chdir(self.eski)

    def analiz_csv(self):
        with open("cuzdan_analiz.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "karar", "gerceklesen_usd", "kapanan", "kazanma_orani", "kar_faktoru", "skor", "medyan_tutma_sn"])
            w.writeheader()
            w.writerow(dict(wallet=A, karar="kopyalanabilir", gerceklesen_usd=119, kapanan=96, kazanma_orani=0.5, kar_faktoru=1.62, skor=0.15, medyan_tutma_sn=61))
            w.writerow(dict(wallet=B, karar="çok hızlı", gerceklesen_usd=500, kapanan=90, kazanma_orani=0.5, kar_faktoru=2, skor=0, medyan_tutma_sn=11))

    def calis(self, **kw):
        with redirect_stdout(io.StringIO()): return O.calistir(**kw)

    def test_oneri_ve_gorulen(self):
        self.analiz_csv()
        s = self.calis(kesif=lambda: [A, B], analiz=lambda: [dict(wallet=A, karar="kopyalanabilir"), dict(wallet=B, karar="çok hızlı")], now=1000.0)
        self.assertEqual((s["durum"], s["aday"], s["analiz_edilen"]), ("tamam", 2, 2))
        self.assertEqual([c["wallet"] for c in s["kopyalanabilir"]], [A])
        self.assertEqual(set(json.load(open("kesif_gorulen.json"))), {A, B})
        self.assertEqual(open("wallets.txt").read(), "9" * 43 + "\n")                 # takip listesine dokunulmaz
        # sonraki gün: görülenler kesif_gorulen.txt'e yazılır (keşif bunları aday saymaz); 14 gün sonra unutulur
        self.calis(kesif=lambda: [], now=1000.0 + 86400)
        self.assertIn(A, open("kesif_gorulen.txt").read())
        self.calis(kesif=lambda: [], now=1000.0 + 15 * 86400)
        self.assertNotIn(A, open("kesif_gorulen.txt").read())

    def test_hata_kaydedilir_ve_bildirilir(self):
        def bozuk(): raise RuntimeError("helius kapalı")
        s = self.calis(kesif=bozuk, now=2000.0)
        self.assertEqual(s["durum"], "hata")
        e = panel.kesif_olayi("kesif_son.json", 0)
        self.assertEqual((e["tur"], e["baslik"]), ("risk", "Otomatik keşif başarısız"))
        self.assertIsNone(panel.kesif_olayi("kesif_son.json", 2000.0))               # zaten görüldü

    def test_yapilacak_is_yoksa_atlanir(self):
        def bos(): raise SystemExit("Takip veritabanında henüz kaynak alımı yok")
        s = self.calis(kesif=bos, now=3000.0)
        self.assertEqual(s["durum"], "atlandı")
        self.assertIsNone(panel.kesif_olayi("kesif_son.json", 0))

    def test_olay_metni(self):
        self.analiz_csv()
        self.calis(kesif=lambda: [A], analiz=lambda: [dict(wallet=A, karar="kopyalanabilir")], now=4000.0)
        e = panel.olaylar("yok.db", "yok.db", son=0, now=5000.0)["olaylar"]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["tur"], "kesif"); self.assertIn("1 yeni kopyalanabilir", e[0]["baslik"])
        self.assertIn("+119$", e[0]["metin"]); self.assertIn("--uygula", e[0]["metin"])


if __name__ == "__main__":
    unittest.main()
