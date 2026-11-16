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
        for bad in [{"max_pos_pct": 0.06}, {"daily_loss_pct": 0.05}, {"max_positions": 9}, {"max_positions_per_wallet": 3},
                    {"max_roundtrip_loss_pct": 7}, {"max_signal_age_s": 30}, {"max_positions": 0},
                    {"start_cash": 1000}, {"max_positions": 2.5}, {"max_positions": "3"}, {"max_positions": True}, {}]:
            with self.assertRaises(ValueError, msg=str(bad)): self.p.ayar_degistir(bad)

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
        c, d = self.call("/ayarlar", {"max_positions": 9}); self.assertEqual(c, 400); self.assertIn("arasında", d["hata"])
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
