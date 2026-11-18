"""Offline-only operator-controlled NEXORA Strategy Lab snapshot generator.

Input JSON: {"schema_version":1,"bars":[...],"candidates":[...]}
No network, Telegram, exchange, production DB, private keys or live orders.
Output file is CREATE-ONLY; existing data is never overwritten or deleted.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from nexora.strategy_lab.engine import backtest, rank_candidates
from nexora.strategy_lab.report import sanitize


def load_input(path):
    file = Path(path)
    if not file.is_file() or file.is_symlink() or file.stat().st_size > 300_000:
        raise ValueError("small regular JSON input required")
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("invalid input schema")
    return data


def analyze(data, *, optional=False):
    result = backtest(data.get("bars"))
    summary = {
        "schema_version": 1, "mode": "PAPER_STRATEGY_LAB",
        "real_order": False, "initial_usdt": "100",
        "equity": result["equity"],
        "candidates": data.get("candidates", []),
    }
    # Strict output contract removes every unrecognized key/sensitive input.
    snapshot = sanitize(summary)
    snapshot["snapshot_status"] = "OFFLINE_SNAPSHOT"
    snapshot["historical_test"] = {
        "final_mark_usdt": result["final_mark_usdt"],
        "trades": len(result["trades"]),
        "fee_bps": result["assumptions"]["fee_bps"],
        "slippage_bps": result["assumptions"]["slippage_bps"],
        "price_basis": "NEXT_BAR_OPEN",
        "actual_execution": False,
    }
    snapshot["optional_reports"] = {}
    if optional:
        from nexora.strategy_lab.integrations import (
            capabilities, duckdb_summary, vectorbt_study, quantstats_summary
        )
        deps = capabilities()
        if deps["vectorbt"]["installed"]:
            snapshot["optional_reports"]["vectorbt"] = vectorbt_study(data["bars"])
        if deps["quantstats"]["installed"] and len(result["equity"]) >= 30:
            snapshot["optional_reports"]["quantstats"] = quantstats_summary(result["equity"])
        if deps["duckdb"]["installed"]:
            snapshot["optional_reports"]["duckdb"] = duckdb_summary(data.get("hypothetical_results", []))
    return snapshot


def create_private_output(path, snapshot):
    file = Path(path)
    if not file.is_absolute() or not file.parent.is_dir() or file.parent.is_symlink():
        raise ValueError("output requires existing absolute parent directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    handle = os.open(file, flags, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        # The caller explicitly requested a *new* file; on failure it remains
        # as an incomplete artifact for manual examination, never delete data.
        raise


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="offline OHLC JSON snapshot")
    parser.add_argument("--output", help="new absolute .json report path; no overwrites")
    parser.add_argument("--optional-analytics", action="store_true")
    a = parser.parse_args(args)
    os.umask(0o077)
    snapshot = analyze(load_input(a.input), optional=a.optional_analytics)
    if a.output:
        if not a.output.endswith(".json"):
            parser.error("output must be .json")
        create_private_output(a.output, snapshot)
        print("NEXORA STRATEJI LAB: YENI OZEL SANAL RAPOR YAZILDI")
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
