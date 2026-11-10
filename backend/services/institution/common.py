# -*- coding: utf-8 -*-
"""机构端通用小工具：JSON 序列化、时间格式化、金额/比例展示。

与业务状态无关，任何机构端模块都可以引用；不要在这里引入 repo / db 依赖。
"""
from __future__ import annotations

import hashlib
import json
import re
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


_HUMAN_TERMS: tuple[tuple[str, str], ...] = (
    ("均分", "平均评分"),
    ("六维", "六个维度"),
    ("净现比", "经营现金流/净利润"),
    ("A级证据", "最高等级证据"),
    ("B级证据", "次高等级证据"),
    ("C级证据", "一般等级证据"),
    ("低分线", "低分门槛"),
    ("OCF/净利", "经营现金流/净利润"),
    ("OCF", "经营现金流"),
    ("DIO", "存货周转天数"),
    ("DSO", "应收账款周转天数"),
    ("ROE", "净资产收益率"),
    ("PE_TTM", "市盈率（TTM）"),
    ("PB_MRQ", "市净率"),
    ("PE", "市盈率"),
    ("PB", "市净率"),
    ("TTM", "最近十二个月"),
    ("FCF", "自由现金流"),
    ("EBITDA", "息税折旧摊销前利润"),
    ("FactPack", "本轮数据包"),
    ("peer_summary", "同业样本"),
    ("history_summary", "历史财务"),
    ("data_completeness", "数据完备性"),
    ("score_10", "评分"),
    ("available=false", "估值服务未给出有效结果"),
    ("available=true", "估值服务结果可用"),
)


def humanize_text(value: Any) -> str:
    """把 Agent 输出里的英文缩写/内部字段名换成人话，保留数字与证据编号。"""
    text = str(value or "")
    for old, new in _HUMAN_TERMS:
        text = text.replace(old, new)
    text = re.sub(r"含金量\s*A\s*档", "现金含量高", text)
    text = re.sub(r"含金量\s*B\s*档", "现金含量中等", text)
    text = re.sub(r"含金量\s*C\s*档", "现金含量偏低", text)
    text = re.sub(r"(?<![A-Za-z0-9])E(\d{2,})(?![A-Za-z0-9])", r"证据 \1", text)
    text = re.sub(r"(\d{4})\s*H1", r"\1 年上半年", text)
    text = re.sub(r"(\d{4})\s*H2", r"\1 年下半年", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*pct", r"\1 个百分点", text, flags=re.IGNORECASE)
    return _clip_brief(text)


def humanize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [humanize_text(value)] if value.strip() else []
    return [humanize_text(x) for x in (value or []) if str(x).strip()]


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


