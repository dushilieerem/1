# -*- coding: utf-8 -*-
"""L1 供应商层：把「哪家供应商、哪个 base_url、哪个 Key、哪个模型」收敛到一处。

本层只认识 messages / tokens / HTTP，不认识任何业务词（社区、因子、转写）。
业务能力一律经 `ai.router` 调用；本模块只被网关与路由层导入。

兼容口径：
- `llm_client`（LLM_*，OpenAI 兼容，走系统代理）与
  `ark_chat`（ARK_* / AI_FACTOR_* / SILICONFLOW_*，走直连）在此合并为同一实现，
  仅以 `ChatTarget.direct` 区分出口，既有行为不变。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator

from ai.errors import (
    AiBadOutput,
    AiInvalidRequest,
    AiNotConfigured,
    AiOutputTruncated,
    AiTimeout,
    AiUpstreamError,
)
from services.core.env_config import env
from services.core.lan_http import urlopen_direct

logger = logging.getLogger(__name__)

# —— 模型目录（SV 助手可选项；加/删模型只改这里）——
CHAT_MODELS: list[dict[str, str]] = [
    # 火山方舟（Agent Plan）
    {"id": "ark-code-latest", "label": "ark-code-latest", "family": "ark", "provider": "ark"},
    {"id": "doubao-seed-2.0-pro", "label": "Doubao Seed 2.0 Pro", "family": "doubao", "provider": "ark"},
    {"id": "doubao-seed-2.0-code", "label": "Doubao Seed 2.0 Code", "family": "doubao", "provider": "ark"},
    {"id": "doubao-seed-2.0-lite", "label": "Doubao Seed 2.0 Lite", "family": "doubao", "provider": "ark"},
    {"id": "doubao-seed-2.0-mini", "label": "Doubao Seed 2.0 Mini", "family": "doubao", "provider": "ark"},
    {"id": "kimi-k2.6", "label": "Kimi K2.6", "family": "kimi", "provider": "ark"},
    {"id": "kimi-k2.6-thinking", "label": "Kimi K2.6 Thinking", "family": "kimi", "provider": "ark"},
    {"id": "minimax-latest", "label": "MiniMax Latest", "family": "minimax", "provider": "ark"},
    # 硅基流动
    {"id": "deepseek-ai/DeepSeek-V3", "label": "DeepSeek V3", "family": "deepseek", "provider": "siliconflow"},
    {"id": "Qwen/Qwen2.5-72B-Instruct", "label": "Qwen2.5 72B", "family": "qwen", "provider": "siliconflow"},
    {"id": "Qwen/Qwen2.5-Coder-32B-Instruct", "label": "Qwen2.5 Coder 32B", "family": "qwen", "provider": "siliconflow"},
    {"id": "THUDM/glm-4-9b-chat", "label": "GLM-4 9B", "family": "glm", "provider": "siliconflow"},
]

ARK_DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/plan/v3"
SILICONFLOW_DEFAULT_BASE = "https://api.siliconflow.cn/v1"
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
ARK_DEFAULT_MODEL = "ark-code-latest"

# 档位：业务只选档位，不选模型。换模型改环境变量即可。
SLOT_DEFAULT = "default"
SLOT_CODE = "code"
SLOT_FAST = "fast"
SLOT_ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatTarget:
    """一次调用的完整出口参数。"""

    provider: str
    base_url: str
    api_key: str
    model: str
    timeout: int = 60
    direct: bool = False

    def __repr__(self) -> str:  # pragma: no cover - 防密钥进日志
        return f"ChatTarget(provider={self.provider!r}, model={self.model!r}, direct={self.direct})"


def _usable_key(value: str | None) -> str:
    v = (value or "").strip()
    if v.lower() in {"changeme", "your-key", "xxx", "none", "null"}:
        return ""
    return v


def _int_env(name: str, default: int) -> int:
    try:
        return max(5, int(env(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


def _windows_user_env(name: str) -> str:
    """沿用 ark_chat 的既定口径：.env 之外还认 Windows 用户环境变量。"""
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or "").strip()
    except Exception:
        return ""


def key_env(name: str) -> str:
    """密钥读取：进程/.env 优先，其次 Windows 用户环境变量（沿用既有口径）。"""
    v = _usable_key(env(name, ""))
    if v:
        return v
    v = _usable_key(_windows_user_env(name))
    if v:
        try:
            os.environ[name] = v
        except Exception:
            pass
    return v


def ark_base_url() -> str:
    return (env("AI_FACTOR_BASE_URL", ARK_DEFAULT_BASE) or ARK_DEFAULT_BASE).rstrip("/")


def siliconflow_base_url() -> str:
    return (env("SILICONFLOW_BASE_URL", SILICONFLOW_DEFAULT_BASE) or SILICONFLOW_DEFAULT_BASE).rstrip("/")


def ark_default_model() -> str:
    return (env("AI_FACTOR_MODEL_ALIAS", ARK_DEFAULT_MODEL) or ARK_DEFAULT_MODEL).strip()


def ark_configured() -> bool:
    return ark_target() is not None


def openai_target(model: str | None = None) -> ChatTarget | None:
    key = _usable_key(env("LLM_API_KEY", ""))
    if not key:
        return None
    base = (env("LLM_BASE_URL", OPENAI_DEFAULT_BASE) or OPENAI_DEFAULT_BASE).rstrip("/")
    return ChatTarget(
        provider="openai_compatible",
        base_url=base,
        api_key=key,
        model=(model or env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip(),
        timeout=_int_env("LLM_TIMEOUT_SEC", 60),
        direct=False,
    )


def ark_target(model: str | None = None) -> ChatTarget | None:
    key = ""
    for name in ("ARK_API_KEY", "AI_FACTOR_API_KEY"):
        key = key_env(name)
        if key:
            break
    if not key:
        return None
    return ChatTarget(
        provider="ark",
        base_url=ark_base_url(),
        api_key=key,
        model=(model or ark_default_model()).strip(),
        timeout=_int_env("AI_FACTOR_TIMEOUT_SEC", 90),
        direct=True,
    )


def siliconflow_target(model: str | None = None) -> ChatTarget | None:
    key = ""
    for name in ("SILICONFLOW_API_KEY", "SILICON_FLOW_API_KEY"):
        key = key_env(name)
        if key:
            break
    if not key:
        return None
    return ChatTarget(
        provider="siliconflow",
        base_url=siliconflow_base_url(),
        api_key=key,
        model=(model or "deepseek-ai/DeepSeek-V3").strip(),
        timeout=_int_env("AI_FACTOR_TIMEOUT_SEC", 90),
        direct=True,
    )


def model_provider(model_id: str) -> str:
    for meta in CHAT_MODELS:
        if meta["id"] == model_id:
            return meta.get("provider") or "ark"
    return "ark"


def resolve_target(
    *,
    slot: str = SLOT_DEFAULT,
    model: str | None = None,
    provider: str | None = None,
) -> ChatTarget:
    """按档位或显式模型解析出口；都不可用时抛 `AiNotConfigured`。

    档位语义：
    - default：OpenAI 兼容（LLM_*），沿用既有 11 个调用点的口径；
    - code：火山方舟（AI_FACTOR_*），代码生成类任务；
    - fast：优先 default，缺失时回落到 code（不引入第三个供应商）；
    - assistant：按模型 id 归属供应商；该供应商未配置密钥时回落到 default（SV 助手）。
    """
    if model:
        chosen = provider or model_provider(model)
        if chosen == "siliconflow":
            target = siliconflow_target(model)
        elif chosen == "ark":
            target = ark_target(model)
        else:
            target = openai_target(model)
        if target is None and slot == SLOT_ASSISTANT:
            # 助手选中的模型供应商未配置时，回落到 default 网关，避免整个助手不可用
            target = openai_target()
        if target is None:
            raise AiNotConfigured(f"模型 {model} 所属供应商未配置密钥")
        return target

    if slot == SLOT_ASSISTANT:
        target = ark_target() or siliconflow_target() or openai_target()
        if target is None:
            raise AiNotConfigured("未配置 ARK_API_KEY / SILICONFLOW_API_KEY / LLM_API_KEY")
        return target

    if slot == SLOT_CODE:
        # 代码生成默认复用现有 LLM_* 网关；需要火山方舟时显式设
        # AI_CODE_PROVIDER=ark。绝不静默降级：缺对应密钥时明确报未配置。
        code_provider = (env("AI_CODE_PROVIDER", "") or "").strip().lower()
        if not code_provider or code_provider in {"default", "openai", "openai_compatible", "llm"}:
            target = openai_target()
            if target is None:
                raise AiNotConfigured(
                    "代码生成未配置 LLM_API_KEY（默认走 LLM_* 网关；如需 Ark 请设 AI_CODE_PROVIDER=ark）"
                )
            return target
        if code_provider == "ark":
            target = ark_target()
            if target is None:
                raise AiNotConfigured("AI_CODE_PROVIDER=ark 但未配置 ARK_API_KEY / AI_FACTOR_API_KEY")
            return target
        if code_provider == "siliconflow":
            target = siliconflow_target()
            if target is None:
                raise AiNotConfigured("AI_CODE_PROVIDER=siliconflow 但未配置 SILICONFLOW_API_KEY")
            return target
        raise AiNotConfigured(
            f"AI_CODE_PROVIDER={code_provider!r} 不受支持（可选 default/ark/siliconflow）"
        )

    if slot == SLOT_FAST:
        target = openai_target() or ark_target()
        if target is None:
            raise AiNotConfigured("未配置 LLM_API_KEY / ARK_API_KEY")
        return target

    target = openai_target()
    if target is None:
        raise AiNotConfigured("LLM 未配置：请在 backend/.env 设置 LLM_API_KEY")
    return target


def resolve_provider(model_id: str) -> tuple[str, str, str]:
    """兼容 ark_chat 的旧接口：返回 (provider, base_url, api_key)。"""
    target = resolve_target(model=model_id)
    return target.provider, target.base_url, target.api_key


def is_configured(slot: str = SLOT_DEFAULT) -> bool:
    try:
        resolve_target(slot=slot)
    except AiNotConfigured:
        return False
    return True


def list_models() -> dict[str, Any]:
    ark = ark_target()
    sf = siliconflow_target()
    try:
        default_model = resolve_target(slot=SLOT_DEFAULT).model
    except AiNotConfigured:
        default_model = ""
    return {
        "configured": bool(ark or sf),
        "defaultModel": default_model or ARK_DEFAULT_MODEL,
        "baseUrl": ark.base_url if ark else ARK_DEFAULT_BASE,
        "siliconflowBaseUrl": sf.base_url if sf else SILICONFLOW_DEFAULT_BASE,
        "arkConfigured": bool(ark),
        "siliconflowConfigured": bool(sf),
        "models": CHAT_MODELS,
    }


# —— 请求执行 ——


class _HttpFailure(Exception):
    """内部信号：HTTP 状态错误，携带原始状态码与响应体，供重试判定。"""

    def __init__(self, status: int, body: str, reason: str) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body
        self.reason = reason


def _post(target: ChatTarget, payload: dict[str, Any], *, timeout: int, stream: bool):
    url = f"{target.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {target.api_key}",
    }
    if stream:
        headers["Accept"] = "text/event-stream"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    kwargs: dict[str, Any] = {"timeout": max(5, int(timeout))}
    try:
        if target.direct:
            return urlopen_direct(req, **kwargs)
        return urllib.request.urlopen(req, **kwargs)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            pass
        raise _HttpFailure(int(exc.code), body, str(exc.reason)) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise AiTimeout(f"{target.provider} 请求超时") from exc
        raise AiUpstreamError(f"{target.provider} 网络错误: {reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise AiTimeout(f"{target.provider} 请求超时") from exc
    except OSError as exc:
        raise AiUpstreamError(f"{target.provider} 连接失败: {exc}") from exc


def _failure_to_error(failure: _HttpFailure, target: ChatTarget) -> AiUpstreamError:
    if failure.status in (401, 403):
        return AiNotConfigured(
            f"{target.provider} 密钥无效或无权访问（HTTP {failure.status}）",
            detail=failure.body,
        )
    if failure.status == 429:
        return AiUpstreamError(f"{target.provider} 触发限流（HTTP 429）", detail=failure.body)
    return AiUpstreamError(
        f"{target.provider} HTTP {failure.status}: {failure.body or failure.reason}",
        detail=failure.body,
    )


def _response_format_unsupported(failure: _HttpFailure) -> bool:
    """供应商明确拒绝 response_format（与 ResearchEngine 同口径）。

    不同网关文案不一致：Ark 常见 ``response_format.type ... not supported``，
    LiteLLM/DeepSeek 返回 ``This response_format type is unavailable now``。
    只认 400 + response_format 相关字样，避免把普通参数错误误判为格式不支持。
    """
    if failure.status != 400:
        return False
    body = (failure.body or "").lower()
    if "response_format" not in body:
        return False
    return any(
        marker in body
        for marker in ("not supported", "unavailable", "unsupported", "invalid", "unknown")
    )


def _send(
    target: ChatTarget,
    payload: dict[str, Any],
    *,
    timeout: int,
    stream: bool,
):
    """发送请求；`response_format` 被拒时降级重试。

    顺序：原格式 → `json_object`（仅原格式是 json_schema 时）→ 去掉格式。
    模型输出仍必须通过任务 validator，降级不会放宽 JSON/代码静态校验。
    """
    try:
        return _post(target, payload, timeout=timeout, stream=stream)
    except _HttpFailure as failure:
        current = payload.get("response_format")
        if current is None or not _response_format_unsupported(failure):
            raise _failure_to_error(failure, target) from failure
        retries: list[dict[str, Any] | None] = []
        if isinstance(current, dict) and current.get("type") == "json_schema":
            retries.append({"type": "json_object"})
        retries.append(None)
        last = failure
        for fmt in retries:
            retry = dict(payload)
            if fmt is None:
                retry.pop("response_format", None)
            else:
                retry["response_format"] = fmt
            try:
                return _post(target, retry, timeout=timeout, stream=stream)
            except _HttpFailure as retry_failure:
                last = retry_failure
                if not _response_format_unsupported(retry_failure):
                    raise _failure_to_error(retry_failure, target) from retry_failure
        raise _failure_to_error(last, target) from last


class _CompletionCache:
    """进程内结果缓存（P1-A03）：默认关闭，`LLM_CACHE_TTL_SEC>0` 时启用。"""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: int) -> dict[str, Any] | None:
        if ttl <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            row = self._rows.get(key)
            if row is None:
                return None
            expires, value = row
            if expires <= now:
                self._rows.pop(key, None)
                return None
            return json.loads(json.dumps(value))  # 调用方可能改返回值

    def put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        if ttl <= 0:
            return
        with self._lock:
            if len(self._rows) >= 256:
                # 简单淘汰：清掉最早写入的一批，避免无界增长
                for k in list(self._rows)[:64]:
                    self._rows.pop(k, None)
            self._rows[key] = (time.monotonic() + ttl, value)


_CACHE = _CompletionCache()


def _cache_key(target: ChatTarget, payload: dict[str, Any]) -> str:
    raw = json.dumps(
        {"base": target.base_url, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fallback_targets(primary: ChatTarget) -> list[ChatTarget]:
    """`LLM_FALLBACK_MODELS=a,b` 指定的兜底模型；不可配置的自动跳过。"""
    raw = (env("LLM_FALLBACK_MODELS", "") or "").strip()
    if not raw:
        return []
    out: list[ChatTarget] = []
    for model_id in (x.strip() for x in raw.split(",")):
        if not model_id:
            continue
        try:
            candidate = resolve_target(model=model_id)
        except AiNotConfigured:
            continue
        if (candidate.provider, candidate.base_url, candidate.model) == (
            primary.provider,
            primary.base_url,
            primary.model,
        ):
            continue
        out.append(candidate)
    return out


def complete(
    target: ChatTarget,
    *,
    messages: list[dict[str, Any]],
    temperature: float = 0.4,
    max_tokens: int | None = 2048,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    response_format: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """一次非流式补全（P1-A03：超时重试 + 多模型兜底 + 可选缓存）。

    返回 {content, message, tool_calls, tokens_in, tokens_out, model, provider}，
    与原 `chat_completions` 同构，便于调用点无感迁移。
    兜底/重试只针对超时与上游错误；参数错误和输出不合规不静默换模型。
    """
    if not messages:
        raise AiInvalidRequest("messages 不能为空")

    payload: dict[str, Any] = {
        "model": target.model,
        "messages": messages,
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    if response_format is not None:
        payload["response_format"] = response_format

    try:
        cache_ttl = max(0, int(env("LLM_CACHE_TTL_SEC", "0") or "0"))
    except (TypeError, ValueError):
        cache_ttl = 0
    key = _cache_key(target, payload)
    cached = _CACHE.get(key, cache_ttl)
    if cached is not None:
        return {**cached, "cached": True}

    try:
        max_retries = max(0, int(env("LLM_MAX_RETRIES", "1") or "1"))
    except (TypeError, ValueError):
        max_retries = 1
    try:
        output_cap = max(1024, int(env("LLM_MAX_OUTPUT_TOKENS", "32000") or "32000"))
    except (TypeError, ValueError):
        output_cap = 32000

    base_payload = dict(payload)
    base_budget = base_payload.get("max_tokens")
    attempts = [target, *_fallback_targets(target)]
    last_error: Exception | None = None
    for index, current in enumerate(attempts):
        # 每个兜底模型都从任务原始预算开始；推理模型被截断时再逐次提高。
        payload = {**base_payload, "model": current.model}
        budget = base_budget
        retry = 0
        expansions = 0
        while True:
            try:
                resp = _send(
                    current, payload, timeout=int(timeout or current.timeout), stream=False
                )
                result = _normalize(_read_json(resp), current, max_tokens=budget)
                if index > 0:
                    result["fallback_from"] = target.model
                if cache_ttl > 0:
                    _CACHE.put(key, result, cache_ttl)
                return result
            except AiOutputTruncated as exc:
                last_error = exc
                if budget and budget < output_cap and expansions < 3:
                    budget = min(budget * 2, output_cap)
                    expansions += 1
                    payload = {**payload, "max_tokens": budget}
                    logger.warning(
                        "LLM 输出被截断，提高 max_tokens 后重试：model=%s budget=%s detail=%s",
                        current.model,
                        budget,
                        exc.detail,
                    )
                    continue
                break
            except AiBadOutput as exc:
                last_error = exc
                if "内容审核" in str(exc) or "content_filter" in str(exc):
                    break
                if retry < max_retries:
                    retry += 1
                    time.sleep(0.4 * retry)
                    continue
                break
            except (AiTimeout, AiUpstreamError) as exc:
                last_error = exc
                if retry < max_retries:
                    retry += 1
                    time.sleep(0.4 * retry)
                    continue
                break
    assert last_error is not None
    raise last_error


def _read_json(resp) -> dict[str, Any]:
    with resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AiBadOutput("上游返回非 JSON") from exc
    if not isinstance(data, dict):
        raise AiBadOutput("上游响应不是 JSON 对象")
    return data


def _normalize(
    data: dict[str, Any], target: ChatTarget, *, max_tokens: int | None = None
) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not isinstance(choices, list) or not choices:
        raise AiBadOutput("上游无 choices")
    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    tool_calls = message.get("tool_calls") or []
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    finish_reason = str(choice.get("finish_reason") or "")
    text = content if isinstance(content, str) else ""
    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = _int(details.get("reasoning_tokens"))
    diagnostics = {
        "model": data.get("model") or target.model,
        "finish_reason": finish_reason,
        "max_tokens": max_tokens,
        "completion_tokens": _int(usage.get("completion_tokens")),
        "reasoning_tokens": reasoning_tokens,
        "reasoning_chars": len(str(reasoning)),
        "content_chars": len(text),
    }
    detail = json.dumps(diagnostics, ensure_ascii=False)
    if finish_reason == "length":
        logger.warning("LLM 输出达到 token 上限：%s", detail)
        raise AiOutputTruncated("上游输出达到 max_tokens 上限，内容不完整", detail=detail)
    if not text.strip() and not tool_calls:
        logger.warning("LLM 返回空内容：%s", detail)
        if finish_reason == "content_filter":
            raise AiBadOutput("上游内容审核拦截，content 为空", detail=detail)
        if finish_reason == "length" or (
            max_tokens and reasoning_tokens >= max(1, int(max_tokens * 0.95))
        ):
            raise AiOutputTruncated("上游推理/输出 token 耗尽，content 为空", detail=detail)
        raise AiBadOutput("上游返回空内容", detail=detail)
    return {
        "content": text.strip(),
        "message": message,
        "tool_calls": tool_calls if isinstance(tool_calls, list) else [],
        "tokens_in": _int(usage.get("prompt_tokens")),
        "tokens_out": _int(usage.get("completion_tokens")),
        "reasoning_tokens": reasoning_tokens,
        "reasoning_chars": len(str(reasoning)),
        "finish_reason": finish_reason,
        "model": data.get("model") or target.model,
        "provider": target.provider,
        "usage": usage if isinstance(usage, dict) else {},
    }


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def stream(
    target: ChatTarget,
    *,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> Iterator[str]:
    """SSE 流式补全，逐段 yield 文本 delta。"""
    if not messages:
        raise AiInvalidRequest("messages 不能为空")
    payload: dict[str, Any] = {
        "model": target.model,
        "messages": messages,
        "temperature": float(temperature),
        "stream": True,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    resp = _send(target, payload, timeout=int(timeout or target.timeout), stream=True)
    try:
        while True:
            line = resp.readline()
            if not line:
                break
            text_line = line.decode("utf-8", errors="replace").strip()
            if not text_line or text_line.startswith(":") or not text_line.startswith("data:"):
                continue
            data_str = text_line[5:].strip()
            if not data_str or data_str == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if isinstance(piece, str) and piece:
                yield piece
    finally:
        try:
            resp.close()
        except Exception:
            pass


__all__ = [
    "CHAT_MODELS",
    "ChatTarget",
    "SLOT_ASSISTANT",
    "SLOT_CODE",
    "SLOT_DEFAULT",
    "SLOT_FAST",
    "complete",
    "is_configured",
    "list_models",
    "resolve_target",
    "stream",
]
