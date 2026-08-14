# -*- coding: utf-8 -*-
"""多 Agent 编排：发帖 Writer/Critic/Router + 读帖 Summarizer/RiskFlagger。"""
from __future__ import annotations

import os
import re
from typing import Any

from services import agent_store
from services.agent_metrics_trust import evaluate_metrics_trust, normalize_platform_ref
from services.agent_skills import apply_board_patch, run_skill
from services.llm_client import LlmError


def new_board(*, goal: str, context: dict[str, Any]) -> dict[str, Any]:
    title = str(context.get("title") or "")
    body = str(context.get("body") or "")
    ref = normalize_platform_ref(context.get("platform_ref"))
    trust = evaluate_metrics_trust(title=title, body=body, platform_ref=ref)
    return {
        "goal": goal or "community_post_multi",
        "draft": {
            "title": title,
            "body": body,
            "section": str(context.get("section") or "strategy"),
            "code_snippet": str(context.get("code_snippet") or ""),
        },
        "flags": list(trust.get("flags") or []),
        "votes": [],
        "artifacts": {
            "platform_ref": trust.get("platform_ref"),
            "data_trust": {
                "status": trust.get("status"),
                "summary": trust.get("summary"),
            },
        },
        "revision": 0,
        "max_revisions": 2,
        "context_meta": {
            "has_platform_ref": bool(trust.get("platform_ref")),
        },
    }


def new_read_board(*, goal: str, context: dict[str, Any]) -> dict[str, Any]:
    title = str(context.get("title") or "")
    body = str(context.get("body") or "")
    code = str(context.get("code_snippet") or "")
    try:
        body_max = int(os.environ.get("AGENT_READ_BODY_MAX", "0") or "0")
    except ValueError:
        body_max = 0
    try:
        code_max = int(os.environ.get("AGENT_READ_CODE_MAX", "0") or "0")
    except ValueError:
        code_max = 0
    truncated = False
    if body_max > 0 and len(body) > body_max:
        body = body[:body_max]
        truncated = True
    if code_max > 0 and len(code) > code_max:
        code = code[:code_max]
        truncated = True
    post_id = context.get("post_id")
    try:
        source_post_id = (
            int(post_id) if post_id is not None and str(post_id).strip() != "" else None
        )
    except (TypeError, ValueError):
        source_post_id = None
    ref = normalize_platform_ref(context.get("platform_ref"))
    if not ref and source_post_id:
        try:
            from services.community_store import get_post_platform_ref

            ref = normalize_platform_ref(get_post_platform_ref(source_post_id))
        except Exception:
            ref = None
    if not ref:
        from services.agent_metrics_trust import infer_platform_ref_from_share_body

        ref = infer_platform_ref_from_share_body(body)
    if ref and ref.get("factor_name") and not (
        ref.get("metrics_display") or ref.get("metrics")
    ):
        try:
            from services.dashboard_store import lookup_panel_metric

            uni = ref.get("universe_code") or ref.get("universe") or "CSI300"
            per = ref.get("period_code") or ref.get("period") or "3y"
            if uni and not re.match(r"^[A-Za-z0-9_]+$", str(uni)):
                uni = "CSI300"
            if per and not re.match(r"^[0-9]+[my]$", str(per), re.I):
                per = "3y"
            filt = ref.get("filter_limit_up")
            looked = lookup_panel_metric(
                factor_name=str(ref["factor_name"]),
                universe=str(uni),
                period=str(per),
                filter_limit_up=True if filt is None else bool(filt),
            )
            if looked:
                ref = normalize_platform_ref({**ref, **looked})
        except Exception:
            pass
    with_risks = context.get("with_risks")
    if with_risks is None:
        with_risks = True
    trust = evaluate_metrics_trust(title=title, body=body, platform_ref=ref)
    return {
        "goal": goal or "community_read",
        "source": {
            "title": title,
            "body": body,
            "code_snippet": code,
        },
        "summary_md": "",
        "flags": list(trust.get("flags") or []),
        "source_post_id": source_post_id,
        "truncated": truncated,
        "artifacts": {
            "platform_ref": trust.get("platform_ref") or ref,
            "with_risks": bool(with_risks),
            "data_trust": {
                "status": trust.get("status"),
                "summary": trust.get("summary"),
            },
        },
        "revision": 0,
        "max_revisions": 0,
    }


def _step(
    *,
    status: str,
    agent: str,
    skill: str | None,
    detail: str,
    board_revision: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "agent": agent,
        "tool": skill or agent,
        "skill": skill,
        "detail": detail,
        "board_revision": board_revision,
    }


def _run_and_bill(
    *,
    user_id: int,
    run_id: str,
    skill_id: str,
    board: dict[str, Any],
    agent: str,
    steps: list[dict[str, Any]],
    usage_acc: dict[str, Any],
) -> dict[str, Any]:
    agent_store.assert_quota_available(user_id, need=1)
    steps.append(
        _step(
            status="running",
            agent=agent,
            skill=skill_id,
            detail=f"{agent} 调用 {skill_id}",
            board_revision=int(board.get("revision") or 0),
        )
    )
    try:
        result = run_skill(skill_id, board=board)
    except LlmError:
        steps.append(
            _step(
                status="failed",
                agent=agent,
                skill=skill_id,
                detail=f"{skill_id} 失败",
                board_revision=int(board.get("revision") or 0),
            )
        )
        raise
    board = apply_board_patch(board, result.get("board_patch"))
    tin = int(result.get("tokens_in") or 0)
    tout = int(result.get("tokens_out") or 0)
    usage_acc["tokens_in"] += tin
    usage_acc["tokens_out"] += tout
    usage_acc["skills"].append(skill_id)
    if result.get("provider"):
        usage_acc["provider"] = result["provider"]
    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill=skill_id,
        tokens_in=tin,
        tokens_out=tout,
    )
    steps[-1] = _step(
        status="completed",
        agent=agent,
        skill=skill_id,
        detail=f"{agent} 完成 {skill_id}"
        + (f"（{result.get('provider')}）" if result.get("provider") else ""),
        board_revision=int(board.get("revision") or 0),
    )
    return board


def _latest_critic_decision(board: dict[str, Any]) -> str:
    votes = list(board.get("votes") or [])
    for v in reversed(votes):
        if isinstance(v, dict) and v.get("agent") == "critic":
            return str(v.get("decision") or "approve")
    report = ((board.get("artifacts") or {}).get("audit_report") or {})
    return str(report.get("decision") or "approve")


def run_community_crew(
    *,
    user_id: int,
    goal: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    流程：Writer 润色 → Critic 审计 → (revise 则 Writer 删改) → Router 分区
         → 若分区变更可再轻量润色标题。
    """
    agent_store.ensure_ai_usage_schema()
    # 预估上限：polish×2 + audit + strip + section + 可选 polish_title ≈ 6
    agent_store.assert_quota_available(user_id, need=4)

    run_id = agent_store.new_run_id()
    board = new_board(goal=goal, context=context)
    trust0 = (board.get("artifacts") or {}).get("data_trust") or {}
    steps: list[dict[str, Any]] = [
        _step(
            status="completed",
            agent="orchestrator",
            skill=None,
            detail="Planning：crew=community_post（Writer/Critic/Router）",
            board_revision=0,
        ),
        _step(
            status="completed",
            agent="orchestrator",
            skill=None,
            detail=f"数据可信度：{trust0.get('status') or 'unknown'} — {trust0.get('summary') or ''}",
            board_revision=0,
        ),
    ]
    usage_acc: dict[str, Any] = {
        "tokens_in": 0,
        "tokens_out": 0,
        "skills": [],
        "provider": "mock_local",
    }
    status = "Executing"
    agents_trace: list[dict[str, Any]] = []

    # Writer 首轮
    for sk in ("polish_title", "polish_body"):
        board = _run_and_bill(
            user_id=user_id,
            run_id=run_id,
            skill_id=sk,
            board=board,
            agent="writer",
            steps=steps,
            usage_acc=usage_acc,
        )
    agents_trace.append({"agent": "writer", "phase": "polish", "ok": True})

    # Critic
    board = _run_and_bill(
        user_id=user_id,
        run_id=run_id,
        skill_id="audit_claims",
        board=board,
        agent="critic",
        steps=steps,
        usage_acc=usage_acc,
    )
    decision = _latest_critic_decision(board)
    agents_trace.append(
        {
            "agent": "critic",
            "phase": "audit",
            "decision": decision,
            "flags": list(board.get("flags") or []),
        }
    )

    if decision == "block":
        status = "Blocked"
        steps.append(
            _step(
                status="completed",
                agent="orchestrator",
                skill=None,
                detail="Blocked：Critic 判定需人工修改后再发",
                board_revision=int(board.get("revision") or 0),
            )
        )
    elif decision == "revise":
        status = "Revising"
        while (
            int(board.get("revision") or 0) < int(board.get("max_revisions") or 2)
            and _latest_critic_decision(board) == "revise"
            and (board.get("flags") or [])
        ):
            board["revision"] = int(board.get("revision") or 0) + 1
            steps.append(
                _step(
                    status="completed",
                    agent="orchestrator",
                    skill=None,
                    detail=f"Revising：第 {board['revision']} 轮回流 Writer（按flags删改，非整篇重润色）",
                    board_revision=board["revision"],
                )
            )
            board = _run_and_bill(
                user_id=user_id,
                run_id=run_id,
                skill_id="strip_unverifiable",
                board=board,
                agent="writer",
                steps=steps,
                usage_acc=usage_acc,
            )
            agents_trace.append(
                {
                    "agent": "writer",
                    "phase": "strip",
                    "revision": board["revision"],
                    "ok": True,
                }
            )
            # 再审计一次，确认是否还要 revise
            board = _run_and_bill(
                user_id=user_id,
                run_id=run_id,
                skill_id="audit_claims",
                board=board,
                agent="critic",
                steps=steps,
                usage_acc=usage_acc,
            )
            decision = _latest_critic_decision(board)
            agents_trace.append(
                {
                    "agent": "critic",
                    "phase": "re-audit",
                    "decision": decision,
                    "flags": list(board.get("flags") or []),
                }
            )
            if decision == "block":
                status = "Blocked"
                break
        if status == "Blocked":
            pass
        elif _latest_critic_decision(board) == "revise" and (board.get("flags") or []):
            # 两轮仍未过：不定稿为「通过」，保留 flags，交人工；仍可带草稿回编辑器
            status = "NeedsReview"
            votes = list(board.get("votes") or [])
            votes.append(
                {
                    "agent": "orchestrator",
                    "decision": "needs_review",
                    "reason": "已达修订上限仍有异议，请人工改后再发",
                }
            )
            board["votes"] = votes
            steps.append(
                _step(
                    status="completed",
                    agent="orchestrator",
                    skill=None,
                    detail="NeedsReview：两轮仍未过审，保留 flags，交人工",
                    board_revision=int(board.get("revision") or 0),
                )
            )
        else:
            status = "Executing"

    section_before = str((board.get("draft") or {}).get("section") or "")
    # Blocked 不跑 Router；NeedsReview 仍建议分区，但前端要看到 flags
    if status != "Blocked":
        board = _run_and_bill(
            user_id=user_id,
            run_id=run_id,
            skill_id="suggest_section",
            board=board,
            agent="router",
            steps=steps,
            usage_acc=usage_acc,
        )
        section_after = str((board.get("draft") or {}).get("section") or "")
        agents_trace.append(
            {
                "agent": "router",
                "phase": "section",
                "section": section_after,
                "suggestion": ((board.get("artifacts") or {}).get("section_suggestion")),
            }
        )
        if section_after and section_after != section_before:
            board = _run_and_bill(
                user_id=user_id,
                run_id=run_id,
                skill_id="polish_title",
                board=board,
                agent="writer",
                steps=steps,
                usage_acc=usage_acc,
            )
            agents_trace.append(
                {
                    "agent": "writer",
                    "phase": "retitle_after_section",
                    "ok": True,
                }
            )

    if status == "Executing":
        status = "Completed"
    elif status == "NeedsReview":
        # 保留 NeedsReview：草稿可回填，但明确未过审
        pass

    steps.append(
        _step(
            status="completed",
            agent="orchestrator",
            skill=None,
            detail=f"结束：{status}",
            board_revision=int(board.get("revision") or 0),
        )
    )

    draft = board.get("draft") or {}
    outputs = {
        "title": draft.get("title"),
        "body": draft.get("body"),
        "section": draft.get("section"),
    }
    quota = agent_store.get_user_quota(user_id)
    board_summary = {
        "revision": board.get("revision"),
        "flags": board.get("flags") or [],
        "votes": board.get("votes") or [],
        "artifacts": board.get("artifacts") or {},
        "section": draft.get("section"),
    }
    _status_api = {
        "Completed": "completed",
        "Blocked": "blocked",
        "NeedsReview": "needs_review",
    }.get(status, status.lower())
    return {
        "ok": status in ("Completed", "Blocked", "NeedsReview"),
        "run_id": run_id,
        "goal": goal or "community_post_multi",
        "mode": "multi",
        "crew": "community_post",
        "status": _status_api,
        "steps": steps,
        "agents_trace": agents_trace,
        "board": board_summary,
        "outputs": outputs,
        "usage": {
            "tokens_in": usage_acc["tokens_in"],
            "tokens_out": usage_acc["tokens_out"],
            "skills": usage_acc["skills"],
            "provider": usage_acc.get("provider"),
            "quota_daily": quota["quota_daily"],
            "used_today": quota["used_today"],
            "remaining": quota["remaining"],
        },
        "error": None
        if status != "Blocked"
        else "内容被 Critic 拦截，请人工修改后再发",
        "ai_assisted": True,
    }


def run_community_read_crew(
    *,
    user_id: int,
    goal: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    读帖 TL;DR：Summarizer →（可选）RiskFlagger。
    无 Writer↔Critic 改稿环；不写回 posts。
    """
    agent_store.ensure_ai_usage_schema()
    board = new_read_board(goal=goal, context=context)
    with_risks = bool((board.get("artifacts") or {}).get("with_risks", True))
    need = 2 if with_risks else 1
    agent_store.assert_quota_available(user_id, need=need)

    run_id = agent_store.new_run_id()
    steps: list[dict[str, Any]] = [
        _step(
            status="completed",
            agent="orchestrator",
            skill=None,
            detail=f"规划 community_read；with_risks={with_risks}；truncated={board.get('truncated')}",
            board_revision=0,
        )
    ]
    agents_trace: list[dict[str, Any]] = []
    usage_acc: dict[str, Any] = {
        "tokens_in": 0,
        "tokens_out": 0,
        "skills": [],
        "provider": None,
    }
    status = "Executing"
    err_msg: str | None = None

    try:
        board = _run_and_bill(
            user_id=user_id,
            run_id=run_id,
            skill_id="summarize_post",
            board=board,
            agent="summarizer",
            steps=steps,
            usage_acc=usage_acc,
        )
        agents_trace.append(
            {
                "agent": "summarizer",
                "phase": "summarize",
                "ok": True,
                "truncated": bool(board.get("truncated")),
            }
        )
        if with_risks:
            board = _run_and_bill(
                user_id=user_id,
                run_id=run_id,
                skill_id="flag_read_risks",
                board=board,
                agent="risk_flagger",
                steps=steps,
                usage_acc=usage_acc,
            )
            agents_trace.append(
                {
                    "agent": "risk_flagger",
                    "phase": "flags",
                    "ok": True,
                    "flags": list(board.get("flags") or []),
                }
            )
        status = "Completed"
    except LlmError as exc:
        status = "Failed"
        err_msg = str(exc) or "读帖摘要失败"

    steps.append(
        _step(
            status="completed" if status == "Completed" else "failed",
            agent="orchestrator",
            skill=None,
            detail=f"结束：{status}",
            board_revision=0,
        )
    )

    quota = agent_store.get_user_quota(user_id)
    summary_md = str(board.get("summary_md") or "")
    flags = list(board.get("flags") or [])
    return {
        "ok": status == "Completed",
        "run_id": run_id,
        "goal": goal or "为社区帖生成 TL;DR 摘要",
        "mode": "multi",
        "crew": "community_read",
        "status": "completed" if status == "Completed" else "failed",
        "steps": steps,
        "agents_trace": agents_trace,
        "board": {
            "summary_md": summary_md,
            "flags": flags,
            "source_post_id": board.get("source_post_id"),
            "truncated": bool(board.get("truncated")),
            "artifacts": board.get("artifacts") or {},
            "revision": 0,
        },
        "outputs": {
            "summary_md": summary_md,
            "flags": flags,
        },
        "usage": {
            "tokens_in": usage_acc["tokens_in"],
            "tokens_out": usage_acc["tokens_out"],
            "skills": usage_acc["skills"],
            "provider": usage_acc.get("provider"),
            "quota_daily": quota["quota_daily"],
            "used_today": quota["used_today"],
            "remaining": quota["remaining"],
        },
        "error": err_msg,
        "ai_assisted": True,
    }
