# -*- coding: utf-8 -*-
"""OpenAI 兼容 Chat Completions 客户端（DeepSeek / 通义 / OpenAI 等）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from services.env_config import env


class LlmError(RuntimeError):
    """LLM 调用失败（配置缺失、超时、上游错误）。"""


def llm_configured() -> bool:
    key = (env("LLM_API_KEY", "") or "").strip()
    return bool(key) and key.lower() not in {"changeme", "your-key", "xxx"}


def llm_settings() -> dict[str, Any]:
    base = (env("LLM_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1").rstrip(
        "/"
    )
    model = (env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip()
    try:
        timeout = max(5, int(env("LLM_TIMEOUT_SEC", "60") or "60"))
    except ValueError:
        timeout = 60
    return {
        "base_url": base,
        "api_key": (env("LLM_API_KEY", "") or "").strip(),
        "model": model,
        "timeout": timeout,
        "configured": llm_configured(),
    }


def chat_completions(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """返回 { content, tokens_in, tokens_out, model, provider }。"""
    cfg = llm_settings()
    if not cfg["configured"]:
        raise LlmError("LLM 未配置：请在 backend/.env 设置 LLM_API_KEY")

    url = f"{cfg['base_url']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        raise LlmError(f"LLM HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"LLM 网络错误: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LlmError("LLM 请求超时") from exc
    except json.JSONDecodeError as exc:
        raise LlmError("LLM 返回非 JSON") from exc

    choices = data.get("choices") or []
    if not choices:
        raise LlmError("LLM 无 choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LlmError("LLM 返回空内容")
    usage = data.get("usage") or {}
    return {
        "content": content.strip(),
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
        "model": data.get("model") or cfg["model"],
        "provider": "openai_compatible",
    }
