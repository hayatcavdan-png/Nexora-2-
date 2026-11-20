import os, sqlite3, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import etiket as E
from nexora import giris_cikis as GC


def db_kur(satirlar):
    """satirlar: (event_id, ts, wallet, token, yas_sn, block_time, {ufuk: (ts, getiri)})"""
    yol = os.path.join(tempfile.mkdtemp(), "e.db"); E.Etiketci(yol, None).db.close()
    c = sqlite3.connect(yol)
    for e, ts, w, t, yas, bt, son in satirlar:
        c.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token, al_sat_kaybi_pct, tb_yas_sn, block_time) VALUES(?,?,?,?,?,?,?)",
                  (e, ts, w, t, 1.0, yas, bt))
        for u, (uts, g) in son.items(): c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES(?,?,?,?)", (e, u, uts, g))
    c.commit(); c.close(); return yol


class GirisCikisTests(unittest.TestCase):
    def setUp(self):
        H = 3600
        self.yol = db_kur([
            # kaynak geç satıp kaybettirmiş, 30 dk iyi
            ("a", 1000, "A", "T1", 30, 1000, {"kaynak": (1000 + 5 * H, -20.0), "30dk": (2800, 10.0), "5dk": (1300, 2.0)}),
            # kaynak 10 dk'da satmış: 'hangisi önce' kaynağı kullanır
            ("b", 2 * H, "B", "T2", 5000, 2 * H, {"kaynak": (2 * H + 600, 15.0), "30dk": (2 * H + 1800, 5.0)}),
            # T2'yi aynı blokta başka cüzdan da almış (bağlı olabilir)
            ("c", 2 * H + 0.4, "C", "T2", 5000, 2 * H, {"kaynak": (3 * H, -5.0), "30dk": (3 * H, -1.0)}),
            # T2'yi 5 dk sonra bağımsız bir cüzdan almış
            ("d", 2 * H + 300, "D", "T2", 5300, 2 * H + 300, {"kaynak": (3 * H, 8.0)}),
            ("g", 4 * H, "G", "T3", 30, 4 * H, {"kaynak": (5 * H, 50.0), "30dk": (5 * H, 50.0)}),     # gölge: A'da yok
        ])

    def test_cikis(self):
        r = GC.rapor(self.yol, now=10 * 3600, gun=1, golge={"G"})
        c = {x["ad"]: x for x in r["cikis"]}
        self.assertEqual(c["Kaynak satınca (şimdiki)"]["n"], 3)         # d'nin 30dk sonucu yok, G gölge
        self.assertAlmostEqual(c["Kaynak satınca (şimdiki)"]["kz"], -0.25, places=2)   # c atlanır: T2 zaten açık
        self.assertGreater(c["30 dk sonra çık"]["kz"], c["Kaynak satınca (şimdiki)"]["kz"])
        self.assertEqual(c["5 dk sonra çık"]["n"], 1)
        self.assertAlmostEqual(c["Kaynak ya da 30 dk, hangisi önce"]["kz"], 1.25, places=1)

    def test_yas_ve_teyit(self):
        r = GC.rapor(self.yol, now=10 * 3600, gun=1, golge={"G"})
        y = {x["ad"]: x for x in r["yas"]["dilimler"]}
        self.assertEqual(y["< 1 dk"]["n"], 2); self.assertEqual(y["1–10 dk"]["n"], 0); self.assertEqual(y["1–24 sa"]["n"], 3)
        t = {x["ad"]: x["n"] for x in r["teyit"]}
        self.assertEqual(t["teyitsiz (ilk alan)"], 3)
        self.assertEqual(t["teyitli: yalnızca aynı blok (bağlı olabilir)"], 1)
        self.assertEqual(t["teyitli: farklı zamanda (bağımsız)"], 1)
        f = {x["ad"]: x for x in r["yas_filtre"]}
        self.assertEqual(f["Şimdiki (yaş süzgeci yok)"]["n"], 4); self.assertEqual(f["Token en az 1 sa'lik"]["n"], 3)   # a (30 sn) düşer
        self.assertGreater(f["Token en az 1 sa'lik"]["kz"], f["Şimdiki (yaş süzgeci yok)"]["kz"])
        metin = "\n".join(GC.satirlar(r)); self.assertIn("[14b]", metin)
        self.assertIn("[13]", metin); self.assertIn("[15]", metin)

    def test_veri_yok(self):
        r = GC.rapor("/yok/e.db", now=1, golge=set())
        self.assertEqual(r["olay"], 0); self.assertTrue(GC.satirlar(r))


if __name__ == "__main__": unittest.main()
