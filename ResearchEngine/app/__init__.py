"""SVQuant 单一 ``app.*`` 命名空间的公共入口。"""

from app.core.config import ConfigManager
from app.core.runtime import ResearchDataContext, ResearchRuntime
from app.repositories.catalogs.factor_loader import FactorLoader
from app.repositories.results.manager import ResultManager
from app.repositories.results.storage import (
    CSVStorage,
    ClickHouseStorage,
    ParquetStorage,
    ResultStorage,
    SQLiteStorage,
)
from app.services.experiment import (
    Experiment,
    ExperimentContext,
    FactorExperiment,
    StrategyExperiment,
)
from app.services.experiment.manager import (
    ExperimentHandle,
    ExperimentManager,
    ExperimentManagerClosedError,
    ExperimentManagerError,
    ExperimentQueueFullError,
    ExperimentStatus,
)
from app.services.factor.plotting import plot_equity_drawdown, plot_group_ic, plot_ic_analysis
from app.services.factor.portfolio import build_close_panel, build_factor_portfolio

__all__ = [
    "Experiment",
    "ExperimentContext",
    "FactorExperiment",
    "StrategyExperiment",
    "ExperimentManager",
    "ExperimentHandle",
    "ExperimentManagerError",
    "ExperimentManagerClosedError",
    "ExperimentQueueFullError",
    "ExperimentStatus",
    "ResearchDataContext",
    "ResearchRuntime",
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
