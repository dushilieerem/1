# -*- coding: utf-8 -*-
"""手机端 Invest AI 任务（ADR-037 TaskSpec）。

合规基线（与 `SVQuant-AI-Agent能力清单交付文档.md` 一致）：
- 只给信息、解释与风险，不给买卖点、目标价、涨跌预测、仓位指令、收益承诺。
- 不自动交易、不代客理财；命中红线走固定话术，不进入模型自由发挥。
- 输出必须带口径（dataSource）与非投资建议声明，由前端卡片协议渲染。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest, TaskSpec, register

PROMPT_VERSION = "invest-v1"

RED_LINE = (
    "合规红线：不提供买卖点、目标价、涨跌预测、仓位指令、收益承诺；"
    "不自动交易、不代客理财。若用户要求上述内容，改为说明风险与可查看的数据。"
)


def _strip(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _load(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip(raw))
    except (json.JSONDecodeError, IndexError, ValueError) as exc:
        raise AiBadOutput("Invest AI 返回不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise AiBadOutput("Invest AI 返回不是 JSON 对象")
    return data


def validate_intent(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    intent = str(data.get("intent") or "").strip()
    allowed = {
        "brief",
        "review",
        "stock",
        "portfolio",
        "debate",
        "compare",
        "announcement",
        "condition",
        "glossary",
        "compliance_block",
        "chat",
    }
    if intent not in allowed:
        raise AiBadOutput("Invest AI 返回了未知意图")
    data["intent"] = intent
    slots = data.get("slots")
    data["slots"] = slots if isinstance(slots, dict) else {}
    return data


def validate_card(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    if not str(data.get("summary") or "").strip():
        raise AiBadOutput("Invest AI 卡片缺少 summary")
    sections = data.get("sections")
    data["sections"] = sections if isinstance(sections, list) else []
    data.setdefault("disclaimer", "AI 生成 · 非投资建议")
    meta = data.get("meta")
    data["meta"] = meta if isinstance(meta, dict) else {}
    data["meta"].setdefault("dataSource", "演示数据")
    return data


INTENT_TASK = register(
    TaskSpec(
        task_id="invest.intent",
        description="Invest 意图路由与槽位抽取",
        temperature=0.1,
        max_tokens=800,
        timeout_sec=60,
        executors=("local",),
        validator=validate_intent,
    )
)

DAILY_TASK = register(
    TaskSpec(
        task_id="invest.daily",
        description="Invest 个性化日报 / 收盘复盘 / 持仓解读",
        temperature=0.4,
        max_tokens=2500,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

STOCK_TASK = register(
    TaskSpec(
        task_id="invest.stock",
        description="Invest 个股洞察：数据摘要、财务/估值解读、多空分歧",
        temperature=0.35,
        max_tokens=3500,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

PORTFOLIO_TASK = register(
    TaskSpec(
        task_id="invest.portfolio",
        description="Invest 组合诊断：问题 → 依据 → 风险提示（不给调仓指令）",
        temperature=0.25,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_card,
    )
)

ANNOUNCEMENT_TASK = register(
    TaskSpec(
        task_id="invest.announcement",
        description="Invest 公告/业绩会要点：发生了什么 / 影响 / 关注",
        temperature=0.25,
        max_tokens=2000,
        timeout_sec=90,
        executors=("local",),
        validator=validate_card,
    )
)

CONDITION_TASK = register(
    TaskSpec(
        task_id="invest.condition",
        description="Invest 自然语言条件选股解析",
        temperature=0.1,
        max_tokens=1200,
        timeout_sec=60,
        executors=("local",),
        validator=lambda raw, req: _load(raw),
    )
)

__all__ = [
    "ANNOUNCEMENT_TASK",
    "CONDITION_TASK",
    "DAILY_TASK",
    "INTENT_TASK",
    "PORTFOLIO_TASK",
    "PROMPT_VERSION",
    "RED_LINE",
    "STOCK_TASK",
    "validate_card",
    "validate_intent",
]
