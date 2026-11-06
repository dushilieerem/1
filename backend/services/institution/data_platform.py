# -*- coding: utf-8 -*-
"""数据平台 A 组（机构六维）只读访问。

约定：
- 表在 schema `svquant`，由数据业务 loader 写入；
- PIT 规则：`report_date <= as_of` 且 `available_time::date <= as_of`（available_time 是公告/可见时点 m_anntime，截止日当天公告可见）；
- 表不存在/未加载时返回 None，调用方按数据缺口处理，不影响研究生成。
"""
from __future__ import annotations

from datetime import date
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


def _query(conn, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]] | None:
    # 数据平台表可能尚未加载；用 savepoint 隔离失败，避免把调用方事务打成 aborted。
    savepoint = "data_platform_read"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        rows = conn.execute(sql, params).fetchall()
    except (
        psycopg.errors.UndefinedTable,
        psycopg.errors.UndefinedColumn,
        psycopg.errors.InvalidSchemaName,
    ):
        # 空库/未加载数据平台时 schema svquant 也不存在，按数据缺口返回，
        # 不能把研究生成打成 500。
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        return None
    else:
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
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
           WHERE symbol=%s AND report_date <= %s AND available_time::date <= %s
        )
        SELECT rank, holder_name, is_org, shares, ratio_pct, shares_type,
               change_text, change_ratio_pct, report_date, source, caliber
          FROM {table}, latest
         WHERE symbol=%s AND report_date=latest.d
           AND available_time::date <= %s
         ORDER BY rank
        """,
        (symbol, _as_of(as_of), _as_of(as_of), symbol, _as_of(as_of)),
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
           WHERE symbol=%s AND report_date <= %s AND available_time::date <= %s
             AND is_subitem = FALSE
        )
        SELECT report_date, segment_type, segment_name, revenue, share_pct,
               gross_profit, gross_margin_pct, source, caliber
          FROM svquant.segment_revenue, latest
         WHERE symbol=%s AND report_date=latest.d
           AND available_time::date <= %s
           AND is_subitem = FALSE
         ORDER BY segment_type, revenue DESC NULLS LAST
        """,
        (symbol, _as_of(as_of), _as_of(as_of), symbol, _as_of(as_of)),
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
        "note": "分部收入来自年报主营构成；产品/地区/行业三类并列，不互相替代；已剔除 is_subitem=true 的子项。",
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


def interest_debt_summary(conn, symbol: str, as_of: Any) -> dict[str, Any] | None:
    """有息负债/净债务/预收款（数据业务口径）。

    口径（2026-11-06 数据业务确认）：
    - interest_debt_total = 短期借款 + 一年内到期非流动负债 + 长期借款 + 应付债券，
      **不含租赁负债**（源三表无 lease_liabilities，固定 NULL，也未计入合计）；
    - net_debt = interest_debt_total − cash，cash **未扣受限资金**
      （restricted_cash 源缺失，不做二次调整，避免与数据业务口径分叉）；
    - advance_receipts 是预收款项；contract_liabilities 源未单列（NULL），两者不可相加；
    - 金融企业（银行/保险/证券）interest_debt_total 与 net_debt 均为 NULL，
      is_financial=true 是主判断，NULL 不得当 0，也不得用总负债−现金替代。
    """
    rows = _query(
        conn,
        """
        SELECT report_date, shortterm_loan, non_current_liability_in_one_year,
               long_term_loans, bonds_payable, lease_liabilities,
               interest_debt_total, cash, restricted_cash, net_debt,
               advance_receipts, contract_liabilities, parent_equity,
               minority_equity, total_equity, sw_l1_code, is_financial,
               source, caliber, available_time
          FROM svquant.interest_debt
         WHERE symbol=%s AND report_date <= %s AND available_time::date <= %s
         ORDER BY report_date DESC LIMIT 1
        """,
        (symbol, _as_of(as_of), _as_of(as_of)),
    )
    if not rows:
        return None
    row = rows[0]
    is_financial = bool(row.get("is_financial"))
    net_debt = row.get("net_debt")
    interest_total = row.get("interest_debt_total")
    advance_receipts = (
        float(row["advance_receipts"]) if row.get("advance_receipts") is not None else None
    )
    return {
        "report_date": str(row.get("report_date")),
        "interest_debt_total": float(interest_total) if interest_total is not None else None,
        "cash": float(row["cash"]) if row.get("cash") is not None else None,
        "net_debt": float(net_debt) if net_debt is not None else None,
        "net_debt_applicable": (not is_financial) and net_debt is not None,
        "is_financial": is_financial,
        "lease_in_total": False,
        "interest_debt_components": (
            "短期借款 + 一年内到期非流动负债 + 长期借款 + 应付债券"
        ),
        "advance_receipts": advance_receipts,
        "advance_receipts_positive": advance_receipts is not None and advance_receipts > 0,
        "contract_liabilities": (
            float(row["contract_liabilities"]) if row.get("contract_liabilities") is not None else None
        ),
        "parent_equity": float(row["parent_equity"]) if row.get("parent_equity") is not None else None,
        "minority_equity": float(row["minority_equity"]) if row.get("minority_equity") is not None else None,
        "restricted_cash": float(row["restricted_cash"]) if row.get("restricted_cash") is not None else None,
        "lease_liabilities": float(row["lease_liabilities"]) if row.get("lease_liabilities") is not None else None,
        "note": (
            "金融企业：有息负债合计与净债务均为 NULL，不适用净债务桥，不能按 0 处理。"
            if is_financial
            else (
                "有息负债合计不含租赁负债（源缺失）；净债务 = 有息负债合计 − 货币资金，"
                "货币资金未扣受限资金；预收款项与合同负债不是同一科目，合同负债源未单列；"
                "预收款项为 0 只表示该期期末无余额或源未列示，不作为有余额证据。"
            )
        ),
        "population_note": (
            "2011–2015 归母权益已回补；available_time 取原表 m_anntime，不是 F10 NOTICE_DATE。"
        ),
        "source": row.get("source"),
        "caliber": row.get("caliber"),
    }


def audit_summary(conn, symbol: str, as_of: Any) -> dict[str, Any] | None:
    rows = _query(
        conn,
        """
        SELECT report_date, opinion_type, announce_date, available_time, source, caliber
          FROM svquant.audit_opinion
         WHERE symbol=%s AND report_date <= %s AND available_time::date <= %s
         ORDER BY report_date DESC LIMIT 1
        """,
        (symbol, _as_of(as_of), _as_of(as_of)),
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


__all__ = [
    "audit_summary",
    "holder_summary",
    "interest_debt_summary",
    "segment_summary",
]
