import os, sqlite3, tempfile, unittest
from nexora import deney as D
from nexora.etiket import SEMA

H = 3600


def s(giris, cikis, w, t, g, rt=1.0): return (giris, cikis, w, t, g, rt)


class SimuleTests(unittest.TestCase):
    def test_yer_siniri_ve_kz(self):
        sig = [s(0, 10 * H, "A", "T1", 20.0), s(1, 10 * H, "B", "T2", -10.0), s(2, 10 * H, "C", "T3", 50.0)]
        r = D.simule(sig, max_poz=2, oran=0.05, rt_max=3.0)
        self.assertEqual((r["islem"], r["kacan"]), (2, 1))                    # 3. sinyal yer yok
        self.assertAlmostEqual(r["kz"], 5 * 0.20 + 5 * -0.10, places=2)
        r = D.simule(sig, max_poz=3, oran=0.05, rt_max=3.0)
        self.assertAlmostEqual(r["kz"], 1.0 - 0.5 + 2.5, places=2)

    def test_kapanan_yer_acar_ve_al_sat_filtresi(self):
        sig = [s(0, H, "A", "T1", 10.0), s(2 * H, 3 * H, "B", "T2", 10.0), s(4 * H, 5 * H, "C", "T3", -50.0, rt=5.0)]
        r = D.simule(sig, max_poz=1, oran=0.05, rt_max=3.0)
        self.assertEqual((r["islem"], r["kacan"]), (2, 0))                    # ilk kapanınca ikincisi girer; 3. al-sat ile elenir
        self.assertEqual(D.simule(sig, max_poz=1, oran=0.05, rt_max=6.0)["islem"], 3)

    def test_kadro_gelecegi_gormez(self):
        # A'nın 10 kapanmış iyi ölçümü olmadan kopyalanmaz; 11. sinyal terfiden sonra kopyalanır
        sig = [s(i * H, i * H + 60, "A", f"T{i}", 10.0) for i in range(10)] + [s(20 * H, 21 * H, "A", "TX", 10.0)]
        r = D.simule(sig, max_poz=16, seviyeler=D.SEVIYE_SIMDI, rt_max=3.0, kadro=True)
        self.assertEqual(r["islem"], 1)

    def test_aktif_cuzdan_terfi_beklemez(self):
        sig = [s(i * H, i * H + 60, "A", f"T{i}", 10.0) for i in range(3)]
        self.assertEqual(D.simule(sig, kadro=True, seviyeler=D.SEVIYE_SIMDI)["islem"], 0)          # yeni: ölçüm bekler
        self.assertEqual(D.simule(sig, kadro=True, seviyeler=D.SEVIYE_SIMDI, aktif={"A"})["islem"], 3)
        kotu = [s(i * H, i * H + 60, "A", f"K{i}", -10.0) for i in range(8)] + [s(20 * H, 21 * H, "A", "Z", 10.0)]
        r = D.simule(kotu, kadro=True, seviyeler=D.SEVIYE_SIMDI, aktif={"A"})
        self.assertEqual(r["islem"], 8)                                                           # 8 kötü ölçümden sonra düşer

    def test_gevsek_kadro_kotuyu_dusurur(self):
        sig = [s(i * H, i * H + 60, "A", f"K{i}", -5.0) for i in range(8)] + [s(20 * H, 21 * H, "A", "Z", 9.0),
               s(22 * H, 23 * H, "B", "Y", 9.0)]
        r = D.simule(sig, max_poz=8, oran=0.05, kadro="gevsek")
        self.assertEqual(r["islem"], 9)                          # A ilk 8'de kopyalanır, sonra düşer; B (ölçümsüz) kopyalanır

    def test_cuzdan_siniri_ve_toplam_risk(self):
        sig = [s(i, 10 * H, "A", f"T{i}", 1.0) for i in range(5)]
        self.assertEqual(D.simule(sig, max_poz=16, oran=0.025, cuzdan_siniri=2)["islem"], 2)
        sig = [s(i, 10 * H, f"W{i}", f"T{i}", 1.0) for i in range(30)]
        self.assertEqual(D.simule(sig, max_poz=40, oran=0.05, cuzdan_siniri=9)["islem"], 8)    # %40 / %5

    def test_masa_veritabanindan(self):
        d = tempfile.mkdtemp(); db = os.path.join(d, "e.db")
        c = sqlite3.connect(db); c.executescript(SEMA)
        c.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token, al_sat_kaybi_pct) VALUES('a', 1000, 'W', 'T', 1.0)")
        c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES('a', 'kaynak', 5000, 12.0)")
        c.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token) VALUES('b', 1000, 'W', 'T2')")
        c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES('b', '30dk', 5000, 99.0)")   # sayılmaz
        c.commit(); c.close()
        m = D.masa(db, now=2000, aktif=set())
        self.assertEqual(m["sinyal"], 1); self.assertEqual(len(m["sonuclar"]), len(D.DENEYLER))
        self.assertEqual(m["sonuclar"][0]["islem"], 1)


if __name__ == "__main__":
    unittest.main()
