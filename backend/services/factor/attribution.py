# -*- coding: utf-8 -*-
"""因子/组合归因（P1-F01）：Brinson-Fachler 行业归因 + 风格暴露贡献。

输入由调用方（面板/回测结果）提供，本模块只做确定性的数学汇总，不访问行情。
"""
from __future__ import annotations

from typing import Any


def _f(v: Any) -> float | None:
    try:
        if v is None or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def brinson_fachler(
    groups: list[dict[str, Any]], *, benchmark_return: float | None = None
) -> dict[str, Any]:
    """按行业/分组计算配置、选股与交互贡献。

    groups: [{name, portfolio_weight, benchmark_weight, portfolio_return, benchmark_return}]
    权重为小数（合计约 1）；收益为小数（0.01 = 1%）。
    """
    if not groups:
        raise ValueError("groups 不能为空")
    rows: list[dict[str, Any]] = []
    total_alloc = total_select = total_interact = 0.0
    for g in groups:
        name = str(g.get("name") or "").strip()
        if not name:
            raise ValueError("每个分组都需要 name")
        wp = _f(g.get("portfolio_weight")) or 0.0
        wb = _f(g.get("benchmark_weight")) or 0.0
        rp = _f(g.get("portfolio_return"))
        rb = _f(g.get("benchmark_return"))
        if rp is None or rb is None:
            raise ValueError(f"分组 {name} 缺少收益")
        alloc = (wp - wb) * (rb - (benchmark_return if benchmark_return is not None else 0.0))
        select = wb * (rp - rb)
        interact = (wp - wb) * (rp - rb)
        total_alloc += alloc
        total_select += select
        total_interact += interact
        rows.append(
            {
                "name": name,
                "portfolio_weight": wp,
                "benchmark_weight": wb,
                "portfolio_return": rp,
                "benchmark_return": rb,
                "allocation": alloc,
                "selection": select,
                "interaction": interact,
                "total": alloc + select + interact,
            }
        )
    rows.sort(key=lambda x: abs(x["total"]), reverse=True)
    return {
        "method": "brinson_fachler",
        "benchmark_return": benchmark_return,
        "allocation": total_alloc,
        "selection": total_select,
        "interaction": total_interact,
        "total": total_alloc + total_select + total_interact,
        "groups": rows,
        "top_contributors": rows[:5],
    }


def style_contribution(
    exposures: dict[str, float],
    style_returns: dict[str, float],
) -> dict[str, Any]:
    """风格暴露 × 风格收益 = 风格贡献（Barra 简化口径）。"""
    rows: list[dict[str, Any]] = []
    total = 0.0
    for name, exposure in exposures.items():
        ret = _f(style_returns.get(name))
        if ret is None:
            continue
        contribution = float(exposure) * ret
        total += contribution
        rows.append({"style": name, "exposure": float(exposure), "return": ret, "contribution": contribution})
    rows.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return {"total": total, "styles": rows}


def run_attribution(payload: dict[str, Any]) -> dict[str, Any]:
    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise ValueError("groups 须为数组")
    out = brinson_fachler(groups, benchmark_return=_f(payload.get("benchmark_return")))
    if isinstance(payload.get("exposures"), dict) and isinstance(payload.get("style_returns"), dict):
        out["style"] = style_contribution(payload["exposures"], payload["style_returns"])
    if payload.get("run_id"):
        out["run_id"] = str(payload["run_id"])
    return out
