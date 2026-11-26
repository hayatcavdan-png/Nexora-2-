import base64, hashlib, json, os, socket, struct, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nexora.ws_client import WSClient, WSClosed, GUID
from nexora.ws_listener import WSListener
from nexora.core import Paper
from nexora.live_tracker import LiveTracker
from test_tracker import swap_tx

def frame(op, payload, fin=True):
    n = len(payload); h = bytes([(0x80 if fin else 0) | op])
    if n < 126: h += bytes([n])
    elif n < 65536: h += bytes([126]) + struct.pack(">H", n)
    else: h += bytes([127]) + struct.pack(">Q", n)
    return h + payload

def read_client_frame(sock):
    def ex(n):
        b = b""
        while len(b) < n:
            c = sock.recv(n - len(b))
            if not c: raise EOFError
            b += c
        return b
    b1, b2 = ex(2); n = b2 & 0x7F
    if n == 126: n = struct.unpack(">H", ex(2))[0]
    elif n == 127: n = struct.unpack(">Q", ex(8))[0]
    assert b2 & 0x80, "istemci çerçeveleri maskeli olmalı"
    m = ex(4); d = ex(n)
    return b1 & 0x0F, bytes(x ^ m[i % 4] for i, x in enumerate(d))

class FrameTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = socket.socketpair(); self.c = WSClient(self.a)
    def tearDown(self): self.a.close(); self.b.close()
    def test_text_and_large(self):
        self.b.sendall(frame(1, b"merhaba")); self.assertEqual(self.c.recv(), "merhaba")
        big = b"x" * 70000; self.b.sendall(frame(1, big)); self.assertEqual(len(self.c.recv()), 70000)
    def test_fragmented(self):
        self.b.sendall(frame(1, b"par", fin=False) + frame(0, b"ca"))
        self.assertEqual(self.c.recv(), "parca")
    def test_ping_gets_pong(self):
        self.b.sendall(frame(9, b"p1") + frame(1, b"ok"))
        self.assertEqual(self.c.recv(), "ok")
        self.assertEqual(read_client_frame(self.b), (0xA, b"p1"))
    def test_close_raises(self):
        self.b.sendall(frame(8, struct.pack(">H", 1000)))
        with self.assertRaises(WSClosed): self.c.recv()
    def test_eof_raises(self):
        self.b.close()
        with self.assertRaises(WSClosed): self.c.recv()
    def test_client_frames_masked(self):
        self.c.send_text('{"a":1}'); self.assertEqual(read_client_frame(self.b), (1, b'{"a":1}'))

class FakeSolanaWS:
    """Yerel WebSocket sunucusu: logsSubscribe yanıtlar, bildirim gönderir."""
    def __init__(self, notifications, reject=()):
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(2)
        self.port = self.srv.getsockname()[1]; self.notifications = notifications; self.reject = set(reject)
        self.subs = []; self.accept_key_ok = True
        threading.Thread(target=self.serve, daemon=True).start()
    def serve(self):
        conn, _ = self.srv.accept()
        req = b""
        while b"\r\n\r\n" not in req: req += conn.recv(4096)
        key = [l.split(b":", 1)[1].strip() for l in req.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
        acc = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest()) if self.accept_key_ok else b"bad"
        conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     b"Sec-WebSocket-Accept: " + acc + b"\r\n\r\n")
        try:
            wallets = {}
            for _ in range(self.expected):
                op, data = read_client_frame(conn); m = json.loads(data)
                w = m["params"][0]["mentions"][0]; self.subs.append(w)
                if w in self.reject:
                    conn.sendall(frame(1, json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -1}}).encode()))
                else:
                    sid = 100 + m["id"]; wallets[w] = sid
                    conn.sendall(frame(1, json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": sid}).encode()))
            conn.sendall(frame(1, b"bozuk json{"))
            for w, sig, err in self.notifications:
                conn.sendall(frame(1, json.dumps({"jsonrpc": "2.0", "method": "logsNotification", "params": {
                    "subscription": wallets.get(w, 999), "result": {"value": {"signature": sig, "err": err, "logs": []}}}}).encode()))
            conn.sendall(frame(8, struct.pack(">H", 1000)))
        except (EOFError, OSError):
            pass
        finally:
            conn.close()

class ListenerTests(unittest.TestCase):
    def run_listener(self, server, wallets, cb):
        server.expected = len(wallets)
        logs = []
        lst = WSListener(f"ws://127.0.0.1:{server.port}/?api-key=GIZLI", wallets, cb, log=logs.append, ping_every=5)
        with self.assertRaises(WSClosed): lst.run_once()
        return logs
    def test_notifications_routed_to_right_wallet(self):
        got = []
        srv = FakeSolanaWS([("W1", "s1", None), ("W2", "s2", None), ("W1", "fail", {"x": 1}), ("ZZ", "s3", None)])
        self.run_listener(srv, ["W1", "W2"], lambda w, s: got.append((w, s)))
        self.assertEqual(got, [("W1", "s1"), ("W2", "s2")])     # hatalı işlem ve bilinmeyen abonelik atlandı
    def test_rejected_subscription_logged_without_key(self):
        srv = FakeSolanaWS([("W2", "s2", None)], reject=["W1"])
        got = []; logs = self.run_listener(srv, ["W1", "W2"], lambda w, s: got.append(s))
        self.assertEqual(got, ["s2"]); self.assertTrue(any("reddedildi" in l for l in logs))
        self.assertFalse(any("GIZLI" in l for l in logs))
    def test_callback_error_does_not_stop_listener(self):
        got = []
        def cb(w, s):
            if s == "s1": raise RuntimeError("patladı")
            got.append(s)
        srv = FakeSolanaWS([("W1", "s1", None), ("W1", "s2", None)])
        logs = self.run_listener(srv, ["W1"], cb)
        self.assertEqual(got, ["s2"]); self.assertTrue(any("İşlem hatası" in l for l in logs))
    def test_bad_accept_key_rejected(self):
        srv = FakeSolanaWS([]); srv.accept_key_ok = False; srv.expected = 0
        with self.assertRaises(WSClosed): WSClient.connect(f"ws://127.0.0.1:{srv.port}/")

class FlakyClient:
    def __init__(self, tx, none_times=0): self.tx, self.none_times, self.calls = tx, none_times, 0
    def call(self, method, params):
        if method == "getTransaction":
            self.calls += 1
            return None if self.calls <= self.none_times else self.tx
        return [{"signature": "s1", "err": None}]

class TrackerWsTests(unittest.TestCase):
    def tracker(self, client, db=":memory:"):
        return LiveTracker(client, Paper(), db, ["A"], clock=lambda: 1003, sleep=lambda s: None)
    def test_ws_signal_recorded_with_source_and_latency(self):
        tr = self.tracker(FlakyClient(swap_tx("s1", "A")))
        r = tr.handle_signature("A", "s1")
        self.assertEqual((r["side"], r["source"], r["latency_s"]), ("BUY", "ws", 3))
        self.assertEqual(tr.latency_stats()["ws"]["n"], 1)
    def test_retry_until_transaction_available(self):
        c = FlakyClient(swap_tx("s1", "A"), none_times=2)
        self.assertIsNotNone(self.tracker(c).handle_signature("A", "s1", retries=4)); self.assertEqual(c.calls, 3)
    def test_unavailable_tx_not_marked_seen(self):
        c = FlakyClient(swap_tx("s1", "A"), none_times=10); tr = self.tracker(c)
        self.assertIsNone(tr.handle_signature("A", "s1", retries=2))
        c.none_times = 0
        self.assertIsNotNone(tr.handle_signature("A", "s1"))          # sonra tamamlanabilir
    def test_ws_then_poll_no_duplicate(self):
        tr = self.tracker(FlakyClient(swap_tx("s1", "A")))
        tr.db.execute("UPDATE tracker_wallets SET last_sig='old'"); tr.db.commit()
        self.assertIsNotNone(tr.handle_signature("A", "s1"))
        self.assertEqual(tr.poll_wallet("A"), [])                       # yoklama tekrar işlemez
        self.assertEqual(len(tr.signals()), 1)
    def test_migrates_old_schema(self):
        import sqlite3
        db = os.path.join(tempfile.mkdtemp(), "old.db"); c = sqlite3.connect(db)
        c.execute("""CREATE TABLE tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, wallet TEXT, sig TEXT,
            side TEXT, token TEXT, token_delta TEXT, quote TEXT, block_time INTEGER, latency_s REAL, decision TEXT, reason TEXT)""")
        c.execute("INSERT INTO tracker_signals(ts,latency_s) VALUES(1, 13)"); c.commit(); c.close()
        tr = self.tracker(FlakyClient(None), db)
        self.assertEqual(tr.latency_stats()["poll"]["n"], 1)            # eski kayıtlar 'poll' sayıldı
if __name__ == "__main__": unittest.main()

class RpcErr(Exception):
    def __init__(self, code): super().__init__(f"RPC hatası: {code}"); self.rpc_code = code

class V1Client:
    """-32015 gibi işleme özgü RPC hatası ya da bağlantı hatası üretir; istenen sürümü kaydeder."""
    def __init__(self, mode): self.mode, self.versions = mode, []
    def call(self, method, params):
        if method == "getSignaturesForAddress":
            return [{"signature": "bad", "err": None}, {"signature": "good", "err": None}]
        self.versions.append(params[1]["maxSupportedTransactionVersion"])
        if params[0] == "bad":
            if self.mode == "rpc": raise RpcErr(-32015)
            raise ConnectionError("ağ yok")
        return swap_tx("good", "A")

class TxVersionTests(unittest.TestCase):
    def make(self, mode):
        c = V1Client(mode)
        tr = LiveTracker(c, Paper(), ":memory:", ["A"], clock=lambda: 1003, sleep=lambda s: None)
        tr.db.execute("UPDATE tracker_wallets SET last_sig='old'"); tr.db.commit()
        return c, tr
    def test_requests_transaction_v1(self):
        c, tr = self.make("rpc"); tr.poll_all()
        self.assertTrue(c.versions and all(v == 1 for v in c.versions))
    def test_rpc_error_on_one_tx_does_not_fail_wallet(self):
        c, tr = self.make("rpc")
        rep = tr.poll_all()
        self.assertEqual(rep["A"], 1)                                   # 'good' yine işlendi
        self.assertEqual(tr.failed_count(), 1)
        st = tr.status()[0]; self.assertEqual((st["errors"], st["quarantined"]), (0, 0))
    def test_connection_error_counts_against_wallet(self):
        c, tr = self.make("net")
        self.assertEqual(tr.poll_all()["A"], "hata"); self.assertEqual(tr.failed_count(), 0)
        self.assertEqual(tr.status()[0]["errors"], 1)
    def test_reset_quarantine(self):
        c, tr = self.make("net")
        for _ in range(5): tr.poll_all()
        self.assertEqual(tr.status()[0]["quarantined"], 1)
        self.assertEqual(tr.reset_quarantine(), 1); self.assertEqual(tr.active_wallets(), ["A"])

class HeliusRpcCodeTests(unittest.TestCase):
    def test_client_exposes_rpc_code(self):
        from unittest.mock import Mock, patch
        from nexora.helius_client import HeliusClient, HeliusRPCError
        c = HeliusClient(rpc_url="https://mainnet.helius-rpc.com/?api-key=test", max_retries=0)
        resp = Mock(status_code=200, headers={}); resp.raise_for_status = Mock()
        resp.json = Mock(return_value={"jsonrpc": "2.0", "id": 1, "error": {"code": -32015, "message": "x"}})
        with patch("nexora.helius_client.requests.Session.post", return_value=resp):
            with self.assertRaises(HeliusRPCError) as ctx: c.call("getTransaction", ["s", {}])
        self.assertEqual(ctx.exception.rpc_code, -32015); c.close()

from nexora.swap_decoder import decode_swap
from nexora.constants import USDC_MINT
from nexora.live_tracker import RATE_MAX

def sol_to_token_tx(sig, W, mint):
    """Cüzdan SOL harcayıp `mint` alır (FHpc örneğindeki SOL->USDC gibi)."""
    JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    bal = lambda a: dict(accountIndex=1, mint=mint, owner=W, uiTokenAmount=dict(amount=str(a), decimals=6))
    return dict(slot=1, blockTime=1000, transaction=dict(signatures=[sig], message=dict(accountKeys=[W, "x"], instructions=[dict(programId=JUP)])),
        meta=dict(err=None, fee=5000, logMessages=[f"Program {JUP} invoke [1]"], preBalances=[10**9, 0], postBalances=[5 * 10**8, 0],
                  preTokenBalances=[bal(1)], postTokenBalances=[bal(10**6)]))

class StableSwapTests(unittest.TestCase):
    def test_sol_to_usdc_not_a_token_buy(self):
        r = decode_swap(sol_to_token_tx("s", "W", USDC_MINT), "W")
        self.assertEqual(r["event_type"], "UNKNOWN"); self.assertIn("quote_asset_swap_not_copyable", r["evidence"])
    def test_sol_to_meme_token_still_buy(self):
        self.assertEqual(decode_swap(sol_to_token_tx("s", "W", "MEMEmint111"), "W")["event_type"], "BUY")

class CountingClient:
    def __init__(self): self.tx_calls = 0
    def call(self, method, params):
        if method == "getTransaction":
            self.tx_calls += 1; return swap_tx(params[0], "A")
        return []

class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]; self.c = CountingClient()
        self.tr = LiveTracker(self.c, Paper(), ":memory:", ["A", "B"], clock=lambda: self.now[0], sleep=lambda s: None)
    def test_high_frequency_wallet_flagged_and_stops_api_calls(self):
        for i in range(RATE_MAX + 10): self.tr.handle_signature("A", f"s{i}")
        self.assertEqual(self.c.tx_calls, RATE_MAX)                     # sınırdan sonra API çağrısı yok
        self.assertEqual(self.tr.bot_wallets(), ["A"]); self.assertEqual(self.tr.flagged, ["A"])
        self.assertNotIn("A", self.tr.active_wallets()); self.assertIn("B", self.tr.active_wallets())
        before = self.c.tx_calls; self.tr.handle_signature("B", "b1")
        self.assertEqual(self.c.tx_calls, before + 1)                  # diğer cüzdan etkilenmez
    def test_slow_wallet_never_flagged(self):
        for i in range(RATE_MAX * 2):
            self.now[0] += 60; self.tr.handle_signature("A", f"s{i}")   # dakikada 1 işlem
        self.assertEqual(self.tr.bot_wallets(), [])
    def test_bot_flag_survives_restart_reset_but_can_be_cleared(self):
        for i in range(RATE_MAX + 1): self.tr.handle_signature("A", f"s{i}")
        self.tr.reset_quarantine(); self.assertEqual(self.tr.bot_wallets(), ["A"])
        self.tr.clear_bot_flag("A"); self.assertIn("A", self.tr.active_wallets())
    def test_wallet_removed_from_list_not_tracked(self):
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        LiveTracker(self.c, Paper(), db, ["A", "B"])
        tr2 = LiveTracker(self.c, Paper(), db, ["B"])                    # A wallets.txt'ten çıkarıldı
        self.assertEqual(tr2.active_wallets(), ["B"])


class KotaGeriCekilmeTest(unittest.TestCase):
    def _bekleyisler(self, hata, n=6):
        from nexora.ws_listener import WSListener
        from nexora.ws_client import WSClosed
        bekle = []
        class Dur:
            def __init__(s): s.k = 0
            def is_set(s): return s.k >= n
            def wait(s, d): bekle.append(d); s.k += 1
        def baglan(url, timeout=None): raise WSClosed(hata)
        WSListener("wss://x", ["W"], lambda w, s: None, connect=baglan, log=lambda m: None).run_forever(Dur())
        return bekle

    def test_429_bekleme_15_dakikaya_kadar_uzar(self):
        b = self._bekleyisler("WebSocket reddedildi: HTTP 429", n=6)
        self.assertEqual(b, [60, 120, 240, 480, 900, 900])

    def test_normal_kopma_60_sn_ile_sinirli(self):
        b = self._bekleyisler("bağlantı kapandı", n=8)
        self.assertEqual(b, [1, 2, 4, 8, 16, 32, 60, 60])
