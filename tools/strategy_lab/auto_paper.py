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
    from nexora.strategy_lab.profit_engine import review as profit_review
    from nexora.strategy_lab.signal_intelligence import assess, review as ai_review

    # Read the FULL private history before ANY new discovery network request.
    # All learning uses only fully mature quote evidence and prior entry features.
    history = store._read()
    profit = profit_review(history, as_of=now)
    if not profit["intake"]["allow_new_paper"]:
        return {"status": "PROFIT_GUARD_PAUSED", "scanned": 0,
                "paper_opened": 0, "lab_rejected": 0,
                "profit_guard": profit["intake"]["reason"], "real_order": False}

    model = ai_review(history, as_of=now)
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
        ai = assess(candidate, state=history, as_of=now, validation=model)
        # The learned model is an *additional* veto, never proof of safe trade.
        # It is shadow-only until independent walk-forward validation passes.
        if ai["action"] == "REJECT_NEW_PAPER" or (
            model["may_filter_new_paper"] and
            ai["action"] != "PAPER_PRIORITY_CANDIDATE"
        ):
            # Validated AI filtering must fail closed on missing feature proof,
            # never silently bypass the model to admit a weaker candidate.
            rejected += 1
            continue
        bound = (ai["prediction"] or {}).get("conservative_bound_usdt", 0)
        # In shadow mode retain the original quality ranking, without allowing
        # an unvalidated model to improve/harm paper selection.
        priority = (bound, verdict["screening_score_not_win_probability"]) if model["may_filter_new_paper"] else (0, verdict["screening_score_not_win_probability"])
        vetted.append((priority, candidate, ai))
    vetted.sort(key=lambda item: item[0], reverse=True)

    opened = 0
    # Default 5-minute horizon is chosen BEFORE each entry. This is essential
    # for obtaining honest training labels before the dynamic model is ready.
    # A learned exit may replace it only after independent forward validation.
    planned = 5
    if profit["status"] == "PAPER_EDGE_CANDIDATE":
        choice = profit.get("recommended_horizon_min")
        if type(choice) is int and choice in (5, 15, 30, 60):
            planned = choice
    for _, candidate, ai in vetted:
        paper_candidate = dict(candidate, planned_exit_horizon_min=planned,
                               lab_ai_decision={"action": ai["action"]})
        result = store.mutate(lambda state: open_study(state, paper_candidate, now=now))
        if result.get("opened") is True:
            opened = 1
            break
    return {"status": "QUOTE_PAPER_RESEARCH", "scanned": scanned,
            "paper_opened": opened, "lab_rejected": rejected, "real_order": False,
            "ai_mode": model["status"], "ai_walk_forward_validated":
                model["may_filter_new_paper"]}


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
