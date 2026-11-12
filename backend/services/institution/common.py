# -*- coding: utf-8 -*-
"""机构端通用小工具：JSON 序列化、时间格式化、金额/比例展示。

与业务状态无关，任何机构端模块都可以引用；不要在这里引入 repo / db 依赖。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb


def _j(value: Any) -> Jsonb:
    return Jsonb(value)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _row_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, (date, datetime)):
            out[k] = _iso(v)
    return out


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clip_brief(value: Any, limit: int | None = None) -> str:
    """只归一化空白，不再按 50 字截断。保留 limit 参数兼容旧调用。"""
    return " ".join(str(value or "").split())


def _evidence_grade(source: str, kind: str, explicit: Any = None) -> str:
    """证据等级：A 公告/年报，B 交易所/数据平台，C 第三方/媒体，D AI/推断。"""
    if str(explicit or "").upper() in {"A", "B", "C", "D"}:
        return str(explicit).upper()
    text = f"{source} {kind}".lower()
    if "agent" in text:
        return "D"
    if kind == "filing":
        return "A"
    if kind in {"financial", "market"} and "ifind" in text:
        return "B"
    if kind in {"filing", "news", "research", "fact"}:
        return "C"
    return "D"


def _yi(value: Any) -> str:
    if value is None:
        return "待补充"
    try:
        return f"{float(value) / 1e8:.2f} 亿元"
    except (TypeError, ValueError):
        return "待补充"


def _pc(value: Any) -> str:
    if value is None:
        return "待补充"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "待补充"


