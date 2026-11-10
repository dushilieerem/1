# -*- coding: utf-8 -*-
"""主观机构端业务服务：公司池、研究、辩论、议案、审批、授权、模拟执行、投后。

边界：
- 这里是业务事实与状态机；AI 只产生建议，不直接改状态（`ai/inst_agents.py` 负责生成）。
- 硬约束在服务端校验：单股 ≤15%、交易后现金 ≥10%、版本一致、无有效批准不得授权。
- 授权是不可变快照；撤销写新行，不 UPDATE 旧行。
"""
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
from . import repo
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

# 拆分后的公共部分（保持 inst_service 旧有名字可用，路由无需改动）
from .common import (  # noqa: F401
    _clip_brief,
    _evidence_grade,
    _hash,
    _iso,
    _j,
    _pc,
    _row_dict,
    _yi,
)
from .stages import (  # noqa: F401
    STAGE_BY_KEY,
    STAGE_BY_NO,
    STAGE_DEFS,
    _record_gate,
    _record_transition,
    _set_case_stage,
    _stage_def,
    _stage_payload,
)
from .guards import (  # noqa: F401
    POLICY_VERSION,
    _audit,
    _member,
    _require_role,
    _uid,
)
from .company_service import (  # noqa: F401
    DEFAULT_NAV,
    DEMO_COMPANIES,
    MAX_INDUSTRY_WEIGHT,
    MAX_SINGLE_WEIGHT,
    MIN_CASH_RATIO,
    _mapped_industry,
    _seed_companies,
    _sync_company_universe,
    ensure_and_seed,
    list_companies,
    search_companies,
    update_company_pool,
)
from .research_service import (  # noqa: F401
    DIMENSION_TASK_IDS,
    SIX_DIM_DEFS,
    _TERM_GLOSSARY,
    _VAGUE_REPLACEMENTS,
    _agent_payload,
    _apply_data_gate,
    _build_research,
    _clean_agent_text,
    _data_completeness,
    _derive_case_stage,
    _dim_status,
    _ensure_version_hash,
    _existing_case_id,
    _first_sentence,
    _four_line_output,
    _history_summary,
    _idea_data_sufficiency,
    _idea_questions,
    _lock_company_case,
    _median,
    _merge_agent_results,
    _merge_industry,
    _net_debt_proxy,
    _overall_score,
    _peer_summary,
    _resample_bars,
    _run_dimension_agent,
    _run_dimension_agents,
    _run_industry_agent,
    _six_dim_list,
    _update_task_progress,
    company_bars,
    create_case,
    evaluate_research_gate,
    export_research,
    generate_research,
    get_case,
    get_company,
    ideas_push,
    list_cases,
    lock_research,
    record_idea_decision,
    reopen_research,
    research_gate,
    review_research,
    review_research_dimension,
    start_research,
)

MAX_SINGLE_WEIGHT = 0.15
MAX_INDUSTRY_WEIGHT = 0.30
MIN_CASH_RATIO = 0.10



class AiUnavailable(RuntimeError):
    """AI 未配置/不可用；由路由层映射为 503。"""




# ---------------------------------------------------------------- 基础工具


# ---------------------------------------------------------------- 种子


# ---------------------------------------------------------------- 驾驶舱 / 公司池


def overview(org_id: int, role: str) -> dict[str, Any]:
    data = repo.overview(OrgScope(org_id), role)
    pf = data.get("portfolio") or {}
    nav = float(pf.get("nav") or DEFAULT_NAV)
    cash = float(pf.get("cash") or nav)
    return {
        "org_id": org_id,
        "role": role,
        "companies": data["companies"],
        "active_cases": data["active_cases"],
        "pending_approvals": data["pending_approvals"],
        "my_pending": data["my_pending"],
        "risk_blocks": data["risk_blocks"],
        "monitor_alerts": data["monitor_alerts"],
        "portfolio": {**pf, "invested_ratio": (1 - cash / nav) if nav else 0},
        "data_date": _iso(data["data_date"]) if data.get("data_date") else None,
        "policy": {
            "max_single_weight": MAX_SINGLE_WEIGHT,
            "min_cash_ratio": MIN_CASH_RATIO,
            "nav": nav,
            "policy_version": POLICY_VERSION,
        },
    }


# ---------------------------------------------------------------- v3 流水线 / 结果页


def _pipeline_card(case: dict[str, Any]) -> dict[str, Any]:
    stage_no = case.get("stage_no")
    if stage_no is None:
        stage_no = _derive_case_stage(case)
    stage = _stage_def(stage_no)
    proposals = case.get("proposals") or []
    latest_proposal = proposals[0] if proposals else None
    return {
        "key": f"case:{int(case['id'])}",
        "case_id": int(case["id"]),
        "company_id": int(case["company_id"]),
        "symbol": case.get("symbol"),
        "company_name": case.get("company_name"),
        "industry": case.get("industry"),
        "stage_no": int(stage_no),
        "stage_key": stage["key"],
        "stage_name": stage["name"],
        "gate": stage["gate"],
        "version_no": case.get("version_no"),
        "version_status": case.get("version_status"),
        "conclusion": case.get("conclusion"),
        "proposal_status": (latest_proposal or {}).get("status"),
        "owner_member_id": case.get("created_by"),
        "updated_at": _iso(case.get("updated_at")),
        "stale": bool(latest_proposal and latest_proposal.get("stale_at")),
    }


def pipeline(org_id: int) -> dict[str, Any]:
    """v3 六阶段看板：stage 0 为候选线索，1–5 为研究案/议案/执行/持仓。

    生产默认不截断，返回该环节全部项目。仅演示环境可显式设置
    INST_PIPELINE_PER_STAGE=3 限制每环节展示数（0 或负数表示不限制）。
    """
    try:
        configured = int(os.getenv("INST_PIPELINE_PER_STAGE", "0") or "0")
    except ValueError:
        configured = 0
    per_stage = None if configured <= 0 else max(1, min(configured, 200))

    def _take(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return items if per_stage is None else items[:per_stage]
    cases = [_row_dict(r) or {} for r in repo.cases(OrgScope(org_id))]
    # 同一公司只保留最近更新的研究案；历史案件仍可按项目 key 访问，但不再占多个环节。
    latest_by_company: dict[int, tuple[str, dict[str, Any]]] = {}
    for case in cases:
        company_id = int(case.get("company_id") or 0)
        if not company_id:
            continue
        recency = f"{case.get('updated_at') or ''}|{int(case.get('id') or 0):012d}"
        if company_id not in latest_by_company or recency > latest_by_company[company_id][0]:
            latest_by_company[company_id] = (recency, case)
    by_stage: dict[int, list[dict[str, Any]]] = {i: [] for i in range(6)}
    case_company_ids: set[int] = set()
    for _, case in latest_by_company.values():
        card = _pipeline_card(case)
        by_stage[card["stage_no"]].append(card)
        case_company_ids.add(card["company_id"])
    # stage 0：量化推送 + 观察池，排除已建研究案的公司。
    push = ideas_push(org_id, limit=12).get("items") or []
    watch = list_companies(org_id, pool_status="watch", limit=20).get("items") or []
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()
    for source, items in (("push", push), ("watch", watch)):
        for item in items:
            company_id = int(item.get("id") or 0)
            if not company_id or company_id in seen or company_id in case_company_ids:
                continue
            seen.add(company_id)
            candidates.append({
                "key": f"company:{company_id}",
                "company_id": company_id,
                "symbol": item.get("symbol"),
                "company_name": item.get("name"),
                "industry": item.get("industry"),
                "stage_no": 0,
                "stage_key": "find",
                "stage_name": "机会发现",
                "gate": "立项三问",
                "source": source,
                "idea": item.get("idea"),
                "ref_price": item.get("ref_price") or item.get("last_close"),
                "updated_at": None,
            })
    by_stage[0] = _take(candidates)
    stages = []
    for no in range(6):
        stage = _stage_def(no)
        all_items = by_stage[no]
        items = _take(all_items)
        stages.append({
            "stage_no": no,
            "stage_key": stage["key"],
            "stage_name": stage["name"],
            "gate": stage["gate"],
            "owner": stage["owner"],
            "count": len(items),
            "total_count": len(all_items),
            "truncated": len(items) < len(all_items),
            "items": items,
        })
    return {
        "stages": stages,
        "total": sum(x["count"] for x in stages),
        "total_count": sum(x["total_count"] for x in stages),
    }


def _position_for_symbol(org_id: int, symbol: str) -> dict[str, Any] | None:
    pf = portfolio(org_id)
    for pos in pf.get("positions") or []:
        if str(pos.get("symbol")) == str(symbol):
            return pos
    return None


def project_result(org_id: int, key: str, *, digest: bool = False) -> dict[str, Any]:
    """v3 结果页聚合：company:<id> 为 01 线索，case:<id> 为 02–06 结果。

    digest=True 时只返回结论与状态摘要，不返回六维全文、证据与辩论明细。
    """
    kind, _, raw_id = str(key).partition(":")
    try:
        entity_id = int(raw_id)
    except ValueError:
        raise LookupError("项目不存在") from None
    if kind == "company":
        company = get_company(org_id, entity_id)
        if not company:
            raise LookupError("公司不存在")
        idea = _idea_questions(company, "watch")
        with get_conn() as conn:
            decision = conn.execute(
                "SELECT * FROM inst_idea_decision WHERE org_id=%s AND company_id=%s ORDER BY id DESC LIMIT 1",
                (org_id, entity_id),
            ).fetchone()
        return {
            "key": key,
            "stage_no": 0,
            "stage_key": "find",
            "stage_name": "机会发现",
            "company": {k: company.get(k) for k in ("id", "symbol", "name", "market", "industry", "ref_price", "data_status", "pool_status")},
            "idea": idea,
            "latest_decision": _row_dict(decision),
        }
    if kind != "case":
        raise LookupError("项目不存在")
    case = get_case(org_id, entity_id)
    if not case:
        raise LookupError("研究案不存在")
    latest_version = (case.get("versions") or [{}])[0]
    latest_debate = (case.get("debates") or [{}])[0]
    latest_proposal = (case.get("proposals") or [{}])[0]
    authorization = None
    if latest_proposal.get("id"):
        authorization = authorization_for_proposal(org_id, int(latest_proposal["id"]))
    position = _position_for_symbol(org_id, str(case.get("symbol") or ""))
    if digest:
        case = {
            k: case.get(k)
            for k in (
                "id", "company_id", "symbol", "company_name", "market", "industry",
                "ref_price", "stage_no", "stage_key", "stage_name", "stage_state",
                "stage_gate", "updated_at",
            )
        }
        latest_version = {
            k: (latest_version or {}).get(k)
            for k in ("id", "version_no", "status", "conclusion", "locked_at", "superseded_at")
        }
        latest_debate = {
            k: (latest_debate or {}).get(k)
            for k in ("id", "status", "conclusion", "started_at", "ended_at")
        }
        latest_proposal = {
            k: (latest_proposal or {}).get(k)
            for k in (
                "id", "direction", "target_weight", "status", "current_version_no",
                "price_low", "price_high", "stale_at", "updated_at",
            )
        }
        authorization = {
            k: (authorization or {}).get(k)
            for k in ("id", "status", "issued_at", "version_no")
        } if authorization else None
    return {
        "key": key,
        "digest": digest,
        "case": case,
        "stage_no": case.get("stage_no"),
        "stage_key": case.get("stage_key"),
        "stage_name": case.get("stage_name"),
        "stage_state": case.get("stage_state"),
        "stage_gate": case.get("stage_gate"),
        "locks": case.get("locks"),
        "latest_version": latest_version,
        "latest_debate": latest_debate,
        "latest_proposal": latest_proposal,
        "authorization": authorization,
        "position": position,
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


def holding_detail(org_id: int, symbol: str) -> dict[str, Any]:
    """v3 单票盘中：持仓 + 论点台账 + 监控事件 + 在途退出。"""
    pf = portfolio(org_id)
    position = next((p for p in pf.get("positions") or [] if str(p.get("symbol")) == symbol), None)
    if not position:
        raise LookupError("持仓不存在")
    company_id = position.get("company_id")
    mon = monitor(org_id)
    events = [e for e in mon.get("events") or [] if str(e.get("symbol")) == symbol]
    theses = [t for t in mon.get("theses") or [] if int(t.get("company_id") or 0) == int(company_id or 0)]
    exits = [
        e for e in mon.get("exits") or []
        if int(e.get("company_id") or 0) == int(company_id or 0)
    ]
    version_no = None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT pv.version_no
              FROM inst_proposal p
              JOIN LATERAL (
                SELECT version_no FROM inst_proposal_version
                 WHERE proposal_id=p.id ORDER BY version_no DESC LIMIT 1
              ) pv ON TRUE
             WHERE p.org_id=%s AND p.company_id=%s
             ORDER BY p.updated_at DESC LIMIT 1
            """,
            (org_id, company_id),
        ).fetchone()
        if row:
            version_no = int(row["version_no"])
    return {
        "symbol": symbol,
        "company_id": company_id,
        "version_no": version_no,
        "position": position,
        "events": events,
        "theses": theses,
        "exits": exits,
        "portfolio": pf.get("portfolio"),
    }


def playbook() -> dict[str, Any]:
    """v3 流程与权限静态配置；前端不再硬编码阶段/门禁。"""
    return {
        "stages": [
            {
                "stage_no": x["no"],
                "stage_key": x["key"],
                "stage_name": x["name"],
                "gate": x["gate"],
                "owner": x["owner"],
                "steps": {
                    "research": ["行业分析", "六维结论", "一页纸", "研究定稿"],
                    "debate": ["多空立论", "交叉质询", "估值复核", "议案"],
                    "approve": ["议案提交", "合伙人", "风控", "Chairman", "授权"],
                    "execute": ["授权核对", "下单成交", "对账", "持仓更新"],
                    "manage": ["组合总览", "单票盘中", "预警与退出"],
                }.get(x["key"], []),
            }
            for x in STAGE_DEFS
        ],
        "gates": [
            {"key": "partner", "name": "合伙人", "rule": "研究质量与上会判断", "actions": ["复核通过", "退回", "附条件"]},
            {"key": "risk", "name": "风控", "rule": "六项硬约束 · 一票否决", "actions": ["放行", "否决", "有条件放行"]},
            {"key": "chairman", "name": "Chairman", "rule": "资本配置 · 最终拍板", "actions": ["批准", "附条件", "拒绝", "退回"]},
        ],
        "hard_constraints": [
            "单票 ≤ 15%；同行业 / 同一发行人聚合 ≤ 15%",
            "交易后现金 ≥ 10%",
            "研究定稿 / 议案 / 证据校验码一致",
            "授权在有效期内，价格在批准带内",
            "停牌 / 涨跌停 / ST / 限售 / 资金股数",
            "两份议案抢同一笔钱 = 拦",
        ],
        "evidence_grades": [
            {"grade": "A", "source": "公告 / 年报 / 审计报告 / 问询回复 / 交易所披露", "rule": "重大结论至少 1 条 A 级"},
            {"grade": "B", "source": "交易所、监管、行业协会、统计局、央行、海关", "rule": "或 2 条独立 B 级"},
            {"grade": "C", "source": "第三方研究、券商研报、权威财经媒体", "rule": "辅助，不单独支撑重大结论"},
            {"grade": "D", "source": "一般媒体、网络信息、推断、无来源", "rule": "不得支撑买入"},
        ],
        "rules": [
            "提案人不能批自己的案子；同一角色多人时各看各的、按人留痕。",
            "风控否决 = 终局，Chairman 不能越过。",
            "下游只读引用，不复制、不改写；上游变更 → 下游版本作废重跑。",
        ],
    }


# ---------------------------------------------------------------- 研究


# ---------------------------------------------------------------- 辩论


def _evidence_payload(
    conn,
    evidence_ids: list[int],
    *,
    org_id: int | None = None,
    case_id: int | None = None,
) -> list[dict[str, Any]]:
    if not evidence_ids:
        return []
    sql = (
        "SELECT id, title, quote, source, as_of, grade, event_time, available_time, "
        "document_id, page_ref, source_uri, cutoff FROM inst_evidence WHERE id = ANY(%s)"
    )
    params: list[Any] = [evidence_ids]
    if org_id is not None:
        sql += " AND org_id=%s"
        params.append(org_id)
    if case_id is not None:
        sql += " AND case_id=%s"
        params.append(case_id)
    sql += " ORDER BY id"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) or {} for r in rows]


def _debate_fallback(company: dict[str, Any], evidence: list[dict[str, Any]], valuation: dict[str, Any] | None) -> dict[str, Any]:
    ev_ids = [e["id"] for e in evidence]
    bull = [
        {
            "side": "bull",
            "round": 1,
            "claim": "长期竞争力与现金流质量支持持续跟踪。",
            "evidence_ids": ev_ids[:4],
            "confidence": 0.62,
            "falsifier": "若收入增速连续两个季度低于行业且现金流恶化，看多假设失效。",
        },
        {
            "side": "bull",
            "round": 2,
            "claim": "估值处于历史偏低分位，存在观察窗口。",
            "evidence_ids": ev_ids[:3],
            "confidence": 0.55,
            "falsifier": "若估值分位上升主要由盈利下修而非价格上涨造成，估值判断失效。",
        },
    ]
    bear = [
        {
            "side": "bear",
            "round": 1,
            "claim": "证据链未闭环：财务与公告尚未交叉核验。",
            "evidence_ids": ev_ids[:4],
            "confidence": 0.58,
            "falsifier": "若完整财报、公告与行业数据补齐且相互印证，该反方论点减弱。",
        },
        {
            "side": "bear",
            "round": 2,
            "claim": "低估值可能来自盈利周期或治理折价，不必然是安全边际。",
            "evidence_ids": ev_ids[:3],
            "confidence": 0.6,
            "falsifier": "若盈利质量、资本配置与治理记录均通过核验，价值陷阱假设减弱。",
        },
    ]
    chair = {
        "side": "chair",
        "round": 2,
        "claim": "证据链尚需补强，结论为「补充研究」。",
        "evidence_ids": ev_ids[:2],
        "confidence": 0.7,
        "falsifier": "若补齐证据后双方仍无法收敛，提交人工裁决。",
    }
    return {"bull": bull, "bear": bear, "chair": [chair]}


def start_debate(
    org_id: int,
    case_id: int,
    *,
    actor_member_id: int | None,
    use_ai: bool = True,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        case = conn.execute(
            """
            SELECT c.*, co.symbol, co.name, co.market, co.industry, co.ref_price
              FROM inst_research_case c JOIN inst_company co ON co.id=c.company_id
             WHERE c.id=%s AND c.org_id=%s
            """,
            (case_id, org_id),
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        version = conn.execute(
            "SELECT * FROM inst_research_version "
            "WHERE case_id=%s AND status='approved' AND superseded_at IS NULL "
            "ORDER BY version_no DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if not version:
            raise PermissionError("研究未审核通过或已重开，不能进入辩论")
        version = _ensure_version_hash(conn, version)
        ev_ids = list(version.get("evidence_ids") or [])
        evidence = _evidence_payload(
            conn, [int(x) for x in ev_ids], org_id=org_id, case_id=case_id
        )
        factpack = {
            "company": _row_dict(case),
            "research_version": _row_dict(version),
            "evidence": evidence,
        }
        session = conn.execute(
            """
            INSERT INTO inst_debate_session
              (case_id, research_version_id, status, agenda_step, factpack, factpack_hash, started_at)
            VALUES (%s,%s,'running',0,%s,%s,NOW()) RETURNING *
            """,
            (case_id, version["id"], _j(factpack), _hash(factpack)),
        ).fetchone()
        args = _debate_fallback(dict(case), evidence, version.get("valuation"))
        ai_args = None
        if use_ai:
            ai_args = _ai_debate(dict(case), evidence, version.get("valuation"), ev_ids)
            if ai_args:
                args = ai_args
        engine = "ai" if ai_args else "rule"
        conn.execute(
            "UPDATE inst_debate_session SET factpack = factpack || %s::jsonb WHERE id=%s",
            (_j({"engine": engine}), int(session["id"])),
        )
        evidence_by_id = {int(e["id"]): e for e in evidence}
        for side in ("bull", "bear", "chair"):
            for index, item in enumerate(args.get(side, []), start=1):
                round_no = int(item.get("round") or 1)
                evidence_ids = [int(x) for x in (item.get("evidence_ids") or []) if str(x).isdigit()]
                claim_id = str(item.get("claim_id") or f"{side}-{round_no}-{index}")
                valid = bool(evidence_ids) if side in {"bull", "bear"} else True
                conn.execute(
                    """
                    INSERT INTO inst_debate_argument
                      (session_id, side, round, claim_id, claim_type, claim, evidence_ids,
                       confidence, falsifier, valid)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        int(session["id"]),
                        side,
                        round_no,
                        claim_id,
                        str(item.get("claim_type") or "inference"),
                        str(item.get("claim") or ""),
                        _j(evidence_ids),
                        float(item.get("confidence") or 0),
                        item.get("falsifier"),
                        valid,
                    ),
                )
                for evidence_id in evidence_ids:
                    ev = evidence_by_id.get(evidence_id)
                    grade = str((ev or {}).get("grade") or "D")
                    status = (
                        "verified"
                        if grade == "A"
                        else "partially_verified"
                        if grade in {"B", "C"}
                        else "unverified"
                    )
                    issues = []
                    if ev is None:
                        issues.append("证据 ID 不在本版本证据包")
                    elif grade == "D":
                        issues.append("D 级证据不得单独支撑结论")
                    elif grade in {"B", "C"}:
                        issues.append("需回原始公告或文件核对")
                    conn.execute(
                        """
                        INSERT INTO inst_evidence_check
                          (session_id, claim_id, evidence_id, status, grade, issues)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (session_id, claim_id, evidence_id) DO NOTHING
                        """,
                        (int(session["id"]), claim_id, evidence_id, status, grade, _j(issues)),
                    )
        conclusion = str(args.get("conclusion") or ("补充研究" if not evidence else "推进审议"))
        conn.execute(
            "UPDATE inst_debate_session SET status='completed', agenda_step=9, conclusion=%s, ended_at=NOW() WHERE id=%s",
            (conclusion, session["id"]),
        )
        conn.execute(
            "UPDATE inst_research_case SET stage='proposal', updated_at=NOW() WHERE id=%s", (case_id,)
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="debate.complete",
            object_type="inst_debate_session",
            object_id=int(session["id"]),
            after={"conclusion": conclusion, "use_ai": use_ai},
        )
    return get_debate(org_id, int(session["id"]))  # type: ignore[return-value]


def _ai_debate(company, evidence, valuation, ev_ids) -> dict[str, Any] | None:
    try:
        from ai.router import available_task, run_task

        if not available_task("inst.debate"):
            return None
        prompt = {
            "company": {"symbol": company.get("symbol"), "name": company.get("name"), "market": company.get("market")},
            "evidence": [{"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source")} for e in evidence],
            "valuation": valuation,
        }
        system, _ = get_effective_prompt("inst.debate", DEBATE_PROMPT)
        out = run_task(
            "inst.debate",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            variables={"evidence_ids": [int(x) for x in ev_ids]},
        )
        data = json.loads(str(out.get("content") or "{}"))
        if not isinstance(data, dict):
            return None
        valid_ids = {int(x) for x in ev_ids}
        if not isinstance(data.get("chair"), list) and data.get("conclusion"):
            data["chair"] = [{
                "claim": str(data.get("conclusion") or ""),
                "evidence_ids": [],
                "confidence": 0.6,
                "round": 2,
                "falsifier": "证据核验未通过或未决项未处理",
            }]
        for side in ("bull", "bear", "chair"):
            items = data.get(side)
            if not isinstance(items, list):
                return None
            for item in items:
                ids = [int(x) for x in item.get("evidence_ids") or [] if str(x).isdigit()]
                item["evidence_ids"] = [x for x in ids if x in valid_ids]
                if not item.get("claim"):
                    return None
        # 需求要求至少两轮；模型常全部标 1，这里按顺序补齐第二轮。
        for side in ("bull", "bear"):
            items = data.get(side) or []
            if len(items) >= 2 and all(int(x.get("round") or 1) == 1 for x in items):
                for idx, item in enumerate(items):
                    item["round"] = 2 if idx >= len(items) // 2 else 1
        return data
    except Exception:
        return None


def get_debate(org_id: int, session_id: int) -> dict[str, Any] | None:
    return repo.debate(OrgScope(org_id), session_id)


# ---------------------------------------------------------------- 议案 / 审批 / 授权


def _current_version(conn, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_proposal_version WHERE proposal_id=%s ORDER BY version_no DESC LIMIT 1",
        (proposal_id,),
    ).fetchone()
    return _row_dict(row)


def _proposal_row(conn, org_id: int, proposal_id: int) -> dict[str, Any] | None:
    return repo.proposal_row(OrgScope(org_id), proposal_id, conn=conn)


# ---------------------------------------------------------------- 退出案状态机


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
            raise PermissionError("独立风控已否决，不能生成授权")
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


def list_authorizations(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    return repo.authorizations(OrgScope(org_id), status=status)


# ---------------------------------------------------------------- 模拟执行 / 组合


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
            _require_role(member, "execution")
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


# ---------------------------------------------------------------- 执行前校验 / 对账 / 异常


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


def precheck_execution(org_id: int, authorization_id: int) -> dict[str, Any]:
    """执行前校验：授权、有效期、价格区间、现金/持仓、停牌与 ST。"""
    from services.institution.execution_guard import evaluate

    with get_conn() as conn:
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
        _require_role(member, "manager", "partner", "execution")
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


def portfolio(org_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        pf, positions = repo.portfolio(OrgScope(org_id), conn=conn)
        if not pf:
            return {"portfolio": None, "positions": [], "cash": 0, "nav": 0}
        # 按最新未复权收盘价做一次盯市；没有行情则保留成交时市值。
        for p in positions:
            bar = md.latest_bar(str(p.get("symbol") or ""), adjust="none")
            if bar and bar.get("close") is not None and p.get("qty") is not None:
                p["last_close"] = bar["close"]
                p["market_value"] = float(p["qty"]) * float(bar["close"])
            p["idea"] = _idea_questions(p, "holdings")
    invested = sum(float(p.get("market_value") or 0) for p in positions)
    cash = float(pf["cash"] or 0)
    nav = cash + invested
    for p in positions:
        p["weight"] = (float(p.get("market_value") or 0) / nav) if nav else 0
    industry: dict[str, float] = {}
    for p in positions:
        key = p.get("industry") or "未分类"
        industry[key] = industry.get(key, 0.0) + float(p.get("market_value") or 0)
    out = _row_dict(pf) or {}
    out["nav"] = nav
    out["cash"] = cash
    out["invested"] = invested
    return {
        "portfolio": out,
        "positions": positions,
        "cash": cash,
        "nav": nav,
        "invested": invested,
        "invested_ratio": invested / nav if nav else 0,
        "industry_exposure": {k: v / nav for k, v in industry.items()} if nav else {},
    }


def monitor(org_id: int) -> dict[str, Any]:
    return {"portfolio": portfolio(org_id), **repo.monitor(OrgScope(org_id))}


def scan_holdings(org_id: int, *, actor_member_id: int | None = None) -> dict[str, Any]:
    """自动监控：复核到期与持仓价格异常，登记监控事件；7 天内同类不重复。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "risk", "monitoring", "partner")
        rows = conn.execute(
            """
            SELECT * FROM (
              SELECT DISTINCT ON (ps.symbol)
                     ps.symbol, ps.qty, ps.cost, co.id AS company_id, co.name AS company_name
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
        created: list[dict[str, Any]] = []
        for pos in rows:
            company_id = pos["company_id"]
            if not company_id:
                continue
            ledger = conn.execute(
                "SELECT * FROM inst_thesis_ledger WHERE org_id=%s AND company_id=%s "
                "ORDER BY updated_at DESC LIMIT 1",
                (org_id, int(company_id)),
            ).fetchone()
            due = ledger.get("review_due") if ledger else None
            if due and due < date.today():
                exists = conn.execute(
                    "SELECT 1 FROM inst_monitor_event WHERE org_id=%s AND company_id=%s "
                    "AND type='thesis' AND created_at > NOW() - INTERVAL '7 days' LIMIT 1",
                    (org_id, int(company_id)),
                ).fetchone()
                if not exists:
                    event = conn.execute(
                        "INSERT INTO inst_monitor_event (org_id, company_id, type, severity, detail) "
                        "VALUES (%s,%s,'thesis','warning',%s) RETURNING *",
                        (
                            org_id,
                            int(company_id),
                            _j({"text": f"买入论点复核到期（约定 {due.isoformat()}）"}),
                        ),
                    ).fetchone()
                    created.append(_row_dict(event) or {})
            bar = (
                conn.execute(
                    "SELECT close FROM md_daily_bar WHERE symbol=%s AND adjust='none' "
                    "ORDER BY trade_date DESC LIMIT 1",
                    (str(pos["symbol"]),),
                ).fetchone()
                if pos["symbol"]
                else None
            )
            cost = float(pos.get("cost") or 0)
            close = float(bar["close"]) if bar and bar.get("close") is not None else 0.0
            if cost > 0 and close > 0 and close < cost * 0.9:
                exists = conn.execute(
                    "SELECT 1 FROM inst_monitor_event WHERE org_id=%s AND company_id=%s "
                    "AND type='price' AND created_at > NOW() - INTERVAL '7 days' LIMIT 1",
                    (org_id, int(company_id)),
                ).fetchone()
                if not exists:
                    event = conn.execute(
                        "INSERT INTO inst_monitor_event (org_id, company_id, type, severity, detail) "
                        "VALUES (%s,%s,'price','warning',%s) RETURNING *",
                        (
                            org_id,
                            int(company_id),
                            _j(
                                {
                                    "text": (
                                        f"现价 {close:g} 较成本 {cost:g} 下跌 "
                                        f"{(1 - close / cost) * 100:.1f}%，需复核论点是否仍成立"
                                    )
                                }
                            ),
                        ),
                    ).fetchone()
                    created.append(_row_dict(event) or {})
        if created:
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="monitor.scan",
                object_type="inst_monitor_event",
                object_id=None,
                after={"created": len(created)},
            )
    return {"created": len(created), "events": created}


def refresh_thesis(org_id: int, company_id: int, *, actor_member_id: int | None = None) -> dict[str, Any]:
    """从最近一笔买入议案/研究版本重新生成论点台账；旧台账保留，不自动覆盖。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner", "monitoring")
        company = conn.execute(
            "SELECT id, symbol, name FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        proposal = conn.execute(
            """
            SELECT p.*, v.snapshot
              FROM inst_proposal p
              JOIN LATERAL (
                SELECT snapshot FROM inst_proposal_version
                 WHERE proposal_id=p.id ORDER BY version_no DESC LIMIT 1
              ) v ON TRUE
             WHERE p.org_id=%s AND p.company_id=%s
             ORDER BY p.updated_at DESC LIMIT 1
            """,
            (org_id, company_id),
        ).fetchone()
        if not proposal:
            raise PermissionError("该公司还没有可生成台账的买入议案")
        snapshot = dict(proposal.get("snapshot") or {})
        research = {}
        if snapshot.get("research_version_id"):
            row = conn.execute(
                "SELECT * FROM inst_research_version WHERE id=%s",
                (snapshot["research_version_id"],),
            ).fetchone()
            research = dict(row) if row else {}
        opinion = str(snapshot.get("investment_opinion") or "").strip()
        conclusion = str(research.get("conclusion") or "").strip()
        status_words = {"好", "ok", "OK", "有条件通过", "待补充", "推进审议"}
        if opinion and opinion not in status_words and len(opinion) >= 6:
            thesis = opinion
        elif conclusion and conclusion not in status_words:
            thesis = conclusion
        else:
            first_dim = next(
                (str(d.get("summary") or "").strip() for d in research.get("six_dim") or [] if isinstance(d, dict) and str(d.get("summary") or "").strip()),
                "",
            )
            thesis = first_dim or f"{company['name']} 买入论点待补充"
        # 台账卡只显示一句买入假设：取第一句，最长 60 字；审批状态/短评不上台账。
        thesis = _clip_brief(re.split(r"[；;。]", thesis)[0] or thesis)[:60]
        assumptions: list[str] = []
        for dim in research.get("six_dim") or []:
            if isinstance(dim, dict):
                text = str(dim.get("summary") or dim.get("conclusion") or "").strip()
            else:
                text = str(dim).strip()
            if text:
                assumptions.append(text[:200])
        monitoring = [str(x).strip() for x in (snapshot.get("monitoring") or []) if str(x).strip()]
        kpis = []
        for line in monitoring[:4]:
            name = re.split(r"[<>=≤≥（(→]", line)[0].strip()[:12] or "KPI"
            kpis.append({"name": name, "target": line[:60]})
        falsifiers = monitoring[:2]
        row = conn.execute(
            """
            INSERT INTO inst_thesis_ledger
              (org_id, company_id, proposal_id, symbol, thesis, key_assumptions, kpis, falsifiers,
               review_due, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                org_id,
                company_id,
                int(proposal["id"]),
                company["symbol"],
                thesis[:2000],
                _j(assumptions[:2]),
                _j(kpis),
                _j(falsifiers),
                date.today() + timedelta(days=30),
                actor_member_id,
            ),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.thesis.refresh",
            object_type="inst_thesis_ledger",
            object_id=int(row["id"]),
            after={"company_id": company_id, "proposal_id": int(proposal["id"])},
        )
        out = _row_dict(row) or {}
        out["company_name"] = company["name"]
        out["review_count"] = 0
    return out


def _validated_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是数组")
    return value


def create_thesis(
    org_id: int,
    *,
    company_id: int,
    thesis: str,
    proposal_id: int | None = None,
    key_assumptions: Any = None,
    kpis: Any = None,
    falsifiers: Any = None,
    review_due: str | None = None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """建立买入论点台账：论点、关键假设、KPI、复核时间、推翻条件。"""
    text = str(thesis or "").strip()
    if not text:
        raise ValueError("买入论点不能为空")
    assumptions = _validated_list(key_assumptions, "关键假设")
    kpi_list = _validated_list(kpis, "KPI")
    falsifier_list = _validated_list(falsifiers, "推翻条件")
    for idx, item in enumerate(kpi_list, start=1):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise ValueError(f"第 {idx} 个 KPI 缺少 name")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner", "monitoring")
        company = conn.execute(
            "SELECT id, symbol, name FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        row = conn.execute(
            """
            INSERT INTO inst_thesis_ledger
              (org_id, company_id, proposal_id, symbol, thesis, key_assumptions, kpis, falsifiers,
               review_due, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                org_id,
                company_id,
                proposal_id,
                company["symbol"],
                text,
                _j(assumptions),
                _j(kpi_list),
                _j(falsifier_list),
                review_due or None,
                actor_member_id,
            ),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.thesis.create",
            object_type="inst_thesis_ledger",
            object_id=int(row["id"]),
            after={"company_id": company_id, "proposal_id": proposal_id, "review_due": review_due},
        )
    return _row_dict(row) or {}


def _thesis_row(conn, org_id: int, ledger_id: int) -> dict[str, Any] | None:
    return repo.thesis_row(conn, OrgScope(org_id), ledger_id)


def list_theses(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    return repo.theses(OrgScope(org_id), status=status)


def review_thesis(
    org_id: int,
    ledger_id: int,
    *,
    kpi_status: str,
    conclusion: str,
    note: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if kpi_status not in {"on_track", "at_risk", "broken"}:
        raise ValueError("kpi_status 必须是 on_track/at_risk/broken")
    if conclusion not in {"hold", "reduce", "exit", "invalidate"}:
        raise ValueError("conclusion 必须是 hold/reduce/exit/invalidate")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner", "monitoring")
        ledger, new_status, out = repo.review_thesis(
            conn, OrgScope(org_id), ledger_id,
            kpi_status=kpi_status, conclusion=conclusion, note=note,
            actor_member_id=actor_member_id,
        )
        if not ledger:
            raise LookupError("论点台账不存在")
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.thesis.review",
            object_type="inst_thesis_ledger",
            object_id=ledger_id,
            before={"status": ledger["status"]},
            after={"status": new_status, "kpi_status": kpi_status, "conclusion": conclusion},
        )
    return out or {}


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
        _require_role(member, "manager", "partner", "monitoring")
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


def create_monitor_event(
    org_id: int,
    company_id: int,
    *,
    event_type: str,
    severity: str,
    detail: str,
    actor_member_id: int | None,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "risk", "monitoring", "partner")
        company = conn.execute(
            "SELECT id FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        row = repo.create_monitor_event(
            conn, OrgScope(org_id), company_id, event_type, severity, detail
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.event.create",
            object_type="inst_monitor_event",
            object_id=int(row["id"]),
            after={"company_id": company_id, "type": event_type, "severity": severity},
        )
    return _row_dict(row) or {}


# ---------------------------------------------------------------- AI 只读辅助


def _ai_task(task_id: str, payload: dict[str, Any], system: str) -> dict[str, Any]:
    try:
        from ai.router import available_task, run_task
    except Exception as exc:  # pragma: no cover - 依赖缺失
        raise AiUnavailable(f"AI 路由层不可用：{exc}") from exc
    if not available_task(task_id):
        raise AiUnavailable("AI 未配置（缺少 LLM 网关或 Key）")
    system, _ = get_effective_prompt(task_id, system)
    out = run_task(
        task_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    data = out.get("data")
    if isinstance(data, dict):
        return data
    return {"summary": str(out.get("content") or "")}


def _memo_metrics(case: dict[str, Any]) -> list[dict[str, Any]]:
    """一页纸顶部指标：只展示已有数据，缺失不编造。"""
    symbol = str(case.get("symbol") or "")
    fin = md.financials(symbol, limit=2) or []
    latest = fin[0] if fin else {}
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    out: list[dict[str, Any]] = []
    if latest.get("revenue") is not None:
        out.append(
            {
                "label": "营业收入",
                "value": _yi(latest.get("revenue")),
                "note": f"同比 {_pc(latest.get('revenue_yoy'))}"
                if latest.get("revenue_yoy") is not None
                else "最近报告期",
            }
        )
    if latest.get("net_profit") is not None:
        out.append(
            {
                "label": "净利润",
                "value": _yi(latest.get("net_profit")),
                "note": f"同比 {_pc(latest.get('profit_yoy'))}"
                if latest.get("profit_yoy") is not None
                else "最近报告期",
            }
        )
    if latest.get("roe") is not None:
        out.append({"label": "ROE", "value": _pc(latest.get("roe")), "note": "最近报告期"})
    if val.get("pe_ttm") is not None:
        out.append(
            {
                "label": "PE TTM",
                "value": f"{float(val['pe_ttm']):.2f}",
                "note": f"历史分位 {_pc(pct.get('pe_percentile'))}",
            }
        )
    elif val.get("pb_mrq") is not None:
        out.append(
            {
                "label": "PB MRQ",
                "value": f"{float(val['pb_mrq']):.2f}",
                "note": f"历史分位 {_pc(pct.get('pb_percentile'))}",
            }
        )
    return out


def _rule_memo(version: dict[str, Any]) -> dict[str, Any]:
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    risks = [str(c) for d in dims for c in (d.get("counter") or [])][:5]
    questions = [
        str(q) for d in dims for q in (d.get("open_questions") or d.get("data_gaps") or [])
    ][:8]
    valuation = version.get("valuation") or {}
    price_range = None
    if any(valuation.get(k) is not None for k in ("low", "base", "high")):
        price_range = {
            "low": valuation.get("low"),
            "base": valuation.get("base"),
            "high": valuation.get("high"),
            "note": "研究区间，不是目标价",
        }
    conclusion = _clean_agent_text(version.get("conclusion"))
    if not conclusion or "待补充" in conclusion:
        overall = _overall_score(dims)
        lead = next(
            (str(d.get("judgment") or "") for d in dims if d.get("judgment")),
            "六维分析已完成",
        )
        conclusion = f"六维平均得分 {overall}/10；{lead}" if overall is not None else lead
    summary = _clip_brief(conclusion)
    return {
        "summary": summary,
        "conclusion": summary,
        "decision": "watch",
        "six_dim_scores": [],
        "conflicts": [],
        "key_variables": questions[:3],
        "evidence": [],
        "risks": [_clip_brief(x) for x in risks],
        "open_questions": [_clip_brief(x) for x in questions],
        "price_range": price_range,
        "holding_period": "1-3 年（论点成立前提下，按季复核）",
        "engine": "rule",
    }


def _apply_memo_data_gate(data: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    gates: dict[str, str] = {}
    for dim in version.get("six_dim") or []:
        if isinstance(dim, dict) and dim.get("key") and dim.get("gate"):
            gates[str(dim["key"])] = str(dim["gate"])
    industry = version.get("industry_analysis") or {}
    if isinstance(industry, dict) and industry.get("gate"):
        gates["industry"] = str(industry["gate"])
    if not gates:
        return data
    data["data_gates"] = gates
    failed = [key for key, gate in gates.items() if gate == "fail"]
    decision = str(data.get("decision") or "")
    if decision == "proceed" and any(gate != "pass" for gate in gates.values()):
        data["decision"] = "watch"
        data["data_gate_note"] = (
            "六维存在数据缺口，研究建议降级为观察，不能进入买入。"
            + (f"其中 {'、'.join(failed)} 为 fail。" if failed else "")
        )
    elif failed and not data.get("data_gate_note"):
        data["data_gate_note"] = (
            f"以下维度数据缺失，按不可买入处理：{'、'.join(failed)}。"
        )
    return data


def _sync_research_conclusion(org_id: int, version_id: int, memo: dict[str, Any]) -> None:
    """一页纸落库后，把同一段结论写回研究版本 conclusion，供 04 三关读取。"""
    conclusion = str(memo.get("conclusion") or memo.get("summary") or "").strip()
    if not conclusion:
        return
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, locked_at FROM inst_research_version WHERE id=%s AND case_id IN "
            "(SELECT id FROM inst_research_case WHERE org_id=%s)",
            (version_id, org_id),
        ).fetchone()
        if not row or row.get("locked_at") or str(row.get("status")) != "pending_review":
            return
        conn.execute(
            "UPDATE inst_research_version SET conclusion=%s, content_hash=NULL WHERE id=%s AND conclusion IS DISTINCT FROM %s",
            (conclusion[:2000], version_id, conclusion[:2000]),
        )


def ai_research_memo(
    org_id: int,
    case_id: int,
    *,
    refresh: bool = False,
    generate: bool = True,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    version = (case.get("versions") or [{}])[0]
    overall = _overall_score(version.get("six_dim") or [])
    if not version.get("id"):
        if not generate:
            return {
                "memo": None,
                "task": "inst.research_memo",
                "cached": True,
                "missing": True,
            }
        raise LookupError("还没有研究版本")
    payload = {
        "company": {k: case.get(k) for k in ("symbol", "company_name", "market", "industry", "ref_price")},
        "version": {k: version.get(k) for k in ("version_no", "status", "conclusion", "valuation", "six_dim")},
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source"), "as_of": e.get("as_of")}
            for e in (case.get("evidence") or [])
        ],
    }
    prompt, prompt_version = get_effective_prompt("inst.research_memo", RESEARCH_MEMO_PROMPT)
    scope_key = f"case:{case_id}:version:{version.get('id')}"
    cache_key = agent_input_hash(
        {"case_id": case_id, "version_id": version.get("id"), "content_hash": version.get("content_hash"), "payload": payload},
        prompt,
    )
    if not refresh:
        hit = get_cached_output(
            "inst.research_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            # 提示词/输入变化后仍优先展示已生成的结论，避免每次进入都重新生成。
            hit = get_latest_output("inst.research_memo", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            memo = _apply_memo_data_gate(dict(hit["output"]), version)
            if not (isinstance(memo.get("metrics"), list) and len(memo.get("metrics") or []) >= 2):
                memo["metrics"] = _memo_metrics(case)
            memo["overall_score"] = overall
            _sync_research_conclusion(org_id, int(version["id"]), memo)
            return {
                "memo": memo,
                "task": "inst.research_memo",
                "version_no": version.get("version_no"),
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if not generate:
        return {
            "memo": None,
            "task": "inst.research_memo",
            "version_no": version.get("version_no"),
            "cached": False,
            "missing": True,
        }
    try:
        data = _ai_task("inst.research_memo", payload, prompt)
        data.setdefault("engine", "agent")
    except AiUnavailable:
        # AI 未配置时仍给出一页纸骨架，内容全部来自六维规则结果。
        data = _rule_memo(version)
    data = _apply_memo_data_gate(data, version)
    metrics = data.get("metrics")
    if not (isinstance(metrics, list) and len(metrics) >= 2):
        data["metrics"] = _memo_metrics(case)
    data["overall_score"] = overall
    _sync_research_conclusion(org_id, int(version["id"]), data)
    # 规则兜底也落盘：避免 AI 暂不可用时每次进入页面都重新生成。
    save_output(
        "inst.research_memo",
        org_id=org_id,
        scope_key=scope_key,
        input_hash=cache_key,
        prompt_version=prompt_version,
        output=data,
        engine=str(data.get("engine") or "agent"),
        created_by=actor_member_id,
    )
    return {
        "memo": data,
        "task": "inst.research_memo",
        "version_no": version.get("version_no"),
        "cached": False,
    }


def ai_dimension_chat_history(
    org_id: int,
    case_id: int,
    key: str,
    *,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    user_id = inst_ai_store.member_user_id(org_id, actor_member_id)
    items = (
        inst_ai_store.list_messages(org_id, case_id, key, user_id, limit=50)
        if user_id
        else []
    )
    return {"items": items}


def ai_dimension_chat(
    org_id: int,
    case_id: int,
    key: str,
    *,
    question: str,
    history: list[dict[str, Any]] | None = None,
    actor_member_id: int | None = None,
    client_message_id: str | None = None,
) -> dict[str, Any]:
    """单维追问：只带该维结论、证据与最近对话，不改业务状态。"""
    q = str(question or "").strip()
    if not q:
        raise ValueError("问题不能为空")
    dim_keys = {d[0] for d in SIX_DIM_DEFS}
    if key not in dim_keys:
        raise ValueError("未知研究维度")
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    version = (case.get("versions") or [{}])[0]
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    dim = next((d for d in dims if d.get("key") == key), None)
    if not dim:
        raise LookupError("该维度尚未生成")
    ev_ids = {int(x) for x in (dim.get("evidence_ids") or []) if str(x).isdigit()}
    evidence = [e for e in (case.get("evidence") or []) if int(e.get("id") or 0) in ev_ids]
    user_id = inst_ai_store.member_user_id(org_id, actor_member_id)
    stored = (
        inst_ai_store.list_messages(org_id, case_id, key, user_id, limit=50)
        if user_id
        else []
    )
    history_source = stored[-8:] if stored else (history or [])[-8:]
    history_in: list[dict[str, str]] = []
    for item in history_source:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            history_in.append({"role": role, "content": content[:2000]})
    payload = {
        "company": {k: case.get(k) for k in ("symbol", "company_name", "market", "industry", "ref_price")},
        "dimension": {
            k: dim.get(k)
            for k in (
                "key",
                "title",
                "question",
                "summary",
                "checks",
                "counter",
                "open_questions",
                "data_gaps",
                "confidence",
                "engine",
            )
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source")}
            for e in evidence
        ],
        "history": history_in,
        "question": q[:2000],
    }
    data = _ai_task("inst.dim.chat", payload, CHAT_PROMPT)
    answer = str(data.get("answer") or data.get("summary") or "").strip()
    if not answer:
        raise AiUnavailable("AI 未返回内容")
    if user_id:
        inst_ai_store.append_message(
            org_id, case_id, key, user_id,
            member_id=actor_member_id, role="user", content=q,
            client_message_id=client_message_id,
        )
        inst_ai_store.append_message(
            org_id, case_id, key, user_id,
            member_id=actor_member_id, role="assistant", content=answer,
            client_message_id=f"{client_message_id}:a" if client_message_id else None,
        )
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.dimension.chat",
            object_type="inst_research_version",
            object_id=int(version.get("id") or 0),
            after={"case_id": case_id, "key": key, "question": q[:200], "answer": answer[:300]},
        )
    return {
        "answer": answer,
        "dimension": key,
        "task": "inst.dim.chat",
        "engine": str(data.get("engine") or "agent"),
    }


def ai_partner_memo(
    org_id: int,
    proposal_id: int,
    *,
    refresh: bool = False,
    actor_member_id: int | None = None,
    cached_only: bool = False,
) -> dict[str, Any]:
    """合伙人审批建议：只给合伙人本人看，独立于其他合伙人意见。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "partner")
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    research = None
    if proposal.get("case_id"):
        with get_conn() as conn:
            research = _research_debate_summary(conn, org_id, int(proposal["case_id"]))
    pf = portfolio(org_id)
    payload = {
        "proposal": {
            k: proposal.get(k)
            for k in (
                "id", "status", "direction", "target_weight", "symbol", "company_name",
                "market", "industry",
            )
        },
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "research_debate": research,
        "portfolio": {
            "nav": pf.get("nav"),
            "cash": pf.get("cash"),
            "invested_ratio": pf.get("invested_ratio"),
            "positions": [
                {
                    k: pos.get(k)
                    for k in ("symbol", "name", "industry", "qty", "cost", "weight")
                }
                for pos in (pf.get("positions") or [])
            ],
        },
    }
    prompt, prompt_version = get_effective_prompt("inst.partner_memo", PARTNER_MEMO_PROMPT)
    scope_key = f"proposal:{proposal_id}:version:{version.get('id')}:task:partner"
    cache_key = agent_input_hash(payload, prompt)
    if not refresh:
        hit = get_cached_output(
            "inst.partner_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            hit = get_latest_output("inst.partner_memo", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            return {
                "memo": hit["output"],
                "task": "inst.partner_memo",
                "version_no": version.get("version_no"),
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if cached_only:
        return {
            "memo": None,
            "task": "inst.partner_memo",
            "version_no": version.get("version_no"),
            "cached": True,
            "missing": True,
        }
    data = _ai_task("inst.partner_memo", payload, prompt)
    data.setdefault("engine", "agent")
    save_output(
        "inst.partner_memo",
        org_id=org_id,
        scope_key=scope_key,
        input_hash=cache_key,
        prompt_version=prompt_version,
        output=data,
        engine=str(data.get("engine") or "agent"),
        created_by=actor_member_id,
    )
    return {
        "memo": data,
        "task": "inst.partner_memo",
        "version_no": version.get("version_no"),
        "cached": False,
    }


def ai_risk_review(
    org_id: int,
    proposal_id: int,
    *,
    refresh: bool = False,
    actor_member_id: int | None = None,
    cached_only: bool = False,
) -> dict[str, Any]:
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    payload = {
        "proposal": {k: proposal.get(k) for k in ("id", "status", "direction", "target_weight", "symbol", "company_name")},
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "checks": None,
        "policy": {"max_single_weight": MAX_SINGLE_WEIGHT, "min_cash_ratio": MIN_CASH_RATIO, "policy_version": POLICY_VERSION},
    }
    # 用真实检查项；避免在 AI 侧重算。
    with get_conn() as conn:
        proposal_row = _proposal_row(conn, org_id, proposal_id)
        current = _current_version(conn, proposal_id)
        checks = _risk_checks(conn, org_id, proposal_row or proposal, current or version)
    payload["checks"] = checks
    prompt, prompt_version = get_effective_prompt("inst.risk_review", RISK_REVIEW_PROMPT)
    scope_key = f"proposal:{proposal_id}:version:{(current or version).get('id')}:task:risk"
    cache_key = agent_input_hash(payload, prompt)
    if not refresh:
        hit = get_cached_output(
            "inst.risk_review",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            hit = get_latest_output("inst.risk_review", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            return {
                "memo": hit["output"],
                "task": "inst.risk_review",
                "checks": checks,
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if cached_only:
        return {
            "memo": None,
            "task": "inst.risk_review",
            "checks": checks,
            "cached": True,
            "missing": True,
        }
    data = _ai_task("inst.risk_review", payload, prompt)
    data.setdefault("engine", "agent")
    if data.get("engine") != "rule":
        save_output(
            "inst.risk_review",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
            output=data,
            engine=str(data.get("engine") or "agent"),
            created_by=actor_member_id,
        )
    return {"memo": data, "task": "inst.risk_review", "checks": checks, "cached": False}


def ai_chairman_memo(
    org_id: int,
    proposal_id: int,
    *,
    refresh: bool = False,
    actor_member_id: int | None = None,
    cached_only: bool = False,
) -> dict[str, Any]:
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    payload = {
        "proposal": {k: proposal.get(k) for k in ("id", "status", "direction", "target_weight", "symbol", "company_name")},
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "approvals": proposal.get("approvals") or [],
        "authorizations": proposal.get("authorizations") or [],
        "policy": {"max_single_weight": MAX_SINGLE_WEIGHT, "min_cash_ratio": MIN_CASH_RATIO, "policy_version": POLICY_VERSION},
    }
    prompt, prompt_version = get_effective_prompt("inst.chairman_memo", CHAIRMAN_MEMO_PROMPT)
    scope_key = f"proposal:{proposal_id}:version:{version.get('id')}:task:chairman"
    cache_key = agent_input_hash(payload, prompt)
    if not refresh:
        hit = get_cached_output(
            "inst.chairman_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            hit = get_latest_output("inst.chairman_memo", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            return {
                "memo": hit["output"],
                "task": "inst.chairman_memo",
                "version_no": version.get("version_no"),
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if cached_only:
        return {
            "memo": None,
            "task": "inst.chairman_memo",
            "version_no": version.get("version_no"),
            "cached": True,
            "missing": True,
        }
    data = _ai_task("inst.chairman_memo", payload, prompt)
    data.setdefault("engine", "agent")
    if data.get("engine") != "rule":
        save_output(
            "inst.chairman_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
            output=data,
            engine=str(data.get("engine") or "agent"),
            created_by=actor_member_id,
        )
    return {"memo": data, "task": "inst.chairman_memo", "version_no": version.get("version_no"), "cached": False}


# ---------------------------------------------------------------- AI Chairman 模式


def _ai_available(task_id: str = "inst.chairman_memo") -> bool:
    try:
        from ai.router import available_task

        return bool(available_task(task_id))
    except Exception:
        return False


def _chairman_context(
    org_id: int, proposal_id: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    with get_conn() as conn:
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        rows = _approval_rows(conn, int(current["id"]))
        state = _approval_state(rows, _member_role_counts(conn, org_id))

        def _summary(step: str, passed_decisions: set[str]) -> dict[str, Any]:
            item = state[step]
            decisions = [str(r.get("decision") or "") for r in item["items"]]
            if "conditional" in decisions:
                decision = "conditional"
            elif item["passed"]:
                decision = next((d for d in decisions if d in passed_decisions), "approve")
            elif item["vetoed"]:
                decision = "veto"
            else:
                decision = item["latest"].get("decision") if item["latest"] else None
            return {
                "step": step,
                "decision": decision,
                "passed": item["passed"],
                "vetoed": item["vetoed"],
                "conditions": item["conditions"],
            }

        approvals = {
            "partner": _summary("partner", {"approve", "conditional"}),
            "risk_precheck": _summary("risk_precheck", {"pass", "conditional"}),
            "chairman": _summary("chairman", {"approve", "conditional"}),
        }
        snapshot = current.get("snapshot") or {}
        risk_checks = _risk_checks(conn, org_id, proposal, current)
        evidence_count = 0
        research_version_id = snapshot.get("research_version_id")
        if research_version_id:
            row = conn.execute(
                "SELECT evidence_ids FROM inst_research_version WHERE id=%s",
                (research_version_id,),
            ).fetchone()
            if row:
                evidence_count = len(row.get("evidence_ids") or [])
    return proposal, current, snapshot, approvals, risk_checks, evidence_count


def ai_chairman_precheck(
    org_id: int, proposal_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """预检查：只读，不改状态。"""
    from services.institution.chairman_mode import evaluate

    proposal, current, snapshot, approvals, risk_checks, evidence_count = _chairman_context(
        org_id, proposal_id
    )
    result = evaluate(
        proposal_status=str(proposal.get("status") or ""),
        snapshot=snapshot,
        approvals=approvals,
        risk_checks=risk_checks,
        evidence_count=evidence_count,
        ai_available=_ai_available(),
        proposer_is_reviewer=int(proposal.get("created_by") or 0) == int(actor_member_id or 0),
    )
    result.update(
        {
            "proposal_id": proposal_id,
            "version_no": current.get("version_no"),
            "status": proposal.get("status"),
        }
    )
    return result


def ai_chairman_simulate(
    org_id: int, proposal_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """模拟批准：只记录建议与审计，不写审批、不改状态。"""
    pre = ai_chairman_precheck(org_id, proposal_id, actor_member_id=actor_member_id)
    memo = None
    if _ai_available():
        try:
            memo = ai_chairman_memo(org_id, proposal_id).get("memo")
        except AiUnavailable:
            memo = None
    recommendation = pre["recommendation"]
    decision = {
        "approve_candidate": "approve",
        "conditional_candidate": "conditional",
    }.get(recommendation, "handover")
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.chairman.ai_simulate",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={
                "simulated_decision": decision,
                "blocking": pre["blocking"],
                "warnings": pre["warnings"],
                "binding": False,
            },
        )
    return {
        **pre,
        "mode": "ai_simulated",
        "simulated_decision": decision,
        "memo": memo,
        "note": "AI 模拟结果不构成批准；需真人 Chairman 表决",
    }


def ai_chairman_handover(
    org_id: int,
    proposal_id: int,
    *,
    actor_member_id: int | None,
    note: str | None = None,
) -> dict[str, Any]:
    """人工移交：Chairman 放弃 AI 模拟，转真人流程；只写审计。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.chairman.ai_handover",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={"note": note or "已移交真人 Chairman", "status": proposal.get("status")},
        )
    return {
        "ok": True,
        "handover": True,
        "proposal_id": proposal_id,
        "status": proposal.get("status"),
        "note": note or "已移交真人 Chairman",
    }


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
        _require_role(member, "manager", "partner", "monitoring")
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


def list_audit(org_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return repo.audit(OrgScope(org_id), limit=limit)


__all__ = [
    "AiUnavailable",
    "DEMO_COMPANIES",
    "POLICY_VERSION",
    "ai_chairman_memo",
    "ai_research_memo",
    "ai_risk_review",
    "approve_and_execute",
    "authorize",
    "chairman_review",
    "create_case",
    "create_exit_case",
    "create_monitor_event",
    "create_proposal",
    "ensure_and_seed",
    "execute_authorization",
    "generate_research",
    "get_case",
    "get_company",
    "get_debate",
    "get_proposal",
    "ideas_push",
    "list_audit",
    "list_authorizations",
    "list_cases",
    "list_companies",
    "list_proposals",
    "monitor",
    "overview",
    "partner_review",
    "portfolio",
    "review_research",
    "risk_check",
    "start_debate",
    "update_company_pool",
]


# ---------------------------------------------------------------- AI 岗位（I01–I06）

AI_ROLE_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("research", "研究统筹 / 产业 / 护城河", "inst.research_memo"),
    ("financial", "财务与取证", "inst.role.financial"),
    ("governance", "治理 / 估值 / 反证", "inst.role.governance"),
    ("debate", "看多 / 看空 / 主持", "inst.debate"),
    ("risk", "风控 / 合规 / 交易", "inst.risk_review"),
    ("post_investment", "投后 / 退出 / 复盘", "inst.role.post_investment"),
)


def institution_agent_catalog(org_id: int, *, can_edit: bool) -> dict[str, Any]:
    """机构 Agent 管理目录：只返回主观机构端自己的 Agent；仅经理可看提示词正文。"""
    from services.ai_agents import catalog as agent_catalog

    items = [
        item
        for item in agent_catalog.list_agents(include_prompt=can_edit)
        if item.get("source") == "institution"
    ]
    return {
        "items": items,
        "count": len(items),
        "editable_count": sum(1 for item in items if item.get("editable")),
        "can_edit": can_edit,
    }


def save_institution_agent_prompt(
    org_id: int,
    task_id: str,
    prompt: str,
    *,
    note: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    from services.ai_agents import catalog as agent_catalog

    if not agent_catalog.is_editable_institution(task_id):
        raise ValueError("该 Agent 暂未接入提示词管理")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        result = agent_store.save_prompt(
            task_id, prompt, updated_by=actor_member_id, note=note
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="agent.prompt.save",
            object_type="ai_agent_prompt",
            object_id=0,
            after={"task_id": task_id, "version": result["version"], "prompt_hash": result["prompt_hash"]},
        )
    result["agent"] = agent_catalog.get_agent(task_id, include_prompt=True)
    return result


def reset_institution_agent_prompt(
    org_id: int,
    task_id: str,
    *,
    actor_member_id: int | None,
) -> dict[str, Any]:
    from services.ai_agents import catalog as agent_catalog

    if not agent_catalog.is_editable_institution(task_id):
        raise ValueError("该 Agent 暂未接入提示词管理")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        result = agent_store.reset_prompt(task_id, updated_by=actor_member_id)
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="agent.prompt.reset",
            object_type="ai_agent_prompt",
            object_id=0,
            after={"task_id": task_id, "version": result["version"]},
        )
    result["agent"] = agent_catalog.get_agent(task_id, include_prompt=True)
    return result


def institution_agent_prompt_history(
    org_id: int,
    task_id: str,
    *,
    actor_member_id: int | None,
) -> dict[str, Any]:
    from services.ai_agents import catalog as agent_catalog

    if not agent_catalog.is_editable_institution(task_id):
        raise ValueError("该 Agent 暂未接入提示词管理")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
    return {
        "items": agent_store.list_prompt_history(task_id),
        "agent": agent_catalog.get_agent(task_id, include_prompt=True),
    }


def ai_role_catalog() -> list[dict[str, Any]]:
    out = []
    for key, label, task in AI_ROLE_CATALOG:
        out.append(
            {
                "key": key,
                "label": label,
                "task": task,
                "available": _ai_available(task),
            }
        )
    return out


def _role_case_payload(org_id: int, case_id: int) -> dict[str, Any]:
    data = get_case(org_id, case_id)
    if not data:
        raise LookupError("研究案不存在")
    version = (data.get("versions") or [None])[0] or {}
    return {
        "company": {
            "symbol": data.get("symbol"),
            "name": data.get("company_name"),
            "market": data.get("market"),
            "industry": data.get("industry"),
            "data_status": data.get("data_status"),
        },
        "research": {
            "version_no": version.get("version_no"),
            "status": version.get("status"),
            "conclusion": version.get("conclusion"),
            "six_dim": [
                {
                    "key": d.get("key"),
                    "title": d.get("title"),
                    "summary": d.get("summary"),
                    "counter": d.get("counter"),
                }
                for d in (version.get("six_dim") or [])
            ],
            "valuation": version.get("valuation"),
            "counter_evidence": version.get("counter_evidence"),
            "open_questions": version.get("open_questions"),
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "source": e.get("source"), "quote": e.get("quote")}
            for e in (data.get("evidence") or [])[:30]
        ],
    }


def ai_role_run(
    org_id: int,
    role_key: str,
    *,
    case_id: int | None = None,
    proposal_id: int | None = None,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """执行一个 AI 岗位：只输出建议，不改业务状态。"""
    role = str(role_key or "").strip().lower()
    task = {key: task_id for key, _label, task_id in AI_ROLE_CATALOG}.get(role)
    if not task:
        raise ValueError("未知 AI 岗位")
    if role == "debate":
        if not case_id:
            raise ValueError("缺少 case_id")
        return {"role": role, "task": task, "result": start_debate(org_id, case_id, actor_member_id=actor_member_id, use_ai=True)}
    if role == "risk":
        if not proposal_id:
            raise ValueError("缺少 proposal_id")
        return {"role": role, "task": task, "result": ai_risk_review(org_id, proposal_id)}
    if role == "research":
        if not case_id:
            raise ValueError("缺少 case_id")
        return {"role": role, "task": task, "result": ai_research_memo(org_id, case_id)}
    if not case_id:
        raise ValueError("缺少 case_id")
    payload = _role_case_payload(org_id, case_id)
    data = _ai_task(task, payload, _ROLE_PROMPTS[role])
    return {"role": role, "task": task, "memo": data}
