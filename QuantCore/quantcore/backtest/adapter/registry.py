"""后端注册表 / 工厂：按 ``BacktestConfig.engine`` 取回测后端实例。

新增第三个后端 = 在此注册 + 实现 :class:`IBacktestEngine`，ResearchEngine 无感。
"""

from __future__ import annotations

from quantcore.backtest.adapter.interfaces import IBacktestEngine
from quantcore.backtest.adapter.native_engine import NativeEngine

_ENGINES = {
    "native": NativeEngine,
}


def get_backtest_engine(name: str = "native", **kwargs) -> IBacktestEngine:
    """按名取回测后端实例。

    Parameters
    ----------
    name:
        ``"native"`` | ``"vectorbt"``（后者懒加载，未装 vectorbt 时实例化不报错、
        ``run`` 时才报）。
    **kwargs:
        透传给后端构造器（当前两后端均无参，预留）。
    """
    if name == "vectorbt":
        # 懒加载：避免无 vectorbt 时 import adapter 即失败
        from quantcore.backtest.adapter.vectorbt_engine import VectorBTEngine

        return VectorBTEngine(**kwargs)
    cls = _ENGINES.get(name)
    if cls is None:
        raise ValueError(
            f"未知回测后端 {name!r}，可选: {sorted(list(_ENGINES)) + ['vectorbt']}"
        )
    return cls(**kwargs)
