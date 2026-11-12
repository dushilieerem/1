# -*- coding: utf-8 -*-
"""机构端 DCF 估值（FR-RES-19..22）。

只做确定性计算：五年显式预测 + 永续增长；不产生投资建议。
输入金额单位由调用方决定（建议用亿元），输出同单位。
"""
from __future__ import annotations

from typing import Any

MIN_GROWTH, MAX_GROWTH = 0.0, 0.20
MIN_MARGIN, MAX_MARGIN = 0.15, 0.70
MIN_DISCOUNT, MAX_DISCOUNT = 0.07, 0.14
MIN_TERMINAL, MAX_TERMINAL = 0.0, 0.05


def _num(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是数字") from exc


def _validate(
    *,
    base_revenue: float,
    cashflow_margin: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> None:
    if base_revenue <= 0:
        raise ValueError("基期收入必须大于 0")
    if not (MIN_MARGIN <= cashflow_margin <= MAX_MARGIN):
        raise ValueError(f"现金流利润率须在 {MIN_MARGIN:.0%}–{MAX_MARGIN:.0%}")
    if not (MIN_DISCOUNT <= discount_rate <= MAX_DISCOUNT):
        raise ValueError(f"折现率须在 {MIN_DISCOUNT:.0%}–{MAX_DISCOUNT:.0%}")
    if not (MIN_TERMINAL <= terminal_growth <= MAX_TERMINAL):
        raise ValueError(f"永续增长率须在 {MIN_TERMINAL:.0%}–{MAX_TERMINAL:.0%}")
    if discount_rate <= terminal_growth:
        raise ValueError("折现率必须高于永续增长率")
    if years < 1 or years > 10:
        raise ValueError("预测年数须在 1–10")


def _dcf(
    *,
    base_revenue: float,
    growth: float,
    cashflow_margin: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> tuple[float, list[dict[str, float]]]:
    rows: list[dict[str, float]] = []
    pv = 0.0
    revenue = base_revenue
    for year in range(1, years + 1):
        revenue *= 1 + growth
        fcf = revenue * cashflow_margin
        discounted = fcf / ((1 + discount_rate) ** year)
        pv += discounted
        rows.append(
            {
                "year": year,
                "revenue": revenue,
                "fcf": fcf,
                "discounted": discounted,
            }
        )
    terminal_fcf = rows[-1]["fcf"] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount_rate) ** years)
    return pv + pv_terminal, rows


def run_dcf(payload: dict[str, Any]) -> dict[str, Any]:
    base_revenue = _num(payload.get("base_revenue"), "base_revenue")
    growth = _num(payload.get("revenue_growth"), "revenue_growth")
    margin = _num(payload.get("cashflow_margin"), "cashflow_margin")
    discount = _num(payload.get("discount_rate"), "discount_rate")
    terminal = _num(payload.get("terminal_growth"), "terminal_growth")
    years = int(payload.get("years") or 5)
    if not (MIN_GROWTH <= growth <= MAX_GROWTH):
        raise ValueError(f"收入增长率须在 {MIN_GROWTH:.0%}–{MAX_GROWTH:.0%}")
    _validate(
        base_revenue=base_revenue,
        cashflow_margin=margin,
        discount_rate=discount,
        terminal_growth=terminal,
        years=years,
    )
    shares = payload.get("shares_outstanding")
    shares_f = _num(shares, "shares_outstanding") if shares not in (None, "") else None
    if shares_f is not None and shares_f <= 0:
        raise ValueError("股本必须大于 0")

    base_value, rows = _dcf(
        base_revenue=base_revenue,
        growth=growth,
        cashflow_margin=margin,
        discount_rate=discount,
        terminal_growth=terminal,
        years=years,
    )
    # 悲观/乐观：增长率和利润率各调整 1 个百分点，折现率不变
    low_growth = max(MIN_GROWTH, growth - 0.01)
    high_growth = min(MAX_GROWTH, growth + 0.01)
    low_margin = max(MIN_MARGIN, margin - 0.01)
    high_margin = min(MAX_MARGIN, margin + 0.01)
    low_value, _ = _dcf(
        base_revenue=base_revenue, growth=low_growth, cashflow_margin=low_margin,
        discount_rate=discount, terminal_growth=terminal, years=years,
    )
    high_value, _ = _dcf(
        base_revenue=base_revenue, growth=high_growth, cashflow_margin=high_margin,
        discount_rate=discount, terminal_growth=terminal, years=years,
    )

    # 折现率 ±1%、永续增长率 ±1% 的 3×3 敏感性
    discounts = [round(discount + d, 4) for d in (-0.01, 0.0, 0.01)]
    terminals = [round(terminal + t, 4) for t in (-0.01, 0.0, 0.01)]
    sensitivity: list[dict[str, Any]] = []
    for d in discounts:
        cells = []
        for tg in terminals:
            try:
                if d <= tg:
                    raise ValueError
                value, _ = _dcf(
                    base_revenue=base_revenue, growth=growth, cashflow_margin=margin,
                    discount_rate=d, terminal_growth=tg, years=years,
                )
                cells.append(round(value, 4))
            except ValueError:
                cells.append(None)
        sensitivity.append({"discount_rate": d, "values": cells})

    def per_share(value: float) -> float | None:
        return round(value / shares_f, 4) if shares_f else None

    return {
        "ok": True,
        "currency": str(payload.get("currency") or "CNY"),
        "assumptions": {
            "base_revenue": base_revenue,
            "revenue_growth": growth,
            "cashflow_margin": margin,
            "discount_rate": discount,
            "terminal_growth": terminal,
            "years": years,
            "shares_outstanding": shares_f,
        },
        "range": {
            "low": round(low_value, 4),
            "base": round(base_value, 4),
            "high": round(high_value, 4),
            "low_per_share": per_share(low_value),
            "base_per_share": per_share(base_value),
            "high_per_share": per_share(high_value),
        },
        "projection": rows,
        "sensitivity": {
            "terminal_growth": terminals,
            "rows": sensitivity,
        },
        "limits": [
            "模型未计税费、营运资本、汇率与治理折价",
            "结果不是目标价，不构成投资建议",
        ],
    }
