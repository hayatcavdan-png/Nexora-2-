import json, os, sys, tempfile, threading, unittest, urllib.request, urllib.error


class RolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp()
        os.environ.update(NEXORA_API_KEY="k", NEXORA_DB=os.path.join(d, "p.db"), UYELIK_DB=os.path.join(d, "u.db"))
        sys.modules.pop("server", None)
        import server
        from http.server import ThreadingHTTPServer
        cls.server = server
        server.paper.record_buy("e1", "GIZLICUZDAN111", "TOK", 2.5, 1_000_000, 6)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()

    def call(self, path, body=None, anahtar=None, oturum=None):
        h = {}
        if anahtar: h["X-API-Key"] = anahtar
        if oturum: h["X-Oturum"] = oturum
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=h,
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

    def test_1_anahtarsiz_kayit_ve_uye_gorunumu(self):
        self.assertEqual(self.call("/portfoy")[0], 401)                               # kimliksiz: hiçbir veri yok
        c, d = self.call("/uye/kayit", {"eposta": "uye@x.co", "parola": "parola-123"})
        self.assertEqual(c, 200); tok = d["oturum"]
        c, d = self.call("/portfoy", oturum=tok)
        self.assertEqual(c, 200); self.assertEqual(d["positions"][0]["wallet"], "gizli")   # cüzdan adresi üyeye gitmez
        self.assertNotIn("GIZLICUZDAN", json.dumps(self.call("/islemler", oturum=tok)[1]))
        c, d = self.call("/durum", oturum=tok); self.assertEqual((c, d["rol"]), (200, "uye")); self.assertNotIn("ayarlar", d)
        self.assertEqual(self.call("/uye/ben", oturum=tok)[1]["rol"], "uye")
        for yol in ("/takip", "/cuzdanlar", "/ayarlar", "/rapor", "/karar-izi", "/yedek/son", "/saglik", "/teshis"):
            self.assertEqual(self.call(yol, oturum=tok)[0], 403, yol)
        for yol, govde in (("/acil-durdur", {}), ("/devam", {}), ("/ayarlar", {"max_positions": 1}), ("/manuel", {}), ("/yedek", {})):
            self.assertEqual(self.call(yol, govde, oturum=tok)[0], 403, yol)
        self.assertFalse(self.server.paper.killed())

    def test_2_kurucu_rolu_ve_anahtar(self):
        c, d = self.call("/uye/kayit", {"eposta": "kurucu@x.co", "parola": "parola-123"}); eski = d["oturum"]
        self.server.uyelik.rol_ata("kurucu@x.co", "kurucu")
        self.assertEqual(self.call("/takip", oturum=eski)[0], 401)                    # rol değişince eski oturum kapanır
        tok = self.call("/uye/giris", {"eposta": "kurucu@x.co", "parola": "parola-123"})[1]["oturum"]
        self.assertEqual(self.call("/uye/ben", oturum=tok)[1]["rol"], "kurucu")
        self.assertEqual(self.call("/ayarlar", oturum=tok)[0], 200)
        self.assertIn("GIZLICUZDAN", json.dumps(self.call("/portfoy", oturum=tok)[1]))
        self.assertEqual(self.call("/ayarlar", {"max_positions": 4}, oturum=tok)[0], 200)
        self.assertEqual(self.call("/ayarlar", anahtar="k")[0], 200)                   # API anahtarı kurucu yetkisi verir
        c, d = self.call("/teshis?gun=1", oturum=tok)
        self.assertEqual(c, 200); self.assertIn("STRATEJİ TEŞHİSİ", d["metin"]); self.assertIn("gerceklesen", d["ozet"])
        self.assertEqual(self.call("/ayarlar", anahtar="yanlis")[0], 401)


class KayitSiniriTests(unittest.TestCase):
    def test_kayit_siniri(self):
        from nexora.uyelik import Uyelik
        u = Uyelik()
        for i in range(Uyelik.KAYIT_SINIRI): u.kayit(f"a{i}@x.co", "parola-123", now=1000.0)
        with self.assertRaises(PermissionError): u.kayit("b@x.co", "parola-123", now=1000.0)
        u.kayit("b@x.co", "parola-123", now=1000.0 + 3600)                                 # pencere geçince açılır

    def test_rol_ata_dogrulama(self):
        from nexora.uyelik import Uyelik, UyelikHatasi
        u = Uyelik()
        with self.assertRaises(UyelikHatasi): u.rol_ata("yok@x.co", "kurucu")
        u.kayit("a@x.co", "parola-123")
        with self.assertRaises(UyelikHatasi): u.rol_ata("a@x.co", "tanri")
        self.assertEqual(u.kurucular(), [])


if __name__ == "__main__":
    unittest.main()
