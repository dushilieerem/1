"""统一实验契约。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar



TResult = TypeVar("TResult")




class Experiment(ABC, Generic[TResult]):
    """所有可由 ExperimentManager 执行的实验。"""

    @abstractmethod
    def run(self) -> TResult:
        """执行任务；共享数据由全局 DataEngine 直接提供。"""

        raise NotImplementedError


__all__ = ["Experiment", "TResult"]
