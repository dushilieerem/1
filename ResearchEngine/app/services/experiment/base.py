"""统一实验契约与只读执行上下文。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.core.runtime import ResearchDataContext


TResult = TypeVar("TResult")


@dataclass(frozen=True)
class ExperimentContext:
    """由应用级 Manager 持有的只读行情上下文。"""

    market: ResearchDataContext

    @property
    def data_engine(self):
        """返回固定 release 的 DataEngine；实验不得替换或关闭它。"""

        return self.market.data_engine

    @property
    def provider(self):
        """返回固定 release 的数据 provider。"""

        return self.market.provider


class Experiment(ABC, Generic[TResult]):
    """所有可由 ExperimentManager 执行的实验。"""

    @abstractmethod
    def run(self, context: ExperimentContext) -> TResult:
        """在 Manager 提供的只读行情上下文中执行实验。"""

        raise NotImplementedError


__all__ = ["Experiment", "ExperimentContext", "TResult"]
