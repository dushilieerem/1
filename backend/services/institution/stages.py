# -*- coding: utf-8 -*-
"""v3 六阶段状态机：阶段定义、阶段推进、门禁与流转记录。

阶段号是服务端唯一事实来源；研究案、议案、授权的阶段都从这里取。
"""
from __future__ import annotations

from typing import Any

from .common import _j


# v3 六环节：0 机会发现 → 5 投资管理。stage_no 是服务端唯一阶段事实。
STAGE_DEFS: tuple[dict[str, Any], ...] = (
    {"no": 0, "key": "find", "name": "机会发现", "gate": "机会来源", "owner": "投资经理"},
    {"no": 1, "key": "research", "name": "价值分析", "gate": "研究定稿", "owner": "投资经理"},
    {"no": 2, "key": "debate", "name": "多空辩论", "gate": "议案锁定", "owner": "投资经理"},
    {"no": 3, "key": "approve", "name": "投委会审批", "gate": "三关审批", "owner": "合伙人 → 风控 → Chairman"},
    {"no": 4, "key": "execute", "name": "执行成交", "gate": "授权执行", "owner": "系统"},
    {"no": 5, "key": "manage", "name": "投资管理", "gate": "监控 / 退出", "owner": "投资经理 / 投委会"},
)
STAGE_BY_NO = {int(x["no"]): x for x in STAGE_DEFS}
STAGE_BY_KEY = {str(x["key"]): x for x in STAGE_DEFS}


def _stage_def(stage_no: Any) -> dict[str, Any]:
    try:
        no = int(stage_no)
    except (TypeError, ValueError):
        no = 1
    return STAGE_BY_NO.get(max(0, min(5, no)), STAGE_BY_NO[1])


def _stage_payload(stage_no: Any) -> dict[str, Any]:
    stage = _stage_def(stage_no)
    return {
        "stage_no": stage["no"],
        "stage_key": stage["key"],
        "stage_name": stage["name"],
        "stage_gate": {"stage_no": stage["no"], "gate": stage["gate"]},
    }


def _record_gate(
    conn,
    *,
    org_id: int,
    case_id: int | None,
    gate_key: str,
    status: str,
    checks: list[dict[str, Any]] | None,
    object_type: str | None = None,
    object_id: int | None = None,
    actor_member_id: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO inst_gate_run
          (org_id, case_id, gate_key, status, checks, object_type, object_id, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (org_id, case_id, gate_key, status, _j(checks or []), object_type, object_id, actor_member_id),
    )


def _record_transition(
    conn,
    *,
    org_id: int,
    case_id: int,
    from_stage: int | None,
    to_stage: int,
    trigger: str,
    actor_member_id: int | None,
    to_state: str = "in_progress",
    object_type: str | None = None,
    object_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO inst_case_transition
          (org_id, case_id, from_stage, to_stage, from_state, to_state, trigger,
           actor_member_id, object_type, object_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            org_id,
            case_id,
            from_stage,
            to_stage,
            None,
            to_state,
            trigger,
            actor_member_id,
            object_type,
            object_id,
            _j(detail or {}),
        ),
    )


def _set_case_stage(
    conn,
    *,
    org_id: int,
    case_id: int,
    to_stage: int,
    trigger: str,
    actor_member_id: int | None,
    to_state: str = "in_progress",
    gate_status: str | None = None,
    gate_checks: list[dict[str, Any]] | None = None,
    object_type: str | None = None,
    object_id: int | None = None,
    detail: dict[str, Any] | None = None,
    terminal_reason: str | None = None,
) -> dict[str, Any]:
    """推进/回退阶段；写 transition，保留旧 stage 文本兼容。"""
    row = conn.execute(
        "SELECT stage_no FROM inst_research_case WHERE id=%s AND org_id=%s",
        (case_id, org_id),
    ).fetchone()
    if not row:
        raise LookupError("研究案不存在")
    from_stage = int(row["stage_no"]) if row.get("stage_no") is not None else None
    stage = _stage_def(to_stage)
    old_stage_text = "draft"
    if stage["no"] >= 2:
        old_stage_text = "approved"
    if stage["no"] >= 3:
        old_stage_text = "proposal"
    conn.execute(
        """
        UPDATE inst_research_case
           SET stage=%s,
               stage_no=%s,
               stage_key=%s,
               stage_gate=%s,
               stage_state=%s,
               terminal_reason=%s,
               stage_locked_at=CASE WHEN %s >= 2 THEN COALESCE(stage_locked_at, NOW()) ELSE stage_locked_at END,
               updated_at=NOW()
         WHERE id=%s AND org_id=%s
        """,
        (
            old_stage_text,
            stage["no"],
            stage["key"],
            _j({"stage_no": stage["no"], "gate": stage["gate"], "status": gate_status or "pending", "checks": gate_checks or []}),
            to_state,
            terminal_reason,
            stage["no"],
            case_id,
            org_id,
        ),
    )
    if from_stage != stage["no"] or to_state != "in_progress":
        _record_transition(
            conn,
            org_id=org_id,
            case_id=case_id,
            from_stage=from_stage,
            to_stage=stage["no"],
            trigger=trigger,
            actor_member_id=actor_member_id,
            to_state=to_state,
            object_type=object_type,
            object_id=object_id,
            detail={**(detail or {}), "from_stage": from_stage, "to_stage": stage["no"], "state": to_state},
        )
    if gate_status:
        _record_gate(
            conn,
            org_id=org_id,
            case_id=case_id,
            gate_key=trigger,
            status=gate_status,
            checks=gate_checks,
            object_type=object_type,
            object_id=object_id,
            actor_member_id=actor_member_id,
        )
    return _stage_payload(stage["no"])
