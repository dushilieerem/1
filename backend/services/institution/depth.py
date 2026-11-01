# -*- coding: utf-8 -*-
"""机构端 24 家公司研究深度刷新（M13）。

默认口径：用数据平台已落库的行情/财务/估值/行业生成六维研究；
美/港缺少财务时按“待补充”记录，不补造数字。
"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn
from services.institution import inst_service as svc
from services.marketdata import store as md


def market_coverage(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "financials": len(md.financials(symbol, limit=8)),
        "valuation": bool(md.valuation_latest(symbol)),
        "industry": bool(md.industry_latest(symbol)),
    }


def summarize(org_id: int) -> list[dict[str, Any]]:
    """24 家公司的研究版本与数据覆盖摘要。"""
    with get_conn() as conn:
        companies = conn.execute(
            "SELECT id, symbol, name, market, data_status FROM inst_company WHERE org_id=%s "
            "AND symbol = ANY(%s) ORDER BY market, symbol",
            (org_id, [item["symbol"] for item in svc.DEMO_COMPANIES]),
        ).fetchall()
        out = []
        for company in companies:
            row = dict(company)
            version = conn.execute(
                "SELECT version_no, status, six_dim, evidence_ids FROM inst_research_version "
                "WHERE case_id IN (SELECT id FROM inst_research_case WHERE company_id=%s) "
                "ORDER BY version_no DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            dims = (version["six_dim"] if version else []) or []
            out.append(
                {
                    **market_coverage(row["symbol"]),
                    "name": row["name"],
                    "market": row["market"],
                    "data_status": row["data_status"],
                    "version_no": version["version_no"] if version else None,
                    "version_status": version["status"] if version else None,
                    "dimensions_done": sum(1 for d in dims if d.get("status") == "done"),
                    "dimensions_total": len(dims),
                }
            )
    return out


def refresh(org_id: int, *, manager_id: int, partner_id: int) -> dict[str, Any]:
    """为 24 家公司补齐研究案/版本；已有版本则不重复生成。"""
    with get_conn() as conn:
        companies = conn.execute(
            "SELECT id, symbol FROM inst_company WHERE org_id=%s AND symbol = ANY(%s)",
            (org_id, [item["symbol"] for item in svc.DEMO_COMPANIES]),
        ).fetchall()
        existing = {
            int(r["company_id"]): int(r["id"])
            for r in conn.execute(
                "SELECT c.id, c.company_id FROM inst_research_case c WHERE c.org_id=%s",
                (org_id,),
            ).fetchall()
        }
    created = 0
    generated = 0
    for company in companies:
        company_id = int(company["id"])
        case_id = existing.get(company_id)
        if not case_id:
            case = svc.create_case(org_id, company_id, manager_id)
            case_id = int(case["id"])
            created += 1
        detail = svc.get_case(org_id, case_id) or {}
        approved = any(v.get("status") == "approved" for v in (detail.get("versions") or []))
        if approved:
            continue
        svc.generate_research(org_id, case_id, mode="full", actor_member_id=manager_id)
        latest = (svc.get_case(org_id, case_id) or {}).get("versions") or []
        if latest:
            try:
                svc.review_research(
                    org_id,
                    int(latest[0]["id"]),
                    decision="approve",
                    comment="M13 深度刷新",
                    actor_member_id=partner_id,
                )
                generated += 1
            except Exception:
                pass
    return {"org_id": org_id, "cases_created": created, "research_generated": generated, "summary": summarize(org_id)}
