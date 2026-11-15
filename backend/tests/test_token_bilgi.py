import datetime, os, tempfile, unittest
from unittest.mock import Mock

from nexora.core import Paper
from nexora.token_bilgi import TokenBilgi, Toplayici, BilgiHatasi, parse, _ts, URL_KEY, URL_LITE
from nexora.rapor import bilgi_summary, build_report, as_text
import token_filtre

MINT = "MEME111111111111111111111111111111"
NOW = 1_763_240_000.0

def iso(t): return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def item(**kw):
    d = {"id": MINT, "createdAt": iso(NOW - 7200), "firstPool": {"id": "P", "createdAt": iso(NOW - 3000)},
         "liquidity": 42000.5, "mcap": 90000, "holderCount": 812, "organicScore": 23.4, "organicScoreLabel": "low",
         "audit": {"topHoldersPercentage": 31.2, "devBalancePercentage": 2.5, "mintAuthorityDisabled": True},
         "launchpad": "pump.fun"}
    d.update(kw); return d

def resp(status=200, body=None):
    r = Mock(status_code=status); r.json = Mock(return_value=body); return r


class ParseTests(unittest.TestCase):
    def test_fields(self):
        d = parse(item(), NOW)
        self.assertAlmostEqual(d["yas_sn"], 3000, delta=1)          # ilk havuz zamanı öncelikli
        self.assertEqual((d["likidite"], d["sahip"], d["organik"], d["top_pct"], d["sus"]), (42000.5, 812, 23.4, 31.2, 0))
    def test_sus_presence_and_fallback_age(self):
        d = parse(item(firstPool=None, audit={"isSus": False}), NOW)
        self.assertEqual(d["sus"], 1)                               # alanın varlığı yeterli
        self.assertAlmostEqual(d["yas_sn"], 7200, delta=1)
    def test_missing_and_bad_values(self):
        d = parse({"id": MINT, "liquidity": True, "createdAt": "bozuk"}, NOW)
        self.assertIsNone(d["likidite"]); self.assertIsNone(d["yas_sn"])
    def test_ts_formats(self):
        self.assertEqual(_ts(1_700_000_000_000), 1_700_000_000); self.assertEqual(_ts("1700000000"), 1_700_000_000)


class FetchTests(unittest.TestCase):
    def tb(self, r, key=""):
        s = Mock(); s.get = Mock(return_value=r); return TokenBilgi(api_key=key, session=s), s
    def test_hosts(self):
        t, s = self.tb(resp(body=[item()]))
        t.fetch(MINT, now=NOW)
        self.assertEqual(s.get.call_args.args[0], URL_LITE); self.assertEqual(s.get.call_args.kwargs["headers"], {})
        t, s = self.tb(resp(body=[item()]), key="k")
        t.fetch(MINT, now=NOW)
        self.assertEqual(s.get.call_args.args[0], URL_KEY); self.assertEqual(s.get.call_args.kwargs["headers"], {"x-api-key": "k"})
    def test_errors(self):
        for r, msg in [(resp(401), "HTTP 401"), (resp(body={"error": "x"}), "geçersiz"),
                       (resp(body=[item(id="BASKA")]), "bulunamadı")]:
            t, _ = self.tb(r)
            with self.assertRaises(BilgiHatasi) as c: t.fetch(MINT, now=NOW)
            self.assertIn(msg, str(c.exception))


class ToplayiciTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "p.db"); self.p = Paper(self.path)

    def test_saves_result_and_error(self):
        f = Mock(); f.fetch = Mock(return_value=parse(item(), NOW))
        t = Toplayici(f, self.p)
        t.enqueue("e1", MINT); t.isle(t.q.get())
        f.fetch = Mock(side_effect=BilgiHatasi("HTTP 401")); t.enqueue("e2", MINT); t.isle(t.q.get())
        rows = {r["event_id"]: dict(r) for r in self.p.db.execute("SELECT * FROM token_bilgi")}
        self.assertEqual(rows["e1"]["likidite"], 42000.5); self.assertIsNone(rows["e1"]["hata"])
        self.assertEqual(rows["e2"]["hata"], "HTTP 401")

    def test_full_queue_never_blocks(self):
        t = Toplayici(Mock(), self.p, maxsize=1)
        t.enqueue("a", MINT); t.enqueue("b", MINT)             # ikincisi sessizce düşer
        self.assertEqual(t.q.qsize(), 1)

    def test_summary_groups_real_and_shadow(self):
        p = self.p
        p.record_buy("b1", "W", "T1", 5.0, 1_000_000, 6); p.record_sell("s1", "W", "T1", 3.0)      # kopya, kayıp
        p.shadow_open("g1", "W", "T2", 5.0, 1_000_000, 6, 8.0, None, "al-sat")
        sid = p.db.execute("SELECT id FROM shadow").fetchone()["id"]; p.shadow_close(sid, 7.0, "x")  # gölge, kazanç
        p.token_bilgi_kaydet("b1", "T1", NOW, parse(item(), NOW))                                   # genç, 42k
        p.token_bilgi_kaydet("g1", "T2", NOW, parse(item(liquidity=500000.0, firstPool={"createdAt": iso(NOW - 10 * 86400)}), NOW))
        p.token_bilgi_kaydet("x9", "T3", NOW, None, hata="HTTP 429")
        r = build_report(self.path)["token_bilgi"]
        self.assertEqual((r["olculen"], r["hatali"], r["kapanan_ornek"]), (3, 1, 2))
        yas = next(b for b in r["boyutlar"] if b["boyut"] == "Token yaşı")["gruplar"]
        self.assertEqual([(g["grup"], g["kopya"], g["golge"], g["kazanan"]) for g in yas],
                         [("1 saatten genç", 1, 0, 0), ("7 günden yaşlı", 0, 1, 1)])
        self.assertAlmostEqual(yas[0]["ort_getiri"], round((3.0 - 0.01 - 5) / 5 * 100, 1))
        self.assertIn("Token özellikleri", as_text(build_report(self.path)))
        txt = token_filtre.report(self.path)
        self.assertIn("Likidite", txt); self.assertIn("250 bin $ üstü", txt)

    def test_empty_report(self):
        self.assertIn("Henüz ölçüm yok", token_filtre.report(self.path))


class DecisionHookTests(unittest.TestCase):
    def test_enqueued_only_after_copy_or_shadow(self):
        from nexora.decision import Decider
        from nexora.constants import USDC_MINT
        p = Paper(); bilgi = Mock()
        safety = Mock(); safety.check = Mock(return_value={"verdict": "UYGUN", "reasons": [], "decimals": 6})
        q = Mock()
        q.quote = Mock(side_effect=lambda i, o, a: dict(out_amount=1_000_000 if i == USDC_MINT else int(a * 0) + 4_950_000,
                                                         price_impact_pct=0.5, in_amount=a))
        d = Decider(p, q, safety, bilgi=bilgi)
        r = d.decide("e1", "W", MINT, "buy", 1)
        self.assertEqual(r["decision"], "KOPYALANDI"); bilgi.enqueue.assert_called_once_with("e1", MINT)
        bilgi.enqueue.reset_mock()
        safety.check = Mock(return_value={"verdict": "RİSKLİ", "reasons": ["x"], "decimals": 6})
        d.decide("e2", "W", "OTHER", "buy", 1)
        bilgi.enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
