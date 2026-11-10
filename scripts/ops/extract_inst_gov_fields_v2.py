# -*- coding: utf-8 -*-
"""机构端治理字段抽取 v2：B1 年报 + B1b 公告/问询/招股书页文本。

- 年报覆盖：controller_profile、board_structure、commitment_history、dividend_financing
- 公告覆盖：pledge_freeze、guarantee、related_party、litigation_penalty、mgmt_change
- 输出 18 列 pending CSV/SQL，复核后由机构端回写 doc_extract。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_inst_gov_fields import (  # noqa: E402
    FIELD_LABELS,
    RULES,
    available_time,
    extract_snippet,
    pick_page,
    sql_row,
)

ANNUAL_FIELDS = (
    "controller_profile",
    "board_structure",
    "commitment_history",
    "dividend_financing",
)
ANNOUNCEMENT_FIELDS = (
    "pledge_freeze",
    "guarantee",
    "related_party",
    "litigation_penalty",
    "mgmt_change",
)
MGMT_TITLE_WORDS = (
    "辞职",
    "聘任",
    "离任",
    "换届",
    "选举",
    "变动",
    "高级管理人员",
    "总裁",
    "总经理",
    "财务总监",
    "董事会秘书",
)

RULES_V2: dict[str, dict[str, Any]] = dict(RULES)
RULES_V2["litigation_penalty"] = {
    "anchors": ("诉讼", "仲裁", "处罚", "监管措施", "警示函", "立案"),
    "must": (("诉讼", "仲裁", "处罚", "监管措施", "警示函", "立案"),),
    "prefer": ("涉案金额", "诉讼请求", "判决", "处罚决定", "罚款", "整改", "进展"),
    "center": ("诉讼", "仲裁", "处罚", "监管措施", "警示函", "立案"),
    "confidence": 0.68,
}
RULES_V2["mgmt_change"] = {
    "anchors": ("辞职", "聘任", "离任", "换届", "选举", "高级管理人员", "董事"),
    "must": (("辞职", "聘任", "离任", "换届", "选举", "高级管理人员", "董事"),),
    "prefer": ("辞职", "聘任", "离任", "换届", "选举", "高级管理人员", "工作变动"),
    "center": ("辞职", "聘任", "离任", "换届", "选举", "高级管理人员"),
    "confidence": 0.65,
}
LABELS = {**FIELD_LABELS, "mgmt_change": "高管变动"}


def _period(value: Any) -> str:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return date.today().isoformat()


def _announce_date(doc: dict[str, Any]) -> str:
    for key in ("announce_time", "available_time"):
        text = str(doc.get(key) or "")[:10]
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            continue
    return date.today().isoformat()


def _base_row(doc: dict[str, Any], field: str, page: dict[str, Any], value_text: str, quote: str, confidence: float, period: str) -> dict[str, Any]:
    return {
        "symbol": doc["symbol"],
        "field_key": field,
        "field_label": LABELS.get(field, field),
        "value_text": str(value_text or "")[:1000],
        "value_num": None,
        "unit": None,
        "report_period": period,
        "page_no": int(page["page_no"]),
        "quote": str(quote or "")[:1200],
        "doc_id": doc["doc_id"],
        "pdf_sha256": doc.get("sha256"),
        "source_url": doc.get("pdf_url"),
        "available_time": available_time(doc),
        "extractor_version": "inst-gov-v2",
        "confidence": round(float(confidence), 2),
        "review_status": "pending",
        "reviewed_by": None,
        "reviewed_at": None,
    }


def _extract_doc(
    doc: dict[str, Any],
    fields: tuple[str, ...],
    pages: pd.DataFrame,
    index: pd.DataFrame,
    *,
    period: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    doc_pages = pages[pages["doc_id"].astype(str) == str(doc["doc_id"])].sort_values("page_no")
    for field in fields:
        rule = RULES_V2[field]
        page, reason = pick_page(
            str(doc["symbol"]),
            str(doc["doc_id"]),
            field,
            rule,
            index,
            doc_pages,
            use_overrides=False,
        )
        if not page:
            missing.append({"symbol": doc["symbol"], "doc_id": doc["doc_id"], "field_key": field, "reason": reason})
            continue
        value_text, quote = extract_snippet(page["text"], rule)
        if len(quote) < 30:
            missing.append({"symbol": doc["symbol"], "doc_id": doc["doc_id"], "field_key": field, "reason": "命中文本过短"})
            continue
        rows.append(_base_row(doc, field, page, value_text, quote, rule["confidence"], period))
    return rows, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annual-catalog", required=True)
    parser.add_argument("--annual-pagetext", required=True)
    parser.add_argument("--ann-catalog", required=True)
    parser.add_argument("--ann-pagetext", required=True)
    parser.add_argument("--section-index", default="")
    parser.add_argument("--out-dir", default="backend/output/inst_gov_extract_v2")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    annual = pd.read_parquet(args.annual_catalog).dropna(subset=["doc_id"])
    annual_pages = pd.read_parquet(args.annual_pagetext)
    ann = pd.read_parquet(args.ann_catalog).dropna(subset=["doc_id"])
    ann_pages = pd.read_parquet(args.ann_pagetext)
    index = (
        pd.read_parquet(args.section_index)
        if args.section_index
        else pd.DataFrame(columns=["symbol", "section", "doc_id", "page_no"])
    )
    wanted = {s.strip() for s in args.symbols.split(",") if s.strip()}
    if wanted:
        annual = annual[annual["symbol"].isin(wanted)]
        ann = ann[ann["symbol"].isin(wanted)]

    annual = annual[
        annual["doc_type"].astype(str).isin({"annual", "annual_report"})
        & annual["status"].astype(str).eq("ok")
    ]
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    report: dict[str, Any] = {"annual_docs": 0, "ann_docs": 0, "rows": 0, "missing": missing}

    for doc in annual.to_dict("records"):
        report["annual_docs"] += 1
        got, miss = _extract_doc(
            doc,
            ANNUAL_FIELDS,
            annual_pages,
            index,
            period=_period(doc.get("report_period")),
        )
        rows.extend(got)
        missing.extend(miss)

    for doc in ann.to_dict("records"):
        types = {x.strip() for x in str(doc.get("doc_types") or "").split(",") if x.strip()}
        fields = [f for f in ANNOUNCEMENT_FIELDS if f in types]
        title = str(doc.get("title") or "")
        if "board_mgmt" in types and any(word in title for word in MGMT_TITLE_WORDS):
            if "mgmt_change" not in fields:
                fields.append("mgmt_change")
        if not fields:
            continue
        report["ann_docs"] += 1
        got, miss = _extract_doc(
            doc,
            fields,
            ann_pages,
            index,
            period=_announce_date(doc),
        )
        rows.extend(got)
        missing.extend(miss)

    # 同一 (doc_id, field_key) 只保留一条，符合 doc_extract 主键。
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault((row["doc_id"], row["field_key"]), row)
    rows = list(deduped.values())
    rows.sort(key=lambda r: (r["symbol"], r["report_period"], r["field_key"]))
    report["rows"] = len(rows)
    report["missing_count"] = len(missing)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "gov_extract_v2_pending.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    sql_path = out_dir / "gov_extract_v2_pending.sql"
    with sql_path.open("w", encoding="utf-8") as fh:
        fh.write("-- 机构端治理字段 v2 抽取，review_status=pending，复核后再改 approved\n")
        for row in rows:
            fh.write(sql_row(row) + "\n")

    report_path = out_dir / "gov_extract_v2_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"annual_docs={report['annual_docs']} ann_docs={report['ann_docs']} rows={len(rows)} missing={len(missing)}")
    print(f"csv={csv_path}")
    print(f"sql={sql_path}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
