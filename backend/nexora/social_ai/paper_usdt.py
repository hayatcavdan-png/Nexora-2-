"""Offline-only Solana mint risk gate and USDT hypothetical paper results.

Every input is a caller-supplied fixture. This module does not fetch prices,
authenticate licensed providers, read Telegram posts or place real/paper orders.
All positive results remain **simulated evidence**, not live buy signals.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import math
import stat

from nexora.token_safety import evaluate as token_safety
from .events import valid_address

HORIZONS = (5, 15, 30, 60)
INITIAL_CASH_USDT = Decimal("100")
MAX_ENTRY_USDT = Decimal("5")
MIN_LIQUIDITY_USDT = Decimal("10000")
MAX_AGE_SECONDS = 120
MAX_EVENT_AGE_SECONDS = 24 * 3600
MAX_SLIPPAGE_BPS = Decimal("300")
MAX_PRICE_IMPACT_BPS = Decimal("300")
EXIT_TOLERANCE_SECONDS = 120


def _decimal(value, *, allow_zero=False):
    """Amounts as decimal strings; no floats, booleans, exponentials or NaN."""
    if isinstance(value, bool) or type(value) not in (str, int):
        return None
    raw = str(value)
    if not raw or len(raw) > 32 or "e" in raw.lower():
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        return None
    return amount


def _time(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def _fresh(row, cutoff, *, start=0, seconds=MAX_AGE_SECONDS):
    """Never use a record fetched after the decision deadline."""
    if not isinstance(row, dict):
        return False
    observed, fetched = _time(row.get("measured_at")), _time(row.get("fetched_at"))
    return (observed is not None and fetched is not None
            and start <= observed <= fetched <= cutoff
            and cutoff - observed <= seconds)


def _quote(row, mint, *, side, cutoff, start=0, seconds=MAX_AGE_SECONDS):
    if not _fresh(row, cutoff, start=start, seconds=seconds):
        return None
    if (row.get("mint") != mint or row.get("side") != side
            or row.get("quote_asset") != "USDT" or row.get("executable") is not True):
        return None
    slip = _decimal(row.get("slippage_bps"), allow_zero=True)
    impact = _decimal(row.get("price_impact_bps"), allow_zero=True)
    network = _decimal(row.get("network_fee_usdt"), allow_zero=True)
    dex = _decimal(row.get("dex_fee_usdt"), allow_zero=True)
    if any(x is None for x in (slip, impact, network, dex)):
        return None
    if slip > MAX_SLIPPAGE_BPS or impact > MAX_PRICE_IMPACT_BPS:
        return None
    qty = _decimal(row.get("token_qty"))
    value = _decimal(row.get("input_usdt") if side == "buy" else row.get("output_usdt"))
    if value is None or qty is None:
        return None
    return value, qty, network + dex


def simulate(candidate, *, now):
    """A single token, with t0-correct entry and each mature horizon's exit.

    Candidate is an OFFLINE user fixture. Provider permission flags are
    declarations, not proofs; no output is marked LIVE_AUTHORIZED.
    """
    now = _time(now)
    if now is None:
        raise ValueError("invalid current time")
    out = dict(
        mode="OFFLINE_PAPER_ONLY", real_order=False, social_ai_transfer=False,
        currency="USDT", initial_cash_usdt=str(INITIAL_CASH_USDT),
        status="BLOCKED", reason="UNKNOWN", mint=None, entry=None,
        horizons={f"{m}dk": dict(status="UNKNOWN", net_usdt=None) for m in HORIZONS},
    )
    if not isinstance(candidate, dict):
        out["reason"] = "CANDIDATE_INVALID"
        return out

    source = candidate.get("source")
    if source not in ("manual_mint", "licensed_feed"):
        out["reason"] = "SOURCE_NOT_AUTHORIZED"
        return out
    if source == "licensed_feed" and (
        candidate.get("permission_verified") is not True
        or not isinstance(candidate.get("license_id"), str)
        or not 1 <= len(candidate["license_id"].strip()) <= 128
    ):
        out["reason"] = "SOURCE_PERMISSION_MISSING"
        return out

    mint = candidate.get("mint")
    if not valid_address(mint):
        out["reason"] = "MINT_INVALID"
        return out
    out["mint"] = mint
    t0 = _time(candidate.get("observed_at"))
    if t0 is None or not t0 <= now <= t0 + MAX_EVENT_AGE_SECONDS:
        out["reason"] = "EVENT_TIME_INVALID"
        return out

    account = candidate.get("account")
    if not _fresh(account, t0) or account.get("queried_mint") != mint:
        out["reason"] = "MINT_PROOF_MISSING_OR_STALE"
        return out
    value = account.get("value")
    if not isinstance(value, dict):
        out["reason"] = "MINT_ACCOUNT_UNKNOWN"
        return out
    data = value.get("data")
    parsed = data.get("parsed") if isinstance(data, dict) else None
    if not isinstance(parsed, dict) or parsed.get("type") != "mint":
        out["reason"] = "NOT_A_MINT"
        return out
    info = parsed.get("info")
    if not isinstance(info, dict) or info.get("isInitialized") is not True:
        out["reason"] = "NOT_INITIALIZED"
        return out
    verdict = token_safety(value)
    if verdict.get("verdict") != "UYGUN":
        out["reason"] = "MINT_RISK_OR_UNKNOWN"
        return out

    liquidity = candidate.get("liquidity")
    if not _fresh(liquidity, t0) or liquidity.get("mint") != mint:
        out["reason"] = "LIQUIDITY_UNKNOWN"
        return out
    total_liquidity = _decimal(liquidity.get("total_usdt"))
    if (liquidity.get("verified") is not True or total_liquidity is None
            or total_liquidity < MIN_LIQUIDITY_USDT):
        out["reason"] = "LIQUIDITY_INSUFFICIENT_OR_UNVERIFIED"
        return out

    entry = _quote(candidate.get("buy_quote"), mint, side="buy", cutoff=t0)
    if entry is None:
        out["reason"] = "ENTRY_QUOTE_UNKNOWN"
        return out
    input_usdt, qty, fees = entry
    spent = input_usdt + fees
    if spent > MAX_ENTRY_USDT:
        out["reason"] = "ENTRY_LIMIT_EXCEEDED"
        return out
    if spent > INITIAL_CASH_USDT:
        out["reason"] = "BUDGET_EXCEEDED"
        return out

    out["status"] = "PAPER_ELIGIBLE"
    out["reason"] = "OFFLINE_EVIDENCE_PASSED"
    out["entry"] = dict(input_usdt=str(input_usdt), fees_usdt=str(fees),
                        total_cost_usdt=str(spent), token_qty=str(qty),
                        remaining_cash_usdt=str(INITIAL_CASH_USDT - spent))
    exits = candidate.get("sell_quotes")
    if not isinstance(exits, dict):
        exits = {}
    for minutes in HORIZONS:
        key, due = f"{minutes}dk", t0 + minutes * 60
        if now < due:
            out["horizons"][key] = dict(status="PENDING", net_usdt=None)
            continue
        # The earliest executable exit available within two minutes of due.
        # A later quote cannot retroactively fill the old 5/15/30/60m result.
        cutoff = min(now, due + EXIT_TOLERANCE_SECONDS)
        sell = _quote(exits.get(key), mint, side="sell", cutoff=cutoff,
                      start=due, seconds=EXIT_TOLERANCE_SECONDS)
        if sell is None or sell[1] != qty:
            continue
        proceeds, _, exit_fees = sell
        net = proceeds - exit_fees - spent
        out["horizons"][key] = dict(
            status="OK", net_usdt=str(net.quantize(Decimal("0.000001")))
        )
    return out


def portfolio(candidates, *, now):
    """Deterministic, read-only 100 USDT paper preview, never a trade ledger."""
    if not isinstance(candidates, list) or len(candidates) > 50:
        raise ValueError("expected <=50 candidate fixtures")
    cash, seen, rows = INITIAL_CASH_USDT, set(), []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            rows.append(simulate(candidate, now=now))
            continue
        mint = candidate.get("mint")
        event_id = candidate.get("event_id")
        dedup = (mint, event_id) if isinstance(mint, str) and isinstance(event_id, str) and 0 < len(event_id) <= 128 else None
        if dedup is not None and dedup in seen:
            row = simulate(None, now=now)
            row["reason"] = "DUPLICATE_EVENT"
            rows.append(row)
            continue
        if dedup is not None:
            seen.add(dedup)
        row = simulate(candidate, now=now)
        if row["status"] == "PAPER_ELIGIBLE":
            cost = Decimal(row["entry"]["total_cost_usdt"])
            if cost > cash:
                row["status"], row["reason"], row["entry"] = "BLOCKED", "PORTFOLIO_CASH_EXCEEDED", None
            else:
                cash -= cost
                row["entry"]["remaining_cash_usdt"] = str(cash)
        rows.append(row)
    return dict(
        schema_version=1, mode="OFFLINE_PAPER_ONLY", currency="USDT",
        read_only=True, real_order=False, social_ai_transfer=False,
        initial_cash_usdt=str(INITIAL_CASH_USDT), remaining_cash_usdt=str(cash),
        positions=sum(r["status"] == "PAPER_ELIGIBLE" for r in rows), results=rows,
    )


def from_file(path, *, now):
    """Read a small operator-specified regular JSON file, not Telegram or DB."""
    if not path:
        return dict(schema_version=1, mode="OFFLINE_PAPER_ONLY", read_only=True,
                    real_order=False, social_ai_transfer=False, currency="USDT",
                    initial_cash_usdt=str(INITIAL_CASH_USDT),
                    remaining_cash_usdt=str(INITIAL_CASH_USDT),
                    positions=0, results=[], snapshot_status="NOT_CONFIGURED")
    flags = __import__("os").O_RDONLY | getattr(__import__("os"), "O_NOFOLLOW", 0) | __import__("os").O_NONBLOCK
    fd = __import__("os").open(path, flags)
    try:
        if not stat.S_ISREG(__import__("os").fstat(fd).st_mode):
            raise ValueError("fixture must be a regular file")
        with __import__("os").fdopen(fd, "rb") as f:
            fd = -1
            raw = f.read(200_001)
    finally:
        if fd >= 0:
            __import__("os").close(fd)
    if len(raw) > 200_000:
        raise ValueError("fixture too large")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("invalid fixture")
    result = portfolio(data.get("candidates"), now=now)
    result["snapshot_status"] = "OFFLINE_FIXTURE_ONLY"
    return result


def main(argv=None):
    import argparse
    import time
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, help="small synthetic/offline JSON fixture")
    parser.add_argument("--now", type=float, default=None)
    args = parser.parse_args(argv)
    print(json.dumps(from_file(args.fixture, now=args.now or time.time()),
                     sort_keys=True, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
