"""社区摘要复用RE现有模型API，模型凭据继续仅留在RE。"""
from __future__ import annotations
import logging
from typing import Any
from ai.gateway.llm_client import LlmError
from services.core.env_config import env

logger = logging.getLogger(__name__)


def summarize_with_re(*, title: str, body: str, code_snippet: str,
                      grounding: dict[str, Any], truncated: bool) -> dict[str, Any] | None:
    # 没有RE的纯本地开发环境保留明确标注的非AI节选。
    if not (env("YG_RE_BASE", "") or "").strip():
        return None
    payload = {
        "title": title[:512], "body": body[:20000], "code_snippet": code_snippet[:20000],
        "grounding": grounding,
        "truncated": truncated or len(title) > 512 or len(body) > 20000 or len(code_snippet) > 20000,
    }
    try:
        from services.core.re_http_gateway import forward_re
        status, _, data = forward_re("POST", "/api/ai/post-summaries", payload=payload, timeout=60)
    except Exception as exc:
        logger.warning("RE post summary connection failed: %s", type(exc).__name__)
        raise LlmError("AI摘要服务连接失败，请稍后重试") from exc
    if status < 200 or status >= 300:
        logger.warning("RE post summary failed, status=%s", status)
    if status == 404:
        raise LlmError("AI摘要服务尚未就绪，请联系管理员完成启用")
    if status == 504:
        raise LlmError("共享AI摘要模型请求超时，请稍后重试")
    if status < 200 or status >= 300:
        raise LlmError("AI摘要服务暂不可用，请稍后重试")
    if not isinstance(data, dict) or data.get("summary_source") != "llm":
        raise LlmError("共享AI摘要服务返回来源无效，未生成AI摘要")
    summary = data.get("summary_md")
    if not isinstance(summary, str) or not summary.strip():
        raise LlmError("共享AI摘要服务返回空摘要")
    try:
        return {
            "summary_md": summary.strip(), "model": str(data.get("model") or ""),
            "provider": str(data.get("provider") or "openai_compatible"),
            "tokens_in": max(0, int(data.get("tokens_in") or 0)),
            "tokens_out": max(0, int(data.get("tokens_out") or 0)),
            "truncated": payload["truncated"],
        }
    except (TypeError, ValueError) as exc:
        raise LlmError("共享AI摘要服务返回的用量信息无效") from exc
