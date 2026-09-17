"""Experiment 抽象契约验收。"""

from __future__ import annotations

import pytest

from app.services.experiment.base import Experiment
from app.services.experiment.manager import ExperimentManager


def test_experiment_is_abstract_and_manager_rejects_callable():
    with pytest.raises(TypeError):
        Experiment()  # type: ignore[abstract]

    manager = ExperimentManager(max_workers=1, max_queue_size=0)
    try:
        with pytest.raises(TypeError, match="只接受 Experiment"):
            manager.submit(lambda: None)  # type: ignore[arg-type]
    finally:
        manager.shutdown()
