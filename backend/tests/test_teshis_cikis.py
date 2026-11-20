import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora.core import Paper


class CikisTetikleyenTests(unittest.TestCase):
    def test_baska_cuzdan_satisi_ayri_sayilir(self):
        d = tempfile.mkdtemp(); yol = os.path.join(d, "p.db"); p = Paper(yol)
        p.record_buy("A:1", "A", "T1", 5.0, 1000, 6); p.record_sell("B:2", "B", "T1", 4.0)    # eski davranış: başkası kapattı
        p.record_buy("A:3", "A", "T2", 5.0, 1000, 6); p.record_sell("A:4", "A", "T2", 6.0)
        eski = {k: os.environ.get(k) for k in ("NEXORA_DB", "TRACKER_DB", "ETIKET_DB")}
        os.environ.update(NEXORA_DB=yol, TRACKER_DB=os.path.join(d, "t.db"), ETIKET_DB=os.path.join(d, "e.db"))
        try:
            from nexora.teshis import rapor
            r = rapor(); metin = "\n".join(r) if isinstance(r, list) else str(r)
        finally:
            for k, v in eski.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
        self.assertIn("BAŞKA cüzdan 1 satış -1.01$", metin); self.assertIn("açan cüzdan 1 satış +0.99$", metin)


if __name__ == "__main__": unittest.main()
