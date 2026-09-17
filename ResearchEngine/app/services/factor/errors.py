"""因子回测的业务错误。"""

from __future__ import annotations


class FactorBacktestError(RuntimeError):
    """所有统一因子回测错误的基类。"""


class FactorBacktestParameterError(ValueError, FactorBacktestError):
    """规格或参数不合法。"""


class FactorBacktestDataError(FileNotFoundError, FactorBacktestError):
    """行情、股票池或基准数据不可用。"""


class FactorBacktestEmptyResult(FactorBacktestError):
    """输入合法但没有形成可用回测结果。"""


class FactorBacktestRuntimeError(FactorBacktestError):
    """执行过程中的未分类运行时错误。"""


__all__ = [
    "FactorBacktestError",
    "FactorBacktestParameterError",
    "FactorBacktestDataError",
    "FactorBacktestEmptyResult",
    "FactorBacktestRuntimeError",
]
