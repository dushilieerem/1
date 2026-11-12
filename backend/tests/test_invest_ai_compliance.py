# -*- coding: utf-8 -*-
"""P1-A05 相关：手机 AI 输出合规扫描不误伤否定句。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routers.invest_ai import BLOCK_MESSAGE, post_scan  # noqa: E402


def test_affirmative_trade_advice_is_blocked() -> None:
    assert post_scan("建议买入并加仓") == BLOCK_MESSAGE
    assert post_scan("目标价 12.50 元") == BLOCK_MESSAGE
    assert post_scan("该股保证收益") == BLOCK_MESSAGE


def test_negated_compliance_phrases_are_allowed() -> None:
    for text in (
        "不保证收益，也不构成投资建议。",
        "不能保证收益。",
        "无法保证盈利。",
        "不建议买入，也不建议卖出。",
    ):
        assert post_scan(text) == text
