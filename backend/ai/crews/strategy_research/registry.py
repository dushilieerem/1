# -*- coding: utf-8 -*-
"""轻量工具注册表：AI Agent 可调用的工具集中登记（名称 → schema + handler）。

新工具接入方式：在本文件 TOOLS 中加一项（schema + handler），即可被
agent_loop 的 function-calling 循环发现与执行。
"""
from __future__ import annotations

from typing import Any, Callable

from ai.crews.strategy_research.backtest_tool import RunBacktestInput, run_backtest

RunBacktestHandler = Callable[..., dict[str, Any]]

_TOOLS: dict[str, dict[str, Any]] = {
    "run_backtest": {
        "description": (
            "运行一次真实的策略回测（由 ResearchEngine 引擎执行）。"
            "strategy_code 与 strategy_id 必须且只能提供一个；"
            "返回真实指标（总收益率/年化/最大回撤/夏普等），引擎未提供的指标会在 "
            "missing_metrics 中说明。回测可能耗时数十秒到数分钟。"
        ),
        "parameters": RunBacktestInput.model_json_schema(),
        "handler": run_backtest,
    },
}


def tool_names() -> list[str]:
    return sorted(_TOOLS)


def openai_tools_spec() -> list[dict[str, Any]]:
    """OpenAI function calling 的 tools 参数。"""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": meta["description"],
                "parameters": meta["parameters"],
            },
        }
        for name, meta in sorted(_TOOLS.items())
    ]


def execute_tool(name: str, args: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    """执行已注册工具；未注册工具返回明确错误（不抛异常）。"""
    meta = _TOOLS.get(str(name or "").strip())
    if not meta:
        return {
            "ok": False,
            "tool": name,
            "status": "unknown_tool",
            "error": f"未注册的工具：{name}（可用：{', '.join(sorted(_TOOLS))}）",
        }
    handler: RunBacktestHandler = meta["handler"]
    return handler(args if isinstance(args, dict) else {}, user_id=user_id)
