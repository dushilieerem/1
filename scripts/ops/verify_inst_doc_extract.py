# -*- coding: utf-8 -*-
"""程序校验 doc_extract 抽取行，把可回溯的原文摘录标为 auto_verified。

auto_verified 只表示：字段锚点命中、原文长度达标、doc_id/page_no/quote/
available_time/来源 URL 完整且置信度达到该字段门槛。它不等同于人工复核，
doc_layer 把它计入正式证据，但 reviewed_by 会保留 auto-qa-v1 便于区分。

默认只允许测试/开发库；生产必须显式 --allow-production。
"""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlsplit

import psycopg

# 字段 -> (最低置信度, 原文最短长度, 必须命中的锚点之一)
# 质押冻结、董事会结构、分红融资的页面命中不稳定，暂不自动校验，保留 pending。
FIELD_QA: dict[str, tuple[float, int, tuple[str, ...]]] = {
    "top5_customers": (0.70, 30, ("前五名客户", "前5名客户", "前五大客户")),
    "volume_price_split": (0.65, 40, ("销售面积", "销售金额", "销售量", "销量")),
    "cost_structure": (0.60, 40, ("营业成本构成", "成本构成", "营业成本")),
    "contract_liabilities": (0.70, 30, ("合同负债",)),
    "channel_data": (0.60, 40, ("销售模式", "直销", "经销", "渠道")),
    "controller_profile": (0.70, 80, ("控股股东", "实际控制人")),
    "related_party": (0.65, 60, ("关联交易", "关联方")),
    "guarantee": (0.65, 60, ("对外担保", "担保")),
    "litigation_penalty": (0.65, 60, ("诉讼", "仲裁", "处罚", "监管")),
    "commitment_history": (0.65, 60, ("承诺",)),
    "mgmt_change": (0.60, 60, ("辞职", "聘任", "离任", "换届", "选举", "高级管理人员")),
    "inquiry_letter": (0.70, 60, ("问询函", "关注函", "监管函", "审核意见函")),
}

BASE_SQL = """
    FROM svquant.doc_extract
    WHERE field_key = %s
      AND review_status = 'pending'
      AND doc_id IS NOT NULL AND doc_id <> ''
      AND page_no IS NOT NULL AND page_no > 0
      AND quote IS NOT NULL AND char_length(quote) >= %s
      AND value_text IS NOT NULL AND char_length(value_text) >= 4
      AND available_time IS NOT NULL
      AND source_url IS NOT NULL AND source_url <> ''
      AND pdf_sha256 IS NOT NULL AND pdf_sha256 <> ''
      AND confidence IS NOT NULL AND confidence >= %s
      AND ({clause})
"""


def _db_name(dsn: str) -> str:
    return urlsplit(dsn).path.lstrip("/")


def _where(field: str) -> tuple[str, list[object]]:
    confidence, quote_len, anchors = FIELD_QA[field]
    likes = [f"%{anchor}%" for anchor in anchors]
    clause = " OR ".join(["quote LIKE %s"] * len(likes))
    sql = BASE_SQL.format(clause=clause)
    return sql, [field, quote_len, confidence, *likes]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--field", action="append", default=[])
    args = parser.parse_args()

    dsn = str(args.dsn or "").strip()
    if not dsn:
        raise SystemExit("missing DATABASE_URL or --dsn")
    name = _db_name(dsn)
    safe = name.endswith("_test") or name.endswith("_dev") or name.endswith("_ci") or name == "svquant_test"
    if not safe and not args.allow_production:
        raise SystemExit(f"refusing to write non-test database: {name}")

    fields = [f for f in args.field if f in FIELD_QA] or list(FIELD_QA)
    total = 0
    with psycopg.connect(dsn) as conn:
        for field in fields:
            where, params = _where(field)
            ready = conn.execute(f"SELECT COUNT(*) {where}", tuple(params)).fetchone()[0]
            print(f"{field}: eligible={ready}")
            if ready and not args.dry_run:
                updated = conn.execute(
                    "UPDATE svquant.doc_extract SET review_status='auto_verified', "
                    "reviewed_by='auto-qa-v1', reviewed_at=now() "
                    f"WHERE (doc_id, field_key) IN (SELECT doc_id, field_key {where})",
                    tuple(params),
                ).rowcount
                total += updated or 0
                print(f"{field}: auto_verified={updated}")
        if not args.dry_run:
            conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM svquant.doc_extract WHERE review_status='pending'"
        ).fetchone()[0]
        print(f"db={name} auto_verified_this_run={total} pending_remaining={remaining}")


if __name__ == "__main__":
    main()
