"""Separate PRIVATE 100 USDT paper-research watch, no orders or prod DB.

Only a user-enabled, already vetted *read-only Jupiter quote candidate* can
reserve a hypothetical amount. Four horizon marks are independent "what-if"
sell quotes, NOT four real sells. Missing/missed quotes remain UNKNOWN.

State I/O uses a user-specified .json path (not default SQLite), process lock,
atomic replacement, mode 0600. NO network activity in this module.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import fcntl
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time

from .events import valid_address
from .recent_research import USDT_MINT, _quote_value

HORIZONS = (5, 15, 30, 60)
TOTAL_USDT = Decimal("100")
INPUT_USDT = Decimal("4")
# Explicit conservative assumptions in USDT, NOT measured Solana gas or fees.
ASSUMED_BUY_FEE_USDT = Decimal("0.04")
ASSUMED_SELL_FEE_USDT = Decimal("0.04")
SLIPPAGE_BUFFER_BPS = Decimal("100")
ENTRY_COST = INPUT_USDT * (Decimal("1") + SLIPPAGE_BUFFER_BPS / Decimal("10000")) + ASSUMED_BUY_FEE_USDT
QUOTE_WINDOW_SECONDS = 120
OPEN_FRESHNESS_SECONDS = 30
MAX_ACTIVE_STUDIES = 5
MAX_RECORDS = 1000


class PaperWatchError(ValueError):
    pass


def _now(value):
    if type(value) not in (int, float):
        raise PaperWatchError("timestamp invalid")
    try:
        num = float(value)
    except (OverflowError, ValueError):
        raise PaperWatchError("timestamp invalid") from None
    if not math.isfinite(num) or num <= 0:
        raise PaperWatchError("timestamp invalid")
    return num


def initial_state():
    return {
        "schema_version": 1,
        "mode": "QUOTE_PAPER_RESEARCH",
        "currency": "USDT",
        "read_only_market": True,
        "real_order": False,
        "social_ai_transfer": False,
        "initial_cash_usdt": "100",
        "available_research_cash_usdt": "100",
        "entries": [],
    }


def _valid_state(state):
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise PaperWatchError("state schema invalid")
    if (state.get("mode") != "QUOTE_PAPER_RESEARCH" or
            state.get("real_order") is not False or
            state.get("social_ai_transfer") is not False or
            state.get("currency") != "USDT"):
        raise PaperWatchError("mode not safe")
    entries = state.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_RECORDS:
        raise PaperWatchError("invalid entry list")
    balance = state.get("available_research_cash_usdt")
    if not isinstance(balance, str):
        raise PaperWatchError("balance invalid")
    try:
        num = Decimal(balance)
    except InvalidOperation:
        raise PaperWatchError("balance invalid") from None
    if not num.is_finite() or not 0 <= num <= TOTAL_USDT:
        raise PaperWatchError("balance outside budget")
    if any(not isinstance(e, dict) or not valid_address(e.get("mint")) for e in entries):
        raise PaperWatchError("invalid record")
    if len({e["mint"] for e in entries}) != len(entries):
        raise PaperWatchError("duplicate mint records")
    return num


def open_study(state, research, *, now):
    """The quote preview may be up to 30 seconds old. Never open from metadata."""
    now = _now(now)
    cash = _valid_state(state)
    if not isinstance(research, dict) or (
        research.get("mode") != "READ_ONLY_RESEARCH" or
        research.get("status") != "RESEARCH_CANDIDATE" or
        research.get("real_order") is not False or
        research.get("quote_only") is not True or
        research.get("paper_entry") is not False or
        research.get("social_ai_transfer") is not False
    ):
        return {"opened": False, "reason": "RESEARCH_PROOF_REQUIRED"}
    mint = research.get("mint")
    if not valid_address(mint) or mint == USDT_MINT:
        return {"opened": False, "reason": "MINT_INVALID"}
    stamp = research.get("observed_at")
    try:
        stamp = _now(stamp)
    except PaperWatchError:
        stamp = None
    if stamp is None or not stamp <= now <= stamp + OPEN_FRESHNESS_SECONDS:
        return {"opened": False, "reason": "QUOTE_STALE"}
    raw_qty = research.get("expected_token_qty_raw")
    if not isinstance(raw_qty, str) or not raw_qty.isdigit() or not 0 < int(raw_qty) < 10 ** 30:
        return {"opened": False, "reason": "TOKEN_QUANTITY_UNKNOWN"}
    entries = state["entries"]
    if any(row["mint"] == mint for row in entries):
        return {"opened": False, "reason": "DUPLICATE_MINT"}
    if len(entries) >= MAX_RECORDS:
        return {"opened": False, "reason": "LEDGER_FULL"}
    active = sum(any(x.get("status") == "PENDING" for x in row.get("horizons", {}).values())
                 for row in entries)
    if active >= MAX_ACTIVE_STUDIES:
        return {"opened": False, "reason": "ACTIVE_STUDY_LIMIT"}
    if ENTRY_COST > cash:
        return {"opened": False, "reason": "CASH_LIMIT"}
    ledger_row = {
        "mint": mint,
        "source": "MANUAL_OR_JUPITER_RECENT",
        "observed_at": stamp,
        "token_qty_raw": raw_qty,
        "buy_input_usdt": "4",
        "assumed_buy_fee_usdt": str(ASSUMED_BUY_FEE_USDT),
        "assumed_sell_fee_usdt": str(ASSUMED_SELL_FEE_USDT),
        "assumed_slippage_bps": str(SLIPPAGE_BUFFER_BPS),
        "reserved_cost_usdt": str(ENTRY_COST),
        "reserved": True,
        "horizons": {f"{m}dk": {"status": "PENDING", "net_usdt": None}
                     for m in HORIZONS},
    }
    entries.append(ledger_row)
    state["available_research_cash_usdt"] = str(cash - ENTRY_COST)
    return {"opened": True, "reason": "SIMULATED_RESEARCH_ONLY", "mint": mint}


def due_horizons(state, *, now, max_results=5):
    now = _now(now)
    _valid_state(state)
    if type(max_results) is not int or not 1 <= max_results <= 10:
        raise PaperWatchError("invalid quote budget")
    due = []
    for row in state["entries"]:
        for m in HORIZONS:
            key = f"{m}dk"
            if row["horizons"][key]["status"] != "PENDING":
                continue
            start = row["observed_at"] + m * 60
            if start <= now <= start + QUOTE_WINDOW_SECONDS:
                due.append((row["mint"], key, int(row["token_qty_raw"])))
                if len(due) >= max_results:
                    return due
    return due


def settle_horizon(state, mint, key, *, now, quote=None):
    """Record a measured quote only during its horizon, never back-fill later."""
    now = _now(now)
    _valid_state(state)
    if key not in {f"{m}dk" for m in HORIZONS}:
        raise PaperWatchError("unknown horizon")
    row = next((r for r in state["entries"] if r["mint"] == mint), None)
    if row is None:
        raise PaperWatchError("unknown position")
    rec = row["horizons"][key]
    if rec.get("status") != "PENDING":
        return rec
    start = row["observed_at"] + int(key[:-2]) * 60
    if now < start:
        return rec
    if now > start + QUOTE_WINDOW_SECONDS:
        rec.update(status="UNKNOWN", reason="WINDOW_MISSED", net_usdt=None)
        return rec
    if quote is None:
        rec.update(status="UNKNOWN", reason="QUOTE_UNAVAILABLE", net_usdt=None)
        return rec
    qty = int(row["token_qty_raw"])
    parsed = _quote_value(quote, qty)
    if parsed is None:
        rec.update(status="UNKNOWN", reason="QUOTE_INVALID", net_usdt=None)
        return rec
    raw_out, _ = parsed
    expected_exit = Decimal(raw_out) / Decimal("1000000")
    buffered = expected_exit * (Decimal("1") - SLIPPAGE_BUFFER_BPS / Decimal("10000"))
    net = buffered - ASSUMED_SELL_FEE_USDT - Decimal(row["reserved_cost_usdt"])
    rec.update(status="OK", reason="QUOTE_SNAPSHOT_ASSUMPTIONS",
               net_usdt=str(net.quantize(Decimal("0.000001"))),
               quoted_exit_usdt=str(expected_exit), measured_at=now)
    return rec


def expire_missed(state, *, now):
    """Mark old unobserved horizons unknown without ever fabricating prices."""
    now = _now(now)
    _valid_state(state)
    changed = False
    for row in state["entries"]:
        for m in HORIZONS:
            rec = row["horizons"][f"{m}dk"]
            if rec["status"] != "PENDING":
                continue
            if now > row["observed_at"] + m * 60 + QUOTE_WINDOW_SECONDS:
                rec.update(status="UNKNOWN", reason="WINDOW_MISSED", net_usdt=None)
                changed = True
    return changed


def release_completed(state):
    """Release principal after every independent horizon is measured or missed.

    The results are *four research scenarios*, not executed sells. Hypothetical
    profits are never credited to available research cash.
    """
    available = _valid_state(state)
    changed = False
    for row in state["entries"]:
        if row.get("reserved") is not True:
            continue
        if any(x.get("status") == "PENDING" for x in row["horizons"].values()):
            continue
        available += Decimal(row["reserved_cost_usdt"])
        row["reserved"] = False
        changed = True
    if changed:
        if available > TOTAL_USDT:
            raise PaperWatchError("released cash outside budget")
        state["available_research_cash_usdt"] = str(available)
    return changed


def public_status(state):
    _valid_state(state)
    return {
        "schema_version": 1,
        "mode": "QUOTE_PAPER_RESEARCH",
        "currency": "USDT",
        "read_only_market": True,
        "real_order": False,
        "social_ai_transfer": False,
        "initial_cash_usdt": "100",
        "available_research_cash_usdt": state["available_research_cash_usdt"],
        "entries": state["entries"][-20:],
        "total_studies": len(state["entries"]),
        "results_are_hypothetical": True,
        "network_fee_is_assumed": True,
        "snapshot_status": "ISOLATED_PAPER_RESEARCH",
    }


class Store:
    """Explicit path only: no default and no production SQLite access."""
    def __init__(self, path):
        if not isinstance(path, (str, Path)) or not str(path):
            raise PaperWatchError("operator path required")
        self.path = Path(path)
        if not self.path.is_absolute() or self.path.suffix != ".json":
            raise PaperWatchError("absolute .json path required")
        if not self.path.parent.is_dir() or self.path.parent.is_symlink():
            raise PaperWatchError("existing private parent directory required")

    def _read(self):
        if not self.path.exists():
            return initial_state()
        fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PaperWatchError("state not regular file")
            with os.fdopen(fd, "rb") as f:
                fd = -1
                raw = f.read(500_001)
        finally:
            if fd >= 0:
                os.close(fd)
        if len(raw) > 500_000:
            raise PaperWatchError("state too large")
        data = json.loads(raw)
        _valid_state(data)
        return data

    def read(self):
        return public_status(self._read())

    def mutate(self, callback):
        lockpath = self.path.with_name(self.path.name + ".lock")
        fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            state = self._read()
            result = callback(state)
            _valid_state(state)
            raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 500_000:
                raise PaperWatchError("state limit exceeded")
            tmpfd, tmpname = tempfile.mkstemp(prefix=".nexora-paper-", dir=self.path.parent)
            try:
                with os.fdopen(tmpfd, "wb") as f:
                    f.write(raw)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmpname, 0o600)
                os.replace(tmpname, self.path)
            finally:
                if os.path.exists(tmpname):
                    os.unlink(tmpname)
            return result
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def refresh_due(store, quoter, *, now=None, max_quotes=3):
    """On-demand read-only quote refresh, bounded; external orchestration optional."""
    real_clock = now is None
    request_time = time.time() if real_clock else _now(now)
    current = store._read()
    due = due_horizons(current, now=request_time, max_results=max_quotes)
    if not due:
        if not expire_missed(current, now=request_time):
            return public_status(current)
        def expire_only(state):
            expire_missed(state, now=request_time)
            release_completed(state)
            return public_status(state)
        return store.mutate(expire_only)
    quotes = {}
    for mint, horizon, qty in due:
        try:
            value = quoter.quote(mint, USDT_MINT, qty)
        except Exception:
            value = None
        measured_at = time.time() if real_clock else request_time
        quotes[(mint, horizon)] = (value, measured_at)
    def apply(state):
        expire_missed(state, now=time.time() if real_clock else request_time)
        for mint, horizon, _ in due:
            quote, measured_at = quotes[(mint, horizon)]
            settle_horizon(state, mint, horizon, now=measured_at,
                           quote=quote)
        release_completed(state)
        return public_status(state)
    return store.mutate(apply)
