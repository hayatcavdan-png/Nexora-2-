"""Opt-in READ-ONLY Jupiter recent -> Helius mint -> two-way quote research.

No wallet, private key, transaction, database writes, order placement or
Telegram message contents. Live calls occur ONLY through explicitly enabled
operators. Separate from 100 USDT offline fixture paper ledger.

Jupiter /tokens/v2/recent is RECENT FIRST POOL, not proof of new mint.
Jupiter /swap/v2/order omits taker: quotes only (transaction null).
Prices are estimates, not executions; missing evidence always blocks.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import os
import threading
import time

from nexora.token_safety import evaluate as mint_safety, TOKEN_2022
from .events import valid_address

USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
USDT_DECIMALS = 6
BUY_USDT_RAW = 4_000_000
MIN_LIQUIDITY_USD = Decimal("10000")
MAX_PRICE_IMPACT_PCT = Decimal("3")
MAX_ROUNDTRIP_LOSS_PCT = Decimal("12")
MAX_TOP_HOLDERS_PCT = Decimal("40")
MAX_DEV_BALANCE_PCT = Decimal("20")
MAX_CANDIDATES_PER_REQUEST = 3
API_RECENT = "https://api.jup.ag/tokens/v2/recent"
STATUS_MODE = "READ_ONLY_RESEARCH"
_MIN_REQUEST_SPACING_SECONDS = 45

_lock = threading.Lock()
_last_request = 0.0


def _num(raw, *, zero=True):
    """Accept strictly finite numeric API values with no exponent explosions."""
    if type(raw) not in (int, float, str):
        return None
    if isinstance(raw, str) and (not raw or len(raw) > 48):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() and (value >= 0 if zero else value > 0) else None


def _deny(mint, reason, *, meta=None):
    out = dict(
        mint=mint if valid_address(mint) else None, status="BLOCKED", reason=reason,
        mode=STATUS_MODE, real_order=False, social_ai_transfer=False,
        paper_entry=False, quote_only=True,
    )
    if isinstance(meta, dict):
        out.update(symbol=meta.get("symbol") if isinstance(meta.get("symbol"), str) else None,
                   name=meta.get("name") if isinstance(meta.get("name"), str) else None)
    return out


def parse_recent(rows, *, max_candidates=MAX_CANDIDATES_PER_REQUEST):
    """Candidate MINTS only; do not accept any text or Social AI payload."""
    if not isinstance(rows, list):
        raise ValueError("recent list invalid")
    limit = min(MAX_CANDIDATES_PER_REQUEST, max(0, int(max_candidates)))
    found = []
    seen = set()
    for row in rows[:150]:
        if not isinstance(row, dict):
            continue
        mint = row.get("id")
        if not valid_address(mint) or mint == USDT_MINT or mint in seen:
            continue
        seen.add(mint)
        # Never interpret symbols or free text as mint addresses.
        found.append({
            "id": mint,
            "symbol": row.get("symbol") if isinstance(row.get("symbol"), str) else None,
            "name": row.get("name") if isinstance(row.get("name"), str) else None,
            "liquidity": row.get("liquidity"),
            "audit": row.get("audit"),
            "organicScore": row.get("organicScore"),
            "isVerified": row.get("isVerified"),
            "firstPool": row.get("firstPool"),
        })
        if len(found) == limit:
            break
    return found


def _safe_mint_rpc(value):
    if not isinstance(value, dict):
        return "MINT_ACCOUNT_UNKNOWN"
    parsed = value.get("data")
    parsed = parsed.get("parsed") if isinstance(parsed, dict) else None
    if not isinstance(parsed, dict) or parsed.get("type") != "mint":
        return "NOT_A_TOKEN_MINT"
    info = parsed.get("info")
    if not isinstance(info, dict) or info.get("isInitialized") is not True:
        return "MINT_UNINITIALIZED"
    decimals = info.get("decimals")
    if type(decimals) is not int or not 0 <= decimals <= 18:
        return "TOKEN_DECIMALS_UNKNOWN"
    for key in ("mintAuthority", "freezeAuthority"):
        if key not in info or (info[key] is not None and not valid_address(info[key])):
            return "TOKEN_AUTHORITY_UNKNOWN"
    if value.get("owner") == TOKEN_2022:
        exts = info.get("extensions")
        if not isinstance(exts, list) or not all(
            isinstance(x, dict) and isinstance(x.get("extension"), str) for x in exts
        ):
            return "TOKEN_2022_EXTENSIONS_UNKNOWN"
    result = mint_safety(value)
    if result.get("verdict") != "UYGUN":
        return "TOKEN_UNSAFE_OR_UNKNOWN"
    return None


def _market_gate(row):
    if not isinstance(row, dict) or row.get("id") is None:
        return "MARKET_PROFILE_MISSING"
    liquidity = _num(row.get("liquidity"), zero=False)
    if liquidity is None:
        return "LIQUIDITY_UNKNOWN"
    if liquidity < MIN_LIQUIDITY_USD:
        return "LIQUIDITY_LOW"
    audit = row.get("audit")
    if not isinstance(audit, dict):
        return "AUDIT_UNKNOWN"
    if audit.get("isSus") is True:
        return "JUPITER_SUSPICIOUS_FLAG"
    top = _num(audit.get("topHoldersPercentage"))
    dev = _num(audit.get("devBalancePercentage"))
    if top is None or dev is None:
        return "HOLDER_CONCENTRATION_UNKNOWN"
    if top > MAX_TOP_HOLDERS_PCT or dev > MAX_DEV_BALANCE_PCT:
        return "HOLDER_CONCENTRATION_RISK"
    # Organic score is a separate signal, not certification of legitimacy.
    return None


def _quote_value(raw, exact_in):
    if not isinstance(raw, dict):
        return None
    if type(raw.get("in_amount")) is not int or raw["in_amount"] != exact_in:
        return None
    out = raw.get("out_amount")
    if type(out) is not int or not 0 < out < 10 ** 30:
        return None
    impact = _num(raw.get("price_impact_pct"))
    if impact is None or impact > MAX_PRICE_IMPACT_PCT:
        return None
    return out, impact


def analyze(mint, profile, *, rpc_call, quote, measured_at=None):
    """Dependency-injected pure-ish probe. Two quote reads only AFTER risk gates."""
    result = _deny(mint, "UNKNOWN", meta=profile)
    if not valid_address(mint) or mint == USDT_MINT:
        result["reason"] = "MINT_INVALID_OR_STABLE"
        return result
    if not isinstance(profile, dict) or profile.get("id") != mint:
        result["reason"] = "SOURCE_MINT_MISMATCH"
        return result

    # Reject suspicious/unknown profiles before burning Helius credits.
    reason = _market_gate(profile)
    if reason is not None:
        result["reason"] = reason
        return result

    try:
        response = rpc_call("getAccountInfo", [
            mint, {"encoding": "jsonParsed", "commitment": "finalized"}])
        if not isinstance(response, dict):
            raise ValueError("RPC response invalid")
        value = response.get("value")
    except Exception:
        result["reason"] = "HELIUS_UNAVAILABLE"
        return result
    risk = _safe_mint_rpc(value)
    if risk is not None:
        result["reason"] = risk
        return result

    try:
        buy = quote(USDT_MINT, mint, BUY_USDT_RAW)
        first = _quote_value(buy, BUY_USDT_RAW)
        if first is None:
            result["reason"] = "BUY_QUOTE_UNKNOWN_OR_UNSAFE"
            return result
        raw_tokens, buy_impact = first
        sell = quote(mint, USDT_MINT, raw_tokens)
        second = _quote_value(sell, raw_tokens)
        if second is None:
            result["reason"] = "SELL_ROUTE_UNKNOWN_OR_UNSAFE"
            return result
        raw_usdt_back, sell_impact = second
    except Exception:
        result["reason"] = "JUPITER_QUOTE_UNAVAILABLE"
        return result

    roundtrip_loss = (Decimal(BUY_USDT_RAW - raw_usdt_back) /
                      Decimal(BUY_USDT_RAW) * 100)
    if roundtrip_loss > MAX_ROUNDTRIP_LOSS_PCT:
        result["reason"] = "ROUNDTRIP_LOSS_TOO_HIGH"
        return result
    # Quote-only estimate (no taker); network SOL fees and future price unknown.
    result.update(
        status="RESEARCH_CANDIDATE", reason="MINT_AND_TWO_WAY_ROUTE_OBSERVED",
        observed_at=measured_at,
        liquidity_usd=str(_num(profile.get("liquidity"))),
        buy_in_usdt="4",
        expected_token_qty_raw=str(raw_tokens),
        immediate_sell_quote_usdt=str(Decimal(raw_usdt_back) / 10 ** USDT_DECIMALS),
        quote_roundtrip_pct=str(round(roundtrip_loss, 4)),
        buy_price_impact_pct=str(buy_impact),
        sell_price_impact_pct=str(sell_impact),
        costs_complete=False, paper_entry=False,
    )
    return result


def _get_recent(session, key):
    if not isinstance(key, str) or not key:
        raise ValueError("JUPITER_API_KEY required")
    try:
        response = session.get(API_RECENT, headers={"x-api-key": key},
                               timeout=8, allow_redirects=False)
    except Exception as exc:
        raise RuntimeError("JUPITER_RECENT_UNAVAILABLE") from exc
    if response.status_code == 429:
        raise RuntimeError("JUPITER_RATE_LIMIT")
    if response.status_code != 200:
        raise RuntimeError("JUPITER_RECENT_UNAVAILABLE")
    if len(response.content) > 1_000_000:
        raise ValueError("recent response too large")
    rows = response.json()
    return parse_recent(rows)


def _admission(now_monotonic):
    global _last_request
    with _lock:
        if now_monotonic - _last_request < _MIN_REQUEST_SPACING_SECONDS:
            return False
        _last_request = now_monotonic
    return True


def research_recent(*, enabled=False, limit=3, rpc=None, quoter=None,
                    session=None, api_key=None, clock=None):
    """One bounded on-demand scan. NO daemon, scraping or background jobs."""
    if enabled is not True:
        return dict(mode=STATUS_MODE, status="DISABLED", results=[],
                    read_only=True, real_order=False, social_ai_transfer=False)
    if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES_PER_REQUEST:
        raise ValueError("invalid limit")
    import requests
    from nexora.helius_client import HeliusClient
    from nexora.market import JupiterQuoter

    key = api_key if api_key is not None else os.getenv("JUPITER_API_KEY", "")
    if not key:
        return dict(mode=STATUS_MODE, status="JUPITER_KEY_MISSING", results=[],
                    read_only=True, real_order=False, social_ai_transfer=False)
    if rpc is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        return dict(mode=STATUS_MODE, status="HELIUS_KEY_MISSING", results=[],
                    read_only=True, real_order=False, social_ai_transfer=False)
    if not _admission(time.monotonic()):
        return dict(mode=STATUS_MODE, status="RATE_LIMITED", results=[],
                    read_only=True, real_order=False, social_ai_transfer=False)

    local_rpc = rpc is None
    session = session or requests.Session()
    rpc = rpc if rpc is not None else HeliusClient(max_retries=0, timeout=8)
    quoter = quoter if quoter is not None else JupiterQuoter(api_key=key, timeout=8)
    now = clock if clock is not None else time.time
    results, error = [], None
    try:
        rows = _get_recent(session, key)[:limit]
        for row in rows:
            measured_at = now()
            results.append(analyze(
                row["id"], row, rpc_call=rpc.call, quote=quoter.quote,
                measured_at=measured_at))
    except Exception as exc:
        error = type(exc).__name__
    finally:
        if local_rpc:
            rpc.close()
    status = "OK" if error is None else "PROVIDER_UNAVAILABLE"
    return dict(
        schema_version=1, mode=STATUS_MODE, status=status, results=results,
        provider_error=error, read_only=True, real_order=False,
        social_ai_transfer=False, paper_position_opened=False,
        source="JUPITER_RECENT_FIRST_POOL_NOT_MINT_BIRTH",
    )
