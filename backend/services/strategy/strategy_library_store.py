# -*- coding: utf-8 -*-
"""内置策略目录的兼容门面。

历史代码曾在这里直接读取本地策略目录。现在由 ``builtin_strategies_store``
维护 ResearchEngine API 的数据库镜像；保留这些函数名只是为了兼容尚未迁移的脚本，
实际不会访问本地策略文件。
"""
from __future__ import annotations

from typing import Any

from services.strategy.builtin_strategies_store import (
    get_builtin_strategy,
    list_builtin_strategies_from_db,
)


def libraries_root() -> None:
    """旧 API 兼容项：内置策略已不再有 SVQuant 本地目录。"""
    return None


def load_index() -> dict[str, Any]:
    """旧 API 兼容项：返回当前数据库镜像目录。"""
    return list_builtin_strategies_from_db()


def list_builtin_strategies() -> dict[str, Any]:
    return list_builtin_strategies_from_db()


def get_strategy_source(
    strategy_id: str, *, version: str | None = None
) -> dict[str, Any]:
    """兼容旧调用；源码只来自数据库中的过渡期快照。"""
    data = get_builtin_strategy(strategy_id)
    if version:
        data["version"] = version
    return data
