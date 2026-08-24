"""后端注册表 / 工厂：按 ``BacktestConfig.engine`` 取回测后端实例。

当前仅提供 NativeEngine；如未来需要新增后端，在此注册并实现 :class:`IBacktestEngine`。
"""

from __future__ import annotations

from app.quantcore.backtest.adapter.interfaces import IBacktestEngine
from app.quantcore.backtest.adapter.native_engine import NativeEngine

_ENGINES = {
    "native": NativeEngine,
}


def get_backtest_engine(name: str = "native", **kwargs) -> IBacktestEngine:
    """按名取回测后端实例。

    Parameters
    ----------
    name:
        ``"native"``。
    **kwargs:
        透传给后端构造器（当前两后端均无参，预留）。
    """
    cls = _ENGINES.get(name)
    if cls is None:
        raise ValueError(f"未知回测后端 {name!r}，可选: {sorted(_ENGINES)}")
    return cls(**kwargs)
