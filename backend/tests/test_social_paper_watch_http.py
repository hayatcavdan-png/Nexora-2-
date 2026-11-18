"""Founder access / fail-closed defaults of isolated 100 USDT watch HTTP."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = r'''
import json, os
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

os.environ["NEXORA_DB"] = "paper-test-only.sqlite"
os.environ["UYELIK_DB"] = "membership-test-only.sqlite"
os.environ["NEXORA_API_KEY"] = "synthetic-founder"
os.environ.pop("SOCIAL_PAPER_WATCH_ENABLED", None)
os.environ.pop("SOCIAL_RESEARCH_LIVE_ENABLED", None)
os.environ.pop("JUPITER_API_KEY", None)
import server
member = server.uyelik.kayit("temp@example.invalid", "offline-test-password")

def req(base, headers, endpoint, body=None):
    data = json.dumps(body).encode() if body is not None else None
    q = Request(base + endpoint, headers=headers, data=data,
                method="POST" if data is not None else "GET")
    try:
        response = urlopen(q, timeout=5)
    except HTTPError as err:
        response = err
    with response:
        return [response.code, json.load(response), response.headers.get("Cache-Control")]

with ThreadingHTTPServer(("127.0.0.1", 0), server.H) as httpd:
    t = Thread(target=httpd.serve_forever)
    t.start()
    url = f"http://127.0.0.1:{httpd.server_port}"
    founder = {"X-API-Key": "synthetic-founder"}
    try:
        with patch("requests.sessions.Session.request", side_effect=AssertionError("external network forbidden")):
            res = {
                "anonymous": req(url, {}, "/admin/social-paper-watch"),
                "member": req(url, {"X-Oturum": member}, "/admin/social-paper-watch"),
                "founder": req(url, founder, "/admin/social-paper-watch"),
                "refresh": req(url, founder, "/admin/social-paper-watch-refresh", {}),
                "manual_paper": req(url, founder, "/admin/token-discovery",
                                    {"mode": "manual", "mint": "So11111111111111111111111111111111111111112",
                                     "paper": True})
            }
    finally:
        httpd.shutdown()
        t.join()
print(json.dumps(res))
'''


class PaperWatchHttpTests(unittest.TestCase):
    def test_no_network_default_and_authorization(self):
        env = {
            "PATH": os.defpath,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        with tempfile.TemporaryDirectory() as directory:
            r = subprocess.run([sys.executable, "-B", "-c", SCRIPT],
                               cwd=directory, env=env, capture_output=True,
                               text=True, timeout=45, check=False)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        d = json.loads(r.stdout.strip())
        self.assertEqual(d["anonymous"][0], 401)
        self.assertEqual(d["member"][0], 403)
        self.assertEqual(d["founder"][0], 200)
        self.assertEqual(d["founder"][1]["snapshot_status"], "DISABLED")
        self.assertEqual(d["founder"][1]["entries"], [])
        self.assertEqual(d["refresh"][1]["snapshot_status"], "DISABLED")
        self.assertEqual(d["manual_paper"][1]["paper_watch"]["status"], "DISABLED")
        for value in d.values():
            self.assertEqual(value[2], "no-store")


if __name__ == "__main__":
    unittest.main()
