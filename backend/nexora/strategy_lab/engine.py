"""Deterministic, no-lookahead and NO REAL ORDER strategy research.

Inputs are complete caller-owned historical candles with monotonic timestamps.
Signals use only information available at each bar close. Next-bar open is the
earliest possible paper fill. Never present simulation as proven live profit.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from math import isfinite
from nexora.social_ai.events import valid_address

MAX_BARS = 10000
CASH = Decimal("100")
FEE_BPS = Decimal("20")
SLIPPAGE_BPS = Decimal("100")
ENTRY_BUDGET_USDT = Decimal("4")
STOP_PCT = Decimal("0.08")
TAKE_PCT = Decimal("0.16")
LOOKBACK = 5


class LabInputError(ValueError):
    pass


def decimal(value, *, allow_zero=False):
    if type(value) not in (str, int, float, Decimal):
        raise LabInputError("number must be finite")
    try:
        val = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LabInputError("invalid number") from None
    if not val.is_finite() or val < 0 or (not allow_zero and val == 0):
        raise LabInputError("positive finite number required")
    return val


def candles_checked(bars):
    if not isinstance(bars, list) or not 2 <= len(bars) <= MAX_BARS:
        raise LabInputError("2..10000 historical bars required")
    result = []
    previous = None
    for bar in bars:
        if not isinstance(bar, dict):
            raise LabInputError("invalid bar")
        ts = bar.get("ts")
        if type(ts) not in (int, float) or not isfinite(ts) or ts <= 0:
            raise LabInputError("invalid timestamp")
        if previous is not None and ts <= previous:
            raise LabInputError("bars must be strictly chronological")
        previous = ts
        op, hi, lo, cl = (decimal(bar.get(k)) for k in ("open", "high", "low", "close"))
        if lo > min(op, cl) or hi < max(op, cl) or lo > hi:
            raise LabInputError("OHLC inconsistency")
        result.append((int(ts), op, hi, lo, cl))
    return result


def backtest(bars, *, fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS):
    """Research-only next-open momentum reversal with stop/take on NEXT bars.

    No look-ahead: signal at bar i close; all fills at bar i+1 open.
    Intrabar stop/take touches cannot be assigned an exact fill timestamp, so
    this conservative model only checks prior close and exits on NEXT open.
    """
    parsed = candles_checked(bars)
    fee = decimal(fee_bps, allow_zero=True) / Decimal("10000")
    slip = decimal(slippage_bps, allow_zero=True) / Decimal("10000")
    if fee > Decimal("0.02") or slip > Decimal("0.10"):
        raise LabInputError("unrealistic costs")
    cash = CASH
    tokens = Decimal("0")
    entry_price = Decimal("0")
    entry_total = Decimal("0")
    trades = []
    equity = []
    pending = None
    for i, (ts, op, hi, lo, cl) in enumerate(parsed):
        if pending == "BUY" and tokens == 0 and cash >= ENTRY_BUDGET_USDT:
            spent = ENTRY_BUDGET_USDT
            actual_price = op * (1 + slip)
            qty = spent / (actual_price * (1 + fee))
            cash -= spent
            tokens, entry_price, entry_total = qty, actual_price, spent
            trades.append({"side": "BUY", "ts": ts, "cost_usdt": str(spent),
                           "price_usdt": str(actual_price), "source": "NEXT_OPEN"})
        elif pending == "SELL" and tokens > 0:
            actual_price = op * (1 - slip)
            proceeds = tokens * actual_price * (1 - fee)
            cash += proceeds
            trades.append({"side": "SELL", "ts": ts,
                           "net_usdt": str((proceeds - entry_total).quantize(Decimal("0.000001"))),
                           "price_usdt": str(actual_price), "source": "NEXT_OPEN"})
            tokens = Decimal("0")
            entry_price = Decimal("0")
            entry_total = Decimal("0")
        pending = None
        if i >= LOOKBACK and i + 1 < len(parsed):
            closes = [bar[4] for bar in parsed[i-LOOKBACK:i]]
            baseline = sum(closes) / Decimal(len(closes))
            if tokens == 0 and cl > baseline * Decimal("1.02"):
                pending = "BUY"
            if tokens > 0 and (cl <= entry_price * (1 - STOP_PCT) or
                               cl >= entry_price * (1 + TAKE_PCT) or
                               cl < baseline):
                pending = "SELL"
        # Mark-to-market only, not an actual executable exit quote.
        e = cash + tokens * cl
        equity.append({"ts": ts, "equity": str(e.quantize(Decimal("0.000001")))})
    closing_value = cash + tokens * parsed[-1][4]
    return {
        "schema_version": 1, "mode": "HISTORICAL_PAPER_ONLY",
        "real_order": False, "read_only": True,
        "initial_usdt": "100",
        "final_mark_usdt": str(closing_value.quantize(Decimal("0.000001"))),
        "unrealized_positions": int(tokens > 0),
        "trades": trades[-100:],
        "equity": equity,
        "assumptions": {
            "fee_bps": str(fee_bps), "slippage_bps": str(slippage_bps),
            "signal": "close momentum > prev5 average +2%",
            "fill": "next bar OPEN, not future candle high/low",
            "unrealized_not_realizable": True,
            "network_gas_included": False,
            "liquidity_verified": False,
        },
        "warning": "Synthetic historical illustration; NOT executable trade proof",
    }


def rank_candidates(rows):
    """Ranking, not a buy instruction. All required evidence must be supplied."""
    if not isinstance(rows, list) or len(rows) > 100:
        raise LabInputError("invalid candidate batch")
    output = []
    for row in rows:
        if not isinstance(row, dict) or not valid_address(row.get("mint")):
            continue
        evidences = ("mint_checked", "sell_route_checked", "liquidity_checked",
                     "holders_checked", "quote_fresh")
        complete = all(row.get(x) is True for x in evidences)
        blocked = row.get("danger_flag") is True
        components = []
        for key in ("liquidity_score", "wallet_score", "momentum_score",
                    "risk_score"):
            x = row.get(key)
            if type(x) not in (int, float) or not isfinite(x) or not 0 <= x <= 100:
                complete = False
                components.append(0)
            else:
                components.append(int(x))
        score = (components[0] * 30 + components[1] * 25 +
                 components[2] * 20 + components[3] * 25) // 100
        output.append({
            "mint": row["mint"][:64], "score": score if complete and not blocked else None,
            "status": "RESEARCH_ONLY" if complete and not blocked else "INSUFFICIENT_EVIDENCE",
            "real_order": False,
            "why": "EVIDENCE_COMPLETE_NOT_A_BUY" if complete and not blocked
                   else "MISSING_OR_RISKY",
        })
    output.sort(key=lambda x: x["score"] if x["score"] is not None else -1, reverse=True)
    return output
