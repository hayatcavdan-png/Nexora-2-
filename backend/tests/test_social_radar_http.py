"""Kurucu Social Radar HTTP uç noktasının offline yetki regresyonu.

NEXORA Paper/Uyelik yalnızca subprocess içindeki bellek DB'lerini kullanır.
Sunucu dinleme soketi, harici HTTP, gerçek üretim DB ve token kullanılmaz.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


# Gerçek H.do_GET() yürütülür. HTTP yanıtı yalnızca testteki _send ile yakalanır.
CHILD_SCRIPT = r'''
import json
import os
from unittest.mock import patch

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

def request(headers):
    h = object.__new__(server.H)
    h.path = "/admin/social-radar"
    h.headers = headers
    results = []
    h._send = lambda status, body: results.append([status, body])
    h.do_GET()
    assert len(results) == 1, results
    return results[0]

with patch.object(server, "uyelik", Members()):
    cases = {
        "anonymous": request({}),
        "member": request({"X-Oturum": "user-token"}),
        "founder_session": request({"X-Oturum": "founder-token"}),
        "founder_key": request({"X-API-Key": "offline-test-founder-key"}),
        "wrong_key": request({"X-API-Key": "not-the-key"}),
    }
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
        for case in ("founder_key", "founder_session"):
            code, payload = cases[case]
            self.assertEqual(code, 200)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["snapshot_status"], "BAGLANTI_BEKLENIYOR")
            self.assertFalse(payload["live_enabled"])
            self.assertEqual(payload["alerts"], [])
            self.assertEqual(len(payload["sources"]), 5)
            self.assertTrue(all(not s["live_verified"] for s in payload["sources"]))


if __name__ == "__main__":
    unittest.main()
