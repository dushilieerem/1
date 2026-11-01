# -*- coding: utf-8 -*-
"""投研数据底座状态（R03 / FEAT-010）。

只读数据平台视图：报告 view_id、契约版本、关键数据集是否存在与覆盖范围，
供研究/回测记录数据版本；不做采集。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.data.platform_view import materialized_view_root

REQUIRED = (
    "daily_bars",
    "daily_bars_unadjusted",
    "valuation_daily",
    "industry_daily",
    "security_status_daily",
    "financial_income",
    "financial_balance",
    "financial_cashflow",
    "pershare_index",
    "calendar",
    "index_price",
    "index_membership",
)


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def foundation_status() -> dict[str, Any]:
    root = materialized_view_root()
    if root is None:
        return {"ok": False, "reason": "view_not_configured", "datasets": []}
    manifest = _manifest(root)
    datasets = manifest.get("datasets") or {}
    rows: list[dict[str, Any]] = []
    for name in REQUIRED:
        item = datasets.get(name) or {}
        path = (root / item["path"]) if item.get("path") else (root / "derived" / name)
        rows.append(
            {
                "name": name,
                "available": path.exists(),
                "coverage_start": item.get("date_min") or item.get("coverage_start"),
                "coverage_end": item.get("date_max") or item.get("coverage_end"),
                "rows": item.get("rows"),
            }
        )
    missing = [row["name"] for row in rows if not row["available"]]
    return {
        "ok": not missing,
        "view_id": manifest.get("view_id"),
        "contract_version": manifest.get("contract_version"),
        "generated_at": manifest.get("generated_at"),
        "required": len(REQUIRED),
        "missing": missing,
        "datasets": rows,
    }


__all__ = ["foundation_status", "REQUIRED"]
