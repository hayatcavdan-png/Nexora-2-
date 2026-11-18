"""Seven-tool opt-in Strategy Lab integration adapters.

No external packages are required to import this module. All optional heavy
dependencies stay off the existing NEXORA production requirements.
No wallet signing, orders, transfers or production database writes.
"""
from __future__ import annotations

from decimal import Decimal
import asyncio
import importlib.util
import json
import math
from pathlib import Path

from nexora.social_ai.events import valid_address
from .engine import LabInputError, candles_checked


OPTIONAL_MODULES = {
    "vectorbt": "vectorbt",
    "solana_py": "solana",
    "raydium_sdk_v2": None,       # separate Node.js CLI
    "orca_whirlpools": None,      # separate Node.js CLI
    "duckdb": "duckdb",
    "quantstats": "quantstats",
    "lightweight_charts": None,   # bundled Android web asset build
}


def capabilities():
    result = {}
    for key, module in OPTIONAL_MODULES.items():
        if module is None:
            result[key] = {"installed": False, "type": "ISOLATED_OPTIONAL", "used_for_orders": False}
        else:
            result[key] = {
                "installed": importlib.util.find_spec(module) is not None,
                "type": "PYTHON_OPTIONAL", "used_for_orders": False,
            }
    return result


def duckdb_summary(rows):
    """Actual DuckDB in-memory SQL, no attached production SQLite connection."""
    import duckdb  # installed only via optional requirements file
    if not isinstance(rows, list) or len(rows) > 1000:
        raise LabInputError("invalid lab results")
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source")
        if source not in ("raydium", "orca", "jupiter", "manual"):
            continue
        profit = row.get("hypothetical_net_usdt")
        status = row.get("status")
        if type(profit) not in (int, float) or not math.isfinite(profit) or abs(profit) > 1000:
            continue
        if status not in ("OK", "UNKNOWN", "BLOCKED"):
            continue
        values.append((source, status, float(profit)))
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE TABLE results(source VARCHAR, status VARCHAR, net_usdt DOUBLE)")
        if values:
            connection.executemany("INSERT INTO results VALUES (?, ?, ?)", values)
        result = connection.execute("""
            SELECT source, count(*) AS n, avg(net_usdt) AS mean_usdt,
                   min(net_usdt) AS worst_usdt
            FROM results WHERE status = 'OK'
            GROUP BY source ORDER BY source LIMIT 4
        """).fetchall()
    finally:
        connection.close()
    return {
        "mode": "OFFLINE_ANALYTICS_ONLY",
        "read_only_market": True, "real_order": False,
        "sources": [{"source": name, "n": count,
                     "average_hypothetical_usdt": round(mean, 6),
                     "worst_hypothetical_usdt": round(worst, 6)}
                    for name, count, mean, worst in result],
        "evaluated_rows": len(values), "profit_realized": False,
    }


def vectorbt_study(candles):
    """Actual VectorBT 100 USDT synthetic backtest; next-bar OPEN entry only."""
    parsed = candles_checked(candles)
    import pandas as pd
    import vectorbt as vbt

    prices = pd.Series([float(row[1]) for row in parsed])
    past_closes = pd.Series([float(row[4]) for row in parsed])
    signal_at_close = past_closes > past_closes.shift(1).rolling(5).mean() * 1.02
    # Signal observed at previous candle's close, filled at next candle OPEN.
    entries = signal_at_close.shift(1, fill_value=False).astype(bool)
    exits = (~signal_at_close).shift(1, fill_value=False).astype(bool)
    pf = vbt.Portfolio.from_signals(
        prices, entries=entries, exits=exits,
        size=4.0, size_type="value", init_cash=100.0,
        fees=0.002, slippage=0.01, freq="1min", direction="longonly",
    )
    return {
        "mode": "SYNTHETIC_BACKTEST_ONLY", "real_order": False,
        "tools_used": ["vectorbt"],
        "total_return_pct": round(float(pf.total_return() * 100), 6),
        "max_drawdown_pct": round(float(pf.max_drawdown() * 100), 6),
        "final_equity_usdt": round(float(pf.final_value()), 6),
        "trades": int(pf.trades.count()),
        "price_basis": "next bar open",
        "gas_fee_included": False,
        "token_liquidity_proved": False,
    }


def quantstats_summary(equity_points):
    """Actual QuantStats report on caller-owned historical equity observations."""
    if not isinstance(equity_points, list) or not 30 <= len(equity_points) <= 10000:
        raise LabInputError("at least 30 equity points required")
    import pandas as pd
    import quantstats as qs
    stamps, equity = [], []
    prev = 0
    for point in equity_points:
        if not isinstance(point, dict):
            raise LabInputError("invalid equity point")
        ts = point.get("ts")
        if type(ts) is not int or ts <= prev:
            raise LabInputError("chronological timestamps required")
        prev = ts
        val = float(point.get("equity"))
        if not math.isfinite(val) or val <= 0:
            raise LabInputError("invalid equity")
        stamps.append(pd.Timestamp(ts, unit="s", tz="UTC"))
        equity.append(val)
    series = pd.Series(equity, index=pd.DatetimeIndex(stamps), dtype=float)
    returns = series.pct_change().fillna(0.0)
    dd = float(qs.stats.max_drawdown(series))
    daily_return = returns.resample("1D").apply(lambda s: (1+s).prod()-1)
    sharpe = float(qs.stats.sharpe(daily_return, periods=365)) if len(daily_return) >= 30 else None
    return {
        "mode": "HISTORICAL_EQUITY_ONLY", "real_order": False,
        "tools_used": ["quantstats"],
        "max_drawdown_pct": round(dd * 100, 4),
        "daily_sharpe": round(sharpe, 4) if sharpe is not None and math.isfinite(sharpe) else None,
        "sample_bars": len(series), "true_live_alpha_proven": False,
    }


async def solana_py_mint_probe(mint, endpoint, *, client_factory=None):
    """Read-only solana-py getAccountInfo JSON-parsed; no keypair and no Tx API."""
    if not valid_address(mint):
        raise LabInputError("invalid mint")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise LabInputError("HTTPS RPC endpoint required")
    from solders.pubkey import Pubkey
    from solana.rpc.async_api import AsyncClient
    from nexora.social_ai.recent_research import _safe_mint_rpc
    factory = client_factory or (lambda url: AsyncClient(url, timeout=8))
    async with factory(endpoint) as client:
        response = await client.get_account_info_json_parsed(
            Pubkey.from_string(mint), commitment="finalized")
    # Solders response supports to_json; JSON data may be base64 when parser
    # unavailable, and the existing safety gate rejects it.
    obj = json.loads(response.to_json())
    value = (obj.get("result") or {}).get("value")
    verdict = _safe_mint_rpc(value)
    return {
        "schema_version": 1, "mode": "READ_ONLY_MINT_PROBE",
        "mint": mint, "status": "MINT_CHECK_PASSED" if verdict is None else "BLOCKED",
        "reason": verdict or "SPL_MINT_AUTHORITY_GATE_PASSED",
        "real_order": False, "used_sdk": "solana-py",
    }


def sdk_pool_snapshot(data):
    """Strictly normalize SDK CLI JSON. Unverified pools NEVER equal buy approval."""
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise LabInputError("SDK schema invalid")
    if data.get("mode") != "SDK_READ_ONLY" or data.get("real_order") is not False:
        raise LabInputError("SDK mode unsafe")
    rows = data.get("pools")
    if not isinstance(rows, list) or len(rows) > 40:
        raise LabInputError("SDK pool size invalid")
    clean = []
    for row in rows:
        if not isinstance(row, dict) or row.get("source") not in ("raydium", "orca"):
            continue
        mint = row.get("mint")
        pool = row.get("pool_id")
        if not valid_address(mint) or not valid_address(pool):
            continue
        clean.append({
            "source": row["source"], "mint": mint, "pool_id": pool,
            "status": "UNVERIFIED_POOL_OBSERVATION",
            "pool_is_not_token_approval": True, "real_order": False,
        })
    return {"schema_version": 1, "mode": "SDK_READ_ONLY",
            "real_order": False, "pools": clean}


def load_sdk_snapshot(path):
    """Optional small local snapshot created by isolated Node read-only SDKs."""
    if not isinstance(path, str) or not path.endswith(".json"):
        raise LabInputError("operator JSON path required")
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 100000:
        raise LabInputError("snapshot unavailable")
    return sdk_pool_snapshot(json.loads(file.read_text(encoding="utf-8")))
