# -*- coding: utf-8 -*-
"""机构端租户读取仓储：只接受 OrgScope，SQL 不再散落在 inst_service。"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn
from services.core.tenant import OrgScope


def company(scope: OrgScope, company_id: int, *, conn=None) -> dict[str, Any] | None:
    def _run(c):
        return c.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, scope.org_id),
        ).fetchone()

    if conn is not None:
        row = _run(conn)
    else:
        with get_conn() as c:
            row = _run(c)
    return dict(row) if row else None


def cases(scope: OrgScope, *, company_id: int | None = None, conn=None) -> list[dict[str, Any]]:
    sql = """
        SELECT c.*, co.symbol, co.name AS company_name, co.market, co.industry,
               v.version_no, v.status AS version_status, v.conclusion
          FROM inst_research_case c
          JOIN inst_company co ON co.id=c.company_id
          LEFT JOIN LATERAL (
            SELECT version_no, status, conclusion FROM inst_research_version
             WHERE case_id=c.id ORDER BY version_no DESC LIMIT 1
          ) v ON TRUE
         WHERE c.org_id=%s
    """
    params: list[Any] = [scope.org_id]
    if company_id:
        sql += " AND c.company_id=%s"
        params.append(company_id)
    sql += " ORDER BY c.updated_at DESC"
    if conn is not None:
        rows = conn.execute(sql, tuple(params)).fetchall()
    else:
        with get_conn() as c:
            rows = c.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def case(scope: OrgScope, case_id: int, *, conn=None) -> dict[str, Any] | None:
    sql = """
        SELECT c.*, co.symbol, co.name AS company_name, co.market, co.industry,
               co.data_status, co.ref_price
          FROM inst_research_case c
          JOIN inst_company co ON co.id=c.company_id
         WHERE c.id=%s AND c.org_id=%s
    """
    if conn is not None:
        row = conn.execute(sql, (case_id, scope.org_id)).fetchone()
    else:
        with get_conn() as c:
            row = c.execute(sql, (case_id, scope.org_id)).fetchone()
    return dict(row) if row else None


__all__ = ["case", "cases", "company"]
