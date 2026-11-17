import os, sqlite3, tempfile, unittest

from nexora import kadro as K
from nexora.etiket import SEMA

NOW = 2_000_000_000.0
W = {k: k * 43 for k in "ABCDEFGH"}


class OlcumModu:
    """Bu testler eski 'olcum' modunu (izle -> terfi -> düşür) doğrular; varsayılan mod artık 'herkes'."""
    def _olcum(self): self._mod, K.MOD = K.MOD, "olcum"
    def _geri(self): K.MOD = self._mod


def olc(n, ort, medyan=None):
    return dict(n=n, ort=ort, medyan=ort if medyan is None else medyan, pozitif=0.5)


class KararTest(OlcumModu, unittest.TestCase):
    def setUp(self): self._olcum()
    def tearDown(self): self._geri()

    def test_terfi_dusur_cikar(self):
        a, b, c, d, e = (W[x] for x in "ABCDE")
        k = K.karar([a, b, c, d, e], [c, d, e], {
            a: olc(12, 4.0),          # kopyalanan, iyi: kalır
            b: olc(9, -1.0),          # kopyalanan, ölçülen ortalama negatif: izlemeye düşer
            c: olc(11, 5.0, 1.0),     # izlenen, iyi: kopyalamaya geçer
            d: olc(12, -6.0),         # izlenen, çok kötü: listeden çıkar
            e: olc(4, 20.0)})         # izlenen, az ölçüm: bekler
        self.assertEqual((k["terfi"], k["dusur"], k["cikar"]), ([c], [b], [d]))
        self.assertEqual(k["liste"], [a, b, c, e])
        self.assertEqual(sorted(k["izle"]), sorted([e, b]))
        self.assertEqual((k["kopyalanan"], k["izlenen"]), (2, 2))

    def test_medyan_negatifse_terfi_yok_ve_az_olcumde_dusurme_yok(self):
        a, b = W["A"], W["B"]
        k = K.karar([a, b], [a], {a: olc(15, 6.0, -2.0), b: olc(7, -9.0)})
        self.assertEqual((k["terfi"], k["dusur"]), ([], []))         # tek büyük kazanç medyanı kurtarmaz; 7 ölçüm yetmez

    def test_adaylar_izlemeye_sinirli_ve_kara_liste(self):
        mevcut = [W["A"]]
        aday = [W[x] for x in "BCDEFGH"]
        k = K.karar(mevcut, [], {}, aday, kara=[W["B"]])
        self.assertEqual(k["eklenen"], [W[x] for x in "CDEFG"])     # günde en fazla 5, kara liste atlanır
        self.assertTrue(set(k["eklenen"]) <= set(k["izle"]))
        eski = K.LISTE_SINIRI
        try:
            K.LISTE_SINIRI = 2
            self.assertEqual(K.karar(mevcut, [], {}, aday)["eklenen"], [W["B"]])   # liste sınırı
        finally:
            K.LISTE_SINIRI = eski


class UygulaTest(OlcumModu, unittest.TestCase):
    def setUp(self):
        self._olcum()
        self.d = tempfile.mkdtemp(); self.eski = os.getcwd(); os.chdir(self.d)
        db = sqlite3.connect("e.db"); db.executescript(SEMA)
        for i, g in enumerate([5.0] * 6 + [2.0] * 5):                 # A: 11 ölçüm, ort > 3, medyan > 0
            db.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token) VALUES(?,?,?,?)", (f"a{i}", NOW - 3600, W["A"], "T"))
            db.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES(?,?,?,?)", (f"a{i}", "kaynak", NOW, g))
        db.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token) VALUES('eski', ?, ?, 'T')", (NOW - 30 * 86400, W["B"]))
        db.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES('eski', 'kaynak', ?, -50)", (NOW,))
        db.execute("INSERT INTO etiket_olay(event_id, ts, wallet, token) VALUES('z', ?, ?, 'T')", (NOW, W["B"]))
        db.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES('z', '30dk', ?, -50)", (NOW,))
        db.commit(); db.close()
        open("wallets.txt", "w").write(f"# yorum\n{W['A']}\n{W['B']}\n")
        open("izle_listesi.txt", "w").write(f"{W['A']}\n")

    def tearDown(self): os.chdir(self.eski); self._geri()

    def test_olcum_yalnizca_kaynak_ufku_ve_pencere(self):
        o = K.olcum("e.db", NOW)
        self.assertEqual(set(o), {W["A"]})                             # B: eski ölçüm ve 30dk ufku sayılmaz
        self.assertEqual(o[W["A"]]["n"], 11)

    def test_uygula_dosyalari_yazar(self):
        oz = K.uygula([W["C"]], etiket_db="e.db", now=NOW)
        self.assertTrue(oz["degisti"]); self.assertEqual(oz["terfi"], [W["A"]]); self.assertEqual(oz["eklenen"], [W["C"]])
        self.assertEqual(K._oku("wallets.txt"), [W["A"], W["B"], W["C"]])
        self.assertEqual(K._oku("izle_listesi.txt"), [W["C"]])
        once = os.path.getmtime("wallets.txt")
        self.assertFalse(K.uygula([], etiket_db="e.db", now=NOW)["degisti"])   # değişiklik yoksa dosyaya dokunmaz
        self.assertEqual(os.path.getmtime("wallets.txt"), once)

    def test_etiket_yoksa_yalnizca_aday_ekler(self):
        oz = K.uygula([], etiket_db="yok.db", now=NOW)
        self.assertFalse(oz["degisti"]); self.assertEqual(oz["olcum"], {})


if __name__ == "__main__":
    unittest.main()


class SessizTests(OlcumModu, unittest.TestCase):
    def setUp(self):
        self._olcum()
        self.d = tempfile.mkdtemp(); self.eski = os.getcwd(); os.chdir(self.d)
        t = sqlite3.connect("t.db")
        t.execute("CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY, ts REAL, wallet TEXT, side TEXT, token TEXT)")
        t.execute("INSERT INTO tracker_signals(ts, wallet, side, token) VALUES(?, ?, 'BUY', 'T')", (NOW + 7 * 86400, W["B"]))   # B son 7 günde aldı
        t.execute("INSERT INTO tracker_signals(ts, wallet, side, token) VALUES(?, ?, 'SELL', 'T')", (NOW - 3600, W["C"]))  # satış sayılmaz
        t.commit(); t.close()
        open("wallets.txt", "w").write("\n".join(W[x] for x in "ABCD") + "\n")
        open("izle_listesi.txt", "w").write("\n".join(W[x] for x in "BCD") + "\n")

    def tearDown(self): os.chdir(self.eski); self._geri()

    def test_sessiz_izlenen_7_gun_sonra_cikar(self):
        oz = K.uygula([], etiket_db="yok.db", now=NOW, tracker_db="t.db")          # ilk görülme: süre yeni başlar
        self.assertFalse(oz["degisti"])
        oz = K.uygula([], etiket_db="yok.db", now=NOW + 8 * 86400, tracker_db="t.db")
        self.assertEqual(sorted(oz["sessiz"]), sorted([W["C"], W["D"]]))           # C yalnızca sattı, D hiç işlem yapmadı
        self.assertNotIn(W["A"], oz["cikar"])                                         # kopyalanan (A) sessiz diye çıkarılmaz
        self.assertEqual(K._oku("wallets.txt"), [W["A"], W["B"]])

    def test_tracker_yoksa_kimse_cikmaz(self):
        K.uygula([], etiket_db="yok.db", now=NOW, tracker_db="yok.db")
        oz = K.uygula([], etiket_db="yok.db", now=NOW + 30 * 86400, tracker_db="yok.db")
        self.assertEqual(oz["sessiz"], []); self.assertFalse(oz["degisti"])


class HerkesModuTests(unittest.TestCase):
    def test_herkes_kopyalanir_performans_elemesi_yok(self):
        a, b, c, d = (W[x] for x in "ABCD")
        k = K.karar([a, b, c], [b, c], {a: olc(20, -9.0), b: olc(12, -6.0), c: olc(15, 8.0)}, adaylar=[d], mod="herkes")
        self.assertEqual(k["liste"], [a, b, c, d]); self.assertEqual(k["izle"], [])       # izlenenler de kopyalanır, aday doğrudan
        self.assertEqual((k["dusur"], k["eklenen"]), ([], [d]))                          # kötü ölçüm düşürmez
        self.assertEqual(sorted(k["terfi"]), sorted([b, c])); self.assertEqual((k["kopyalanan"], k["izlenen"]), (4, 0))
        k = K.karar([a, b], [], {}, sessiz=[b], mod="herkes")
        self.assertEqual((k["liste"], k["cikar"]), ([a], [b]))                           # sessiz cüzdan yine çıkar

    def test_seviyeler_herkes_modunda_kapali(self):
        eski = K.MOD
        try:
            K.MOD = "herkes"; self.assertEqual(K.seviyeler({W["A"]: olc(20, 9.0)}), {})
            K.MOD = "olcum"; self.assertEqual(K.seviyeler({W["A"]: olc(20, 9.0)}), {W["A"]: "kanitlanmis"})
        finally:
            K.MOD = eski
