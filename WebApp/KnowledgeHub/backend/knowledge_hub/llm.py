# -*- coding: utf-8 -*-
"""OpenAI 兼容 Chat Completions（读 KnowledgeHub 默认 LLM 供应商）。"""
from __future__ import annotations

from typing import Any

from knowledge_hub.embedding import _post_json, get_role_credentials


class KhLlmError(RuntimeError):
    """知识库 LLM 调用失败。"""


def llm_configured() -> bool:
    return get_role_credentials("llm") is not None


def chat_completions(
    *,
    messages: list[dict[str, str]],
    temperature: float | None = 0.2,
    max_tokens: int | None = 2048,
    top_p: float | None = None,
    model_override: str | None = None,
    creds: dict[str, str] | None = None,
) -> dict[str, Any]:
    """返回 { content, model, tokensIn, tokensOut, providerKey }。"""
    c = creds or get_role_credentials("llm")
    if not c:
        raise KhLlmError("未配置默认 LLM（设置页：供应商 / 默认模型 / Key）")

    url = f"{c['baseUrl']}/chat/completions"
    payload: dict[str, Any] = {
        "model": (model_override or c["modelName"]).strip(),
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if top_p is not None:
        payload["top_p"] = float(top_p)

    data = _post_json(url, payload, c["apiKey"], timeout=120, retries=2)
    choices = data.get("choices") or []
    if not choices:
        raise KhLlmError("LLM 返回空 choices")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if content is None:
        content = ""
    usage = data.get("usage") or {}
    return {
        "content": str(content).strip(),
        "model": str(data.get("model") or payload["model"]),
        "tokensIn": int(usage.get("prompt_tokens") or 0),
        "tokensOut": int(usage.get("completion_tokens") or 0),
        "providerKey": c["providerKey"],
    }
