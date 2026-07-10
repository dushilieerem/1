"""ResearchEngine - 投资研究层（用户入口）。

依据 ``docs/03-模块.md`` 划分为四个模块 + 核心对象 Experiment：

- ``Experiment``         - 核心对象，一次实验
- ``ExperimentManager``   - 整个 ResearchEngine 的核心（编排）
- ``FactorLoader``        - 动态加载因子文件
- ``ConfigManager``       - 统一配置读取
- ``ResultManager``       - 保存结果（不计算）

ResearchEngine 永远是用户入口，调用 QuantCore 完成计算。
"""

from researchengine.config import ConfigManager
from researchengine.experiment import Experiment
from researchengine.factor_loader import FactorLoader
from researchengine.manager import ExperimentManager
from researchengine.plotting import plot_equity_drawdown, plot_group_ic
from researchengine.portfolio import build_factor_portfolio, build_close_panel
from researchengine.result.manager import ResultManager
from researchengine.result.storage import (
    CSVStorage,
    ClickHouseStorage,
    ParquetStorage,
    ResultStorage,
    SQLiteStorage,
)

__all__ = [
    "Experiment",
    "ExperimentManager",
    "FactorLoader",
    "ConfigManager",
    "ResultManager",
    "ResultStorage",
    "CSVStorage",
    "ParquetStorage",
    "SQLiteStorage",
    "ClickHouseStorage",
    "build_factor_portfolio",
    "build_close_panel",
    "plot_equity_drawdown",
    "plot_group_ic",
]
