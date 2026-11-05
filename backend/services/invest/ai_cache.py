# -*- coding: utf-8 -*-
"""Invest AI 结果落盘缓存。

按 user_id + 命名空间 + 输入哈希存 JSON 文件，刷新（重新生成）时覆盖同一键。
不设 TTL：输入数据或提示词变化会生成新键；旧键保留，便于回看与排查。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2] / "data" / "invest_ai_cache"


def make_key(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path(user_id: int | None, namespace: str, key: str) -> Path:
    uid = str(int(user_id or 0))
    safe_ns = "".join(c if c.isalnum() or c in "-_." else "_" for c in namespace)[:80] or "default"
    return ROOT / uid / safe_ns / f"{key[:64]}.json"


def get(user_id: int | None, namespace: str, key: str) -> dict[str, Any] | None:
    path = _path(user_id, namespace, key)
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def put(user_id: int | None, namespace: str, key: str, value: dict[str, Any]) -> None:
    path = _path(user_id, namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**value, "cached_at": int(time.time())}
    fd, tmp = tempfile.mkstemp(prefix=".ai-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def clear(user_id: int | None, namespace: str | None = None) -> int:
    base = ROOT / str(int(user_id or 0))
    target = base / namespace if namespace else base
    removed = 0
    if not target.exists():
        return 0
    for path in target.rglob("*.json"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


__all__ = ["clear", "get", "make_key", "put"]
