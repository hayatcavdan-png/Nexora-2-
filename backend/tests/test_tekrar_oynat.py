import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
import tekrar_oynat as T


class TekrarTests(unittest.TestCase):
    def test_modlar_farkli_sonuc_verir(self):
        ev = [dict(ts=1, event_id="e1", wallet="A", token="T", side="buy", price=1.0),
              dict(ts=2, event_id="e2", wallet="B", token="T", side="buy", price=2.0),
              dict(ts=3, event_id="e3", wallet="B", token="T", side="sell", price=3.0)]
        tok = T.oynat(ev, "token")
        cuz = T.oynat(ev, "cuzdan")
        self.assertEqual(tok["kapanan"], 1)
        self.assertEqual(cuz["kapanan"], 1)
        self.assertNotEqual(tok["net"], cuz["net"])      # token: B A'nın 1.0 hissesini satar; cuzdan: kendi 2.0 hissesini

    def test_girdi_bos(self):
        self.assertEqual(T.oynat([], "cuzdan")["kapanan"], 0)


if __name__ == "__main__":
    unittest.main()
