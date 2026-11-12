# -*- coding: utf-8 -*-
"""年报原文抽取（doc_lake / doc_llm）单元测试：不调真实 LLM，不读生产缓存。"""
from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.institution import doc_lake, doc_layer, doc_llm


@pytest.fixture()
def section_cache(tmp_path, monkeypatch):
    rows = {
        "symbol": ["TEST.SZ"] * 6,
        "doc_id": ["D1"] * 6,
        "report_period": ["2025-12-31"] * 6,
        "section_name": ["股份质押冻结"] * 6,
        "page_no": ["10", "11", "12", "13", "14", "15"],
        "text": [
            "管理层讨论与分析，行业情况。",
            "股东名称 本次质押股数 占其所持股份比例 质押起始日",
            "前十名股东质押、冻结情况：无。",
            "董事会由 9 名董事组成，其中独立董事 3 名。",
            "公司控股股东为测试集团，持股 40%。",
            "重要提示：本报告经审计。",
        ],
        "source_sha256": ["x"] * 6,
        "pdf_url": ["u"] * 6,
        "available_time": ["2026-03-20"] * 6,
    }
    path = tmp_path / "sections.parquet"
    pq.write_table(pa.table(rows), path)
    monkeypatch.setenv("SVQUANT_DOC_SECTIONS_PARQUET", str(path))
    doc_lake._dataset.cache_clear()
    yield path
    doc_lake._dataset.cache_clear()


def test_sections_reads_latest_period(section_cache):
    blocks = doc_lake.sections("TEST.SZ", "2026-11-12")
    assert list(blocks) == ["股份质押冻结"]
    assert len(blocks["股份质押冻结"]["pages"]) == 6


def test_section_text_prioritises_keyword_pages(section_cache):
    block = doc_lake.section_text(
        "TEST.SZ", "股份质押冻结", as_of="2026-11-12", max_chars=40, keywords=("质押",)
    )
    assert block is not None
    page_numbers = [p["page_no"] for p in block["pages"]]
    assert 11 in page_numbers
    assert 10 not in page_numbers
    assert block["truncated"] is True


def test_pit_filter_hides_future_documents(section_cache):
    assert doc_lake.sections("TEST.SZ", "2026-03-01") == {}


def test_missing_symbol_returns_empty(section_cache):
    assert doc_lake.sections("NOPE.SZ", "2026-11-12") == {}


def test_validate_drops_unknown_field_and_unverified_quote():
    pages = [{"page_no": 11, "text": "股东名称 本次质押股数 占其所持股份比例"}]
    data = {
        "section": "股份质押冻结",
        "found": True,
        "facts": [
            {"field_key": "pledge_freeze", "value": {"shareholder": "A"}, "quote": "本次质押股数", "page_no": 11, "confidence": 0.9},
            {"field_key": "board_structure", "value": {}, "quote": "本次质押股数", "page_no": 11, "confidence": 0.9},
            {"field_key": "pledge_freeze", "value": {}, "quote": "编造的句子", "page_no": 11, "confidence": 0.9},
            {"field_key": "pledge_freeze", "value": {}, "quote": "本次质押股数", "page_no": 99, "confidence": 0.9},
        ],
    }
    out = doc_llm._validate(data, "股份质押冻结", pages)
    assert len(out["facts"]) == 2
    good, bad_quote = out["facts"]
    assert good["quote_verified"] is True and good["confidence"] == 0.9
    assert bad_quote["quote_verified"] is False and bad_quote["confidence"] <= 0.5


def test_merge_pending_keeps_verified_and_fills_pending():
    summary = {
        "fields": {
            "pledge_freeze": {"label": "质押冻结", "status": "missing", "items": []},
            "board_structure": {
                "label": "董事会结构",
                "status": "have",
                "items": [{"value": {"board_size": 9}, "reviewed": True}],
            },
        },
        "coverage": {"pledge_freeze": "missing", "board_structure": "have"},
    }
    merged = doc_layer.merge_pending(
        summary,
        {
            "pledge_freeze": [{"value": {"shareholder": "A"}, "review_status": "pending"}],
            "board_structure": [{"value": {"board_size": 8}, "review_status": "pending"}],
        },
    )
    assert merged["coverage"]["pledge_freeze"] == "pending"
    assert merged["fields"]["pledge_freeze"]["items"][0]["value"] == {"shareholder": "A"}
    assert merged["coverage"]["board_structure"] == "have"
    assert merged["fields"]["board_structure"]["items"][0]["value"] == {"board_size": 9}


def test_persist_is_off_by_default(monkeypatch):
    monkeypatch.delenv("SVQUANT_DOC_LLM_PERSIST", raising=False)
    assert doc_llm.persist_result({"facts": [{"symbol": "TEST.SZ"}]}) == 0


def _fake_conn(existing):
    calls: list[tuple[str, tuple | None]] = []

    class _Result:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _Conn:
        def execute(self, sql, params=None):
            calls.append((sql, params))
            if sql.strip().startswith("SELECT value_text"):
                return _Result(existing)
            return _Result({"doc_id": "D1"})

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Conn(), calls


def test_persist_inserts_when_no_platform_row(monkeypatch):
    monkeypatch.setenv("SVQUANT_DOC_LLM_PERSIST", "1")
    conn, calls = _fake_conn(None)
    monkeypatch.setattr(doc_llm, "get_conn", lambda: conn)
    written = doc_llm.persist_result(
        {
            "facts": [
                {"symbol": "TEST.SZ", "doc_id": "D1", "field_key": "pledge_freeze", "value": {"a": 1}, "page_no": 11},
                {"symbol": "TEST.SZ", "doc_id": "D1", "field_key": "pledge_freeze", "value": {"a": 2}, "page_no": 12},
            ]
        }
    )
    assert written == 1
    insert_sql = calls[-1][0]
    assert "INSERT INTO svquant.doc_extract" in insert_sql
    assert calls[-1][1][3] == '[{"a": 1}, {"a": 2}]'


def test_persist_replaces_low_quality_verified_row(monkeypatch):
    monkeypatch.setenv("SVQUANT_DOC_LLM_PERSIST", "1")
    conn, calls = _fake_conn(
        {"value_text": "股东名称 股东性质 持股比例 " + "…" * 150, "review_status": "auto_verified"}
    )
    monkeypatch.setattr(doc_llm, "get_conn", lambda: conn)
    written = doc_llm.persist_result(
        {"facts": [{"symbol": "TEST.SZ", "doc_id": "D1", "field_key": "pledge_freeze", "value": {"a": 1}, "page_no": 11}]}
    )
    assert written == 1
    update_sql = calls[-1][0]
    assert "UPDATE svquant.doc_extract" in update_sql
    assert "superseded_value_text = CASE WHEN" in update_sql


def test_persist_keeps_structured_platform_row(monkeypatch):
    monkeypatch.setenv("SVQUANT_DOC_LLM_PERSIST", "1")
    conn, calls = _fake_conn({"value_text": "每10股派息1元", "review_status": "verified"})
    monkeypatch.setattr(doc_llm, "get_conn", lambda: conn)
    written = doc_llm.persist_result(
        {"facts": [{"symbol": "TEST.SZ", "doc_id": "D1", "field_key": "pledge_freeze", "value": {"a": 1}, "page_no": 11}]}
    )
    assert written == 0
    assert all("UPDATE svquant.doc_extract" not in sql for sql, _ in calls)


def test_low_quality_scope_limited_to_governance():
    assert doc_llm.is_low_quality("pledge_freeze", "x" * 300) is True
    assert doc_llm.is_low_quality("dividend_financing", "x" * 300) is False
    assert doc_llm.is_low_quality("pledge_freeze", '[{"shareholder":"A"}]') is False


def test_doc_llm_extract_enabled_by_default(monkeypatch):
    from services.institution.research_service import _doc_llm_extract_enabled

    monkeypatch.delenv("SVQUANT_DOC_LLM_EXTRACT", raising=False)
    assert _doc_llm_extract_enabled() is True


def test_doc_llm_extract_can_be_disabled(monkeypatch):
    from services.institution.research_service import _doc_llm_extract_enabled

    monkeypatch.setenv("SVQUANT_DOC_LLM_EXTRACT", "0")
    assert _doc_llm_extract_enabled() is False
