# -*- coding: utf-8 -*-
"""Legacy 兼容入口（ADR-037）。

实现已迁到 `ai/gateway/providers.py`（出口解析 + HTTP）与 `ai/router/`（任务路由）。
本模块只为既有调用点与测试保留同名 API，**新代码请用 `ai.router`**。
"""
from __future__ import annotations

from typing import Any

from ai.errors import AiError, AiNotConfigured
from ai.gateway import providers

#: 兼容别名：既有 `except LlmError` 与 `raise LlmError(...)` 继续有效。
LlmError = AiError


def llm_configured() -> bool:
    return providers.is_configured(providers.SLOT_DEFAULT)


def llm_settings() -> dict[str, Any]:
    try:
        target = providers.resolve_target(slot=providers.SLOT_DEFAULT)
    except AiNotConfigured:
        return {
            "base_url": providers.OPENAI_DEFAULT_BASE,
            "api_key": "",
            "model": (providers.env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"),
            "timeout": 60,
            "configured": False,
        }
    return {
        "base_url": target.base_url,
        "api_key": target.api_key,
        "model": target.model,
        "timeout": target.timeout,
        "configured": True,
    }


def chat_completions(
    *,
    messages: list[dict[str, Any]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """OpenAI 兼容补全（legacy）。

    返回 {content, message, tool_calls, tokens_in, tokens_out, model, provider}。
    """
    target = providers.resolve_target(slot=providers.SLOT_DEFAULT)
    return providers.complete(
        target,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        tool_choice=tool_choice,
    )


__all__ = ["LlmError", "chat_completions", "llm_configured", "llm_settings"]
