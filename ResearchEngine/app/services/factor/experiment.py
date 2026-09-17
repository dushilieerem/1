"""因子回测实验任务。"""

from __future__ import annotations

from typing import Any, Callable

from app.services.experiment.base import Experiment
from app.models.factor_backtest import FactorBacktestResult, FactorBacktestSpec


class FactorBacktestExperiment(Experiment[FactorBacktestResult]):
    """提交给 ExperimentManager 的因子回测任务。"""

    def __init__(
        self,
        spec: FactorBacktestSpec,
        *,
        engine=None,
        run_policy: Callable[[Callable[[], FactorBacktestResult]], Any] | None = None,
    ) -> None:
        from app.services.backtest.engine import BacktestEngine

        self.spec = spec
        self.engine = engine or BacktestEngine()
        self._run_policy = run_policy

    def run(self) -> FactorBacktestResult:
        execute = lambda: self.engine.run(self.spec)
        if self._run_policy is not None:
            return self._run_policy(execute)
        return execute()


__all__ = ["FactorBacktestExperiment"]
