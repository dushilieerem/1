# -*- coding: utf-8 -*-
"""SV 助手对话：业务外壳（系统提示词、思考痕迹清洗）。

供应商解析与 HTTP/SSE 已合并到 `ai/gateway/providers.py`（ADR-037）。
本模块只保留助手场景的业务约束；新调用方请用 `ai.router.stream_task("assistant.chat", ...)`。
"""
from __future__ import annotations

import re
from typing import Any, Iterator

from ai.errors import AiError
from ai.gateway import providers

CHAT_MODELS = providers.CHAT_MODELS

# 兼容旧名
ARK_CHAT_MODELS = CHAT_MODELS

SYSTEM_PROMPT = (
    "你是 SVQuant 智能助手，协助用户做量化研究、因子与策略讨论。"
    "直接给出最终回答，不要输出思考过程、内心独白、任务分析、提纲或「用户意图」类元描述。"
    "不要以「用户问候…」「我需要…」「首先分析…」等开头。"
    "排版：用换行区分层级，不要把多条挤在同一行。"
    "一级写「一、二、三、」；二级写「1. 2. 3.」且章内递增；三级「（1）（2）」各占一行；四级「①②」各占一行。"
    "可用 ## 标一级标题。禁止 --- 分隔线。适合/不适合用 ✅/❌ 且各占一行。"
    "公式：含中文用 $$...$$ 且 \\dfrac{\\text{…}}{\\text{…}}；下标写成 P_{t}；代码块注明语言。"
    "不确定时明确说明；不要编造未给出的回测数字。"
)

#: 兼容别名（旧调用点 `except ArkChatError` 继续有效）。
ArkChatError = AiError


def ark_api_key() -> str:
    for name in ("ARK_API_KEY", "AI_FACTOR_API_KEY"):
        value = providers.key_env(name)
        if value:
            return value
    return ""


def siliconflow_api_key() -> str:
    for name in ("SILICONFLOW_API_KEY", "SILICON_FLOW_API_KEY"):
        value = providers.key_env(name)
        if value:
            return value
    return ""


def ark_base_url() -> str:
    return providers.ark_base_url()


def siliconflow_base_url() -> str:
    return providers.siliconflow_base_url()


def ark_default_model() -> str:
    return providers.ark_default_model()


def ark_configured() -> bool:
    return providers.ark_configured()


def resolve_provider(model_id: str) -> tuple[str, str, str]:
    """返回 (provider, base_url, api_key)。"""
    return providers.resolve_provider(model_id)


def list_ark_models() -> dict[str, Any]:
    return providers.list_models()


_THINK_RE = re.compile(
    r"(?is)<think>.*?</think>|<thinking>.*?</thinking>"
    r"|^\s*用户[^\n]{0,60}(问候|意图|提问|简短)[^\n]*\n+"
    r"|^\s*(简短自我介绍|任务分析|思考过程)[^\n]*\n+"
)


def strip_thinking(text: str) -> str:
    """去掉思考标签 / 首行元描述。"""
    s = (text or "").strip()
    s = _THINK_RE.sub("", s).strip()
    lines = s.splitlines()
    if lines and re.match(r"^(用户|助手|思考|分析|意图|任务)[:：]?", lines[0].strip()):
        if len(lines) > 1 and len(lines[0]) < 80:
            s = "\n".join(lines[1:]).strip()
    return s


def prepare_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """注入助手系统提示词并裁掉无效消息。"""
    cleaned: list[dict[str, str]] = []
    for m in messages[-40:]:
        role = str(m.get("role") or "user").strip()
        content = str(m.get("content") or "").strip()
        if role not in ("system", "user", "assistant") or not content:
            continue
        cleaned.append({"role": role, "content": content})
    if not cleaned:
        raise ArkChatError("无有效消息")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *[m for m in cleaned if m["role"] != "system"],
    ]


# 兼容旧名
_prepare_messages = prepare_messages


def chat(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.7,
    timeout: int = 90,
) -> dict[str, Any]:
    """Legacy 入口：经 ai.router 执行，保留助手侧的思考痕迹清洗与 usage 形状。"""
    from ai.router import run_task

    model_id = (model or providers.ark_default_model()).strip() or providers.ark_default_model()
    if not messages:
        raise ArkChatError("messages 不能为空")
    cleaned = prepare_messages(messages)
    data = run_task("assistant.chat", messages=cleaned, model=model_id)
    usage = data.get("usage") or {}
    return {
        "content": strip_thinking(str(data.get("content") or "")),
        "model": data.get("model") or model_id,
        "usage": {
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
        },
    }


def iter_chat_stream(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.7,
    timeout: int = 120,
) -> Iterator[str]:
    """向上游请求 stream=true，逐段 yield 文本 delta（经 ai.router）。"""
    from ai.router import stream_task

    model_id = (model or providers.ark_default_model()).strip() or providers.ark_default_model()
    if not messages:
        raise ArkChatError("messages 不能为空")
    cleaned = prepare_messages(messages)
    yield from stream_task(
        "assistant.chat",
        messages=cleaned,
        model=model_id,
        temperature=temperature,
        timeout=timeout,
    )


__all__ = [
    "ARK_CHAT_MODELS",
    "CHAT_MODELS",
    "SYSTEM_PROMPT",
    "ArkChatError",
    "ark_api_key",
    "ark_base_url",
    "ark_configured",
    "ark_default_model",
    "chat",
    "iter_chat_stream",
    "list_ark_models",
    "prepare_messages",
    "resolve_provider",
    "siliconflow_api_key",
    "siliconflow_base_url",
    "strip_thinking",
]
