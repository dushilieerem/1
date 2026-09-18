# -*- coding: utf-8 -*-
"""分块策略插件登记处。新增策略：实现模块 → 在 REGISTRY 注册。"""
from __future__ import annotations

from typing import Any, Callable

ChunkFn = Callable[..., list[dict[str, Any]]]

# id -> { label_zh, description, fn, default_options }
REGISTRY: dict[str, dict[str, Any]] = {}


def register(
    strategy_id: str,
    *,
    label_zh: str,
    description: str = "",
    default_options: dict[str, Any] | None = None,
) -> Callable[[ChunkFn], ChunkFn]:
    def deco(fn: ChunkFn) -> ChunkFn:
        REGISTRY[strategy_id] = {
            "id": strategy_id,
            "labelZh": label_zh,
            "description": description,
            "defaultOptions": default_options or {},
            "fn": fn,
        }
        return fn

    return deco


def list_strategies() -> list[dict[str, Any]]:
    _ensure_builtins()
    return [
        {
            "id": v["id"],
            "labelZh": v["labelZh"],
            "description": v.get("description") or "",
            "defaultOptions": v.get("defaultOptions") or {},
        }
        for v in REGISTRY.values()
    ]


def get_strategy(strategy_id: str) -> dict[str, Any]:
    _ensure_builtins()
    sid = (strategy_id or "").strip()
    if sid not in REGISTRY:
        raise ValueError(f"未知分块策略: {sid}")
    return REGISTRY[sid]


def chunk_text(
    text: str,
    strategy_id: str,
    options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    meta = get_strategy(strategy_id)
    opts = {**(meta.get("defaultOptions") or {}), **(options or {})}
    return meta["fn"](text or "", **opts)


_BUILTINS_LOADED = False


def _ensure_builtins() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    # side-effect imports register strategies
    from knowledge_hub.chunking import strategies as _strategies  # noqa: F401

    _BUILTINS_LOADED = True
