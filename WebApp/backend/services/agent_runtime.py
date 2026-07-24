# -*- coding: utf-8 -*-
"""SVQuant Agent 运行时：single（兼容）+ multi（协作审校）。"""
from __future__ import annotations

from typing import Any

from services import agent_store
from services.agent_orchestrator import run_community_crew
from services.agent_skills import (
    SINGLE_SKILLS,
    apply_board_patch,
    run_skill,
)
from services.llm_client import LlmError


def resolve_skills(skills: list[str] | None, goal: str) -> list[str]:
    if skills:
        out: list[str] = []
        for s in skills:
            s = str(s).strip()
            if s in SINGLE_SKILLS and s not in out:
                out.append(s)
        if out:
            return out
    g = (goal or "").lower()
    want_title = "title" in g or "标题" in (goal or "")
    want_body = "body" in g or "正文" in (goal or "") or "摘要" in (goal or "")
    if want_title and not want_body:
        return ["polish_title"]
    if want_body and not want_title:
        return ["polish_body"]
    return ["polish_title", "polish_body"]


def start_run_single(
    *,
    user_id: int,
    goal: str,
    skills: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """单 Agent 顺序调用 skills（发帖快速润色）。"""
    agent_store.ensure_ai_usage_schema()
    ctx = dict(context or {})
    planned = resolve_skills(skills, goal)
    if not planned:
        raise ValueError("没有可执行的技能")

    agent_store.assert_quota_available(user_id, need=len(planned))
    run_id = agent_store.new_run_id()
    board: dict[str, Any] = {
        "goal": goal or "polish_post",
        "draft": {
            "title": str(ctx.get("title") or ""),
            "body": str(ctx.get("body") or ""),
            "section": str(ctx.get("section") or "strategy"),
            "code_snippet": str(ctx.get("code_snippet") or ""),
        },
        "flags": [],
        "votes": [],
        "artifacts": {},
        "revision": 0,
        "max_revisions": 0,
    }
    steps: list[dict[str, Any]] = [
        {
            "status": "completed",
            "agent": "writer",
            "tool": "plan",
            "skill": None,
            "detail": f"规划技能：{', '.join(planned)}",
        }
    ]
    outputs: dict[str, Any] = {}
    tokens_in = 0
    tokens_out = 0
    provider = "mock_local"

    for skill in planned:
        steps.append(
            {
                "status": "running",
                "agent": "writer",
                "tool": skill,
                "skill": skill,
                "detail": f"调用 {skill}",
            }
        )
        try:
            result = run_skill(skill, board=board, ctx=ctx)
        except LlmError:
            steps.append(
                {
                    "status": "failed",
                    "agent": "writer",
                    "tool": "error",
                    "skill": skill,
                    "detail": "LLM 调用失败",
                }
            )
            raise
        board = apply_board_patch(board, result.get("board_patch"))
        outputs.update(result.get("outputs") or {})
        tokens_in += int(result.get("tokens_in") or 0)
        tokens_out += int(result.get("tokens_out") or 0)
        provider = str(result.get("provider") or provider)
        agent_store.record_usage(
            user_id=user_id,
            run_id=run_id,
            skill=skill,
            tokens_in=int(result.get("tokens_in") or 0),
            tokens_out=int(result.get("tokens_out") or 0),
        )
        steps[-1] = {
            "status": "completed",
            "agent": "writer",
            "tool": skill,
            "skill": skill,
            "detail": f"完成 {skill}" + (f"（{provider}）" if provider else ""),
        }
    steps.append(
        {
            "status": "completed",
            "agent": "writer",
            "tool": "done",
            "skill": None,
            "detail": "完成",
        }
    )

    draft = board.get("draft") or {}
    if "title" not in outputs and draft.get("title") is not None:
        outputs["title"] = draft.get("title")
    if "body" not in outputs and draft.get("body") is not None:
        outputs["body"] = draft.get("body")

    quota = agent_store.get_user_quota(user_id)
    return {
        "ok": True,
        "run_id": run_id,
        "goal": goal or "polish_post",
        "mode": "single",
        "status": "completed",
        "steps": steps,
        "agents_trace": [{"agent": "writer", "phase": "single", "skills": planned}],
        "board": {
            "revision": 0,
            "flags": [],
            "votes": [],
            "artifacts": {},
            "section": draft.get("section"),
        },
        "outputs": outputs,
        "usage": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "skills": planned,
            "provider": provider,
            "quota_daily": quota["quota_daily"],
            "used_today": quota["used_today"],
            "remaining": quota["remaining"],
        },
        "error": None,
        "ai_assisted": True,
    }


def start_run(
    *,
    user_id: int,
    goal: str,
    skills: list[str] | None = None,
    context: dict[str, Any] | None = None,
    mode: str | None = None,
    crew: str | None = None,
) -> dict[str, Any]:
    mode_n = (mode or "single").strip().lower()
    if mode_n in ("multi", "crew", "collab"):
        crew_n = (crew or "community_post").strip()
        if crew_n != "community_post":
            raise ValueError(f"暂不支持 crew={crew_n}")
        return run_community_crew(
            user_id=user_id,
            goal=goal or "把草稿整理成可发社区帖",
            context=dict(context or {}),
        )
    return start_run_single(
        user_id=user_id,
        goal=goal,
        skills=skills,
        context=context,
    )
