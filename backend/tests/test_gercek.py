import base64, json, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import gercek as G
from nexora.core import Paper
from nexora.ed25519 import acik_anahtar, b58, imzala

TOHUM = bytes(range(32)); ACIK = acik_anahtar(TOHUM); ADRES = b58(ACIK)
TOK = "TokenMint1111111111111111111111111111111111"


def tx(taker_pub=ACIK):
    mesaj = bytes([0x80, 1, 0, 1, 2]) + taker_pub + bytes(range(32, 64)) + bytes(32) + bytes([0, 0])
    return base64.b64encode(bytes([1]) + bytes(64) + mesaj).decode(), mesaj


class Hazir:
    def __init__(self): self.cagri = []; self.sim = True; self.tx = tx()[0]
    def hazirla(self, giris, cikis, miktar, taker, kayma_bps=None):
        self.cagri.append((giris, cikis, miktar, taker)); return dict(transaction=self.tx, request_id="r1")
    def simule(self, t): return dict(basarili=self.sim, hata=None if self.sim else "x")


class Yanit:
    def __init__(self, d): self.d = d
    def json(self): return self.d


class Oturum:
    def __init__(self): self.gonderilen = []; self.yanit = dict(code=0, status="Success", totalInputAmount="20000000",
                                                                 totalOutputAmount="5000", signature="SIG")
    def post(self, url, json=None, headers=None, timeout=None): self.gonderilen.append((url, json)); return Yanit(dict(self.yanit))


class GercekTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.anahtar = os.path.join(self.d, "pilot.json")
        json.dump(list(TOHUM + ACIK), open(self.anahtar, "w"))
        self.ayar = os.path.join(self.d, "ayar.json"); self.paper = Paper(); self.h = Hazir(); self.s = Oturum()
        self.p = G.GercekPilot(self.paper, anahtar_yolu=self.anahtar, db_yol=os.path.join(self.d, "g.db"), ayar_yolu=self.ayar,
                               session=self.s, api_key="", hazirlayici=self.h)
        os.environ["GERCEK_ISLEM"] = "1"

    def tearDown(self): os.environ.pop("GERCEK_ISLEM", None)

    def ac(self, **k):
        a = G.ayar_oku(self.ayar); a.update(acik=True, **k); G.ayar_yaz(a, self.ayar)

    def test_imza_yalnizca_ilk_yuva(self):
        t, mesaj = tx(); im = base64.b64decode(G.imzali(t, TOHUM, ADRES))
        self.assertEqual(im[1:65], imzala(TOHUM, mesaj)); self.assertEqual(im[65:], mesaj)
        with self.assertRaises(G.GercekHata): G.imzali(tx(bytes(32))[0], TOHUM, ADRES)    # ücret ödeyen biz değiliz

    def test_cift_kilit(self):
        self.assertEqual(self.p.al("e1", TOK)["neden"], "pilot kapalı")
        self.ac(); os.environ["GERCEK_ISLEM"] = "0"
        self.assertEqual(self.p.al("e1", TOK)["neden"], "GERCEK_ISLEM=1 değil"); self.assertEqual(self.s.gonderilen, [])

    def test_al_sat_ve_kz(self):
        self.ac(islem_usd=20.0)
        r = self.p.al("e1", TOK); self.assertEqual(r["durum"], "tamam")
        url, govde = self.s.gonderilen[0]
        self.assertTrue(url.endswith("/swap/v2/execute")); self.assertEqual(govde["requestId"], "r1")
        self.assertEqual(self.h.cagri[0][2], 20_000_000); self.assertEqual(self.h.cagri[0][3], ADRES)
        self.assertEqual(self.p.al("e2", TOK)["neden"], "bu token'da gerçek pozisyon var")
        self.s.yanit.update(totalOutputAmount="23000000")
        r = self.p.sat("e3", TOK); self.assertEqual(r["durum"], "tamam"); self.assertAlmostEqual(r["kz"], 3.0)
        self.assertEqual(self.h.cagri[1][2], 5000)                          # satış: alınan miktarın tamamı
        o = self.p.ozet(); self.assertEqual((o["kapanan"], o["toplam_kz"], len(o["acik_poz"])), (1, 3.0, 0))

    def test_sinirlar(self):
        self.ac(islem_usd=20.0, butce_usd=40.0, en_fazla_poz=5)
        self.p.al("a", "T1"); self.p.al("b", "T2")
        self.assertEqual(self.p.al("c", "T3")["neden"], "bütçe dolu")
        self.paper._set("kill", "1"); self.assertEqual(self.p.al("d", "T4")["neden"], "acil durdurma açık"); self.paper._set("kill", "0")
        self.s.yanit.update(totalOutputAmount="5000000")                    # 20$ -> 5$: 15$ zarar
        self.p.sat("x", "T1")
        self.ac(gunluk_zarar_usd=15.0, durdurma_usd=100.0)
        self.assertEqual(self.p.al("e", "T5")["neden"], "günlük gerçek zarar sınırı")
        self.ac(gunluk_zarar_usd=100.0, durdurma_usd=10.0)
        self.assertIn("KENDİNİ kapattı", self.p.al("f", "T6")["neden"]); self.assertFalse(G.ayar_oku(self.ayar)["acik"])

    def test_basarisiz_ve_simulasyon(self):
        self.ac(); self.h.sim = False
        self.assertEqual(self.p.al("e1", TOK)["durum"], "hata"); self.assertEqual(self.s.gonderilen, [])   # simülasyon geçmezse gönderim yok
        self.h.sim = True; self.s.yanit = dict(code=-1005, status="Failed", error="expired")
        self.assertEqual(self.p.al("e2", TOK)["durum"], "basarisiz"); self.assertEqual(self.p.ozet()["acik_poz"], [])

    def test_uzlastirma_ve_ek_alim(self):
        self.ac(); self.p.al("e1", TOK)
        out = self.p.bakim(now=10 ** 10)                                    # paper'da pozisyon yok -> gerçek satılır
        self.assertEqual(out[0][1]["durum"], "tamam"); self.assertEqual(self.p.ozet()["acik_poz"], [])
        self.p.bildir("e9", "T9", "buy", ek=True); self.assertTrue(self.p.q.empty())   # güçlendirme kopyalanmaz

    def test_ayar_sinirlari(self):
        with self.assertRaises(G.GercekHata): G.ayar_yaz(dict(G.VARSAYILAN, islem_usd=1000.0), self.ayar)
        with self.assertRaises(G.GercekHata): G.ayar_yaz(dict(G.VARSAYILAN, islem_usd=50.0, butce_usd=20.0), self.ayar)


if __name__ == "__main__": unittest.main()
