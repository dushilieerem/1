"""进程级字段缓存与共享面板测试。"""

from __future__ import annotations

import threading
import time

import pandas as pd

from app.quantcore import FieldParquetProvider
from app.quantcore.data.field_cache import FieldFrameCache


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
    cache = FieldFrameCache(max_bytes=1024 * 1024)
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


def test_provider_reuses_date_and_symbol_slice(tmp_path):
    _write_fields(tmp_path)
    cache = FieldFrameCache(max_bytes=1024 * 1024)
    provider = FieldParquetProvider(tmp_path, cache=cache)

    first = provider.get_panels(
        "2024-01-02", "2024-01-03", fields=["close"]
    )["close"]
    second = provider.get_panels(
        "2024-01-02", "2024-01-03", fields=["close"]
    )["close"]

    assert first is second
    assert list(first.columns) == ["A", "B"]
    assert len(first) == 2
    assert cache.stats()["hits"] >= 1


def test_lru_never_exceeds_configured_bytes(tmp_path):
    _write_fields(tmp_path)
    probe = FieldParquetProvider(tmp_path, cache=FieldFrameCache(max_bytes=1024 * 1024))
    size = probe._cache.estimate_bytes(probe._read_field("close"))
    cache = FieldFrameCache(max_bytes=size + 1)
    provider = FieldParquetProvider(tmp_path, cache=cache)

    provider._read_field("close")
    provider._read_field("open")

    stats = cache.stats()
    assert stats["bytes"] <= stats["max_bytes"]
    assert stats["evictions"] >= 1
