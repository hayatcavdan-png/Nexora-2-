import contextlib, io, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cuzdan_tarama as ct

NOW = 1_000_000
W = ["A" * 32, "B" * 32, "C" * 32, "D" * 32, "E" * 32]

def sigs(times, err_every=0):
    return [{"signature": f"s{i}", "blockTime": t, "err": ({"x": 1} if err_every and i % err_every == 0 else None)}
            for i, t in enumerate(sorted(times, reverse=True))]

class Classify(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(ct.classify([], NOW)["durum"], "pasif")
        self.assertEqual(ct.classify(sigs([NOW - 5 * 86400]), NOW)["durum"], "pasif")
        self.assertEqual(ct.classify(sigs([NOW - i * 10 for i in range(40)]), NOW)["durum"], "bot")      # 10 dk'da 40
        self.assertEqual(ct.classify(sigs([NOW - i * 3600 for i in range(10)]), NOW)["durum"], "aday")   # saatte 1
        self.assertEqual(ct.classify(sigs([NOW - 3600]), NOW)["durum"], "düşük aktivite")
        self.assertEqual(ct.classify(sigs([NOW - i * 3600 for i in range(10)], err_every=1), NOW)["durum"], "şüpheli")
    def test_full_page_within_day_marked(self):
        r = ct.classify(sigs([NOW - i * 700 for i in range(100)]), NOW)   # 100 işlem ~19 saatte
        self.assertGreaterEqual(r["islem_24s"], 100); self.assertIn("100", r["not"])

class FakeClient:
    def __init__(self, fail=()): self.calls, self.fail = [], set(fail)
    def call(self, method, params):
        w = params[0]; self.calls.append(w)
        if w in self.fail: raise ValueError("geçici")
        if w == W[0]: return sigs([NOW - i * 10 for i in range(40)])          # bot
        if w == W[1]: return sigs([NOW - i * 3600 for i in range(20)])        # aday, 20/gün
        if w == W[2]: return sigs([NOW - i * 7200 for i in range(5)])         # aday, 5/gün
        return []                                                             # pasif

class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        with open("in.txt", "w") as f: f.write("\n".join(W + [W[1], "gecersiz!adres"]) + "\n")
        ct.INPUT = os.path.join(self.d, "in.txt")
    def tearDown(self): os.chdir(self.cwd)
    def test_scan_resume_and_candidates(self):
        c1 = FakeClient(fail=[W[3]])
        with contextlib.redirect_stdout(io.StringIO()): counts = ct.main(client=c1, now_fn=lambda: NOW, sleep=lambda s: None)
        self.assertEqual(len(c1.calls), 5)                                    # yinelenen/geçersiz atlandı
        self.assertEqual((counts["bot"], counts["aday"], counts["hata"]), (1, 2, 1))
        aday = [l.strip() for l in open("wallets_aday.txt") if not l.startswith("#")]
        self.assertEqual(aday, [W[1], W[2]])                                  # ölçülü ve aktif önce, bot yok
        c2 = FakeClient()
        with contextlib.redirect_stdout(io.StringIO()): counts = ct.main(client=c2, now_fn=lambda: NOW, sleep=lambda s: None)
        self.assertEqual(c2.calls, [W[3]])                                    # yalnızca hatalı yeniden denendi
        self.assertNotIn("hata", counts); self.assertEqual(counts["pasif"], 2)
    def test_kara_liste_excluded_and_moderate_first(self):
        with open("kara_liste.txt", "w") as f: f.write("# bot\n" + W[2] + "\n")
        class C:
            def call(self, m, p):
                w = p[0]
                if w == W[0]: return sigs([NOW - i * 120 for i in range(100)])     # >=100/gün: aday ama ölçülü değil
                if w == W[1]: return sigs([NOW - i * 3600 for i in range(8)])      # ölçülü
                if w == W[2]: return sigs([NOW - i * 3600 for i in range(20)])     # kara listede
                return []
        with contextlib.redirect_stdout(io.StringIO()): ct.main(client=C(), now_fn=lambda: NOW, sleep=lambda s: None)
        aday = [l.strip() for l in open("wallets_aday.txt") if not l.startswith("#")]
        self.assertEqual(aday, [W[1], W[0]])                                  # ölçülü önce, kara liste yok
if __name__ == "__main__": unittest.main()
