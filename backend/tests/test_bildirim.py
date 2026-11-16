import os, tempfile, unittest
from nexora.bildirim import Bildirim, uret

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


if __name__ == "__main__":
    unittest.main()
