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
