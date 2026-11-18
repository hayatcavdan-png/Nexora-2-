"""Kurucu Social Radar HTTP uç noktasının offline yetki regresyonu.

NEXORA Paper/Uyelik yalnızca subprocess içindeki bellek DB'lerini kullanır.
HTTP istekleri yalnızca geçici bir loopback soketine gider.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHILD_SCRIPT = r'''
import json
import os
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

os.environ["NEXORA_DB"] = ":memory:"
os.environ["UYELIK_DB"] = ":memory:"
os.environ["NEXORA_API_KEY"] = "offline-test-founder-key"
os.environ.pop("SOCIAL_RADAR_SNAPSHOT", None)

import server

class Members:
    def uye(self, session):
        if session == "user-token":
            return {"rol": "uye"}
        if session == "founder-token":
            return {"rol": "kurucu"}
        return None

def request(base, headers, path="/admin/social-radar", method="GET"):
    req = Request(base + path, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.load(response)

with patch.object(server, "uyelik", Members()), ThreadingHTTPServer(("127.0.0.1", 0), server.H) as httpd:
    base = f"http://127.0.0.1:{httpd.server_port}"
    thread = Thread(target=httpd.serve_forever)
    thread.start()
    founder = {"X-API-Key": "offline-test-founder-key"}
    try:
        cases = {
            "anonymous": request(base, {}),
            "member": request(base, {"X-Oturum": "user-token"}),
            "founder_session": request(base, {"X-Oturum": "founder-token"}),
            "founder_key": request(base, founder),
            "wrong_key": request(base, {"X-API-Key": "not-the-key"}),
            "unknown_path": request(base, founder, path="/admin/social-radar/missing"),
            "write": request(base, founder, method="POST"),
        }
    finally:
        httpd.shutdown()
        thread.join()
print(json.dumps(cases))
'''


class SocialRadarHttpTests(unittest.TestCase):
    def test_authorization_and_default_offline_endpoint(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["SOCIAL_LIVE_ENABLED"] = "0"
        with tempfile.TemporaryDirectory(prefix="nexora-social-api-test-") as home:
            run = subprocess.run(
                [sys.executable, "-B", "-c", CHILD_SCRIPT],
                cwd=home, env=env, capture_output=True, text=True, timeout=45,
                check=False,
            )
        self.assertEqual(run.returncode, 0, run.stderr[-1200:])
        cases = json.loads(run.stdout.strip())
        self.assertEqual(cases["anonymous"][0], 401)
        self.assertEqual(cases["member"][0], 403)
        self.assertEqual(cases["wrong_key"][0], 401)
        self.assertEqual(cases["unknown_path"][0], 404)
        self.assertEqual(cases["write"][0], 404)
        for case in ("founder_key", "founder_session"):
            code, payload = cases[case]
            self.assertEqual(code, 200)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["snapshot_status"], "BAGLANTI_BEKLENIYOR")
            self.assertFalse(payload["live_enabled"])
            self.assertEqual(payload["alerts"], [])
            self.assertEqual({s["source_id"] for s in payload["sources"]},
                             {"solana_early_trending", "kolscope", "ansem", "lookonchain", "bubblemaps"})
            self.assertTrue(all(not s["live_verified"] for s in payload["sources"]))


if __name__ == "__main__":
    unittest.main()
