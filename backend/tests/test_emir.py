import base64, io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest.mock import Mock
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import ed25519 as E
from nexora.emir import cozumle, denetle, EmirHazirlayici, EmirHatasi
import pilot_cuzdan, emir_dene

TOHUM = bytes(range(32))
TAKER_B = E.acik_anahtar(TOHUM); TAKER = E.b58(TAKER_B)


def tx(imzaci=1, hesaplar=None, imza=None, surum=0):
    hesaplar = hesaplar or [TAKER_B, bytes([7]) * 32]
    msg = (bytes([0x80 | surum]) if surum is not None else b"") + bytes([imzaci, 0, 1, len(hesaplar)]) + b"".join(hesaplar) \
          + bytes(32) + bytes([0]) + (bytes([0]) if surum is not None else b"")
    imzalar = imza if imza is not None else bytes(64) * imzaci
    return base64.b64encode(bytes([len(imzalar) // 64]) + imzalar + msg).decode()


class Resp:
    def __init__(self, body, status=200): self.status_code, self.body = status, body
    def json(self): return self.body


class Test(unittest.TestCase):
    def test_rfc8032(self):
        s = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        self.assertEqual(E.acik_anahtar(s).hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        self.assertEqual(E.imzala(s, b"").hex(), "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bac"
                                                 "c61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")

    def test_cozumle_ve_denetle(self):
        c = cozumle(tx())
        self.assertEqual((c["surum"], c["imzaci_sayisi"], c["hesaplar"][0], c["imzalar_bos"]), (0, 1, TAKER, True))
        self.assertEqual(denetle(tx(), TAKER)[0], [])
        self.assertIn("ücreti ödeyen hesap bizim cüzdan değil", denetle(tx(hesaplar=[bytes([9]) * 32, TAKER_B]), TAKER)[0])
        self.assertTrue(any("2 imzacı" in s for s in denetle(tx(imzaci=2), TAKER)[0]))
        self.assertIn("işlem önceden imzalanmış", denetle(tx(imza=bytes([1]) * 64), TAKER)[0])
        self.assertEqual(cozumle(tx(surum=None))["surum"], "legacy")
        with self.assertRaises(EmirHatasi): cozumle(tx(surum=1))
        with self.assertRaises(EmirHatasi): cozumle("bozuk!")

    def test_hazirla_parametreler_ve_bakiye_hatasi(self):
        s = Mock(); s.get = Mock(return_value=Resp({"transaction": "", "errorCode": 1, "router": "metis"}))
        o = EmirHazirlayici(Mock(), api_key="k", session=s).hazirla("A", "B", 1_000_000, TAKER)
        self.assertEqual((o["transaction"], o["hata"]), (None, "giriş token bakiyesi yetersiz"))
        p = s.get.call_args.kwargs["params"]
        self.assertEqual((p["taker"], p["excludeRouters"], p["maxSupportedTransactionVersion"]), (TAKER, "jupiterz", "0"))
        self.assertEqual(s.get.call_args.kwargs["headers"], {"x-api-key": "k"})
        s.get = Mock(return_value=Resp({}, 429))
        with self.assertRaises(EmirHatasi): EmirHazirlayici(Mock(), session=s).hazirla("A", "B", 1, TAKER)

    def test_simule(self):
        h = Mock(); h.call = Mock(return_value={"value": {"err": None, "unitsConsumed": 120000, "logs": ["a", "b"]}})
        r = EmirHazirlayici(h).simule(tx())
        self.assertTrue(r["basarili"]); self.assertEqual(r["birim"], 120000)
        m, params = h.call.call_args.args
        self.assertEqual(m, "simulateTransaction"); self.assertFalse(params[1]["sigVerify"])

    def test_gonderim_kodu_yok(self):
        kaynak = open(os.path.join(HERE, "..", "nexora", "emir.py")).read() + open(os.path.join(HERE, "..", "emir_dene.py")).read()
        self.assertNotIn("/execute\"", kaynak); self.assertNotIn("sendTransaction\"", kaynak)
        from nexora.helius_client import HeliusClient
        self.assertNotIn("sendTransaction", HeliusClient.READ_ONLY_METHODS)

    def test_pilot_cuzdan(self):
        d = tempfile.mkdtemp(); k = os.path.join(d, "pilot.json"); a = os.path.join(d, "adres.txt")
        adres = pilot_cuzdan.olustur(k, a, rastgele=lambda n: TOHUM)
        self.assertEqual(adres, TAKER)
        self.assertEqual(oct(os.stat(k).st_mode & 0o777), "0o600")
        self.assertEqual(bytes(json.load(open(k)))[32:], TAKER_B)
        with self.assertRaises(SystemExit): pilot_cuzdan.olustur(k, a)                 # asla üzerine yazmaz
        os.remove(a); self.assertEqual(pilot_cuzdan.adres(k, a), TAKER)
        with self.assertRaises(SystemExit): pilot_cuzdan.olustur(os.path.join(d, "yok", "p.json"), a)

    def test_deneme_akisi(self):
        d = tempfile.mkdtemp(); eski = os.environ.get("PILOT_ADRES")
        a = os.path.join(d, "adres.txt"); open(a, "w").write(TAKER + "\n")
        pilot_cuzdan.ADRES = a
        try:
            s = Mock(); s.get = Mock(return_value=Resp({"transaction": tx(), "router": "metis", "outAmount": "5", "requestId": "r"}))
            h = Mock(); h.call = Mock(return_value={"value": {"err": None, "unitsConsumed": 9, "logs": []}})
            orig = pilot_cuzdan.adres
            pilot_cuzdan.adres = lambda: open(a).read().strip()
            with redirect_stdout(io.StringIO()) as out: r = emir_dene.main([], helius=h, session=s)
            self.assertEqual(r, dict(asama="simule", basarili=True)); self.assertIn("GÖNDERİM YOK", out.getvalue())
            s.get = Mock(return_value=Resp({"transaction": "", "errorCode": 2, "router": "metis"}))
            with redirect_stdout(io.StringIO()): r = emir_dene.main([], helius=h, session=s)
            self.assertEqual(r["hata"], "ağ ücreti için SOL yetersiz")
        finally:
            pilot_cuzdan.adres = orig


if __name__ == "__main__":
    unittest.main()
