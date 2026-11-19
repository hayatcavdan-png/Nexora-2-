"""NEXORA: causal, adaptive signal ranking for quote-only paper studies.

A small, explainable kernel-regression ML model learns from features frozen
BEFORE a proposed paper entry, paired with the ONE exit horizon precommitted
at that entry. Each training result must be fully mature. Walk-forward checks
retrain at each old decision timestamp, never on its own future quote.

Not an LLM, oracle, guaranteed win probability or order execution engine.
No provider access, SDK imports, private keys, I/O or writable production DB.
The unmodified Helius/Jupiter and entry_signal risk gates remain authoritative.
"""
from __future__ import annotations

from math import exp, isfinite, sqrt
from statistics import mean, pstdev

from .profit_engine import (
    HORIZONS, MATURITY_S, MAX_RECORDS, _observed_net, _samples,
    ProfitEvidenceError,
)

FEATURES = (
    "liquidity", "roundtrip", "buy_impact", "sell_impact",
    "organic", "holders", "developer",
)
WEIGHTS = (1.0, 2.0, 1.0, 1.0, 0.25, 0.5, 0.5)
MIN_TRAIN = 30
MIN_FORWARD_CHECKED = 20
MIN_FORWARD_SELECTED = 10
MIN_QUOTE_COVERAGE = 0.90
ENTRY_PREDICTION_MIN_USDT = 0.05
STRESS_CEILING_USDT = 8.16


def _finite(value, lo, hi):
    if type(value) not in (int, float, str):
        return None
    if isinstance(value, str) and (not value or len(value) > 32):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not isfinite(number) or not lo <= number <= hi:
        return None
    return number


def entry_features(proof):
    """Seven bounded ex-ante features; unknown optional fields are neutral.

    These features are *descriptive* and do not replace confirmed sellability.
    Caller must first pass entry_signal's strict independent validation.
    """
    if not isinstance(proof, dict):
        return None
    liquidity = _finite(proof.get("liquidity_usd"), 20_000, 10**15)
    roundtrip = _finite(proof.get("quote_roundtrip_pct"), 0, 8)
    buy = _finite(proof.get("buy_price_impact_pct"), 0, 2)
    sell = _finite(proof.get("sell_price_impact_pct"), 0, 2)
    if any(x is None for x in (liquidity, roundtrip, buy, sell)):
        return None
    organic = _finite(proof.get("organic_score"), 0, 100)
    holders = _finite(proof.get("top_holders_pct"), 0, 40)
    developer = _finite(proof.get("dev_balance_pct"), 0, 20)
    return {
        "liquidity": round(min(liquidity / 100_000, 1), 6),
        "roundtrip": round(1 - roundtrip / 8, 6),
        "buy_impact": round(1 - buy / 2, 6),
        "sell_impact": round(1 - sell / 2, 6),
        "organic": round(organic / 100, 6) if organic is not None else 0.5,
        "holders": round(1 - holders / 40, 6) if holders is not None else 0.5,
        "developer": round(1 - developer / 20, 6) if developer is not None else 0.5,
    }


def _valid_features(values):
    if not isinstance(values, dict) or set(values) != set(FEATURES):
        return False
    return all(type(values.get(name)) in (int, float) and
               isfinite(values[name]) and 0 <= values[name] <= 1
               for name in FEATURES)


def _training_samples(state, at):
    """Only mature, precommitted single-exit outcomes are eligible.

    A missing quote is a *full-loss STRESS assumption*, not a realized sale.
    Legacy uncommitted studies cannot be relabeled in hindsight.
    """
    records = _samples(state, at)
    examples = []
    quoted = 0
    for item in records:
        record = item["raw"]
        values = record.get("lab_pretrade_features")
        decided = record.get("plan_decided_at")
        planned = record.get("planned_exit_horizon_min")
        if not _valid_features(values):
            continue
        if type(decided) not in (int, float) or not isfinite(decided):
            continue
        if not item["ts"] <= decided <= item["ts"] + 30:
            continue
        if type(planned) is not int or planned not in HORIZONS:
            continue
        quote = _observed_net(item, planned, as_of=at)
        quoted += (quote is not None)
        result = -item["cost"] if quote is None else min(quote, min(STRESS_CEILING_USDT, item["cost"] * 2))
        examples.append({
            "ts": item["ts"], "features": values, "stress_net": result,
            "quoted": quote is not None, "cost": item["cost"],
        })
    # Stable ordering on timestamp preserves conservative ordering on ties.
    examples.sort(key=lambda r: r["ts"])
    return examples, quoted


def _predict(examples, features):
    """Distance-weighted kernel regression, shrunk to past overall mean.

    This is machine learning from historical examples, not model calibration
    or a claim that the forecast is a probability of winning.
    """
    if len(examples) < MIN_TRAIN or not _valid_features(features):
        return None
    historical = [x["stress_net"] for x in examples]
    prior_mean = mean(historical)
    spread = pstdev(historical)
    weighted_net = 0.0
    weight_total = 0.0
    weight_sum_sq = 0.0
    for item in examples:
        distance = sum(w * abs(item["features"][name] - features[name])
                       for name, w in zip(FEATURES, WEIGHTS)) / sum(WEIGHTS)
        weight = exp(-4.0 * distance)
        weighted_net += weight * item["stress_net"]
        weight_total += weight
        weight_sum_sq += weight * weight
    # Ten virtual prior samples shrink weak neighborhoods back toward the
    # all-history average (instead of chasing one memecoin outlier).
    estimate = (weighted_net + 10 * prior_mean) / (weight_total + 10)
    effective = (weight_total * weight_total / weight_sum_sq) if weight_sum_sq else 0
    # Deliberately conservatively floor uncertainty at a tenth of a USDT.
    lower = estimate - 1.64 * max(spread, 0.1) / sqrt(max(effective, 1))
    return {
        "estimated_stress_net_usdt": round(estimate, 6),
        "conservative_bound_usdt": round(lower, 6),
        "effective_neighbors": round(effective, 3),
        "based_on_mature_paper": len(examples),
        "is_not_win_probability": True,
    }


def _forward_validation(examples):
    """Walk-forward, with strict 60-minute+120-second maturity embargo."""
    checked, selected, covered = 0, 0, 0
    pnls = []
    baseline = []
    max_dd = 0.0
    value = peak = 100.0
    for i, item in enumerate(examples):
        prior = [r for r in examples[:i] if r["ts"] + MATURITY_S <= item["ts"]]
        if len(prior) < MIN_TRAIN:
            continue
        predicted = _predict(prior, item["features"])
        if predicted is None:
            continue
        checked += 1
        baseline.append(item["stress_net"])
        if predicted["conservative_bound_usdt"] <= ENTRY_PREDICTION_MIN_USDT:
            continue
        selected += 1
        pnls.append(item["stress_net"])
        covered += item["quoted"]
        value += item["stress_net"]
        peak = max(peak, value)
        max_dd = max(max_dd, 100 * (peak - value) / peak if peak > 0 else 100)
    average = mean(pnls) if pnls else None
    low = (average - 1.64 * pstdev(pnls) / sqrt(len(pnls))) if len(pnls) > 1 else None
    return {
        "walk_forward_checked": checked,
        "walk_forward_selected": selected,
        "selected_quote_coverage": round(covered / selected, 4) if selected else None,
        "selected_stress_average_usdt": round(average, 6) if average is not None else None,
        "selected_stress_lower_bound_usdt": round(low, 6) if low is not None else None,
        "all_opportunities_stress_average_usdt": round(mean(baseline), 6) if baseline else None,
        "sequential_stress_max_drawdown_pct": round(max_dd, 4),
        "not_concurrent_portfolio_backtest": True,
    }


def review(state, *, as_of):
    """Redacted aggregate model review. No mint, wallets or raw history."""
    at = _finite(as_of, 1, 10**12)
    if at is None:
        raise ValueError("INVALID_AS_OF")
    try:
        examples, observed_quotes = _training_samples(state, at)
    except (ProfitEvidenceError, ValueError, TypeError, KeyError, OverflowError):
        return {
            "schema_version": 1, "mode": "PAPER_AI_SIGNAL_RESEARCH",
            "status": "EVIDENCE_INVALID", "real_order": False,
            "trained_samples": 0, "operator_approval": False,
            "forward": {}, "may_filter_new_paper": False,
            "not_live_alpha_proven": True,
        }
    forward = _forward_validation(examples)
    supported = (
        len(examples) >= MIN_TRAIN + MIN_FORWARD_CHECKED and
        forward["walk_forward_checked"] >= MIN_FORWARD_CHECKED and
        forward["walk_forward_selected"] >= MIN_FORWARD_SELECTED and
        forward["selected_quote_coverage"] is not None and
        forward["selected_quote_coverage"] >= MIN_QUOTE_COVERAGE and
        forward["selected_stress_lower_bound_usdt"] is not None and
        forward["selected_stress_lower_bound_usdt"] > 0 and
        forward["sequential_stress_max_drawdown_pct"] <= 10.0
    )
    return {
        "schema_version": 1, "mode": "PAPER_AI_SIGNAL_RESEARCH",
        "status": "PAPER_FILTER_VALIDATED" if supported else "SHADOW_LEARNING",
        "real_order": False, "operator_approval": False,
        "trained_samples": len(examples),
        "exit_quotes_observed": observed_quotes,
        "forward": forward,
        "may_filter_new_paper": supported,
        "not_live_alpha_proven": True,
        "not_calibrated_win_probability": True,
    }


def assess(candidate, *, state, as_of, validation=None):
    """Advisory AI score. Caller must independently run entry_signal first."""
    f = entry_features(candidate)
    result = validation if validation is not None else review(state, as_of=as_of)
    base = {
        "mode": "PAPER_AI_SIGNAL_RESEARCH", "real_order": False,
        "features": f, "ai_status": result["status"],
        "model_can_veto": result.get("may_filter_new_paper") is True,
        "order_allowed": False,
    }
    if f is None or result.get("status") == "EVIDENCE_INVALID":
        return dict(base, action="NO_MODEL_EVIDENCE", prediction=None)
    try:
        examples, _ = _training_samples(state, as_of)
    except (ProfitEvidenceError, ValueError, TypeError, KeyError):
        return dict(base, action="NO_MODEL_EVIDENCE", prediction=None)
    prediction = _predict(examples, f)
    if not result.get("may_filter_new_paper") or prediction is None:
        return dict(base, action="SHADOW_ONLY", prediction=prediction)
    return dict(
        base, prediction=prediction,
        action=("REJECT_NEW_PAPER" if
                prediction["conservative_bound_usdt"] <= ENTRY_PREDICTION_MIN_USDT
                else "PAPER_PRIORITY_CANDIDATE"),
    )
