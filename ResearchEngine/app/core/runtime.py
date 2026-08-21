"""app 进程级回测运行时。

``ExperimentManager`` 持有一个 ``ResearchRuntime``，由它统一提供当前
MarketData release 的 ``DataEngine`` 和字段缓存。运行时只缓存原始行情字段
及其日期/股票池切片，不缓存因子值或回测结果。
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from app.quantcore import DataEngine, FieldParquetProvider
from app.quantcore.data.field_cache import (
    FieldFrameCache,
    field_cache_max_bytes_from_env,
    get_process_field_cache,
)
from app.quantcore.data.providers.field_parquet_provider import _release_signature


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    return Path(
        os.environ.get("SVQUANT_DATA_DIR", _repo_root() / "MarketData")
    )


def _effective_data_dir(data_dir: str | Path) -> Path:
    path = Path(data_dir).expanduser().resolve()
    if path.is_file():
        return path.parent
    current = path / "current"
    return current if current.is_dir() else path


def _release_hint(data_dir: str | Path) -> tuple[Path, str]:
    effective = _effective_data_dir(data_dir)
    panels = effective / "panels"
    panels_dir = panels if panels.is_dir() else effective
    benchmark = effective / "benchmark"
    return effective, _release_signature(effective, panels_dir, benchmark)


@dataclass(frozen=True)
class ResearchDataContext:
    """一个固定 release 的只读数据上下文。"""

    data_dir: Path
    release_id: str
    provider: FieldParquetProvider
    data_engine: DataEngine


class ResearchRuntime:
    """由进程级 ``ExperimentManager`` 持有的共享回测运行时。"""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        *,
        cache: FieldFrameCache | None = None,
        max_cache_bytes: int | None = None,
    ) -> None:
        if cache is not None and max_cache_bytes is not None:
            raise ValueError("cache 与 max_cache_bytes 不能同时指定")
        if cache is None:
            cache = get_process_field_cache(
                field_cache_max_bytes_from_env()
                if max_cache_bytes is None
                else max_cache_bytes
            )
        self.default_data_dir = (
            None
            if data_dir is None
            else Path(data_dir).expanduser().resolve()
        )
        self.cache = cache
        self._context: ResearchDataContext | None = None
        self._lock = threading.RLock()
        self._closed = False

    def get_context(
        self,
        data_dir: str | Path | None = None,
    ) -> ResearchDataContext:
        """返回当前 release 上下文，release 变化时原子替换。"""

        requested = Path(
            data_dir or self.default_data_dir or default_data_dir()
        ).expanduser().resolve()
        effective, release_hint = _release_hint(requested)
        with self._lock:
            if self._closed:
                raise RuntimeError("ResearchRuntime 已关闭")
            current = self._context
            if (
                current is not None
                and current.data_dir == effective
                and current.release_id == release_hint
            ):
                return current

            provider = FieldParquetProvider(requested, cache=self.cache)
            context = ResearchDataContext(
                data_dir=provider.data_dir.resolve(),
                release_id=provider.release_id,
                provider=provider,
                data_engine=DataEngine(provider),
            )
            self._context = context
            return context

    def get_data_engine(self, data_dir: str | Path | None = None) -> DataEngine:
        return self.get_context(data_dir).data_engine

    def cache_stats(self) -> dict[str, int]:
        return self.cache.stats()

    def close(self) -> None:
        """释放上下文引用；正在运行的任务由 Manager 先等待完成。"""

        with self._lock:
            self._context = None
            self._closed = True


__all__ = [
    "ResearchDataContext",
    "ResearchRuntime",
    "default_data_dir",
]
