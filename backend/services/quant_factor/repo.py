# -*- coding: utf-8 -*-
"""量化因子租户仓储：所有读路径集中在这里，强制使用 Tenant。

服务层仍保留原有 (uid, org) 签名；跨租户过滤不再散落在 service/ledger。
"""
from __future__ import annotations

from services.core.db import get_conn
from services.core.tenant import Tenant


def candidate(tenant: Tenant, candidate_id: str) -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s",
            (candidate_id, tenant.user_id, tenant.org_id),
        ).fetchone()
    if not row:
        raise KeyError(candidate_id)
    return dict(row)


def candidates(tenant: Tenant, project_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT id,project_id,snapshot_hash,status,created_at,updated_at,evidence,archive "
            "FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s "
            "ORDER BY created_at DESC LIMIT 100",
            (tenant.user_id, tenant.org_id, project_id),
        ).fetchall()
    return [dict(row) for row in rows]


def topic(tenant: Tenant, topic_id: str) -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s",
            (topic_id, tenant.user_id, tenant.org_id),
        ).fetchone()
    if not row:
        raise KeyError(topic_id)
    return dict(row)


def topics(tenant: Tenant, project_id: str | None = None) -> list[dict]:
    with get_conn() as c:
        if project_id is None:
            rows = c.execute(
                "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s ORDER BY created_at",
                (tenant.user_id, tenant.org_id),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at",
                (tenant.user_id, tenant.org_id, project_id),
            ).fetchall()
    return [dict(row) for row in rows]


def branches(tenant: Tenant, topic_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quant_factor_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at",
            (tenant.user_id, tenant.org_id, topic_id),
        ).fetchall()
    return [dict(row) for row in rows]


def trials(tenant: Tenant, topic_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no",
            (tenant.user_id, tenant.org_id, topic_id),
        ).fetchall()
    return [dict(row) for row in rows]


__all__ = ["branches", "candidate", "candidates", "topic", "topics", "trials"]

def candidate_for_org(tenant: Tenant, candidate_id: str) -> dict | None:
    """复核人按 org 读取候选；user_id 由 ensure_reviewer 另行校验。"""
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_candidates WHERE id=%s AND org_id=%s",
            (candidate_id, tenant.org_id),
        ).fetchone()
    return dict(row) if row else None


def review_queue(tenant: Tenant, reviewer_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT id,snapshot_hash,status,snapshot->>'name' AS name,archive,updated_at "
            "FROM quant_factor_candidates WHERE org_id=%s AND user_id<>%s "
            "AND archive->'review'->>'status'='requested' ORDER BY updated_at DESC LIMIT 100",
            (tenant.org_id, reviewer_id),
        ).fetchall()
    return [dict(row) for row in rows]


def imported_summary(tenant: Tenant) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT status,metrics_status,COUNT(*) AS n FROM quant_factor_imported_factors "
            "WHERE org_id=%s GROUP BY status,metrics_status ORDER BY status,metrics_status",
            (tenant.org_id,),
        ).fetchall()
    return [dict(row) for row in rows]
