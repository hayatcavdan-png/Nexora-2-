import io, os, sqlite3, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest.mock import Mock
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
import pilot_olcum
sys.path.insert(0, HERE)
from test_emir import tx, TAKER, Resp


class Helius:
    def __init__(self, sol=0.05, usdc=3.0, sim_ok=True):
        self.sol, self.usdc, self.sim_ok, self.cagri = sol, usdc, sim_ok, []
    def call(self, m, p):
        self.cagri.append(m)
        assert m != "sendTransaction"
        if m == "getBalance": return {"value": int(self.sol * 1e9)}
        if m == "getTokenAccountsByOwner":
            return {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": self.usdc}}}}}}]}
        if m == "simulateTransaction": return {"value": {"err": None if self.sim_ok else {"InstructionError": [2, "x"]}, "unitsConsumed": 90000, "logs": []}}
        raise AssertionError(m)


def _ortam(tokenler):
    d = tempfile.mkdtemp(); tr = os.path.join(d, "t.db"); c = sqlite3.connect(tr)
    c.execute("CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY, side TEXT, token TEXT)")
    for t in tokenler: c.execute("INSERT INTO tracker_signals(side, token) VALUES('buy', ?)", (t,))
    c.commit(); c.close()
    return d, tr


class Test(unittest.TestCase):
    def test_bakiye(self):
        _ortam([])
        with redirect_stdout(io.StringIO()):
            b = pilot_olcum.main(["bakiye"], adres=TAKER, helius=Helius(0.02, 2.5))
        self.assertEqual((b["sol"], b["usdc"]), (0.02, 2.5))

    def test_bakiye_yetersizse_hic_denemez(self):
        d, tr = _ortam(["A" * 44])
        s = Mock()
        with redirect_stdout(io.StringIO()):
            r = pilot_olcum.main(["olc"], adres=TAKER, helius=Helius(0.001, 0), session=s, db_yolu=os.path.join(d, "p.db"), tracker=tr)
        self.assertFalse(r["hazir"]); s.get.assert_not_called()

    def test_olcum_ve_ozet(self):
        d, tr = _ortam(["T1" * 22, "T2" * 22, "T1" * 22])                  # tekrar eden token bir kez ölçülür
        s = Mock(); s.get.return_value = Resp({"transaction": tx(), "router": "iris", "outAmount": "5"})
        h = Helius(sim_ok=True)
        with redirect_stdout(io.StringIO()):
            r = pilot_olcum.main(["olc"], adres=TAKER, helius=h, session=s, db_yolu=os.path.join(d, "p.db"), tracker=tr, uyku=lambda x: None)
        self.assertEqual(len(r["sonuc"]), 2); self.assertEqual(r["ozet"]["basarili"], 2)
        self.assertNotIn("sendTransaction", h.cagri)
        h.sim_ok = False; s.get.return_value = Resp({"errorCode": 1})
        with redirect_stdout(io.StringIO()):
            r = pilot_olcum.main(["olc"], adres=TAKER, helius=h, session=s, db_yolu=os.path.join(d, "p.db"), tracker=tr, uyku=lambda x: None)
        self.assertEqual(r["ozet"]["n"], 4); self.assertEqual(r["ozet"]["oran_pct"], 50.0)
        self.assertEqual(r["sonuc"][0]["hata"], "giriş token bakiyesi yetersiz")


if __name__ == "__main__":
    unittest.main()
