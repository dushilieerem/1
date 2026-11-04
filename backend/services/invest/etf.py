# -*- coding: utf-8 -*-
"""ETF 穿透（H06/H07，默认代理口径）。

数据平台暂无 ETF 官方持仓，默认用“跟踪指数成分/权重”作代理：
- 明确标注 tracking=index_proxy，不冒充官方持仓；
- 未知 ETF 返回 unmapped，页面显示需要数据补充。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from services.data.platform_view import materialized_view_root

# 常见宽基 ETF → 跟踪指数（可直接维护；未知代码返回 None）
ETF_INDEX: dict[str, str] = {
    "510300.SH": "000300.SH",
    "159919.SZ": "000300.SH",
    "510310.SH": "000300.SH",
    "510330.SH": "000300.SH",
    "159925.SZ": "000300.SH",
    "510500.SH": "000905.SH",
    "159922.SZ": "000905.SH",
    "510510.SH": "000905.SH",
    "512500.SH": "000905.SH",
    "510050.SH": "000016.SH",
    "510710.SH": "000016.SH",
    "512100.SH": "000852.SH",
    "159845.SZ": "000852.SH",
    "588000.SH": "000688.SH",
    "588080.SH": "000688.SH",
    "588090.SH": "000688.SH",
    "159915.SZ": "399006.SZ",
    "159952.SZ": "399006.SZ",
}

_ETF_RE = re.compile(r"^(5[168]\d{4}\.SH|1[56]\d{4}\.SZ)$")

# 货币 ETF/现金管理工具没有股票成分，不能按指数代理展示。
CASH_ETFS = {"511880.SH", "511990.SH", "511660.SH", "511620.SH", "511850.SH"}


def normalize_etf(code: str) -> str:
    text = (code or "").strip().upper()
    if "." in text:
        return text
    if re.fullmatch(r"5[168]\d{4}", text):
        return f"{text}.SH"
    if re.fullmatch(r"1[56]\d{4}", text):
        return f"{text}.SZ"
    raise ValueError("ETF 代码格式错误")


def is_etf(code: str) -> bool:
    try:
        return bool(_ETF_RE.match(normalize_etf(code)))
    except ValueError:
        return False


def _weights_path(index_code: str) -> Path | None:
    root = materialized_view_root()
    if root is None:
        return None
    path = root / "free" / "index_weights" / f"{index_code}.parquet"
    return path if path.exists() else None


def load_weights(index_code: str) -> list[dict[str, Any]]:
    path = _weights_path(index_code)
    if path is None:
        return []
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(path, columns=["Symbol", "Weight"])
        rows = table.to_pylist()
    except Exception:
        # 可选依赖/文件异常不应让 H5 500；页面会显示“成分数据待补充”。
        return []
    out = []
    for row in rows:
        try:
            weight = float(row.get("Weight"))
        except (TypeError, ValueError):
            continue
        out.append({"symbol": str(row.get("Symbol") or "").upper(), "weight": weight})
    out.sort(key=lambda x: x["weight"], reverse=True)
    return out


def profile(code: str, *, top: int = 20) -> dict[str, Any]:
    symbol = normalize_etf(code)
    if symbol in CASH_ETFS:
        return {
            "ok": True,
            "etf": symbol,
            "tracking": "cash_management",
            "tracked_index": None,
            "constituent_count": 0,
            "constituents": [],
            "warning": (
                "货币 ETF/现金管理工具，没有股票成分，不适用指数穿透；"
                "它不是“数据缺失”，也不代表收益承诺。ETF 日线仅到 2026-10-23，不能当实时净值。"
            ),
        }
    index_code = ETF_INDEX.get(symbol)
    if not index_code:
        return {
            "ok": True,
            "etf": symbol,
            "tracking": "unmapped",
            "tracked_index": None,
            "constituents": [],
            "warning": "未登记跟踪指数，需补充 ETF 官方持仓或指数映射",
        }
    weights = load_weights(index_code)
    return {
        "ok": True,
        "etf": symbol,
        "tracking": "index_proxy",
        "tracked_index": index_code,
        "constituent_count": len(weights),
        "constituents": weights[: max(1, min(top, 200))],
        "warning": (
            "代理口径：以跟踪指数成分/权重代替 ETF 官方持仓，非真实持仓"
            if weights else "跟踪指数已登记，但成分权重文件缺失或读取失败；显示待补充，不按 0 处理。"
        ),
    }


def overlap(code_a: str, code_b: str) -> dict[str, Any]:
    a = profile(code_a, top=500)
    b = profile(code_b, top=500)
    wa = {row["symbol"]: row["weight"] for row in a["constituents"]}
    wb = {row["symbol"]: row["weight"] for row in b["constituents"]}
    common = sorted(set(wa) & set(wb))
    weighted = sum(min(wa[s], wb[s]) for s in common)  # 百分比权重的重叠强度
    return {
        "ok": True,
        "a": {"etf": a["etf"], "tracked_index": a["tracked_index"], "tracking": a["tracking"]},
        "b": {"etf": b["etf"], "tracked_index": b["tracked_index"], "tracking": b["tracking"]},
        "common_count": len(common),
        "overlap_weight_pct": round(weighted, 4),
        "common": [{"symbol": s, "a": wa[s], "b": wb[s]} for s in common[:50]],
        "warning": "代理口径重叠度，仅用于研究比较",
    }
