# -*- coding: utf-8 -*-
"""研究线与助手线 AI 任务。

`strategy_research.agent` 需要 function calling；`assistant.chat` 走流式，
两者都只声明契约，具体 prompt 由调用方构造。
"""
from __future__ import annotations

from ai.gateway.providers import SLOT_ASSISTANT
from ai.router.specs import TaskSpec, register

RESEARCH_TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        task_id="gather_idea.factor",
        description="从研报/公告抽取因子线索",
        temperature=0.2,
        max_tokens=1200,
    ),
    TaskSpec(
        task_id="gather_idea.gather",
        description="多源资料汇总",
        temperature=0.2,
        max_tokens=1200,
    ),
    TaskSpec(
        task_id="gather_idea.idea",
        description="生成研究想法",
        temperature=0.3,
        max_tokens=4500,
    ),
    TaskSpec(
        task_id="strategy_research.agent",
        description="策略研究工具调用循环",
        temperature=0.2,
        max_tokens=2048,
        allow_tools=True,
    ),
    TaskSpec(
        task_id="assistant.chat",
        description="SV 助手对话（流式/非流式）",
        slot=SLOT_ASSISTANT,
        temperature=0.7,
        max_tokens=None,
        allow_stream=True,
    ),
)


def register_research_tasks() -> None:
    for spec in RESEARCH_TASKS:
        register(spec)
