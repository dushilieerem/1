# -*- coding: utf-8 -*-
"""社区线 AI 任务（原 `ai/runtime/skills.py` 的内联参数集中到此）。

prompt 仍留在 skill 实现里；本文件只声明“用什么档位、多少 token、什么温度”。
P1 迁移 RE 能力时，prompt 与校验器随任务一起迁入 `ai/router/tasks/`。
"""
from __future__ import annotations

from ai.router.specs import TaskSpec, register

COMMUNITY_TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        task_id="community.polish_title",
        description="润色社区帖标题",
        temperature=0.35,
        max_tokens=200,
    ),
    TaskSpec(
        task_id="community.polish_body",
        description="润色社区帖正文",
        temperature=0.35,
        max_tokens=1200,
    ),
    TaskSpec(
        task_id="community.suggest_section",
        description="建议社区分区",
        temperature=0.2,
        max_tokens=200,
    ),
    TaskSpec(
        task_id="community.audit_claims",
        description="审计夸大表述",
        temperature=0.1,
        max_tokens=800,
    ),
    TaskSpec(
        task_id="community.strip_unverifiable",
        description="按审计结论删改不可核实句",
        temperature=0.25,
        max_tokens=1400,
    ),
    TaskSpec(
        task_id="community.summarize_post",
        description="读帖摘要（TL;DR）",
        temperature=0.2,
        max_tokens=450,
    ),
    TaskSpec(
        task_id="community.flag_read_risks",
        description="读帖风险标注",
        temperature=0.1,
        max_tokens=600,
    ),
)


def register_community_tasks() -> None:
    for spec in COMMUNITY_TASKS:
        register(spec)
