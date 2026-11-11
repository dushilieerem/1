# -*- coding: utf-8 -*-
"""机构端授权与模拟执行：授权快照、预检、成交、对账、异常处理。

从 inst_service 拆出，函数名与签名不变；调用方仍从 inst_service 导入。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from psycopg.types.json import Jsonb

from ai.runtime import agent_store
from ai.runtime.agent_store import (
    get_cached_output,
    get_effective_prompt,
    get_latest_output,
    input_hash as agent_input_hash,
    save_output,
)
from services.core.db import get_conn
from services.core.tenant import OrgScope
from services.institution.prompts import (
    CHAIRMAN_MEMO_PROMPT,
    PARTNER_MEMO_PROMPT,
    CHAT_PROMPT,
    INDUSTRY_PROMPT,
    DEBATE_PROMPT,
    DIMENSION_PROMPTS as _DIMENSION_PROMPTS,
    RESEARCH_MEMO_PROMPT,
    RISK_REVIEW_PROMPT,
    ROLE_PROMPTS as _ROLE_PROMPTS,
)
from services.institution import data_platform, inst_ai_store
from services.institution.report import render_research_report, report_filename
from services.marketdata import store as md

from . import repo
from .common import _clip_brief, _evidence_grade, _hash, _iso, _j, _pc, _row_dict, _yi
from .guards import POLICY_VERSION, _audit, _member, _require_role, _uid
from .stages import _record_gate, _record_transition, _set_case_stage, _stage_def, _stage_payload
from .company_service import DEFAULT_NAV, _mapped_industry
from .proposal_service import (
    _approval_rows,
    _approval_state,
    _current_version,
    _member_role_counts,
    _proposal_row,
    get_proposal,
)
from .research_service import *   # noqa: F401,F403
from .debate_service import *    # noqa: F401,F403
from .exit_service import *      # noqa: F401,F403


def authorize(org_id: int, proposal_id: int, *, actor_member_id: int | None) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman", "risk")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        if proposal.get("stale_at"):
            raise PermissionError("研究已重开，议案已作废，不能生成授权")
        if int(proposal.get("created_by") or 0) == int(actor_member_id or 0):
            raise PermissionError("提案人不得签发自己的授权")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        # 同一议案版本只允许一份有效授权；重复调用返回已有授权。
        conn.execute(
            "SELECT pg_advisory_xact_lock(7303, %s::int)", (int(current["id"]),)
        )
        existing = conn.execute(
            "SELECT * FROM inst_authorization "
            "WHERE proposal_version_id=%s AND status IN ('qualified','filled') "
            "ORDER BY id LIMIT 1",
            (int(current["id"]),),
        ).fetchone()
        if existing:
            return get_proposal(org_id, proposal_id)  # type: ignore[return-value]
        approvals = _approval_rows(conn, int(current["id"]))
        state = _approval_state(approvals, _member_role_counts(conn, org_id))
        if not state["partner"]["passed"]:
            raise PermissionError("缺少合伙人批准")
        if not state["chairman"]["passed"]:
            raise PermissionError("缺少 Chairman 批准")
        if state["risk_precheck"]["vetoed"]:
            raise PermissionError("风控已否决，不能生成授权")
        if not state["risk_precheck"]["passed"]:
            raise PermissionError("风控尚未放行")
        if proposal["status"] != "authorized":
            raise PermissionError("议案尚未完成审批，不能生成授权")
        risk = state["risk_precheck"]["latest"] or {}
        approval_conditions = [
            {
                "step": r.get("step"),
                "decision": r.get("decision"),
                "comment": r.get("comment"),
                "conditions": r.get("conditions") or [],
                "approver_member_id": r.get("approver_member_id"),
            }
            for r in approvals
            if r.get("conditions")
        ]
        snapshot = {
            "authorization_id": None,
            "proposal_id": proposal_id,
            "proposal_version_id": int(current["id"]),
            "proposal_version_no": int(current["version_no"]),
            "proposal_hash": _hash(current.get("snapshot") or {}),
            "research_version_id": (current.get("snapshot") or {}).get("research_version_id"),
            "research_content_hash": (current.get("snapshot") or {}).get("research_content_hash"),
            "research_cutoff": (current.get("snapshot") or {}).get("research_cutoff"),
            "evidence_hash": (current.get("snapshot") or {}).get("evidence_hash"),
            "direction": proposal["direction"],
            "target_weight": (current.get("snapshot") or {}).get("target_weight", proposal["target_weight"]),
            "price_low": (current.get("snapshot") or {}).get("price_low"),
            "price_high": (current.get("snapshot") or {}).get("price_high"),
            "account": (current.get("snapshot") or {}).get("account"),
            "funding_source": (current.get("snapshot") or {}).get("funding_source"),
            "currency": (current.get("snapshot") or {}).get("currency"),
            "fx_rate": (current.get("snapshot") or {}).get("fx_rate"),
            "valid_until": (current.get("snapshot") or {}).get("valid_until"),
            "monitoring": (current.get("snapshot") or {}).get("monitoring") or [],
            "approval_conditions": approval_conditions,
            "approval_chain": [
                {
                    "step": r.get("step"),
                    "decision": r.get("decision"),
                    "comment": r.get("comment"),
                    "conditions": r.get("conditions") or [],
                    "approver_member_id": r.get("approver_member_id"),
                    "decided_at": (
                        r["decided_at"].isoformat()
                        if hasattr(r.get("decided_at"), "isoformat")
                        else r.get("decided_at")
                    ),
                }
                for r in approvals
            ],
            "policy_version": POLICY_VERSION,
            "issued_at": datetime.now().isoformat(timespec="seconds"),
        }
        row = conn.execute(
            "INSERT INTO inst_authorization (proposal_version_id, approval_id, snapshot, status) VALUES (%s,%s,%s,'qualified') RETURNING *",
            (current["id"], risk.get("id"), _j(snapshot)),
        ).fetchone()
        snapshot["authorization_id"] = int(row["id"])
        conn.execute(
            "UPDATE inst_authorization SET snapshot=%s WHERE id=%s", (_j(snapshot), row["id"])
        )
        conn.execute(
            "UPDATE inst_proposal SET status='authorized', updated_at=NOW() WHERE id=%s", (proposal_id,)
        )
        conn.execute("UPDATE inst_proposal_version SET status='authorized' WHERE id=%s", (current["id"],))
        _set_case_stage(
            conn,
            org_id=org_id,
            case_id=int(proposal["case_id"]),
            to_stage=4,
            trigger="authorization.issue",
            actor_member_id=actor_member_id,
            gate_status="pass",
            gate_checks=[],
            object_type="inst_authorization",
            object_id=int(row["id"]),
            detail={"proposal_id": proposal_id, "proposal_version_id": int(current["id"])},
        )
        exit_case = _exit_case_for_proposal(conn, org_id, proposal_id)
        if exit_case:
            # 退出案状态没有独立「已授权」态：授权不改状态，只写审计，下一步执行后关闭。
            exit_case = _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "approved",
                actor_member_id=actor_member_id,
                action="monitor.exit.approve",
                extra={"proposal_id": proposal_id, "authorization_id": int(row["id"])},
            )
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="monitor.exit.authorize",
                object_type="inst_exit_case",
                object_id=int(exit_case["id"]),
                before={"status": exit_case["status"]},
                after={
                    "status": exit_case["status"],
                    "proposal_id": proposal_id,
                    "authorization_id": int(row["id"]),
                },
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.authorize",
            object_type="inst_authorization",
            object_id=int(row["id"]),
            after=snapshot,
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def approve_and_execute(
    org_id: int,
    proposal_id: int,
    *,
    actor_member_id: int | None,
    price: float | None = None,
    conditions_met: bool = False,
) -> dict[str, Any]:
    """线性流程 B：审批最后一关通过后，一次动作完成授权 + 模拟成交。

    - 已有已成交授权：幂等返回原结果；
    - 已有有效授权（上次成交失败）：直接重试成交，不重复生成授权；
    - 否则先 authorize，再以系统执行方式调用 SimBroker。
    """
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman", "risk")
        proposal = _proposal_row(conn, org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    if proposal.get("status") == "executed":
        current = get_proposal(org_id, proposal_id) or {}
        for auth in current.get("authorizations") or []:
            if auth.get("status") == "filled":
                return {
                    "proposal": current,
                    "authorization_id": int(auth["id"]),
                    "execution": {"ok": True, "idempotent": True},
                }
    current = get_proposal(org_id, proposal_id) or {}
    qualified = [
        a for a in (current.get("authorizations") or []) if a.get("status") == "qualified"
    ]
    if qualified:
        auth_id = int(qualified[0]["id"])
    else:
        authorized = authorize(org_id, proposal_id, actor_member_id=actor_member_id)
        qualified = [
            a for a in (authorized.get("authorizations") or []) if a.get("status") == "qualified"
        ]
        if not qualified:
            raise PermissionError("授权生成失败")
        auth_id = int(qualified[0]["id"])
    execution = execute_authorization(
        org_id,
        auth_id,
        actor_member_id=actor_member_id,
        price=price,
        bypass_role=True,
        conditions_met=conditions_met,
    )
    return {
        "proposal": get_proposal(org_id, proposal_id),
        "authorization_id": auth_id,
        "execution": execution,
    }


def list_authorizations(
    org_id: int, *, status: str | None = None, viewer_role: str | None = None
) -> list[dict[str, Any]]:
    rows = repo.authorizations(OrgScope(org_id), status=status)
    if viewer_role == "manager":
        return rows
    # 非投资经理角色只看授权进度，不返回价格区间、账户、有效期等执行要素。
    hidden = {"snapshot", "version_snapshot"}
    return [{key: value for key, value in row.items() if key not in hidden} for row in rows]


def execute_authorization(
    org_id: int,
    authorization_id: int,
    *,
    actor_member_id: int | None,
    price: float | None = None,
    bypass_role: bool = False,
    conditions_met: bool = False,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        if not bypass_role:
            _require_role(member, "manager")
        row = conn.execute(
            """
            SELECT a.*, v.snapshot AS version_snapshot, p.id AS proposal_id, p.case_id, p.company_id, p.direction,
                   co.symbol, co.name AS company_name
              FROM inst_authorization a
              JOIN inst_proposal_version v ON v.id=a.proposal_version_id
              JOIN inst_proposal p ON p.id=v.proposal_id
              JOIN inst_company co ON co.id=p.company_id
             WHERE a.id=%s AND p.org_id=%s
            """,
            (authorization_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("授权不存在")
        auth = dict(row)
        # 幂等优先：同一授权重复执行返回原订单，而不是报“状态不可执行”。
        existing = conn.execute(
            "SELECT * FROM inst_order WHERE authorization_id=%s", (authorization_id,)
        ).fetchone()
        if existing:
            exit_case = _exit_case_for_proposal(conn, org_id, int(auth["proposal_id"]))
            if exit_case:
                _advance_exit_case(
                    conn,
                    org_id,
                    exit_case,
                    "closed",
                    actor_member_id=actor_member_id,
                    action="monitor.exit.close",
                    extra={"order_id": int(existing["id"]), "authorization_id": authorization_id},
                )
            return {"ok": True, "idempotent": True, "order": _row_dict(existing)}
        if auth["status"] != "qualified":
            raise PermissionError(f"授权状态为 {auth['status']}，不可执行")
        snapshot = auth.get("snapshot") or {}
        approval_conditions = snapshot.get("approval_conditions") or []
        if approval_conditions and not conditions_met:
            raise PermissionError("存在审批附加条件，执行人需确认条件已满足后再成交")
        valid_until = snapshot.get("valid_until")
        if valid_until and str(valid_until)[:10] < date.today().isoformat():
            raise PermissionError("授权已过期")
        portfolio = conn.execute(
            "SELECT * FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
        ).fetchone()
        if not portfolio:
            raise LookupError("组合不存在")
        bar = md.latest_bar(auth["symbol"], adjust="none")
        px = float(price or (bar or {}).get("close") or 0)
        status = md.status_latest(auth["symbol"]) or {}
        if status.get("is_suspended") or status.get("is_st"):
            reason = "停牌" if status.get("is_suspended") else "ST"
            _record_blocked_execution(
                org_id,
                authorization_id,
                type_="suspended_or_st",
                detail=f"{auth['symbol']} 当前状态：{reason}",
                actor_member_id=actor_member_id,
            )
            raise PermissionError(f"标的当前{reason}，不能执行")
        if px <= 0:
            _record_blocked_execution(
                org_id,
                authorization_id,
                type_="price_invalid",
                detail=f"{auth['symbol']} 无可用成交价",
                actor_member_id=actor_member_id,
            )
            raise ValueError("没有可用的成交价")
        low = snapshot.get("price_low")
        high = snapshot.get("price_high")
        if low is not None and px < float(low):
            raise PermissionError(f"成交价 {px} 低于授权下限 {low}")
        if high is not None and px > float(high):
            raise PermissionError(f"成交价 {px} 高于授权上限 {high}")
        nav = float(portfolio["nav"] or DEFAULT_NAV)
        cash = float(portfolio["cash"] or nav)
        target = float(snapshot.get("target_weight") or 0)
        direction = auth["direction"]
        pos = None
        if direction in {"sell", "exit"}:
            pos = conn.execute(
                "SELECT qty, cost FROM inst_position_snapshot WHERE portfolio_id=%s AND symbol=%s ORDER BY as_of DESC LIMIT 1",
                (portfolio["id"], auth["symbol"]),
            ).fetchone()
            if not pos or float(pos["qty"]) <= 0:
                raise PermissionError("没有可卖持仓")
            pos_qty = float(pos["qty"])
            # target=0 表示清仓；否则按目标权重减持，但不允许超过现有持仓。
            qty = pos_qty if target <= 0 else min(pos_qty, math.floor(target * nav / px / 100) * 100)
        else:
            qty = math.floor(target * nav / px / 100) * 100
        if qty <= 0:
            raise ValueError("目标仓位不足以形成一手")
        if direction in {"buy"}:
            cost = qty * px
            fee = cost * 0.0003
            if cost + fee > cash:
                raise PermissionError("现金不足，无法执行")
            new_cash = cash - cost - fee
            side = "buy"
        else:
            proceeds = qty * px
            fee = proceeds * 0.0003
            new_cash = cash + proceeds - fee
            side = "sell"
        order = conn.execute(
            """
            INSERT INTO inst_order (authorization_id, portfolio_id, symbol, side, qty, price, status, idempotency_key, filled_at)
            VALUES (%s,%s,%s,%s,%s,%s,'filled',%s,NOW()) RETURNING *
            """,
            (authorization_id, portfolio["id"], auth["symbol"], side, qty, px, f"auth-{authorization_id}"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_fill (order_id, qty, price, fee) VALUES (%s,%s,%s,%s)",
            (order["id"], qty, px, fee),
        )
        conn.execute(
            "UPDATE inst_portfolio SET cash=%s, updated_at=NOW() WHERE id=%s", (new_cash, portfolio["id"])
        )
        # 更新持仓快照（按最新交易日）
        today = date.today()
        prev = conn.execute(
            "SELECT qty, cost FROM inst_position_snapshot WHERE portfolio_id=%s AND symbol=%s ORDER BY as_of DESC LIMIT 1",
            (portfolio["id"], auth["symbol"]),
        ).fetchone()
        prev_qty = float(prev["qty"]) if prev else 0.0
        prev_cost = float(prev["cost"]) if prev else 0.0
        if side == "buy":
            new_qty = prev_qty + qty
            new_cost = (prev_qty * prev_cost + qty * px) / new_qty if new_qty else 0
        else:
            new_qty = prev_qty - qty
            new_cost = prev_cost
        mv = new_qty * px
        weight = mv / nav if nav else 0
        conn.execute(
            """
            INSERT INTO inst_position_snapshot (portfolio_id, symbol, qty, cost, market_value, weight, as_of)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (portfolio_id, symbol, as_of) DO UPDATE
              SET qty=EXCLUDED.qty, cost=EXCLUDED.cost, market_value=EXCLUDED.market_value, weight=EXCLUDED.weight
            """,
            (portfolio["id"], auth["symbol"], new_qty, new_cost, mv, weight, today),
        )
        conn.execute("UPDATE inst_authorization SET status='filled' WHERE id=%s", (authorization_id,))
        conn.execute(
            "UPDATE inst_proposal SET status='executed', updated_at=NOW() WHERE id=%s", (auth["proposal_id"],)
        )
        _set_case_stage(
            conn,
            org_id=org_id,
            case_id=int(auth["case_id"]),
            to_stage=5,
            trigger="execution.filled",
            actor_member_id=actor_member_id,
            gate_status="pass",
            gate_checks=[],
            object_type="inst_order",
            object_id=int(order["id"]),
            detail={"authorization_id": authorization_id, "symbol": auth["symbol"], "qty": qty, "price": px},
        )
        exit_case = _exit_case_for_proposal(conn, org_id, int(auth["proposal_id"]))
        if exit_case:
            _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "closed",
                actor_member_id=actor_member_id,
                action="monitor.exit.close",
                extra={"order_id": int(order["id"]), "authorization_id": authorization_id},
            )
        conn.execute(
            "UPDATE inst_execution_exception SET status='resolved', resolution='执行成功自动关闭', "
            "resolved_by=%s, resolved_at=NOW() "
            "WHERE org_id=%s AND authorization_id=%s AND status='open'",
            (actor_member_id, org_id, authorization_id),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="authorization.execute",
            object_type="inst_order",
            object_id=int(order["id"]),
            after={"symbol": auth["symbol"], "side": side, "qty": qty, "price": px, "fee": fee},
        )
    return {"ok": True, "idempotent": False, "order": _row_dict(order), "cash": new_cash}


def _execution_context(conn, org_id: int, authorization_id: int):
    row = conn.execute(
        """
        SELECT a.*, v.snapshot AS version_snapshot, p.id AS proposal_id, p.company_id, p.direction,
               co.symbol, co.name AS company_name
          FROM inst_authorization a
          JOIN inst_proposal_version v ON v.id=a.proposal_version_id
          JOIN inst_proposal p ON p.id=v.proposal_id
          JOIN inst_company co ON co.id=p.company_id
         WHERE a.id=%s AND p.org_id=%s
        """,
        (authorization_id, org_id),
    ).fetchone()
    if not row:
        raise LookupError("授权不存在")
    auth = dict(row)
    portfolio = conn.execute(
        "SELECT * FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
    ).fetchone()
    existing = conn.execute(
        "SELECT * FROM inst_order WHERE authorization_id=%s", (authorization_id,)
    ).fetchone()
    pos = conn.execute(
        "SELECT qty FROM inst_position_snapshot WHERE portfolio_id=%s AND symbol=%s "
        "ORDER BY as_of DESC LIMIT 1",
        (portfolio["id"] if portfolio else 0, auth["symbol"]),
    ).fetchone()
    return auth, (auth.get("snapshot") or {}), portfolio, existing, float(pos["qty"]) if pos else 0.0


def precheck_execution(
    org_id: int, authorization_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """执行前校验：授权、有效期、价格区间、现金/持仓、停牌与 ST。

    现金、持仓、可执行数量属于执行要素，仅投资经理可读。
    """
    from services.institution.execution_guard import evaluate

    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        auth, snapshot, portfolio, existing, pos_qty = _execution_context(
            conn, org_id, authorization_id
        )
    bar = md.latest_bar(str(auth["symbol"]), adjust="none") or {}
    status = md.status_latest(str(auth["symbol"])) or {}
    price = float(bar.get("close") or 0)
    nav = float((portfolio or {}).get("nav") or DEFAULT_NAV)
    cash = float((portfolio or {}).get("cash") or 0)
    target = float(snapshot.get("target_weight") or 0)
    direction = str(auth["direction"])
    if direction in {"sell", "exit"}:
        lot = math.floor(target * nav / price / 100) * 100 if price > 0 and target > 0 else pos_qty
        qty = int(min(pos_qty, lot))
        cost = 0.0
    else:
        qty = math.floor(target * nav / price / 100) * 100 if price > 0 else 0
        cost = qty * price * 1.0003
    out = evaluate(
        auth_status=str(auth["status"]),
        valid_until=(snapshot.get("valid_until") if isinstance(snapshot, dict) else None),
        direction=direction,
        price=price,
        price_low=snapshot.get("price_low"),
        price_high=snapshot.get("price_high"),
        cash=cash,
        cost=cost,
        qty=qty,
        position_qty=pos_qty,
        suspended=bool(status.get("is_suspended") or False),
        is_st=bool(status.get("is_st") or False),
        duplicate_order=existing is not None,
    )
    return {
        **out,
        "authorization_id": authorization_id,
        "symbol": auth["symbol"],
        "price": price,
        "qty": qty,
        "cash": cash,
        "position_qty": pos_qty,
    }


def _record_execution_exception(
    conn, org_id: int, authorization_id: int, *, type_: str, detail: str
) -> None:
    exists = conn.execute(
        "SELECT 1 FROM inst_execution_exception WHERE org_id=%s AND authorization_id=%s "
        "AND type=%s AND status='open'",
        (org_id, authorization_id, type_),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO inst_execution_exception (org_id, authorization_id, type, detail) "
        "VALUES (%s,%s,%s,%s)",
        (org_id, authorization_id, type_, detail),
    )


def _record_blocked_execution(
    org_id: int,
    authorization_id: int,
    *,
    type_: str,
    detail: str,
    actor_member_id: int | None,
) -> None:
    """失败请求会回滚，异常记录用独立事务落库。"""
    try:
        with get_conn() as conn:
            _record_execution_exception(conn, org_id, authorization_id, type_=type_, detail=detail)
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="authorization.execute.blocked",
                object_type="inst_authorization",
                object_id=authorization_id,
                after={"type": type_, "detail": detail},
            )
    except Exception:
        pass


def list_execution_exceptions(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    return repo.execution_exceptions(OrgScope(org_id), status=status)


def resolve_execution_exception(
    org_id: int,
    exception_id: int,
    *,
    status: str,
    resolution: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if status not in {"resolved", "ignored"}:
        raise ValueError("status 必须是 resolved/ignored")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        row, updated = repo.resolve_execution_exception(
            conn, OrgScope(org_id), exception_id, status, resolution, actor_member_id
        )
        if not row:
            raise LookupError("异常记录不存在")
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"execution.exception.{status}",
            object_type="inst_execution_exception",
            object_id=exception_id,
            before={"status": row["status"]},
            after={"status": status, "resolution": resolution},
        )
    return _row_dict(updated) or {}


def reconcile_authorization(
    org_id: int, authorization_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """成交对账：订单、成交、持仓快照与组合现金的一致性检查。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        auth, _snapshot, portfolio, order, pos_qty = _execution_context(
            conn, org_id, authorization_id
        )
        fill = (
            conn.execute("SELECT * FROM inst_fill WHERE order_id=%s", (order["id"],)).fetchone()
            if order
            else None
        )
        differences: list[str] = []
        if order is None:
            differences.append("授权没有成交订单")
        else:
            if fill is None:
                differences.append("订单没有成交记录")
            else:
                if int(fill["qty"]) != int(order["qty"]):
                    differences.append(f"成交数量 {fill['qty']} ≠ 订单数量 {order['qty']}")
                if abs(float(fill["price"]) - float(order["price"])) > 1e-6:
                    differences.append(f"成交价 {fill['price']} ≠ 订单价 {order['price']}")
            if str(order["side"]) == "buy" and pos_qty < float(order["qty"]):
                differences.append(f"持仓 {pos_qty} 少于买入数量 {order['qty']}")
            expected = float((portfolio or {}).get("cash") or 0)
            if expected < 0:
                differences.append("组合现金为负")
        matched = not differences
        if order is not None and not matched:
            exists = conn.execute(
                "SELECT 1 FROM inst_execution_exception WHERE org_id=%s AND authorization_id=%s "
                "AND type='reconcile_mismatch' AND status='open'",
                (org_id, authorization_id),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO inst_execution_exception "
                    "  (org_id, authorization_id, order_id, type, detail, status) "
                    "VALUES (%s,%s,%s,'reconcile_mismatch',%s,'open')",
                    (org_id, authorization_id, order["id"], "；".join(differences)[:500]),
                )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="authorization.reconcile",
            object_type="inst_authorization",
            object_id=authorization_id,
            after={"matched": matched, "differences": differences},
        )
    return {
        "authorization_id": authorization_id,
        "matched": matched,
        "differences": differences,
        "order": _row_dict(order) if order else None,
        "fill": _row_dict(fill) if fill else None,
    }


def authorization_for_proposal(org_id: int, proposal_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT a.* FROM inst_authorization a
              JOIN inst_proposal_version v ON v.id=a.proposal_version_id
              JOIN inst_proposal p ON p.id=v.proposal_id
             WHERE p.id=%s AND p.org_id=%s
             ORDER BY a.id DESC LIMIT 1
            """,
            (proposal_id, org_id),
        ).fetchone()
    return _row_dict(row)


