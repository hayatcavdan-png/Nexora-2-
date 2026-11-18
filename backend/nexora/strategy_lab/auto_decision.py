"""NEXORA Strategy Lab opt-in automatic PAPER decision gates.

Two separate decisions: vetted Jupiter/Helius quote -> paper entry, and
fresh Jupiter exit quote -> hypothetical stop/take/time signal. Neither sends
a transaction or changes a real order. Missing proof FAILS CLOSED.
VectorBT/QuantStats results must never be treated as live fill evidence.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite

from nexora.social_ai.events import valid_address
from nexora.constants import USDC_MINT
from nexora.social_ai.recent_research import USDT_MINT

PAPER_USDT = Decimal("4")
MIN_LIQUIDITY = Decimal("20000")
MAX_ROUNDTRIP_PCT = Decimal("8")
MAX_IMPACT_PCT = Decimal("2")
MAX_SIGNAL_AGE_S = 30
STOP_LOSS_PCT = Decimal("-8")
TAKE_PROFIT_PCT = Decimal("16")
MAX_HOLD_SECONDS = 3600
EXIT_SLIPPAGE_BPS = Decimal("100")
EXIT_FEE_USDT = Decimal("0.04")
USDT_MULTIPLIER = Decimal("1000000")


def _decimal(value):
    if type(value) not in (str, int, float, Decimal):
        return None
    if isinstance(value, str) and len(value) > 64:
        return None
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return number if number.is_finite() else None


def _fresh(stamp, now, max_age):
    if type(now) not in (int, float) or type(stamp) not in (int, float):
        return False
    return (isfinite(now) and isfinite(stamp) and
            0 < stamp <= now <= stamp + max_age)


def _decision(action, reason, *, score=None, roi_pct=None):
    result = {
        "schema_version": 1,
        "mode": "STRATEGY_LAB_PAPER_SIGNALS",
        "action": action,
        "reason": reason,
        "real_order": False,
        "signer_used": False,
        "estimated_not_executed": True,
    }
    if score is not None:
        result["screening_score_not_win_probability"] = score
    if roi_pct is not None:
        result["hypothetical_net_return_pct"] = str(roi_pct.quantize(Decimal("0.001")))
    return result


def entry_signal(research, *, now):
    """Require fresh confirmed quote-only proof before any 4 USDT paper study.

    This deliberately does NOT use a historical Sharpe, chart line, pool
    count, social hype or backtest score as a replacement for market evidence.
    """
    if not isinstance(research, dict):
        return _decision("SKIP", "PROOF_MISSING")
    for name, value in {
        "mode": "READ_ONLY_RESEARCH",
        "status": "RESEARCH_CANDIDATE",
        "real_order": False,
        "quote_only": True,
        "paper_entry": False,
        "social_ai_transfer": False,
    }.items():
        actual = research.get(name)
        mismatch = (type(actual) is not bool or actual is not value) if type(value) is bool else actual != value
        if mismatch:
            return _decision("SKIP", "PROOF_MISSING")
    mint = research.get("mint")
    if not valid_address(mint) or mint in (
        USDT_MINT, USDC_MINT, "So11111111111111111111111111111111111111112"
    ):
        return _decision("SKIP", "MINT_INVALID")
    if not _fresh(research.get("observed_at"), now, MAX_SIGNAL_AGE_S):
        return _decision("SKIP", "QUOTE_STALE")
    if _decimal(research.get("buy_in_usdt")) != PAPER_USDT:
        return _decision("SKIP", "ENTRY_BUDGET_MISMATCH")
    qty = research.get("expected_token_qty_raw")
    if not isinstance(qty, str) or not qty.isdigit() or len(qty) > 30 or not 0 < int(qty) < 10**30:
        return _decision("SKIP", "QUANTITY_MISSING")
    liquidity = _decimal(research.get("liquidity_usd"))
    roundtrip = _decimal(research.get("quote_roundtrip_pct"))
    buy_impact = _decimal(research.get("buy_price_impact_pct"))
    sell_impact = _decimal(research.get("sell_price_impact_pct"))
    back_quote = _decimal(research.get("immediate_sell_quote_usdt"))
    if any(x is None for x in (liquidity, roundtrip, buy_impact, sell_impact, back_quote)):
        return _decision("SKIP", "QUOTE_EVIDENCE_INCOMPLETE")
    if liquidity < MIN_LIQUIDITY:
        return _decision("SKIP", "LIQUIDITY_TOO_LOW")
    if not (Decimal("0") <= roundtrip <= MAX_ROUNDTRIP_PCT):
        return _decision("SKIP", "ROUNDTRIP_COST_TOO_HIGH_OR_INCONSISTENT")
    if not all(Decimal("0") <= impact <= MAX_IMPACT_PCT for impact in (buy_impact, sell_impact)):
        return _decision("SKIP", "PRICE_IMPACT_TOO_HIGH")
    implied_sell = PAPER_USDT * (Decimal("1") - roundtrip / Decimal("100"))
    if not Decimal("0") < back_quote <= PAPER_USDT or abs(back_quote - implied_sell) > Decimal("0.05"):
        return _decision("SKIP", "SELL_QUOTE_INCONSISTENT")
    # Descriptive quality ordering only; *not* a predicted return probability.
    liq_points = min(25, int(25 * liquidity / Decimal("100000")))
    rt_points = max(0, int(35 * (1 - roundtrip / MAX_ROUNDTRIP_PCT)))
    impact_points = max(0, int(40 * (1 - max(buy_impact, sell_impact) / MAX_IMPACT_PCT)))
    return _decision("OPEN_PAPER_STUDY", "RISK_SCREEN_PASSED",
                     score=liq_points + rt_points + impact_points)


def exit_signal(position, quote, *, observed_at, now):
    """Independent quote-only stop/take/timeout advice, NOT an executed sale.

    If Jupiter cannot quote the full token amount, return EXIT_UNAVAILABLE,
    never pretend a stop-loss filled. Called on each actual observed horizon.
    """
    if not isinstance(position, dict):
        return _decision("HOLD", "POSITION_MISSING")
    if not _fresh(observed_at, now, MAX_SIGNAL_AGE_S):
        return _decision("HOLD", "QUOTE_STALE")
    start = position.get("observed_at")
    if type(start) not in (int, float) or not isfinite(start) or start > now:
        return _decision("HOLD", "ENTRY_TIME_INVALID")
    qty = position.get("token_qty_raw")
    cost = _decimal(position.get("reserved_cost_usdt"))
    if not isinstance(qty, str) or not qty.isdigit() or len(qty) > 30 or not 0 < int(qty) < 10**30:
        return _decision("HOLD", "POSITION_QUANTITY_INVALID")
    if cost is None or cost <= 0:
        return _decision("HOLD", "ENTRY_COST_INVALID")
    if not isinstance(quote, dict) or type(quote.get("in_amount")) is not int or quote["in_amount"] != int(qty):
        return _decision("EXIT_UNAVAILABLE", "SELL_ROUTE_UNAVAILABLE")
    raw = quote.get("out_amount")
    impact = _decimal(quote.get("price_impact_pct"))
    if type(raw) is not int or not 0 < raw < 10**30 or impact is None or not Decimal("0") <= impact <= MAX_IMPACT_PCT:
        return _decision("EXIT_UNAVAILABLE", "SELL_QUOTE_UNSAFE")
    expected_usdt = Decimal(raw) / USDT_MULTIPLIER
    net = expected_usdt * (Decimal("1") - EXIT_SLIPPAGE_BPS / Decimal("10000")) - EXIT_FEE_USDT
    net_pct = (net - cost) / cost * 100
    if net_pct <= STOP_LOSS_PCT:
        return _decision("PAPER_SELL_SIGNAL", "STOP_LOSS", roi_pct=net_pct)
    if net_pct >= TAKE_PROFIT_PCT:
        return _decision("PAPER_SELL_SIGNAL", "TAKE_PROFIT", roi_pct=net_pct)
    if now - start >= MAX_HOLD_SECONDS:
        return _decision("PAPER_SELL_SIGNAL", "TIME_LIMIT", roi_pct=net_pct)
    return _decision("HOLD", "WITHIN_LIMITS", roi_pct=net_pct)
