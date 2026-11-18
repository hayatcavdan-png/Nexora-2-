"""Strategy Lab CLI creates only new sanitized artifacts and never overwrites."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/strategy_lab/run_once.py"


class StrategyRunnerTests(unittest.TestCase):
    def test_cli_sanitizes_secrets_and_never_overwrites(self):
        sample = [
            {"ts":1800000000+i*60,
             "open":str(1+i/100),"close":str(1+i/100),
             "low":str(.99+i/100),"high":str(1.01+i/100)}
            for i in range(40)
        ]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            output = Path(folder) / "out.json"
            source.write_text(json.dumps({
                "schema_version":1, "bars":sample,
                "api_key":"never-copy-this-value", "candidates":[]
            }), encoding="utf-8")
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                   "PYTHONDONTWRITEBYTECODE":"1", "PATH":os.defpath}
            cmd = [sys.executable, "-B", str(SCRIPT), "--input", str(source),
                   "--output", str(output)]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    env=env, cwd=folder, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = output.read_text(encoding="utf-8")
            self.assertNotIn("never-copy-this-value", saved)
            data = json.loads(saved)
            self.assertEqual(data["mode"], "PAPER_STRATEGY_LAB")
            self.assertEqual(data["historical_test"]["price_basis"], "NEXT_BAR_OPEN")
            self.assertEqual(data["summary"]["profitable_proven"], False)
            from nexora.strategy_lab.report import read_snapshot
            viewed = read_snapshot(str(output))
            self.assertEqual(viewed["historical_test"]["actual_execution"], False)
            self.assertIn("final_mark_usdt", viewed["historical_test"])
            second = subprocess.run(cmd, capture_output=True, text=True,
                                    env=env, cwd=folder, timeout=20)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), saved)
            self.assertFalse(data["real_order"])


    def test_full_day_chart_is_bounded_and_keeps_endpoints(self):
        # A normal 24-hour 1-minute feed used to fail report sanitization.
        sample = [
            {"ts": 1800000000 + i * 60,
             "open": "1", "high": "1.01", "low": "0.99", "close": "1"}
            for i in range(1440)
        ]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "full_day.json"
            source.write_text(json.dumps({
                "schema_version": 1, "bars": sample, "candidates": []
            }), encoding="utf-8")
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                   "PYTHONDONTWRITEBYTECODE": "1", "PATH": os.defpath}
            process = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--input", str(source)],
                capture_output=True, text=True, env=env, cwd=folder, timeout=20)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads(process.stdout)
            points = report["equity"]
            self.assertEqual(len(points), 1000)
            self.assertEqual(points[0]["ts"], sample[0]["ts"])
            self.assertEqual(points[-1]["ts"], sample[-1]["ts"])
            self.assertTrue(all(a["ts"] < b["ts"]
                                for a, b in zip(points, points[1:])))
            self.assertFalse(report["real_order"])



if __name__ == "__main__":
    unittest.main()
