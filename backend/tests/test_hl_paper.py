import os, sqlite3, tempfile, unittest

from nexora import hl, hl_paper as P

IYI, KOTU = "0xaaa0000000000000000000000000000000000001", "0xbbb0000000000000000000000000000000000002"


class Bos:
    def ortalar(self): return {}


def kur():
    yol = os.path.join(tempfile.mkdtemp(), "h.db")
    o = hl.Olcer(yol, Bos(), saat=lambda: 1_000_000.0)
    return yol, o.db


def gecmis(db, w, getiri, n=30, ts=990_000.0):
    for i in range(n):
        db.execute("""INSERT INTO hl_sinyal(wallet, coin, yon, kaynak_px, giris_ts, giris_px, durum, getiri_pct, getiri_net_pct)
                      VALUES(?,?,?,?,?,?,'kapandi',?,?)""", (w, "OLD", 1, 1.0, ts + i, 1.0, getiri, getiri))
    db.commit()


def sinyal(db, w, coin, yon, px, ts, defter=None):
    c = db.execute("""INSERT INTO hl_sinyal(wallet, coin, yon, kaynak_px, giris_ts, giris_px, giris_defter, durum)
                      VALUES(?,?,?,?,?,?,?,'acik')""", (w, coin, yon, px, ts, px, defter))
    db.commit(); return c.lastrowid


def kapat(db, sid, px, fon=0.0, neden="kaynak kapattı"):
    db.execute("UPDATE hl_sinyal SET durum='kapandi', cikis_px=?, cikis_defter=?, fonlama_pct=?, getiri_pct=0, neden=? WHERE id=?",
               (px, px, fon, neden, sid)); db.commit()


class PaperTest(unittest.TestCase):
    def setUp(self):
        self.yol, self.db = kur()
        gecmis(self.db, IYI, 0.5); gecmis(self.db, KOTU, -0.5)
        self.p = P.HlPaper(self.db, saat=lambda: 1_000_000.0)

    def test_uygun_trader_long_kopyalanir_ve_kar_hesabi(self):
        sid = sinyal(self.db, IYI, "BTC", 1, 100.0, 1_000_000.0, defter=100.0)
        r = self.p.adim({"BTC": 100.0}, now=1_000_010.0)
        self.assertEqual(r["acilan"], 1)
        poz = self.db.execute("SELECT * FROM hlp_poz").fetchone()
        self.assertAlmostEqual(poz["teminat"], 5.0); self.assertAlmostEqual(poz["buyukluk"], 15.0)
        kapat(self.db, sid, 110.0, fon=-0.1)
        r = self.p.adim({"BTC": 110.0}, now=1_000_100.0)
        self.assertEqual(r["kapanan"], 1)
        poz = self.db.execute("SELECT * FROM hlp_poz").fetchone()
        beklenen = 15.0 * 0.10 - 15.0 * 0.001 - 15.0 * P.TAKER_PCT / 100 - 16.5 * P.TAKER_PCT / 100   # %10 kâr − fonlama − ücretler
        self.assertAlmostEqual(poz["pnl"], beklenen, places=6)
        self.assertAlmostEqual(self.p.varlik(), 100.0 + beklenen, places=6)

    def test_short_kopyalanir(self):
        sid = sinyal(self.db, IYI, "ETH", -1, 10.0, 1_000_000.0, defter=10.0)
        self.p.adim({"ETH": 10.0}, now=1_000_010.0)
        kapat(self.db, sid, 9.0)
        self.p.adim({"ETH": 9.0}, now=1_000_100.0)
        self.assertGreater(self.db.execute("SELECT pnl FROM hlp_poz").fetchone()[0], 1.4)   # short %10 düşüşte kazanır

    def test_uygun_olmayan_ve_az_olcumlu_trader_kopyalanmaz(self):
        sinyal(self.db, KOTU, "BTC", 1, 100.0, 1_000_000.0)
        yeni = "0xccc0000000000000000000000000000000000003"; gecmis(self.db, yeni, 2.0, n=10)
        sinyal(self.db, yeni, "SOL", 1, 20.0, 1_000_000.0)
        self.assertEqual(self.p.adim({"BTC": 100.0, "SOL": 20.0}, now=1_000_010.0)["acilan"], 0)

    def test_tasfiye_teminati_sifirlar(self):
        sinyal(self.db, IYI, "DOGE", 1, 1.0, 1_000_000.0, defter=1.0)
        self.p.adim({"DOGE": 1.0}, now=1_000_010.0)
        r = self.p.adim({"DOGE": 0.6}, now=1_000_100.0)                # %40 düşüş > %32,3 eşik
        self.assertEqual(r["tasfiye"], 1)
        poz = self.db.execute("SELECT * FROM hlp_poz").fetchone()
        self.assertTrue(poz["neden"].startswith("TASFİYE"))
        self.assertAlmostEqual(poz["pnl"], -5.0 - 15.0 * P.TAKER_PCT / 100, places=6)   # teminat + giriş ücreti
        self.assertAlmostEqual(self.p.varlik(), 100.0 + poz["pnl"], places=6)

    def test_tasfiye_esigi_altinda_kalan_kayip_tasfiye_degil(self):
        sinyal(self.db, IYI, "DOGE", 1, 1.0, 1_000_000.0, defter=1.0)
        self.p.adim({"DOGE": 1.0}, now=1_000_010.0)
        self.assertEqual(self.p.adim({"DOGE": 0.75}, now=1_000_100.0)["tasfiye"], 0)
        self.assertLess(self.db.execute("SELECT anlik_pnl FROM hlp_poz").fetchone()[0], -3.7)

    def test_maks_pozisyon_ve_ayni_coin(self):
        for i, c in enumerate(["A", "B", "C", "D", "E", "F"]): sinyal(self.db, IYI, c, 1, 1.0, 1_000_000.0 + i)
        sinyal(self.db, IYI, "A", -1, 1.0, 1_000_009.0)
        r = self.p.adim({c: 1.0 for c in "ABCDEF"}, now=1_000_010.0)
        self.assertEqual(r["acilan"], P.MAKS_POZ)
        neden = {x[0] for x in self.db.execute("SELECT neden FROM hlp_atla")}
        self.assertTrue(any("en fazla" in n for n in neden))

    def test_eski_ve_bayat_sinyal_kopyalanmaz(self):
        yol, db = kur(); gecmis(db, IYI, 0.5)
        sinyal(db, IYI, "BTC", 1, 100.0, 1_000_000.0)                  # motor başlamadan önce
        p = P.HlPaper(db, saat=lambda: 1_000_000.0)
        sinyal(db, IYI, "ETH", 1, 10.0, 999_000.0)                     # kesinti sonrası eski
        self.assertEqual(p.adim({"BTC": 100.0, "ETH": 10.0}, now=1_000_010.0)["acilan"], 0)

    def test_ozet_ve_ekran(self):
        sinyal(self.db, IYI, "BTC", 1, 100.0, 1_000_000.0, defter=100.0)
        self.p.adim({"BTC": 101.0}, now=1_000_010.0)
        o = P.ozet(self.yol, now=1_000_020.0)
        self.assertEqual(o["mod"], "PAPER"); self.assertEqual(len(o["pozisyonlar"]), 1)
        self.assertEqual([u["wallet"] for u in o["uygun"]], [IYI])
        self.assertTrue(P.satirlar(o)[0].startswith("Hyperliquid PAPER"))
        self.assertIsNotNone(hl.ekran(self.yol, "/yok.txt", now=1_000_020.0)["paper"])

    def test_kapali(self):
        os.environ["HL_PAPER"] = "0"
        try: self.assertEqual(self.p.adim({}, now=1_000_010.0), dict(durum="kapali"))
        finally: del os.environ["HL_PAPER"]


if __name__ == "__main__":
    unittest.main()
