import json, math, os, random, sqlite3, tempfile, unittest
from nexora import etiket as E
from nexora.ozellik import ozellikler, veri_seti, temel_cizgiler, kalite, OZELLIKLER, sinyalleri_oku
from nexora.model import degerlendir, Model
import yz_veri, yz_model


def doldur(path, n, isaret=True, tohum=1):
    """Yapay veri: isaret=True ise organik skor gerçekten getiriyi belirler; False ise getiri tamamen rastgele."""
    E.Etiketci(path, None).db.close()
    c = sqlite3.connect(path); r = random.Random(tohum)
    for i in range(n):
        org = r.uniform(0, 100)
        y = (org - 50) * 0.4 + r.gauss(0, 12) if isaret else r.gauss(-2, 15)
        ts = 1_000_000 + i // 24 * 86400 + i % 24 * 1800
        likidite = None if i % 10 == 0 else r.uniform(1e3, 1e6)
        o = dict(event_id=f"e{i}", ts=ts, wallet=f"W{i % 7}", token=f"T{i}", gecikme_sn=r.uniform(0, 5),
                 karar="KOPYALANDI" if i % 3 else "REDDEDİLDİ", giris_usdc=5, qty_raw="5000000", al_sat_kaybi_pct=2,
                 olcum_v=1, giris_ts=ts+2, roundtrip_ts=ts+3, kayit_ts=ts+4, karar_ts=ts+1, ucret_usdc=0.02,
                 kaynak_vade=ts+100, t0_token_ts=ts-10, t0_token=json.dumps(dict(tb_organik=org, tb_likidite=likidite)),
                 tb_likidite=likidite, durum="tamam")
        c.execute(f"INSERT INTO etiket_olay({','.join(o)}) VALUES({','.join('?' for _ in o)})", tuple(o.values()))
        cikis = round(5.02 + 5 * y / 100, 6)
        c.execute("INSERT INTO etiket_sonuc VALUES(?,?,?,?,?,?,?)",
                  (f"e{i}", "kaynak", ts+100, cikis, E.getiri(cikis, 5), 0, None))
    c.commit(); c.close()


class SizintiTests(unittest.TestCase):
    def test_only_t0_columns_allowed(self):
        with self.assertRaises(ValueError): ozellikler({"event_id": "e", "getiri_pct": 5})
        o = ozellikler({"event_id": "e", "karar": "KOPYALANDI", "saat_utc": 6})
        self.assertEqual(set(o), set(OZELLIKLER)); self.assertAlmostEqual(o["saat_sin"], 1.0)

    def test_features_independent_of_outcomes(self):
        p = os.path.join(tempfile.mkdtemp(), "e.db"); doldur(p, 60)
        once = {e: o for _, e, _, o, _ in veri_seti(p)}
        c = sqlite3.connect(p); c.execute("UPDATE etiket_sonuc SET cikis_usdc=4, getiri_pct=-20.4"); c.commit(); c.close()
        sonra = {e: o for _, e, _, o, _ in veri_seti(p)}
        self.assertEqual(once, sonra)

    def test_time_order_and_unlabeled_excluded(self):
        p = os.path.join(tempfile.mkdtemp(), "e.db"); doldur(p, 30)
        c = sqlite3.connect(p); c.execute("DELETE FROM etiket_sonuc WHERE event_id='e5'"); c.commit(); c.close()
        v = veri_seti(p)
        self.assertEqual(len(v), 29); self.assertEqual([x[0] for x in v], sorted(x[0] for x in v))


class TemelTests(unittest.TestCase):
    def test_baselines_and_quality(self):
        p = os.path.join(tempfile.mkdtemp(), "e.db"); doldur(p, 100)
        v = veri_seti(p); t = {x["yontem"]: x for x in temel_cizgiler(v)}
        self.assertEqual(t["hepsini kopyala"]["n"], 100); self.assertEqual(t["botun kararı (şu anki kurallar)"]["n"], 66)
        q = kalite(v); self.assertEqual((q["n"], q["cuzdan_sayisi"]), (100, 7)); self.assertEqual(q["eksik_pct"]["log_likidite"], 10.0)
        d = tempfile.mkdtemp(); out = yz_veri.rapor(p, csv_yol=os.path.join(d, "x.csv"))
        self.assertIn("hepsini kopyala", out); self.assertEqual(len(open(os.path.join(d, "x.csv")).readlines()), 101)


class ModelTests(unittest.TestCase):
    def test_finds_planted_signal(self):
        p = os.path.join(tempfile.mkdtemp(), "e.db"); doldur(p, 600, isaret=True)
        s, m = degerlendir(sinyalleri_oku(p)[0], bootstrap=300)
        self.assertEqual(s["karar"], "avantaj var"); self.assertIsNotNone(m)
        self.assertEqual(s["agirliklar"][0][0], "organik"); self.assertGreater(s["agirliklar"][0][1], 0)
        self.assertGreater(s["fark_guven_araligi"][0], 0); self.assertLess(s["brier"], s["brier_taban"])
        self.assertEqual(s["kopya"]["n"], s["net"]["ortak_n"])
        self.assertGreater(s["kopya"]["n"], 0)
        self.assertEqual(s["kopya"]["secilen"], s["net"]["ortak_model"]["secili"])

    def test_no_signal_no_advantage(self):
        kabul = 0
        for t in range(3):
            p = os.path.join(tempfile.mkdtemp(), "e.db"); doldur(p, 600, isaret=False, tohum=10 + t)
            s, m = degerlendir(sinyalleri_oku(p)[0], bootstrap=300)
            kabul += s["karar"] == "avantaj var"
        self.assertEqual(kabul, 0)

    def test_insufficient_data_and_cli(self):
        p = os.path.join(tempfile.mkdtemp(), "e.db"); doldur(p, 100)
        self.assertIn("Yetersiz veri: 100/500", yz_model.calistir(p))
        d = tempfile.mkdtemp(); p2 = os.path.join(d, "e.db"); doldur(p2, 600)
        out = yz_model.calistir(p2, yol=os.path.join(d, "m.json"))
        self.assertIn("AVANTAJ VAR", out)
        self.assertIn("Kopyalanan cüzdanlar", out)
        j = json.load(open(os.path.join(d, "m.json"))); self.assertEqual(j["ozellikler"][0], "log_gecikme")
        self.assertIn("esik", j)


if __name__ == "__main__":
    unittest.main()


class GolgeOzellikTests(unittest.TestCase):
    def test_izlenen_bot_karari_bilinmiyor_ve_teyit(self):
        o = ozellikler(dict(karar="REDDEDİLDİ", gerekce="cüzdan yalnızca izleniyor", teyit=3))
        self.assertIsNone(o["bot_kopyaladi"]); self.assertGreater(o["log_teyit"], 0)
        self.assertEqual(ozellikler(dict(karar="KOPYALANDI", gerekce="geçti"))["bot_kopyaladi"], 1.0)
