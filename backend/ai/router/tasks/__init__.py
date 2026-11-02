# -*- coding: utf-8 -*-
"""任务模块：导入即注册（进程级一次）。"""
from __future__ import annotations

from ai.router.tasks.backtest_interpretation import INTERPRET_TASK  # noqa: F401  导入即注册
from ai.router.tasks.community import register_community_tasks
from ai.router.tasks.community_summary import SUMMARY_TASK  # noqa: F401  导入即注册
from ai.router.tasks.factor_generation import FACTOR_TASK  # noqa: F401  导入即注册
from ai.router.tasks.institution import (  # noqa: F401  导入即注册
    CHAIRMAN_MEMO_TASK,
    DEBATE_TASK,
    DIMENSION_TASKS,
    FINANCIAL_ROLE_TASK,
    GOVERNANCE_ROLE_TASK,
    POST_INVESTMENT_ROLE_TASK,
    RESEARCH_MEMO_TASK,
    RISK_REVIEW_TASK,
)
from ai.router.tasks.invest import (  # noqa: F401  导入即注册
    ANNOUNCEMENT_TASK,
    COMPARE_TASK,
    CONDITION_TASK,
    DAILY_TASK,
    INTENT_TASK,
    PAPER_TASK,
    PORTFOLIO_TASK,
    QUANT_TASK,
    STOCK_TASK,
)
from ai.router.tasks.research import register_research_tasks
from ai.router.tasks.strategy_generation import STRATEGY_TASK  # noqa: F401  导入即注册
from ai.router.tasks.strategy_transcription import TRANSCRIPTION_TASK  # noqa: F401  导入即注册

register_community_tasks()
register_research_tasks()

__all__ = ["register_community_tasks", "register_research_tasks"]
