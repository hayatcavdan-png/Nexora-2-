import csv, os, sqlite3, tempfile, unittest
from nexora import golge as G, deney as D


class GolgeTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); j = lambda n: os.path.join(self.d, n); self.j = j
        with open(j("a.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["wallet", "karar", "gerceklesen_usd"]); w.writeheader()
            for r in (("A", "zayıf", 110), ("B", "zararda", 50), ("C", "yetersiz veri", 3), ("D", "bot şüphesi", 99),
                      ("E", "zayıf", -5), ("F", "eksik veri", 40), ("T", "kopyalanabilir", 70)):
                w.writerow(dict(wallet=r[0], karar=r[1], gerceklesen_usd=r[2]))
        open(j("w.txt"), "w").write("T\n"); open(j("k.txt"), "w").write("F\n")

    def doldur(self, **k):
        return G.doldur(sinir=k.pop("sinir", 2), yol=self.j("g.txt"), analiz_csv=self.j("a.csv"), takip_yolu=self.j("w.txt"),
                        kara_yolu=self.j("k.txt"), tracker_db=self.j("yok.db"), kayit_yolu=self.j("g.json"), **k)

    def test_secim_ve_sinir(self):
        r = self.doldur()
        self.assertEqual(r["eklenen"], ["A", "C"])                 # kâr eden; bot/zararda/kara/takipte olmayan; sınır 2
        self.assertEqual(G.oku(self.j("g.txt")), ["A", "C"])
        self.assertFalse(self.doldur()["degisti"])

    def test_deney_golgeyi_ayirir(self):
        db = self.j("e.db"); c = sqlite3.connect(db)
        c.executescript("""CREATE TABLE etiket_olay(event_id TEXT, ts REAL, wallet TEXT, token TEXT, al_sat_kaybi_pct REAL, giris_usdc REAL);
                           CREATE TABLE etiket_sonuc(event_id TEXT, ufuk TEXT, ts REAL, cikis_usdc REAL, getiri_pct REAL);""")
        for i, (w, tok) in enumerate((("G", "X"), ("W", "X"), ("W", "Y"))):
            c.execute("INSERT INTO etiket_olay VALUES(?,?,?,?,1,5)", (f"e{i}", 1000 + i, w, tok))
            c.execute("INSERT INTO etiket_sonuc VALUES(?, 'kaynak', ?, 5.5, 10)", (f"e{i}", 2000 + i))
        c.commit(); c.close()
        det = [x for x in D.sinyaller_detay(db, now=3000, gun=1, golge={"G"}) if not x["golge"]]
        self.assertEqual([(x["t"], x["teyit"], x["teyit_golge"]) for x in det], [("X", 1, 2), ("Y", 1, 1)])
        m = D.masa(db, now=3000, gun=1, deneyler=[], aktif=(), golge={"G"})
        self.assertEqual((m["sinyal"], m["golge_sinyal"], len(m["sonuclar"])), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()


class TerfiKomutuTests(unittest.TestCase):
    def test_terfi_kopyalamaya_alir(self):
        import tempfile, havuz
        from unittest import mock
        from nexora import golge, kadro
        d = tempfile.mkdtemp(); eski = os.getcwd(); os.chdir(d)
        try:
            open("wallets.txt", "w").write("A\n")
            with mock.patch.object(golge, "karne", return_value=dict(terfi=["G1", "G2"], satirlar=[("G1", dict(n=25, ort=21.0)), ("G2", dict(n=20, ort=5.0))])), \
                 mock.patch.object(golge, "doldur", return_value={}), mock.patch.object(kadro, "alim_yapanlar", return_value=None):
                m = havuz.terfi()
            self.assertIn("2/2", m); self.assertEqual([l.strip() for l in open("wallets.txt") if not l.startswith("#")], ["A", "G1", "G2"])
            self.assertEqual(kadro.YENI_GUNLUK, 5)
        finally:
            os.chdir(eski)
