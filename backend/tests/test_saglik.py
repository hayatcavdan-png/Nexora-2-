import json, os, sqlite3, sys, tempfile, time, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from nexora import saglik as S, panel
from nexora.core import Paper


def systemd(durumlar):
    def calistir(komut):
        if komut[:2] != ["systemctl", "show"]: return ""
        return "\n\n".join(f"Id={u}\nActiveState={durumlar.get(u, 'active')}\nNRestarts=0\nActiveEnterTimestamp=x" for u in S.BIRIMLER + S.ZAMANLAYICI)
    return calistir


class SaglikTests(unittest.TestCase):
    def test_servisler_ve_bilinmiyor(self):
        s = {x["birim"]: x for x in S.servisler(systemd({"nexora-hl": "failed"}))}
        self.assertEqual(s["nexora-hl"]["durum"], "failed"); self.assertEqual(s["nexora-takip"]["durum"], "active")
        self.assertTrue(all(x["durum"] == "bilinmiyor" for x in S.servisler(lambda k: "")))

    def test_kesinti_bildirimi(self):
        yol = os.path.join(tempfile.mkdtemp(), "s.json")
        self.assertEqual(S.olaylar(0, 1000, systemd({}), yol), [])                       # ilk kayıt: olay yok
        self.assertEqual(S.olaylar(0, 1010, systemd({"nexora-hl": "failed"}), yol), [])  # 90 sn dolmadı
        e = S.olaylar(0, 1110, systemd({"nexora-hl": "failed"}), yol)
        self.assertEqual(len(e), 1); self.assertIn("Hyperliquid", e[0]["baslik"]); self.assertEqual(e[0]["ts"], 1100)
        self.assertEqual(S.olaylar(1100, 1200, systemd({"nexora-hl": "failed"}), yol), [])   # bir kez
        e = S.olaylar(1100, 1300, systemd({}), yol)
        self.assertEqual(len(e), 1); self.assertIn("yeniden", e[0]["baslik"])
        # kısa yeniden başlatma alarm üretmez
        S.olaylar(1300, 1400, systemd({"nexora-takip": "activating"}), yol)
        self.assertEqual(S.olaylar(1300, 1420, systemd({}), yol), [])
        self.assertEqual(S.olaylar(0, 1, lambda k: "", os.path.join(tempfile.mkdtemp(), "y.json")), [])

    def test_durum_paper(self):
        p = Paper(); d = S.durum(p, systemd({"nexora-bnb": "inactive"}), now=10)
        self.assertEqual(d["sorun"], 1); self.assertFalse(d["paper"]["limit_doldu"]); self.assertIn("kurulan", d["surum"])

    def test_tutarlilik(self):
        d = tempfile.mkdtemp(); pyol = os.path.join(d, "p.db"); p = Paper(pyol)
        now = time.time(); bas = now - 3600
        p.record_buy("W:1", "W", "T1", 5.0, 1000, 6); p.record_sell("W:2", "W", "T1", 6.0)
        r = S.tutarlilik(pyol, os.path.join(d, "yok.db"), bas=bas, now=now, golge=set())
        self.assertEqual((r["canli"]["alim"], r["canli"]["satis"], r["canli"]["kazanan"]), (1, 1, 1))
        self.assertGreater(r["canli"]["toplam_pct"], 0); self.assertEqual(r["deney"]["islem"], 0)
        self.assertIn("erken", r["yorum"])


class GeceOlayTests(unittest.TestCase):
    def test_yz_ve_terfi(self):
        yol = os.path.join(tempfile.mkdtemp(), "k.json")
        json.dump(dict(ts=500, yz_degisti=dict(onceki="Karar: AVANTAJ VAR", yeni="Karar: AVANTAJ BULUNAMADI"), terfi_yeni=["A" * 44]), open(yol, "w"))
        e = panel.gece_olaylari(yol, 0)
        self.assertEqual([x["id"][0] for x in e], ["y", "p"]); self.assertEqual(panel.gece_olaylari(yol, 600), [])


if __name__ == "__main__": unittest.main()


class EslesmeTests(unittest.TestCase):
    def test_ayni_sinyal_iki_sonuc(self):
        from nexora import etiket as E
        d = tempfile.mkdtemp(); pyol, eyol = os.path.join(d, "p.db"), os.path.join(d, "e.db")
        p = Paper(pyol); E.Etiketci(eyol, None).db.close()
        p.record_buy("W:1", "W", "T1", 5.0, 1000, 6); p.record_sell("W:2", "W", "T1", 6.0)     # canlı ~ +%20
        p.record_buy("W:3", "W", "T2", 5.0, 1000, 6); p.record_sell("W:4", "W", "T2", 4.0)     # etiketsiz
        c = sqlite3.connect(eyol); c.execute("INSERT INTO etiket_sonuc(event_id, ufuk, ts, getiri_pct) VALUES('W:1','kaynak',1,15.0)")
        c.commit(); c.close()
        r = S.eslesme(pyol, eyol, 0)
        self.assertEqual((r["n"], r["etiketsiz"], r["alim"], r["eksiksizlik"]), (1, 1, 2, 0)); self.assertAlmostEqual(r["olculen_ort"], 15.0)
        self.assertGreater(r["fark_ort"], 3); self.assertLess(r["fark_ort"], 6)
        self.assertEqual(S.eslesme("/yok", eyol, 0)["n"], 0)
