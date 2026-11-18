"""Quote-only, walk-forward profit research and capital-preservation gate.

Not a predictor or execution engine. All four horizons are counterfactual
Jupiter quotes for the SAME proposed entry, not four trades.
A horizon is chosen using ONLY records fully mature before the new
candidate was observed. A missing exit quote is treated as a full-cost
loss in the explicit STRESS scenario; it is NOT claimed as an actual loss.
"""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import mean, pstdev
from decimal import Decimal, InvalidOperation

HORIZONS = (5, 15, 30, 60)
QUOTE_GRACE_S = 120
MATURITY_S = HORIZONS[-1] * 60 + QUOTE_GRACE_S
MIN_TRAIN = 30
MIN_COVERAGE = 0.90
CONFIDENCE_Z = 1.64
INITIAL_EQUITY = 100.0
MAX_RECORDS = 1000
MIN_VALIDATION_TRADES = 20


class ProfitEvidenceError(ValueError):
    pass


def _finite_number(value):
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


def _money(value):
    if type(value) not in (str, int, float, Decimal):
        return None
    if isinstance(value, str) and len(value) > 64:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return float(number) if number.is_finite() and abs(number) <= 1000 else None


def _observed_net(row, minutes, *, as_of):
    """A usable quote needs both a finite net and timely measurement proof."""
    histories = row["raw"].get("horizons")
    if not isinstance(histories, dict):
        return None
    horizon = histories.get(f"{minutes}dk")
    if not isinstance(horizon, dict) or horizon.get("status") != "OK":
        return None
    timestamp = _finite_number(horizon.get("measured_at"))
    start = row["ts"] + minutes * 60
    if timestamp is None or timestamp < start or timestamp > start + QUOTE_GRACE_S or timestamp > as_of:
        return None
    net = _money(horizon.get("net_usdt"))
    if net is None or net < -row["cost"] or net > 1000:
        return None
    return net


def _stress_net(row, minutes, *, as_of):
    net = _observed_net(row, minutes, as_of=as_of)
    if net is None:
        return -row["cost"]
    # A rare huge memecoin spike cannot single-handedly certify an edge.
    return min(net, row["cost"] * 2.0)


def _samples(state, as_of):
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ProfitEvidenceError("INVALID_SCHEMA")
    if (state.get("mode") != "QUOTE_PAPER_RESEARCH" or
            state.get("real_order") is not False or
            state.get("social_ai_transfer") is not False):
        raise ProfitEvidenceError("UNSAFE_MODE")
    records = state.get("entries")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ProfitEvidenceError("INVALID_RECORD_COUNT")
    matured = []
    for record in records:
        if not isinstance(record, dict):
            raise ProfitEvidenceError("INVALID_RECORD")
        ts = _finite_number(record.get("observed_at"))
        cost = _money(record.get("reserved_cost_usdt"))
        if ts is None or cost is None or cost <= 0 or cost > 5.0:
            raise ProfitEvidenceError("INVALID_COST_OR_TIME")
        if not isinstance(record.get("horizons"), dict):
            raise ProfitEvidenceError("INVALID_HORIZONS")
        if ts + MATURITY_S > as_of:
            continue
        matured.append({"ts": ts, "cost": cost, "raw": record})
    matured.sort(key=lambda record: record["ts"])
    return matured


def _horizon_stats(rows, minutes, *, as_of):
    n = len(rows)
    if not n:
        return {
            "horizon_minutes": minutes, "samples": 0,
            "quotes_available": 0, "coverage": 0.0,
            "observed_average_net_usdt": None,
            "stress_average_net_usdt": None, "stress_lower_bound_usdt": None,
            "stress_total_net_usdt": 0.0, "eligible": False,
        }
    quoted = [_observed_net(row, minutes, as_of=as_of) for row in rows]
    valid = [x for x in quoted if x is not None]
    stress = [_stress_net(row, minutes, as_of=as_of) for row in rows]
    avg = mean(stress)
    lower = avg - CONFIDENCE_Z * (pstdev(stress) / sqrt(n)) if n > 1 else float("-inf")
    coverage = len(valid) / n
    return {
        "horizon_minutes": minutes,
        "samples": n,
        "quotes_available": len(valid),
        "coverage": round(coverage, 4),
        "observed_average_net_usdt": round(mean(valid), 6) if valid else None,
        "stress_average_net_usdt": round(avg, 6),
        "stress_lower_bound_usdt": round(lower, 6) if isfinite(lower) else None,
        "stress_total_net_usdt": round(sum(stress), 6),
        "eligible": (n >= MIN_TRAIN and coverage >= MIN_COVERAGE and lower > 0.0),
    }


def _choose(rows, *, as_of):
    scores = [_horizon_stats(rows, horizon, as_of=as_of) for horizon in HORIZONS]
    accepted = [row for row in scores if row["eligible"]]
    if not accepted:
        return None, scores
    # Highest conservative lower bound; equal quality favors a shorter hold.
    best = max(accepted, key=lambda row: (row["stress_lower_bound_usdt"],
                                          -row["horizon_minutes"]))
    return best["horizon_minutes"], scores


def _walk_forward(rows, *, as_of):
    """Each study is evaluated using a horizon selected before its entry time.

    Fully mature observations may enter training only after the last quote
    window. No per-token oracle selecting the best of four exit outcomes.
    Results are per-signal stress approximations, not a concurrent portfolio.
    """
    chosen = 0
    observed = 0
    stressed = 0.0
    wins = 0
    equity = peak = INITIAL_EQUITY
    max_dd = 0.0
    for i, item in enumerate(rows):
        training = [
            older for older in rows[:i]
            if older["ts"] + MATURITY_S <= item["ts"]
        ]
        choice, _ = _choose(training, as_of=item["ts"])
        if choice is None:
            continue  # cash baseline, no trade selected at this decision time
        chosen += 1
        outcome = _observed_net(item, choice, as_of=as_of)
        if outcome is not None:
            observed += 1
        pnl = _stress_net(item, choice, as_of=as_of)
        wins += int(pnl > 0)
        stressed += pnl
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 1.0)
    return {
        "selected_paper_studies": chosen,
        "observed_exit_quotes": observed,
        "quote_coverage": round(observed / chosen, 4) if chosen else None,
        "stress_net_usdt": round(stressed, 6),
        "stress_average_net_usdt": round(stressed / chosen, 6) if chosen else None,
        "stress_winning_fraction": round(wins / chosen, 4) if chosen else None,
        "sequential_stress_max_drawdown_pct": round(max_dd * 100, 3),
        "realized_profit": False,
        "simultaneous_exposure_modeled": False,
    }


def review(state, *, as_of):
    """Evaluate a private paper ledger; return aggregates only, no mint or keys."""
    at = _finite_number(as_of)
    if at is None:
        raise ProfitEvidenceError("INVALID_AS_OF")
    try:
        rows = _samples(state, at)
    except ProfitEvidenceError as exc:
        return {
            "schema_version": 1, "mode": "QUOTE_ONLY_PROFIT_RESEARCH",
            "real_order": False, "status": "EVIDENCE_INVALID",
            "reason": str(exc), "mature_samples": 0,
            "recommended_horizon_min": None,
            "intake": {"allow_new_paper": False, "reason": "EVIDENCE_INVALID"},
            "hypothetical_not_execution": True,
        }

    choice, horizons = _choose(rows, as_of=at)
    out = _walk_forward(rows, as_of=at)
    n = len(rows)
    status = "INSUFFICIENT_DATA" if n < MIN_TRAIN else (
        "NO_VALID_EDGE" if choice is None else "EDGE_UNVALIDATED")
    if choice is not None and out["selected_paper_studies"] >= MIN_VALIDATION_TRADES:
        if (out["stress_average_net_usdt"] > 0 and
                out["quote_coverage"] >= MIN_COVERAGE and
                out["sequential_stress_max_drawdown_pct"] <= 10.0):
            status = "PAPER_EDGE_CANDIDATE"
        else:
            status = "FORWARD_STRESS_NOT_PASSED"

    # Precommitted 5-minute safety sentinel (not the hindsight winner).
    # Bad availability or repeated deep losses limit further sampling.
    intake_reason = "RESEARCH_ONLY"
    allow = True
    if n >= MIN_TRAIN:
        recent = rows[-MIN_TRAIN:]
        sentinel = _horizon_stats(recent, HORIZONS[0], as_of=at)
        bad = (sentinel["coverage"] < 0.70 or
               sentinel["stress_average_net_usdt"] < -0.60)
        if (out["selected_paper_studies"] >= MIN_VALIDATION_TRADES and
                out["stress_average_net_usdt"] < -0.20):
            bad = True
        if bad:
            # An immutable historical ledger cannot lock the system forever.
            # Resume cautiously after an hour, at most one paper sample/cycle.
            cooldown_until = rows[-1]["ts"] + MATURITY_S + 3600
            if at < cooldown_until:
                allow = False
                intake_reason = "CIRCUIT_BREAKER_COOLDOWN"
            else:
                intake_reason = "CAUTIOUS_RESEARCH_AFTER_COOLDOWN"
    return {
        "schema_version": 1, "mode": "QUOTE_ONLY_PROFIT_RESEARCH",
        "real_order": False, "status": status,
        "mature_samples": n,
        "recommended_horizon_min": choice,
        "horizons": horizons,
        "forward_stress": out,
        "intake": {"allow_new_paper": allow, "reason": intake_reason},
        "hypothetical_not_execution": True,
        "missing_quotes_stressed_as_full_loss_not_observed_loss": True,
        "large_positive_outliers_capped_for_stress": True,
        "horizon_results_are_alternatives_not_independent_trades": True,
    }
