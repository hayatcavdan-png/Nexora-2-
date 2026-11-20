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

    def test_ek_ucret_her_islemde_iki_kez(self):
        sig = [s(0, 60, "A", "T", 10.0)]
        a, b = D.simule(sig, max_poz=8, oran=0.05)["kz"], D.simule(sig, max_poz=8, oran=0.05, ek_ucret=0.1)["kz"]
        self.assertAlmostEqual(a - b, 0.2, places=2)               # 5$'lık pozisyon: +0.50$ → +0.30$

    def test_gunluk_zarar_siniri_ve_token_gunluk(self):
        sig = [s(0, 60, "A", "T1", -40.0), s(100, 200, "B", "T2", 50.0), s(90_000, 90_100, "C", "T3", 10.0),
               s(90_200, 90_300, "C", "T3", 10.0), s(90_400, 90_500, "D", "T3", 10.0)]
        a = D.simule(sig, max_poz=8, oran=0.05, cuzdan_siniri=4)
        b = D.simule(sig, max_poz=8, oran=0.05, cuzdan_siniri=4, gunluk_zarar=0.01, token_gunluk=2)
        self.assertEqual(a["islem"], 5); self.assertEqual(b["limit_durdu"], 1)      # -2$ kayıp (%2) sonrası T2 alınmaz; ertesi gün sıfırlanır
        self.assertEqual(b["islem"], 3)                                            # T3 günde 2 giriş

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


class ModelTests(unittest.TestCase):
    def db(self, satirlar):
        d = tempfile.mkdtemp(); yol = os.path.join(d, "e.db")
        c = sqlite3.connect(yol); c.executescript(SEMA)
        for i, (ts, w, t, k_ts, g, ck, c5, rt) in enumerate(satirlar):
            c.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token, al_sat_kaybi_pct, giris_usdc) VALUES(?,?,?,?,?,5.0)",
                      (f"e{i}", ts, w, t, rt))
            if g is not None:
                c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct, cikis_usdc) VALUES(?, 'kaynak', ?, ?, ?)",
                          (f"e{i}", k_ts, g, ck))
            if c5 is not None:
                c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct, cikis_usdc) VALUES(?, '5dk', ?, 0, ?)",
                          (f"e{i}", ts + 300, c5))
        c.commit(); c.close(); return yol

    def test_teyit_sayisi_ve_model_a(self):
        yol = self.db([(1000, "A", "T", 9000, 10.0, 5.5, None, 1.0), (1300, "B", "T", 9000, 12.0, 5.6, None, 1.0),
                       (1500, "C", "T", 9000, 8.0, 5.4, None, 1.0), (5000, "A", "U", 9000, -5.0, 4.7, None, 1.0)])
        d = D.sinyaller_detay(yol, now=10_000)
        self.assertEqual([x["teyit"] for x in d], [1, 2, 3, 1])
        self.assertEqual([x[3] for x in D.model_a(d, 2)], ["T", "T"])
        self.assertEqual(len(D.model_a(d, 3)), 1)

    def test_model_b_geri_cekilme(self):
        # rt %2: anlık satış değeri 4.90; 5 dk'da 4.50 (%-8.2) -> giriş; kaynakta 5.40
        yol = self.db([(1000, "A", "T", 9000, 8.0, 5.40, 4.50, 2.0),
                       (2000, "B", "U", 9000, 8.0, 5.40, 4.85, 2.0),        # %-1: geri çekilme yok
                       (3000, "C", "V", 3100, 8.0, 5.40, 4.50, 2.0)])       # kaynak 5 dk dolmadan sattı: girilemez
        d = D.sinyaller_detay(yol, now=10_000)
        b = D.model_b(d, 3.0)
        self.assertEqual(len(b), 1); self.assertEqual(b[0][0], 1300)
        self.assertAlmostEqual(b[0][4], ((5.40 / 4.50) * 0.98 - 1 - D.UCRET_PAY) * 100)
        self.assertEqual(len(D.model_b(d, 10.0)), 0)
        m = D.modeller(yol, now=10_000)
        self.assertEqual(m["sinyal"], 3); self.assertEqual(len(m["sonuclar"]), len(D.MODELLER))


class GuclendiriciTests(unittest.TestCase):
    def test_tutulan_tokena_ek_parca_ve_yeni_girise_kat(self):
        H = 3600
        sig = [(0, 10 * H, "A", "T", 10.0, 1.0, 1.0),          # A alır: normal büyüklük
               (60, 10 * H, "B", "T", 20.0, 1.0, 2.0),         # B teyit eder: ek parça (1x daha)
               (120, 10 * H, "C", "T", 20.0, 1.0, 2.0),        # ikinci ek parça yok
               (200, 10 * H, "D", "U", 10.0, 1.0, 2.0)]        # tutulmayan token, teyitli: 2x ile girer
        r = D.simule(sig, max_poz=10, oran=0.04, rt_max=3.0)
        self.assertEqual(r["islem"], 3)
        self.assertAlmostEqual(r["kz"], round(4.0 * 0.10 + 4.0 * 0.20 + 8.0 * 0.10, 2), places=1)
        self.assertEqual(D.simule([s[:6] for s in sig], max_poz=10, oran=0.04)["islem"], 2)   # çarpansız: ek yok

    def test_ek_parca_yer_saymaz_ama_toplam_risk_sayar(self):
        sig = [(i, 99999, f"W{i}", f"T{i}", 1.0, 1.0, 1.0) for i in range(10)] + [(50, 99999, "X", "T0", 1.0, 1.0, 2.0)]
        r = D.simule(sig, max_poz=10, oran=0.04, rt_max=3.0)       # 10 x %4 = %40 dolu: ek parça risk sınırına takılır
        self.assertEqual((r["islem"], r["kacan"]), (10, 1))
