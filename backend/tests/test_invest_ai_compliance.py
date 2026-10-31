# -*- coding: utf-8 -*-
"""手机 Invest AI 合规前置/后置扫描回归（PG 版）。"""
from __future__ import annotations

from app.routers import invest_ai as ai


def test_pre_block_explicit_trade_request() -> None:
    assert ai.compliance_block("帮我买入宁德时代")
    assert ai.compliance_block("给我一个目标价")
    assert ai.compliance_block("保证收益的票")


def test_pre_block_allows_research_question() -> None:
    assert not ai.compliance_block("宁德时代最近估值怎么样？")
    assert not ai.compliance_block("我的组合集中度风险大吗？")


def test_post_scan_blocks_actual_advice() -> None:
    assert ai.post_scan("建议买入宁德时代") == ai.BLOCK_MESSAGE
    assert ai.post_scan("目标价为 250 元") == ai.BLOCK_MESSAGE
    assert ai.post_scan("保证收益") == ai.BLOCK_MESSAGE


def test_post_scan_allows_negation() -> None:
    text = "我们不提供目标价、买卖点、涨跌预测或收益承诺。"
    assert ai.post_scan(text) == text
