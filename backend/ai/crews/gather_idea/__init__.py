# -*- coding: utf-8 -*-
"""信息搜集 → Idea → 因子草稿 → 回测报告 → 评价。"""
from ai.crews.gather_idea.gather_agent import run_gather
from ai.crews.gather_idea.idea_agent import run_idea
from ai.crews.gather_idea.factor_agent import run_factor
from ai.crews.gather_idea.pipeline import (
    run_gather_pipeline,
    run_idea_pipeline,
    run_factor_pipeline,
    run_backtest_pipeline,
    run_eval_pipeline,
)

__all__ = [
    "run_gather",
    "run_gather_pipeline",
    "run_idea",
    "run_idea_pipeline",
    "run_factor",
    "run_factor_pipeline",
    "run_backtest_pipeline",
    "run_eval_pipeline",
]
