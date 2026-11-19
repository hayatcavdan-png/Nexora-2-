"""Explicitly enabled NEXORA AI Lab paper worker: inputs -> entries -> exits.

UNTRUSTED external quotes are read-only. No trade execution, signing, RPC
sendTransaction, Telegram bridge, primary paper SQLite or wallet secrets.
This runner replaces TWO optional lab processes (candidate scanner and exit
quote watcher) with a single bounded schedule when an operator opts in.
Do NOT run alongside tools/social_paper/worker.py on the same private ledger.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from auto_paper import cycle
from nexora.social_ai.paper_watch import Store, refresh_due


def tick(*, store, quoter, research, now, scan=True, refresh=refresh_due):
    """One full paper-only signal cycle; mocks can replace every I/O edge."""
    if type(scan) is not bool:
        raise ValueError("invalid scan mode")
    # Exit quotes are maintained even when new BUY studies are paused.
    # Never skip due EXIT monitoring just because the profit guard is red.
    snapshot = refresh(store, quoter, now=now, max_quotes=3)
    if snapshot.get("mode") != "QUOTE_PAPER_RESEARCH" or snapshot.get("real_order") is not False:
        raise ValueError("unsafe paper snapshot")
    studies = snapshot.get("total_studies")
    if type(studies) is not int or not 0 <= studies <= 1000:
        raise ValueError("invalid paper ledger count")
    if scan:
        outcome = cycle(research=research, store=store, now=now)
    else:
        outcome = {"status": "EXIT_MONITOR_ONLY", "scanned": 0,
                   "paper_opened": 0, "lab_rejected": 0, "real_order": False}
    if outcome.get("real_order") is not False:
        raise ValueError("order mode prohibited")
    # No mints, source text, credentials, wallet identifiers or PnL claims.
    return {
        "mode": "PAPER_AI_SIGNAL_PIPELINE",
        "status": outcome["status"],
        "real_order": False,
        "studies": studies,
        "candidates_scanned": outcome["scanned"],
        "paper_entries": outcome["paper_opened"],
        "hard_or_ai_rejections": outcome["lab_rejected"],
        "ai_mode": outcome.get("ai_mode", "SHADOW_OR_PAUSED"),
        "exit_monitor_tick": True,
        "execution_not_proven": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEXORA optional quote-only AI signal paper runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--scan-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    if not 20 <= args.poll_seconds <= 60:
        parser.error("poll must be 20..60 seconds to watch 120-second quote windows")
    if not 120 <= args.scan_seconds <= 3600:
        parser.error("new candidate scan must be 120..3600 seconds")
    if (os.getenv("NEXORA_LAB_AUTO_PAPER") != "1"
            or os.getenv("SOCIAL_RESEARCH_LIVE_ENABLED") != "1"
            or os.getenv("SOCIAL_PAPER_WATCH_ENABLED") != "1"):
        parser.error("isolated paper and read-only provider flags must ALL be enabled")
    if not os.getenv("HELIUS_API_KEY") or not os.getenv("JUPITER_API_KEY"):
        parser.error("provider keys are missing from separate private environment")
    path = os.getenv("SOCIAL_PAPER_WATCH_PATH", "")
    if not path:
        parser.error("private absolute paper JSON path required")

    from nexora.market import JupiterQuoter
    from nexora.social_ai.recent_research import research_recent
    os.umask(0o077)
    store = Store(path)
    quoter = JupiterQuoter(timeout=8)

    def discover(**args):
        # Reuse one private HTTP session and bound the discovery quota.
        return research_recent(quoter=quoter, **args)

    last_scan = float("-inf")
    try:
        while True:
            now = time.time()
            monotonic = time.monotonic()
            due_scan = monotonic - last_scan >= args.scan_seconds
            try:
                status = tick(store=store, quoter=quoter, research=discover,
                              now=now, scan=due_scan)
                if due_scan:
                    last_scan = monotonic
                print("NEXORA_PAPER_SIGNAL", status["status"],
                      "studies", status["studies"],
                      "scanned", status["candidates_scanned"],
                      "paper_entries", status["paper_entries"],
                      "ai", status["ai_mode"], flush=True)
            except (OSError, ValueError, RuntimeError, TypeError, KeyError):
                # Never swallow an error into a fictitious entry or sell.
                print("NEXORA_PAPER_SIGNAL_UNAVAILABLE_NO_ORDER", flush=True)
            if args.once:
                break
            time.sleep(args.poll_seconds)
    finally:
        quoter.session.close()


if __name__ == "__main__":
    main()
