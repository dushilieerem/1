# -*- coding: utf-8 -*-
"""doc_extract 接入层：把年报/公告页级抽取结果接入六维 FactPack。

数据业务负责 doc_catalog / doc_page_text / doc_extract；本模块只读消费：
- 表缺失或字段不齐时返回空覆盖，不阻断研究生成；
- 严格按 available_time <= as_of 做 PIT；
- 每条结果保留 page_no / quote / doc_id / pdf_sha256，供证据回溯；
- 只有 review_status 为 approved/verified/reviewed 的结果视为正式证据；
  not_applicable 表示业务上不适用；pending 只作线索并在 FactPack 中标注。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

DOC_FIELDS: dict[str, str] = {
    "top5_customers": "前五大客户及占比",
    "volume_price_split": "量价拆分",
    "cost_structure": "成本结构",
    "contract_liabilities": "合同负债",
    "channel_data": "渠道与销售模式",
    "controller_profile": "实控人/董事长履历",
    "board_structure": "董事会结构",
    "pledge_freeze": "质押冻结",
    "related_party": "关联交易与资金占用",
    "guarantee": "对外担保",
    "litigation_penalty": "处罚诉讼",
    "commitment_history": "承诺兑现记录",
    "dividend_financing": "分红/回购/融资历史",
    "mgmt_change": "高管变动",
}

BUSINESS_DOC_FIELDS: tuple[str, ...] = (
    "top5_customers",
    "volume_price_split",
    "cost_structure",
    "contract_liabilities",
    "channel_data",
)
GOVERNANCE_DOC_FIELDS: tuple[str, ...] = (
    "controller_profile",
    "board_structure",
    "pledge_freeze",
    "related_party",
    "guarantee",
    "litigation_penalty",
    "commitment_history",
    "dividend_financing",
    "mgmt_change",
)
GOVERNANCE_CORE_FIELDS: tuple[str, ...] = (
    "controller_profile",
    "board_structure",
    "pledge_freeze",
    "related_party",
    "guarantee",
    "litigation_penalty",
)

DOC_DIM_MAP: dict[str, tuple[str, ...]] = {
    "business_model": BUSINESS_DOC_FIELDS,
    "financial": ("cost_structure", "contract_liabilities"),
    "governance": GOVERNANCE_DOC_FIELDS,
}

APPROVED_REVIEW_STATUSES = {"approved", "verified", "reviewed"}
NOT_APPLICABLE_REVIEW_STATUSES = {"not_applicable", "n/a", "na"}
TABLE_CANDIDATES = ("svquant.doc_extract", "doc_extract", "public.doc_extract")


def _table_name(conn) -> str | None:
    for name in TABLE_CANDIDATES:
        row = conn.execute("SELECT to_regclass(%s) AS t", (name,)).fetchone()
        if row and (row.get("t") if isinstance(row, dict) else row[0]):
            return name
    return None


def _columns(conn, table: str) -> set[str]:
    schema, _, name = table.partition(".")
    if not name:
        schema, name = "public", table
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s",
        (schema, name),
    ).fetchall()
    return {
        str((r.get("column_name") if isinstance(r, dict) else r[0]))
        for r in rows
    }


def _value(row: dict[str, Any]) -> Any:
    for key in ("value_num", "value_text", "value"):
        value = row.get(key)
        if value is not None and value != "":
            return float(value) if isinstance(value, Decimal) else value
    return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def empty_doc_extracts(reason: str = "doc_extract 表未建立") -> dict[str, Any]:
    return {
        "available": False,
        "table": None,
        "reason": reason,
        "fields": {
            key: {"label": label, "status": "missing", "items": []}
            for key, label in DOC_FIELDS.items()
        },
        "coverage": {k: "missing" for k in DOC_FIELDS},
    }


def load_doc_extracts(conn, symbol: str, as_of: Any) -> dict[str, Any]:
    """读取某标的在 as_of 前可见的 doc_extract 结果，按字段归一。"""
    table = _table_name(conn)
    if not table:
        return empty_doc_extracts("doc_extract 表未建立")
    columns = _columns(conn, table)
    required = {"symbol", "field_key", "available_time"}
    if not required <= columns:
        return empty_doc_extracts("doc_extract 缺少 symbol/field_key/available_time 字段")
    fields = {
        key: {"label": label, "status": "missing", "items": []}
        for key, label in DOC_FIELDS.items()
    }
    sql = (
        f"SELECT * FROM {table} WHERE symbol=%s "
        "AND available_time IS NOT NULL AND available_time::date <= %s "
        "ORDER BY available_time DESC"
    )
    params: list[Any] = [symbol, as_of if as_of else date.today().isoformat()]
    rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]

    by_field: dict[str, list[dict[str, Any]]] = {k: [] for k in DOC_FIELDS}
    for row in rows:
        if row.get("available_time") is None:
            continue
        key = str(row.get("field_key") or row.get("field") or "").strip()
        if key not in by_field:
            continue
        value = _value(row)
        if value is None:
            continue
        status = str(row.get("review_status") or "pending").lower()
        by_field[key].append(
            {
                "value": value,
                "unit": row.get("unit"),
                "report_period": row.get("report_period") or row.get("period"),
                "page_no": row.get("page_no") or row.get("page"),
                "quote": row.get("quote") or row.get("evidence_quote"),
                "doc_id": row.get("doc_id") or row.get("document_id"),
                "pdf_sha256": row.get("pdf_sha256") or row.get("sha256"),
                "source_url": row.get("source_url"),
                "available_time": _iso(row.get("available_time")),
                "confidence": float(row["confidence"]) if isinstance(row.get("confidence"), Decimal) else row.get("confidence"),
                "review_status": status,
                "reviewed": status in APPROVED_REVIEW_STATUSES,
                "not_applicable": status in NOT_APPLICABLE_REVIEW_STATUSES,
                "extractor_version": row.get("extractor_version"),
            }
        )

    coverage: dict[str, str] = {}
    for key, items in by_field.items():
        approved = [x for x in items if x["reviewed"]]
        na = [x for x in items if x["not_applicable"]]
        if approved:
            coverage[key] = "have"
            fields[key]["status"] = "have"
            fields[key]["items"] = approved[:3]
        elif na:
            coverage[key] = "na"
            fields[key]["status"] = "na"
            fields[key]["items"] = na[:3]
        elif items:
            coverage[key] = "pending"
            fields[key]["status"] = "pending"
            fields[key]["items"] = items[:3]
        else:
            coverage[key] = "missing"
    return {
        "available": True,
        "table": table,
        "reason": None,
        "fields": fields,
        "coverage": coverage,
        "note": (
            "doc_extract 来自年报/公告页级抽取；引用时必须带 doc_id、page_no、quote 与 available_time；"
            "review_status 未通过的结果只作线索，不进入正式结论；not_applicable 表示业务上不适用，不计入数据缺口。"
        ),
    }


def document_payload(facts: dict[str, Any], dim_key: str) -> dict[str, Any]:
    """给某个六维 Agent 的文档字段子集。"""
    keys = DOC_DIM_MAP.get(dim_key, ())
    source = (facts.get("document_extracts") or {})
    coverage = (facts.get("document_coverage") or {})
    return {
        "fields": {k: source[k] for k in keys if k in source},
        "coverage": {k: coverage.get(k, "missing") for k in keys},
        "note": facts.get("document_extract_note"),
    }
