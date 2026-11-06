# -*- coding: utf-8 -*-
"""数据平台 A 组（机构六维）只读访问。

约定：
- 表在 schema `svquant`，由数据业务 loader 写入；
- 所有查询按 available_time / report_date 做 PIT，不读未来数据；
- 表不存在/未加载时返回 None，调用方按数据缺口处理，不影响研究生成。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import psycopg


def _as_of(value: Any) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return date.today()


def _pit_upper(value: Any) -> str:
    # 截止日当天可见的数据都算已可用；不读次日及以后。
    return (_as_of(value) + timedelta(days=1)).isoformat()


def _query(conn, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]] | None:
    try:
        rows = conn.execute(sql, params).fetchall()
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        return None
    return [dict(r) for r in rows]


def holder_summary(
    conn, symbol: str, as_of: Any, *, float_only: bool = False
) -> dict[str, Any] | None:
    table = "svquant.holder_float_top10" if float_only else "svquant.holder_top10"
    rows = _query(
        conn,
        f"""
        WITH latest AS (
          SELECT MAX(report_date) AS d FROM {table}
           WHERE symbol=%s AND report_date <= %s AND available_time < %s
        )
        SELECT rank, holder_name, is_org, shares, ratio_pct, shares_type,
               change_text, change_ratio_pct, report_date, source, caliber
          FROM {table}, latest
         WHERE symbol=%s AND report_date=latest.d
           AND available_time < %s
         ORDER BY rank
        """,
        (symbol, _as_of(as_of), _pit_upper(as_of), symbol, _pit_upper(as_of)),
    )
    if not rows:
        return None
    total = sum(float(r.get("ratio_pct") or 0) for r in rows)
    top = rows[0]
    return {
        "report_date": str(top.get("report_date")),
        "count": len(rows),
        "top10_ratio_pct": round(total, 4),
        "top_holder": {
            "name": top.get("holder_name"),
            "ratio_pct": float(top.get("ratio_pct") or 0),
            "is_org": top.get("is_org"),
        },
        "holders": [
            {
                "rank": r.get("rank"),
                "name": r.get("holder_name"),
                "ratio_pct": float(r["ratio_pct"]) if r.get("ratio_pct") is not None else None,
                "shares": float(r["shares"]) if r.get("shares") is not None else None,
                "change_text": r.get("change_text"),
            }
            for r in rows[:10]
        ],
        "is_control_known": False,
        "note": "报告期前十大合计，未认定一致行动人；不代表控制权集中度，不能单独作为治理通过依据。",
        "source": top.get("source"),
        "caliber": top.get("caliber"),
    }


def segment_summary(
    conn,
    symbol: str,
    as_of: Any,
    *,
    consolidated_revenue: float | None = None,
) -> dict[str, Any] | None:
    rows = _query(
        conn,
        """
        WITH latest AS (
          SELECT MAX(report_date) AS d FROM svquant.segment_revenue
           WHERE symbol=%s AND report_date <= %s AND available_time < %s
        )
        SELECT report_date, segment_type, segment_name, revenue, share_pct,
               gross_profit, gross_margin_pct, source, caliber
          FROM svquant.segment_revenue, latest
         WHERE symbol=%s AND report_date=latest.d
           AND available_time < %s
         ORDER BY segment_type, revenue DESC NULLS LAST
        """,
        (symbol, _as_of(as_of), _pit_upper(as_of), symbol, _pit_upper(as_of)),
    )
    if not rows:
        return None
    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_type.setdefault(str(r.get("segment_type")), []).append(r)
    out: dict[str, Any] = {
        "report_date": str(rows[0].get("report_date")),
        "source": rows[0].get("source"),
        "types": {},
        "note": "分部收入来自年报主营构成；产品/地区/行业三类并列，不互相替代。",
    }
    for seg_type, items in by_type.items():
        total = sum(float(i.get("revenue") or 0) for i in items)
        out["types"][seg_type] = {
            "revenue_total": total,
            "items": [
                {
                    "name": i.get("segment_name"),
                    "revenue": float(i["revenue"]) if i.get("revenue") is not None else None,
                    "share_pct": float(i["share_pct"]) if i.get("share_pct") is not None else None,
                    "gross_margin_pct": (
                        float(i["gross_margin_pct"]) if i.get("gross_margin_pct") is not None else None
                    ),
                }
                for i in items[:8]
            ],
        }
    if consolidated_revenue:
        for seg_type, block in out["types"].items():
            deviation = (block["revenue_total"] - consolidated_revenue) / consolidated_revenue
            block["revenue_vs_consolidated_pct"] = round(deviation * 100, 4)
    return out


def audit_summary(conn, symbol: str, as_of: Any) -> dict[str, Any] | None:
    rows = _query(
        conn,
        """
        SELECT report_date, opinion_type, announce_date, available_time, source, caliber
          FROM svquant.audit_opinion
         WHERE symbol=%s AND report_date <= %s AND available_time < %s
         ORDER BY report_date DESC LIMIT 1
        """,
        (symbol, _as_of(as_of), _pit_upper(as_of)),
    )
    if not rows:
        return None
    row = rows[0]
    opinion = str(row.get("opinion_type") or "").strip()
    standard = "标准无保留" in opinion
    return {
        "report_date": str(row.get("report_date")),
        "opinion_type": opinion or None,
        "announce_date": str(row.get("announce_date") or "") or None,
        "is_standard": standard,
        "red_flag": bool(opinion) and not standard,
        "note": "仅审计意见类型；审计机构、KAM、问询函属 B 组。",
        "source": row.get("source"),
    }


__all__ = ["audit_summary", "holder_summary", "segment_summary"]
