"""OPT-IN AUTOMATED READ-ONLY Solana discovery -> independent 100 USDT study.

Never submits/signs an order. Never touches production Paper, wallet keys,
Termux bridge, Telegram or production SQLite. Does nothing until operator
enables BOTH research and isolated paper flags in a separate process.
"""
import argparse
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def cycle(*, research, store, now):
    """Read-only provider -> independent lab risk gate -> bounded paper ledger.

    Safe, deterministic ordering by observed quality (not forecast win rate).
    Only one new study per cycle; a replayed mint cannot consume a slot.
    """
    from nexora.social_ai.paper_watch import open_study
    from nexora.strategy_lab.auto_decision import entry_signal

    response = research(enabled=True, limit=2)
    if not isinstance(response, dict) or response.get("mode") != "READ_ONLY_RESEARCH":
        return {"status": "PROVIDER_UNAVAILABLE", "scanned": 0,
                "paper_opened": 0, "lab_rejected": 0, "real_order": False}
    if response.get("status") != "OK" or response.get("real_order") is not False:
        return {"status": response.get("status", "PROVIDER_UNAVAILABLE"),
                "scanned": 0, "paper_opened": 0,
                "lab_rejected": 0, "real_order": False}

    vetted = []
    scanned = 0
    rejected = 0
    rows = response.get("results", [])
    if not isinstance(rows, list):
        return {"status": "PROVIDER_UNAVAILABLE", "scanned": 0,
                "paper_opened": 0, "lab_rejected": 0, "real_order": False}
    for candidate in rows[:2]:
        if not isinstance(candidate, dict):
            continue
        scanned += 1
        verdict = entry_signal(candidate, now=now)
        if verdict["action"] != "OPEN_PAPER_STUDY":
            rejected += 1
            continue
        vetted.append((verdict["screening_score_not_win_probability"],
                       candidate))
    vetted.sort(key=lambda item: item[0], reverse=True)

    opened = 0
    for _, candidate in vetted:
        result = store.mutate(lambda state: open_study(state, candidate, now=now))
        if result.get("opened") is True:
            opened = 1
            break
    return {"status": "QUOTE_PAPER_RESEARCH", "scanned": scanned,
            "paper_opened": opened, "lab_rejected": rejected, "real_order": False}


def main(args=None):
    parser = argparse.ArgumentParser(description="Isolated opt-in paper-only scanner")
    parser.add_argument("--once", action="store_true", help="one bounded scan, then exit")
    parser.add_argument("--interval", type=int, default=180)
    options = parser.parse_args(args)
    if not 120 <= options.interval <= 3600:
        parser.error("interval must be 120..3600 seconds")
    if not (os.getenv("NEXORA_LAB_AUTO_PAPER") == "1"
            and os.getenv("SOCIAL_RESEARCH_LIVE_ENABLED") == "1"
            and os.getenv("SOCIAL_PAPER_WATCH_ENABLED") == "1"):
        parser.error("operator has not enabled isolated read-only paper research")
    if not os.getenv("HELIUS_API_KEY") or not os.getenv("JUPITER_API_KEY"):
        parser.error("provider credentials missing from separate operator environment")
    path = os.getenv("SOCIAL_PAPER_WATCH_PATH", "")
    if not path:
        parser.error("isolated paper watch path missing")
    os.umask(0o077)
    from nexora.social_ai.paper_watch import Store
    from nexora.social_ai.recent_research import research_recent
    store = Store(path)
    while True:
        try:
            state = cycle(research=research_recent, store=store, now=time.time())
            # Deliberately no candidate mints, provider secrets or wallet IDs in logs.
            print("STRATEGY_LAB_AUTO_PAPER", state["status"],
                  "scanned", state["scanned"],
                  "paper_opened", state["paper_opened"], flush=True)
        except (OSError, ValueError, RuntimeError):
            print("STRATEGY_LAB_AUTO_PAPER_PROVIDER_OR_STATE_UNAVAILABLE", flush=True)
        if options.once:
            break
        time.sleep(options.interval)


if __name__ == "__main__":
    main()
