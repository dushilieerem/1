# -*- coding: utf-8 -*-
"""手机端术语库：分类/搜索/别名匹配，以及人话正文/例子/常见误用。"""
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


def test_glossary_terms_have_plain_example_and_misuse() -> None:
    out = glossary.list_terms()
    assert out["items"]
    for item in out["items"]:
        assert item.get("plain"), item["id"]
        assert item.get("example"), item["id"]
        assert item.get("misuse"), item["id"]


def test_glossary_find_term_returns_explain() -> None:
    item = glossary.find_term("PE 分位是多少")
    assert item and item["id"] == "pe_ttm"
    assert item["plain"] and item["misuse"]
    assert "投资建议" not in item["plain"]


def test_matching_acceptance_cases() -> None:
    cases = {
        "夏普比率": ("sharpe", 1),
        "夏普": "sharpe",
        "夏普比": "sharpe",
        "夏谱": ("sharpe", 4),
        "Sharpe": "sharpe",
        "sharpe ratio": "sharpe",
        "什么是夏普": "sharpe",
        "夏普比率是什么意思": "sharpe",
        "ROE": "roe",
        "roe 怎么算": "roe",
        "市盈率": "pe_ttm",
        "PE": "pe_ttm",
        "最大回撤率": "max_drawdown",
        "MDD": "max_drawdown",
        "β": "beta",
        "贝塔系数": "beta",
        "索提诺": "sortino",
        "下行夏普": "sortino",
        "IR": "information_ratio",
        "Calmar": "calmar",
    }
    for query, expected in cases.items():
        hit = glossary.lookup(query)
        term = hit["matched"]
        if isinstance(expected, tuple):
            assert term and term["id"] == expected[0], query
            assert hit["layer"] == expected[1], query
        else:
            assert term and term["id"] == expected, query


def test_single_char_and_stop_word_go_to_suggestions() -> None:
    for query in ("夏", "率"):
        hit = glossary.lookup(query)
        assert hit["matched"] is None, query
        assert 1 <= len(hit["candidates"]) <= 3, query


def test_unknown_word_gets_three_real_candidates() -> None:
    hit = glossary.lookup("阿巴阿巴")
    assert hit["matched"] is None
    assert len(hit["candidates"]) == 3
    assert all(x["id"] for x in hit["candidates"])


def test_model_candidate_requires_existing_id() -> None:
    hit = glossary.lookup("那个衡量风险的指标", model_term_id="sharpe")
    assert hit["layer"] == 5 and hit["matched"]["id"] == "sharpe"
    fake = glossary.lookup("那个衡量风险的指标", model_term_id="not_a_real_term")
    assert fake["matched"] is None


def test_aliases_do_not_conflict_with_term_names() -> None:
    names = {glossary.normalize(x["term"]): x["id"] for x in glossary.TERMS}
    aliases: dict[str, str] = {}
    for item in glossary.TERMS:
        for alias in item.get("aliases") or []:
            key = glossary.normalize(alias)
            assert key, item["id"]
            if key in names:
                assert names[key] == item["id"], f"{alias} 与 {names[key]} 冲突"
            assert key not in aliases or aliases[key] == item["id"], f"{alias} 被多个词条使用"
            aliases[key] = item["id"]


def test_expanded_detail_for_sharpe() -> None:
    term = glossary.find_term("夏普")
    assert term["formula"] == "S = (Rp − Rf) ÷ σp"
    assert "0.67" in term["calc_example"]
    assert len(term["misreads"]) >= 2
    assert {x["term"] for x in term["compare"]} >= {"索提诺比率", "信息比率", "卡玛比率"}
    assert term["where"]
