# -*- coding: utf-8 -*-
"""市场数据只读查询（供机构端 / 手机端 / AI 工具共用）。

约定：
- 所有查询返回 dict/list[dict]，时间用 ISO 字符串。
- 行情展示用未复权（adjust='none'），收益/回撤用后复权（adjust='hfq'）。
- 数据不足时返回 None / 空列表，不补造数字。
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from services.core.db import get_conn


def _d(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def latest_trade_date(market: str = "CN") -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(trade_date) AS d FROM ref_trading_calendar WHERE market=%s AND is_open",
            (market,),
        ).fetchone()
    return _d(row["d"]) if row else None


def security(symbol: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT symbol, name, market, exchange, board, list_date, delist_date, status, source "
            "FROM ref_security WHERE symbol=%s",
            (symbol,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["list_date"] = _d(out.get("list_date"))
    out["delist_date"] = _d(out.get("delist_date"))
    return out


def search_securities(q: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    term = (q or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol, name, market, board, status
              FROM ref_security
             WHERE symbol ILIKE %s OR name ILIKE %s
             ORDER BY (symbol = %s) DESC, symbol
             LIMIT %s OFFSET %s
            """,
            (like, like, term, max(1, min(limit, 200)), max(0, offset)),
        ).fetchall()
    return [dict(r) for r in rows]


def count_securities(q: str) -> int:
    term = (q or "").strip()
    if not term:
        return 0
    like = f"%{term}%"
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM ref_security WHERE symbol ILIKE %s OR name ILIKE %s",
            (like, like),
        ).fetchone()
    return int(row["n"] or 0)


def latest_bar(symbol: str, adjust: str = "none") -> dict[str, Any] | None:
    # 展示优先未复权；未复权尚未同步时回退后复权，并在 adjust 字段如实标注。
    candidates = [adjust] + [a for a in ("none", "hfq") if a != adjust]
    with get_conn() as conn:
        for adj in candidates:
            row = conn.execute(
                """
                SELECT symbol, trade_date, open, high, low, close, pre_close, volume, amount, turnover, adjust
                  FROM md_daily_bar
                 WHERE symbol=%s AND adjust=%s
                 ORDER BY trade_date DESC LIMIT 1
                """,
                (symbol, adj),
            ).fetchone()
            if row:
                out = dict(row)
                out["trade_date"] = _d(out["trade_date"])
                return out
    return None


def bar_history(
    symbol: str,
    *,
    start: str | None = None,
    end: str | None = None,
    adjust: str = "hfq",
    limit: int = 1300,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT trade_date, open, high, low, close, volume, amount, turnover "
        "FROM md_daily_bar WHERE symbol=%s AND adjust=%s"
    )
    params: list[Any] = [symbol, adjust]
    if start:
        sql += " AND trade_date >= %s"
        params.append(start)
    if end:
        sql += " AND trade_date <= %s"
        params.append(end)
    sql += " ORDER BY trade_date DESC LIMIT %s"
    params.append(max(1, min(limit, 5000)))
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    out = [dict(r) for r in rows]
    out.reverse()
    for item in out:
        item["trade_date"] = _d(item["trade_date"])
    return out


def valuation_latest(symbol: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT trade_date, pe_ttm, pb_mrq, pcf_ocf_ttm, dividend_yield_ttm,
                   float_mv, total_mv, total_shares
              FROM md_valuation_daily
             WHERE symbol=%s
             ORDER BY trade_date DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["trade_date"] = _d(out["trade_date"])
    return out


def valuation_percentile(symbol: str, *, years: int = 3) -> dict[str, Any] | None:
    """当前 PE/PB 在过去 N 年同日频序列中的分位（0-1，越低越便宜）。"""
    latest = valuation_latest(symbol)
    if not latest:
        return None
    end = latest["trade_date"]
    start = (date.fromisoformat(end) - timedelta(days=365 * years)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE pe_ttm IS NOT NULL) AS n_pe,
              COUNT(*) FILTER (WHERE pe_ttm IS NOT NULL AND pe_ttm <= %s) AS le_pe,
              COUNT(*) FILTER (WHERE pb_mrq IS NOT NULL) AS n_pb,
              COUNT(*) FILTER (WHERE pb_mrq IS NOT NULL AND pb_mrq <= %s) AS le_pb
              FROM md_valuation_daily
             WHERE symbol=%s AND trade_date BETWEEN %s AND %s
            """,
            (latest.get("pe_ttm"), latest.get("pb_mrq"), symbol, start, end),
        ).fetchone()
    if not row:
        return None
    n_pe, n_pb = int(row["n_pe"] or 0), int(row["n_pb"] or 0)
    return {
        "years": years,
        "start": start,
        "end": end,
        "pe_ttm": latest.get("pe_ttm"),
        "pb_mrq": latest.get("pb_mrq"),
        "pe_percentile": (int(row["le_pe"] or 0) / n_pe) if n_pe else None,
        "pb_percentile": (int(row["le_pb"] or 0) / n_pb) if n_pb else None,
        "sample_days": max(n_pe, n_pb),
    }


def status_latest(symbol: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT trade_date, listed_status, up_down_status, is_st, is_suspended "
            "FROM md_status_daily WHERE symbol=%s ORDER BY trade_date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["trade_date"] = _d(out["trade_date"])
    return out


def industry_latest(symbol: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT industry_code, effective_from, effective_to
              FROM ref_security_industry
             WHERE symbol=%s AND level=1
             ORDER BY effective_from DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["effective_from"] = _d(out.get("effective_from"))
    out["effective_to"] = _d(out.get("effective_to"))
    return out


def financials(symbol: str, limit: int = 8) -> list[dict[str, Any]]:
    """按报告期合并利润表/资产负债表/现金流量表，只返回已公告记录。"""
    with get_conn() as conn:
        income = conn.execute(
            """
            SELECT report_date, notice_date, revenue, operating_profit, net_profit,
                   gross_profit, total_profit, eps
              FROM fin_income_statement
             WHERE symbol=%s AND notice_date IS NOT NULL AND notice_date <= CURRENT_DATE
             ORDER BY report_date DESC LIMIT %s
            """,
            (symbol, limit),
        ).fetchall()
        balance = conn.execute(
            """
            SELECT report_date, total_assets, total_liabilities, total_equity,
                   current_assets, current_liabilities, cash, inventory, receivables
              FROM fin_balance_sheet
             WHERE symbol=%s AND notice_date IS NOT NULL AND notice_date <= CURRENT_DATE
             ORDER BY report_date DESC LIMIT %s
            """,
            (symbol, limit),
        ).fetchall()
        cashflow = conn.execute(
            """
            SELECT report_date, operating_cf, investing_cf, financing_cf,
                   free_cash_flow, capex
              FROM fin_cash_flow
             WHERE symbol=%s AND notice_date IS NOT NULL AND notice_date <= CURRENT_DATE
             ORDER BY report_date DESC LIMIT %s
            """,
            (symbol, limit),
        ).fetchall()
        indicators = conn.execute(
            """
            SELECT report_date, roe, gross_margin, net_margin, eps_ttm, revenue_yoy, profit_yoy
              FROM fin_indicator
             WHERE symbol=%s AND notice_date IS NOT NULL AND notice_date <= CURRENT_DATE
             ORDER BY report_date DESC LIMIT %s
            """,
            (symbol, limit),
        ).fetchall()
    by_date: dict[str, dict[str, Any]] = {}
    for rows, prefix in ((income, ""), (balance, ""), (cashflow, ""), (indicators, "")):
        for row in rows:
            d = _d(row["report_date"])
            item = by_date.setdefault(d, {"report_date": d})
            for k, v in dict(row).items():
                if k == "report_date":
                    continue
                if k == "notice_date":
                    item["notice_date"] = _d(v)
                else:
                    item[k] = v
    return [by_date[k] for k in sorted(by_date, reverse=True)]


def risk_stats(
    symbol: str,
    *,
    days: int = 252,
    index_code: str | None = "000300.SH",
) -> dict[str, Any] | None:
    """近 N 个交易日：年化波动、最大回撤、相对基准 beta（基准缺失时 beta=None）。"""
    start = (date.today() - timedelta(days=days * 2)).isoformat()
    bars = bar_history(symbol, start=start, adjust="hfq", limit=days + 5)
    if len(bars) < 30:
        return None
    idx = []
    if index_code:
        with get_conn() as conn:
            idx = conn.execute(
                "SELECT trade_date, close FROM md_index_bar WHERE index_code=%s AND trade_date >= %s ORDER BY trade_date",
                (index_code, start),
            ).fetchall()
    idx_map = {_d(r["trade_date"]): float(r["close"]) for r in idx if r["close"]}
    closes = [(b["trade_date"], float(b["close"])) for b in bars if b["close"]]
    if len(closes) < 30:
        return None
    rets = []
    for (d0, c0), (d1, c1) in zip(closes, closes[1:]):
        if c0:
            rets.append((d1, c1 / c0 - 1))
    if not rets:
        return None
    rs = [r for _, r in rets]
    mean = sum(rs) / len(rs)
    var = sum((r - mean) ** 2 for r in rs) / max(1, len(rs) - 1)
    vol = math.sqrt(var) * math.sqrt(252)
    peak = closes[0][1]
    max_dd = 0.0
    for _, c in closes:
        peak = max(peak, c)
        if peak:
            max_dd = min(max_dd, c / peak - 1)
    # beta vs index
    pairs = []
    for d, r in rets:
        if d in idx_map and d not in {p[0] for p in pairs}:
            pairs.append((d, r))
    beta = None
    if len(pairs) >= 30:
        idx_rets = []
        idx_dates = sorted(idx_map)
        for d0, d1 in zip(idx_dates, idx_dates[1:]):
            if idx_map[d0] and d1 in idx_map:
                idx_rets.append((d1, idx_map[d1] / idx_map[d0] - 1))
        imap = dict(idx_rets)
        xs = [(r, imap[d]) for d, r in pairs if d in imap]
        if len(xs) >= 30:
            mx = sum(x for x, _ in xs) / len(xs)
            my = sum(y for _, y in xs) / len(xs)
            cov = sum((x - mx) * (y - my) for x, y in xs) / max(1, len(xs) - 1)
            vy = sum((y - my) ** 2 for _, y in xs) / max(1, len(xs) - 1)
            beta = cov / vy if vy else None
    return {
        "days": len(closes),
        "annual_vol": vol,
        "max_drawdown": max_dd,
        "beta_1y": beta,
        "start": closes[0][0],
        "end": closes[-1][0],
    }


def index_latest(index_code: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT trade_date, close FROM md_index_bar WHERE index_code=%s ORDER BY trade_date DESC LIMIT 2",
            (index_code,),
        ).fetchall()
    if not rows:
        return None
    latest = dict(rows[0])
    prev = dict(rows[1]) if len(rows) > 1 else None
    change = None
    if prev and prev.get("close"):
        change = float(latest["close"]) / float(prev["close"]) - 1
    return {
        "index_code": index_code,
        "trade_date": _d(latest["trade_date"]),
        "close": latest["close"],
        "change": change,
    }


def industry_peers(industry_code: str, *, limit: int = 10) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.symbol, s.name, v.pe_ttm, v.pb_mrq, v.float_mv
              FROM ref_security s
              JOIN ref_security_industry i ON i.symbol = s.symbol AND i.level = 1
              LEFT JOIN LATERAL (
                SELECT pe_ttm, pb_mrq, float_mv
                  FROM md_valuation_daily
                 WHERE symbol = s.symbol
                 ORDER BY trade_date DESC LIMIT 1
              ) v ON TRUE
             WHERE i.industry_code = %s
             ORDER BY v.float_mv DESC NULLS LAST
             LIMIT %s
            """,
            (industry_code, limit),
        ).fetchall()
    return [dict(r) for r in rows]


__all__ = [
    "bar_history",
    "financials",
    "index_latest",
    "industry_latest",
    "industry_peers",
    "latest_bar",
    "latest_trade_date",
    "risk_stats",
    "count_securities",
    "search_securities",
    "security",
    "status_latest",
    "valuation_latest",
    "valuation_percentile",
]
