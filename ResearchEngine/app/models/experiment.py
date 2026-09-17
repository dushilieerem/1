"""实验输入与任务状态数据。"""

from __future__ import annotations

import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Literal, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.experiment.base import Experiment
    from app.services.data.engine import DataEngine

T = TypeVar("T")
ExecutionLane = Literal["interactive", "batch"]


class ExperimentStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class _ExperimentRun(Generic[T]):
    run_id: str
    experiment: Experiment[T]
    key: str | None
    lane: ExecutionLane
    metadata: dict[str, Any]
    status: ExperimentStatus = ExperimentStatus.CREATED
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    future: Future[T] = field(default_factory=Future)
    result: T | None = None
    error: str | None = None
    cancel_requested: bool = False
    capacity_released: bool = False
