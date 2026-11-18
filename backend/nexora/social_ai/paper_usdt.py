"""NEXORA manual/licensed-source USDT paper prototype (OFFLINE ONLY).

No network, Telegram content, database, private keys or order execution.
The caller supplies time-stamped provider evidence, which is NOT automatically
authenticated by this module. Fixtures and offline results are never LIVE proof.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import sys

from nexora.token_safety import evaluate as token_safety
from .events import valid_address

HORIZONS = (5, 15, 30, 60)
INITIAL_CASH_USDT = Decimal("100")
MAX_ENTRY_USDT = Decimal("5")
MIN_LIQUIDITY_USDT = Decimal("10000")
MAX_QUOTE_AGE = 120
MAX_SLIPPAGE_BPS = Decimal("300")
MAX_IMPACT_BPS = Decimal("300")


def _amount(value, *, zero=False):
    """Reject floats, exponents, negatives, NaN, infinite and malformed amounts."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    raw = str(value)
    if len(raw) > 32 or not raw or "e" in raw.lower():
        return None
    try:
        out = Decimal(raw)
    except InvalidOperation:
        return None
    if not out.is_finite() or (out < 0 if zero else out <= 0):
        return None
    return out


def _timestamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _sample(row, now, *, lower=0, max_age=MAX_QUOTE_AGE):
    if not isinstance(row, dict):
        return False
    observed = _timestamp(row.get("measured_at"))
    fetched = _timestamp(row.get("fetched_at"))
    return (
        observed is not None and fetched is not None
        and lower <= observed <= fetched <= now
        and now - observed <= max_age
    )


def _quote(row, mint, now, *, side, lower=0, max_age=MAX_QUOTE_AGE):
    if not _sample(row, now, lower=lower, max_age=max_age):
        return None
    if row.get("executable") is not True or row.get("side") != side:
        return None
    if row.get("mint") != mint or row.get("quote_asset") != "USDT":
        return None
    if _amount(row.get("slippage_bps"), zero=True) is None or _amount(
        row.get("price_impact_bps"), zero=True
    ) is None:
        return None
    if _amount(row["slippage_bps"], zero=True) > MAX_SLIPPAGE_BPS or _amount(
        row["price_impact_bps"], zero=True
    ) > MAX_IMPACT_BPS:
        return None
    fee = _amount(row.get("network_fee_usdt"), zero=True)
    dex = _amount(row.get("dex_fee_usdt"), zero=True)
    if fee is None or dex is None:
        return None
    if side == "buy":
        paid = _amount(row.get("input_usdt"))
        qty = _amount(row.get("token_qty"))
        if paid is None or qty is None:
            return None
        return paid, qty, fee + dex
    qty = _amount(row.get("token_qty"))
    received = _amount(row.get("output_usdt"))
    if qty is None or received is None:
        return None
    return received, qty, fee + dex


def simulate(candidate, *, now):
    """Review a candidate and hypothetical 5/15/30/60 minute quotes.

    The input is untrusted OFFLINE EVIDENCE. A returned PAPER_ELIGIBLE is a
    *fixture-level* verdict, never a verified live purchase recommendation.
    """
    now = _timestamp(now)
    if now is None:
        raise ValueError("now must be a positive finite timestamp")
    result = {
        "mode": "OFFLINE_PAPER_ONLY",
        "currency": "USDT",
        "initial_cash_usdt": str(INITIAL_CASH_USDT),
        "status": "BLOCKED",
        "reason": "UNKNOWN",
        "mint": None,
        "entry": None,
        "horizons": {
            f"{m}dk": {"status": "UNKNOWN", "net_usdt": None} for m in HORIZONS
        },
        "real_order": False,
        "social_ai_transfer": False,
    }
    if not isinstance(candidate, dict):
        result["reason"] = "CANDIDATE_INVALID"
        return result

    # No Telegram message content, post metadata or channel notifications as
    # an input source for a token identification/AI decision.
    if candidate.get("source") not in ("manual_mint", "licensed_feed"):
        result["reason"] = "SOURCE_NOT_AUTHORIZED"
        return result
    if candidate["source"] == "licensed_feed" and (
        candidate.get("permission_verified") is not True
        or not isinstance(candidate.get("license_id"), str)
        or not candidate.get("license_id").strip()
    ):
        result["reason"] = "SOURCE_PERMISSION_MISSING"
        return result

    mint = candidate.get("mint")
    if not valid_address(mint):
        result["reason"] = "MINT_INVALID"
        return result
    result["mint"] = mint
    observed = _timestamp(candidate.get("observed_at"))
    if observed is None or observed > now or now - observed > MAX_QUOTE_AGE:
        result["reason"] = "EVENT_STALE"
        return result
    account = candidate.get("account")
    if not _sample(account, now):
        result["reason"] = "ACCOUNT_PROOF_MISSING_OR_STALE"
        return result
    rpc = account.get("value")
    if not isinstance(rpc, dict):
        result["reason"] = "MINT_ACCOUNT_UNKNOWN"
        return result
    parsed = rpc.get("data", {}).get("parsed") if isinstance(rpc.get("data"), dict) else None
    if not isinstance(parsed, dict) or parsed.get("type") != "mint":
        result["reason"] = "NOT_A_MINT_ACCOUNT"
        return result
    info = parsed.get("info")
    if not isinstance(info, dict) or info.get("isInitialized") is not True:
        result["reason"] = "NOT_INITIALIZED"
        return result
    verdict = token_safety(rpc)
    if verdict["verdict"] != "UYGUN":
        result["reason"] = "MINT_RISK_OR_UNKNOWN"
        result["mint_safety"] = verdict["verdict"]
        return result
    liquidity = candidate.get("liquidity")
    if not _sample(liquidity, now):
        result["reason"] = "LIQUIDITY_UNKNOWN"
        return result
    amount = _amount(liquidity.get("total_usdt"))
    if amount is None or amount < MIN_LIQUIDITY_USDT or liquidity.get("verified") is not True:
        result["reason"] = "LIQUIDITY_INSUFFICIENT_OR_UNVERIFIED"
        return result

    buy = candidate.get("buy_quote")
    entry = _quote(buy, mint, now, side="buy")
    if entry is None:
        result["reason"] = "ENTRY_QUOTE_UNKNOWN"
        return result
    paid, qty, fees = entry
    total = paid + fees
    if total > MAX_ENTRY_USDT or total > INITIAL_CASH_USDT:
        result["reason"] = "BUDGET_EXCEEDED"
        return result
    result["status"] = "PAPER_ELIGIBLE"
    result["reason"] = "OFFLINE_EVIDENCE_PASSED"
    result["entry"] = {
        "input_usdt": str(paid),
        "fees_usdt": str(fees),
        "total_cost_usdt": str(total),
        "token_qty": str(qty),
        "remaining_cash_usdt": str(INITIAL_CASH_USDT - total),
    }
    exits = candidate.get("sell_quotes", {})
    if not isinstance(exits, dict):
        exits = {}

    # A quote is usable only when it was measured no earlier than its horizon.
    # No future quote is allowed to leak into past paper decisions.
    for m in HORIZONS:
        key = f"{m}dk"
        due = observed + m * 60
        if now < due:
            result["horizons"][key] = {"status": "PENDING", "net_usdt": None}
            continue
        row = exits.get(key)
        exit_ = _quote(row, mint, now, side="sell", lower=due, max_age=max(MAX_QUOTE_AGE, now - due + 1))
        if exit_ is None or exit_[1] != qty:
            result["horizons"][key] = {"status": "UNKNOWN", "net_usdt": None}
            continue
        value, _, exit_fees = exit_
        net = value - exit_fees - total
        result["horizons"][key] = {
            "status": "OK",
            "net_usdt": str(net.quantize(Decimal("0.000001"))),
        }
    return result


def main(argv=None):
    """CLI for *user-owned/synthetic fixture* only, never from Telegram."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    args = parser.parse_args(argv)
    path = Path(args.fixture)
    if not path.is_file() or path.stat().st_size > 200_000:
        parser.error("fixture missing or too large")
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(simulate(payload["candidate"], now=payload["now"]),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
