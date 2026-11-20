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
