"""真实研究链路包：数据接入 -> 四因子 -> 评价(IC/IR) -> 组合回测 -> 分析。"""
from __future__ import annotations

from .data_source import fetch_data
from .factors import compute_factors, FACTOR_NAMES
from .db import FactorDB
from .evaluation import evaluate_factors
from .strategy import build_composite, backtest, analyze

__all__ = [
    "fetch_data", "compute_factors", "FACTOR_NAMES", "FactorDB",
    "evaluate_factors", "build_composite", "backtest", "analyze",
]
