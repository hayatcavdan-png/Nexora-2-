import json, os, sys, tempfile, threading, unittest, urllib.request, urllib.error
from nexora.core import Paper, CFG, AYARLANABILIR


class AyarTests(unittest.TestCase):
    def setUp(self): self.p = Paper()

    def test_defaults(self):
        g = self.p.ayarlar()["gecerli"]
        for k in AYARLANABILIR: self.assertEqual(g[k], CFG[k])

    def test_tighten_and_audit(self):
        self.p.ayar_degistir({"max_positions": 3, "daily_loss_pct": 0.02})
        self.assertEqual(self.p.limit("max_positions"), 3); self.assertEqual(self.p.limit("daily_loss_pct"), 0.02)
        g = self.p.ayarlar()["gecmis"]
        self.assertEqual({(x["ayar"], x["yeni"]) for x in g}, {("max_positions", "3"), ("daily_loss_pct", "0.02")})
        self.p.ayar_degistir({"max_positions": 3})                 # değişmeyen değer kayıt üretmez
        self.assertEqual(len(self.p.ayarlar()["gecmis"]), 2)

    def test_cannot_loosen_beyond_rules(self):
        for bad in [{"max_pos_pct": 0.06}, {"daily_loss_pct": 0.05}, {"max_positions": 17}, {"max_positions_per_wallet": 3},
                    {"max_roundtrip_loss_pct": 7}, {"max_signal_age_s": 30}, {"max_positions": 0},
                    {"start_cash": 1000}, {"max_positions": 2.5}, {"max_positions": "3"}, {"max_positions": True}, {}]:
            with self.assertRaises(ValueError, msg=str(bad)): self.p.ayar_degistir(bad)

    def test_toplam_risk_korunur(self):
        with self.assertRaises(ValueError) as e: self.p.ayar_degistir({"max_positions": 16})     # 16 x %5 = %80
        self.assertIn("toplam risk", str(e.exception))
        self.assertEqual(self.p.limit("max_positions"), CFG["max_positions"])                    # hiçbiri uygulanmadı
        self.p.ayar_degistir({"max_positions": 16, "max_pos_pct": 0.025})                        # 16 x %2.5 = %40
        self.assertEqual((self.p.limit("max_positions"), self.p.limit("max_pos_pct")), (16, 0.025))
        self.assertEqual(self.p.precheck("buy", "T1", 1, "W1")[1], 2.5)                          # 100 $ x %2.5
        with self.assertRaises(ValueError): self.p.ayar_degistir({"max_pos_pct": 0.05})          # yeniden büyütülemez
        self.p._set("ayar:max_pos_pct", "0.05"); self.p.db.commit()                              # elle yazılsa bile...
        self.assertAlmostEqual(self.p.poz_orani(), 0.025)                                        # ...boyut %40/16'ya kısılır

    def test_all_or_nothing(self):
        with self.assertRaises(ValueError): self.p.ayar_degistir({"max_positions": 2, "max_pos_pct": 0.5})
        self.assertEqual(self.p.limit("max_positions"), CFG["max_positions"])

    def test_tampered_db_value_ignored(self):
        self.p._set("ayar:max_pos_pct", "0.5"); self.p.db.commit()   # elle bozulmuş değer -> varsayılan
        self.assertEqual(self.p.limit("max_pos_pct"), CFG["max_pos_pct"])

    def test_limits_enforced_in_precheck(self):
        self.p.ayar_degistir({"max_positions": 1, "max_pos_pct": 0.01})
        r, size = self.p.precheck("buy", "T1", 1, "W1")
        self.assertIsNone(r); self.assertAlmostEqual(size, 1.0)
        self.p.record_buy("e1", "W1", "T1", size, 1_000_000, 6)
        self.assertEqual(self.p.precheck("buy", "T2", 1, "W2")[0], "maks. eşzamanlı pozisyon")
        self.p.ayar_degistir({"max_signal_age_s": 3})
        self.assertEqual(self.p.precheck("sell", "T1", 5, "W1")[0], "sinyal bayat")

    def test_token_daily_entry_limit(self):
        for i in range(2):
            r, size = self.p.precheck("buy", "TT", 1, "W1")
            self.assertIsNone(r)
            self.p.record_buy(f"b{i}", "W1", "TT", size, 1_000_000, 6)
            self.p.record_sell(f"s{i}", "W1", "TT", size)
        self.assertEqual(self.p.precheck("buy", "TT", 1, "W1")[0], "bu token'a bugünkü giriş sınırı dolu")
        self.assertIsNone(self.p.precheck("buy", "TX", 1, "W1")[0])
        p2 = Paper(); p2.ayar_degistir({"max_token_entries_per_day": 1})
        r, size = p2.precheck("buy", "TT", 1, "W1"); p2.record_buy("b", "W1", "TT", size, 1_000_000, 6)
        p2.record_sell("s", "W1", "TT", size)
        self.assertEqual(p2.precheck("buy", "TT", 1, "W1")[0], "bu token'a bugünkü giriş sınırı dolu")
        with self.assertRaises(ValueError): p2.ayar_degistir({"max_token_entries_per_day": 3})

    def test_shared_between_processes(self):
        path = os.path.join(tempfile.mkdtemp(), "p.db")
        a, b = Paper(path), Paper(path)                            # sunucu ve takip ayrı bağlantılar
        a.ayar_degistir({"max_positions": 2})
        self.assertEqual(b.limit("max_positions"), 2)


class ServerAyarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["NEXORA_API_KEY"] = "k"; os.environ["NEXORA_DB"] = os.path.join(tempfile.mkdtemp(), "s.db")
        sys.modules.pop("server", None)
        import server
        from http.server import ThreadingHTTPServer
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-API-Key": "k"}, method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

    def test_get_post(self):
        c, d = self.call("/ayarlar"); self.assertEqual(c, 200); self.assertIn("sinirlar", d)
        c, d = self.call("/ayarlar", {"max_positions": 4}); self.assertEqual((c, d["gecerli"]["max_positions"]), (200, 4))
        self.assertEqual(self.call("/durum")[1]["ayarlar"]["max_positions"], 4)
        c, d = self.call("/ayarlar", {"max_positions": 17}); self.assertEqual(c, 400); self.assertIn("arasında", d["hata"])
        c, d = self.call("/ayarlar", None)
        self.assertEqual(d["gecerli"]["max_positions"], 4)


if __name__ == "__main__":
    unittest.main()


class ServerYedekTests(unittest.TestCase):
    def test_backup_endpoints(self):
        import shutil
        kok = tempfile.mkdtemp(); eski = os.getcwd(); os.chdir(kok)
        try:
            os.environ["NEXORA_API_KEY"] = "k"; os.environ["NEXORA_DB"] = os.path.join(kok, "nexora_paper.db")
            sys.modules.pop("server", None)
            import server
            from http.server import ThreadingHTTPServer
            srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            def req(path, post=False):
                r = urllib.request.Request(base + path, data=b"{}" if post else None, headers={"X-API-Key": "k"},
                                           method="POST" if post else "GET")
                try:
                    with urllib.request.urlopen(r) as x: return x.status, x.headers, x.read()
                except urllib.error.HTTPError as e: return e.code, e.headers, e.read()
            self.assertEqual(req("/yedek/son")[0], 404)
            c, _, b = req("/yedek", post=True); self.assertEqual(c, 200)
            ad = json.loads(b)["ad"]
            c, h, b = req("/yedek/son")
            self.assertEqual((c, h["X-Yedek-Ad"]), (200, ad)); self.assertEqual(b[:2], b"\x1f\x8b")   # gzip
            r = urllib.request.Request(base + "/yedek/son")                                           # anahtarsız
            with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(r)
            srv.shutdown(); srv.server_close()
        finally:
            os.chdir(eski)


class SeviyeTests(unittest.TestCase):
    def setUp(self):
        self.p = Paper(); self.p.ayar_degistir({"max_positions": 16, "max_pos_pct": 0.025})
        self.p.seviye = {"K": "kanitlanmis", "N": "normal"}

    def ac(self, wallet, token):
        r, size = self.p.precheck("buy", token, 1, wallet)
        if r: return r, size
        self.p.record_buy(f"e-{token}", wallet, token, size, 1_000_000, 6); return None, size

    def test_seviyeye_gore_boyut_ve_sinir(self):
        self.assertEqual(self.ac("K", "T1"), (None, 3.5))                    # kanıtlanmış: %3.5
        r, size = self.ac("N", "T2"); self.assertIsNone(r); self.assertAlmostEqual(size, 2.5, places=2)   # normal: %2.5
        self.assertAlmostEqual(self.ac("Y", "T3")[1], 1.5, places=2)         # ölçümü olmayan: yeni, %1.5
        self.assertEqual(self.ac("Y", "T4")[0], "bu cüzdan için pozisyon sınırı dolu")   # yeni: 1 pozisyon
        for i in range(3): self.assertIsNone(self.ac("K", f"K{i}")[0])     # kanıtlanmış: 4 pozisyona kadar
        self.assertEqual(self.ac("K", "K9")[0], "bu cüzdan için pozisyon sınırı dolu")

    def test_toplam_risk_acik_maliyetle_korunur(self):
        self.p.seviye = {f"K{i}": "kanitlanmis" for i in range(20)}
        acilan = 0
        for i in range(20):
            if self.ac(f"K{i}", f"T{i}")[0] is None: acilan += 1
        self.assertEqual(acilan, 11)                                          # 11 x 3.5 = 38.5; 12. pozisyon %40'ı aşar
        self.assertEqual(self.p.precheck("buy", "TX", 1, "K19")[0], "toplam risk sınırı (%40) dolu")

    def test_kullanici_sikilastirirsa_seviyeler_kuculur(self):
        self.p.ayar_degistir({"max_pos_pct": 0.0125, "max_positions_per_wallet": 1})
        self.assertAlmostEqual(self.p.poz_orani("K"), 0.0175)                 # yarıya iner
        self.assertEqual(self.p.cuzdan_siniri("K"), 1)                         # sıkılaştırılmış sınır geçerli

    def test_seviye_yoksa_eski_davranis_ve_elle_islem(self):
        self.p.seviye = {}
        self.assertEqual(self.p.cuzdan_siniri("X"), CFG["max_positions_per_wallet"])
        self.assertAlmostEqual(self.p.poz_orani("X"), 0.025)
        self.p.seviye = {"K": "kanitlanmis"}
        self.assertIsNone(self.p.cuzdan_seviyesi("MANUEL"))


class KadroSeviyeTests(unittest.TestCase):
    def test_seviye_esikleri(self):
        from nexora.kadro import seviye
        m = lambda n, o, md: dict(n=n, ort=o, medyan=md, pozitif=0.5)
        self.assertEqual(seviye(m(20, 9.3, 4.9)), "kanitlanmis")            # DtVW
        self.assertEqual(seviye(m(16, 3.5, 8.1)), "normal")                 # 31Z4: ortalama %5'in altında
        self.assertEqual(seviye(m(20, 9.0, -1.0)), "normal")                # medyan negatif: kanıtlanmış değil
        self.assertEqual(seviye(m(2, 9.8, 9.8)), "yeni")                    # 6KBN: az ölçüm
        self.assertEqual(seviye(None), "yeni")
