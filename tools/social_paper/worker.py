"""Optional, isolated **quote-only** NEXORA 100 USDT paper research worker.

Does nothing until an operator explicitly configures ALL required env flags
and starts this script. Does not access Telegram or production SQLite.
Does NOT simulate actual execution, sign, broadcast or send transactions.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from nexora.market import JupiterQuoter
from nexora.social_ai.paper_watch import Store, refresh_due


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Jupiter exit quote monitor")
    parser.add_argument("--once", action="store_true", help="one bounded update then exit")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args(argv)

    if not 20 <= args.interval <= 600:
        parser.error("interval must be 20-600 seconds")
    if (os.getenv("SOCIAL_PAPER_WATCH_ENABLED") != "1"
            or os.getenv("SOCIAL_RESEARCH_LIVE_ENABLED") != "1"):
        parser.error("operator has not enabled PAPER and READ_ONLY_RESEARCH")
    if not os.getenv("JUPITER_API_KEY"):
        parser.error("JUPITER_API_KEY missing")
    path = os.getenv("SOCIAL_PAPER_WATCH_PATH")
    if not path:
        parser.error("separate SOCIAL_PAPER_WATCH_PATH absolute .json required")

    os.umask(0o077)
    store = Store(path)
    quoter = JupiterQuoter(timeout=8)

    try:
        while True:
            result = refresh_due(store, quoter, max_quotes=3)
            statuses = {}
            for entry in result["entries"]:
                for row in entry["horizons"].values():
                    code = row["status"]
                    statuses[code] = statuses.get(code, 0) + 1
            # No mint IDs, API keys, wallets, channel content in stdout.
            print(json.dumps({
                "mode": "PAPER_ONLY", "real_order": False,
                "studies": result["total_studies"],
                "horizons": statuses,
            }), flush=True)
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        quoter.session.close()


if __name__ == "__main__":
    main()
