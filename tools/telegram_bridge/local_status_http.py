"""Local-only, metadata-only HTTP endpoint compatible with Android PR #13.

This server MUST NOT be launched while Termux T12 already occupies port 18991.
It never reads Telegram session files, secrets or actual message contents.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from nexora.social_ai.telegram_bridge import read_t10  # noqa: E402


SOURCE = Path.home() / ".nexora_telegram_bridge" / "t9_nexora_bridge.json"
SESSIONS = ("nexora_tg_bridge", "nexora_tg_status", "nexora_tg_t10")


def worker_running(name):
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-t", name,
             "-F", "#{pane_current_command}|#{pane_dead}"],
            text=True, capture_output=True, timeout=2, check=False)
        return result.returncode == 0 and "python|0" in result.stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        return False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/status":
            self.send_error(404)
            return
        try:
            status = {name: worker_running(name) for name in SESSIONS}
            data = read_t10(SOURCE, worker_status=status)
            code = 200
        except (ValueError, OSError, TypeError):
            data = {"status": "UNAVAILABLE"}
            code = 503
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18991), Handler).serve_forever()
