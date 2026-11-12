# -*- coding: utf-8 -*-
"""AI 任务路由层（ADR-037）。

分层：
  ai/gateway/providers.py   L1 供应商层：出口解析、HTTP/SSE、重试、异常
  ai/router/                L2 任务路由层：TaskSpec 注册表、执行链、统一返回

业务代码唯一入口：
    from ai.router import run_task, stream_task, available_task
    out = run_task("community.polish_title", messages=[...])

约定：
- 上层不得出现供应商名（ark / siliconflow / base_url / api_key）；
- 异常只用 `ai.errors` 里的类型，不按文案猜状态码。
"""
from __future__ import annotations

from ai.router import tasks as _tasks  # noqa: F401  导入即注册任务
from ai.router.errors import (
    AiBadOutput,
    AiError,
    AiInvalidRequest,
    AiNotConfigured,
    AiQuotaExceeded,
    AiTimeout,
    AiUpstreamError,
)
from ai.router.router import available_task, run_task, stream_task
from ai.router.specs import TaskSpec, all_tasks, get_task, register

__all__ = [
    "AiBadOutput",
    "AiError",
    "AiInvalidRequest",
    "AiNotConfigured",
    "AiQuotaExceeded",
    "AiTimeout",
    "AiUpstreamError",
    "TaskSpec",
    "all_tasks",
    "available_task",
    "get_task",
    "register",
    "run_task",
    "stream_task",
]
