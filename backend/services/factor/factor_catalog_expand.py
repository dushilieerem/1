# -*- coding: utf-8 -*-
"""将 index.yaml 中未列全的库展开为可展示的 factors 列表。

- 经典 / 聚宽库：AST 解析 .py 类内公开方法 + docstring
- alpha_features：按 alpha_features.py 动态注册规则生成 alpha158_/alpha360_（不依赖 import quantcore）
- qlib_alpha：旧命名 qlib_alpha158_/qlib_alpha360_（兼容历史）
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

FACTOR_DIR = Path(__file__).resolve().parents[2] / "factor"

_QLIB_KBAR = (
    "kmid",
    "klen",
    "kmid2",
    "kup",
    "kup2",
    "klow",
    "klow2",
    "ksft",
    "ksft2",
)
_QLIB_ROLLING = (
    "roc",
    "ma",
    "std",
    "beta",
    "rsqr",
    "resi",
    "max",
    "min",
    "qtlu",
    "qtld",
    "rank",
    "rsv",
    "imax",
    "imin",
    "imxd",
    "corr",
    "cord",
    "cntp",
    "cntn",
    "cntd",
    "sump",
    "sumn",
    "sumd",
    "vma",
    "vstd",
    "wvma",
    "vsump",
    "vsumn",
    "vsumd",
)
_QLIB_WINDOWS = (5, 10, 20, 30, 60)
_QLIB_360_FIELDS = ("close", "open", "high", "low", "vwap", "volume")


def _doc_first_line(doc: str | None) -> str:
    if not doc:
        return ""
    return doc.strip().split("\n", 1)[0].strip()


def factors_from_py(file_name: str) -> list[dict[str, Any]]:
    path = FACTOR_DIR / file_name
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    out: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name.startswith("_"):
                continue
            doc = _doc_first_line(ast.get_docstring(item))
            out.append(
                {
                    "name": item.name,
                    "description": doc or item.name,
                    "tags": [],
                }
            )
    return out


def _factors_alpha_style(*, prefix158: str, prefix360: str) -> list[dict[str, Any]]:
    """生成 Alpha158/360 特征名列表（与 alpha_features.py / 旧 qlib_alpha 规则一致）。"""
    out: list[dict[str, Any]] = []
    for field in _QLIB_360_FIELDS:
        for day in range(60):
            out.append(
                {
                    "name": f"{prefix360}{field}{day}",
                    "description": f"Alpha360 {field.upper()}{day}",
                    "tags": ["alpha360", field],
                }
            )
    for suffix in _QLIB_KBAR:
        out.append(
            {
                "name": f"{prefix158}{suffix}",
                "description": f"Alpha158 {suffix.upper()}",
                "tags": ["alpha158", "kbar"],
            }
        )
    for field in ("open", "high", "low", "vwap"):
        out.append(
            {
                "name": f"{prefix158}{field}0",
                "description": f"Alpha158 {field.upper()}0",
                "tags": ["alpha158", field],
            }
        )
    for window in _QLIB_WINDOWS:
        for suffix in _QLIB_ROLLING:
            out.append(
                {
                    "name": f"{prefix158}{suffix}{window}",
                    "description": f"Alpha158 {suffix.upper()}{window}",
                    "tags": ["alpha158", "rolling", f"w{window}"],
                    "params": {"window": window},
                }
            )
    return out


def factors_alpha_features() -> list[dict[str, Any]]:
    """同事新库 alpha_features：alpha158_* / alpha360_*。"""
    return _factors_alpha_style(prefix158="alpha158_", prefix360="alpha360_")


def factors_qlib_alpha() -> list[dict[str, Any]]:
    """旧库命名兼容：qlib_alpha158_* / qlib_alpha360_*。"""
    return _factors_alpha_style(prefix158="qlib_alpha158_", prefix360="qlib_alpha360_")


def expand_lib_factors(lib_key: str, lib: dict[str, Any]) -> list[dict[str, Any]]:
    """返回最终 factors；已有显式列表则原样返回（custom_lib 除外也可保留）。"""
    listed = list(lib.get("factors") or [])
    file_name = str(lib.get("file") or "").strip()
    # 动态注册库：即使 yaml 写了空 factors / generated，也按规则展开
    if lib_key == "alpha_features" or file_name == "alpha_features.py":
        return factors_alpha_features()
    if lib_key == "qlib_alpha" or file_name == "qlib_alpha.py":
        return factors_qlib_alpha()
    if listed:
        return listed
    if not file_name:
        return []
    return factors_from_py(file_name)


def expand_index(index: dict[str, Any]) -> dict[str, Any]:
    """深拷贝式展开：补全各库 factors，并重算 total_factors。"""
    libs_in = index.get("libraries") or {}
    libs_out: dict[str, Any] = {}
    total = 0
    for key, lib in libs_in.items():
        if not isinstance(lib, dict):
            libs_out[key] = lib
            continue
        factors = expand_lib_factors(key, lib)
        lib2 = {**lib, "factors": factors, "factor_count": len(factors)}
        libs_out[key] = lib2
        total += len(factors)
    return {**index, "libraries": libs_out, "total_factors": total}


def merge_source_name(factors: list[dict[str, Any]], lib: dict[str, Any]) -> list[dict[str, Any]]:
    """若 yaml 里已有 factors 带 source_name，保留；展开项无需处理。"""
    return factors
