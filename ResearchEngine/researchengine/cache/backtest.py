"""因子回测本地文件缓存。"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class FileBacktestCache:
    """保存完整 API 响应的可再生本地缓存。"""

    # v4: 因子计算改用未复权 OHLC、收益计算改用后复权 close。
    version = "factor-backtest-v4"

    def __init__(self, root: Path, ttl_days: int = 30, max_bytes: int = 10 * 1024**3):
        self.root = Path(root)
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        self.max_bytes = max_bytes

    @staticmethod
    def make_key(request: dict[str, Any], data_fingerprint: str) -> str:
        payload = {
            "cache_version": FileBacktestCache.version,
            "request": request,
            "data_fingerprint": data_fingerprint,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def data_fingerprint(data_dir: Path) -> str:
        """用行情与基准 Parquet 的路径、大小和修改时间生成数据指纹。"""
        rows = []
        for path in sorted(data_dir.rglob("*.parquet")):
            stat = path.stat()
            rows.append((str(path.relative_to(data_dir)), stat.st_size, stat.st_mtime_ns))
        encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _data_path(self, key: str) -> Path:
        return self.root / f"{key}.json.gz"

    def _meta_path(self, key: str) -> Path:
        return self.root / f"{key}.meta.json"

    def _lock_path(self, key: str) -> Path:
        return self.root / f"{key}.lock"

    @contextmanager
    def lock(self, key: str, wait_seconds: float = 10.0):
        """同键请求的短生命周期写锁；超时后调用方可降级自行计算。"""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._lock_path(key)
        deadline = time.monotonic() + wait_seconds
        acquired = False
        while time.monotonic() < deadline:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.05)
        try:
            yield acquired
        finally:
            if acquired:
                path.unlink(missing_ok=True)

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._data_path(key)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                payload = json.load(fh)
            now = time.time()
            if now - path.stat().st_mtime > self.ttl_seconds:
                self.delete(key)
                return None
            os.utime(path, None)
            return payload
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self._data_path(key)
        tmp = target.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, target)
        self._meta_path(key).write_text(
            json.dumps({"created_at": time.time(), "size": target.stat().st_size}),
            encoding="utf-8",
        )
        self.cleanup()

    def delete(self, key: str) -> None:
        for path in (self._data_path(key), self._meta_path(key)):
            path.unlink(missing_ok=True)

    def cleanup(self) -> None:
        if not self.root.exists():
            return
        now = time.time()
        entries = []
        for path in self.root.glob("*.json.gz"):
            if now - path.stat().st_mtime > self.ttl_seconds:
                self.delete(path.name.removesuffix(".json.gz"))
            else:
                entries.append(path)
        total = sum(path.stat().st_size for path in entries)
        for path in sorted(entries, key=lambda item: item.stat().st_mtime):
            if total <= self.max_bytes:
                break
            total -= path.stat().st_size
            self.delete(path.name.removesuffix(".json.gz"))
