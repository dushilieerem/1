# -*- coding: utf-8 -*-
"""AI 能力统一异常语义（ADR-037）。

只有这五种异常会越过路由层边界；HTTP 状态码由 `app/routers/*` 按类型映射，
不再依据错误文案字符串猜测。既有 `LlmError` / `ArkChatError` 是 `AiError` 的别名，
保留为兼容入口，新代码一律抛本模块的类型。
"""
from __future__ import annotations


class AiError(RuntimeError):
    """所有 AI 相关失败的基类。"""

    code = "ai_error"
    http_status = 502

    def __init__(self, message: str = "", *, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail or ""

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志
        base = super().__str__()
        return f"{base} | {self.detail}" if self.detail else base


class AiNotConfigured(AiError):
    """当前任务没有可用的供应商配置（缺 Key / 缺 base_url）。"""

    code = "ai_not_configured"
    http_status = 503


class AiUpstreamError(AiError):
    """上游返回错误，或网络层失败。"""

    code = "ai_upstream_error"
    http_status = 502


class AiTimeout(AiUpstreamError):
    """上游超时（单独成类，便于映射 504 与触发重试）。"""

    code = "ai_timeout"
    http_status = 504


class AiBadOutput(AiError):
    """上游返回内容不满足任务契约（空内容、JSON 结构不符、AST 校验失败）。"""

    code = "ai_bad_output"
    http_status = 502


class AiQuotaExceeded(AiError):
    """用户 AI 配额不足。"""

    code = "ai_quota_exceeded"
    http_status = 429


class AiInvalidRequest(AiError):
    """请求本身不合法（输入校验失败）。"""

    code = "ai_invalid_request"
    http_status = 422


__all__ = [
    "AiError",
    "AiNotConfigured",
    "AiUpstreamError",
    "AiTimeout",
    "AiBadOutput",
    "AiQuotaExceeded",
    "AiInvalidRequest",
]
