# -*- coding: utf-8 -*-
"""任务模块：导入即注册（进程级一次）。"""
from __future__ import annotations

from ai.router.tasks.backtest_interpretation import INTERPRET_TASK  # noqa: F401  导入即注册
from ai.router.tasks.community import register_community_tasks
from ai.router.tasks.community_summary import SUMMARY_TASK  # noqa: F401  导入即注册
from ai.router.tasks.factor_generation import FACTOR_TASK  # noqa: F401  导入即注册
from ai.router.tasks.research import register_research_tasks
from ai.router.tasks.strategy_generation import STRATEGY_TASK  # noqa: F401  导入即注册

register_community_tasks()
register_research_tasks()

__all__ = ["register_community_tasks", "register_research_tasks"]
