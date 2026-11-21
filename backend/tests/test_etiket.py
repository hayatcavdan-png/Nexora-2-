import json, os, sqlite3, tempfile, unittest
from nexora.constants import USDC_MINT
from nexora.market import QuoteError
from nexora import etiket as E


class Q:
    """USDC->TOK: 1 USDC = 100 token birimi. TOK->USDC: fiyat çarpanı ile."""
    def __init__(self): self.carpan, self.calls, self.fail = 1.0, [], set()
    def bos(self): return True
    def quote(self, i, o, amt):
        self.calls.append((i, o, amt))
        if (i, o) in self.fail: raise QuoteError("rota yok")
        if i == USDC_MINT: return dict(out_amount=amt * 100, price_impact_pct=0.4)
        return dict(out_amount=int(amt / 100 * self.carpan * 0.98), price_impact_pct=0.3)


class B:
    def fetch(self, token, now=None): return dict(yas_sn=3600, likidite=42000, organik=25.0, top_pct=30.0, sus=0, sahip=500, mcap=1e5)


class EtiketTests(unittest.TestCase):
    def setUp(self):
        self.t = [1_000_000.0]
        self.q = Q()
        self.path = os.path.join(tempfile.mkdtemp(), "e.db")
        self.e = E.Etiketci(self.path, self.q, bilgi=B(), cuzdanlar={"W": {"skor": "1.2"}},
                            clock=lambda: self.t[0], sleep=lambda s: None)

    def run_all(self):
        while self.e.adim(): pass

    def at(self, sn): self.t[0] += sn; self.run_all()

    def rows(self, sql, *a): return [dict(r) for r in self.e.db.execute(sql, a)]

    def test_entry_features(self):
        self.e.sinyal("W:s1", "W", "TOK", "buy", "s1", 999_990, 1.5, "REDDEDİLDİ", "al-sat kaybı yüksek")
        self.run_all()
        o = self.rows("SELECT * FROM etiket_olay")[0]
        self.assertEqual((o["durum"], o["qty_raw"], o["karar"], o["tb_likidite"]), ("izleniyor", "500000000", "REDDEDİLDİ", 42000))
        self.assertAlmostEqual(o["al_sat_kaybi_pct"], 2.0)
        self.assertEqual(json.loads(o["cuzdan"])["skor"], "1.2")

    def test_shadow_model_decision(self):
        gorulen = []
        class M:
            def olasilik(self, satir, db=None):
                gorulen.append(satir); return dict(olasilik=0.8, esik=0.5, surum="v1", secerdi=True)
        self.e.model = M()
        self.e.sinyal("W:s1", "W", "TOK", "buy", "s1", 999_990, 1.5, "KOPYALANDI", "")
        self.run_all()
        g = self.rows("SELECT * FROM golge_karar")
        self.assertEqual([(x["event_id"], x["model_surumu"], x["secerdi"]) for x in g], [("W:s1", "v1", 1)])
        self.assertAlmostEqual(gorulen[0]["al_sat_kaybi_pct"], 2.0)                    # t0 özellikleriyle çağrılır
        class Bozuk:
            def olasilik(self, satir): raise RuntimeError("x")
        self.e.model = Bozuk(); self.t[0] += 4000
        self.e.sinyal("W:s2", "W", "TOK2", "buy", "s2", self.t[0] - 1, 1.0, "KOPYALANDI", ""); self.run_all()
        self.assertEqual(len(self.rows("SELECT * FROM etiket_olay")), 2)                # model hatası etiketlemeyi durdurmaz

    def test_horizons_and_source_sell(self):
        self.e.sinyal("W:s1", "W", "TOK", "buy", "s1", 0, 1, "KOPYALANDI", "ok"); self.run_all()
        self.q.carpan = 1.5; self.at(300)                                     # 5 dk
        self.q.carpan = 0.5; self.at(1500)                                    # 30 dk
        self.q.carpan = 2.0; self.e.sinyal("W:s2", "W", "TOK", "sell", "s2", 0, 1, "x", "x"); self.run_all()
        s = {r["ufuk"]: r for r in self.rows("SELECT * FROM etiket_sonuc")}
        self.assertEqual(set(s), {"5dk", "30dk", "kaynak"})
        self.assertAlmostEqual(s["5dk"]["getiri_pct"], E.getiri(5 * 1.5 * 0.98))
        self.assertAlmostEqual(s["kaynak"]["getiri_pct"], E.getiri(5 * 2.0 * 0.98))
        self.assertEqual(self.rows("SELECT durum FROM etiket_olay")[0]["durum"], "tamam")
        self.at(E.KAYNAK_ZAMAN_ASIMI)                                         # zaman aşımı artık iş yapmaz
        self.assertEqual(len(self.rows("SELECT * FROM etiket_sonuc")), 3)
        oz = E.ozet(self.path)
        self.assertEqual((oz["etiketli"], oz["tamam"], oz["ufuklar"]["kaynak"]["kazanan"]), (1, 1, 1))

    def test_dedup_cap_and_no_route(self):
        self.e.sinyal("W:a", "W", "TOK", "buy", "a", 0, 1, "x", "x")
        self.e.sinyal("W:b", "W", "TOK", "buy", "b", 0, 1, "x", "x")          # 30 dk içinde aynı cüzdan+token
        self.q.fail = {(USDC_MINT, "BAD")}
        self.e.sinyal("W:c", "W", "BAD", "buy", "c", 0, 1, "x", "x")
        self.run_all()
        d = {r["event_id"]: r["durum"] for r in self.rows("SELECT event_id, durum FROM etiket_olay")}
        self.assertEqual(d, {"W:a": "izleniyor", "W:c": "giris_yok"})
        old = E.GUNLUK; E.GUNLUK = 2
        try:
            self.e.sinyal("Z:d", "Z", "T2", "buy", "d", 0, 1, "x", "x"); self.run_all()
            self.assertEqual(len(self.rows("SELECT * FROM etiket_olay")), 2)
            self.e.sinyal("Z:e", "Z", "T3", "buy", "e", 0, 1, "KOPYALANDI", "ok"); self.run_all()     # gerçek işlem sınıra takılmaz
            self.assertEqual(len(self.rows("SELECT * FROM etiket_olay")), 3)
        finally:
            E.GUNLUK = old

    def test_golge_ayri_sinir_ve_teyit(self):
        old = (E.GUNLUK, E.GOLGE_GUNLUK); E.GUNLUK, E.GOLGE_GUNLUK = 2, 1
        try:
            self.e.sinyal("G1:a", "G1", "TOK", "buy", "a", 0, 1, "REDDEDİLDİ", E.IZLENEN); self.run_all()
            self.e.sinyal("G2:b", "G2", "TOK", "buy", "b", 0, 1, "REDDEDİLDİ", E.IZLENEN); self.run_all()   # gölge sınırı dolu
            self.e.sinyal("W:c", "W", "TOK", "buy", "c", 0, 1, "KOPYALANDI", "geçti"); self.run_all()       # kopyalanan etkilenmez
            d = {r["event_id"]: r["teyit"] for r in self.rows("SELECT event_id, teyit FROM etiket_olay")}
            self.assertEqual(d, {"G1:a": 1, "W:c": 2})
        finally:
            E.GUNLUK, E.GOLGE_GUNLUK = old

    def test_missed_horizon_and_unsellable_and_timeout(self):
        self.e.sinyal("W:a", "W", "TOK", "buy", "a", 0, 1, "x", "x"); self.run_all()
        self.t[0] += 300 + 500                                               # 5 dk vadesi tolerans dışında
        self.q.fail = {("TOK", USDC_MINT)}
        self.run_all()
        s = {r["ufuk"]: r for r in self.rows("SELECT * FROM etiket_sonuc")}
        self.assertEqual(s["5dk"]["hata"], "kaçırıldı"); self.assertIsNone(s["5dk"]["getiri_pct"])
        self.at(1000)                                                        # 30 dk vadesinde satılamıyor
        s = {r["ufuk"]: r for r in self.rows("SELECT * FROM etiket_sonuc")}
        self.assertTrue(s["30dk"]["hata"].startswith("satılamadı")); self.assertAlmostEqual(s["30dk"]["getiri_pct"], -100.4)
        self.q.fail = set(); self.at(E.KAYNAK_ZAMAN_ASIMI)
        s = {r["ufuk"]: r for r in self.rows("SELECT * FROM etiket_sonuc")}
        self.assertIn("zaman aşımı", s["kaynak"]["hata"]); self.assertIsNotNone(s["kaynak"]["getiri_pct"])

    def test_restart_reschedules(self):
        self.e.sinyal("W:a", "W", "TOK", "buy", "a", 0, 1, "x", "x"); self.run_all()
        e2 = E.Etiketci(self.path, self.q, clock=lambda: self.t[0], sleep=lambda s: None)
        self.assertEqual(sorted(u for _, _, u in e2.plan), ["30dk", "5dk", "kaynak_asim"])
        self.t[0] += 300
        while e2.adim(): pass
        self.assertEqual([r["ufuk"] for r in self.rows("SELECT ufuk FROM etiket_sonuc")], ["5dk"])

    def test_tracker_hook(self):
        from nexora.live_tracker import LiveTracker
        from nexora.core import Paper
        tr = LiveTracker(None, Paper(), os.path.join(tempfile.mkdtemp(), "t.db"), ["W"], etiketci=self.e)
        self.assertIs(tr.etiketci, self.e)


if __name__ == "__main__":
    unittest.main()
