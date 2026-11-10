# -*- coding: utf-8 -*-
"""机构端治理字段抽取（A 方案）：section_index + pagetext → 18 列 pending CSV/SQL。

只抽明确章节/表格；锚点不足就记 missing，不用泛化段落凑数。
数据业务负责 page_no/quote/pdf_sha256 校验与入库。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

SYMBOLS = (
    "000001.SZ",
    "000002.SZ",
    "000006.SZ",
    "000625.SZ",
    "001219.SZ",
    "001233.SZ",
)
FIELD_LABELS = {
    "controller_profile": "实控人/董事长履历",
    "board_structure": "董事会结构",
    "pledge_freeze": "质押冻结",
    "related_party": "关联交易与资金占用",
    "guarantee": "对外担保",
    "litigation_penalty": "处罚诉讼",
    "commitment_history": "承诺兑现记录",
    "dividend_financing": "分红/回购/融资历史",
}
# (必须命中的锚点组, 优先页特征, 抽取中心词)
RULES: dict[str, dict[str, Any]] = {
    "controller_profile": {
        "anchors": ("实际控制人", "控股股东"),
        "must": (("实际控制人", "控股股东"),),
        "prefer": ("实际控制人性质", "实际控制人姓名", "无实际控制人", "控股股东是", "控股股东为", "持股", "持有", "控制"),
        "center": ("实际控制人", "控股股东"),
        "confidence": 0.78,
    },
    "board_structure": {
        "anchors": ("董事会", "独立董事", "专门委员会", "名董事"),
        "must": (("董事会",), ("独立董事", "专门委员会", "名董事", "董事会成员")),
        "prefer": ("董事会由", "董事会成员", "独立董事", "专门委员会", "现任", "董事"),
        "center": ("董事会由", "董事会成员", "独立董事", "专门委员会"),
        "confidence": 0.72,
    },
    "pledge_freeze": {
        "anchors": ("质押", "冻结", "股份状态"),
        "must": (("质押", "冻结"),),
        "prefer": ("股东", "股份状态", "质押", "冻结"),
        "center": ("质押", "冻结", "股份状态"),
        "confidence": 0.68,
    },
    "related_party": {
        "anchors": ("关联交易",),
        "must": (("关联交易",), ("购销", "关联方", "资金占用", "日常关联交易", "采购商品")),
        "prefer": ("关联交易情况", "日常关联交易", "购销商品", "购销", "资金占用", "关联方"),
        "center": ("关联交易", "日常关联交易"),
        "confidence": 0.72,
    },
    "guarantee": {
        "anchors": ("对外担保",),
        "must": (("对外担保",),),
        "prefer": ("无违规对外担保", "不适用", "担保总额", "担保余额"),
        "center": ("对外担保",),
        "confidence": 0.72,
    },
    "litigation_penalty": {
        "anchors": ("重大诉讼", "处罚"),
        "must": (("重大诉讼", "处罚"),),
        "prefer": ("不适用", "无重大", "无对经营产生重大影响", "整改"),
        "center": ("重大诉讼", "处罚"),
        "confidence": 0.72,
    },
    "commitment_history": {
        "anchors": ("承诺事项履行", "承诺事项"),
        "must": (("承诺事项",),),
        "prefer": ("履行完毕", "尚未履行", "承诺方", "承诺背景"),
        "center": ("承诺事项履行", "承诺事项"),
        "confidence": 0.7,
    },
    "dividend_financing": {
        "anchors": ("利润分配", "现金红利", "每10股", "派发现金"),
        "must": (("利润分配",), ("每10股", "现金红利", "派发现金", "现金分红")),
        "prefer": ("每10股", "现金红利", "派发现金", "现金分红"),
        "center": ("每10股", "现金红利", "派发现金", "利润分配"),
        "confidence": 0.7,
    },
}
TABLE_HEAVY = {"board_structure", "pledge_freeze", "related_party"}
# 通用锚点对少数版式仍会命中相邻章节；这几页已人工核对，固定使用。
PAGE_OVERRIDES = {
    ("000001.SZ", "board_structure"): 65,
    ("000001.SZ", "related_party"): 95,
    ("000006.SZ", "pledge_freeze"): 49,
    ("001219.SZ", "controller_profile"): 56,
    ("001219.SZ", "board_structure"): 26,
}


def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def has_all(text: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    return all(any(word in text for word in group) for group in groups)


def score_page(text: str, rule: dict[str, Any], section: str) -> int:
    if not has_all(text, rule["must"]):
        return -1
    score = sum(1 for word in rule["anchors"] if word in text)
    score += 2 * sum(1 for word in rule["prefer"] if word in text)
    if section == "guarantee" and "对外担保" in text and ("听取" in text or "汇报" in text):
        score -= 3
    if section == "related_party":
        if "关联交易" in text and ("控制委员会" in text or "关联交易控" in text) and not any(
            word in text for word in ("购销", "关联方", "资金占用", "日常关联交易", "采购商品")
        ):
            score -= 5
        if "关联交易" in text and "尽量减少" in text and "承诺" in text:
            score -= 3
    if section in {"controller_profile", "board_structure", "related_party"} and (
        "承诺事项履行" in text or "承诺方" in text
    ):
        score -= 6
    if section == "controller_profile" and (
        "股东数量及持股情况" in text
        and not any(word in text for word in ("实际控制人性质", "实际控制人姓名", "无实际控制人", "控股股东是"))
    ):
        score -= 3
    if section == "board_structure":
        if "公司治理" in text and "董事会由" not in text and "名董事" not in text:
            score -= 2
        if any(word in text for word in ("工作细则", "议事规则", "治理制度")):
            score -= 2
        if any(word in text for word in ("薪酬由", "报酬为", "薪酬总额", "报酬总额")):
            score -= 5
        if any(word in text for word in ("衍生品", "优先股", "募集资金", "保证金")):
            score -= 5
    return score

def pick_page(
    symbol: str,
    doc_id: str,
    section: str,
    rule: dict[str, Any],
    index: pd.DataFrame,
    pages: pd.DataFrame,
    *,
    use_overrides: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()
    # 调用方传入 doc_id，避免同 symbol 的 2023/2024 年报页面串入 2025 结果。
    idx_rows = index[
        (index["symbol"] == symbol)
        & (index["section"] == section)
        & (index["doc_id"].astype(str) == doc_id)
    ]
    for _, row in idx_rows.iterrows():
        seen.add(int(row["page_no"]))
    all_pages = pages[(pages["symbol"] == symbol) & (pages["doc_id"].astype(str) == doc_id)]
    for _, row in all_pages.iterrows():
        page_no = int(row["page_no"])
        text = norm(row["text"])
        score = score_page(text, rule, section)
        if score < 0:
            continue
        candidates.append(
            {"page_no": page_no, "text": text, "doc_id": row["doc_id"], "score": score}
        )
    override = PAGE_OVERRIDES.get((symbol, section)) if use_overrides else None
    if override is not None:
        for row in all_pages.itertuples(index=False):
            if int(row.page_no) == int(override):
                return {
                    "page_no": int(row.page_no),
                    "text": norm(row.text),
                    "doc_id": row.doc_id,
                    "score": 99,
                }, "ok"
    if not candidates:
        return None, "未命中明确章节锚点"
    candidates.sort(key=lambda x: (-x["score"], x["page_no"]))
    best = candidates[0]
    if best["score"] < 3:
        return None, f"锚点不足（最高分 {best['score']}）"
    return best, "ok"


def extract_snippet(text: str, rule: dict[str, Any], limit: int = 900) -> tuple[str, str]:
    positions = [text.find(word) for word in rule["center"] if text.find(word) >= 0]
    if not positions:
        positions = [text.find(word) for word in rule["anchors"] if text.find(word) >= 0]
    pos = min(positions) if positions else 0
    start = max(0, pos - 80)
    snippet = text[start : start + limit].strip()
    return snippet, snippet


def available_time(row: dict[str, Any]) -> str:
    raw = row.get("available_time")
    if raw and str(raw) != "NaT":
        return str(raw)
    announce = row.get("announce_time")
    if announce and str(announce) != "NaT":
        return (pd.Timestamp(announce) + timedelta(days=1)).isoformat()
    return ""


def sql_literal(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def sql_row(row: dict[str, Any]) -> str:
    cols = list(row.keys())
    vals = []
    for col in cols:
        value = row[col]
        if col == "available_time" and value:
            vals.append(f"{sql_literal(value)}::timestamptz")
        else:
            vals.append(sql_literal(value))
    return f"INSERT INTO svquant.doc_extract ({', '.join(cols)}) VALUES ({', '.join(vals)});"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--pagetext", required=True)
    parser.add_argument("--section-index", required=True)
    parser.add_argument("--out-dir", default="backend/output/inst_gov_extract")
    parser.add_argument("--symbols", default=",".join(SYMBOLS))
    args = parser.parse_args()

    catalog = pd.read_parquet(args.catalog).dropna(subset=["doc_id"])
    catalog = catalog[catalog["report_period"].astype(str).str.startswith("2025")]
    pages = pd.read_parquet(args.pagetext)
    index = pd.read_parquet(args.section_index)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {"rows": 0, "missing": [], "docs": {}}

    for symbol in symbols:
        docs = catalog[catalog["symbol"] == symbol]
        if docs.empty:
            report["missing"].append({"symbol": symbol, "section": "*", "reason": "无 2025 年报"})
            continue
        doc = docs.iloc[0].to_dict()
        report["docs"][symbol] = {"doc_id": doc["doc_id"], "fields": {}}
        for section, label in FIELD_LABELS.items():
            rule = RULES[section]
            best, reason = pick_page(symbol, str(doc["doc_id"]), section, rule, index, pages)
            if not best:
                report["missing"].append({"symbol": symbol, "section": section, "reason": reason})
                report["docs"][symbol]["fields"][section] = {"status": "missing", "reason": reason}
                continue
            value_text, quote = extract_snippet(best["text"], rule)
            if len(quote) < 30:
                report["missing"].append({"symbol": symbol, "section": section, "reason": "命中文本过短"})
                report["docs"][symbol]["fields"][section] = {"status": "missing", "reason": "命中文本过短"}
                continue
            row = {
                "symbol": symbol,
                "field_key": section,
                "field_label": label,
                "value_text": value_text[:1000],
                "value_num": None,
                "unit": None,
                "report_period": "2025-12-31",
                "page_no": int(best["page_no"]),
                "quote": quote[:1200],
                "doc_id": doc["doc_id"],
                "pdf_sha256": doc.get("sha256"),
                "source_url": doc.get("pdf_url"),
                "available_time": available_time(doc),
                "extractor_version": "gov-section-v0.1",
                "confidence": rule["confidence"],
                "review_status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
            }
            rows.append(row)
            report["docs"][symbol]["fields"][section] = {
                "status": "ok",
                "page_no": int(best["page_no"]),
                "score": best["score"],
            }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "gov_extract_pending.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    sql_path = out_dir / "gov_extract_pending.sql"
    with sql_path.open("w", encoding="utf-8") as fh:
        fh.write("-- 治理字段抽取，review_status=pending；数据业务校验后入库\n")
        for row in rows:
            fh.write(sql_row(row) + "\n")
    report["rows"] = len(rows)
    report_path = out_dir / "gov_extract_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"rows={len(rows)} missing={len(report['missing'])}")
    print(csv_path)
    print(sql_path)
    print(report_path)


if __name__ == "__main__":
    main()
