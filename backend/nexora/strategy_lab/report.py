"""Founder-only, redacted Strategy Lab snapshot contract.

No production DB access or provider calls. File is an operator-supplied offline
artifact; unknown fields, secrets and account details are never returned.
"""
import json
import os
import stat

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
        from math import isfinite
        if type(stamp) is not int or stamp <= previous or not isfinite(value) or value <= 0 or value > 1000000:
            raise ValueError("invalid historical equity point")
        previous = stamp
        res["equity"].append({"ts": stamp, "equity": round(value, 6)})
    res["summary"] = {
        "strategies_tested": 1 if res["equity"] else 0,
        "profitable_proven": False,
        "notice": "Historical and simulated; NOT investment profit evidence",
    }
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
