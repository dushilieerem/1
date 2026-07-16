"""pandas / 指标 -> JSON-able 纯 Python 序列化。

避免 ``NaN``/``inf`` 进 JSON（非法），统一转 ``None``；把 ``DatetimeIndex`` 序列化成
ISO 日期字符串；PNG 转 base64。所有转换都在这里集中，路由层只组装。
"""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Optional

import pandas as pd


def _safe_float(v) -> Optional[float]:
    """转 float；``NaN``/``inf``/不可解析 -> ``None``（JSON ``null``）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def metrics_to_dict(metrics: "dict") -> "dict[str, Optional[float]]":
    """指标字典 -> JSON 安全（``NaN`` -> ``null``）。"""
    return {str(k): _safe_float(v) for k, v in metrics.items()}


def equity_to_points(series) -> "list[dict]":
    """净值 ``pd.Series`` -> ``[{date, value}]``。"""
    if series is None or len(series) == 0:
        return []
    out: list[dict] = []
    for ts, val in series.items():
        v = _safe_float(val)
        out.append({"date": pd.Timestamp(ts).strftime("%Y-%m-%d"), "value": 0.0 if v is None else v})
    return out


def date_range_from(series) -> "dict[str, Optional[str]]":
    """从净值序列取起止日期。"""
    if series is None or len(series) == 0:
        return {"start": None, "end": None}
    return {
        "start": pd.Timestamp(series.index[0]).strftime("%Y-%m-%d"),
        "end": pd.Timestamp(series.index[-1]).strftime("%Y-%m-%d"),
    }


def png_to_b64(path) -> Optional[str]:
    """PNG 文件 -> base64 字符串；不存在返回 ``None``。"""
    p = Path(path)
    if not p.exists():
        return None
    return base64.b64encode(p.read_bytes()).decode("ascii")
