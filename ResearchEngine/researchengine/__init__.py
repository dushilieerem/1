"""ResearchEngine - 投资研究层（用户入口）。

依据 ``docs/04-features/FEAT-002-research-engine/03-modules.md`` 划分为执行单元、
任务调度器和结果对象：

- ``Experiment``         - 核心对象，一次实验
- ``ExperimentManager``   - 进程级回测任务调度器和线程池所有者
- ``FactorLoader``        - 动态加载因子文件
- ``ConfigManager``       - 统一配置读取
- ``ResultManager``       - 保存结果（不计算）

ResearchEngine 永远是用户入口，调用 QuantCore 完成计算。
"""

from researchengine.config import ConfigManager
from researchengine.experiment import Experiment
from researchengine.factor_loader import FactorLoader
from researchengine.manager import (
    ExperimentHandle,
    ExperimentManager,
    ExperimentManagerClosedError,
    ExperimentManagerError,
    ExperimentQueueFullError,
    ExperimentStatus,
)
from researchengine.plotting import plot_equity_drawdown, plot_group_ic, plot_ic_analysis
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
    "ExperimentHandle",
    "ExperimentManagerError",
    "ExperimentManagerClosedError",
    "ExperimentQueueFullError",
    "ExperimentStatus",
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
    "plot_ic_analysis",
]
