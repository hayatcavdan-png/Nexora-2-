import os, unittest
from nexora import yz_xai

VERI = {"kopyalanan": 12, "canli_kar_yuzde": 50.92, "deney_yuzde": -13.46, "fark_medyan": 0.3}


class TestYzXai(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("YZ_XAI")

    def tearDown(self):
        if self._old is None: os.environ.pop("YZ_XAI", None)
        else: os.environ["YZ_XAI"] = self._old

    def _yanit(self, metin):
        return {"model": "gemini-3.1-flash-lite", "steps": [{"type": "thought", "summary": []},
                {"type": "model_output", "content": [{"type": "text", "text": metin}]}]}

    def test_kapali_iken_cagrilmaz(self):
        os.environ["YZ_XAI"] = "0"
        called = []
        self.assertIsNone(yz_xai.rapor(VERI, post=lambda g: called.append(g) or {}))
        self.assertEqual(called, [])

    def test_istem_yalniz_veri_icerir(self):
        p = yz_xai.istem(VERI)
        self.assertIn("50.92", p)
        self.assertNotIn("GEMINI_API_KEY", p)
        self.assertIn("uydurma", p)

    def test_metin_cek_son_metni_alir(self):
        self.assertEqual(yz_xai.metin_cek(self._yanit("merhaba")), "merhaba")
        self.assertIsNone(yz_xai.metin_cek({"steps": [{"type": "thought", "summary": []}]}))

    def test_dogrulama_uydurma_sayiyi_yakalar(self):
        ok, bil = yz_xai.dogrula("Kâr %50.92, ama 77.7 hedefi var", VERI)
        self.assertFalse(ok); self.assertIn(77.7, bil)

    def test_dogrulama_veriden_gelen_sayiyi_kabul_eder(self):
        ok, bil = yz_xai.dogrula("Canlı %50.92, deney %-13.46, fark 0.3", VERI)
        self.assertTrue(ok, bil)

    def test_acik_rapor_dogrulama_ile_doner(self):
        os.environ["YZ_XAI"] = "1"; os.environ["GEMINI_API_KEY"] = "test"
        s = yz_xai.rapor(VERI, post=lambda g: self._yanit("Canlı pozitif (50.92), deney negatif (-13.46)."))
        self.assertTrue(s["dogru"]); self.assertEqual(s["model"], "gemini-3.1-flash-lite")
        os.environ.pop("GEMINI_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
