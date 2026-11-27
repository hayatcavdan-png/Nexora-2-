import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import hl

W = "0xabc0000000000000000000000000000000000001"


def d(tid, t, coin, side, sz, bas, px):
    return dict(tid=tid, time=t * 1000, coin=coin, side=side, sz=str(sz), startPosition=str(bas), px=str(px))


class FakeIst:
    def __init__(self): self.mids, self.fills, self.rows = {"BTC": 100.0}, {}, []
    def ortalar(self): return dict(self.mids)
    def dolumlar(self, w, bas_ms): return [f for f in self.fills.get(w, []) if f["time"] >= bas_ms]
    def lider(self): return self.rows


class OlcerTests(unittest.TestCase):
    def setUp(self):
        self.now = [10_000.0]; self.ist = FakeIst()
        self.o = hl.Olcer(os.path.join(tempfile.mkdtemp(), "h.db"), self.ist, saat=lambda: self.now[0])

    def test_long_ac_kapat_ve_getiri(self):
        self.ist.fills[W] = [d(1, 9990, "BTC", "B", 1, 0, 99.0)]
        self.assertEqual(self.o.tur([W])["acilan"], 1)
        self.ist.fills[W].append(d(2, 10_050, "BTC", "B", 0.5, 1, 100.5))      # ekleme: yeni ölçüm yok
        self.now[0] = 10_060; self.assertEqual(self.o.tur([W])["acilan"], 0)
        self.ist.mids["BTC"] = 110.0; self.now[0] = 12_000                       # 30 dk fiyatı
        self.o.tur([W])
        self.ist.fills[W].append(d(3, 12_100, "BTC", "A", 1.5, 1.5, 111.0))     # pozisyon sıfır: kapanış
        self.ist.mids["BTC"] = 112.0; self.now[0] = 12_110
        self.assertEqual(self.o.tur([W])["kapanan"], 1)
        r = hl.rapor(self.o.db.execute("PRAGMA database_list").fetchone()[2], now=12_200)
        self.assertEqual(r["kapanan"], 1)
        self.assertAlmostEqual(r["biz"]["ort"], 12.0 - 2 * hl.UCRET_PCT, places=3)          # 100 -> 112
        self.assertAlmostEqual(r["kaynak"]["ort"], (111 / 99 - 1) * 100, places=2)
        self.assertAlmostEqual(r["dk30"]["ort"], 10.0 - 2 * hl.UCRET_PCT, places=3)
        self.assertAlmostEqual(r["gecikme_pct"], (100 / 99 - 1) * 100, places=3)          # kaynaktan pahalı girdik
        self.assertIn("[16]", "\n".join(hl.satirlar(r)))

    def test_short_yon_degistirme_ve_eski_pozisyon(self):
        self.ist.fills[W] = [d(1, 9995, "ETH", "A", 2, 0, 50.0), d(2, 9996, "SOL", "A", 1, 5, 20.0)]   # SOL önceden açık: ölçülmez
        self.ist.mids.update(ETH=50.0, SOL=20.0)
        self.assertEqual(self.o.tur([W])["acilan"], 1)
        self.ist.fills[W].append(d(3, 10_010, "ETH", "B", 3, -2, 45.0))         # short -> long: kapat ve yeni aç
        self.ist.mids["ETH"] = 45.0; self.now[0] = 10_020
        r = self.o.tur([W]); self.assertEqual((r["acilan"], r["kapanan"]), (1, 1))
        g = self.o.db.execute("SELECT getiri_pct, yon FROM hl_sinyal ORDER BY id").fetchall()
        self.assertAlmostEqual(g[0][0], 10.0 - 2 * hl.UCRET_PCT, places=3); self.assertEqual(g[1][1], 1)

    def test_bayat_ve_spot_ve_tekrar(self):
        self.ist.fills[W] = [d(1, 9000, "BTC", "B", 1, 0, 99.0), d(2, 9990, "@107", "B", 1, 0, 1.0)]
        self.assertEqual(self.o.tur([W])["acilan"], 0)                          # 1000 sn eski, spot
        self.assertEqual(self.o.tur([W])["acilan"], 0)

    def test_secim(self):
        def row(a, hesap, wp, mp, mroi, mvlm, tp):
            return dict(ethAddress=a, accountValue=str(hesap), windowPerformances=[
                ["week", dict(pnl=str(wp), roi="0.1", vlm="1")], ["month", dict(pnl=str(mp), roi=str(mroi), vlm=str(mvlm))],
                ["allTime", dict(pnl=str(tp), roi="1", vlm="1")]])
        rows = [row("0xA", 1e6, 1, 5e5, 0.5, 1e7, 1e6), row("0xB", 1e6, 1, 9e5, 0.9, 1e7, 1e6),
                row("0xC", 1e6, -1, 9e5, 0.9, 1e7, 1e6),       # haftalık zarar
                row("0xD", 1e6, 1, 9e5, 0.9, 5e8, 1e6),        # hacim/hesap 500: yüksek frekans
                row("0xE", 1e4, 1, 9e5, 0.9, 1e5, 1e6)]        # küçük hesap
        self.assertEqual(hl.sec(rows), ["0xb", "0xa"])

    def test_rapor_veri_yok(self):
        self.assertIsNone(hl.rapor("/yok/h.db")); self.assertIn("henüz veri yok", hl.satirlar(None)[0])


if __name__ == "__main__": unittest.main()


class EkranTests(unittest.TestCase):
    def test_ekran(self):
        now = [10_000.0]; ist = FakeIst(); d = tempfile.mkdtemp(); yol = os.path.join(d, "h.db")
        o = hl.Olcer(yol, ist, saat=lambda: now[0])
        ist.fills[W] = [d_(1, 9990, "BTC", "B", 1, 0, 99.0), d_(2, 9991, "ETH", "A", 1, 0, 10.0)]; ist.mids["ETH"] = 10.0
        o.tur([W]); ist.fills[W].append(d_(3, 10_050, "BTC", "A", 1, 1, 105.0)); ist.mids["BTC"] = 105.0; now[0] = 10_060; o.tur([W])
        hl.liste_yaz([W], os.path.join(d, "l.txt"))
        e = hl.ekran(yol, os.path.join(d, "l.txt"), now=10_100)
        self.assertEqual(e["liste"], 1); self.assertEqual(len(e["son"]), 2)
        m = e["cuzdanlar"][0]; self.assertEqual((m["n"], m["acik"]), (1, 1)); self.assertIsNotNone(m["kaynak_ort"])
        self.assertIsNone(hl.ekran("/yok/h.db", now=1)["ozet"])

    def test_acik_zarar_siralamaya_girer(self):
        """A: 1 kârlı kapanış + 2 ağır zararda açık; B: 1 küçük kârlı kapanış. Eskiden A üstteydi, şimdi B üstte."""
        A, B = W, "0xbbb0000000000000000000000000000000000002"
        now = [10_000.0]; ist = FakeIst(); dd = tempfile.mkdtemp(); yol = os.path.join(dd, "h.db")
        ist.mids.update(BTC=100.0, ETH=10.0, SOL=20.0, DOGE=1.0)
        o = hl.Olcer(yol, ist, saat=lambda: now[0])
        ist.fills[A] = [d_(1, 9990, "BTC", "B", 1, 0, 100.0), d_(2, 9991, "ETH", "B", 1, 0, 10.0), d_(3, 9992, "SOL", "B", 1, 0, 20.0)]
        ist.fills[B] = [d_(4, 9993, "DOGE", "B", 1, 0, 1.0)]
        o.tur([A, B])
        ist.fills[A].append(d_(5, 10_050, "BTC", "A", 1, 1, 110.0)); ist.fills[B].append(d_(6, 10_051, "DOGE", "A", 1, 1, 1.01))
        ist.mids.update(BTC=110.0, DOGE=1.01, ETH=8.0, SOL=16.0); now[0] = 10_060; o.tur([A, B])   # A'nın açıkları %-20
        e = hl.ekran(yol, os.path.join(dd, "l.txt"), now=10_100)
        m = {x["wallet"]: x for x in e["cuzdanlar"]}
        self.assertGreater(m[A]["ort"], m[B]["ort"])                         # yalnız kapananlara bakınca A iyi görünür
        self.assertAlmostEqual(m[A]["acik_ort"], -20 - 2 * hl.UCRET_PCT, places=3)
        self.assertLess(m[A]["toplam_ort"], 0); self.assertEqual(m[A]["toplam_n"], 3)
        self.assertEqual(e["cuzdanlar"][0]["wallet"], B)                      # açıklar dahil sıralama
        det = hl.cuzdan_detay(yol, A, now=10_100)
        self.assertLess(det["ozet"]["toplam_ort"], 0)
        self.assertTrue(any(x["anlik_pct"] is not None for x in det["olcumler"] if x["durum"] == "acik"))


d_ = d


class GercekciTests(unittest.TestCase):
    def test_defter_fonlama_kaldirac_durak(self):
        now = [10_000.0]; ist = FakeIst(); yol = os.path.join(tempfile.mkdtemp(), "h.db")
        ist.defter = lambda coin: ([(ist.mids[coin] * 0.999, 1e6)], [(ist.mids[coin] * 1.001, 0.5), (ist.mids[coin] * 1.002, 1e6)])
        ist.fonlama = lambda coin, a, b: [0.0001, 0.0001]                     # long 2 saat öder: -%0,02
        ist.pozisyon = lambda w, coin: dict(kaldirac=20.0, tasfiye_px=95.0, giris_px=99.0)
        o = hl.Olcer(yol, ist, saat=lambda: now[0])
        ist.fills[W] = [d_(1, 9990, "BTC", "B", 1, 0, 99.0)]; o.tur([W])
        sg = o.db.execute("SELECT * FROM hl_sinyal").fetchone()
        self.assertEqual(sg["kaldirac"], 20.0)
        self.assertGreater(sg["giris_defter"], 100.1); self.assertLess(sg["giris_defter"], 100.2)    # 0.5 adet yetmez, ikinci seviye
        ist.mids["BTC"] = 93.0; now[0] = 10_100; o.tur([W])                   # en kötü an -%7
        ist.mids["BTC"] = 110.0; now[0] = 10_200; ist.fills[W].append(d_(2, 10_190, "BTC", "A", 1, 1, 111.0)); o.tur([W])
        sg = o.db.execute("SELECT * FROM hl_sinyal").fetchone()
        self.assertAlmostEqual(sg["en_kotu_pct"], -7.0, places=3)
        self.assertAlmostEqual(sg["fonlama_pct"], -0.02, places=4)
        self.assertAlmostEqual(sg["getiri_net_pct"], sg["getiri_defter_pct"] - 0.02, places=4)
        r = hl.rapor(yol, now=10_300)
        self.assertEqual(r["defter"]["n"], 1); self.assertIn(">10x", r["kaldirac"])
        du = {x["durak"]: x for x in r["duraklar"]}
        self.assertEqual(du[5.0]["tetik"], 1); self.assertEqual(du[10.0]["tetik"], 0)
        self.assertAlmostEqual(du[5.0]["ort"], -5 - 2 * hl.UCRET_PCT, places=3)
        metin = "\n".join(hl.satirlar(r)); self.assertIn("NET", metin); self.assertIn("zarar durdur", metin)
        dt = hl.cuzdan_detay(yol, W, now=10_300)
        self.assertEqual(dt["ozet"]["n"], 1); self.assertEqual(dt["olcumler"][0]["kaldirac"], 20.0)

    def test_vwap(self):
        self.assertAlmostEqual(hl.vwap([(10.0, 5)], 20), 10.0); self.assertIsNone(hl.vwap([(10.0, 1)], 20))
