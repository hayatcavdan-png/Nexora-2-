"""Yalnızca standart kütüphaneyle minimal WebSocket istemcisi (RFC 6455).
Termux'ta paket derleme gerektirmez. Hata mesajlarına URL (API anahtarı) yazılmaz."""
import base64, hashlib, os, socket, ssl, struct
from urllib.parse import urlparse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 16 * 1024 * 1024

class WSClosed(Exception):
    pass

class WSClient:
    def __init__(self, sock):
        self.sock = sock

    @classmethod
    def connect(cls, url, timeout=30):
        u = urlparse(url)
        if u.scheme not in ("ws", "wss") or not u.hostname:
            raise ValueError("Geçersiz WebSocket adresi")
        port = u.port or (443 if u.scheme == "wss" else 80)
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        raw = socket.create_connection((u.hostname, port), timeout=timeout)
        sock = (ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname)
                if u.scheme == "wss" else raw)
        key = base64.b64encode(os.urandom(16)).decode()
        host = u.hostname if not u.port else f"{u.hostname}:{u.port}"
        sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                      "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk or len(buf) > 65536:
                sock.close(); raise WSClosed("El sıkışma yanıtı alınamadı")
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        status = lines[0].split(" ")
        if len(status) < 2 or status[1] != "101":
            sock.close(); raise WSClosed(f"WebSocket reddedildi: HTTP {status[1] if len(status) > 1 else '?'}")
        hdr = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
        expect = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if hdr.get("sec-websocket-accept") != expect:
            sock.close(); raise WSClosed("WebSocket kabul anahtarı hatalı")
        c = cls(sock); c._pending = rest
        return c

    _pending = b""

    def _recv_exact(self, n):
        out = self._pending[:n]; self._pending = self._pending[n:]
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk: raise WSClosed("Bağlantı kapandı")
            out += chunk
        return out

    def _send_frame(self, op, payload=b""):
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | op])
        if n < 126: head += bytes([0x80 | n])
        elif n < 65536: head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else: head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send_text(self, text): self._send_frame(0x1, text.encode())
    def ping(self): self._send_frame(0x9, b"nx")

    def recv(self):
        """Bir metin mesajı döndürür. Ping'e otomatik pong verir. Kapanışta WSClosed."""
        parts, total = [], 0
        while True:
            b1, b2 = self._recv_exact(2)
            fin, op, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126: n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127: n = struct.unpack(">Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if b2 & 0x80 else None
            if n > MAX_MESSAGE: raise WSClosed("Mesaj çok büyük")
            data = self._recv_exact(n)
            if mask: data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                try: self._send_frame(0x8, data[:2])
                except OSError: pass
                raise WSClosed("Sunucu bağlantıyı kapattı")
            if op == 0x9: self._send_frame(0xA, data); continue
            if op == 0xA: continue
            if op in (0x0, 0x1, 0x2):
                parts.append(data); total += n
                if total > MAX_MESSAGE: raise WSClosed("Mesaj çok büyük")
                if fin: return b"".join(parts).decode("utf-8", "replace")
                continue
            raise WSClosed("Bilinmeyen çerçeve türü")

    def close(self):
        try: self._send_frame(0x8, struct.pack(">H", 1000))
        except OSError: pass
        try: self.sock.close()
        except OSError: pass
