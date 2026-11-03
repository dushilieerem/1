# -*- coding: utf-8 -*-
"""手机端术语库：分类/搜索/别名匹配。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.invest import glossary  # noqa: E402


def test_list_by_category_and_search() -> None:
    valuation = glossary.list_terms(category="估值")
    assert valuation["total"] >= 3
    assert all(item["category"] == "估值" for item in valuation["items"])
    found = glossary.list_terms(q="市盈率")
    assert any(item["id"] == "pe_ttm" for item in found["items"])


def test_find_term_by_alias() -> None:
    term = glossary.find_term("这个股票的 ROE 怎么看")
    assert term and term["id"] == "roe"
    beta = glossary.find_term("β 是什么")
    assert beta and beta["id"] == "beta"
    assert glossary.find_term("不存在的词") is None


def test_rules_exposes_meta_and_news_helpers() -> None:
    from services.invest import rules

    assert callable(getattr(rules, "build_meta", None))
    assert callable(getattr(rules, "build_news", None))
    assert callable(getattr(rules, "build_search", None))
