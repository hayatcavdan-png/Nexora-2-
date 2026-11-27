import unittest

from nexora import stop_sinama as S


class StopSinamaTest(unittest.TestCase):
    def test_kayma(self):
        self.assertEqual(S.kayma_olc([(10, -1.6, -16), (10, -1.8, -18), (10, 0.5, -5)]), 5.0)
        self.assertEqual(S.kayma_olc([]), 3.0)

    def test_toparlanan_pozisyonu_dar_esik_keser(self):
        # 1: %-20'ye inip +%30 kapanan; 2: %-40'a inip %-60 kapanan; 3: hiç düşmeden +%10
        oncesi = [(10, 3.0, -20), (10, -6.0, -40), (10, 1.0, -1)]
        r = {s["esik"]: s for s in S.sina(oncesi, kayma=4, esikler=(12, 30))}
        self.assertEqual(r[None]["toplam"], -2.0)
        self.assertEqual((r[12]["kesilen"], r[12]["kurtarilirdi"], r[12]["toplam"]), (2, 1, round(-1.6 - 1.6 + 1.0, 2)))
        self.assertEqual((r[30]["kesilen"], r[30]["toplam"]), (1, round(3.0 - 3.4 + 1.0, 2)))


if __name__ == "__main__":
    unittest.main()
