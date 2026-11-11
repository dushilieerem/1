# -*- coding: utf-8 -*-
"""doc_extract 接入层：PIT、复核状态与 FactPack 完整性联动。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution import doc_layer  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, table: str | None = "doc_extract", columns: set[str] | None = None, rows=None):
        self.table = table
        self.columns = columns or {
            "symbol",
            "field_key",
            "field_label",
            "value_text",
            "value_num",
            "unit",
            "report_period",
            "page_no",
            "quote",
            "doc_id",
            "pdf_sha256",
            "source_url",
            "available_time",
            "extractor_version",
            "confidence",
            "review_status",
        }
        self.rows = rows or []
        self.sqls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.sqls.append((sql, params))
        if "to_regclass" in sql:
            name = params[0]
            return _Result([{"t": name if name == self.table else None}])
        if "information_schema.columns" in sql:
            return _Result([{"column_name": c} for c in sorted(self.columns)])
        if "SELECT *" in sql:
            return _Result(self.rows)
        raise AssertionError(sql)


ROWS = [
    {
        "symbol": "600519.SH",
        "field_key": "top5_customers",
        "value_text": "前五名客户销售额占比 12.3%",
        "value_num": None,
        "unit": "%",
        "report_period": "2025A",
        "page_no": 38,
        "quote": "前五名客户销售额占年度销售总额 12.3%",
        "doc_id": "doc-2025-annual",
        "pdf_sha256": "abc",
        "available_time": "2026-03-28",
        "confidence": 0.92,
        "review_status": "approved",
    },
    {
        "symbol": "600519.SH",
        "field_key": "volume_price_split",
        "value_num": 3.1,
        "unit": "%",
        "report_period": "2025A",
        "page_no": 22,
        "quote": "销量同比增长 3.1%",
        "doc_id": "doc-2025-annual",
        "pdf_sha256": "abc",
        "available_time": "2026-03-28",
        "confidence": 0.71,
        "review_status": "pending",
    },
    {
        "symbol": "600519.SH",
        "field_key": "cost_structure",
        "value_text": "营业成本中直接材料占 61%",
        "report_period": "2025A",
        "page_no": 41,
        "quote": "直接材料占营业成本 61%",
        "doc_id": "doc-2025-annual",
        "pdf_sha256": "abc",
        "available_time": "2026-03-28",
        "review_status": "verified",
    },
    {
        "symbol": "600519.SH",
        "field_key": "guarantee",
        "value_text": "公司报告期无违规对外担保情况",
        "report_period": "2025A",
        "page_no": 45,
        "quote": "三、违规对外担保情况 适用 不适用 公司报告期无违规对外担保情况。",
        "doc_id": "doc-2025-annual",
        "pdf_sha256": "abc",
        "available_time": "2026-03-28",
        "review_status": "auto_verified",
    },
]


def test_missing_table_degrades_to_empty_coverage() -> None:
    out = doc_layer.load_doc_extracts(_FakeConn(table=None), "600519.SH", "2026-10-30")
    assert out["available"] is False
    assert out["reason"] == "doc_extract 表未建立"
    assert set(out["coverage"].values()) == {"missing"}


def test_missing_required_column_degrades() -> None:
    conn = _FakeConn(columns={"field_key", "value_text"})
    out = doc_layer.load_doc_extracts(conn, "600519.SH", "2026-10-30")
    assert out["available"] is False
    assert "symbol/field_key" in out["reason"]


def test_pit_filter_and_review_status() -> None:
    conn = _FakeConn(rows=ROWS)
    out = doc_layer.load_doc_extracts(conn, "600519.SH", "2026-10-30")
    assert out["available"] is True
    assert out["coverage"]["top5_customers"] == "have"
    assert out["coverage"]["volume_price_split"] == "pending"
    assert out["coverage"]["cost_structure"] == "have"
    assert out["coverage"]["guarantee"] == "have"
    assert out["fields"]["guarantee"]["items"][0]["reviewed"] is True
    assert out["coverage"]["contract_liabilities"] == "missing"
    top5 = out["fields"]["top5_customers"]["items"][0]
    assert top5["page_no"] == 38
    assert top5["doc_id"] == "doc-2025-annual"
    assert top5["pdf_sha256"] == "abc"
    assert top5["reviewed"] is True
    pending = out["fields"]["volume_price_split"]["items"][0]
    assert pending["reviewed"] is False

    query, params = next((s, p) for s, p in conn.sqls if "SELECT *" in s)
    assert "available_time::date <=" in query
    assert "available_time IS NOT NULL" in query
    assert params == ("600519.SH", "2026-10-30")


def test_null_available_time_is_ignored() -> None:
    row = dict(ROWS[0], available_time=None, review_status="approved")
    out = doc_layer.load_doc_extracts(_FakeConn(rows=[row]), "600519.SH", "2026-10-30")
    assert set(out["coverage"].values()) == {"missing"}
    assert out["fields"]["top5_customers"]["items"] == []


def test_document_payload_scopes_fields_by_dimension() -> None:
    facts = {
        "document_extracts": doc_layer.load_doc_extracts(_FakeConn(rows=ROWS), "600519.SH", "2026-10-30")["fields"],
        "document_coverage": doc_layer.load_doc_extracts(_FakeConn(rows=ROWS), "600519.SH", "2026-10-30")["coverage"],
        "document_extract_note": "note",
    }
    biz = doc_layer.document_payload(facts, "business_model")
    fin = doc_layer.document_payload(facts, "financial")
    equity = doc_layer.document_payload(facts, "valuation")
    assert set(biz["fields"]) == set(doc_layer.BUSINESS_DOC_FIELDS)
    assert set(fin["fields"]) == {"cost_structure", "contract_liabilities"}
    assert set(doc_layer.document_payload(facts, "governance")["fields"]) == set(doc_layer.GOVERNANCE_DOC_FIELDS)
    assert equity["fields"] == {}


def test_data_completeness_and_agent_payload_use_documents() -> None:
    docs = {"top5_customers": "have", "contract_liabilities": "have", "volume_price_split": "pending"}
    completeness = svc._data_completeness(
        ind={},
        peers=[],
        history={},
        fin=[],
        val={},
        debt={"advance_receipts": 0},
        documents=docs,
    )
    biz = completeness["business_model"]
    assert "前五大客户占比" not in biz["missing"]
    assert "合同负债/预收款" not in biz["missing"]
    assert any("前五大客户" in x and "已校验" in x for x in biz["have"])
    assert any("量价拆分" in x and "待复核" in x for x in biz["missing"])
    fin = completeness["financial"]
    assert any("合同负债/预收款" in x and "已校验" in x for x in fin["have"])
    assert "受限资金/租赁负债/合同负债（源数据为空，B 组补）" not in fin["missing"]

    facts = {
        "document_extracts": {
            key: {"label": label, "status": docs.get(key, "missing"), "items": []}
            for key, label in doc_layer.DOC_FIELDS.items()
        },
        "document_coverage": docs,
    }
    payload = svc._agent_payload(facts, "business_model")
    assert "document_extracts" in payload
    assert "前五大客户" in payload["business_model_note"]
    assert "待复核" in payload["business_model_note"]
    assert "document_extracts" not in svc._agent_payload(facts, "valuation")


def test_not_applicable_review_status_is_na_not_missing() -> None:
    row = dict(ROWS[0], review_status="not_applicable", value_text="不适用：公司无对外担保", field_key="guarantee")
    out = doc_layer.load_doc_extracts(_FakeConn(rows=[row]), "600519.SH", "2026-10-30")
    assert out["coverage"]["guarantee"] == "na"
    assert out["fields"]["guarantee"]["status"] == "na"
    item = out["fields"]["guarantee"]["items"][0]
    assert item["not_applicable"] is True
    assert item["reviewed"] is False
