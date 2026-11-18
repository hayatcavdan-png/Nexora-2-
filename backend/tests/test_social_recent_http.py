"""HTTP permission and default-off gates for on-demand mint discovery."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHILD = r'''
import json
import os
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

os.environ["NEXORA_DB"] = "offline-only-paper.sqlite"
os.environ["UYELIK_DB"] = "offline-only-member.sqlite"
os.environ["NEXORA_API_KEY"] = "fake-test-founder"
os.environ.pop("SOCIAL_RESEARCH_LIVE_ENABLED", None)
os.environ.pop("JUPITER_API_KEY", None)
os.environ.pop("HELIUS_API_KEY", None)
import server
member = server.uyelik.kayit("sample@invalid.invalid", "test-local-password")

def send(base, headers, body):
    request = Request(base + "/admin/token-discovery",
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST")
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as err:
        response = err
    with response:
        return [response.status, json.load(response), response.headers.get("Cache-Control")]

with ThreadingHTTPServer(("127.0.0.1", 0), server.H) as httpd:
    url = f"http://127.0.0.1:{httpd.server_port}"
    t = Thread(target=httpd.serve_forever)
    t.start()
    try:
        with patch("requests.sessions.Session.request", side_effect=AssertionError("external network forbidden")):
            data = {
                "anonymous": send(url, {}, {"mode": "recent"}),
                "member": send(url, {"X-Oturum": member}, {"mode": "recent"}),
                "founder": send(url, {"X-API-Key": "fake-test-founder"}, {"mode": "recent"}),
                "manual": send(url, {"X-API-Key": "fake-test-founder"},
                               {"mode": "manual", "mint": "So11111111111111111111111111111111111111112"}),
                "invalid": send(url, {"X-API-Key": "fake-test-founder"}, {"mode": "recent", "limit": 1000}),
            }
    finally:
        httpd.shutdown()
        t.join()
print(json.dumps(data))
'''


class SocialRecentHttpTests(unittest.TestCase):
    def test_http_roles_and_default_off(self):
        env = {
            "PATH": os.defpath,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOCIAL_RESEARCH_LIVE_ENABLED": "0",
        }
        with tempfile.TemporaryDirectory() as directory:
            r = subprocess.run(
                [sys.executable, "-B", "-c", CHILD],
                cwd=directory, env=env, capture_output=True,
                text=True, timeout=50, check=False
            )
        self.assertEqual(r.returncode, 0, r.stderr[-1600:])
        cases = json.loads(r.stdout.strip())
        self.assertEqual(cases["anonymous"][0], 401)
        self.assertEqual(cases["member"][0], 403)
        self.assertEqual(cases["founder"][0], 200)
        self.assertEqual(cases["manual"][0], 200)
        self.assertEqual(cases["founder"][1]["status"], "DISABLED")
        self.assertEqual(cases["manual"][1]["status"], "DISABLED")
        self.assertEqual(cases["founder"][1]["results"], [])
        self.assertFalse(cases["founder"][1]["real_order"])
        self.assertEqual(cases["invalid"][0], 400)
        for row in cases.values():
            self.assertEqual(row[2], "no-store")


if __name__ == "__main__":
    unittest.main()
