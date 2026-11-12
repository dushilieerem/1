"""Strategy gate policy v1 (PM-V5-048 / prototype v5/strategy.html).

Thresholds are an explicit test policy version, not production calibration:
the institution may publish a new policy version with different values.
IR is computed from the daily excess series (strategy NAV vs benchmark NAV).
"""
from __future__ import annotations

import math

POLICY_VERSION = "strategy-v5-p0"
POLICY = {
    "excess": 0.03,       # net annual excess vs benchmark
    "dd": 0.12,           # relative max drawdown
    "turnover": 15.0,     # one-way annual turnover, times
    "neighborhood_cells": 6,  # of 9 cells must clear excess>=3% and IR>=0.5
    "neighborhood_excess": 0.03,
    "neighborhood_ir": 0.5,
    "seal_excess": 0.0,   # sealed excess > 0
    "seal_ir": 0.3,       # sealed IR >= 0.3
    "trading_days": 252,
}


def need_ir(k: int) -> float:
    """IR bar rises with the number of viewed trials: 0.5 + 0.15*sqrt(2 ln K)."""
    return round(0.5 + 0.15 * math.sqrt(2 * math.log(max(1, int(k)))), 4)


def _series(result):
    curve = result.get("equity_curve") or []
    bench = result.get("benchmark_curve") or []
    if not curve or not bench:
        return None, None
    s = {str(p.get("date")): float(p.get("value")) for p in curve if p.get("date") and p.get("value")}
    b = {str(p.get("date")): float(p.get("value")) for p in bench if p.get("date") and p.get("value")}
    dates = sorted(set(s) & set(b))
    if len(dates) < 3:
        return None, None
    return s, b, dates


def metrics_from_result(result) -> dict:
    """Daily excess and relative drawdown derived from the two equity curves."""
    # RE returns only the cumulative period excess; the gate needs the policy
    # definition: annual arithmetic net excess = mean(daily net excess) * 252.
    out = {"annual_excess": None, "period_excess": result.get("excess_return"),
           "ir": None, "relative_dd": None, "turnover_annual": None}
    m = result.get("metrics") or {}
    try:
        if m.get("turnover") is not None:
            out["turnover_annual"] = float(m["turnover"]) * POLICY["trading_days"]
    except (TypeError, ValueError):
        pass
    series = _series(result)
    if not series[0]:
        return out
    s, b, dates = series
    rets = []
    for prev, cur in zip(dates, dates[1:]):
        rs = s[cur] / s[prev] - 1.0
        rb = b[cur] / b[prev] - 1.0
        rets.append(rs - rb)
    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
        ann = mean * POLICY["trading_days"]
        out["annual_excess"] = ann
        vol = math.sqrt(var) * math.sqrt(POLICY["trading_days"])
        if vol > 0:
            out["ir"] = ann / vol
        rel = [s[d] / b[d] for d in dates]
        peak, worst = rel[0], 0.0
        for v in rel:
            peak = max(peak, v)
            worst = min(worst, v / peak - 1.0)
        out["relative_dd"] = abs(worst)
    return out


def evaluate(result, k: int, *, cost_2x_excess=None, neighborhood=None, sealed=False) -> dict:
    """Six development gates; sealed validation uses the 2-gate policy."""
    derived = metrics_from_result(result)
    excess = derived["annual_excess"]
    if cost_2x_excess is None and isinstance(result.get("cost_2x_excess"), (int, float)):
        cost_2x_excess = float(result["cost_2x_excess"])
    if neighborhood is None and isinstance(result.get("neighborhood"), dict):
        neighborhood = result["neighborhood"]
    if sealed:
        checks = [
            {"name": "封存扣费后年化超额", "actual": excess, "operator": ">", "threshold": POLICY["seal_excess"],
             "passed": None if excess is None else float(excess) > POLICY["seal_excess"]},
            {"name": "封存信息比率", "actual": derived["ir"], "operator": ">=", "threshold": POLICY["seal_ir"],
             "passed": None if derived["ir"] is None else derived["ir"] >= POLICY["seal_ir"]},
        ]
        return {"policy_version": POLICY_VERSION, "basis": "annual", "sealed": True, "checks": checks,
                "passed": all(c["passed"] is True for c in checks),
                "complete": all(c["passed"] is not None for c in checks),
                "pending": [c["name"] for c in checks if c["passed"] is None]}
    nb_ok = None
    if isinstance(neighborhood, dict) and neighborhood.get("cells") is not None:
        nb_ok = neighborhood.get("passed_cells")
    checks = [
        {"name": "扣费后年化超额", "actual": converted(excess), "operator": ">=", "threshold": POLICY["excess"],
         "passed": None if excess is None else float(excess) >= POLICY["excess"]},
        {"name": "信息比率（按试验数校正）", "actual": derived["ir"], "operator": ">=", "threshold": need_ir(k),
         "passed": None if derived["ir"] is None else derived["ir"] >= need_ir(k)},
        {"name": "相对基准最大回撤", "actual": derived["relative_dd"], "operator": "<=", "threshold": POLICY["dd"],
         "passed": None if derived["relative_dd"] is None else derived["relative_dd"] <= POLICY["dd"]},
        {"name": "单边年换手", "actual": derived["turnover_annual"], "operator": "<=", "threshold": POLICY["turnover"],
         "passed": None if derived["turnover_annual"] is None else derived["turnover_annual"] <= POLICY["turnover"]},
        {"name": "2 倍成本下超额", "actual": converted(cost_2x_excess), "operator": ">", "threshold": 0.0,
         "passed": None if cost_2x_excess is None else float(cost_2x_excess) > 0},
        {"name": "参数邻域达标", "actual": nb_ok, "operator": ">=", "threshold": POLICY["neighborhood_cells"],
         "passed": None if nb_ok is None else int(nb_ok) >= POLICY["neighborhood_cells"]},
    ]
    return {"policy_version": POLICY_VERSION, "basis": "annual", "sealed": False, "checks": checks,
            "passed": all(c["passed"] is True for c in checks),
            "complete": all(c["passed"] is not None for c in checks),
            "pending": [c["name"] for c in checks if c["passed"] is None],
            "thresholds": dict(POLICY, ir=need_ir(k), k=k)}


def converted(value):
    return None if value is None else float(value)


__all__ = ["POLICY", "POLICY_VERSION", "evaluate", "metrics_from_result", "need_ir"]
