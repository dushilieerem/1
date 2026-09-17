"""运行时资产版本数据。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyAsset:
    """可被回测引用的不可变策略源码版本。"""

    strategy_id: str
    name: str
    strategy_type: str
    execution_mode: str
    version: str
    entrypoint: str
    source_code: str
    code_hash: str
