# -*- coding: utf-8 -*-
"""多因子合成与因子择时（P1-F02）。

输入逐因子截面值（同一股票池），输出合成分数；支持等权、IC/IR 加权、
自定义权重与简单择时（按日期开关系数）。
"""
from __future__ import annotations

import math
from typing import Any


def _num(v: Any) -> float | None:
    try:
        if v is None or isinstance(v, bool):
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def zscore(values: list[float | None]) -> list[float | None]:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return [None for _ in values]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = math.sqrt(var)
    if std <= 0:
        return [0.0 if v is not None else None for v in values]
    return [(v - mean) / std if v is not None else None for v in values]


def _weights(scheme: str, factors: list[str], metrics: dict[str, Any], custom: dict[str, Any]) -> dict[str, float]:
    if scheme == "equal":
        w = {f: 1.0 for f in factors}
    elif scheme == "ic":
        w = {f: max(0.0, _num(metrics.get(f, {}).get("ic")) or 0.0) for f in factors}
    elif scheme == "ir":
        w = {f: max(0.0, _num(metrics.get(f, {}).get("ir")) or 0.0) for f in factors}
    elif scheme == "custom":
        w = {f: max(0.0, _num(custom.get(f)) or 0.0) for f in factors}
    else:
        raise ValueError(f"不支持的权重方案: {scheme}")
    total = sum(w.values())
    if total <= 0:
        if scheme == "equal":
            raise ValueError("因子列表为空")
        raise ValueError("权重合计为 0，请检查 IC/IR 或自定义权重")
    return {k: v / total for k, v in w.items()}


def combine(
    *,
    factors: dict[str, list[float | None]],
    scheme: str = "equal",
    metrics: dict[str, Any] | None = None,
    custom_weights: dict[str, Any] | None = None,
    timing: dict[str, float] | None = None,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """factors: {factor_name: [value per stock]}；timing: {date: 0..1} 仅返回乘数。"""
    names = [k for k, v in factors.items() if isinstance(v, list)]
    if not names:
        raise ValueError("至少需要一个因子序列")
    lengths = {len(factors[n]) for n in names}
    if len(lengths) != 1:
        raise ValueError("各因子序列长度必须一致")
    weights = _weights(scheme, names, metrics or {}, custom_weights or {})
    normalized = {n: zscore(factors[n]) for n in names}
    scores: list[float | None] = []
    for i in range(lengths.pop()):
        total = 0.0
        present = 0
        for n in names:
            v = normalized[n][i]
            if v is None:
                continue
            total += v * weights[n]
            present += 1
        scores.append(total if present else None)
    multiplier: list[float | None] = []
    if timing:
        for i in range(len(scores)):
            key = dates[i] if dates and i < len(dates) else str(i)
            m = _num(timing.get(key))
            if m is None:
                # 未配置的日期按 1 处理，避免悄悄清零
                m = 1.0
            multiplier.append(m)
    else:
        multiplier = [1.0] * len(scores)
    timed_scores = [
        (s * m) if s is not None else None for s, m in zip(scores, multiplier)
    ]
    return {
        "scheme": scheme,
        "weights": weights,
        "scores": scores,
        "timing_multiplier": multiplier if timing else [],
        "timed_scores": timed_scores,
        "timing": timing or {},
        "coverage": [sum(1 for n in names if normalized[n][i] is not None) for i in range(len(scores))],
    }
