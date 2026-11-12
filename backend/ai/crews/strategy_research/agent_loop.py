# -*- coding: utf-8 -*-
"""AI 回测助手：自然语言 → 模型 Tool Calling → run_backtest → 真实结果作答。

模型侧只做意图识别与参数抽取；回测一律由后端执行真实工具
（ai.crews.strategy_research.registry.execute_tool → ResearchEngine）。
模型最终回答必须基于工具返回的真实结果，失败/超时须如实转述。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiError
from ai.router import run_task
from ai.crews.strategy_research.registry import execute_tool, openai_tools_spec
from ai.runtime import store as agent_store

#: 兼容旧调用点的异常捕获。
LlmError = AiError

SYSTEM_PROMPT = (
    "你是 SVQuant 量化投研平台的策略研究助手。\n"
    "当用户想回测策略时，调用 run_backtest 工具：\n"
    "- 用户提到内置策略名称时，优先用 strategy_id（内置策略库如 ma_13_26_maotai 是"
    "「贵州茅台 13/26 日双均线」）；用户直接给 Python 策略代码时用 strategy_code。\n"
    "- 起止时间未说明时选最近的一段完整区间（如近 1 年），并在回答里说明你选的区间。\n"
    "- 回测区间不宜过长，避免不必要的等待。\n"
    "硬性要求：\n"
    "1. 所有收益/回撤/夏普等数字只能来自工具返回的 metrics，严禁编造或估算。\n"
    "2. 工具返回 ok=false 时，如实告诉用户失败原因，不得声称回测成功。\n"
    "3. 引擎未提供的指标（missing_metrics）要明确说「引擎未提供」。\n"
    "回答用中文，简洁给出关键指标和一句解读。"
)

_MAX_TOOL_ROUNDS = 3


def _tool_call_items(resp_tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for tc in resp_tool_calls:
        fn = tc.get("function") or {}
        name = str(fn.get("name") or "").strip()
        raw_args = fn.get("arguments")
        if isinstance(raw_args, dict):
            args = raw_args
        else:
            try:
                args = json.loads(str(raw_args or "{}"))
            except json.JSONDecodeError:
                args = {}
        call_id = str(tc.get("id") or f"call_{len(out)}")
        out.append({"id": call_id, "name": name, "args": args})
    return out


def run_backtest_chat(
    *,
    user_id: int,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """一条自然语言 → 工具调用循环 → 最终中文回答（基于真实回测结果）。"""
    text = str(message or "").strip()
    if not text:
        raise ValueError("message 不能为空")

    agent_store.ensure_ai_usage_schema()
    agent_store.assert_quota_available(user_id, need=1)
    run_id = agent_store.new_run_id()

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history or []:
        role = str(turn.get("role") or "").strip()
        content = str(turn.get("content") or "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})

    tools_spec = openai_tools_spec()
    tool_trace: list[dict[str, Any]] = []
    tokens_in = 0
    tokens_out = 0
    answer = ""

    for _round in range(_MAX_TOOL_ROUNDS + 1):
        resp = run_task(
            "strategy_research.agent",
            messages=messages,
            tools=tools_spec,
        )
        tokens_in += int(resp.get("tokens_in") or 0)
        tokens_out += int(resp.get("tokens_out") or 0)
        calls = _tool_call_items(resp.get("tool_calls") or [])

        if not calls:
            answer = str(resp.get("content") or "").strip()
            break

        messages.append(resp["message"])
        for call in calls:
            result = execute_tool(call["name"], call["args"], user_id=user_id)
            tool_trace.append(
                {
                    "tool": call["name"],
                    "args": call["args"],
                    "ok": bool(result.get("ok")),
                    "status": result.get("status"),
                    "run_id": result.get("run_id"),
                    "error": result.get("error"),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        answer = "已达到工具调用轮次上限，未能生成最终回答；请缩小问题范围后重试。"

    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill="strategy_research_chat",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    quota = agent_store.get_user_quota(user_id)
    return {
        "ok": True,
        "run_id": run_id,
        "status": "completed",
        "answer": answer,
        "tool_trace": tool_trace,
        "usage": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tool_calls": len(tool_trace),
            "quota_daily": quota["quota_daily"],
            "used_today": quota["used_today"],
            "remaining": quota["remaining"],
        },
    }
