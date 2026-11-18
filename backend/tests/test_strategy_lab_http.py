"""Strategy Lab status is founder-only and never touches live providers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHILD = r'''
import json, os
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

os.environ["NEXORA_DB"] = "paper-test-only.sqlite"
os.environ["UYELIK_DB"] = "membership-test-only.sqlite"
os.environ["NEXORA_API_KEY"] = "test-founder-local"
os.environ.pop("STRATEGY_LAB_SNAPSHOT", None)
import server
member = server.uyelik.kayit("lab@example.invalid", "local-only-password")

def req(base, headers):
    q = Request(base + "/admin/strategy-lab", headers=headers)
    try:
        response = urlopen(q, timeout=5)
    except HTTPError as err:
        response = err
    with response:
        return [response.code, json.load(response), response.headers.get("Cache-Control")]

with ThreadingHTTPServer(("127.0.0.1", 0), server.H) as srv:
    t = Thread(target=srv.serve_forever)
    t.start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        with patch("requests.sessions.Session.request", side_effect=AssertionError("no external network")):
            cases = {
                "anonymous": req(base, {}),
                "member": req(base, {"X-Oturum": member}),
                "founder": req(base, {"X-API-Key": "test-founder-local"}),
            }
    finally:
        srv.shutdown(); t.join()
print(json.dumps(cases))
'''


class StrategyLabHttpTests(unittest.TestCase):
    def test_authorization_no_external_network_and_empty_default(self):
        env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1]),
               "PYTHONDONTWRITEBYTECODE": "1", "PATH": os.defpath}
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-B", "-c", CHILD], cwd=folder,
                env=env, capture_output=True, text=True, timeout=50)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        data = json.loads(result.stdout.strip())
        self.assertEqual(data["anonymous"][0], 401)
        self.assertEqual(data["member"][0], 403)
        self.assertEqual(data["founder"][0], 200)
        self.assertEqual(data["founder"][1]["snapshot_status"], "NOT_CONFIGURED")
        self.assertFalse(data["founder"][1]["real_order"])
        self.assertEqual(data["founder"][1]["equity"], [])
        self.assertEqual(len(data["founder"][1]["capabilities"]), 7)
        self.assertEqual(data["founder"][1]["auto_paper"]["status"], "DISABLED")
        self.assertFalse(data["founder"][1]["auto_paper"]["real_order"])
        self.assertFalse(data["founder"][1]["auto_paper"]["worker_running_verified"])
        for row in data.values():
            self.assertEqual(row[2], "no-store")


if __name__ == "__main__":
    unittest.main()
