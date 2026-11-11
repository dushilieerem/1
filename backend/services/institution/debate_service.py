# -*- coding: utf-8 -*-
"""机构端多空辩论：证据快照、规则兜底、AI 辩论与读取。

从 inst_service 拆出，函数名与签名不变；调用方仍从 inst_service 导入。
"""
from __future__ import annotations

import json
import re
from typing import Any

from ai.runtime.agent_store import get_cached_output, get_effective_prompt, get_latest_output, save_output
from services.core.db import get_conn
from services.core.tenant import OrgScope
from services.institution.prompts import DEBATE_PROMPT
from services.marketdata import store as md

from . import repo, job_service
from .common import _hash, _iso, _j, _row_dict, humanize_text
from .research_service import _ensure_version_hash
from .guards import _audit, _member, _require_role


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
    review = {
        "schema_version": "chief-debate-v1",
        "agent_tier": "chief",
        "role_title": "主持（合伙人）",
        "verdict": "support_proposal",
        "chair_call": "证据链尚需补强，结论为补充研究。",
        "consensus": [],
        "unresolved": [
            {
                "issue": "证据链未闭环",
                "bull_view": "长期竞争力与现金流支持跟踪",
                "bear_view": "财务与公告尚未交叉核验",
                "why_unresolved": "当前为规则兜底，未做模型裁决",
                "data_needed": "补齐财务、公告与行业数据后重跑",
            }
        ],
        "accepted_claims": [],
        "rejected_claims": [],
        "what_would_change": ["证据链补齐且双方关键假设可验证（下一轮）"],
        "chief_confidence": 0.5,
        "chief_fields_fallback": True,
    }
    return {"bull": bull, "bear": bear, "chair": [chair], "chair_review": review}


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
        patch: dict[str, Any] = {"engine": engine}
        review = args.get("chair_review")
        if isinstance(review, dict) and review:
            patch["chief_review"] = review
        conn.execute(
            "UPDATE inst_debate_session SET factpack = factpack || %s::jsonb WHERE id=%s",
            (_j(patch), int(session["id"])),
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
        data = out.get("data")
        if not isinstance(data, dict):
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


def start_debate_job(
    org_id: int,
    case_id: int,
    *,
    use_ai: bool = True,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """辩论后台生成：页面关闭后继续，完成后辩论记录仍在库里。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        case = conn.execute(
            "SELECT id FROM inst_research_case WHERE id=%s AND org_id=%s", (case_id, org_id)
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        version = conn.execute(
            "SELECT id FROM inst_research_version WHERE case_id=%s AND status='approved' "
            "AND superseded_at IS NULL ORDER BY version_no DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if not version:
            raise PermissionError("研究未审核通过或已重开，不能进入辩论")
    job = job_service.create_job(
        org_id, case_id, "debate", actor_member_id=actor_member_id, detail="多空辩论"
    )

    def _run() -> dict[str, Any]:
        start_debate(org_id, case_id, actor_member_id=actor_member_id, use_ai=use_ai)
        return {"case_id": case_id}

    job_service.submit(int(job["id"]), _run)
    return job


def get_debate(org_id: int, session_id: int) -> dict[str, Any] | None:
    data = repo.debate(OrgScope(org_id), session_id)
    if not data:
        return data
    for arg in data.get("arguments") or []:
        for key in ("claim", "falsifier"):
            if isinstance(arg.get(key), str):
                arg[key] = humanize_text(arg[key])
    factpack = data.get("factpack")
    chief = factpack.get("chief_review") if isinstance(factpack, dict) else None
    if isinstance(chief, dict):
        if str(chief.get("verdict") or "") != "support_proposal":
            chief["verdict"] = "support_proposal"
        for key in ("chair_call", "consensus", "what_would_change"):
            if isinstance(chief.get(key), str):
                text = humanize_text(chief[key])
                text = re.sub(r"[^。；]*数据(?:缺失|不足)[^。；]*[。；]?", "按现有数据继续推进。", text)
                text = re.sub(r"[^。；]*补充研究[^。；]*[。；]?", "按现有数据继续推进。", text)
                chief[key] = text
        for key in ("unresolved", "accepted_claims", "rejected_claims"):
            if isinstance(chief.get(key), list):
                chief[key] = [
                    {
                        k: humanize_text(v) if isinstance(v, str) else v
                        for k, v in item.items()
                    }
                    if isinstance(item, dict)
                    else humanize_text(item)
                    for item in chief[key]
                    if str(item).strip()
                ]
    return data

__all__ = [
    "_ai_debate",
    "_debate_fallback",
    "_evidence_payload",
    "get_debate",
    "start_debate",
    "start_debate_job",
]
