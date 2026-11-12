# -*- coding: utf-8 -*-
"""Agent 目录：机构 14 个可编辑 Agent + 其余 TaskSpec/Skill 只读展示。"""
from __future__ import annotations

from typing import Any

from ai.router import all_tasks
from ai.runtime import agent_store
from ai.runtime.skills import SKILL_REGISTRY
from services.institution.prompts import INSTITUTION_AGENTS, default_prompt


def _source_group(task_id: str) -> str:
    for prefix, label in (
        ("invest.", "投资 AI"),
        ("community.", "社区 AI"),
        ("research.", "研究 AI"),
        ("strategy_research.", "研究 AI"),
        ("assistant.", "助手"),
        ("gather_idea.", "研究 AI"),
    ):
        if task_id.startswith(prefix):
            return label
    return "平台 AI"


def list_agents(*, include_prompt: bool = False) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    institution_ids = {item["task_id"] for item in INSTITUTION_AGENTS}
    for meta in INSTITUTION_AGENTS:
        task_id = meta["task_id"]
        prompt, version = agent_store.get_effective_prompt(task_id, default_prompt(task_id))
        active = agent_store.get_active_prompt(task_id)
        item = {
            **meta,
            "agent_key": task_id,
            "prompt_version": version,
            "override": bool(active),
            "default_prompt": default_prompt(task_id) if include_prompt else None,
            "prompt": prompt if include_prompt else None,
        }
        items.append(item)

    for spec in all_tasks():
        if spec.task_id in institution_ids or spec.task_id.startswith("inst."):
            continue
        items.append(
            {
                "task_id": spec.task_id,
                "agent_key": spec.task_id,
                "name": spec.task_id,
                "group": _source_group(spec.task_id),
                "description": spec.description,
                "auto_run": False,
                "editable": False,
                "source": "platform",
                "prompt_version": spec.prompt_version,
                "override": False,
                "default_prompt": None,
                "prompt": None,
            }
        )

    for skill in SKILL_REGISTRY.values():
        items.append(
            {
                "task_id": f"skill:{skill['id']}",
                "agent_key": f"skill:{skill['id']}",
                "name": skill.get("name") or skill["id"],
                "group": "Agent 技能",
                "description": skill.get("description") or "",
                "auto_run": False,
                "editable": False,
                "source": "skill",
                "prompt_version": "0",
                "override": False,
                "default_prompt": None,
                "prompt": None,
            }
        )
    items.sort(key=lambda x: (x["source"] != "institution", x["group"], x["name"]))
    return items


def get_agent(task_id: str, *, include_prompt: bool = False) -> dict[str, Any] | None:
    return next((item for item in list_agents(include_prompt=include_prompt) if item["task_id"] == task_id), None)


def is_editable_institution(task_id: str) -> bool:
    return any(item["task_id"] == task_id for item in INSTITUTION_AGENTS)
