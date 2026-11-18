"""Founder-only, redacted Strategy Lab snapshot contract.

No production DB access or provider calls. File is an operator-supplied offline
artifact; unknown fields, secrets and account details are never returned.
"""
import json
import os
import stat
from math import isfinite

from .integrations import capabilities

MAX_BYTES = 300000


def empty(status="NOT_CONFIGURED"):
    return {
        "schema_version": 1, "mode": "PAPER_STRATEGY_LAB",
        "snapshot_status": status, "real_order": False,
        "live_trading": False, "initial_usdt": "100",
        "capabilities": capabilities(),
        "candidates": [], "equity": [], "trades": [],
        "summary": {"strategies_tested": 0, "profitable_proven": False},
    }


def sanitize(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("mode") != "PAPER_STRATEGY_LAB":
        raise ValueError("invalid strategy snapshot")
    if data.get("real_order") is not False:
        raise ValueError("real orders prohibited")
    res = empty("OFFLINE_SNAPSHOT")
    candidates = data.get("candidates", [])
    equity = data.get("equity", [])
    if not isinstance(candidates, list) or len(candidates) > 100:
        raise ValueError("too many candidates")
    if not isinstance(equity, list) or len(equity) > 1000:
        raise ValueError("too many equity points")
    from .engine import rank_candidates
    res["candidates"] = rank_candidates(candidates)[:20]
    previous = 0
    for point in equity:
        if not isinstance(point, dict):
            raise ValueError("invalid equity")
        stamp = point.get("ts")
        try:
            value = float(point.get("equity"))
        except (ValueError, TypeError):
            raise ValueError("invalid equity value") from None
        if type(stamp) is not int or stamp <= previous or not isfinite(value) or value <= 0 or value > 1000000:
            raise ValueError("invalid historical equity point")
        previous = stamp
        res["equity"].append({"ts": stamp, "equity": round(value, 6)})
    res["summary"] = {
        "strategies_tested": 1 if res["equity"] else 0,
        "profitable_proven": False,
        "notice": "Historical and simulated; NOT investment profit evidence",
    }
    metrics = data.get("historical_test")
    if isinstance(metrics, dict):
        allowed = ("final_mark_usdt", "trades", "fee_bps", "slippage_bps")
        valid = {}
        for key in allowed:
            val = metrics.get(key)
            if key == "trades" and type(val) is int and 0 <= val <= 10000:
                valid[key] = val
            elif key != "trades" and type(val) in (int, float, str):
                try:
                    x = float(val)
                except (ValueError, OverflowError):
                    continue
                if isfinite(x) and 0 <= x <= 1000000:
                    valid[key] = round(x, 6)
        if valid:
            res["historical_test"] = dict(valid,
                price_basis="NEXT_BAR_OPEN", actual_execution=False,
                pnl_is_hypothetical=True)
    optional = data.get("optional_reports")
    if isinstance(optional, dict):
        cleaned = {}
        for tool, keys in {
            "vectorbt": ("final_equity_usdt", "total_return_pct", "max_drawdown_pct", "trades"),
            "quantstats": ("max_drawdown_pct", "daily_sharpe", "sample_bars"),
            "duckdb": ("evaluated_rows",),
        }.items():
            val = optional.get(tool)
            if not isinstance(val, dict) or val.get("real_order") is not False:
                continue
            row = {}
            for field in keys:
                number = val.get(field)
                if type(number) in (int, float) and isfinite(number) and abs(number) < 1_000_000:
                    row[field] = round(number, 6) if isinstance(number, float) else number
            if row:
                cleaned[tool] = row
        res["optional_reports"] = cleaned
    return res


def read_snapshot(path):
    if not path:
        return empty()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return empty("UNAVAILABLE")
            with os.fdopen(fd, "rb") as file:
                fd = -1
                raw = file.read(MAX_BYTES+1)
        finally:
            if fd >= 0:
                os.close(fd)
        if len(raw) > MAX_BYTES:
            return empty("UNAVAILABLE")
        return sanitize(json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return empty("UNAVAILABLE")


def auto_paper_status(path, *, enabled=False):
    """Founder-private aggregate from separate paper JSON, never an order flag.

    A readable ledger is NOT evidence that the background worker is running.
    Do not return token addresses, wallets, keys or raw provider responses.
    """
    base = {
        "schema_version": 1, "mode": "QUOTE_PAPER_RESEARCH",
        "status": "DISABLED", "real_order": False, "live_trading": False,
        "total_studies": 0, "active_recent_studies": 0,
        "recent_sell_signals": 0, "recent_exit_unavailable": 0,
        "available_research_cash_usdt": None,
        "worker_running_verified": False,
    }
    if not enabled:
        return base
    if not path:
        return dict(base, status="PATH_NOT_CONFIGURED")
    try:
        from nexora.social_ai.paper_watch import Store, public_status
        from nexora.strategy_lab.profit_engine import review as profit_review
        from time import time
        store = Store(path)
        history = store._read()
        public = public_status(history)
        review = profit_review(history, as_of=time())
        entries = public.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("invalid entries")
        signals = [
            v.get("lab_exit_signal", {})
            for row in entries if isinstance(row, dict)
            for v in row.get("horizons", {}).values() if isinstance(v, dict)
        ]
        return dict(
            base, status="LEDGER_AVAILABLE",
            total_studies=public["total_studies"],
            active_recent_studies=sum(row.get("reserved") is True for row in entries),
            recent_sell_signals=sum(v.get("action") == "PAPER_SELL_SIGNAL"
                                    for v in signals if isinstance(v, dict)),
            recent_exit_unavailable=sum(v.get("action") == "EXIT_UNAVAILABLE"
                                        for v in signals if isinstance(v, dict)),
            available_research_cash_usdt=public["available_research_cash_usdt"],
            profit_research={
                "status": review["status"],
                "mature_samples": review["mature_samples"],
                "recommended_horizon_min": review["recommended_horizon_min"],
                "intake": review["intake"],
                "forward_stress": review.get("forward_stress", {}),
                "not_proven_real_profit": True,
            },
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return dict(base, status="LEDGER_UNAVAILABLE")
