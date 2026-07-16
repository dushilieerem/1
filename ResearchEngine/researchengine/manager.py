"""``ExperimentManager`` - ResearchEngine 的核心，负责组织实验流程。

依据 ``docs/04-features/FEAT-002-research-engine/04-class-design.md`` ExperimentManager 节与 ``docs/04-features/FEAT-002-research-engine/05-runtime-flow.md``：

    属性：
      experiments: Dict[str, Experiment]

    方法：
      create(factor, universe, start, end, config) -> Experiment
      run(experiment: Experiment) -> ResultManager
      run_all() -> Dict[str, ResultManager]

**关键原则**：ExperimentManager 只组织流程，不计算收益、不计算因子、不计算指标。
"""

from __future__ import annotations

from typing import Dict, Optional

from quantcore import BaseFactor

from researchengine.config import ConfigManager
from researchengine.experiment import Experiment
from researchengine.result.manager import ResultManager


class ExperimentManager:
    """实验管理器（只编排）。"""

    def __init__(self) -> None:
        self.experiments: Dict[str, Experiment] = {}

    def create(
        self,
        factor: BaseFactor,
        universe: str = "CSI500",
        start: str = "2020-01-01",
        end: str = "2024-12-31",
        config: Optional[ConfigManager] = None,
    ) -> Experiment:
        """创建一个实验并登记。"""
        exp = Experiment(
            factor=factor,
            universe=universe,
            start_date=start,
            end_date=end,
            config=config,
        )
        self.experiments[factor.name] = exp
        return exp

    def run(self, experiment: Experiment) -> ResultManager:
        """运行单个实验。"""
        return experiment.run()

    def run_all(self) -> Dict[str, ResultManager]:
        """运行全部已登记实验。"""
        results: Dict[str, ResultManager] = {}
        for name, exp in self.experiments.items():
            results[name] = exp.run()
        return results

    def get(self, name: str) -> Optional[Experiment]:
        return self.experiments.get(name)
