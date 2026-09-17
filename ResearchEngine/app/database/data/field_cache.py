"""进程内行情字段缓存。

缓存只保存活动 release 的完整原始行情字段，不保存因子值、任务切片或回测结果。
一个应用级 ``DataEngine`` 将缓存显式注入其 ``FieldParquetProvider``；缓存本身线程安全，
并会合并同一键的并发首次加载。缓存没有容量上限：活动 release 在 FastAPI
启动时完整预热，Experiment 只从这里复制自己的任务数据。
"""

from __future__ import annotations

import sys
import threading
from concurrent.futures import Future
from typing import Any, Callable, Hashable


class FieldFrameCache:
    """无容量上限、线程安全且支持并发合并的活动 release 字段缓存。"""

    def __init__(self) -> None:
        self._entries: dict[Hashable, tuple[Any, int]] = {}
        self._pending: dict[Hashable, Future[Any]] = {}
        self._bytes = 0
        self._peak_bytes = 0
        self._hits = 0
        self._misses = 0
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

    def put(self, key: Hashable, value: Any) -> None:
        """写入完整字段；缓存生命周期随活动 release 和进程结束。"""

        size = self.estimate_bytes(value)
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._bytes -= previous[1]
            self._entries[key] = (value, size)
            self._bytes += size
            self._peak_bytes = max(self._peak_bytes, self._bytes)

    def clear(self) -> None:
        """清空已完成的缓存项；不打断正在加载的任务。"""

        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "bytes": self._bytes,
                "peak_bytes": self._peak_bytes,
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "pending": len(self._pending),
            }


__all__ = [
    "FieldFrameCache",
]
