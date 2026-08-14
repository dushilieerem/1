# -*- coding: utf-8 -*-
"""SV 助手多供应商对话：火山方舟 Agent Plan + 硅基流动（OpenAI 兼容）。

密钥优先读进程环境 / .env，其次 Windows 用户环境变量（与 ARK_API_KEY 同口径）。
加模型：只改 CHAT_MODELS；加供应商：补 resolve_provider + 密钥函数。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Iterator

from services.env_config import env, load_env
from services.lan_http import urlopen_direct

# provider: ark = 火山方舟 /api/plan/v3；siliconflow = 硅基流动（用户所称「轨迹流动」）
# 维护：加/删模型只改本列表
CHAT_MODELS: list[dict[str, str]] = [
    # —— 火山方舟（Agent Plan 冒烟通过）——
    {"id": "ark-code-latest", "label": "ark-code-latest", "family": "ark", "provider": "ark"},
    {"id": "doubao-seed-2.0-pro", "label": "Doubao Seed 2.0 Pro", "family": "doubao", "provider": "ark"},
    {"id": "doubao-seed-2.0-code", "label": "Doubao Seed 2.0 Code", "family": "doubao", "provider": "ark"},
    {"id": "doubao-seed-2.0-lite", "label": "Doubao Seed 2.0 Lite", "family": "doubao", "provider": "ark"},
    {"id": "doubao-seed-2.0-mini", "label": "Doubao Seed 2.0 Mini", "family": "doubao", "provider": "ark"},
    {"id": "kimi-k2.6", "label": "Kimi K2.6", "family": "kimi", "provider": "ark"},
    {"id": "kimi-k2.6-thinking", "label": "Kimi K2.6 Thinking", "family": "kimi", "provider": "ark"},
    {"id": "minimax-latest", "label": "MiniMax Latest", "family": "minimax", "provider": "ark"},
    # —— 硅基流动（与方舟列表不重复）——
    {
        "id": "deepseek-ai/DeepSeek-V3",
        "label": "DeepSeek V3",
        "family": "deepseek",
        "provider": "siliconflow",
    },
    {
        "id": "Qwen/Qwen2.5-72B-Instruct",
        "label": "Qwen2.5 72B",
        "family": "qwen",
        "provider": "siliconflow",
    },
    {
        "id": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "label": "Qwen2.5 Coder 32B",
        "family": "qwen",
        "provider": "siliconflow",
    },
    {
        "id": "THUDM/glm-4-9b-chat",
        "label": "GLM-4 9B",
        "family": "glm",
        "provider": "siliconflow",
    },
]

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


def _pull_windows_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            val, _ = winreg.QueryValueEx(key, name)
            return str(val or "").strip()
    except Exception:
        return ""


def _env_or_user(name: str) -> str:
    load_env()
    v = (os.environ.get(name) or "").strip()
    if v:
        return v
    v = _pull_windows_user_env(name)
    if v:
        os.environ[name] = v
        return v
    return ""


def ark_api_key() -> str:
    for k in ("ARK_API_KEY", "AI_FACTOR_API_KEY"):
        v = _env_or_user(k)
        if v:
            return v
    return ""


def siliconflow_api_key() -> str:
    for k in ("SILICONFLOW_API_KEY", "SILICON_FLOW_API_KEY"):
        v = _env_or_user(k)
        if v:
            return v
    return ""


def ark_base_url() -> str:
    load_env()
    return (
        env("AI_FACTOR_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
        or "https://ark.cn-beijing.volces.com/api/plan/v3"
    ).rstrip("/")


def siliconflow_base_url() -> str:
    load_env()
    return (
        env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        or "https://api.siliconflow.cn/v1"
    ).rstrip("/")


def ark_default_model() -> str:
    return (
        env("AI_FACTOR_MODEL_ALIAS", "ark-code-latest") or "ark-code-latest"
    ).strip()


def ark_configured() -> bool:
    return bool(ark_api_key() or siliconflow_api_key())


def _model_meta(model_id: str) -> dict[str, str]:
    for m in CHAT_MODELS:
        if m["id"] == model_id:
            return m
    return {"id": model_id, "label": model_id, "family": "ark", "provider": "ark"}


def resolve_provider(model_id: str) -> tuple[str, str, str]:
    """返回 (provider, base_url, api_key)。"""
    meta = _model_meta(model_id)
    provider = (meta.get("provider") or "ark").strip().lower()
    if provider == "siliconflow":
        key = siliconflow_api_key()
        if not key:
            raise ArkChatError(
                "未配置 SILICONFLOW_API_KEY（请写入 backend/.env 或系统用户环境变量）"
            )
        return provider, siliconflow_base_url(), key
    key = ark_api_key()
    if not key:
        raise ArkChatError("未配置 ARK_API_KEY（请写入 backend/.env 或系统用户环境变量）")
    return "ark", ark_base_url(), key


def list_ark_models() -> dict[str, Any]:
    return {
        "configured": ark_configured(),
        "defaultModel": ark_default_model(),
        "baseUrl": ark_base_url(),
        "siliconflowBaseUrl": siliconflow_base_url(),
        "arkConfigured": bool(ark_api_key()),
        "siliconflowConfigured": bool(siliconflow_api_key()),
        "models": CHAT_MODELS,
    }


class ArkChatError(RuntimeError):
    pass


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
    if lines and re.match(
        r"^(用户|助手|思考|分析|意图|任务)[:：]?", lines[0].strip()
    ):
        if len(lines) > 1 and len(lines[0]) < 80:
            s = "\n".join(lines[1:]).strip()
    return s


def _prepare_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
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


def _post_completion(
    *,
    base_url: str,
    api_key: str,
    model_id: str,
    cleaned: list[dict[str, str]],
    temperature: float,
    stream: bool,
    timeout: int,
):
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": cleaned,
        "temperature": float(temperature),
    }
    if stream:
        payload["stream"] = True
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if stream:
        headers["Accept"] = "text/event-stream"
    req = urllib.request.Request(url, data=raw, method="POST", headers=headers)
    try:
        return urlopen_direct(req, timeout=max(15, int(timeout)))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            pass
        raise ArkChatError(f"上游 HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ArkChatError(f"上游网络错误: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ArkChatError("上游请求超时") from exc


def chat(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.7,
    timeout: int = 90,
) -> dict[str, Any]:
    model_id = (model or ark_default_model()).strip() or ark_default_model()
    if not messages:
        raise ArkChatError("messages 不能为空")
    _provider, base, key = resolve_provider(model_id)
    cleaned = _prepare_messages(messages)
    with _post_completion(
        base_url=base,
        api_key=key,
        model_id=model_id,
        cleaned=cleaned,
        temperature=temperature,
        stream=False,
        timeout=timeout,
    ) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise ArkChatError("上游响应格式异常") from exc

    text = content if isinstance(content, str) else str(content)
    text = strip_thinking(text)
    usage = data.get("usage") or {}
    return {
        "content": text,
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
    """向上游请求 stream=true，逐段 yield 文本 delta。"""
    model_id = (model or ark_default_model()).strip() or ark_default_model()
    if not messages:
        raise ArkChatError("messages 不能为空")
    _provider, base, key = resolve_provider(model_id)
    cleaned = _prepare_messages(messages)
    resp = _post_completion(
        base_url=base,
        api_key=key,
        model_id=model_id,
        cleaned=cleaned,
        temperature=temperature,
        stream=True,
        timeout=timeout,
    )
    try:
        while True:
            line = resp.readline()
            if not line:
                break
            try:
                text_line = line.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not text_line or text_line.startswith(":"):
                continue
            if not text_line.startswith("data:"):
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
