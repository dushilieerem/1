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


def portfolio(scope: OrgScope, *, conn=None):
    """返回 (portfolio_row, position_rows)；仓位按最新快照读取。"""
    def _read(c):
        pf = c.execute(
            "SELECT * FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1",
            (scope.org_id,),
        ).fetchone()
        if not pf:
            return None, []
        latest = c.execute(
            "SELECT MAX(as_of) AS d FROM inst_position_snapshot WHERE portfolio_id=%s",
            (pf["id"],),
        ).fetchone()
        if not latest or not latest["d"]:
            return dict(pf), []
        rows = c.execute(
            """
            SELECT ps.*, co.id AS company_id, co.name, co.industry, co.market, co.data_status
              FROM inst_position_snapshot ps
              LEFT JOIN inst_company co ON co.symbol=ps.symbol AND co.org_id=%s
             WHERE ps.portfolio_id=%s AND ps.as_of=%s AND ps.qty > 0
             ORDER BY ps.market_value DESC
            """,
            (scope.org_id, pf["id"], latest["d"]),
        ).fetchall()
        return dict(pf), [dict(r) for r in rows]

    if conn is not None:
        return _read(conn)
    with get_conn() as c:
        return _read(c)


def proposals(scope: OrgScope, *, status: str | None = None):
    sql = """
        SELECT p.*, co.symbol, co.name AS company_name, co.market,
               v.version_no, v.snapshot, v.status AS version_status,
               a.id AS authorization_id, a.status AS authorization_status,
               x.id AS exit_case_id, x.status AS exit_status, x.reason_type AS exit_reason_type
          FROM inst_proposal p
          JOIN inst_company co ON co.id=p.company_id
          LEFT JOIN LATERAL (
            SELECT version_no, snapshot, status, id FROM inst_proposal_version
             WHERE proposal_id=p.id ORDER BY version_no DESC LIMIT 1
          ) v ON TRUE
          LEFT JOIN LATERAL (
            SELECT id, status FROM inst_authorization
             WHERE proposal_version_id=v.id AND status='qualified' ORDER BY id DESC LIMIT 1
          ) a ON TRUE
          LEFT JOIN LATERAL (
            SELECT id, status, reason_type FROM inst_exit_case
             WHERE proposal_id=p.id ORDER BY id DESC LIMIT 1
          ) x ON TRUE
         WHERE p.org_id=%s
    """
    params: list[Any] = [scope.org_id]
    if status:
        sql += " AND p.status=%s"
        params.append(status)
    sql += " ORDER BY p.updated_at DESC"
    with get_conn() as c:
        rows = c.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def monitor(scope: OrgScope) -> dict[str, list[dict[str, Any]]]:
    with get_conn() as conn:
        events = conn.execute(
            "SELECT e.*, co.symbol, co.name AS company_name FROM inst_monitor_event e "
            "LEFT JOIN inst_company co ON co.id=e.company_id WHERE e.org_id=%s ORDER BY e.created_at DESC LIMIT 50",
            (scope.org_id,),
        ).fetchall()
        exits = conn.execute(
            """
            SELECT x.*, co.symbol, co.name AS company_name, c.case_no,
                   p.status AS proposal_status, p.direction AS proposal_direction,
                   a.status AS authorization_status
              FROM inst_exit_case x
              JOIN inst_company co ON co.id=x.company_id
              LEFT JOIN inst_research_case c ON c.id=x.case_id
              LEFT JOIN inst_proposal p ON p.id=x.proposal_id
              LEFT JOIN LATERAL (
                SELECT au.status FROM inst_authorization au
                  JOIN inst_proposal_version v ON v.id=au.proposal_version_id
                 WHERE v.proposal_id=x.proposal_id
                 ORDER BY au.id DESC LIMIT 1
              ) a ON TRUE
             WHERE x.org_id=%s ORDER BY x.created_at DESC LIMIT 50
            """,
            (scope.org_id,),
        ).fetchall()
        theses = conn.execute(
            """
            SELECT t.*, co.name AS company_name,
                   (SELECT COUNT(*) FROM inst_thesis_review r WHERE r.ledger_id=t.id) AS review_count
              FROM inst_thesis_ledger t
              JOIN inst_company co ON co.id=t.company_id
             WHERE t.org_id=%s
             ORDER BY t.updated_at DESC LIMIT 100
            """,
            (scope.org_id,),
        ).fetchall()
        exit_reviews = conn.execute(
            """
            SELECT r.* FROM inst_exit_review r
              JOIN inst_exit_case x ON x.id=r.exit_case_id
             WHERE x.org_id=%s ORDER BY r.created_at DESC LIMIT 50
            """,
            (scope.org_id,),
        ).fetchall()
    return {
        "events": [dict(r) for r in events],
        "exits": [dict(r) for r in exits],
        "theses": [dict(r) for r in theses],
        "exit_reviews": [dict(r) for r in exit_reviews],
    }


def authorizations(scope: OrgScope, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT a.*, p.id AS proposal_id, p.company_id, co.symbol, co.name AS company_name,
               v.version_no, v.snapshot AS version_snapshot
          FROM inst_authorization a
          JOIN inst_proposal_version v ON v.id=a.proposal_version_id
          JOIN inst_proposal p ON p.id=v.proposal_id
          JOIN inst_company co ON co.id=p.company_id
         WHERE p.org_id=%s
    """
    params: list[Any] = [scope.org_id]
    if status:
        sql += " AND a.status=%s"
        params.append(status)
    sql += " ORDER BY a.issued_at DESC"
    with get_conn() as c:
        rows = c.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def theses(scope: OrgScope, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT t.*, co.name AS company_name, co.market, "
        "  (SELECT COUNT(*) FROM inst_thesis_review r WHERE r.ledger_id=t.id) AS review_count "
        "  FROM inst_thesis_ledger t JOIN inst_company co ON co.id=t.company_id "
        " WHERE t.org_id=%s"
    )
    params: list[Any] = [scope.org_id]
    if status:
        sql += " AND t.status=%s"
        params.append(status)
    sql += " ORDER BY t.updated_at DESC LIMIT 100"
    with get_conn() as c:
        rows = c.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def execution_exceptions(scope: OrgScope, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT e.*, co.symbol, co.name AS company_name FROM inst_execution_exception e "
        "LEFT JOIN inst_authorization a ON a.id=e.authorization_id "
        "LEFT JOIN inst_proposal_version v ON v.id=a.proposal_version_id "
        "LEFT JOIN inst_proposal p ON p.id=v.proposal_id "
        "LEFT JOIN inst_company co ON co.id=p.company_id "
        "WHERE e.org_id=%s"
    )
    params: list[Any] = [scope.org_id]
    if status:
        sql += " AND e.status=%s"
        params.append(status)
    sql += " ORDER BY e.created_at DESC LIMIT 200"
    with get_conn() as c:
        rows = c.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def audit(scope: OrgScope, limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT e.*, m.role AS actor_role,
                   COALESCE(u.display_name, u.username) AS actor_name
              FROM inst_audit_event e
              LEFT JOIN inst_members m ON m.id=e.actor_member_id
              LEFT JOIN users u ON u.id=m.user_id
             WHERE e.org_id=%s
             ORDER BY e.id DESC LIMIT %s
            """,
            (scope.org_id, max(1, min(limit, 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def companies(
    scope: OrgScope,
    *,
    market: str | None = None,
    q: str | None = None,
    pool_status: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where = ["c.org_id=%s"]
    params: list[Any] = [scope.org_id]
    if market:
        where.append("c.market=%s")
        params.append(market)
    if pool_status:
        where.append("c.pool_status=%s")
        params.append(pool_status)
    if q:
        where.append("(c.symbol ILIKE %s OR c.name ILIKE %s OR c.industry ILIKE %s)")
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    clause = " AND ".join(where)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    sql = f"""
        SELECT c.*,
               v.pe_ttm, v.pb_mrq, v.float_mv,
               b.close AS last_close, b.trade_date AS last_trade_date,
               st.listed_status, st.up_down_status, st.is_st, st.is_suspended,
               ind.name AS industry_name
          FROM inst_company c
          LEFT JOIN LATERAL (
            SELECT pe_ttm, pb_mrq, float_mv FROM md_valuation_daily
             WHERE symbol=c.symbol ORDER BY trade_date DESC LIMIT 1
          ) v ON TRUE
          LEFT JOIN LATERAL (
            SELECT close, trade_date FROM md_daily_bar
             WHERE symbol=c.symbol AND adjust='none' ORDER BY trade_date DESC LIMIT 1
          ) b ON TRUE
          LEFT JOIN LATERAL (
            SELECT listed_status, up_down_status, is_st, is_suspended
              FROM md_status_daily WHERE symbol=c.symbol
             ORDER BY trade_date DESC LIMIT 1
          ) st ON TRUE
          LEFT JOIN LATERAL (
            SELECT ri.name
              FROM ref_security_industry rsi
              JOIN ref_industry ri
                ON ri.industry_code = rsi.industry_code AND ri.level = 1
             WHERE rsi.symbol = c.symbol AND rsi.level = 1
             ORDER BY rsi.effective_from DESC
             LIMIT 1
          ) ind ON TRUE
         WHERE {clause}
         ORDER BY c.market, c.symbol
         LIMIT %s OFFSET %s
    """
    with get_conn() as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM inst_company c WHERE {clause}", tuple(params)
            ).fetchone()["n"]
            or 0
        )
        rows = conn.execute(sql, tuple(params + [limit, offset])).fetchall()
    return [dict(row) for row in rows], total


__all__ = ["audit", "authorizations", "case", "cases", "companies", "company", "execution_exceptions", "monitor", "portfolio", "proposals", "theses"]
