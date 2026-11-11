# -*- coding: utf-8 -*-
"""机构端退出研究：退出案状态机、创建与复核。

从 inst_service 拆出，函数名与签名不变；调用方仍从 inst_service 导入。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from services.core.db import get_conn
from services.core.tenant import OrgScope

from . import repo
from .common import _iso, _j, _row_dict
from .guards import _audit, _member, _require_role, _uid
from .research_service import _existing_case_id, _lock_company_case
from .stages import _record_transition, _set_case_stage


_EXIT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"approved", "rejected", "closed"},
    "approved": {"rejected", "closed"},
    "rejected": set(),
    "closed": set(),
}
def _exit_case_for_case(conn, org_id: int, case_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_exit_case WHERE case_id=%s AND org_id=%s ORDER BY id DESC LIMIT 1",
        (case_id, org_id),
    ).fetchone()
    return _row_dict(row)


def _exit_case_for_proposal(conn, org_id: int, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_exit_case WHERE proposal_id=%s AND org_id=%s ORDER BY id DESC LIMIT 1",
        (proposal_id, org_id),
    ).fetchone()
    return _row_dict(row)


def _transition_exit_case(
    conn,
    org_id: int,
    exit_case: dict[str, Any],
    new_status: str,
    *,
    actor_member_id: int | None,
    action: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    """按状态机迁移退出案；非法迁移直接拒绝，成功迁移写审计。"""
    old_status = str(exit_case.get("status") or "draft")
    if new_status == old_status:
        return False
    if new_status not in _EXIT_TRANSITIONS.get(old_status, set()):
        raise PermissionError(f"退出案状态不能从 {old_status} 迁移到 {new_status}")
    row = conn.execute(
        "UPDATE inst_exit_case SET status=%s WHERE id=%s AND org_id=%s AND status=%s RETURNING id",
        (new_status, int(exit_case["id"]), org_id, old_status),
    ).fetchone()
    if not row:
        raise PermissionError("退出案状态已变化，请刷新后重试")
    _audit(
        conn,
        org_id=org_id,
        actor_member_id=actor_member_id,
        action=action,
        object_type="inst_exit_case",
        object_id=int(exit_case["id"]),
        before={"status": old_status},
        after={"status": new_status, **(extra or {})},
    )
    return True


def _advance_exit_case(
    conn,
    org_id: int,
    exit_case: dict[str, Any],
    new_status: str,
    *,
    actor_member_id: int | None,
    action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """兼容旧数据：仍为 draft 的退出案先补 submitted，再前进到目标状态。"""
    if new_status in {"approved", "rejected", "closed"} and str(
        exit_case.get("status") or "draft"
    ) == "draft":
        _transition_exit_case(
            conn,
            org_id,
            exit_case,
            "submitted",
            actor_member_id=actor_member_id,
            action="monitor.exit.submit",
            extra={"auto": True},
        )
        exit_case = {**exit_case, "status": "submitted"}
    _transition_exit_case(
        conn,
        org_id,
        exit_case,
        new_status,
        actor_member_id=actor_member_id,
        action=action,
        extra=extra,
    )
    return {**exit_case, "status": new_status}


def create_exit_case(
    org_id: int,
    company_id: int,
    *,
    reason_type: str,
    memo: str,
    actor_member_id: int | None,
) -> dict[str, Any]:
    allowed = {"thesis_invalid", "valuation", "better_allocation", "portfolio_constraint", "other"}
    if reason_type not in allowed:
        raise ValueError("reason_type 不合法")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        company = conn.execute(
            "SELECT id, symbol, name FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        pos = conn.execute(
            """
            SELECT ps.id, ps.portfolio_id, ps.symbol, ps.qty
              FROM inst_position_snapshot ps
              JOIN inst_portfolio p ON p.id=ps.portfolio_id
             WHERE p.org_id=%s AND ps.symbol=%s AND ps.qty > 0
             ORDER BY ps.as_of DESC LIMIT 1
            """,
            (org_id, company["symbol"]),
        ).fetchone()
        if not pos:
            raise PermissionError("该标的不在持仓中，不能发起退出研究")
        # 退出研究使旧授权失效：只撤销仍有效的授权，保留历史。
        conn.execute(
            """
            UPDATE inst_authorization a
               SET status='revoked', revoked_at=NOW(),
                   revoke_reason='exit research: ' || %s
             WHERE a.status='qualified'
               AND a.id IN (
                 SELECT a2.id FROM inst_authorization a2
                   JOIN inst_proposal_version v ON v.id=a2.proposal_version_id
                   JOIN inst_proposal p ON p.id=v.proposal_id
                  WHERE p.org_id=%s AND p.company_id=%s
               )
            """,
            (memo[:120] or reason_type, org_id, company_id),
        )
        # 退出研究开启后，旧的买入/减持议案全部作废，避免与新退出议案并存。
        conn.execute(
            "UPDATE inst_proposal SET stale_at=NOW(), stale_reason=%s, status='rejected', updated_at=NOW() "
            "WHERE org_id=%s AND company_id=%s AND stale_at IS NULL "
            "AND status IN ('draft','partner_review','risk_precheck','chairman_review','authorized')",
            (f"exit research: {memo[:120] or reason_type}", org_id, company_id),
        )
        # 一股一流程：退出研究复用该公司当前研究案，不再新建第二个案。
        _lock_company_case(conn, org_id, company_id)
        case_id = _existing_case_id(conn, org_id, company_id)
        if case_id is None:
            case_no = f"EX-{date.today():%Y%m%d}-{str(company['symbol']).split('.')[0]}-{_uid()[:4]}"
            created = conn.execute(
                "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, stage_no, stage_key, stage_gate, created_by) "
                "VALUES (%s,%s,%s,'draft',1,'research','{\"stage_no\":1,\"gate\":\"研究定稿\"}'::jsonb,%s) RETURNING id",
                (org_id, company_id, case_no, actor_member_id),
            ).fetchone()
            case_id = int(created["id"])
        else:
            existing = conn.execute(
                "SELECT case_no FROM inst_research_case WHERE id=%s", (case_id,)
            ).fetchone()
            case_no = str((existing or {}).get("case_no") or f"RC-{case_id}")
            _set_case_stage(
                conn,
                org_id=org_id,
                case_id=case_id,
                to_stage=1,
                trigger="monitor.exit.create",
                actor_member_id=actor_member_id,
                to_state="in_progress",
                detail={"reason_type": reason_type},
            )
        row = conn.execute(
            "INSERT INTO inst_exit_case (org_id, company_id, position_id, case_id, reason_type, memo, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'draft') RETURNING *",
            (org_id, company_id, pos["id"], case_id, reason_type, memo),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.exit.create",
            object_type="inst_exit_case",
            object_id=int(row["id"]),
            after={"company_id": company_id, "reason_type": reason_type, "case_id": case_id},
        )
    out = _row_dict(row) or {}
    out["case_id"] = case_id
    out["case_no"] = case_no
    return out


def review_exit(
    org_id: int,
    exit_case_id: int,
    *,
    thesis_verdict: str,
    realized_return: float | None = None,
    holding_days: int | None = None,
    lessons: str | None = None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """退出复盘：结果、持有天数、论点对错与教训。"""
    if thesis_verdict not in {"right", "wrong", "mixed"}:
        raise ValueError("thesis_verdict 必须是 right/wrong/mixed")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        exit_case = conn.execute(
            "SELECT * FROM inst_exit_case WHERE id=%s AND org_id=%s",
            (exit_case_id, org_id),
        ).fetchone()
        if not exit_case:
            raise LookupError("退出案不存在")
        row = conn.execute(
            """
            INSERT INTO inst_exit_review
              (exit_case_id, realized_return, holding_days, thesis_verdict, lessons, reviewer_member_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (exit_case_id) DO UPDATE
              SET realized_return=EXCLUDED.realized_return,
                  holding_days=EXCLUDED.holding_days,
                  thesis_verdict=EXCLUDED.thesis_verdict,
                  lessons=EXCLUDED.lessons,
                  reviewer_member_id=EXCLUDED.reviewer_member_id,
                  created_at=NOW()
            RETURNING *
            """,
            (exit_case_id, realized_return, holding_days, thesis_verdict, lessons, actor_member_id),
        ).fetchone()
        current_status = str(exit_case["status"] or "draft")
        if current_status in {"approved", "submitted"}:
            _transition_exit_case(
                conn,
                org_id,
                _row_dict(exit_case) or {},
                "closed",
                actor_member_id=actor_member_id,
                action="monitor.exit.close",
                extra={"review_id": int(row["id"]), "source": "post_mortem"},
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.exit.review",
            object_type="inst_exit_case",
            object_id=exit_case_id,
            after={"thesis_verdict": thesis_verdict, "realized_return": realized_return},
        )
    return _row_dict(row) or {}

__all__ = [
    "_advance_exit_case",
    "_exit_case_for_case",
    "_exit_case_for_proposal",
    "_transition_exit_case",
    "create_exit_case",
    "review_exit",
]
