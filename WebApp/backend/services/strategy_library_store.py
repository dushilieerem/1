# -*- coding: utf-8 -*-
"""平台策略库：读 SVQuant/Strategy/libraries（index.yaml + 源码）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# WebApp/backend/services → SVQuant/
_SVQUANT_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_LIB_DIR = _SVQUANT_ROOT / "Strategy" / "libraries"
INDEX_PATH = STRATEGY_LIB_DIR / "index.yaml"

STRATEGY_TYPE_LABELS = {
    "trend": "趋势",
    "momentum": "动量",
    "reversal": "反转",
    "low_volatility": "低波动",
    "minimum_variance": "最小方差",
    "statistical_arbitrage": "统计套利",
    "small_cap": "小市值",
    "custom": "自定义",
}


def libraries_root() -> Path:
    return STRATEGY_LIB_DIR


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        raise FileNotFoundError(f"策略库索引不存在: {INDEX_PATH}")
    raw = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("index.yaml 格式无效")
    return raw


def list_builtin_strategies() -> dict[str, Any]:
    idx = load_index()
    strategies = idx.get("strategies") or {}
    items: list[dict[str, Any]] = []
    for sid, meta in strategies.items():
        if not isinstance(meta, dict):
            continue
        stype = str(meta.get("strategy_type") or "custom")
        cur = str(meta.get("current_version") or "v1")
        versions = meta.get("versions") or {}
        ver = versions.get(cur) if isinstance(versions, dict) else None
        file_name = ""
        entrypoint = ""
        if isinstance(ver, dict):
            file_name = str(ver.get("file") or "")
            entrypoint = str(ver.get("entrypoint") or "")
        items.append(
            {
                "id": str(sid),
                "name": str(meta.get("name") or sid),
                "strategy_type": stype,
                "strategy_type_label": STRATEGY_TYPE_LABELS.get(stype, stype),
                "execution_mode": str(meta.get("execution_mode") or "vectorized"),
                "current_version": cur,
                "tags": list(meta.get("tags") or []),
                "file": file_name,
                "entrypoint": entrypoint,
                "source": "builtin",
            }
        )
    items.sort(key=lambda x: (x["strategy_type_label"], x["name"], x["id"]))
    return {
        "ok": True,
        "index_version": idx.get("version"),
        "root": str(STRATEGY_LIB_DIR),
        "total": len(items),
        "items": items,
    }


def get_strategy_source(strategy_id: str, *, version: str | None = None) -> dict[str, Any]:
    sid = (strategy_id or "").strip()
    if not sid:
        raise ValueError("strategy_id 不能为空")
    idx = load_index()
    strategies = idx.get("strategies") or {}
    meta = strategies.get(sid)
    if not isinstance(meta, dict):
        raise KeyError(f"未知策略: {sid}")
    cur = str(version or meta.get("current_version") or "v1")
    versions = meta.get("versions") or {}
    ver = versions.get(cur) if isinstance(versions, dict) else None
    if not isinstance(ver, dict):
        raise KeyError(f"策略 {sid} 无版本 {cur}")
    file_name = str(ver.get("file") or "").strip()
    if not file_name:
        raise ValueError(f"策略 {sid}@{cur} 未声明 file")
    path = STRATEGY_LIB_DIR / file_name
    if not path.is_file():
        raise FileNotFoundError(f"源码不存在: {path}")
    # 防目录穿越
    if not path.resolve().is_relative_to(STRATEGY_LIB_DIR.resolve()):
        raise PermissionError("非法路径")
    code = path.read_text(encoding="utf-8")
    stype = str(meta.get("strategy_type") or "custom")
    return {
        "ok": True,
        "id": sid,
        "name": str(meta.get("name") or sid),
        "strategy_type": stype,
        "strategy_type_label": STRATEGY_TYPE_LABELS.get(stype, stype),
        "execution_mode": str(meta.get("execution_mode") or "vectorized"),
        "version": cur,
        "file": file_name,
        "entrypoint": str(ver.get("entrypoint") or ""),
        "tags": list(meta.get("tags") or []),
        "strategy_code": code,
        "source": "builtin",
    }
