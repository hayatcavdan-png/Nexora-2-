import os, tempfile, unittest
from nexora.bildirim import Bildirim, uret, islem_bildirimleri, gunluk_zarar_bildirimi

W = "W" * 44
LISTELI, YOK = "L" * 44, "Y" * 44


class BildirimTest(unittest.TestCase):
    def sig(self, **k):
        d = dict(id=1, ts=100.0, sig="s1", side="BUY", token=YOK, wallet=W); d.update(k); return d

    def test_listede_olmayan_alim_bildirilir(self):
        out = uret([self.sig()], {LISTELI})
        self.assertEqual(len(out), 1); self.assertEqual(out[0]["tur"], "borsada_yok")
        self.assertIn("yalnızca bilgi", out[0]["metin"]); self.assertIn("işlem açmaz", out[0]["metin"])

    def test_listedeki_ve_satis_bildirilmez(self):
        self.assertEqual(uret([self.sig(token=LISTELI)], {LISTELI}), [])
        self.assertEqual(uret([self.sig(side="SELL")], {LISTELI}), [])

    def test_tekilleştirme_veritabani_ile(self):
        d = os.path.join(tempfile.mkdtemp(), "b.db")
        b = Bildirim(d)
        self.assertEqual(b.ekle(uret([self.sig(), self.sig(id=2)], set())), 1)     # aynı sig iki kez: bir bildirim
        self.assertEqual(b.ekle(uret([self.sig()], set())), 0)                     # yeniden tarama: yeni bildirim yok
        self.assertEqual(len(b.son()), 1)

    def test_metinde_anahtar_ya_da_tam_adres_yok(self):
        m = uret([self.sig()], set())[0]["metin"]
        self.assertNotIn(W, m); self.assertNotIn(YOK, m)


    def test_islem_bildirimi_yalnizca_kopyalananlar(self):
        s = [(1, 100.0, "buy", YOK, 0.0, "KOPYALANDI", W), (2, 110.0, "sell", YOK, 1.25, "KOPYALANDI", W),
             (3, 111.0, "buy", YOK, 0.0, "REDDEDİLDİ", W)]
        out = islem_bildirimleri(s, "bnb")
        self.assertEqual([x["olay"] for x in out], ["islem:bnb:1", "islem:bnb:2"])
        self.assertIn("K/Z +1.25", out[1]["metin"]); self.assertIn("Gerçek para kullanılmadı", out[0]["metin"])
        self.assertNotIn(YOK, out[0]["metin"])

    def test_gunluk_zarar_esigi(self):
        self.assertEqual(gunluk_zarar_bildirimi("base", "2026-11-16", 100.0, 98.0, 0.03), [])        # %2: aşılmadı
        b = gunluk_zarar_bildirimi("base", "2026-11-16", 100.0, 96.5, 0.03)                         # %3.5: aşıldı
        self.assertEqual(len(b), 1); self.assertEqual(b[0]["olay"], "gunluk:base:2026-11-16")
        d = tempfile.mkdtemp(); x = Bildirim(os.path.join(d, "g.db"))
        self.assertEqual(x.ekle(b), 1); self.assertEqual(x.ekle(gunluk_zarar_bildirimi("base", "2026-11-16", 100.0, 95.0, 0.03)), 0)


if __name__ == "__main__":
    unittest.main()
