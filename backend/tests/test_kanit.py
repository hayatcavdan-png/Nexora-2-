import os, random, tempfile, unittest
from unittest import mock
from nexora.core import Paper
from nexora import kanit as KN

NOW = 1_800_000_000.0


def defter(yol, getiriler, gun=20):
    p = Paper(yol)
    for i, g in enumerate(getiriler):
        ts = NOW - gun * 86400 + i * (gun * 86400 / max(1, len(getiriler)))
        p.db.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (ts, f"e{i}", "w", "t", "sell", 1.0, 10.0 * (1 + g), 0.0, 10.0 * g, "KOPYALANDI", "ok"))
    p.db.commit()


class KanitTest(unittest.TestCase):
    def test_duzeyler(self):
        d = tempfile.mkdtemp(); r = random.Random(1)
        yollar = {k: os.path.join(d, k + ".db") for k in ("guclu", "sans", "zarar", "az")}
        defter(yollar["guclu"], [0.05 + r.uniform(-0.02, 0.02) for _ in range(40)])
        defter(yollar["sans"], [r.choice([0.3, -0.25]) for _ in range(40)])
        defter(yollar["zarar"], [-0.03] * 40)
        defter(yollar["az"], [0.5] * 5)
        kl = [(k, k, y) for k, y in yollar.items()]
        with mock.patch.object(KN.Y, "kaynaklar", return_value=kl):
            k = KN.karne(kok=d, now=NOW)
        dz = {x["kaynak"]: x["duzey"] for x in k["kaynaklar"]}
        self.assertEqual(dz["guclu"], "güçlü"); self.assertEqual(dz["zarar"], "zararda"); self.assertEqual(dz["az"], "yetersiz veri")
        self.assertIn(dz["sans"], ("umut verici", "zararda"))
        self.assertEqual(k["kaynaklar"][0]["kaynak"], "guclu"); self.assertIn("guclu", k["ozet"])
        self.assertAlmostEqual(k["kaynaklar"][0]["islem"]["ort"], 5.0, delta=0.5)
        self.assertIn("GÜÇLÜ", KN.metin(k))

    def test_kisa_sure_yetersiz(self):
        self.assertEqual(KN.duzey(dict(n=50, ort=5.0, guven_alt=3.0, profit_factor=9.0), 5), "yetersiz veri")

    def test_dusus(self):
        self.assertEqual(KN.en_buyuk_dusus([100, 120, 90, 130, 117]), 25.0)


if __name__ == "__main__":
    unittest.main()
