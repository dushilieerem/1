# -*- coding: utf-8 -*-
"""机构端经营五字段抽取（本地 parquet → CSV + 回写 SQL）。

只读数据业务交付的 catalog/page_text parquet，不连生产库、不写 doc_extract。
产出 review_status=pending，人工抽检后再改 approved。

用法：
  python scripts/ops/extract_inst_doc_fields.py \
    --catalog /data/.../catalog.parquet \
    --pagetext /data/.../pagetext.parquet \
    --out-dir backend/output/inst_doc_extract_2025
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

FIELD_LABELS = {
    "top5_customers": "前五大客户及占比",
    "volume_price_split": "量价拆分",
    "cost_structure": "成本结构",
    "contract_liabilities": "合同负债",
    "channel_data": "渠道与销售模式",
}
FIELD_ORDER = list(FIELD_LABELS)
EXTRACTOR_VERSION = "inst-doc-extract-v0.1"
REPORT_PERIOD = "2025-12-31"

# 银行/地产等不适用标准工业口径的字段，明确标注而不是硬抽。
NOT_APPLICABLE = {
    ("000001.SZ", "top5_customers"): "银行不披露销售客户集中度",
    ("000001.SZ", "volume_price_split"): "银行无量价/产销口径",
    ("000001.SZ", "cost_structure"): "银行无营业成本构成",
    ("000001.SZ", "channel_data"): "银行无经销/直销渠道口径",
    ("000002.SZ", "top5_customers"): "地产年报无前五名客户销售占比表述",
    ("000002.SZ", "cost_structure"): "地产年报无营业成本构成表",
    ("000002.SZ", "channel_data"): "地产无经销/直销渠道口径",
}


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _year(doc: dict[str, Any]) -> tuple[str, str]:
    year = str(doc.get("report_period") or "")[:4]
    if not year.isdigit():
        year = REPORT_PERIOD[:4]
    prior = str(int(year) - 1)
    return year, prior


def _num(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return None


def _quote(text: str, start: int, word: str, width: int = 260) -> str:
    left = max(0, start - 60)
    snippet = text[left : start + width]
    return snippet.strip()


def _available_time(row: dict[str, Any]) -> str:
    raw = row.get("available_time")
    if raw and str(raw) != "NaT":
        return str(raw)
    announce = row.get("announce_time")
    if announce and str(announce) != "NaT":
        return (pd.Timestamp(announce) + timedelta(days=1)).isoformat()
    return ""


def _row(
    *,
    doc: dict[str, Any],
    field_key: str,
    page_no: int,
    quote: str,
    value_text: str,
    value_num: float | None = None,
    unit: str | None = None,
    confidence: float,
) -> dict[str, Any]:
    return {
        "symbol": doc["symbol"],
        "field_key": field_key,
        "field_label": FIELD_LABELS[field_key],
        "value_text": value_text[:500],
        "value_num": value_num,
        "unit": unit,
        "report_period": doc["report_period"],
        "page_no": int(page_no),
        "quote": quote[:800],
        "doc_id": doc["doc_id"],
        "pdf_sha256": doc.get("sha256"),
        "source_url": doc.get("pdf_url"),
        "available_time": _available_time(doc),
        "extractor_version": EXTRACTOR_VERSION,
        "confidence": round(confidence, 2),
        "review_status": "pending",
    }


def extract_top5(doc: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[dict | None, str]:
    for pg in pages:
        t = _norm(pg["text"])
        m = re.search(
            r"前五名客户销售额([\d,]+\.?\d*)\s*万元[^%]{0,50}?占年度销售总额\s*([\d.]+)%",
            t,
        )
        if m:
            pct = _num(m.group(2))
            return (
                _row(
                    doc=doc,
                    field_key="top5_customers",
                    page_no=pg["page_no"],
                    quote=_quote(t, m.start(), "前五名客户"),
                    value_text=f"前五名客户销售额 {m.group(1)} 万元，占年度销售总额 {pct}%",
                    value_num=pct,
                    unit="%",
                    confidence=0.9,
                ),
                "ok",
            )
        m = re.search(r"前五名客户合计销售金额占年度销售总额比例\s*([\d.]+)%", t)
        if m:
            pct = _num(m.group(1))
            amount = re.search(r"前五名客户合计销售金额（元）\s*([\d,]+\.?\d*)", t)
            amount_text = f"前五名客户合计销售金额 {amount.group(1)} 元，" if amount else ""
            return (
                _row(
                    doc=doc,
                    field_key="top5_customers",
                    page_no=pg["page_no"],
                    quote=_quote(t, m.start(), "前五名客户"),
                    value_text=f"{amount_text}占年度销售总额 {pct}%",
                    value_num=pct,
                    unit="%",
                    confidence=0.9,
                ),
                "ok",
            )
    return None, NOT_APPLICABLE.get((doc["symbol"], "top5_customers"), "未找到前五名客户销售占比")


def extract_volume_price(doc: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[dict | None, str]:
    symbol = doc["symbol"]
    year, _ = _year(doc)
    for pg in pages:
        t = _norm(pg["text"])
        if "销售量" not in t and "销售面积" not in t:
            continue
        m = None
        value_text = None
        value_num = None
        unit = None
        if symbol == "600519.SH":
            m = re.search(
                r"酒类\s+吨\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)",
                t,
            )
            if m:
                value_text = (
                    f"{year} 年酒类：生产量 {m.group(1)} 吨，销售量 {m.group(2)} 吨，"
                    f"库存量 {m.group(3)} 吨；销量同比 {m.group(5)}%"
                )
                value_num, unit = _num(m.group(2)), "吨"
        elif symbol == "001219.SZ":
            m = re.search(
                r"合计\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+"
                r"(-?[\d.]+)%\s+(-?[\d.]+)%\s+(-?[\d.]+)%",
                t,
            )
            if m:
                value_text = (
                    f"{year} 年合计：生产量 {m.group(1)}，销售量 {m.group(2)}，库存量 {m.group(3)}；"
                    f"销量同比 {m.group(8)}%"
                )
                value_num = _num(m.group(2))
        elif symbol == "000625.SZ":
            m = re.search(
                r"合计\s+([\d,]+)\s+([\d,]+)\s+(-?[\d.]+)%\s+([\d,]+)\s+([\d,]+)\s+(-?[\d.]+)%",
                t,
            )
            if m:
                value_text = (
                    f"{year} 年整车：产量 {m.group(1)} 辆（同比 {m.group(3)}%），"
                    f"销量 {m.group(4)} 辆（同比 {m.group(6)}%）"
                )
                value_num, unit = _num(m.group(4)), "辆"
        elif symbol == "001233.SZ":
            m = re.search(
                r"销售量\s+条\s+([\d,]+)\s+([\d,]+)\s+(-?[\d.]+)%\s+"
                r"生产量\s+条\s+([\d,]+)\s+([\d,]+)\s+(-?[\d.]+)%",
                t,
            )
            if m:
                value_text = (
                    f"{year} 年全钢巨胎：销售量 {m.group(1)} 条（同比 {m.group(3)}%），"
                    f"生产量 {m.group(4)} 条（同比 {m.group(6)}%）"
                )
                value_num, unit = _num(m.group(1)), "条"
        elif symbol == "000002.SZ":
            m = re.search(
                r"销售面积([\d,.]+)\s*万平方米[，,]\s*销售金额([\d,.]+)\s*亿元[^。]{0,30}?"
                r"同比分别(下降|增长)\s*([\d.]+)%和([\d.]+)%",
                t,
            )
            if m:
                value_text = (
                    f"{year} 年销售面积 {m.group(1)} 万平方米（同比{m.group(3)} {m.group(4)}%），"
                    f"销售金额 {m.group(2)} 亿元（同比{m.group(3)} {m.group(5)}%）"
                )
                value_num, unit = _num(m.group(1)), "万平方米"
        if not m:
            # 通用：年报“实物销售收入”表，如“销售量 万件 4,680.68 4,005.22 16.86%”。
            m = re.search(
                r"销售量\s*(?:([一-龥/]+)\s*)?"
                r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+(-?[\d.]+)%",
                t,
            )
            if m:
                unit = m.group(1) or ""
                if unit in {"元", "万元", "亿元"}:
                    m = None
                    continue
                value_text = (
                    f"{year} 年销售量 {m.group(2)} {unit}"
                    f"（同比 {m.group(4)}%，上年 {m.group(3)} {unit}）"
                ).strip()
                value_num = _num(m.group(2))
        if not m:
            # 通用：地产口径“销售面积 X 万平方米，销售金额 Y 亿元”。
            m = re.search(
                r"销售面积\s*([\d,.]+)\s*(万)?平方米[，,]\s*(?:签约)?销售金额\s*([\d,.]+)\s*亿元",
                t,
            )
            if m:
                unit = f"{m.group(2) or ''}平方米"
                value_text = (
                    f"{year} 年销售面积 {m.group(1)} {unit}，销售金额 {m.group(3)} 亿元"
                )
                value_num = _num(m.group(1))
        if m:
            return (
                _row(
                    doc=doc,
                    field_key="volume_price_split",
                    page_no=pg["page_no"],
                    quote=_quote(t, m.start(), "销售量"),
                    value_text=value_text or "",
                    value_num=value_num,
                    unit=unit,
                    confidence=0.75 if symbol in {"600519.SH", "001219.SZ", "000625.SZ", "001233.SZ", "000002.SZ"} else 0.68,
                ),
                "ok",
            )
    return None, NOT_APPLICABLE.get((doc["symbol"], "volume_price_split"), "未找到产销量/量价表")


def extract_cost_structure(doc: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[dict | None, str]:
    for pg in pages:
        t = _norm(pg["text"])
        idx = t.find("营业成本构成")
        if idx < 0:
            continue
        snippet = t[idx : idx + 700]
        cut = re.search(r"公司主要销售客户|前五名客户|主要销售客户和主要供应商", snippet)
        if cut:
            snippet = snippet[: cut.start()]
        snippet = snippet.strip()
        if len(snippet) < 40:
            continue
        return (
            _row(
                doc=doc,
                field_key="cost_structure",
                page_no=pg["page_no"],
                quote=snippet[:800],
                value_text=snippet[:480],
                confidence=0.65,
            ),
            "ok",
        )
    return None, NOT_APPLICABLE.get((doc["symbol"], "cost_structure"), "年报无营业成本构成表")


def _unit_of(text: str) -> str:
    if "单位：万元" in text or "单位:万元" in text:
        return "万元"
    if "人民币百万元" in text or "单位：百万元" in text or "单位:百万元" in text:
        return "百万元"
    if "单位：元" in text or "单位:元" in text:
        return "元"
    return "元"


def extract_contract_liabilities(doc: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[dict | None, str]:
    year, prior_year = _year(doc)
    best: tuple[int, dict[str, Any], str, str, str] | None = None
    ref = r"(?:[（(][^)）]{1,12}[)）]|[一二三四五六七八九十百]+[、.．]\d{1,3}|\d{1,3}\s+)?"
    line_re = re.compile(
        rf"合同负债\s*{ref}\s*([\d,]{{3,}}(?:\.\d+)?)\s+(?:[\d.]+%\s+)?([\d,]{{3,}}(?:\.\d+)?)"
    )
    for pg in pages:
        t = _norm(pg["text"])
        if "合同负债" not in t:
            continue
        unit = _unit_of(t)
        # 优先取“合同负债情况”附注的合计：合并口径、期末/期初二列。
        note_idx = t.find("合同负债")
        note_heading = "合同负债情况" in t or bool(re.search(r"\d{1,3}、\s*合同负债", t))
        if note_heading:
            tail = t[note_idx : note_idx + 1200]
            total = re.search(r"合计\s*([\d,]{3,}(?:\.\d+)?)\s+([\d,]{3,}(?:\.\d+)?)", tail)
            if total:
                candidate = (10, pg, total.group(1), total.group(2), unit)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        for m in line_re.finditer(t):
            amount = _num(m.group(1))
            if amount is None or amount < 100:
                continue
            score = 1
            if "合并资产负债表" in t:
                score += 4
            if "母公司资产负债表" in t:
                score -= 3
            if "负债合计" in t:
                score += 1
            if (
                "期末余额" in t
                or f"{year} 年末" in t
                or "本年年末" in t
                or f"{year}年12月31日" in t
            ):
                score += 1
            if "审计" in t or "会计政策" in t:
                score -= 2
            candidate = (score, pg, m.group(1), m.group(2), unit)
            if best is None or candidate[0] > best[0]:
                best = candidate
    if not best:
        return None, "未找到合同负债金额"
    _, pg, amount_text, prior_text, unit = best
    t = _norm(pg["text"])
    amount = _num(amount_text)
    prior = _num(prior_text)
    return (
        _row(
            doc=doc,
            field_key="contract_liabilities",
            page_no=pg["page_no"],
            quote=_quote(t, t.find("合同负债"), "合同负债"),
            value_text=(
                f"{year} 年末合同负债 {amount_text} {unit}"
                + (f"，{prior_year} 年末 {prior_text} {unit}" if prior is not None else "")
            ),
            value_num=amount,
            unit=unit,
            confidence=0.8 if best[0] >= 10 else 0.78,
        ),
        "ok",
    )


def extract_channel(doc: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[dict | None, str]:
    for pg in pages:
        t = _norm(pg["text"])
        if "销售模式" not in t:
            continue
        m = re.search(r"(?:主要销售模式|销售模式为)[：:]?.{0,320}", t)
        if m and re.search(r"直销|经销|直营|批发|代理", m.group(0)):
            return (
                _row(
                    doc=doc,
                    field_key="channel_data",
                    page_no=pg["page_no"],
                    quote=m.group(0)[:600],
                    value_text=m.group(0)[:420],
                    confidence=0.72,
                ),
                "ok",
            )
        m = re.search(r"分销售模式.{0,360}", t)
        if m and re.search(r"直销|经销|直营|批发|代理|渠道", m.group(0)):
            return (
                _row(
                    doc=doc,
                    field_key="channel_data",
                    page_no=pg["page_no"],
                    quote=m.group(0)[:600],
                    value_text=m.group(0)[:420],
                    confidence=0.6,
                ),
                "ok",
            )
    return None, NOT_APPLICABLE.get((doc["symbol"], "channel_data"), "未找到渠道/销售模式描述")


EXTRACTORS = {
    "top5_customers": extract_top5,
    "volume_price_split": extract_volume_price,
    "cost_structure": extract_cost_structure,
    "contract_liabilities": extract_contract_liabilities,
    "channel_data": extract_channel,
}


def _sql_literal(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _sql_row(row: dict[str, Any]) -> str:
    cols = [
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
    ]
    values = []
    for col in cols:
        value = row.get(col)
        if col == "available_time" and value:
            values.append(f"{_sql_literal(value)}::timestamptz")
        else:
            values.append(_sql_literal(value))
    return f"INSERT INTO svquant.doc_extract ({', '.join(cols)}) VALUES ({', '.join(values)});"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--pagetext", required=True)
    parser.add_argument("--out-dir", default="backend/output/inst_doc_extract_2025")
    parser.add_argument(
        "--report-period",
        default=REPORT_PERIOD,
        help="报告期前缀，如 2025；传 all/* 处理 catalog 中所有报告期",
    )
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    catalog = pd.read_parquet(args.catalog).dropna(subset=["doc_id"])
    pages_df = pd.read_parquet(args.pagetext)
    # 全A 页文本有上百万行，逐份过滤会退化成 O(文档数×页数)；按 doc_id 分组一次。
    pages_by_doc = {
        str(doc_id): group.sort_values("page_no").to_dict("records")
        for doc_id, group in pages_df.groupby("doc_id", sort=False)
    }
    period = str(args.report_period or "").strip().lower()
    if period not in {"", "all", "*"}:
        catalog = catalog[catalog["report_period"].astype(str).str.startswith(args.report_period[:4])]
    wanted = {s.strip() for s in args.symbols.split(",") if s.strip()}
    if wanted:
        catalog = catalog[catalog["symbol"].isin(wanted)]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {"period": args.report_period, "docs": [], "missing": []}

    for doc in catalog.to_dict("records"):
        doc_pages = pages_by_doc.get(str(doc["doc_id"]), [])
        doc_report = {
            "symbol": doc["symbol"],
            "doc_id": doc["doc_id"],
            "pages": len(doc_pages),
            "fields": {},
        }
        for key, extractor in EXTRACTORS.items():
            row, reason = extractor(doc, doc_pages)
            if row:
                rows.append(row)
                doc_report["fields"][key] = {"status": "ok", "page_no": row["page_no"]}
            else:
                doc_report["fields"][key] = {"status": "missing", "reason": reason}
                report["missing"].append(
                    {"symbol": doc["symbol"], "field_key": key, "reason": reason}
                )
        report["docs"].append(doc_report)

    rows.sort(key=lambda r: (r["symbol"], FIELD_ORDER.index(r["field_key"])))
    period_label = "all" if period in {"", "all", "*"} else args.report_period
    csv_path = out_dir / f"doc_extract_{period_label}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    sql_path = out_dir / f"doc_extract_{period_label}.sql"
    with sql_path.open("w", encoding="utf-8") as fh:
        fh.write(f"-- 机构端 {period_label} 五字段抽取，review_status=pending，复核后再改 approved\n")
        fh.write("-- 执行前确认 doc_extract 表已建、available_time 为公告日+1 天\n")
        for row in rows:
            fh.write(_sql_row(row) + "\n")

    report_path = out_dir / f"doc_extract_{period_label}_report.json"
    report["extracted"] = len(rows)
    report["missing_count"] = len(report["missing"])
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"docs={len(report['docs'])} rows={len(rows)} missing={len(report['missing'])}")
    print(f"csv={csv_path}")
    print(f"sql={sql_path}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
