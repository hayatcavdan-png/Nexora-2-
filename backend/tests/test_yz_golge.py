import os, sqlite3, tempfile, unittest
from nexora import yz_golge


def _db(olaylar, sonuclar=()):
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False); f.close()
    db = sqlite3.connect(f.name)
    db.executescript("""CREATE TABLE etiket_olay(event_id TEXT PRIMARY KEY, ts REAL, wallet TEXT, token TEXT, karar TEXT,
      gerekce TEXT, giris_usdc REAL, saat_utc INTEGER, gun INTEGER, giris_etki REAL, al_sat_kaybi_pct REAL,
      tb_yas_sn REAL, tb_likidite REAL, tb_mcap REAL, tb_sahip REAL, tb_organik REAL, tb_top_pct REAL, tb_dev_pct REAL,
      tb_sus INTEGER, cuzdan TEXT, durum TEXT, hata TEXT, sig TEXT, block_time REAL, gecikme_sn REAL, qty_raw TEXT);
      CREATE TABLE etiket_sonuc(event_id TEXT, ufuk TEXT, ts REAL, cikis_usdc REAL, getiri_pct REAL, sapma_sn REAL,
      hata TEXT, PRIMARY KEY(event_id, ufuk));""")
    for e in olaylar:
        db.execute("INSERT INTO etiket_olay(event_id,ts,karar,gerekce) VALUES(?,?,?,?)", (e, 1.0, "kopyalanabilir", "x"))
    for e, g in sonuclar:
        db.execute("INSERT INTO etiket_sonuc(event_id,ufuk,ts,getiri_pct) VALUES(?,?,?,?)", (e, "kaynak", 2.0, g))
    db.commit(); db.close()
    return f.name


def _post(metin):
    return lambda govde: {"model": "gemini-3.1-flash-lite", "steps": [{"type": "model_output",
                          "content": [{"type": "text", "text": metin}]}]}


class GolgeTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)

    def test_kapaliyken_cagri_yok(self):
        os.environ.pop("YZ_GOLGE", None)
        p = _db(["a"])
        self.assertEqual(yz_golge.calistir(p)["durum"], "kapali")
        # kapalıyken tablo bile oluşturulmaz: hiçbir yazma yapılmaz
        self.assertIsNone(sqlite3.connect(p).execute("SELECT name FROM sqlite_master WHERE name='golge_llm'").fetchone())

    def test_istem_sonuc_alanlarini_icermez(self):
        s = yz_golge.istem({"karar": "kopyalanabilir", "gerekce": "g", "getiri_pct": 99.0, "sapma_sn": 5.0})
        self.assertNotIn("getiri", s); self.assertNotIn("sapma", s)

    def test_oneri_cozumle(self):
        self.assertEqual(yz_golge.oneri_cozumle("AL."), "AL")
        self.assertEqual(yz_golge.oneri_cozumle("atla"), "ATLA")  # küçük harf büyütülür
        self.assertEqual(yz_golge.oneri_cozumle("Bence AL"), "belirsiz")
        self.assertEqual(yz_golge.oneri_cozumle(None), "belirsiz")

    def test_kayit_yazilir_ve_bir_kez(self):
        os.environ["YZ_GOLGE"] = "1"; os.environ["GEMINI_API_KEY"] = "t"
        p = _db(["a", "b"])
        r1 = yz_golge.calistir(p, post=_post("AL"), now=10.0)
        r2 = yz_golge.calistir(p, post=_post("ATLA"), now=11.0)
        self.assertEqual(r1["islenen"], 2); self.assertEqual(r2["islenen"], 0)
        self.assertEqual(sqlite3.connect(p).execute("SELECT oneri FROM golge_llm WHERE event_id='a'").fetchone()[0], "AL")

    def test_ust_sinir(self):
        os.environ["YZ_GOLGE"] = "1"; os.environ["GEMINI_API_KEY"] = "t"
        p = _db(["a", "b", "c"])
        self.assertEqual(yz_golge.calistir(p, limit=2, post=_post("AL"))["islenen"], 2)

    def test_hata_yutulur_ve_isaretlenir(self):
        os.environ["YZ_GOLGE"] = "1"; os.environ["GEMINI_API_KEY"] = "t"
        p = _db(["a"])
        def boom(govde): raise OSError("ağ")
        r = yz_golge.calistir(p, post=boom)
        self.assertEqual(r["hata"], 1)
        self.assertEqual(sqlite3.connect(p).execute("SELECT hata FROM golge_llm").fetchone()[0], "OSError")

    def test_rapor_karsilastirir(self):
        os.environ["YZ_GOLGE"] = "1"; os.environ["GEMINI_API_KEY"] = "t"
        p = _db(["a", "b"], sonuclar=[("a", 4.0), ("b", -2.0)])
        yz_golge.calistir(p, post=_post("AL"))
        rp = yz_golge.rapor(p)
        self.assertEqual(rp["gemini_al_n"], 2); self.assertEqual(rp["gemini_al_ort"], 1.0)
        self.assertFalse(rp["yeterli"])


if __name__ == "__main__":
    unittest.main()
