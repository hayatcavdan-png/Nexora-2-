"""Kurucu Social Radar HTTP uç noktasının offline yetki regresyonu.

NEXORA Paper/Uyelik yalnızca geçici SQLite dosyalarını kullanır.
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
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

os.environ["NEXORA_DB"] = "smoke-paper.sqlite"
os.environ["UYELIK_DB"] = "smoke-membership.sqlite"
os.environ["NEXORA_API_KEY"] = "offline-test-founder-key"
os.environ.pop("SOCIAL_RADAR_SNAPSHOT", None)

import server

parola = "synthetic-smoke-password"
member_token = server.uyelik.kayit("member@example.invalid", parola)
server.uyelik.kayit("founder@example.invalid", parola)
server.uyelik.rol_ata("founder@example.invalid", "kurucu")
founder_token = server.uyelik.giris("founder@example.invalid", parola)

def request(base, headers, path="/admin/social-radar", method="GET"):
    req = Request(base + path, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.load(response), response.headers.get("Cache-Control")

with ThreadingHTTPServer(("127.0.0.1", 0), server.H) as httpd:
    base = f"http://127.0.0.1:{httpd.server_port}"
    thread = Thread(target=httpd.serve_forever)
    thread.start()
    founder = {"X-API-Key": "offline-test-founder-key"}
    try:
        cases = {
            "anonymous": request(base, {}),
            "member": request(base, {"X-Oturum": member_token}),
            "founder_session": request(base, {"X-Oturum": founder_token}),
            "founder_key": request(base, founder),
            "wrong_key": request(base, {"X-API-Key": "not-the-key"}),
            "unknown_path": request(base, founder, path="/admin/social-radar/missing"),
            "write": request(base, founder, method="POST"),
        }
        Path("unreadable-snapshot.json").write_text("{bozuk", encoding="utf-8")
        os.environ["SOCIAL_RADAR_SNAPSHOT"] = "unreadable-snapshot.json"
        cases["live_off"] = request(base, founder)
    finally:
        httpd.shutdown()
        thread.join()
print(json.dumps(cases))
'''


class SocialRadarHttpTests(unittest.TestCase):
    def test_authorization_and_default_offline_endpoint(self):
        paths = [str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH")]
        env = {
            "PATH": os.defpath,
            "PYTHONPATH": os.pathsep.join(filter(None, paths)),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOCIAL_LIVE_ENABLED": "0",
        }
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
        for case in ("anonymous", "member", "wrong_key"):
            self.assertEqual(cases[case][2], "no-store")
        self.assertEqual(cases["live_off"][0], 200)
        self.assertEqual(cases["live_off"][1]["snapshot_status"], "CANLI_IZLEME_KAPALI")
        self.assertEqual(cases["live_off"][1]["alerts"], [])
        for case in ("founder_key", "founder_session"):
            code, payload, cache = cases[case]
            self.assertEqual(code, 200)
            self.assertEqual(cache, "no-store")
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["snapshot_status"], "BAGLANTI_BEKLENIYOR")
            self.assertFalse(payload["live_enabled"])
            self.assertEqual(payload["alerts"], [])
            self.assertEqual({s["source_id"] for s in payload["sources"]},
                             {"solana_early_trending", "kolscope", "ansem", "lookonchain", "bubblemaps"})
            self.assertTrue(all(not s["live_verified"] for s in payload["sources"]))


if __name__ == "__main__":
    unittest.main()
