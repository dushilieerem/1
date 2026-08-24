"""进程内行情字段缓存。

缓存只保存原始行情字段及其日期/股票池切片，不保存因子值或回测结果。
多个 ``FieldParquetProvider`` 可以共享同一个缓存对象；缓存本身线程安全，
并会合并同一键的并发首次加载，避免多个回测 Worker 重复读取同一份 Parquet。
"""

from __future__ import annotations

import os
import sys
import threading
from collections import OrderedDict
from concurrent.futures import Future
from typing import Any, Callable, Hashable


DEFAULT_FIELD_CACHE_MAX_BYTES = 2 * 1024**3


def field_cache_max_bytes_from_env() -> int:
    """读取进程级字段缓存上限。"""

    raw = os.environ.get("SVQUANT_FIELD_CACHE_MAX_BYTES")
    if raw is None:
        return DEFAULT_FIELD_CACHE_MAX_BYTES
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "SVQUANT_FIELD_CACHE_MAX_BYTES 必须是正整数"
        ) from exc
    if value <= 0:
        raise ValueError("SVQUANT_FIELD_CACHE_MAX_BYTES 必须大于 0")
    return value


class FieldFrameCache:
    """带字节上限、线程安全且支持并发合并的 LRU 缓存。"""

    def __init__(self, max_bytes: int | None = None) -> None:
        self.max_bytes = (
            field_cache_max_bytes_from_env()
            if max_bytes is None
            else int(max_bytes)
        )
        if self.max_bytes <= 0:
            raise ValueError("字段缓存上限必须大于 0")
        self._entries: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()
        self._pending: dict[Hashable, Future[Any]] = {}
        self._bytes = 0
        self._peak_bytes = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.RLock()

    @staticmethod
    def estimate_bytes(value: Any) -> int:
        """估算缓存对象占用的字节数。"""

        try:
            memory_usage = value.memory_usage(index=True, deep=True)
            return max(1, int(memory_usage.sum()))
        except Exception:  # pragma: no cover - 非 DataFrame 的兼容兜底
            return max(1, int(sys.getsizeof(value)))

    def get_or_load(self, key: Hashable, loader: Callable[[], Any]) -> Any:
        """读取缓存；未命中时只允许一个线程执行 ``loader``。"""

        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                self._hits += 1
                return cached[0]
            pending = self._pending.get(key)
            if pending is None:
                pending = Future()
                self._pending[key] = pending
                owner = True
                self._misses += 1
            else:
                owner = False

        if not owner:
            return pending.result()

        try:
            value = loader()
            self.put(key, value)
            pending.set_result(value)
            return value
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)

    def put(self, key: Hashable, value: Any) -> bool:
        """写入缓存；单项超过预算时返回 ``False`` 但不阻断调用方。"""

        size = self.estimate_bytes(value)
        if size > self.max_bytes:
            return False
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._bytes -= previous[1]
            self._entries[key] = (value, size)
            self._bytes += size
            self._peak_bytes = max(self._peak_bytes, self._bytes)
            while self._bytes > self.max_bytes and self._entries:
                old_key, (_, old_size) = self._entries.popitem(last=False)
                if old_key == key and self._bytes <= self.max_bytes:
                    self._bytes -= old_size
                    break
                self._bytes -= old_size
                self._evictions += 1
            return key in self._entries

    def clear(self) -> None:
        """清空已完成的缓存项；不打断正在加载的任务。"""

        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "max_bytes": self.max_bytes,
                "bytes": self._bytes,
                "peak_bytes": self._peak_bytes,
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "pending": len(self._pending),
            }


_PROCESS_CACHE: FieldFrameCache | None = None
_PROCESS_CACHE_LOCK = threading.Lock()


def get_process_field_cache(max_bytes: int | None = None) -> FieldFrameCache:
    """取得当前进程共享的默认字段缓存。"""

    global _PROCESS_CACHE
    with _PROCESS_CACHE_LOCK:
        if _PROCESS_CACHE is None:
            _PROCESS_CACHE = FieldFrameCache(max_bytes)
        elif max_bytes is not None and _PROCESS_CACHE.max_bytes != int(max_bytes):
            raise ValueError(
                "当前进程已创建字段缓存，不能使用不同的 max_bytes；"
                "请在进程启动前设置 SVQUANT_FIELD_CACHE_MAX_BYTES"
            )
        return _PROCESS_CACHE


def reset_process_field_cache() -> None:
    """测试和进程重启场景使用的缓存重置入口。"""

    global _PROCESS_CACHE
    with _PROCESS_CACHE_LOCK:
        _PROCESS_CACHE = None


__all__ = [
    "DEFAULT_FIELD_CACHE_MAX_BYTES",
    "FieldFrameCache",
    "field_cache_max_bytes_from_env",
    "get_process_field_cache",
    "reset_process_field_cache",
]
