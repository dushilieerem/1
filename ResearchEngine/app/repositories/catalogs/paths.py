"""项目级因子资产目录。"""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def factor_library_dir() -> Path:
    """返回因子库目录，可由 ``SVQUANT_FACTOR_DIR`` 覆盖。"""
    return Path(
        os.environ.get(
            "SVQUANT_FACTOR_DIR",
            _app_root() / "assets" / "factors" / "libraries",
        )
    )


def factor_index_path() -> Path:
    """返回因子目录索引；默认索引位于 ``assets/factors/index.yaml``。"""
    if "SVQUANT_FACTOR_DIR" in os.environ:
        return factor_library_dir() / "index.yaml"
    return factor_library_dir().parent / "index.yaml"


def backtest_cache_dir() -> Path:
    """返回回测缓存目录，可由 ``SVQUANT_BACKTEST_CACHE_DIR`` 覆盖。"""
    return Path(
        os.environ.get(
            "SVQUANT_BACKTEST_CACHE_DIR",
            _repo_root() / "Factor" / "backtest_results",
        )
    )


def strategy_library_dir() -> Path:
    """返回项目级策略库目录，可由 ``SVQUANT_STRATEGY_DIR`` 覆盖。"""
    return Path(
        os.environ.get(
            "SVQUANT_STRATEGY_DIR",
            _app_root() / "assets" / "strategies" / "libraries",
        )
    )


def strategy_index_path() -> Path:
    """返回策略目录索引；默认索引位于 ``assets/strategies/index.yaml``。"""
    if "SVQUANT_STRATEGY_DIR" in os.environ:
        return strategy_library_dir() / "index.yaml"
    return strategy_library_dir().parent / "index.yaml"
