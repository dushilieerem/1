# -*- coding: utf-8 -*-
"""策略研究 crew：为 AI Agent 提供真实策略回测工具（run_backtest）。

链路：AI 模型 → 本 crew 工具层 → services.core.re_http_gateway.forward_re
→ ResearchEngine（独立服务）→ 规范化回测结果。
本 crew 不实现任何回测计算，仅做参数校验、提交、轮询与结果规范化。
"""
from ai.crews.strategy_research.agent_loop import run_backtest_chat
from ai.crews.strategy_research.backtest_tool import RunBacktestInput, run_backtest
from ai.crews.strategy_research.registry import execute_tool, openai_tools_spec

__all__ = [
    "RunBacktestInput",
    "run_backtest",
    "execute_tool",
    "openai_tools_spec",
    "run_backtest_chat",
]
