"""因子批量回测的只读查询用例。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.factor_backtest import FactorBacktestRepository


class FactorBacktestBatchQuery:
    """向 API 提供批次、因子明细和历史查询，不执行回测。"""

    def __init__(
        self,
        repository: FactorBacktestRepository | None = None,
        *,
        db_path: str | Path | None = None,
    ) -> None:
        if repository is not None and db_path is not None:
            raise ValueError("repository 与 db_path 不能同时指定")
        self.repository = repository or FactorBacktestRepository(db_path)

    def list_batches(self, **filters: Any) -> list[dict[str, Any]]:
        return self.repository.list_batches(**filters)

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        return self.repository.get_batch(batch_id)

    def list_factor_runs(self, batch_id: str, **filters: Any) -> list[dict[str, Any]]:
        return self.repository.list_factor_runs(batch_id, **filters)

    def factor_history(
        self,
        library_name: str,
        factor_name: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        return self.repository.factor_history(library_name, factor_name, **filters)


__all__ = ["FactorBacktestBatchQuery"]
