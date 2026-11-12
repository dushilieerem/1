# -*- coding: utf-8 -*-
"""年报章节页读取：数据业务的 doc_page_text / section_index → 机构端可用的章节文本。

发布物（只读）：
  <release>/page_text/year=YYYY/part.parquet
  <release>/section_index/report_period=YYYY-MM-DD/part.parquet

机构端不直接扫 3GB 原始页文本，而是读 scripts/ops/build_doc_section_cache.py
裁出来的单文件缓存（按 symbol 排序），按 symbol+section 取最近一期年报的章节页。

约定：
- PIT：available_time <= as_of；
- 只返回年报（doc_type=annual）最近一期；
- 缓存缺失、pyarrow 缺失、无该股票时返回 None/空，不抛错、不阻断研究。
"""
from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

SECTIONS: tuple[str, ...] = (
    "公司治理",
    "股份质押冻结",
    "承诺事项",
    "关联交易",
    "对外担保",
    "董监高变动",
)

DEFAULT_CACHE = "backend/output/doc_sections_pagetext-20261112.parquet"


def cache_path() -> Path:
    raw = os.getenv("SVQUANT_DOC_SECTIONS_PARQUET") or DEFAULT_CACHE
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[3] / path
    return path


def available() -> bool:
    return cache_path().exists()


@lru_cache(maxsize=4)
def _dataset(path_str: str):
    import pyarrow.dataset as ds

    return ds.dataset(path_str, format="parquet")


def _rows(symbol: str, as_of: str, section: str | None = None) -> list[dict[str, Any]]:
    if not available():
        return []
    import pyarrow.compute as pc

    dataset = _dataset(str(cache_path()))
    expr = (pc.field("symbol") == symbol) & (pc.field("available_time") <= as_of)
    if section:
        expr = expr & (pc.field("section_name") == section)
    table = dataset.to_table(
        columns=["symbol", "doc_id", "report_period", "section_name", "page_no", "text", "source_sha256", "pdf_url", "available_time"],
        filter=expr,
    )
    rows = table.to_pylist()
    if not rows:
        return []
    latest = max(str(r.get("report_period") or "") for r in rows)
    rows = [r for r in rows if str(r.get("report_period") or "") == latest]
    rows.sort(key=lambda r: (str(r.get("section_name")), int(str(r.get("page_no") or "0") or 0)))
    return rows


def sections(symbol: str, as_of: str | None = None) -> dict[str, dict[str, Any]]:
    """symbol 最近一期年报的六节页文本（按节聚合，页内文本原样）。"""
    as_of = (as_of or date.today().isoformat())[:10]
    rows = _rows(symbol, as_of)
    if not rows:
        return {}
    doc_id = str(rows[0].get("doc_id") or "")
    report_period = str(rows[0].get("report_period") or "")
    available_time = str(rows[0].get("available_time") or "")[:10]
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("doc_id")) != doc_id:
            continue
        name = str(row.get("section_name") or "")
        block = out.setdefault(
            name,
            {"section": name, "doc_id": doc_id, "report_period": report_period, "available_time": available_time, "pages": []},
        )
        block["pages"].append(
            {
                "page_no": int(str(row.get("page_no") or "0") or 0),
                "text": row.get("text") or "",
                "pdf_url": row.get("pdf_url"),
                "source_sha256": row.get("source_sha256"),
            }
        )
    for block in out.values():
        block["char_count"] = sum(len(p["text"]) for p in block["pages"])
    return out


def section_text(
    symbol: str,
    section: str,
    *,
    as_of: str | None = None,
    max_chars: int = 14000,
    keywords: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """单节页文本，按字符上限截断（保留页边界，供 LLM 引用页码）。

    给了 keywords 时，先保留命中关键词的页（同组内保持原顺序），再用未命中的页补足，
    避免章节首尾的无关页把真正的表格挤出上下文。
    """
    blocks = sections(symbol, as_of)
    block = blocks.get(section)
    if not block:
        return None
    pages = list(block["pages"])
    if keywords:
        hit = [p for p in pages if any(k in (p["text"] or "") for k in keywords)]
        miss = [p for p in pages if p not in hit]
        pages = hit + miss
    kept: list[dict[str, Any]] = []
    used = 0
    for page in pages:
        text = page["text"]
        if used >= max_chars:
            break
        remaining = max_chars - used
        kept.append({**page, "text": text[:remaining]})
        used += min(len(text), remaining)
    kept.sort(key=lambda p: p["page_no"])
    return {
        "symbol": symbol,
        "section": section,
        "doc_id": block["doc_id"],
        "report_period": block["report_period"],
        "available_time": block["available_time"],
        "pages": kept,
        "truncated": used < block["char_count"],
        "char_count": block["char_count"],
        "text": "\n".join(f"[第{p['page_no']}页]\n{p['text']}" for p in kept),
    }


def latest_report_period(symbol: str, as_of: str | None = None) -> str | None:
    blocks = sections(symbol, as_of)
    if not blocks:
        return None
    return next(iter(blocks.values())).get("report_period")


__all__ = [
    "SECTIONS",
    "available",
    "cache_path",
    "latest_report_period",
    "section_text",
    "sections",
]
