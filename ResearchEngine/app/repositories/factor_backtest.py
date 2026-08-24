"""因子批量回测的 SQLite 持久化边界。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.factor_backtest_store import FactorBacktestStore


class FactorBacktestRepository:
    """把 SQLite 存储细节隔离在 repository 层。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.store = FactorBacktestStore(path)

    # 写入方法只做持久化边界转发；批次幂等、重试和窗口编排仍属于
    # FactorBacktestBatchCoordinator，不下沉到通用 repository。
    def get_batch_by_key(self, batch_key: str) -> dict[str, Any] | None:
        return self.store.get_batch_by_key(batch_key)

    def create_batch(self, **payload: Any) -> dict[str, Any]:
        return self.store.create_batch(**payload)

    def mark_batch_running(self, batch_id: str) -> None:
        self.store.mark_batch_running(batch_id)

    def mark_batch_failed(
        self,
        batch_id: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.store.mark_batch_failed(
            batch_id,
            error_code=error_code,
            error_message=error_message,
        )

    def ensure_factor_run(self, **payload: Any) -> dict[str, Any]:
        return self.store.ensure_factor_run(**payload)

    def mark_factor_running(self, factor_run_id: str) -> None:
        self.store.mark_factor_running(factor_run_id)

    def record_factor(self, factor_run_id: str, **payload: Any) -> None:
        self.store.record_factor(factor_run_id, **payload)

    def refresh_batch_counts(self, batch_id: str, *, final: bool = False) -> dict[str, Any]:
        return self.store.refresh_batch_counts(batch_id, final=final)

    def list_batches(self, **filters: Any) -> list[dict[str, Any]]:
        return self.store.list_batches(**filters)

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        return self.store.get_batch(batch_id)

    def list_factor_runs(self, batch_id: str, **filters: Any) -> list[dict[str, Any]]:
        return self.store.list_factor_runs(batch_id, **filters)

    def factor_history(
        self,
        library_name: str,
        factor_name: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        return self.store.factor_history(library_name, factor_name, **filters)


__all__ = ["FactorBacktestRepository"]
