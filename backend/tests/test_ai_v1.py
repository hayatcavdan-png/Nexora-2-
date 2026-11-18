import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nexora import etiket as E
from nexora.ai_denetim import rapor
from nexora.constants import USDC_MINT
from nexora.model import Model, degerlendir, zaman_bol
from nexora.model_kapisi import ModelDosyasi, ModelKapisi
from nexora.olcum import GIRIS_TOLERANS, KAYNAK_TOLERANS
from nexora.ozellik import Sinyal, aileler, sinyalleri_oku, t0_ozellikler
from test_etiket import B, Q
from test_yz import doldur
import yz_model


class EtiketV1Tests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = Path(d.name) / "fixture ? #.db"
        self.clock = 1_000_000
        self.q = Q()
        self.e = self.etiketci()

    def etiketci(self, **kw):
        e = E.Etiketci(self.path, self.q, bilgi=B(), clock=lambda: self.clock, **kw)
        self.addCleanup(e.db.close)
        return e

    def sinyal(self, id, wallet="C1", token="T1", side="buy", block=None, karar="KOPYALANDI", gerekce=""):
        self.e.sinyal(id, wallet, token, side, id, self.clock - 5 if block is None else block, 5, karar, gerekce)

    def ilerle(self, sn):
        self.clock += sn
        while self.e.adim():
            pass

    def test_persisted_source_sell_across_restart_and_entry_notional(self):
        with patch.object(E, "ETIKET_USD", 7.50):
            self.sinyal("buy")
            self.ilerle(0)
        self.clock += 40
        self.sinyal("sell", side="sell")
        self.sinyal("sell", side="sell")
        self.e = self.etiketci()
        self.q.carpan = 1.2
        self.ilerle(0)
        s = self.e.db.execute("SELECT * FROM etiket_sonuc").fetchone()
        self.assertEqual(s["ufuk"], "kaynak")
        self.assertAlmostEqual(s["getiri_pct"], E.getiri(s["cikis_usdc"], 7.50))
        self.assertEqual(sum(c[0] == "T1" for c in self.q.calls), 2)

    def test_sale_while_entry_queued_is_unknown(self):
        self.sinyal("buy")
        self.clock += 10
        self.sinyal("sell", side="sell")
        self.ilerle(0)
        s = self.e.db.execute("SELECT * FROM etiket_sonuc").fetchone()
        self.assertEqual((s["hata"], s["cikis_usdc"], s["getiri_pct"]), ("girişten önce satış", None, None))
        self.assertEqual(len(self.q.calls), 2)

    def test_older_source_sale_does_not_attach_and_timeout_never_quotes(self):
        self.sinyal("buy")
        self.ilerle(0)
        self.clock += 20
        self.sinyal("old", side="sell", block=self.clock - 40)
        self.ilerle(0)
        self.assertIsNone(self.e.db.execute("SELECT kaynak_vade FROM etiket_olay").fetchone()[0])
        self.ilerle(280)
        self.ilerle(1500)
        n = len(self.q.calls)
        self.ilerle(E.KAYNAK_ZAMAN_ASIMI)
        s = self.e.db.execute("SELECT * FROM etiket_sonuc WHERE ufuk='kaynak'").fetchone()
        self.assertIsNone(s["getiri_pct"])
        self.assertIn("zaman aşımı", s["hata"])
        self.assertEqual(len(self.q.calls), n)

    def test_quote_crossing_deadline_is_unknown(self):
        self.sinyal("buy")
        self.ilerle(0)
        original = self.q.quote

        def gec(*args):
            self.clock += KAYNAK_TOLERANS + 1
            return original(*args)

        self.q.quote = gec
        self.clock += 20
        self.sinyal("sell", side="sell")
        self.ilerle(0)
        s = self.e.db.execute("SELECT * FROM etiket_sonuc WHERE ufuk='kaynak'").fetchone()
        self.assertEqual((s["hata"], s["sapma_sn"], s["getiri_pct"]), ("kaçırıldı", KAYNAK_TOLERANS + 1, None))

    def test_late_and_malformed_entry_never_label(self):
        self.sinyal("late")
        self.ilerle(GIRIS_TOLERANS + 1)
        self.assertEqual(self.q.calls, [])
        self.q.quote = lambda *_: dict(out_amount=float("inf"), in_amount=1)
        self.sinyal("broken", token="T2")
        self.ilerle(0)
        self.assertEqual(self.e.db.execute("SELECT COUNT(*) FROM etiket_sonuc").fetchone()[0], 0)
        r = rapor(self.path, now=self.clock)
        self.assertEqual(r["ufuklar"]["kaynak"]["unknown"], 2)
        self.assertIsNone(r["ufuklar"]["kaynak"]["net"]["hepsini_kopyala"]["sinyal_basi_usdc"])
        self.assertEqual(r["ufuklar"]["kaynak"]["net"]["alim_yok"]["sinyal_basi_usdc"], 0)

    def test_t0_snapshot_excludes_same_time_and_post_decision_fields(self):
        self.sinyal("a")
        self.sinyal("b", wallet="C2")
        self.ilerle(0)
        self.clock += 1
        self.sinyal("c", wallet="C3")
        self.ilerle(0)
        rows = {s.olay["event_id"]: s.olay for s in sinyalleri_oku(self.path)[0]}
        self.assertEqual([rows[k]["teyit"] for k in ("a", "b", "c")], [1, 1, 3])
        self.assertIsNone(t0_ozellikler(rows["b"])["log_likidite"])
        once = t0_ozellikler(rows["c"])
        self.assertIsNotNone(once["log_likidite"])
        sonra = t0_ozellikler(dict(rows["c"], karar="REDDEDİLDİ", cuzdan='{"skor":42}', tb_likidite=1,
                                     giris_etki=200, al_sat_kaybi_pct=50))
        self.assertEqual(once, sonra)
        self.assertIsNone(once["bot_kopyaladi"])
        self.assertIsNone(t0_ozellikler(dict(rows["c"], t0_token_ts=rows["c"]["ts"]))["log_likidite"])
        self.assertIsNone(t0_ozellikler(dict(rows["c"], t0_token="[]"))["log_likidite"])


class DogrulamaV1Tests(unittest.TestCase):
    def test_purge_overlap_equal_timestamp_and_linked_signature(self):
        ts = [10, 20, 30, 40, 40, 50, 60, 60, 60, 70]
        tok = ["A", "B", "C", "D", "E", "F", "G", "B", "H", "I"]
        sons = [19, 29, 60, 45, 46, 55, 61, 62, 63, 74]
        sinyaller = [Sinyal(dict(ts=t, token=k, sig="ortak" if k in ("D", "H") else None), {}, None)
                     for t, k in zip(ts, tok)]
        veri = [SimpleNamespace(ts=s.ts, token=s.token, cikis_ts=x) for s, x in zip(sinyaller, sons)]
        e, s, n = zaman_bol(veri, 0.7, aile=aileler(sinyaller))
        self.assertEqual([r.token for r in e], ["A", "E", "F"])
        self.assertEqual([r.ts for r in s], [60, 60, 60, 70])
        self.assertEqual(n, 3)

    def test_low_diversity_and_forced_runs_do_not_save_models(self):
        with tempfile.TemporaryDirectory() as d:
            db, yol = Path(d) / "e.db", Path(d) / "s.json"
            doldur(db, 520)
            with sqlite3.connect(db) as c:
                c.execute("UPDATE etiket_olay SET token='aynı token'")
            result, model = degerlendir(sinyalleri_oku(db)[0])
            self.assertIsNone(model)
            self.assertIn("veri çeşitliliği", result["gerekceler"])
            self.assertEqual(result["aile_n"], 1)
            self.assertEqual(result["egitim"], 0)
            yz_model.calistir(db, zorla=True, yol=yol)
            self.assertFalse(yol.exists())

    def test_non_finite_and_corrupt_model(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "m.json"
            m = Model(["organik"]).egit([{"organik": float("nan")}, {"organik": "inf"}, {"organik": 99}], [-1, -1, 1])
            self.assertEqual(m.olasilik([{"organik": float("nan")}]), m.olasilik([{}]))
            m.kaydet(yol, {"esik": 0.5})
            j = json.loads(yol.read_text())
            for alan, v in (("b", float("nan")), ("std", {"organik": 0}), ("esik", float("inf"))):
                yol.write_text(json.dumps(dict(j, **{alan: v})))
                self.assertIsNone(ModelDosyasi(yol).yukle())

    def test_v1_model_rejects_past_signals_and_uses_other_file_than_closed_filter(self):
        with tempfile.TemporaryDirectory() as d:
            yol, ayar = Path(d) / "v1.json", Path(d) / "filtre.json"
            m = Model(["organik"]).egit([{"organik": 20}, {"organik": 70}], [-1, 1])
            with patch("nexora.model.time.time", return_value=2000):
                m.kaydet(yol, dict(esik=0.5, golge_v1=True, ufuk="kaynak", son_veri_ts=1999))
            self.assertIsNone(ModelDosyasi(yol).yukle())
            md = ModelDosyasi(yol, golge=True)
            self.assertIsNone(md.golge_olasilik(dict(ts=1999)))
            self.assertIsNotNone(md.golge_olasilik(dict(ts=2001, olcum_v=1)))
            self.assertIsNone(ModelKapisi(md, ayar_yolu=ayar).izin("W", "T", 1, 0.5, 2.0))
            self.assertFalse(ayar.exists())


class RaporV1Tests(unittest.TestCase):
    def test_four_classes_masked_data_and_repeatable_read_only_report(self):
        class ModelStub:
            def golge_olasilik(self, row):
                p = 0.1 if row["wallet"] == "C2" else 0.9
                return dict(olasilik=p, esik=0.5, surum="999900-abcdef12", secerdi=p >= 0.5)

        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "local ?.db"
            q = Q()
            q.fail = {(USDC_MINT, "MINT-EKSIK")}
            e = E.Etiketci(db, q, bilgi=B(), clock=lambda: 1_000_000, golge_model=ModelStub())
            for i, (w, k, karar, neden) in enumerate((
                ("C1", "MINT-PRIVATE", "KOPYALANDI", "api-key=GIZLI"),
                ("C2", "T2", "KOPYALANDI", ""),
                ("C3", "T3", "REDDEDİLDİ", "token REDDEDİLDİ: auth=GIZLI"),
                ("C4", "MINT-EKSIK", "KOPYALANDI", ""),
            )):
                e.sinyal(f"SIG-HASSAS-{i}", w, k, "buy", "SIG-HASSAS", 999_995, 5, karar, neden)
            while e.adim():
                pass
            with e.db:
                e.db.execute("INSERT INTO etiket_sonuc VALUES('SAHIPSIZ', 'kaynak', 1000002, 5, 0, 0, NULL)")
            e.db.close()
            once = db.read_bytes()
            report = rapor(db, now=1_200_000, ayrinti=True)
            self.assertEqual(report, rapor(db, now=1_200_000, ayrinti=True))
            self.assertEqual(once, db.read_bytes())
            self.assertEqual(set(report["golge"]["siniflar"]), {"PAPER-ADAY", "GÖLGE-İZLE", "RİSK-RED", "VERİ-YETERSİZ"})
            self.assertEqual(report["eslesmeyen_etiket"], 1)
            self.assertEqual(report["token_ailesi_sayisi"], 1)
            self.assertEqual(report["ufuklar"]["kaynak"]["net"]["hepsini_kopyala"]["unknown_sonuc"], 4)
            raw = json.dumps(report, ensure_ascii=False, allow_nan=False)
            for secret in ("MINT-PRIVATE", "C1", "SIG-HASSAS", "SAHIPSIZ", "GIZLI", "api-key", "auth"):
                self.assertNotIn(secret, raw)

    def test_legacy_db_unknown_and_no_creation_for_absent_db(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "old.db"
            self.assertEqual(rapor(db)["durum"], "veri yok")
            self.assertFalse(db.exists())
            with sqlite3.connect(db) as c:
                # V1 öncesindeki iki tablo, sonradan eklenmiş sütunlar bulunmuyor.
                c.executescript(E.SEMA.split("CREATE TABLE IF NOT EXISTS etiket_kaynak_satis")[0])
                c.execute("""INSERT INTO etiket_olay(event_id, ts, wallet, token, giris_usdc, qty_raw, al_sat_kaybi_pct)
                             VALUES('e', 1000, 'W', 'T', 5, '10', 2)""")
                c.execute("INSERT INTO etiket_sonuc VALUES('e', 'kaynak', 1010, 0, -100.4, 0, 'satılamadı: sır')")
                c.execute("INSERT INTO etiket_sonuc VALUES('e', '5dk', 1300, 6, 19.6, 0, NULL)")
                c.execute("INSERT INTO etiket_sonuc VALUES('e', '30dk', 2800, 6, ?, 0, NULL)", (float("inf"),))
            report = rapor(db, now=100_000, ayrinti=True)
            self.assertEqual(report["ufuklar"]["kaynak"]["satis_yolu_hatasi"], 1)
            self.assertEqual(report["ufuklar"]["5dk"]["dogrulanamayan_eski_kayit"], 1)
            self.assertEqual(report["ufuklar"]["30dk"]["net_ornek"], 0)
            self.assertTrue(all(x["durum"] == "UNKNOWN" for x in report["sinyaller"][0]["sonuclar"].values()))
            with sqlite3.connect(db) as c:
                self.assertNotIn("olcum_v", [r[1] for r in c.execute("PRAGMA table_info(etiket_olay)")])
