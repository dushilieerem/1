# -*- coding: utf-8 -*-
"""财务三表/指标 + 公告日点时（P1-D01）。

设计原则：
- **公告日点时**：查询默认只返回 `announce_date <= as_of` 的最新一期，
  避免用未来才披露的财报做回测（look-ahead）。
- 数据来源为外部 release（CSV/Parquet 导出），本模块负责装载、校验与查询；
  不臆造财务数字。
- 表结构按 statement_type 区分 income / balance / cashflow / indicator，
  指标字段以 JSONB 保存，字段字典见 `FIELD_DICT`。
"""
from __future__ import annotations

import csv
import json
from datetime import date
from typing import Any, Iterable

from services.core.db import get_conn

STATEMENT_TYPES = ("income", "balance", "cashflow", "indicator")

# 常用字段字典（iFinD 口径中文名；实际来源字段可在数据里扩展）
FIELD_DICT: dict[str, dict[str, str]] = {
    "income": {
        "total_revenue": "营业总收入",
        "revenue": "营业收入",
        "operating_cost": "营业成本",
        "gross_profit": "毛利",
        "operating_profit": "营业利润",
        "net_profit": "净利润",
        "net_profit_attr_parent": "归母净利润",
        "eps": "基本每股收益",
    },
    "balance": {
        "total_assets": "资产总计",
        "total_liabilities": "负债合计",
        "total_equity": "所有者权益合计",
        "current_assets": "流动资产合计",
        "current_liabilities": "流动负债合计",
        "inventory": "存货",
        "receivables": "应收账款",
        "cash": "货币资金",
    },
    "cashflow": {
        "operating_cash_flow": "经营活动现金流净额",
        "investing_cash_flow": "投资活动现金流净额",
        "financing_cash_flow": "筹资活动现金流净额",
        "capex": "购建固定资产等支付的现金",
    },
    "indicator": {
        "roe": "净资产收益率",
        "roa": "总资产收益率",
        "gross_margin": "毛利率",
        "net_margin": "净利率",
        "debt_ratio": "资产负债率",
        "current_ratio": "流动比率",
    },
}


def ensure_financial_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS financial_statements (
              id             BIGSERIAL PRIMARY KEY,
              symbol         TEXT NOT NULL,
              report_period  DATE NOT NULL,
              announce_date  DATE NOT NULL,
              statement_type TEXT NOT NULL,
              data           JSONB NOT NULL DEFAULT '{}'::jsonb,
              source         TEXT NOT NULL DEFAULT '',
              updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (symbol, report_period, statement_type)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_financial_symbol_pit "
            "ON financial_statements (symbol, announce_date DESC, report_period DESC)"
        )


def validate_records(records: Iterable[dict[str, Any]]) -> list[str]:
    """返回问题列表；空=通过。问题不阻断查询，但导入时应拒绝。"""
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for i, rec in enumerate(records):
        symbol = str(rec.get("symbol") or "").strip()
        stype = str(rec.get("statement_type") or "").strip()
        period = str(rec.get("report_period") or "").strip()
        announce = str(rec.get("announce_date") or "").strip()
        if not symbol or not period or not stype:
            errors.append(f"第 {i + 1} 行缺少 symbol/report_period/statement_type")
            continue
        if stype not in STATEMENT_TYPES:
            errors.append(f"{symbol} {period}: 未知报表类型 {stype}")
        try:
            p = date.fromisoformat(period)
            a = date.fromisoformat(announce)
        except ValueError:
            errors.append(f"{symbol} {period}: 日期须为 YYYY-MM-DD")
            continue
        if a < p:
            errors.append(f"{symbol} {period}: 公告日早于报告期，疑似口径错误")
        key = (symbol, period, stype)
        if key in seen:
            errors.append(f"{symbol} {period} {stype}: 重复记录")
        seen.add(key)
        data = rec.get("data")
        if not isinstance(data, dict) or not data:
            errors.append(f"{symbol} {period} {stype}: data 为空")
    return errors


def select_point_in_time(
    rows: list[dict[str, Any]], *, as_of: str | None = None
) -> dict[str, dict[str, Any]]:
    """按 as_of 选每个报表类型最新一期（announce_date <= as_of）。"""
    picked: dict[str, dict[str, Any]] = {}
    for row in rows:
        stype = str(row.get("statement_type") or "")
        announce = str(row.get("announce_date") or "")
        period = str(row.get("report_period") or "")
        if as_of and announce > as_of:
            continue
        cur = picked.get(stype)
        if cur is None or (announce, period) > (
            str(cur.get("announce_date") or ""),
            str(cur.get("report_period") or ""),
        ):
            picked[stype] = row
    return picked


def _row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for key in ("report_period", "announce_date"):
        val = item.get(key)
        if hasattr(val, "isoformat"):
            item[key] = val.isoformat()
    item["updated_at"] = (
        row["updated_at"].isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at")
    )
    return item


def upsert_records(records: list[dict[str, Any]], *, source: str = "external") -> int:
    problems = validate_records(records)
    if problems:
        raise ValueError("；".join(problems[:8]))
    ensure_financial_schema()
    count = 0
    with get_conn() as conn:
        for rec in records:
            conn.execute(
                """
                INSERT INTO financial_statements
                  (symbol, report_period, announce_date, statement_type, data, source)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (symbol, report_period, statement_type) DO UPDATE SET
                  announce_date = EXCLUDED.announce_date,
                  data = EXCLUDED.data,
                  source = EXCLUDED.source,
                  updated_at = NOW()
                """,
                (
                    str(rec["symbol"]).strip().upper(),
                    str(rec["report_period"]),
                    str(rec["announce_date"]),
                    str(rec["statement_type"]),
                    json.dumps(rec.get("data") or {}, ensure_ascii=False),
                    source,
                ),
            )
            count += 1
    return count


def query_financials(
    symbol: str, *, as_of: str | None = None, statement_type: str | None = None
) -> dict[str, Any]:
    ensure_financial_schema()
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("证券代码不能为空")
    if statement_type and statement_type not in STATEMENT_TYPES:
        raise ValueError(f"statement_type 须为 {', '.join(STATEMENT_TYPES)}")
    sql = "SELECT * FROM financial_statements WHERE symbol = %s"
    params: list[Any] = [sym]
    if statement_type:
        sql += " AND statement_type = %s"
        params.append(statement_type)
    if as_of:
        sql += " AND announce_date <= %s"
        params.append(as_of)
    sql += " ORDER BY announce_date DESC, report_period DESC"
    with get_conn() as conn:
        rows = [_row(dict(r)) for r in conn.execute(sql, params).fetchall()]
    latest = select_point_in_time(rows, as_of=as_of)
    return {
        "ok": True,
        "symbol": sym,
        "as_of": as_of,
        "count": len(rows),
        "latest_by_type": latest,
        "items": rows,
        "field_dict": FIELD_DICT,
        "note": "点时查询按公告日过滤；latest_by_type 为 as_of 时点可用的最新一期",
    }


def read_csv_records(path: str) -> list[dict[str, Any]]:
    """宽表 CSV → 记录：symbol,report_period,announce_date,statement_type,字段...

    其中字段列会进入 data JSONB；非数值列保留原字符串。
    """
    meta_cols = {"symbol", "report_period", "announce_date", "statement_type"}
    records: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = meta_cols - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV 缺少列: {', '.join(sorted(missing))}")
        for raw in reader:
            data: dict[str, Any] = {}
            for key, value in raw.items():
                if key in meta_cols or key is None or value is None or value == "":
                    continue
                try:
                    data[key] = float(value)
                except ValueError:
                    data[key] = value
            records.append(
                {
                    "symbol": raw["symbol"],
                    "report_period": raw["report_period"],
                    "announce_date": raw["announce_date"],
                    "statement_type": raw["statement_type"],
                    "data": data,
                }
            )
    return records
