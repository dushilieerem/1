"""项目级因子资产目录。"""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _app_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def factor_database_path() -> Path:
    """返回 SQLite 因子库路径。

    因子库位于项目的 ``assets/factors`` 目录；保留环境变量别名，方便本地开发、
    测试和部署环境使用不同的数据库位置。
    """

    return Path(
        os.environ.get("SVQUANT_FACTOR_DB_PATH")
        or os.environ.get("SVQUANT_FACTOR_DB")
        or _app_root() / "assets" / "factors" / "factor_library.db"
    ).expanduser()


def factor_tool_path() -> Path:
    """返回 SQLite 因子源码依赖的公共 ``tool.py`` 路径。"""

    return Path(
        os.environ.get("SVQUANT_FACTOR_TOOL_PATH")
        or os.environ.get("SVQUANT_FACTOR_TOOL")
        or _app_root() / "assets" / "factors" / "tool.py"
    ).expanduser()


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
