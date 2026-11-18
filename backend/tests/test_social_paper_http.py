"""Independent loopback HTTP smoke for admin-only offline paper preview."""
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

os.environ["NEXORA_DB"] = "paper-test.sqlite"
os.environ["UYELIK_DB"] = "member-test.sqlite"
os.environ["NEXORA_API_KEY"] = "synthetic-founder-secret"
os.environ.pop("SOCIAL_PAPER_FIXTURE", None)

import server
token = server.uyelik.kayit("member@local.invalid", "local-only-pass")
def get(base, headers=None):
    req = Request(base + "/admin/social-paper", headers=headers or {})
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return [response.code, json.load(response), response.headers.get("Cache-Control")]

with ThreadingHTTPServer(("127.0.0.1", 0), server.H) as srv:
    base = "http://127.0.0.1:" + str(srv.server_port)
    t = Thread(target=srv.serve_forever)
    t.start()
    try:
        cases = {
            "anonymous": get(base),
            "member": get(base, {"X-Oturum": token}),
            "founder": get(base, {"X-API-Key": "synthetic-founder-secret"}),
        }
        open("bad-fixture.json", "w").write('{"broken": 1}')
        os.environ["SOCIAL_PAPER_FIXTURE"] = "bad-fixture.json"
        cases["bad_fixture"] = get(base, {"X-API-Key": "synthetic-founder-secret"})
    finally:
        srv.shutdown()
        t.join()
print(json.dumps(cases))
'''


class SocialPaperHttpTests(unittest.TestCase):
    def test_admin_only_no_live_calls(self):
        env = {
            "PATH": os.defpath,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOCIAL_LIVE_ENABLED": "0",
        }
        with tempfile.TemporaryDirectory() as folder:
            r = subprocess.run([sys.executable, "-B", "-c", CHILD],
                               cwd=folder, env=env, capture_output=True,
                               text=True, timeout=45, check=False)
        self.assertEqual(r.returncode, 0, r.stderr[-1200:])
        cases = json.loads(r.stdout.strip())
        self.assertEqual(cases["anonymous"][0], 401)
        self.assertEqual(cases["member"][0], 403)
        self.assertEqual(cases["founder"][0], 200)
        self.assertEqual(cases["founder"][1]["snapshot_status"], "NOT_CONFIGURED")
        self.assertEqual(cases["founder"][1]["remaining_cash_usdt"], "100")
        self.assertEqual(cases["founder"][1]["results"], [])
        self.assertEqual(cases["bad_fixture"][0], 200)
        self.assertEqual(cases["bad_fixture"][1]["snapshot_status"], "SNAPSHOT_ERROR")
        for value in cases.values():
            self.assertEqual(value[2], "no-store")


if __name__ == "__main__":
    unittest.main()
