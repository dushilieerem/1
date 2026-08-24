# -*- coding: utf-8 -*-
"""Agent E · 评价雏形：回测报告 → 是否建议入库（不自动写入库）。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

_TZ = timezone(timedelta(hours=8))


def _num(raw: Any) -> float | None:
    try:
        if raw is None:
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def run_eval(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    _ = user_id
    t0 = time.perf_counter()
    report = body.get("report") if isinstance(body.get("report"), dict) else {}
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    # RE 常见字段名不完全固定，尽量兼容
    sharpe = _num(metrics.get("sharpe") or metrics.get("Sharpe") or report.get("sharpe"))
    ann = _num(
        metrics.get("annual_return")
        or metrics.get("annualReturn")
        or report.get("annual_return")
    )
    mdd = _num(metrics.get("max_drawdown") or metrics.get("maxDrawdown"))
    err = str(report.get("error") or "").strip()

    reasons: list[str] = []
    if err:
        reasons.append(f"回测报错：{err[:120]}")
        verdict = "reject"
        note = "接口失败，不能入库。"
    else:
        score = 0
        if sharpe is not None and sharpe >= 0.5:
            score += 1
            reasons.append(f"Sharpe {sharpe:.2f} ≥ 0.5")
        elif sharpe is not None:
            reasons.append(f"Sharpe {sharpe:.2f} 偏低")
        else:
            reasons.append("报告里没有 Sharpe，只能人工看曲线")
        if ann is not None and ann > 0:
            score += 1
            reasons.append(f"年化 {ann:.2%} 为正")
        if mdd is not None and mdd > -0.4:
            score += 1
            reasons.append(f"回撤 {mdd:.2%} 未极端")
        # 有效期：单区间不能当终身有效
        reasons.append("同一因子换区间可能完全不同，建议对照样本外后再决定")
        if score >= 2 and not err:
            verdict = "review"
            note = "指标尚可，建议人工对照样本外后再考虑入库，本步不自动写入。"
        else:
            verdict = "reject"
            note = "当前报告不足以建议入库。"

    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "eval_id": f"fev_{datetime.now(_TZ).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "verdict": verdict,  # admit 留给以后；雏形只有 review / reject
        "admit": False,
        "note": note,
        "reasons": reasons,
        "stats": {"elapsed_ms": elapsed, "eval_mode": "rule"},
        "warnings": ["评价 Agent 为雏形，不会改因子库"],
    }
