# -*- coding: utf-8 -*-
"""机构端议案与三关审批：议案创建/锁定/提交、合伙人→风控→Chairman 审批。

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
from .company_service import (
    DEFAULT_NAV,
    MAX_INDUSTRY_WEIGHT,
    MAX_SINGLE_WEIGHT,
    MIN_CASH_RATIO,
    _mapped_industry,
)
from .research_service import *   # noqa: F401,F403
from .debate_service import *    # noqa: F401,F403
from .exit_service import *      # noqa: F401,F403


def _current_version(conn, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_proposal_version WHERE proposal_id=%s ORDER BY version_no DESC LIMIT 1",
        (proposal_id,),
    ).fetchone()
    return _row_dict(row)


def _proposal_row(conn, org_id: int, proposal_id: int) -> dict[str, Any] | None:
    return repo.proposal_row(OrgScope(org_id), proposal_id, conn=conn)


def _position_hint(org_id: int, symbol: str) -> tuple[bool, float]:
    with get_conn() as conn:
        pf = conn.execute(
            "SELECT nav, cash FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1",
            (org_id,),
        ).fetchone()
        pos = conn.execute(
            """
            SELECT ps.qty, ps.market_value
              FROM inst_position_snapshot ps
              JOIN inst_portfolio p ON p.id=ps.portfolio_id
             WHERE p.org_id=%s AND ps.symbol=%s
             ORDER BY ps.as_of DESC, ps.id DESC LIMIT 1
            """,
            (org_id, symbol),
        ).fetchone()
    qty = float((pos or {}).get("qty") or 0)
    if qty <= 0:
        return False, 0.0
    nav = float((pf or {}).get("nav") or 0)
    market_value = float((pos or {}).get("market_value") or 0)
    return True, (market_value / nav if nav > 0 else 0.0)


def proposal_advice(org_id: int, case_id: int) -> dict[str, Any]:
    """交易员 Agent：汇总六维评分与辩论结论，给出买卖结论、仓位与议案框架。"""
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    versions = case.get("versions") or []
    # 议案建议展示当前最新研究版本；已批准的历史版本可能没有最新六维评分。
    version = versions[0] if versions else None
    dims = [d for d in ((version or {}).get("six_dim") or []) if isinstance(d, dict)]
    scores = [
        {
            "key": d.get("key"),
            "title": d.get("title"),
            "score_10": (
                d.get("score_10")
                if d.get("score_10") is not None
                else (
                    round(float(d["rating"]) * 2, 1)
                    if d.get("rating") is not None
                    else None
                )
            ),
            "rating_benchmark": d.get("rating_benchmark"),
            "gate": d.get("gate"),
        }
        for d in dims
    ]
    overall = _overall_score(dims)
    sessions = case.get("debates") or []
    session = sessions[0] if sessions else None
    debate = get_debate(org_id, int(session["id"])) if session else None
    conclusion = str((debate or {}).get("conclusion") or "尚未形成辩论结论")
    args = (debate or {}).get("arguments") or []
    bull = sum(1 for a in args if str(a.get("side")) == "bull")
    bear = sum(1 for a in args if str(a.get("side")) == "bear")
    debate_ready = bool(debate and str(debate.get("status")) == "completed")
    research_ready = debate_ready and "补充研究" not in conclusion

    held, current_weight = _position_hint(org_id, str(case.get("symbol") or ""))
    gate_fail = [str(d.get("title") or d.get("key")) for d in dims if str(d.get("gate")) == "fail"]

    if overall is None:
        recommendation, direction, target_weight = "avoid", "hold", 0.0
        reason = "六维评分不完整，暂不具备形成议案的条件"
    elif held:
        if overall < 5.0 or gate_fail:
            recommendation, direction, target_weight = "sell", "sell", 0.0
            reason = "持仓标的研究评分跌破门槛或存在阻断维度，建议退出"
        else:
            recommendation, direction, target_weight = "hold", "hold", current_weight
            reason = "已持仓且研究未失效，建议维持现有仓位并继续复核"
    elif research_ready and not gate_fail and overall >= 7.0:
        recommendation, direction = "buy", "buy"
        target_weight = 0.05 if overall >= 9.0 else 0.03 if overall >= 8.0 else 0.02
        reason = "六维评分达到买入门槛，辩论未给出补充研究结论，建议建仓"
    else:
        recommendation, direction, target_weight = "avoid", "hold", 0.0
        reason = (
            "存在阻断维度，暂不买入"
            if gate_fail
            else "辩论尚未形成可执行结论，暂不买入"
            if not research_ready
            else "综合评分未达到买入门槛，暂不买入"
        )

    label = {
        "buy": "推荐买入",
        "sell": "推荐卖出",
        "hold": "建议持有",
        "avoid": "暂不买入",
    }[recommendation]
    price = float(case.get("ref_price") or 0)
    valuation = (version or {}).get("valuation") or {}
    low = valuation.get("low")
    high = valuation.get("high")
    try:
        low_f, high_f = float(low), float(high)
    except (TypeError, ValueError):
        low_f = high_f = 0.0
    if not (price > 0 and low_f > 0 and high_f > low_f and low_f >= price * 0.3 and high_f <= price * 3.0):
        low_f = round(price * 0.95, 2) if price > 0 else None
        high_f = round(price * 1.05, 2) if price > 0 else None

    monitoring: list[str] = []
    for d in dims:
        for item in d.get("counter") or []:
            text = _clean_agent_text(item)
            if text and text not in monitoring:
                monitoring.append(text)
    for a in args:
        text = _clean_agent_text(a.get("falsifier"))
        if text and text not in monitoring:
            monitoring.append(text)
    monitoring = monitoring[:3] or ["季度复核收入、毛利率与现金流；综合评分跌破 6.0 则重开研究"]
    target_text = f"{target_weight * 100:.1f}%"
    opinion = (
        f"六维平均得分 {overall:.1f}/10" if overall is not None else "六维评分不完整"
    ) + f"，多空辩论结论为“{conclusion}”。{label}，建议目标仓位 {target_text}。"
    opinion += f"主要风险：{monitoring[0]}；若该风险触发或综合评分跌破 6.0，则重开研究并复核仓位。"
    if len(opinion) < 60:
        opinion += "本议案仅基于当前锁定研究版本，审批前需复核证据与价格带。"
    valid_until = (date.today() + timedelta(days=30)).isoformat()

    return {
        "available": True,
        "case_id": int(case["id"]),
        "case_no": case.get("case_no"),
        "company": {
            "symbol": case.get("symbol"),
            "name": case.get("company_name"),
            "price": price or None,
        },
        "scores": scores,
        "overall_score": overall,
        "debate": {
            "session_id": int(session["id"]) if session else None,
            "status": (debate or {}).get("status"),
            "conclusion": conclusion,
            "bull_count": bull,
            "bear_count": bear,
        },
        "recommendation": recommendation,
        "recommendation_label": label,
        "direction": direction,
        "target_weight": target_weight,
        "current_weight": current_weight,
        "held": held,
        "rationale": reason,
        "framework": {
            "direction": direction,
            "target_weight": target_weight,
            "price_low": low_f,
            "price_high": high_f,
            "funding_source": "现金",
            "valid_until": valid_until,
            "monitoring": monitoring,
            "investment_opinion": opinion,
        },
        "engine": "trader_agent",
    }


def create_proposal(
    org_id: int,
    case_id: int,
    *,
    actor_member_id: int | None,
    direction: str | None = None,
    target_weight: float | None = None,
    price_low: float | None = None,
    price_high: float | None = None,
    funding_source: str | None = None,
    valid_until: str | None = None,
    monitoring: list[str] | None = None,
    investment_opinion: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        case = conn.execute(
            "SELECT * FROM inst_research_case WHERE id=%s AND org_id=%s", (case_id, org_id)
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        if case["stage"] not in {"proposal", "approved"}:
            raise PermissionError("研究与辩论未完成，不能创建议案")
        inflight = conn.execute(
            """
            SELECT id FROM inst_proposal
             WHERE org_id=%s AND case_id=%s AND stale_at IS NULL
               AND status IN ('partner_review','risk_precheck','chairman_review','authorized')
             LIMIT 1
            """,
            (org_id, case_id),
        ).fetchone()
        if inflight:
            raise PermissionError("该研究案已有在途议案，请先完成审批或等待其作废")
        version = conn.execute(
            "SELECT * FROM inst_research_version "
            "WHERE case_id=%s AND status='approved' AND superseded_at IS NULL "
            "ORDER BY version_no DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if not version:
            raise PermissionError("没有已审核通过的研究版本（研究可能已重开）")
        version = _ensure_version_hash(conn, version)
        debate = conn.execute(
            "SELECT * FROM inst_debate_session "
            "WHERE case_id=%s AND research_version_id=%s AND status='completed' "
            "ORDER BY id DESC LIMIT 1",
            (case_id, version["id"]),
        ).fetchone()
        exit_case = _exit_case_for_case(conn, org_id, case_id)
        if exit_case and exit_case.get("proposal_id"):
            raise PermissionError("该退出研究案已关联议案，不能重复创建")
        resolved_direction = str(direction or ("exit" if exit_case else "buy")).strip()
        if resolved_direction not in {"buy", "sell", "exit"}:
            raise ValueError("direction 必须是 buy/sell/exit")
        # 退出案只能清仓/减持，不允许借退出研究案创建买入议案。
        if exit_case and resolved_direction not in {"sell", "exit"}:
            raise ValueError("退出研究案只能创建 sell/exit 方向的退出议案")
        if target_weight is None:
            resolved_target = 0.0 if exit_case else 0.05
        else:
            resolved_target = float(target_weight)
        if not (0 <= resolved_target <= 1):
            raise ValueError("target_weight 必须在 0-1")
        if not exit_case and resolved_target <= 0:
            raise ValueError("买入议案的目标仓位必须大于 0")
        low = price_low
        high = price_high
        if low is None and config and config.get("price_low") is not None:
            low = float(config["price_low"])
        if high is None and config and config.get("price_high") is not None:
            high = float(config["price_high"])
        if low is not None or high is not None:
            if low is None or high is None:
                raise ValueError("价格区间必须同时填写上限和下限")
            low, high = float(low), float(high)
            if low <= 0 or high <= 0 or low > high:
                raise ValueError("价格区间必须为正且下限不高于上限")
        funding = str(funding_source or (config or {}).get("funding_source") or "现金").strip()[:100]
        if not funding:
            raise ValueError("请填写资金来源")
        validity = str(valid_until or (config or {}).get("valid_until") or (date.today() + timedelta(days=30)).isoformat())[:10]
        try:
            valid_date = date.fromisoformat(validity)
        except ValueError:
            raise ValueError("有效期必须是 YYYY-MM-DD") from None
        if valid_date < date.today():
            raise ValueError("有效期不能早于今天")
        monitor_items = monitoring if monitoring is not None else (config or {}).get("monitoring")
        if isinstance(monitor_items, str):
            monitor_items = [x.strip() for x in monitor_items.splitlines() if x.strip()]
        if not isinstance(monitor_items, list) or not monitor_items:
            monitor_items = ["季度财报后复核论点", "单股仓位超过 15% 触发复核"]
        monitor_items = [str(x)[:200] for x in monitor_items if str(x).strip()][:10]
        opinion = str(investment_opinion or (config or {}).get("investment_opinion") or "").strip()[:2000]
        version_evidence_ids = [int(x) for x in (version.get("evidence_ids") or []) if str(x).isdigit()]
        evidence_hash = (
            _hash(_evidence_payload(
                conn, version_evidence_ids, org_id=org_id, case_id=case_id
            )) if version_evidence_ids else None
        )
        snapshot = {
            "research_version_id": int(version["id"]),
            "research_version_no": int(version["version_no"]),
            "research_content_hash": version.get("content_hash"),
            "research_cutoff": (version.get("cutoff").isoformat() if hasattr(version.get("cutoff"), "isoformat") else version.get("cutoff")),
            "evidence_hash": evidence_hash,
            "debate_session_id": int(debate["id"]) if debate else None,
            "direction": resolved_direction,
            "target_weight": resolved_target,
            "exit_case_id": int(exit_case["id"]) if exit_case else None,
            "price_low": low,
            "price_high": high,
            "account": "SIM-001",
            "funding_source": funding,
            "currency": "CNY",
            "fx_rate": 1.0,
            "valid_until": validity,
            "monitoring": monitor_items,
            "investment_opinion": opinion,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        row = conn.execute(
            """
            INSERT INTO inst_proposal (org_id, case_id, company_id, direction, target_weight, current_version_no, status, created_by)
            VALUES (%s,%s,%s,%s,%s,1,'draft',%s) RETURNING *
            """,
            (org_id, case_id, case["company_id"], resolved_direction, resolved_target, actor_member_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_proposal_version (proposal_id, version_no, snapshot, status, created_by) "
            "VALUES (%s,1,%s,'draft',%s)",
            (row["id"], _j(snapshot), actor_member_id),
        )
        if exit_case:
            conn.execute(
                "UPDATE inst_exit_case SET proposal_id=%s WHERE id=%s AND org_id=%s",
                (row["id"], int(exit_case["id"]), org_id),
            )
            _transition_exit_case(
                conn,
                org_id,
                exit_case,
                "submitted",
                actor_member_id=actor_member_id,
                action="monitor.exit.submit",
                extra={"proposal_id": int(row["id"]), "direction": resolved_direction},
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.create",
            object_type="inst_proposal",
            object_id=int(row["id"]),
            after={
                "case_id": case_id,
                "direction": resolved_direction,
                "target_weight": resolved_target,
                "exit_case_id": int(exit_case["id"]) if exit_case else None,
            },
        )
    return get_proposal(org_id, int(row["id"]))  # type: ignore[return-value]


def evaluate_proposal_gate(conn, proposal: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version.get("snapshot") or {}
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot or "{}")
    checks: list[dict[str, Any]] = []
    blocking = False

    research_id = snapshot.get("research_version_id")
    research = conn.execute(
        "SELECT * FROM inst_research_version WHERE id=%s AND case_id=%s",
        (research_id, proposal.get("case_id")),
    ).fetchone()
    research_locked = bool(
        research
        and research.get("locked_at")
        and not research.get("superseded_at")
        and str(research.get("status")) == "approved"
    )
    checks.append({
        "key": "research_lock",
        "label": "研究定稿 R3",
        "status": "pass" if research_locked else "block",
        "detail": f"R{research.get('version_no')} 已锁定" if research_locked else "未锁定、已重开或版本不匹配",
    })
    blocking = blocking or not research_locked

    debate = conn.execute(
        "SELECT * FROM inst_debate_session WHERE id=%s AND case_id=%s AND status='completed'",
        (snapshot.get("debate_session_id"), proposal.get("case_id")),
    ).fetchone()
    checks.append({
        "key": "debate_complete",
        "label": "辩论完成",
        "status": "pass" if debate else "block",
        "detail": f"辩论 #{debate['id']}" if debate else "没有已完成的辩论",
    })
    blocking = blocking or not debate
    factpack = (debate or {}).get("factpack") or {}
    if isinstance(factpack, str):
        try:
            factpack = json.loads(factpack or "{}")
        except ValueError:
            factpack = {}
    debate_engine = str((factpack or {}).get("engine") or "")
    checks.append({
        "key": "debate_engine",
        "label": "辩论由 AI 生成",
        "status": "warn" if debate_engine == "rule" else "pass",
        "detail": (
            "本次辩论为规则兜底（AI 未参与），结论仅供人工参考"
            if debate_engine == "rule" else "AI 已参与辩论"
        ),
    })

    research_ev_ids = [
        int(x) for x in ((research or {}).get("evidence_ids") or [])
        if str(x).isdigit()
    ]
    grades: list[str] = []
    if research_ev_ids:
        org_id = int(proposal.get("org_id") or 0)
        rows = conn.execute(
            "SELECT grade FROM inst_evidence "
            "WHERE id = ANY(%s) AND org_id=%s AND case_id=%s",
            (research_ev_ids, org_id, proposal.get("case_id")),
        ).fetchall()
        grades = [str(r.get("grade") or "D") for r in rows]
    a_count = sum(1 for g in grades if g == "A")
    b_count = sum(1 for g in grades if g == "B")
    checks.append({
        "key": "evidence_quality",
        "label": "证据等级满足上会",
        "status": "pass" if (a_count >= 1 or b_count >= 2) else "warn",
        "detail": f"A 级 {a_count} 条 / B 级 {b_count} 条；建议至少 1 条 A 或 2 条独立 B",
    })

    fields = {
        "direction": snapshot.get("direction"),
        "target_weight": snapshot.get("target_weight"),
        "price_low": snapshot.get("price_low"),
        "price_high": snapshot.get("price_high"),
        "funding_source": snapshot.get("funding_source"),
        "valid_until": snapshot.get("valid_until"),
        "monitoring": snapshot.get("monitoring"),
        "investment_opinion": snapshot.get("investment_opinion"),
    }
    missing = [
        k for k, v in fields.items()
        if v in (None, "", []) or (k == "target_weight" and float(v or 0) <= 0 and snapshot.get("direction") == "buy")
    ]
    checks.append({
        "key": "proposal_fields",
        "label": "议案要素齐全",
        "status": "block" if missing else "pass",
        "detail": f"缺失：{', '.join(missing)}" if missing else "方向/仓位/价格带/资金/有效期/监控齐全",
    })
    blocking = blocking or bool(missing)

    bull = bear = 0
    if debate:
        counts = conn.execute(
            "SELECT side, COUNT(*) AS n FROM inst_debate_argument WHERE session_id=%s GROUP BY side",
            (int(debate["id"]),),
        ).fetchall()
        by_side = {str(r["side"]): int(r["n"]) for r in counts}
        bull, bear = by_side.get("bull", 0), by_side.get("bear", 0)
    checks.append({
        "key": "debate_claims",
        "label": "多空各 3 条",
        "status": "pass" if bull >= 3 and bear >= 3 else "warn",
        "detail": f"多方 {bull} 条 / 空方 {bear} 条",
    })
    status = "block" if blocking else ("warn" if any(x["status"] == "warn" for x in checks) else "pass")
    return {"status": status, "checks": checks}


def submit_proposal(
    org_id: int, proposal_id: int, *, actor_member_id: int | None, allow_warnings: bool = True
) -> dict[str, Any]:
    """v3 议案锁定：P3 门禁通过后提交三关，阶段 2→3。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        if proposal.get("stale_at"):
            raise PermissionError("研究已重开，议案已作废，请重新生成")
        if str(proposal.get("status")) != "draft":
            raise PermissionError("只有草稿议案可以提交")
        case_id = int(proposal["case_id"])
        conn.execute("SELECT pg_advisory_xact_lock(7302, %s::int)", (case_id,))
        inflight = conn.execute(
            """
            SELECT id FROM inst_proposal
             WHERE org_id=%s AND case_id=%s AND id<>%s AND stale_at IS NULL
               AND status IN ('partner_review','risk_precheck','chairman_review','authorized')
             LIMIT 1
            """,
            (org_id, case_id, proposal_id),
        ).fetchone()
        if inflight:
            raise PermissionError("该研究案已有在途议案，不能重复提交")
        version = _current_version(conn, proposal_id)
        if not version:
            raise PermissionError("议案没有版本")
        gate = evaluate_proposal_gate(conn, proposal, version)
        if gate["status"] == "block" or (gate["status"] == "warn" and not allow_warnings):
            raise PermissionError("议案门禁未通过：" + "；".join(
                x["detail"] for x in gate["checks"] if x["status"] in {"block", "warn"}
            ))
        snapshot = version.get("snapshot") or {}
        lock_hash = _hash(snapshot)
        conn.execute(
            "UPDATE inst_proposal SET status='partner_review', locked_at=COALESCE(locked_at,NOW()), updated_at=NOW() WHERE id=%s",
            (proposal_id,),
        )
        conn.execute(
            "UPDATE inst_proposal_version SET status='partner_submitted', locked_at=COALESCE(locked_at,NOW()), lock_hash=%s WHERE id=%s",
            (lock_hash, int(version["id"])),
        )
        _set_case_stage(
            conn,
            org_id=org_id,
            case_id=int(proposal["case_id"]),
            to_stage=3,
            trigger="proposal.lock",
            actor_member_id=actor_member_id,
            gate_status=gate["status"],
            gate_checks=gate["checks"],
            object_type="inst_proposal",
            object_id=proposal_id,
            detail={"proposal_version_id": int(version["id"]), "lock_hash": lock_hash},
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.lock",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={"case_id": int(proposal["case_id"]), "gate": gate, "lock_hash": lock_hash},
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def list_proposals(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    return repo.proposals(OrgScope(org_id), status=status)


STAGE_ROLE = {"partner": "partner", "risk_precheck": "risk", "chairman": "chairman"}


def _member_role_counts(conn, org_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT role, COUNT(*) AS n FROM inst_members WHERE org_id=%s AND status='active' GROUP BY role",
        (org_id,),
    ).fetchall()
    return {str(r["role"]): int(r["n"]) for r in rows}


def _stage_time(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _stage_summary(
    step: str, rows: list[dict[str, Any]], total: int, *, include_items: bool = False
) -> dict[str, Any]:
    items = [dict(r) for r in rows if str(r.get("step") or "") == step]
    decisions = [str(r.get("decision") or "") for r in items]
    reviewed = len(
        {int(r["approver_member_id"]) for r in items if r.get("approver_member_id")}
    )
    required = max(int(total or 0), 0)
    all_decided = required > 0 and reviewed >= required
    if step == "partner":
        if any(d == "return" for d in decisions):
            status = "returned"
        elif all_decided and all(d in {"approve", "conditional"} for d in decisions):
            status = "conditional" if any(d == "conditional" for d in decisions) else "approved"
        else:
            status = "in_progress" if items else "not_started"
    elif step == "risk_precheck":
        if any(d in {"veto", "block"} for d in decisions):
            status = "vetoed"
        elif all_decided and all(d in {"pass", "conditional"} for d in decisions):
            status = "conditional" if any(d == "conditional" for d in decisions) else "passed"
        else:
            status = "in_progress" if items else "not_started"
    else:
        if any(d in {"reject", "veto", "block"} for d in decisions):
            status = "rejected"
        elif any(d == "return" for d in decisions):
            status = "returned"
        elif all_decided and all(d in {"approve", "conditional"} for d in decisions):
            status = "conditional" if any(d == "conditional" for d in decisions) else "approved"
        else:
            status = "in_progress" if items else "not_started"
    conditions = [
        str(c)
        for r in items
        for c in (r.get("conditions") or [])
        if str(c).strip()
    ]
    latest = items[-1] if items else None
    out = {
        "status": status,
        "reviewed": reviewed,
        "decided": reviewed,
        "required": required,
        "total": max(total, reviewed),
        "decision": latest.get("decision") if latest else None,
        "comment": latest.get("comment") if latest else None,
        "conditions": conditions,
        "decided_at": _stage_time(latest.get("decided_at")) if latest else None,
    }
    if include_items:
        out["items"] = [
            {
                "approver_member_id": r.get("approver_member_id"),
                "approver_name": r.get("approver_name"),
                "approver_role": r.get("approver_role"),
                "decision": r.get("decision"),
                "comment": r.get("comment"),
                "conditions": r.get("conditions") or [],
                "decided_at": _stage_time(r.get("decided_at")),
            }
            for r in items
        ]
    return out


def _proposal_progress(conn, org_id: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _member_role_counts(conn, org_id)
    return {
        "partner": _stage_summary("partner", rows, counts.get("partner", 0)),
        "risk_precheck": _stage_summary("risk_precheck", rows, counts.get("risk", 0)),
        "chairman": _stage_summary("chairman", rows, counts.get("chairman", 0)),
    }


def _authorization_summary(data: dict[str, Any]) -> dict[str, Any] | None:
    auths = data.get("authorizations") or []
    if not auths:
        return None
    latest = auths[0]
    snapshot = latest.get("snapshot") or {}
    return {
        "id": latest.get("id"),
        "status": latest.get("status"),
        "issued_at": _stage_time(latest.get("issued_at")),
        "valid_until": snapshot.get("valid_until"),
    }


def _research_debate_summary(conn, org_id: int, case_id: int) -> dict[str, Any] | None:
    version = conn.execute(
        "SELECT * FROM inst_research_version WHERE case_id=%s ORDER BY version_no DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    if not version:
        return None
    version = dict(version)
    session = conn.execute(
        "SELECT * FROM inst_debate_session WHERE case_id=%s AND status='completed' "
        "ORDER BY id DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    debate = None
    if session:
        args = conn.execute(
            "SELECT * FROM inst_debate_argument WHERE session_id=%s ORDER BY id",
            (int(session["id"]),),
        ).fetchall()
        checks = conn.execute(
            "SELECT * FROM inst_evidence_check WHERE session_id=%s ORDER BY id",
            (int(session["id"]),),
        ).fetchall()
        debate = {
            "id": int(session["id"]),
            "conclusion": session.get("conclusion"),
            "arguments": [_row_dict(r) or {} for r in args],
            "evidence_checks": [_row_dict(r) or {} for r in checks],
        }
    memo = get_latest_output(
        "inst.research_memo",
        org_id=org_id,
        scope_key=f"case:{case_id}:version:{int(version['id'])}",
    )
    return {
        "version_no": version.get("version_no"),
        "status": version.get("status"),
        "industry_analysis": version.get("industry_analysis"),
        "six_dim": version.get("six_dim") or [],
        "overall_score": _overall_score(version.get("six_dim") or []),
        "memo": (memo or {}).get("output") if memo else None,
        "debate": debate,
    }


def list_proposals_for_member(
    org_id: int, member_id: int, role: str, *, scope: str = "pending"
) -> list[dict[str, Any]]:
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
    params: list[Any] = [org_id]
    if role == "manager":
        sql += " AND p.created_by=%s"
        params.append(member_id)
    elif role == "partner":
        if scope == "reviewed":
            sql += (
                " AND EXISTS (SELECT 1 FROM inst_approval ap"
                " JOIN inst_proposal_version pv ON pv.id=ap.proposal_version_id"
                " WHERE pv.proposal_id=p.id AND ap.step='partner' AND ap.approver_member_id=%s)"
            )
        else:
            sql += (
                " AND p.status IN ('draft','partner_review')"
                " AND NOT EXISTS (SELECT 1 FROM inst_approval ap"
                " JOIN inst_proposal_version pv ON pv.id=ap.proposal_version_id"
                " WHERE pv.proposal_id=p.id AND ap.step='partner' AND ap.approver_member_id=%s)"
            )
        params.append(member_id)
    elif role == "risk":
        if scope == "reviewed":
            sql += (
                " AND EXISTS (SELECT 1 FROM inst_approval ap"
                " JOIN inst_proposal_version pv ON pv.id=ap.proposal_version_id"
                " WHERE pv.proposal_id=p.id AND ap.step='risk_precheck' AND ap.approver_member_id=%s)"
            )
        else:
            sql += (
                " AND p.status IN ('risk_precheck','chairman_review')"
                " AND NOT EXISTS (SELECT 1 FROM inst_approval ap"
                " JOIN inst_proposal_version pv ON pv.id=ap.proposal_version_id"
                " WHERE pv.proposal_id=p.id AND ap.step='risk_precheck' AND ap.approver_member_id=%s)"
            )
        params.append(member_id)
    elif role == "chairman":
        if scope == "reviewed":
            sql += (
                " AND EXISTS (SELECT 1 FROM inst_approval ap"
                " JOIN inst_proposal_version pv ON pv.id=ap.proposal_version_id"
                " WHERE pv.proposal_id=p.id AND ap.step='chairman' AND ap.approver_member_id=%s)"
            )
        else:
            sql += (
                " AND p.status='chairman_review'"
                " AND NOT EXISTS (SELECT 1 FROM inst_approval ap"
                " JOIN inst_proposal_version pv ON pv.id=ap.proposal_version_id"
                " WHERE pv.proposal_id=p.id AND ap.step='chairman' AND ap.approver_member_id=%s)"
                " AND NOT EXISTS (SELECT 1 FROM inst_approval ar"
                " JOIN inst_proposal_version pvr ON pvr.id=ar.proposal_version_id"
                " WHERE pvr.proposal_id=p.id AND ar.step='risk_precheck' AND ar.decision IN ('veto','block'))"
            )
        params.append(member_id)
    else:
        return []
    sql += " ORDER BY p.updated_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) or {} for r in rows]


def _overall_score_for_case(conn, org_id: int, case_id: int) -> float | None:
    row = conn.execute(
        "SELECT six_dim FROM inst_research_version "
        "WHERE case_id=%s AND superseded_at IS NULL AND status='approved' "
        "ORDER BY version_no DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT six_dim FROM inst_research_version WHERE case_id=%s "
            "ORDER BY version_no DESC LIMIT 1",
            (case_id,),
        ).fetchone()
    return _overall_score((row or {}).get("six_dim") or [])


def _proposal_common(data: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "status", "direction", "target_weight", "company_id", "symbol",
        "company_name", "market", "industry", "created_by", "created_at", "updated_at",
        "case_id", "exit_case", "overall_score",
    )
    out = {k: data.get(k) for k in keys}
    out["current_version"] = data.get("current_version")
    return out


def _my_decision(
    rows: list[dict[str, Any]], step: str, member_id: int
) -> dict[str, Any] | None:
    for row in reversed(rows):
        if (
            str(row.get("step") or "") == step
            and int(row.get("approver_member_id") or 0) == int(member_id)
        ):
            return {
                "decision": row.get("decision"),
                "comment": row.get("comment"),
                "conditions": row.get("conditions") or [],
                "decided_at": _stage_time(row.get("decided_at")),
            }
    return None


def get_proposal_for_member(
    org_id: int, proposal_id: int, *, member_id: int, role: str
) -> dict[str, Any] | None:
    data = get_proposal(org_id, proposal_id)
    if not data:
        return None
    with get_conn() as conn:
        data["overall_score"] = _overall_score_for_case(
            conn, org_id, int(data.get("case_id") or 0)
        )
    rows = data.get("approvals") or []
    status = str(data.get("status") or "")
    created_by = int(data.get("created_by") or 0)

    def has_step(step: str) -> bool:
        return any(
            str(r.get("step") or "") == step
            and int(r.get("approver_member_id") or 0) == int(member_id)
            for r in rows
        )

    if role == "manager":
        if created_by != int(member_id):
            raise PermissionError("该议案不在你当前角色的审批范围")
        out = _proposal_common(data)
        with get_conn() as conn:
            out["progress"] = _proposal_progress(conn, org_id, rows)
        out["authorization"] = _authorization_summary(data)
        return out

    if role == "partner":
        if not (status in {"draft", "partner_review"} or has_step("partner")):
            raise PermissionError("该议案不在你当前角色的审批范围")
        out = _proposal_common(data)
        out["my_decision"] = _my_decision(rows, "partner", int(member_id))
        with get_conn() as conn:
            out["progress"] = _proposal_progress(conn, org_id, rows)
            out["research_debate"] = (
                _research_debate_summary(conn, org_id, int(data["case_id"]))
                if data.get("case_id")
                else None
            )
        return out

    if role == "risk":
        if not (status in {"risk_precheck", "chairman_review"} or has_step("risk_precheck")):
            raise PermissionError("该议案不在你当前角色的审批范围")
        out = _proposal_common(data)
        out["my_decision"] = _my_decision(rows, "risk_precheck", int(member_id))
        with get_conn() as conn:
            out["progress"] = _proposal_progress(conn, org_id, rows)
        out["risk_checks"] = data.get("risk_checks") or []
        out["partner_stage"] = out["progress"]["partner"]
        return out

    if role == "chairman":
        if not (status == "chairman_review" or has_step("chairman")):
            raise PermissionError("该议案不在你当前角色的审批范围")
        out = _proposal_common(data)
        out["my_decision"] = _my_decision(rows, "chairman", int(member_id))
        with get_conn() as conn:
            out["progress"] = _proposal_progress(conn, org_id, rows)
            out["research_debate"] = (
                _research_debate_summary(conn, org_id, int(data["case_id"]))
                if data.get("case_id")
                else None
            )
        out["risk_stage"] = out["progress"]["risk_precheck"]
        out["approval_chain"] = _stage_summary(
            "partner", rows, out["progress"]["partner"]["total"], include_items=True
        )["items"] + _stage_summary(
            "risk_precheck", rows, out["progress"]["risk_precheck"]["total"], include_items=True
        )["items"] + _stage_summary(
            "chairman", rows, out["progress"]["chairman"]["total"], include_items=True
        )["items"]
        out["authorization"] = _authorization_summary(data)
        return out

    raise PermissionError("该议案不在你当前角色的审批范围")


def get_proposal(org_id: int, proposal_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            return None
        versions = repo.proposal_versions(proposal_id, conn=conn)
        version = versions[0] if versions else None
        approvals = []
        auths = []
        if version:
            approvals = repo.proposal_approvals(version["id"], conn=conn)
            auths = repo.proposal_authorizations(version["id"], conn=conn)
        exit_case = repo.proposal_exit_case(OrgScope(org_id), proposal_id, conn=conn)
        # 六项风控检查按实时数据计算，供审批页在人工复核前查看。
        risk_checks = _risk_checks(conn, org_id, proposal, version) if version else []
    proposal["versions"] = versions
    proposal["current_version"] = version
    proposal["approvals"] = approvals
    proposal["authorizations"] = auths
    proposal["risk_checks"] = risk_checks
    proposal["exit_case"] = exit_case
    return proposal


def _approval_rows(conn, version_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM inst_approval WHERE proposal_version_id=%s ORDER BY decided_at, id",
        (version_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _approval_state(
    rows: list[dict[str, Any]], required: dict[str, int] | None = None
) -> dict[str, dict[str, Any]]:
    """按角色汇总多人审批：全部有效审批人给出意见才算通过；风控否决终局。"""
    role_for = {"partner": "partner", "risk_precheck": "risk", "chairman": "chairman"}
    counts = required or {}
    state: dict[str, dict[str, Any]] = {}
    for step in ("partner", "risk_precheck", "chairman"):
        items = [r for r in rows if str(r.get("step") or "") == step]
        decisions = [str(r.get("decision") or "") for r in items]
        approvers = {int(r.get("approver_member_id") or 0) for r in items if r.get("approver_member_id")}
        req = int(counts.get(role_for[step], 0))
        if req <= 0:
            req = max(1, len(approvers))
        if step == "risk_precheck":
            approved = [d for d in decisions if d in {"pass", "conditional"}]
            vetoed = any(d in {"veto", "block"} for d in decisions)
            passed = not vetoed and len(approvers) >= req and len(approved) >= req
            blocked = vetoed
        elif step == "chairman":
            approved = [d for d in decisions if d in {"approve", "conditional"}]
            rejected = any(d in {"reject", "veto", "block"} for d in decisions)
            passed = not rejected and len(approvers) >= req and len(approved) >= req
            vetoed = False
            blocked = rejected
        else:
            approved = [d for d in decisions if d in {"approve", "conditional"}]
            returned = any(d in {"return", "reject"} for d in decisions)
            passed = not returned and len(approvers) >= req and len(approved) >= req
            vetoed = False
            blocked = returned
        state[step] = {
            "items": items,
            "latest": items[-1] if items else None,
            "passed": passed,
            "vetoed": vetoed,
            "blocked": blocked,
            "required": req,
            "decided": len(approvers),
            "approved": len(approved),
            "conditions": [
                str(c).strip()
                for r in items
                for c in (r.get("conditions") or [])
                if str(c).strip()
            ],
        }
    return state


def _clean_conditions(conditions: Any) -> list[str]:
    if isinstance(conditions, str):
        conditions = [x.strip() for x in conditions.splitlines()]
    if not isinstance(conditions, list):
        return []
    return [str(x).strip()[:300] for x in conditions if str(x).strip()][:10]


def _role_member_ids(
    conn, org_id: int, role: str, *, exclude_member_id: int | None = None
) -> set[int]:
    rows = conn.execute(
        "SELECT id FROM inst_members WHERE org_id=%s AND role=%s AND status='active'",
        (org_id, role),
    ).fetchall()
    exclude = int(exclude_member_id or 0)
    return {int(r["id"]) for r in rows if int(r["id"]) != exclude}


def _insert_approval(
    conn,
    *,
    version_id: int,
    step: str,
    actor_member_id: int | None,
    decision: str,
    comment: str | None,
    conditions: list[str] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO inst_approval
          (proposal_version_id, step, approver_member_id, decision, comment, policy_version, conditions)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (proposal_version_id, step, approver_member_id) DO UPDATE
          SET decision=EXCLUDED.decision, comment=EXCLUDED.comment,
              conditions=EXCLUDED.conditions, policy_version=EXCLUDED.policy_version,
              decided_at=NOW()
        """,
        (
            version_id,
            step,
            actor_member_id,
            decision,
            comment,
            POLICY_VERSION,
            _j(conditions or []),
        ),
    )


def partner_review(
    org_id: int,
    proposal_id: int,
    *,
    decision: str,
    comment: str | None,
    updates: dict[str, Any] | None,
    actor_member_id: int | None,
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    if decision not in {"approve", "conditional", "return"}:
        raise ValueError("decision 必须是 approve/conditional/return")
    condition_list = _clean_conditions(conditions)
    if decision == "conditional" and not condition_list:
        raise ValueError("附条件通过必须填写具体条件")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "partner")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        if proposal.get("stale_at"):
            raise PermissionError("研究已重开，议案已作废，不能继续审批")
        if int(proposal.get("created_by") or 0) == int(actor_member_id or 0):
            raise PermissionError("提案人不得审批自己的议案")
        # 顺序固定：合伙人 → 风控 → Chairman，合伙人通过后本环节关闭。
        if proposal["status"] not in {"draft", "partner_review"}:
            raise PermissionError("合伙人审批环节已结束，不能重复审批")
        conn.execute("SELECT pg_advisory_xact_lock(7305, %s::int)", (proposal_id,))
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        snapshot = dict(current.get("snapshot") or {})
        version_id = int(current["id"])
        version_no = int(current["version_no"])
        if updates:
            # 审批人只能调整可协商字段；方向、研究版本、账户与哈希等身份字段不可改写。
            editable = {
                "investment_opinion", "monitoring", "funding_source",
                "valid_until", "price_low", "price_high", "target_weight",
            }
            forbidden = sorted(set(updates) - editable)
            if forbidden:
                raise ValueError(f"合伙人不能修改字段：{', '.join(forbidden)}")
            snapshot.update({k: updates[k] for k in updates if k in editable})
            gate = evaluate_proposal_gate(conn, proposal, {"snapshot": snapshot})
            if gate["status"] == "block":
                raise PermissionError("修改后议案门禁未通过：" + "；".join(
                    x["detail"] for x in gate["checks"] if x["status"] == "block"
                ))
            version_no += 1
            row = conn.execute(
                "INSERT INTO inst_proposal_version (proposal_id, version_no, snapshot, status, created_by) "
                "VALUES (%s,%s,%s,'partner_submitted',%s) RETURNING id",
                (proposal_id, version_no, _j(snapshot), actor_member_id),
            ).fetchone()
            version_id = int(row["id"])
        _insert_approval(
            conn,
            version_id=version_id,
            step="partner",
            actor_member_id=actor_member_id,
            decision=decision,
            comment=comment,
            conditions=condition_list,
        )
        rows = _approval_rows(conn, version_id)
        partner_rows = [r for r in rows if r.get("step") == "partner"]
        decided = {
            int(r["approver_member_id"])
            for r in partner_rows
            if r.get("approver_member_id")
        }
        required = _role_member_ids(
            conn, org_id, "partner", exclude_member_id=proposal.get("created_by")
        )
        if not required:
            raise PermissionError("当前机构没有可用的合伙人审批人")
        returned = any(str(r.get("decision")) == "return" for r in partner_rows)
        # 同角色多人：全部给出意见、且无人退回，才进入风控。
        new_status = (
            "partner_review"
            if returned or not required <= decided
            else "risk_precheck"
        )
        conn.execute(
            "UPDATE inst_proposal SET status=%s, current_version_no=%s, updated_at=NOW() WHERE id=%s",
            (new_status, version_no, proposal_id),
        )
        conn.execute(
            "UPDATE inst_proposal_version SET status=%s WHERE id=%s",
            ("draft" if decision == "return" else "partner_submitted", version_id),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"proposal.partner.{decision}",
            object_type="inst_proposal",
            object_id=proposal_id,
            before={"status": proposal["status"], "version_no": current["version_no"]},
            after={
                "status": new_status,
                "version_no": version_no,
                "comment": comment,
                "conditions": condition_list,
                "reviewed": len(decided),
                "required": len(required),
            },
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def chairman_review(
    org_id: int,
    proposal_id: int,
    *,
    decision: str,
    comment: str | None,
    actor_member_id: int | None,
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    if decision not in {"approve", "conditional", "return", "reject"}:
        raise ValueError("decision 必须是 approve/conditional/return/reject")
    condition_list = _clean_conditions(conditions)
    if decision == "conditional" and not condition_list:
        raise ValueError("附条件批准必须填写具体条件")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        if proposal.get("stale_at"):
            raise PermissionError("研究已重开，议案已作废，不能继续审批")
        if int(proposal.get("created_by") or 0) == int(actor_member_id or 0):
            raise PermissionError("提案人不得审批自己的议案")
        # 顺序固定：合伙人 → 风控 → Chairman，不能跳级。
        if proposal["status"] != "chairman_review":
            raise PermissionError("议案尚未到达 Chairman 环节（需合伙人、风控先后通过）")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        state = _approval_state(_approval_rows(conn, int(current["id"])), _member_role_counts(conn, org_id))
        if state["risk_precheck"]["vetoed"]:
            raise PermissionError("独立风控已否决，Chairman 不能批准")
        if not state["partner"]["passed"]:
            raise PermissionError("合伙人复核未通过，不能提交 Chairman")
        if not state["risk_precheck"]["passed"]:
            raise PermissionError("独立风控尚未放行，不能提交 Chairman")
        _insert_approval(
            conn,
            version_id=int(current["id"]),
            step="chairman",
            actor_member_id=actor_member_id,
            decision=decision,
            comment=comment,
            conditions=condition_list,
        )
        rows = _approval_rows(conn, int(current["id"]))
        chair_rows = [r for r in rows if r.get("step") == "chairman"]
        decided = {
            int(r["approver_member_id"])
            for r in chair_rows
            if r.get("approver_member_id")
        }
        required = _role_member_ids(
            conn, org_id, "chairman", exclude_member_id=proposal.get("created_by")
        )
        if not required:
            raise PermissionError("当前机构没有可用的 Chairman 审批人")
        if decision == "reject":
            status = "rejected"
        elif decision == "return":
            status = "partner_review"
        elif required <= decided:
            status = "authorized"
        else:
            status = "chairman_review"
        conn.execute("UPDATE inst_proposal SET status=%s, updated_at=NOW() WHERE id=%s", (status, proposal_id))
        if status == "authorized":
            conn.execute("UPDATE inst_proposal_version SET status='chairman_approved' WHERE id=%s", (current["id"],))
        elif decision == "return":
            conn.execute("UPDATE inst_proposal_version SET status='draft' WHERE id=%s", (current["id"],))
        elif decision == "reject":
            conn.execute("UPDATE inst_proposal_version SET status='rejected' WHERE id=%s", (current["id"],))
        exit_case = _exit_case_for_proposal(conn, org_id, proposal_id)
        if exit_case and status == "authorized":
            _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "approved",
                actor_member_id=actor_member_id,
                action="monitor.exit.approve",
                extra={"proposal_id": proposal_id, "decision": decision},
            )
        elif exit_case and decision == "reject":
            _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "rejected",
                actor_member_id=actor_member_id,
                action="monitor.exit.reject",
                extra={"proposal_id": proposal_id, "decision": decision},
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"proposal.chairman.{decision}",
            object_type="inst_proposal",
            object_id=proposal_id,
            before={"status": proposal["status"]},
            after={
                "status": status,
                "comment": comment,
                "conditions": condition_list,
                "reviewed": len(decided),
                "required": len(required),
            },
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def _evidence_approval_check(conn, proposal: dict[str, Any]) -> dict[str, Any]:
    """未验证/矛盾证据不得进入审批：检查本轮辩论中有效论点的证据核验状态。"""
    case_id = proposal.get("case_id")
    session = (
        conn.execute(
            "SELECT id FROM inst_debate_session WHERE case_id=%s AND status='completed' "
            "ORDER BY id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if case_id
        else None
    )
    if not session:
        return {
            "key": "evidence_verification",
            "label": "证据核验可用于审批",
            "value": "无已完成辩论",
            "status": "block",
        }
    total = conn.execute(
        """
        SELECT COUNT(*) AS n
          FROM inst_evidence_check ec
          JOIN inst_debate_argument a
            ON a.session_id=ec.session_id AND a.claim_id=ec.claim_id
         WHERE ec.session_id=%s AND a.valid=TRUE AND a.side IN ('bull','bear')
        """,
        (int(session["id"]),),
    ).fetchone()["n"]
    bad = conn.execute(
        """
        SELECT COUNT(*) AS n
          FROM inst_evidence_check ec
          JOIN inst_debate_argument a
            ON a.session_id=ec.session_id AND a.claim_id=ec.claim_id
         WHERE ec.session_id=%s AND a.valid=TRUE AND a.side IN ('bull','bear')
           AND ec.status IN ('unverified','contradicted')
        """,
        (int(session["id"]),),
    ).fetchone()["n"]
    total, bad = int(total or 0), int(bad or 0)
    return {
        "key": "evidence_verification",
        "label": "证据核验可用于审批",
        "threshold": None,
        "value": f"有效证据 {total} 条，未验证/矛盾 {bad} 条",
        "status": "pass" if total > 0 and bad == 0 else "block",
    }


def _issuer_key(name: Any) -> str:
    return re.sub(r"[\s\-·（）()]+", "", str(name or "")).lower()


def _risk_checks(conn, org_id: int, proposal: dict[str, Any], version: dict[str, Any]) -> list[dict[str, Any]]:
    """六项硬约束：集中度、现金、版本一致、有效期与价格、交易资格、重复与冲突。

    状态：pass 通过 / warn 警告 / block 否决。
    """
    snapshot = version.get("snapshot") or {}
    direction = str(proposal.get("direction") or snapshot.get("direction") or "buy")
    is_buy = direction == "buy"
    target = float(snapshot.get("target_weight") or proposal.get("target_weight") or 0)
    portfolio = conn.execute(
        "SELECT id, nav, cash FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
    ).fetchone()
    pf = dict(portfolio) if portfolio else {}
    nav = float(pf.get("nav") or DEFAULT_NAV)
    cash = float(pf.get("cash") or nav)
    amount = target * nav if is_buy else 0.0
    cash_after = (cash - amount) / nav if nav else 0.0

    company_row = (
        conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s",
            (proposal.get("company_id"), org_id),
        ).fetchone()
        if proposal.get("company_id")
        else None
    )
    company = dict(company_row) if company_row else {}
    symbol = str(company.get("symbol") or proposal.get("symbol") or "")
    company_key = _issuer_key(company.get("name"))
    industry = str(company.get("industry") or "")

    # 现有持仓（最新快照）：同发行人（同公司名，跨 A/H/美股）与同行业聚合。
    positions = [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM (
              SELECT DISTINCT ON (ps.symbol)
                     ps.symbol, ps.qty, ps.market_value, co.name, co.industry
                FROM inst_position_snapshot ps
                JOIN inst_portfolio p ON p.id=ps.portfolio_id
                LEFT JOIN inst_company co ON co.symbol=ps.symbol AND co.org_id=p.org_id
               WHERE p.org_id=%s
               ORDER BY ps.symbol, ps.as_of DESC, ps.id DESC
            ) latest
             WHERE latest.qty > 0
            """,
            (org_id,),
        ).fetchall()
    ]
    issuer_weight = sum(
        float(p.get("market_value") or 0)
        for p in positions
        if company_key and _issuer_key(p.get("name")) == company_key
    ) / nav if nav else 0.0
    industry_weight = sum(
        float(p.get("market_value") or 0)
        for p in positions
        if industry and str(p.get("industry") or "") == industry
    ) / nav if nav else 0.0
    issuer_after = issuer_weight + target if is_buy else issuer_weight
    industry_after = industry_weight + target if is_buy else industry_weight

    if not is_buy:
        concentration = {"status": "pass", "value": "减持/退出不受集中度限制"}
    elif not company_key:
        concentration = {"status": "warn", "value": "缺少公司信息，无法核对同发行人集中度"}
    else:
        status = "pass"
        if issuer_after > MAX_SINGLE_WEIGHT or industry_after > MAX_INDUSTRY_WEIGHT:
            status = "block"
        elif issuer_after >= MAX_SINGLE_WEIGHT * 0.85 or industry_after >= MAX_INDUSTRY_WEIGHT * 0.85:
            status = "warn"
        if not industry:
            status = "warn" if status == "pass" else status
        concentration = {
            "status": status,
            "value": (
                f"同发行人 {issuer_after:.1%}（已持 {issuer_weight:.1%} + 本议案 {target:.1%}）；"
                f"同行业 {industry_after:.1%}（{industry or '行业待补充'}）"
            ),
        }

    if is_buy:
        cash_status = "pass"
        if cash_after < MIN_CASH_RATIO:
            cash_status = "block"
        elif cash_after < MIN_CASH_RATIO * 1.2:
            cash_status = "warn"
        cash_check = {
            "status": cash_status,
            "value": f"交易后现金 {cash_after:.1%}（现金 {cash:,.0f} / 净值 {nav:,.0f}）",
        }
    else:
        cash_check = {"status": "pass", "value": "卖出增加现金，不做现金下限校验"}

    research_id = snapshot.get("research_version_id")
    research_row = (
        conn.execute("SELECT * FROM inst_research_version WHERE id=%s", (research_id,)).fetchone()
        if research_id
        else None
    )
    research = dict(research_row) if research_row else {}
    research_hash = str(research.get("content_hash") or "")
    research_ev_ids = [int(x) for x in (research.get("evidence_ids") or []) if str(x).isdigit()]
    case_scope = int(proposal.get("case_id") or research.get("case_id") or 0) or None
    current_evidence_hash = (
        _hash(_evidence_payload(
            conn, research_ev_ids, org_id=org_id, case_id=case_scope
        ))
        if research_ev_ids else None
    )
    snapshot_research_hash = str(snapshot.get("research_content_hash") or "")
    snapshot_evidence_hash = snapshot.get("evidence_hash")
    hash_ok = bool(
        research
        and research_hash
        and snapshot_research_hash == research_hash
        and snapshot_evidence_hash == current_evidence_hash
    )
    debate = (
        conn.execute(
            "SELECT id FROM inst_debate_session WHERE case_id=%s AND status='completed' "
            "ORDER BY id DESC LIMIT 1",
            (proposal.get("case_id"),),
        ).fetchone()
        if proposal.get("case_id")
        else None
    )
    evidence_check = _evidence_approval_check(conn, proposal)
    if not proposal.get("case_id"):
        evidence_status = "warn"
    else:
        evidence_status = str(evidence_check.get("status") or "warn")
    version_status = "pass"
    if not research or not snapshot.get("research_version_id") or not hash_ok:
        version_status = "block"
    elif evidence_status == "block":
        version_status = "block"
    elif not debate:
        version_status = "warn"
    version_check = {
        "status": version_status,
        "value": (
            f"研究 v{snapshot.get('research_version_no') or '缺失'} / "
            f"辩论 #{int(debate['id']) if debate else '缺失'} / "
            f"hash {snapshot_research_hash[:10] or '缺失'} / "
            f"{evidence_check.get('value') or '证据未核验'}"
        ),
    }

    valid_until = snapshot.get("valid_until")
    expired = bool(valid_until and str(valid_until)[:10] < date.today().isoformat())
    low, high = snapshot.get("price_low"), snapshot.get("price_high")
    inverted = low is not None and high is not None and float(low) > float(high)
    bar = (
        conn.execute(
            "SELECT close FROM md_daily_bar WHERE symbol=%s AND adjust='none' "
            "ORDER BY trade_date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if symbol
        else None
    )
    last_px = float((dict(bar) if bar else {}).get("close") or 0) if bar else 0.0
    price_status = "pass"
    price_notes: list[str] = []
    if expired:
        price_status = "block"
        price_notes.append(f"授权已于 {str(valid_until)[:10]} 过期")
    if inverted:
        price_status = "block"
        price_notes.append(f"价格区间倒挂（{low} - {high}）")
    elif is_buy and low is not None and high is not None and last_px > 0:
        if last_px < float(low) or last_px > float(high):
            price_status = "block"
            price_notes.append(f"现价 {last_px:g} 超出批准区间 {float(low):g}-{float(high):g}")
    if not price_notes:
        price_notes.append(
            f"有效期 {str(valid_until)[:10] or '未设置'}；"
            + (f"现价 {last_px:g} / 区间 {low}-{high}" if last_px else "无最新行情")
        )
    validity_check = {"status": price_status, "value": "；".join(price_notes)}

    status_row = (
        conn.execute(
            "SELECT trade_date, listed_status, up_down_status, is_st, is_suspended "
            "FROM md_status_daily WHERE symbol=%s ORDER BY trade_date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if symbol
        else None
    )
    if status_row:
        status_row = dict(status_row)
    trading_status = "pass"
    trading_notes: list[str] = []
    if status_row:
        listed = str(status_row.get("listed_status") or "")
        updown = str(status_row.get("up_down_status") or "")
        if status_row.get("is_suspended") or updown == "停牌":
            trading_status = "block"
            trading_notes.append("停牌")
        if status_row.get("is_st") or "ST" in listed:
            trading_status = "block"
            trading_notes.append(listed or "ST")
        if listed in {"退市整理", "终止上市"}:
            trading_status = "block"
            trading_notes.append(listed)
        if updown in {"涨停", "跌停"}:
            trading_status = "block"
            trading_notes.append(updown)
        if not trading_notes:
            trading_notes.append(f"{listed or '在市'} / {updown or '正常'}")
    else:
        trading_status = "warn"
        trading_notes.append("无交易状态数据")
    pos_row = (
        conn.execute(
            "SELECT qty FROM inst_position_snapshot ps JOIN inst_portfolio p ON p.id=ps.portfolio_id "
            "WHERE p.org_id=%s AND ps.symbol=%s AND ps.qty>0 ORDER BY ps.as_of DESC LIMIT 1",
            (org_id, symbol),
        ).fetchone()
        if symbol
        else None
    )
    if is_buy:
        if amount > cash:
            trading_status = "block"
            trading_notes.append(f"现金不足（需 {amount:,.0f}，可用 {cash:,.0f}）")
    else:
        if not pos_row or float(pos_row["qty"]) <= 0:
            trading_status = "block"
            trading_notes.append("无可卖持仓")
        else:
            trading_notes.append(f"可卖 {float(pos_row['qty']):,.0f} 股")
    trading_check = {"status": trading_status, "value": "；".join(trading_notes)}

    duplicate_status = "pass"
    duplicate_notes: list[str] = []
    if proposal.get("company_id"):
        others = conn.execute(
            """
            SELECT id, status, direction, target_weight FROM inst_proposal
             WHERE org_id=%s AND company_id=%s AND id<>%s
               AND status IN ('draft','partner_review','risk_precheck','chairman_review','authorized')
            """,
            (org_id, proposal.get("company_id"), proposal.get("id") or 0),
        ).fetchall()
        if others:
            duplicate_status = "warn"
            duplicate_notes.append(f"同标的有 {len(others)} 个在途议案")
        committed = 0.0
        for r in conn.execute(
            """
            SELECT target_weight FROM inst_proposal
             WHERE org_id=%s AND direction='buy'
               AND status IN ('partner_review','risk_precheck','chairman_review','authorized')
               AND id<>%s
            """,
            (org_id, proposal.get("id") or 0),
        ).fetchall():
            committed += float(r["target_weight"] or 0) * nav
        if is_buy:
            committed += amount
        if committed > cash:
            duplicate_status = "block"
            duplicate_notes.append(f"在途买入合计 {committed:,.0f} 超过现金 {cash:,.0f}")
        qualified = conn.execute(
            """
            SELECT COUNT(*) AS n FROM inst_authorization a
              JOIN inst_proposal_version v ON v.id=a.proposal_version_id
              JOIN inst_proposal p ON p.id=v.proposal_id
             WHERE p.org_id=%s AND p.company_id=%s AND p.id<>%s AND a.status='qualified'
            """,
            (org_id, proposal.get("company_id"), proposal.get("id") or 0),
        ).fetchone()["n"]
        if int(qualified or 0) > 0:
            duplicate_status = "warn" if duplicate_status == "pass" else duplicate_status
            duplicate_notes.append(f"已有 {int(qualified)} 个未执行授权")
    if not duplicate_notes:
        duplicate_notes.append("无重复下单或在途资金冲突")
    duplicate_check = {"status": duplicate_status, "value": "；".join(duplicate_notes)}

    return [
        {
            "key": "concentration",
            "label": "集中度（同发行人 ≤15% / 同行业 ≤30%）",
            "threshold": MAX_SINGLE_WEIGHT,
            **concentration,
        },
        {
            "key": "cash",
            "label": "交易后现金 ≥10%",
            "threshold": MIN_CASH_RATIO,
            **cash_check,
        },
        {
            "key": "version",
            "label": "研究/辩论/证据版本一致",
            "threshold": None,
            **version_check,
        },
        {
            "key": "validity_price",
            "label": "有效期与价格",
            "threshold": None,
            **validity_check,
        },
        {
            "key": "trading_qualification",
            "label": "交易资格（停牌/涨跌停/ST/资金或持仓）",
            "threshold": None,
            **trading_check,
        },
        {
            "key": "duplicate_conflict",
            "label": "重复与冲突",
            "threshold": None,
            **duplicate_check,
        },
    ]


def risk_check(
    org_id: int,
    proposal_id: int,
    *,
    actor_member_id: int | None,
    comment: str | None = None,
    decision: str | None = None,
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    if decision not in {None, "pass", "conditional", "veto"}:
        raise ValueError("decision 必须是 pass/conditional/veto")
    condition_list = _clean_conditions(conditions)
    if decision == "conditional" and not condition_list:
        raise ValueError("有条件放行必须填写具体条件")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "risk")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        if proposal.get("stale_at"):
            raise PermissionError("研究已重开，议案已作废，不能继续审批")
        if int(proposal.get("created_by") or 0) == int(actor_member_id or 0):
            raise PermissionError("提案人不得审批自己的议案")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        state = _approval_state(_approval_rows(conn, int(current["id"])), _member_role_counts(conn, org_id))
        if not state["partner"]["passed"]:
            raise PermissionError("合伙人复核未通过，不能进入风控")
        # 顺序固定：合伙人 → 风控 → Chairman；风控可在 Chairman 批准前追加否决。
        if proposal["status"] not in {"risk_precheck", "chairman_review"}:
            raise PermissionError("议案已离开风控环节，不能再审批")
        checks = _risk_checks(conn, org_id, proposal, current)
        hard_blocks = [c for c in checks if c["status"] == "block"]
        effective = "veto" if hard_blocks else (decision or "pass")
        _insert_approval(
            conn,
            version_id=int(current["id"]),
            step="risk_precheck",
            actor_member_id=actor_member_id,
            decision=effective,
            comment=comment,
            conditions=condition_list,
        )
        if effective == "veto":
            reason = "；".join(str(c["label"]) for c in hard_blocks) or "风控否决"
            conn.execute(
                "UPDATE inst_proposal SET status='frozen', updated_at=NOW() WHERE id=%s", (proposal_id,)
            )
            conn.execute("UPDATE inst_proposal_version SET status='revoked' WHERE id=%s", (current["id"],))
            exit_case = _exit_case_for_proposal(conn, org_id, proposal_id)
            if exit_case:
                _advance_exit_case(
                    conn,
                    org_id,
                    exit_case,
                    "rejected",
                    actor_member_id=actor_member_id,
                    action="monitor.exit.risk_block",
                    extra={"proposal_id": proposal_id, "risk_decision": effective},
                )
        else:
            rows = _approval_rows(conn, int(current["id"]))
            risk_rows = [r for r in rows if r.get("step") == "risk_precheck"]
            decided = {
                int(r["approver_member_id"])
                for r in risk_rows
                if r.get("approver_member_id")
            }
            required = _role_member_ids(
                conn, org_id, "risk", exclude_member_id=proposal.get("created_by")
            )
            if not required:
                raise PermissionError("当前机构没有可用的风控审批人")
            # 同角色多人：全部给出意见且无人否决，才进入 Chairman。
            if required <= decided:
                conn.execute(
                    "UPDATE inst_proposal SET status='chairman_review', updated_at=NOW() WHERE id=%s",
                    (proposal_id,),
                )
                conn.execute("UPDATE inst_proposal_version SET status='risk_passed' WHERE id=%s", (current["id"],))
            else:
                conn.execute(
                    "UPDATE inst_proposal SET status='risk_precheck', updated_at=NOW() WHERE id=%s",
                    (proposal_id,),
                )
            reason = ""
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"proposal.risk.{effective}",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={
                "checks": checks,
                "comment": comment,
                "conditions": condition_list,
                "reason": reason,
                "reviewed": len(decided) if effective != "veto" else None,
                "required": len(required) if effective != "veto" else None,
            },
        )
    out = get_proposal(org_id, proposal_id) or {}
    out["risk_checks"] = checks
    return out


