"""策略回测 Experiment 适配器。"""

from __future__ import annotations

from app.schemas.backtest import StrategyBacktestRequest, StrategyBacktestResponse
from app.services.experiment.base import Experiment
from app.services.data.engine import DataEngine
from app.services.strategy.backtest import run_strategy_backtest


class StrategyExperiment(Experiment[StrategyBacktestResponse]):
    """将一个策略回测请求适配为统一 Experiment 契约。"""

    def __init__(self, request: StrategyBacktestRequest) -> None:
        self.request = request

    def run(self) -> StrategyBacktestResponse:
        return run_strategy_backtest(self.request, data_engine=DataEngine.get_instance())


__all__ = ["StrategyExperiment"]
