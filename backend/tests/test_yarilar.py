import os, sqlite3, tempfile, unittest
from nexora import kadro
from nexora.kopyalanabilirlik import sinif


def _db(olaylar):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "e.db")
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE etiket_olay (event_id TEXT, wallet TEXT, ts REAL)")
    c.execute("CREATE TABLE etiket_sonuc (event_id TEXT, ufuk TEXT, getiri_pct REAL)")
    for i, (w, ts, g) in enumerate(olaylar):
        c.execute("INSERT INTO etiket_olay VALUES (?,?,?)", (f"e{i}", w, ts))
        c.execute("INSERT INTO etiket_sonuc VALUES (?,?,?)", (f"e{i}", "kaynak", g))
    c.commit(); c.close()
    return p


class TestYarilar(unittest.TestCase):
    def test_iki_yari_zaman_sirasiyla(self):
        # ekleme sırası karışık; zaman sırasıyla ilk yarı (5, 6) ve son yarı (-4, -5) olmalı
        olaylar = [("W", 300, -4.0), ("W", 100, 5.0), ("W", 400, -5.0), ("W", 200, 6.0)]
        r = kadro.yarilar_olcum(_db(olaylar), now=1000, gun=1)
        self.assertEqual(r["W"]["yarilar"], (5.5, 2, -4.5, 2))

    def test_tek_olcum_atlanir(self):
        r = kadro.yarilar_olcum(_db([("W", 100, 3.0)]), now=1000, gun=1)
        self.assertNotIn("W", r)

    def test_a_icin_tutarlilik_gerekir(self):
        # ort ve örnek A eşiklerini geçer ama son yarı negatif -> A olmamalı
        olaylar = [("W", i, 8.0) for i in range(10)] + [("W", 100 + i, -1.0) for i in range(10)]
        db = _db(olaylar)
        ort_sinif = sinif({"n": 20, "ort": 3.5, "medyan": 2.0, "pozitif": 0.6},
                          kadro.yarilar_olcum(db, now=1000, gun=1)["W"])[0]
        self.assertEqual(ort_sinif, "B")


if __name__ == "__main__":
    unittest.main()
