# -*- coding: utf-8 -*-
"""Agent 运行时：额度、编排、skills。

导出采用惰性加载（PEP 562）：`store` 依赖 PostgreSQL 驱动，
但 skills / 路由层本身并不需要数据库；让 `import ai.runtime.skills`
不必先装 psycopg，也让 AI 层可以脱离数据库做单测。
"""
from __future__ import annotations

from typing import Any

_FROM_STORE = frozenset(
    {
        "ensure_ai_usage_schema",
        "new_run_id",
        "set_user_ai_quota",
        "usage_admin_summary",
        "usage_summary_for_user",
    }
)
_FROM_RUNTIME = frozenset({"resolve_skills", "start_run"})

__all__ = [
    "ensure_ai_usage_schema",
    "new_run_id",
    "resolve_skills",
    "set_user_ai_quota",
    "start_run",
    "usage_admin_summary",
    "usage_summary_for_user",
]


def __getattr__(name: str) -> Any:
    if name in _FROM_STORE:
        from ai.runtime import store

        return getattr(store, name)
    if name in _FROM_RUNTIME:
        from ai.runtime import runtime

        return getattr(runtime, name)
    raise AttributeError(f"module 'ai.runtime' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
