"""进程级字段缓存与共享面板测试。"""

from __future__ import annotations

import threading
import time

import pandas as pd

from app.database.data.providers.field_parquet_provider import FieldParquetProvider
from app.database.data.field_cache import FieldFrameCache
from app.services.data.engine import DataEngine


def _write_fields(tmp_path):
    dates = pd.date_range("2024-01-02", periods=4, freq="D")
    for name, values in {
        "close": [10.0, 11.0, 12.0, 13.0],
        "open": [9.0, 10.0, 11.0, 12.0],
    }.items():
        pd.DataFrame({"datetime": dates, "A": values, "B": values}).to_parquet(
            tmp_path / f"{name}.parquet",
            index=False,
        )


def test_concurrent_cache_miss_executes_loader_once():
    cache = FieldFrameCache()
    calls = {"count": 0}
    lock = threading.Lock()

    def load():
        with lock:
            calls["count"] += 1
        time.sleep(0.05)
        return pd.DataFrame({"value": [1.0]})

    results = []

    def worker():
        results.append(cache.get_or_load("same", load))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["count"] == 1
    assert len(results) == 4
    assert all(result is results[0] for result in results)


def test_provider_reuses_complete_field_from_shared_cache(tmp_path):
    _write_fields(tmp_path)
    cache = FieldFrameCache()
    provider = FieldParquetProvider(tmp_path, cache=cache)

    first = provider.get_panels(
        "2024-01-02", "2024-01-03", fields=["close"]
    )["close"]
    second = provider.get_panels(
        "2024-01-02", "2024-01-03", fields=["close"]
    )["close"]

    pd.testing.assert_frame_equal(first, second)
    assert list(first.columns) == ["A", "B"]
    assert len(first) == 2
    assert cache.stats()["hits"] >= 1


def test_preloaded_field_cache_has_no_capacity_eviction_and_task_panels_are_isolated(tmp_path):
    _write_fields(tmp_path)
    cache = FieldFrameCache()
    provider = FieldParquetProvider(tmp_path, cache=cache)

    provider.preload_all_fields()
    shared_close = provider._read_field("close")
    first = provider.get_task_panels("2024-01-02", "2024-01-03", ["close"])["close"]
    second = provider.get_task_panels("2024-01-02", "2024-01-03", ["close"])["close"]
    first.iloc[0, 0] = -1.0

    stats = cache.stats()
    assert stats["entries"] == 2
    assert stats["bytes"] > 0
    assert shared_close.iloc[0, 0] == 10.0
    assert second.iloc[0, 0] == 10.0


def test_data_engine_load_does_not_preload_the_active_release(tmp_path):
    _write_fields(tmp_path)
    engine = DataEngine()
    engine.load_parquet(tmp_path)

    assert engine.cache_stats()["entries"] == 0
    engine.get_task_panels(fields=["close"])["close"]
    assert engine.cache_stats()["entries"] == 1
