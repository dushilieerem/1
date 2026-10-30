# -*- coding: utf-8 -*-
"""`ai.errors` 的门面，避免上层同时记两个 import 路径。"""
from __future__ import annotations

from ai.errors import (
    AiBadOutput,
    AiError,
    AiInvalidRequest,
    AiNotConfigured,
    AiQuotaExceeded,
    AiTimeout,
    AiUpstreamError,
)

__all__ = [
    "AiBadOutput",
    "AiError",
    "AiInvalidRequest",
    "AiNotConfigured",
    "AiQuotaExceeded",
    "AiTimeout",
    "AiUpstreamError",
]
