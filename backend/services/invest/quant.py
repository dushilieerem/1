# -*- coding: utf-8 -*-
"""量化研究 H5 后端：因子快照、规则风格、回测与模拟盘。

设计约束（对应 11.4 量化研究功能设计）：
- 指标以净值序列为唯一原始产出，AI 不参与任何计算；
- 市场风格、因子结论、榜单全部由服务端规则生成；
- 回测/模拟盘只做历史记账，不产生真实委托，不输出买卖建议；
- 数据缺失时返回 ``available: false`` 或空列表，不用 0 填充。

这里刻意不依赖 pandas/numpy：生产环境的 requirements 只保证标准库与
psycopg。因子面板在内存中按数据日期缓存，回测/模拟盘复用同一份面板。
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable

try:  # 生产环境有 numpy 时用它加速横截面；没有则退回纯 Python。
    import numpy as np
except Exception:  # pragma: no cover - 依赖缺失时的兜底
    np = None

from services.factor.factor_combo import combine as combine_factors
from services.invest import rules

RISK_FREE = 0.02
COST_ONE_WAY = 0.001
DEFAULT_HOLDINGS = 20
MIN_AMOUNT = 50_000_000.0
MAX_HISTORY = 260  # 约 1 年交易日 + 预热

FACTORS: tuple[dict[str, Any], ...] = (
    {
        "key": "value", "name": "低估值", "name_en": "Low valuation",
        "formula": "EP = 1 / PE(TTM)", "formula_en": "EP = 1 / PE(TTM)",
        "direction": "high", "unit": "ratio", "plain": "用市盈率的倒数衡量便宜程度",
        "plain_en": "Earnings yield, the inverse of P/E",
        "high_label": "便宜", "low_label": "贵", "high_label_en": "Cheap", "low_label_en": "Expensive",
    },
    {
        "key": "momentum", "name": "动量", "name_en": "Momentum",
        "formula": "近 20 日涨幅（剔除最近 1 日）", "formula_en": "20-day return, excluding the latest day",
        "direction": "high", "unit": "pct", "plain": "过去一段时间涨得相对好的股票",
        "plain_en": "Stocks that have risen more recently",
        "high_label": "强", "low_label": "弱", "high_label_en": "Strong", "low_label_en": "Weak",
    },
    {
        "key": "volatility", "name": "低波动", "name_en": "Low volatility",
        "formula": "近 20 日收益标准差（越低越好）", "formula_en": "20-day return standard deviation (lower is better)",
        "direction": "low", "unit": "pct", "plain": "价格起伏越小，越接近低波动",
        "plain_en": "Smaller price swings mean lower volatility",
        "high_label": "高波动", "low_label": "低波动", "high_label_en": "High vol", "low_label_en": "Low vol",
    },
    {
        "key": "quality", "name": "质量", "name_en": "Quality",
        "formula": "ROE(TTM)", "formula_en": "ROE (TTM)",
        "direction": "high", "unit": "pct", "plain": "股东投入资本的盈利效率",
        "plain_en": "How efficiently equity capital is used",
        "high_label": "高 ROE", "low_label": "低 ROE", "high_label_en": "High ROE", "low_label_en": "Low ROE",
    },
    {
        "key": "growth", "name": "成长", "name_en": "Growth",
        "formula": "营收同比", "formula_en": "Revenue year-over-year",
        "direction": "high", "unit": "pct", "plain": "收入增长的速度",
        "plain_en": "The pace of revenue growth",
        "high_label": "高增长", "low_label": "低增长", "high_label_en": "High growth", "low_label_en": "Low growth",
    },
    {
        "key": "liquidity", "name": "流动性", "name_en": "Liquidity",
        "formula": "近 20 日日均成交额", "formula_en": "20-day average turnover value",
        "direction": "high", "unit": "yi", "plain": "买卖是否容易成交",
        "plain_en": "How easily the stock trades",
        "high_label": "高流动", "low_label": "低流动", "high_label_en": "Liquid", "low_label_en": "Illiquid",
    },
)
FACTOR_BY_KEY = {f["key"]: f for f in FACTORS}

def re_universe(universe: str) -> str:
    return {"hs300": "CSI300", "zz500": "CSI500", "all": "ALL_A"}.get(universe, "CSI300")


def re_benchmark(universe: str) -> str:
    return "CSI500" if re_universe(universe) == "CSI500" else "CSI300"


UNIVERSES: dict[str, dict[str, str]] = {
    "hs300": {"name": "沪深300", "name_en": "CSI 300", "index": "000300.SH"},
    "zz500": {"name": "中证500", "name_en": "CSI 500", "index": "000905.SH"},
    "all": {"name": "全市场", "name_en": "All A-shares", "index": "000300.SH"},
    # 因子榜/市场风格用的代表性样本：按总市值取前 1000 只，避免首屏扫描全市场。
    "board": {"name": "全市场总市值前 500", "name_en": "Top 500 by market cap", "index": "000300.SH"},
}

_STYLE_TEXT = {
    "attack": ("近 20 日，{a} 与 {b} 的多空收益均为正，市场在奖励{tags}。", "Over the last 20 days, both {a} and {b} long-short spreads were positive; the market rewarded {tags}."),
    "defense": ("近 20 日，{a} 与 {b} 的多空收益均为负，防守型因子相对占优。", "Over the last 20 days, both {a} and {b} long-short spreads were negative; defensive factors held up better."),
    "balanced": ("近 20 日，因子表现分化，{a} 相对占优，{b} 相对落后。", "Over the last 20 days, factor performance diverged: {a} led while {b} lagged."),
}

_PANEL_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_BOARD_PAYLOAD_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_BOARD_CACHE_VERSION = 1
_BOARD_CACHE_ROOT = Path(
    os.environ.get("SVQUANT_QUANT_CACHE_DIR")
    or (Path(__file__).resolve().parents[2] / "data" / "invest_quant_cache")
)
_BOARD_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 1800.0
_LOGGER = logging.getLogger(__name__)


class QuantDataError(ValueError):
    """数据不足或参数不合法。"""


def _num(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> str:
    return str(value or "")[:10]


def _pct(value: float | None, digits: int = 1) -> float | None:
    return float(round(float(value), digits)) if value is not None and math.isfinite(value) else None


def _stdev(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(var)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 5:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _compound(values: Iterable[float]) -> float | None:
    nav = 1.0
    n = 0
    for value in values:
        nav *= 1.0 + value
        n += 1
    return (nav - 1.0) * 100 if n else None


def _max_drawdown(navs: list[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for nav in navs:
        peak = max(peak, nav)
        if peak > 0:
            worst = min(worst, nav / peak - 1.0)
    return worst * 100


def _annualized(navs: list[float]) -> float | None:
    if len(navs) < 2 or navs[0] <= 0 or navs[-1] <= 0:
        return None
    return ((navs[-1] / navs[0]) ** (252.0 / max(1, len(navs) - 1)) - 1.0) * 100


def _daily_rets(navs: list[float]) -> list[float]:
    return [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1]]


def _annual_from_rets(rets: list[float]) -> float | None:
    if len(rets) < 5:
        return None
    nav = 1.0
    for value in rets:
        nav *= 1.0 + value
    if nav <= 0:
        return None
    return (nav ** (252.0 / len(rets)) - 1.0) * 100


def _beta_alpha(strategy_navs: list[float], bench_navs: list[float]) -> tuple[float | None, float | None]:
    rs = _daily_rets(strategy_navs)
    rb = _daily_rets(bench_navs)
    n = min(len(rs), len(rb))
    if n < 5:
        return None, None
    rs, rb = rs[-n:], rb[-n:]
    mr, mb = sum(rs) / n, sum(rb) / n
    cov = sum((a - mr) * (b - mb) for a, b in zip(rs, rb)) / n
    var = sum((b - mb) ** 2 for b in rb) / n
    if var <= 0:
        return None, None
    beta = cov / var
    strat_annual = (_annual_from_rets(rs) or 0.0) / 100.0
    bench_annual = (_annual_from_rets(rb) or 0.0) / 100.0
    alpha = strat_annual - (RISK_FREE + beta * (bench_annual - RISK_FREE))
    return float(beta), float(alpha * 100)


def _month_key(day: str) -> str:
    return str(day)[:7]


def _next_trading_day(conn: Any, day: str) -> str:
    try:
        row = rules.one(
            conn,
            "SELECT MIN(trade_date)::text AS d FROM ref_trading_calendar "
            "WHERE market='CN' AND is_open=TRUE AND trade_date > ?::date",
            (day,),
        )
        if row and row.get("d"):
            return _date(row["d"])
    except Exception:
        pass
    d = date.fromisoformat(_date(day))
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def _normalize_factors(raw: Any) -> list[dict[str, Any]]:
    """2–4 个因子，key 去重；未知因子直接拒绝；保留自定义权重。"""
    if not isinstance(raw, list):
        raise QuantDataError("factors 必须是数组")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        weight = None
        if isinstance(item, str):
            key = item
            direction = ""
        elif isinstance(item, dict):
            key = str(item.get("key") or item.get("id") or "").strip()
            direction = str(item.get("direction") or "").strip().lower()
            weight = _num(item.get("weight"))
        else:
            continue
        if not key or key in seen:
            continue
        meta = FACTOR_BY_KEY.get(key)
        if not meta:
            raise QuantDataError(f"未知因子：{key}")
        seen.add(key)
        entry: dict[str, Any] = {"key": key, "direction": direction if direction in ("high", "low") else meta["direction"]}
        if weight is not None:
            entry["weight"] = max(0.0, float(weight))
        out.append(entry)
    if not 2 <= len(out) <= 4:
        raise QuantDataError("请选择 2–4 个因子")
    if any("weight" in x for x in out) and not all("weight" in x for x in out):
        raise QuantDataError("自定义权重需要每个因子都填写")
    total = sum(float(x.get("weight") or 0) for x in out)
    if any("weight" in x for x in out) and total <= 0:
        raise QuantDataError("权重合计必须大于 0")
    return out


def _normalize_universe(value: Any) -> str:
    key = str(value or "hs300").strip().lower()
    return key if key in UNIVERSES else "hs300"


def _factor_meta(key: str) -> dict[str, Any]:
    meta = dict(FACTOR_BY_KEY[key])
    return meta


def _direction_sign(meta: dict[str, Any], direction: str | None) -> float:
    chosen = direction if direction in ("high", "low") else str(meta.get("direction") or "high")
    return 1.0 if chosen == "high" else -1.0


def _membership(conn: Any, universe: str, asof: str) -> tuple[list[str], dict[str, list[tuple[str, str]]]]:
    """返回股票池和成员区间；中证/沪深按历史区间判断，避免只用当前成分。"""
    if universe == "board":
        rows = rules.rows(
            conn,
            "SELECT symbol FROM md_valuation_daily "
            "WHERE trade_date = (SELECT MAX(trade_date) FROM md_valuation_daily) "
            "AND total_mv IS NOT NULL ORDER BY total_mv DESC LIMIT 500",
        )
        symbols = [str(r["symbol"]) for r in rows if r.get("symbol")]
        if symbols:
            return symbols, {}
    if universe in ("hs300", "zz500"):
        code = UNIVERSES[universe]["index"]
        rows = rules.rows(
            conn,
            "SELECT symbol, effective_from::text AS f, "
            "COALESCE(effective_to::text, '') AS t "
            "FROM ref_index_member WHERE index_code=? AND effective_from <= ?::date",
            (code, asof),
        )
        spans: dict[str, list[tuple[str, str]]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            spans.setdefault(symbol, []).append((_date(row.get("f")), _date(row.get("t"))))
        symbols = sorted(spans)
        if symbols:
            return symbols, spans
        # 生产数据缺失时回退到全市场，调用方会在假设里标注。
    rows = rules.rows(
        conn,
        "SELECT symbol FROM ref_security WHERE status='listed' "
        "AND COALESCE(market,'CN')='CN' ORDER BY symbol",
    )
    return [str(r["symbol"]) for r in rows if r.get("symbol")], {}


def _in_universe(spans: dict[str, list[tuple[str, str]]], symbol: str, day: str) -> bool:
    if not spans:
        return True
    for start, end in spans.get(symbol, []):
        if start and start <= day and (not end or day < end):
            return True
    return False


def _chunks(items: list[str], size: int = 450) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _load_panel(conn: Any, universe: str) -> dict[str, Any]:
    """加载并缓存因子面板。缓存键带 dataDate，数据更新后自然失效。"""
    row = rules.one(conn, "SELECT MAX(trade_date)::text AS d FROM md_daily_bar WHERE adjust='hfq'")
    data_date = _date((row or {}).get("d"))
    key = (universe, data_date)
    now = time.time()
    with _CACHE_LOCK:
        hit = _PANEL_CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    if not data_date:
        raise QuantDataError("行情数据尚未就绪")
    cutoff = (date.fromisoformat(data_date) - timedelta(days=430)).isoformat()
    symbols, spans = _membership(conn, universe, data_date)
    if not symbols:
        raise QuantDataError("股票池为空")
    # 交易日历有 (market, trade_date) 主键，比 DISTINCT 扫日线快两个数量级。
    dates_rows = rules.rows(
        conn,
        "SELECT trade_date::text AS d FROM ref_trading_calendar "
        "WHERE market='CN' AND is_open=TRUE AND trade_date BETWEEN ?::date AND ?::date ORDER BY d",
        (cutoff, data_date),
    )
    dates = [_date(r.get("d")) for r in dates_rows if r.get("d")]
    if not dates:
        dates_rows = rules.rows(
            conn,
            "SELECT DISTINCT trade_date::text AS d FROM md_daily_bar "
            "WHERE adjust='hfq' AND trade_date BETWEEN ?::date AND ?::date ORDER BY d",
            (cutoff, data_date),
        )
        dates = [_date(r.get("d")) for r in dates_rows if r.get("d")]
    if not dates:
        raise QuantDataError("区间内没有交易日")
    idx = {d: i for i, d in enumerate(dates)}
    n = len(dates)

    close: dict[str, list[float | None]] = {}
    amount: dict[str, list[float | None]] = {}
    pe: dict[str, list[float | None]] = {}
    for symbol in symbols:
        close[symbol] = [None] * n
        amount[symbol] = [None] * n
        pe[symbol] = [None] * n

    raw_conn = getattr(conn, "raw", None)
    bulk = None
    if raw_conn is not None:
        from psycopg.rows import tuple_row
        from services.invest.db import pg_sql

        def bulk(sql: str, args: tuple[Any, ...]) -> list[tuple[Any, ...]]:
            cur = raw_conn.cursor(row_factory=tuple_row)
            cur.execute(pg_sql(sql), args)
            return cur.fetchall()

    for chunk in _chunks(symbols):
        if bulk:
            for symbol, trade_date, value, amt in bulk(
                "SELECT symbol, trade_date::text, close, amount FROM md_daily_bar "
                "WHERE adjust='hfq' AND trade_date BETWEEN ?::date AND ?::date AND symbol = ANY(?)",
                (cutoff, data_date, chunk),
            ):
                pos = idx.get(_date(trade_date))
                if pos is not None:
                    close[symbol][pos] = value
                    amount[symbol][pos] = amt
            for symbol, trade_date, value in bulk(
                "SELECT symbol, trade_date::text, pe_ttm FROM md_valuation_daily "
                "WHERE trade_date BETWEEN ?::date AND ?::date AND symbol = ANY(?)",
                (cutoff, data_date, chunk),
            ):
                pos = idx.get(trade_date)
                if pos is not None:
                    pe[symbol][pos] = value
        else:
            for row in rules.rows(
                conn,
                "SELECT symbol, trade_date::text AS d, close, amount FROM md_daily_bar "
                "WHERE adjust='hfq' AND trade_date BETWEEN ?::date AND ?::date AND symbol = ANY(?)",
                (cutoff, data_date, chunk),
            ):
                symbol = str(row.get("symbol") or "")
                pos = idx.get(_date(row.get("d")))
                if symbol in close and pos is not None:
                    close[symbol][pos] = _num(row.get("close"))
                    amount[symbol][pos] = _num(row.get("amount"))
            for row in rules.rows(
                conn,
                "SELECT symbol, trade_date::text AS d, pe_ttm FROM md_valuation_daily "
                "WHERE trade_date BETWEEN ?::date AND ?::date AND symbol = ANY(?)",
                (cutoff, data_date, chunk),
            ):
                symbol = str(row.get("symbol") or "")
                pos = idx.get(_date(row.get("d")))
                if symbol in pe and pos is not None:
                    pe[symbol][pos] = _num(row.get("pe_ttm"))

    fin: dict[str, list[tuple[str, float | None, float | None]]] = {}
    for row in rules.rows(
        conn,
        "SELECT symbol, notice_date::text AS d, roe, revenue_yoy FROM fin_indicator "
        "WHERE notice_date BETWEEN (?::date - INTERVAL '2 years') AND ?::date AND symbol = ANY(?) "
        "ORDER BY symbol, notice_date",
        (data_date, data_date, symbols),
    ):
        symbol = str(row.get("symbol") or "")
        if symbol in close and row.get("d"):
            fin.setdefault(symbol, []).append((_date(row["d"]), _num(row.get("roe")), _num(row.get("revenue_yoy"))))

    name: dict[str, str] = {}
    list_date: dict[str, str] = {}
    for row in rules.rows(
        conn,
        "SELECT symbol, name, list_date::text AS d FROM ref_security WHERE symbol = ANY(?)",
        (symbols,),
    ):
        symbol = str(row.get("symbol") or "")
        if symbol:
            name[symbol] = str(row.get("name") or symbol)
            list_date[symbol] = _date(row.get("d"))

    st: set[str] = set()
    suspended: set[str] = set()
    for row in rules.rows(
        conn,
        "SELECT symbol, is_st, is_suspended FROM md_status_daily "
        "WHERE trade_date = (SELECT MAX(trade_date) FROM md_status_daily) AND symbol = ANY(?)",
        (symbols,),
    ):
        symbol = str(row.get("symbol") or "")
        if row.get("is_st"):
            st.add(symbol)
        if row.get("is_suspended"):
            suspended.add(symbol)

    bench_code = UNIVERSES.get(universe, {}).get("index") or "000300.SH"
    bench: dict[str, float] = {}
    for row in rules.rows(
        conn,
        "SELECT trade_date::text AS d, close FROM md_index_bar "
        "WHERE index_code=? AND trade_date BETWEEN ?::date AND ?::date",
        (bench_code, cutoff, data_date),
    ):
        value = _num(row.get("close"))
        if value is not None:
            bench[_date(row.get("d"))] = value

    panel = {
        "universe": universe,
        "data_date": data_date,
        "dates": dates,
        "idx": idx,
        "symbols": symbols,
        "spans": spans,
        "close": close,
        "amount": amount,
        "pe": pe,
        "fin": fin,
        "name": name,
        "list_date": list_date,
        "st": st,
        "suspended": suspended,
        "bench_code": bench_code,
        "bench": bench,
        "derived": None,
    }
    _prepare(panel)
    with _CACHE_LOCK:
        _PANEL_CACHE[key] = (now, panel)
    return panel


def _matrix_from_lists(rows: dict[str, list[Any]], symbols: list[str], n: int) -> Any:
    out = np.full((len(symbols), n), np.nan, dtype=float)
    for i, symbol in enumerate(symbols):
        values = rows.get(symbol)
        if values:
            out[i] = np.fromiter((np.nan if v is None else v for v in values), dtype=float, count=n)
    return out


def _prepare_numpy(panel: dict[str, Any]) -> None:
    """numpy 版滚动因子：全市场 5500 只 × 300 日可在亚秒级完成。"""
    symbols = panel["symbols"]
    dates = panel["dates"]
    n = len(dates)
    ns = len(symbols)
    close = _matrix_from_lists(panel["close"], symbols, n)
    amount = _matrix_from_lists(panel["amount"], symbols, n)
    pe = _matrix_from_lists(panel["pe"], symbols, n)

    ret = np.full((ns, n), np.nan)
    prev = close[:, :-1]
    cur = close[:, 1:]
    valid = np.isfinite(cur) & np.isfinite(prev) & (prev != 0)
    ret[:, 1:] = np.where(valid, cur / np.where(prev == 0, np.nan, prev) - 1.0, np.nan)
    ret_next = np.full((ns, n), np.nan)
    ret_next[:, :-1] = ret[:, 1:]

    ep = np.where(np.isfinite(pe) & (pe > 0), 1.0 / np.where(pe == 0, np.nan, pe), np.nan)
    mom = np.full((ns, n), np.nan)
    c1 = close[:, 20:-1]
    c21 = close[:, :-21]
    ok = np.isfinite(c1) & np.isfinite(c21) & (c21 != 0)
    mom[:, 21:] = np.where(ok, c1 / np.where(c21 == 0, np.nan, c21) - 1.0, np.nan)

    zeros = np.zeros((ns, 1))
    r = np.nan_to_num(ret, nan=0.0)
    m = np.isfinite(ret).astype(float)
    cs = np.concatenate([zeros, np.cumsum(r, axis=1)], axis=1)
    cm = np.concatenate([zeros, np.cumsum(m, axis=1)], axis=1)
    csq = np.concatenate([zeros, np.cumsum(r * r, axis=1)], axis=1)
    w_sum = cs[:, 20:-1] - cs[:, :-21]
    w_count = cm[:, 20:-1] - cm[:, :-21]
    w_sq = csq[:, 20:-1] - csq[:, :-21]
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = w_sum / w_count
        var = w_sq / w_count - mean * mean
    vol = np.full((ns, n), np.nan)
    vol[:, 20:] = np.where(w_count >= 10, np.sqrt(np.maximum(var, 0.0)), np.nan)
    vol[:, :21] = np.nan

    a = np.nan_to_num(amount, nan=0.0)
    am = np.isfinite(amount).astype(float)
    acs = np.concatenate([zeros, np.cumsum(a, axis=1)], axis=1)
    acm = np.concatenate([zeros, np.cumsum(am, axis=1)], axis=1)
    a_sum = acs[:, 20:-1] - acs[:, :-21]
    a_count = acm[:, 20:-1] - acm[:, :-21]
    with np.errstate(divide="ignore", invalid="ignore"):
        liq = np.full((ns, n), np.nan)
        liq[:, 20:] = np.where(a_count >= 10, a_sum / a_count, np.nan)
    liq[:, :20] = np.nan

    date_ord = np.array([date.fromisoformat(d).toordinal() for d in dates], dtype=int)
    roe = np.full((ns, n), np.nan)
    growth = np.full((ns, n), np.nan)
    for i, symbol in enumerate(symbols):
        flows = panel["fin"].get(symbol) or []
        if not flows:
            continue
        fd = np.array([date.fromisoformat(f[0]).toordinal() for f in flows], dtype=int)
        pos = np.searchsorted(fd, date_ord, side="right") - 1
        hit = pos >= 0
        if hit.any():
            roe[i, hit] = [flows[p][1] if flows[p][1] is not None else np.nan for p in pos[hit]]
            growth[i, hit] = [flows[p][2] if flows[p][2] is not None else np.nan for p in pos[hit]]

    derived = {
        "value": {s: ep[i] for i, s in enumerate(symbols)},
        "momentum": {s: mom[i] for i, s in enumerate(symbols)},
        "volatility": {s: vol[i] for i, s in enumerate(symbols)},
        "quality": {s: roe[i] for i, s in enumerate(symbols)},
        "growth": {s: growth[i] for i, s in enumerate(symbols)},
        "liquidity": {s: liq[i] for i, s in enumerate(symbols)},
        "_ret_next": {s: ret_next[i] for i, s in enumerate(symbols)},
    }
    panel["derived"] = derived
    panel["np_mats"] = {
        "value": ep, "momentum": mom, "volatility": vol, "quality": roe,
        "growth": growth, "liquidity": liq, "_ret_next": ret_next, "_amount": amount,
    }


def _prepare(panel: dict[str, Any]) -> None:
    """一次性计算每只股票的滚动因子，避免逐日重复扫描 K 线。

    滚动波动/成交额用滑动和计算（O(T)），不要在每个交易日切片重算 20 日窗口；
    全市场 5500 只 × 300 日时，后者会慢一个数量级。
    """
    if panel.get("derived"):
        return
    if np is not None:
        _prepare_numpy(panel)
        return
    dates: list[str] = panel["dates"]
    n = len(dates)
    derived = {key: {} for key in FACTOR_BY_KEY}
    for symbol in panel["symbols"]:
        close = panel["close"].get(symbol) or [None] * n
        amount = panel["amount"].get(symbol) or [None] * n
        pe = panel["pe"].get(symbol) or [None] * n
        ret: list[float | None] = [None] * n
        for i in range(1, n):
            prev = close[i - 1]
            cur = close[i]
            if cur is not None and prev:
                ret[i] = cur / prev - 1.0
        ret_next: list[float | None] = [None] * n
        for i in range(n - 1):
            cur = close[i]
            nxt = close[i + 1]
            if cur and nxt is not None:
                ret_next[i] = nxt / cur - 1.0

        ep = [None] * n
        mom = [None] * n
        vol = [None] * n
        liq = [None] * n
        for i in range(n):
            p = pe[i]
            if p is not None and p > 0:
                ep[i] = 1.0 / p
            if i >= 21:
                c1, c21 = close[i - 1], close[i - 21]
                if c1 and c21:
                    mom[i] = c1 / c21 - 1.0

        # 20 日收益标准差：窗口 ret[i-20:i]，滑动维护 sum/sumsq/count。
        w_sum = 0.0
        w_sq = 0.0
        w_count = 0
        for i in range(1, n):
            r = ret[i - 1]
            if r is not None:
                w_sum += r
                w_sq += r * r
                w_count += 1
            if i - 21 >= 0:
                old = ret[i - 21]
                if old is not None:
                    w_sum -= old
                    w_sq -= old * old
                    w_count -= 1
            if i >= 21 and w_count >= 10:
                mean = w_sum / w_count
                var = max(0.0, w_sq / w_count - mean * mean)
                vol[i] = math.sqrt(var)

        # 20 日日均成交额：窗口 amount[i-20:i]。
        a_sum = 0.0
        a_count = 0
        for i in range(1, n):
            value = amount[i - 1]
            if value is not None:
                a_sum += value
                a_count += 1
            if i - 21 >= 0:
                old = amount[i - 21]
                if old is not None:
                    a_sum -= old
                    a_count -= 1
            if i >= 20 and a_count >= 10:
                liq[i] = a_sum / a_count

        roe = [None] * n
        growth = [None] * n
        flows = panel["fin"].get(symbol) or []
        cursor = -1
        for i, day in enumerate(dates):
            while cursor + 1 < len(flows) and flows[cursor + 1][0] <= day:
                cursor += 1
            if cursor >= 0:
                roe[i] = flows[cursor][1]
                growth[i] = flows[cursor][2]

        derived["value"][symbol] = ep
        derived["momentum"][symbol] = mom
        derived["volatility"][symbol] = vol
        derived["quality"][symbol] = roe
        derived["growth"][symbol] = growth
        derived["liquidity"][symbol] = liq
        derived.setdefault("_ret_next", {})[symbol] = ret_next
    panel["derived"] = derived


def _raw(panel: dict[str, Any], symbol: str, key: str, i: int) -> float | None:
    if i >= len(panel["dates"]):
        return None
    values = (panel["derived"].get(key) or {}).get(symbol)
    if values is None:
        return None
    value = values[i]
    return float(value) if value is not None and value == value else None


def _ret_next(panel: dict[str, Any], symbol: str, i: int) -> float | None:
    values = (panel["derived"].get("_ret_next") or {}).get(symbol)
    if values is None:
        return None
    value = values[i]
    return float(value) if value is not None and value == value else None


def _eligible(panel: dict[str, Any], symbol: str, i: int, *, require_liquidity: bool = True, filters: dict[str, bool] | None = None) -> bool:
    filters = filters or {}
    day = panel["dates"][i]
    if not _in_universe(panel["spans"], symbol, day):
        return False
    if symbol in panel["suspended"]:
        return False
    if filters.get("st", True) and symbol in panel["st"]:
        return False
    if filters.get("listed60", True):
        listed = panel["list_date"].get(symbol)
        if listed:
            try:
                if (date.fromisoformat(day) - date.fromisoformat(listed)).days < 60:
                    return False
            except ValueError:
                pass
    if require_liquidity and filters.get("amount", True):
        liq = _raw(panel, symbol, "liquidity", i)
        if liq is None or liq < MIN_AMOUNT:
            return False
    return True


def _standardize(values: dict[str, float]) -> dict[str, float]:
    if len(values) < 5:
        return {}
    ordered = sorted(values.values())
    med = median(ordered)
    deviations = sorted(abs(v - med) for v in ordered)
    mad = median(deviations)
    lo = hi = None
    if mad > 0:
        spread = 1.4826 * mad
        lo, hi = med - 3 * spread, med + 3 * spread
    clean: dict[str, float] = {}
    for symbol, value in values.items():
        if lo is not None and hi is not None:
            value = min(hi, max(lo, value))
        clean[symbol] = value
    mean = sum(clean.values()) / len(clean)
    var = sum((v - mean) ** 2 for v in clean.values()) / len(clean)
    sd = math.sqrt(var)
    if sd <= 0:
        return {s: 0.0 for s in clean}
    return {s: (v - mean) / sd for s, v in clean.items()}


def _cross_section(
    panel: dict[str, Any],
    i: int,
    keys: Iterable[str],
    *,
    require_liquidity: bool = True,
    filters: dict[str, bool] | None = None,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {key: {} for key in keys}
    for symbol in panel["symbols"]:
        if not _eligible(panel, symbol, i, require_liquidity=require_liquidity, filters=filters):
            continue
        for key in out:
            value = _raw(panel, symbol, key, i)
            if value is not None:
                out[key][symbol] = value
    return out


def _scores(panel: dict[str, Any], i: int, factors: list[dict[str, Any]], *, filters: dict[str, bool] | None = None) -> dict[str, float]:
    """复用 factor_combo.combine：MAD 去极值 → 横截面 z-score → 等权/自定义权重合成。"""
    raws = _cross_section(panel, i, [f["key"] for f in factors], filters=filters)
    if not raws or any(not values for values in raws.values()):
        return {}
    symbols = sorted(set().union(*(set(values) for values in raws.values())))
    factor_series: dict[str, list[float | None]] = {}
    for factor in factors:
        key = factor["key"]
        sign = _direction_sign(FACTOR_BY_KEY[key], factor.get("direction"))
        values = raws.get(key) or {}
        factor_series[key] = [values[s] * sign if s in values else None for s in symbols]
    custom = {f["key"]: float(f.get("weight") or 0) for f in factors} if all("weight" in f for f in factors) else None
    try:
        combined = combine_factors(
            factors=factor_series,
            scheme="custom" if custom is not None else "equal",
            custom_weights=custom,
            winsorize=True,
        )
    except ValueError:
        return {}
    scores = combined.get("scores") or []
    coverage = combined.get("coverage") or []
    need = len(factors)
    return {
        symbol: float(score)
        for symbol, score, covered in zip(symbols, scores, coverage)
        if score is not None and covered == need
    }


def _pick(
    panel: dict[str, Any],
    i: int,
    factors: list[dict[str, Any]],
    n: int = DEFAULT_HOLDINGS,
    *,
    filters: dict[str, bool] | None = None,
) -> list[str]:
    scores = _scores(panel, i, factors, filters=filters)
    return [s for s, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def _benchmark(panel: dict[str, Any]) -> tuple[list[float | None], str]:
    """基准日收益；指数缺失时用股票池等权，并在假设中明确。"""
    dates = panel["dates"]
    if panel["bench"]:
        closes = [panel["bench"].get(d) for d in dates]
        rets: list[float | None] = [None] * len(dates)
        for i in range(len(dates) - 1):
            if closes[i] and closes[i + 1] is not None:
                rets[i] = closes[i + 1] / closes[i] - 1
        return rets, "index"
    rets = [None] * len(dates)
    for i in range(len(dates) - 1):
        vals = [
            r for s in panel["symbols"]
            if (r := _ret_next(panel, s, i)) is not None and _eligible(panel, s, i)
        ]
        if vals:
            rets[i] = sum(vals) / len(vals)
    return rets, "equal_weight"


def _monthly_groups(panel: dict[str, Any], start: int, end: int) -> list[tuple[int, int]]:
    """返回 [(rebalance_idx, period_end_idx)]，period_end 为下一次调仓前一日。"""
    groups: list[tuple[int, int]] = []
    current = start
    last_month = _month_key(panel["dates"][start])
    for i in range(start + 1, end + 1):
        month = _month_key(panel["dates"][i])
        if month != last_month:
            groups.append((current, i - 1))
            current = i
            last_month = month
    groups.append((current, end))
    return [g for g in groups if g[0] <= g[1]]


def _rebalance_groups(panel: dict[str, Any], start: int, end: int, frequency: str) -> list[tuple[int, int]]:
    frequency = frequency if frequency in ("monthly", "biweekly", "quarterly") else "monthly"
    if frequency == "monthly":
        return _monthly_groups(panel, start, end)
    groups: list[tuple[int, int]] = []
    current = start
    if frequency == "biweekly":
        step = 10
        for i in range(start + step, end + 1, step):
            groups.append((current, i - 1))
            current = i
        groups.append((current, end))
        return [g for g in groups if g[0] <= g[1]]
    # quarterly
    last_quarter = panel["dates"][start][:4] + "Q" + str((int(panel["dates"][start][5:7]) - 1) // 3 + 1)
    for i in range(start + 1, end + 1):
        d = panel["dates"][i]
        quarter = d[:4] + "Q" + str((int(d[5:7]) - 1) // 3 + 1)
        if quarter != last_quarter:
            groups.append((current, i - 1))
            current = i
            last_quarter = quarter
    groups.append((current, end))
    return [g for g in groups if g[0] <= g[1]]


def _run_curve(
    panel: dict[str, Any],
    factors: list[dict[str, Any]],
    *,
    start_idx: int | None = None,
    end_idx: int | None = None,
    holdings: int = DEFAULT_HOLDINGS,
    rebalance: str = "monthly",
    filters: dict[str, bool] | None = None,
) -> dict[str, Any]:
    dates = panel["dates"]
    n = len(dates)
    end = n - 2 if end_idx is None else min(end_idx, n - 2)
    start = max(21, n - 1 - MAX_HISTORY) if start_idx is None else max(21, start_idx)
    if end <= start + 2:
        raise QuantDataError("历史数据不足，暂时无法回测")
    bench_rets, bench_kind = _benchmark(panel)
    groups = _rebalance_groups(panel, start, end, rebalance)

    nav = 1.0
    bench_nav = 1.0
    navs = [1.0]
    bench_navs = [1.0]
    curve: list[dict[str, Any]] = [{"date": dates[start], "nav": 1.0, "benchmark": 1.0}]
    old_weights: dict[str, float] = {}
    trade_count = 0
    periods: list[tuple[float, float]] = []
    total_cost = 0.0
    last_holdings: list[str] = []

    for gi, (r_idx, p_end) in enumerate(groups):
        picked = _pick(panel, r_idx, factors, holdings, filters=filters)
        if not picked:
            continue
        weights = {s: 1.0 / len(picked) for s in picked}
        if old_weights:
            turnover = 0.5 * sum(
                abs(weights.get(s, 0.0) - old_weights.get(s, 0.0))
                for s in set(weights) | set(old_weights)
            )
        else:
            turnover = 1.0
        cost = turnover * COST_ONE_WAY
        total_cost += cost
        trade_count += len(set(picked) - set(old_weights))
        period_start_nav = nav
        period_start_bench = bench_nav
        nav *= 1.0 - cost
        # 调仓日当天不重复计收益，从下一交易日开始持有。
        for i in range(r_idx, p_end + 1):
            if i >= end + 1:
                break
            port_ret = 0.0
            covered = 0.0
            for symbol, weight in weights.items():
                r = _ret_next(panel, symbol, i)
                if r is not None:
                    port_ret += weight * r
                    covered += weight
            if covered > 0 and covered < 1:
                port_ret /= covered
            bench_ret = bench_rets[i]
            nav = float(nav * (1.0 + port_ret))
            if bench_ret is not None:
                bench_nav = float(bench_nav * (1.0 + bench_ret))
            navs.append(nav)
            bench_navs.append(bench_nav)
            curve.append({"date": dates[i + 1] if i + 1 < n else dates[i], "nav": nav, "benchmark": bench_nav})
        periods.append((nav / period_start_nav - 1 if period_start_nav else 0.0, bench_nav / period_start_bench - 1 if period_start_bench else 0.0))
        old_weights = weights
        last_holdings = picked

    if len(navs) < 3:
        raise QuantDataError("历史数据不足，暂时无法回测")
    wins = sum(1 for a, b in periods if a > b)
    annual = _annualized(navs)
    bench_annual = _annualized(bench_navs)
    vol = (_stdev(_daily_rets(navs)) or 0.0) * math.sqrt(252) * 100
    beta, alpha = _beta_alpha(navs, bench_navs)
    sharpe = ((annual or 0.0) / 100.0 - RISK_FREE) / (vol / 100.0) if vol > 0 else None
    metrics = {
        "cumulative": _pct((navs[-1] - 1) * 100),
        "annual_return": _pct(annual),
        "max_drawdown": _pct(_max_drawdown(navs)),
        "sharpe": float(round(sharpe, 2)) if sharpe is not None else None,
        "win_rate": float(round(wins / len(periods) * 100, 0)) if periods else None,
        "trade_count": trade_count,
        "volatility": _pct(vol),
        "beta": float(round(beta, 2)) if beta is not None else None,
        "alpha": _pct(alpha),
        "benchmark_return": _pct((bench_navs[-1] - 1) * 100),
        "benchmark_annual": _pct(bench_annual),
        "excess": _pct((navs[-1] - bench_navs[-1]) * 100),
        "turnover_cost": _pct(total_cost * 100),
    }
    return {
        "curve": curve,
        "navs": navs,
        "bench_navs": bench_navs,
        "metrics": metrics,
        "holdings": last_holdings,
        "start_date": dates[start],
        "end_date": dates[min(end + 1, n - 1)],
        "bench_kind": bench_kind,
        "bench_code": panel["bench_code"],
        "periods": len(periods),
    }


def _assumptions(
    panel: dict[str, Any],
    factors: list[dict[str, Any]],
    universe: str,
    holdings: int,
    shortened: bool,
    *,
    rebalance: str = "monthly",
    filters: dict[str, bool] | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    bench_kind = "index" if panel["bench"] else "equal_weight"
    rebalance_label = {"monthly": ("月度", "Monthly"), "biweekly": ("双周", "Biweekly"), "quarterly": ("季度", "Quarterly")}
    reb_zh, reb_en = rebalance_label.get(rebalance, rebalance_label["monthly"])
    excluded = []
    excluded_en = []
    if filters.get("st", True):
        excluded.append("ST")
        excluded_en.append("ST")
    if filters.get("listed60", True):
        excluded.append("上市不足 60 天")
        excluded_en.append("listed <60 days")
    if filters.get("amount", True):
        excluded.append("近 20 日日均成交额低于 5000 万")
        excluded_en.append("20-day average turnover < CNY 50m")
    weighting = "自定义" if any("weight" in f for f in factors) else "等权"
    weighting_en = "Custom" if weighting == "自定义" else "Equal weight"
    return {
        "universe": UNIVERSES[universe]["name"],
        "universe_en": UNIVERSES[universe]["name_en"],
        "rebalance": reb_zh,
        "rebalance_en": reb_en,
        "holdings": holdings,
        "weighting": weighting,
        "weighting_en": weighting_en,
        "cost": "单边 0.1%",
        "cost_en": "0.1% one-way",
        "dividend": "含分红（前复权价格）",
        "dividend_en": "Dividends included (forward-adjusted prices)",
        "exclusions": "、".join(excluded) if excluded else "不过滤",
        "exclusions_en": ", ".join(excluded_en) if excluded_en else "No extra filters",
        "benchmark": "沪深300指数" if bench_kind == "index" and panel["bench_code"] == "000300.SH" else (
            "中证500指数" if bench_kind == "index" and panel["bench_code"] == "000905.SH" else "股票池等权"
        ),
        "benchmark_en": "CSI 300" if bench_kind == "index" and panel["bench_code"] == "000300.SH" else (
            "CSI 500" if bench_kind == "index" and panel["bench_code"] == "000905.SH" else "Equal-weight universe"
        ),
        "shortened": shortened,
        "factor_count": len(factors),
        "risk_free": RISK_FREE,
    }


def run_backtest(
    conn: Any,
    factors: Any,
    universe: Any = "hs300",
    *,
    start_date: str | None = None,
    persist: bool = False,
    user_id: int | None = None,
    name: str | None = None,
    project_id: str | None = None,
    holdings: Any = DEFAULT_HOLDINGS,
    rebalance: Any = "monthly",
    filters: Any = None,
) -> dict[str, Any]:
    selected = _normalize_factors(factors)
    universe_key = _normalize_universe(universe)
    try:
        holdings = int(holdings)
    except (TypeError, ValueError):
        holdings = DEFAULT_HOLDINGS
    if holdings not in (10, 20, 30):
        holdings = DEFAULT_HOLDINGS
    rebalance = str(rebalance or "monthly").lower()
    if rebalance not in ("monthly", "biweekly", "quarterly"):
        rebalance = "monthly"
    filter_state = {"st": True, "listed60": True, "amount": True}
    if isinstance(filters, dict):
        for key in filter_state:
            if key in filters:
                filter_state[key] = bool(filters[key])
    # RE 策略接口只接受默认参数；非默认配置走本地同口径引擎，避免 UI 与结果不一致。
    default_config = (
        holdings == DEFAULT_HOLDINGS
        and rebalance == "monthly"
        and all(filter_state.values())
        and not any("weight" in f for f in selected)
    )
    name = name or " + ".join(FACTOR_BY_KEY[f["key"]]["name"] for f in selected)
    try:
        data_date = rules.latest_date(conn)
    except Exception:
        data_date = date.today().isoformat()
    re_result = None
    re_error = None
    try:
        from services.invest import quant_re

        if default_config and quant_re.supports(selected):
            try:
                re_start = start_date or (date.fromisoformat(data_date) - timedelta(days=365)).isoformat()
            except ValueError:
                re_start = start_date
            re_result = quant_re.run_re_strategy(
                factors=selected,
                universe=universe_key,
                start_date=re_start,
                end_date=data_date,
                name=name,
            )
    except Exception as exc:
        re_error = str(exc)[:300]
        _LOGGER.warning("quant RE backtest fallback: %s", re_error)
        re_result = None
    if re_result:
        shortened = False
        result = {
            "id": None,
            "name": name,
            "factors": selected,
            "factor_meta": [_factor_meta(f["key"]) | {"chosen_direction": f["direction"], **({"chosen_weight": f["weight"]} if f.get("weight") is not None else {})} for f in selected],
            "universe": universe_key,
            "start_date": re_result.get("start_date"),
            "end_date": re_result.get("end_date"),
            "metrics": re_result.get("metrics") or {},
            "curve": re_result.get("curve") or [],
            "assumptions": re_result.get("assumptions") or {},
            "holdings": re_result.get("holdings") or [],
            "benchmark": "index",
            "shortened": False,
            "data_date": data_date,
            "engine": "re",
            "engine_reason": None,
            "engine_error": None,
            "disclaimer": "历史回测 · 非真实收益 · 不代表未来",
        }
    else:
        panel = _load_panel(conn, universe_key)
        start_idx = None
        if start_date:
            try:
                start_idx = next(i for i, d in enumerate(panel["dates"]) if d >= _date(start_date))
            except StopIteration:
                raise QuantDataError("起始日期晚于最新数据") from None
        curve = _run_curve(
            panel,
            selected,
            start_idx=start_idx,
            holdings=holdings,
            rebalance=rebalance,
            filters=filter_state,
        )
        shortened = bool(len(panel["dates"]) <= 200)
        try:
            from services.invest import quant_re

            reason = "unsupported_factors" if quant_re.unsupported_keys(selected) else "re_unavailable"
        except Exception:
            reason = "re_unavailable"
        result = {
            "id": None,
            "name": name,
            "factors": selected,
            "factor_meta": [_factor_meta(f["key"]) | {"chosen_direction": f["direction"], **({"chosen_weight": f["weight"]} if f.get("weight") is not None else {})} for f in selected],
            "universe": universe_key,
            "start_date": curve["start_date"],
            "end_date": curve["end_date"],
            "metrics": curve["metrics"],
            "curve": curve["curve"],
            "assumptions": _assumptions(
                panel, selected, universe_key, holdings, shortened,
                rebalance=rebalance, filters=filter_state,
            ),
            "holdings": [
                {"code": code, "name": panel["name"].get(code, code)}
                for code in curve["holdings"][:holdings]
            ],
            "benchmark": curve["bench_kind"],
            "shortened": shortened,
            "data_date": panel["data_date"],
            "engine": "local",
            "engine_reason": reason,
            "engine_error": re_error,
            "disclaimer": "历史回测 · 非真实收益 · 不代表未来",
        }
    if persist:
        if user_id is None:
            raise QuantDataError("保存回测需要用户")
        pid = project_id or _root_project(user_id, selected, universe_key)
        result["project_id"] = pid
        result["id"] = _save_quant_run(
            user_id, pid, result, factors=selected, universe=universe_key
        )
    return result


def _row_factor_meta(row: dict[str, Any]) -> list[dict[str, Any]]:
    factors = row.get("factors") or []
    if isinstance(factors, str):
        try:
            factors = json.loads(factors)
        except ValueError:
            factors = []
    out = []
    for item in factors if isinstance(factors, list) else []:
        if isinstance(item, dict):
            key = str(item.get("key") or "")
            if key in FACTOR_BY_KEY:
                meta = _factor_meta(key) | {"chosen_direction": item.get("direction") or FACTOR_BY_KEY[key]["direction"]}
                if item.get("weight") is not None:
                    meta["chosen_weight"] = float(item["weight"])
                out.append(meta)
    return out


def _row_json(row: dict[str, Any], key: str, default: Any) -> Any:
    value = row.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value


PCT_KEYS = {
    "cumulative", "annual_return", "max_drawdown", "win_rate", "volatility",
    "alpha", "benchmark_return", "benchmark_annual", "excess", "turnover_cost",
}


def _re_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """H5 百分数点 → RE/strategy_runs 的小数口径。"""
    out: dict[str, Any] = {}
    for key, value in (metrics or {}).items():
        if value is None:
            out[key] = None
        elif key in PCT_KEYS:
            try:
                out[key] = float(value) / 100.0
            except (TypeError, ValueError):
                out[key] = None
        else:
            out[key] = value
    return out


def _h5_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (metrics or {}).items():
        if value is None:
            out[key] = None
        elif key in PCT_KEYS:
            try:
                out[key] = float(value) * 100.0
            except (TypeError, ValueError):
                out[key] = None
        else:
            out[key] = value
    return out


def _quant_config(factors: list[dict[str, str]], universe: str, *, draft: bool = False) -> dict[str, Any]:
    from services.strategy import strategy_store

    uni = re_universe(universe)
    benchmark = re_benchmark(universe)
    code = ""
    try:
        from services.invest import quant_re

        code = quant_re.build_strategy_code(factors)
    except Exception:
        code = ""
    local_only = not bool(code)
    cfg = strategy_store._default_config()
    cfg.update({
        "universe": uni,
        "benchmark": benchmark,
        "rangeMode": "period",
        "backtestPeriod": "1y",
        "commission_rate": 0.001,
        "stamp_tax": 0.0,
        "slippage_rate": 0.0,
        "initial_capital": 1_000_000,
        "top_n": 20,
        "rebalance_days": 20,
        "strategy_code": code,
        "engine_mode": "vectorized",
        "quant": True,
        "quant_local_only": local_only,
        "quant_factors": factors,
        "quant_universe": universe,
        "quant_draft": draft,
    })
    return cfg


def _ensure_project(
    user_id: int,
    name: str,
    factors: list[dict[str, str]],
    universe: str,
    *,
    project_id: str | None = None,
    draft: bool = False,
) -> str:
    from services.strategy import strategy_store

    cfg = _quant_config(factors, universe, draft=draft)
    out = strategy_store.upsert_project(
        user_id,
        {
            "id": project_id or str(uuid.uuid4()),
            "name": name,
            "description": "H5 本地降级记录（不可执行）" if cfg.get("quant_local_only") else "H5 量化研究",
            "config": cfg,
        },
    )
    return str(out["project"]["id"])


def _root_project(user_id: int, factors: list[dict[str, str]], universe: str) -> str:
    from services.strategy import strategy_store

    existing = None
    for project in (strategy_store.list_projects(user_id).get("projects") or []):
        if (project.get("config") or {}).get("quant_root"):
            existing = project
            break
    name = (existing or {}).get("name") or "H5 快速实验"
    pid = _ensure_project(user_id, name, factors, universe, project_id=(existing or {}).get("id"))
    project = strategy_store.get_project(user_id, pid)["project"]
    cfg = dict(project.get("config") or {})
    # 快速实验的根项目只承载回测记录，不在 Web 侧提供可执行策略，
    # 避免把“记录项目”误当成可回测策略。
    cfg["quant_root"] = True
    cfg["quant_draft"] = False
    cfg["quant_local_only"] = True
    cfg["strategy_code"] = ""
    strategy_store.upsert_project(
        user_id,
        {
            "id": pid,
            "name": project["name"],
            "description": "H5 快速实验记录（不可执行）",
            "config": cfg,
        },
    )
    return pid


def _run_storage_payload(result: dict[str, Any]) -> dict[str, Any]:
    curve = result.get("curve") or []
    metrics_pct = result.get("metrics") or {}
    equity = [{"date": p.get("date"), "value": float(p.get("nav") or 0)} for p in curve]
    benchmark = [{"date": p.get("date"), "value": float(p.get("benchmark") or 0)} for p in curve]
    return {
        "metrics": _re_metrics(metrics_pct),
        "equity_curve": equity,
        "benchmark_curve": benchmark,
        "date_range": {"start": result.get("start_date"), "end": result.get("end_date")},
        "excess_return": (float(metrics_pct.get("excess") or 0) / 100.0),
        "assumptions": result.get("assumptions") or {},
        "positions": [{
            "date": result.get("end_date"),
            "holdings": [
                {"symbol": h.get("code"), "name": h.get("name"), "weight": 1.0 / max(1, len(result.get("holdings") or []))}
                for h in (result.get("holdings") or [])
            ],
        }],
        "meta": {
            "source": "h5_quant",
            "engine": result.get("engine") or "local",
            "universe": result.get("universe"),
        },
        "quant": {
            "metrics_pct": metrics_pct,
            "curve": curve,
            "assumptions": result.get("assumptions") or {},
            "holdings": result.get("holdings") or [],
            "factors": result.get("factor_meta") or [],
            "engine": result.get("engine") or "local",
            "engine_reason": result.get("engine_reason"),
            "engine_error": result.get("engine_error"),
            "shortened": bool(result.get("shortened")),
        },
    }


def _save_quant_run(
    user_id: int,
    project_id: str,
    result: dict[str, Any],
    *,
    factors: list[dict[str, str]],
    universe: str,
    elapsed: float = 0,
) -> str:
    from services.strategy import strategy_store

    saved = strategy_store.save_run(
        user_id,
        {
            "projectId": project_id,
            "name": result.get("name") or "量化回测",
            "description": "H5 量化研究",
            "elapsedSec": elapsed,
            "request": {
                "quant": True,
                "quant_factors": factors,
                "universe": universe,
                "engine": result.get("engine") or "local",
                "engine_reason": result.get("engine_reason"),
                "engine_error": result.get("engine_error"),
                "start": result.get("start_date"),
                "end": result.get("end_date"),
            },
            "result": _run_storage_payload(result),
        },
    )
    return str(saved["run"]["id"])


def _run_to_backtest(run: dict[str, Any]) -> dict[str, Any]:
    result = run.get("result") or {}
    request = run.get("request") or {}
    quant = result.get("quant") or {}
    metrics_pct = quant.get("metrics_pct") or _h5_metrics(result.get("metrics") or {})
    curve = quant.get("curve") or [
        {"date": p.get("date"), "nav": p.get("value"), "benchmark": None}
        for p in (result.get("equity_curve") or [])
    ]
    if curve and curve[0].get("benchmark") is None:
        benches = {p.get("date"): p.get("value") for p in (result.get("benchmark_curve") or [])}
        for point in curve:
            point["benchmark"] = benches.get(point.get("date"))
    date_range = result.get("date_range") or {}
    assumptions = quant.get("assumptions") or result.get("assumptions") or {}
    holdings = quant.get("holdings") or []
    if not holdings:
        positions = result.get("positions") or []
        if positions:
            holdings = [{"code": h.get("symbol"), "name": h.get("name")} for h in (positions[-1].get("holdings") or [])]
    factors = request.get("quant_factors") or []
    return {
        "id": run.get("id"),
        "project_id": run.get("projectId"),
        "name": run.get("name") or "量化回测",
        "factors": _row_factor_meta({"factors": factors}),
        "universe": request.get("universe") or assumptions.get("universe") or "hs300",
        "start_date": date_range.get("start") or request.get("start"),
        "end_date": date_range.get("end") or request.get("end"),
        "metrics": metrics_pct,
        "curve": curve,
        "assumptions": assumptions,
        "holdings": holdings,
        "shortened": bool(quant.get("shortened")),
        "engine": quant.get("engine") or request.get("engine") or "local",
        "engine_reason": quant.get("engine_reason") or request.get("engine_reason"),
        "engine_error": quant.get("engine_error") or request.get("engine_error"),
        "created_at": run.get("finishedAt"),
        "disclaimer": "历史回测 · 非真实收益 · 不代表未来",
    }


def list_backtests(conn: Any, user_id: int, limit: int = 50) -> dict[str, Any]:
    from services.strategy import strategy_store

    projects = strategy_store.list_projects(user_id).get("projects") or []
    quant_projects = {
        str(p["id"]): p for p in projects if (p.get("config") or {}).get("quant")
    }
    runs: list[dict[str, Any]] = []
    for project_id in quant_projects:
        runs.extend(strategy_store.list_runs(user_id, project_id).get("runs") or [])
    runs.sort(key=lambda r: str(r.get("finishedAt") or ""), reverse=True)
    items = []
    for run in runs[:limit]:
        result = run.get("result") or {}
        request = run.get("request") or {}
        metrics = _h5_metrics(result.get("metrics") or {})
        date_range = result.get("date_range") or {}
        factors = request.get("quant_factors") or []
        items.append({
            "id": str(run["id"]),
            "name": run.get("name"),
            "factors": _row_factor_meta({"factors": factors}),
            "universe": request.get("universe") or "hs300",
            "range": f"{date_range.get('start') or '—'} ~ {date_range.get('end') or '—'}",
            "start_date": date_range.get("start"),
            "end_date": date_range.get("end"),
            "cumulative": metrics.get("cumulative"),
            "benchmark_return": metrics.get("benchmark_return"),
            "shortened": bool((result.get("quant") or {}).get("shortened")),
            "created_at": run.get("finishedAt"),
            "engine": request.get("engine") or (result.get("meta") or {}).get("engine"),
        })
    return {"items": items, "note": "不同区间的记录不做横向比较。"}


def get_backtest(conn: Any, user_id: int, backtest_id: str) -> dict[str, Any] | None:
    from services.strategy import strategy_store

    try:
        run = strategy_store.get_run(user_id, str(backtest_id)).get("run")
    except (KeyError, ValueError):
        return None
    if not run:
        return None
    try:
        project = strategy_store.get_project(user_id, str(run.get("projectId"))).get("project") or {}
    except KeyError:
        return None
    if not (project.get("config") or {}).get("quant"):
        return None
    return _run_to_backtest(run)


def _correlation_matrix(series: dict[str, list[float]]) -> list[list[float | None]]:
    keys = list(FACTOR_BY_KEY)
    out: list[list[float | None]] = []
    for a in keys:
        row: list[float | None] = []
        for b in keys:
            r = 1.0 if a == b else _pearson(series.get(a, []), series.get(b, []))
            row.append(round(r, 2) if r is not None else None)
        out.append(row)
    return out


def _date_series(panel: dict[str, Any], values: list[float]) -> list[dict[str, Any]]:
    dates = panel["dates"]
    offset = max(0, len(dates) - len(values))
    return [{"date": dates[offset + i], "value": round(v * 100, 2)} for i, v in enumerate(values)]


def _np_matrix(panel: dict[str, Any], key: str) -> Any:
    """把按股票存储的因子序列转成 (股票 × 日期) 矩阵。"""
    symbols = panel["symbols"]
    n = len(panel["dates"])
    out = np.full((len(symbols), n), np.nan, dtype=float)
    rows = (panel.get("derived") or {}).get(key) or {}
    for i, symbol in enumerate(symbols):
        values = rows.get(symbol)
        if values is not None:
            if isinstance(values, np.ndarray):
                out[i] = values
            else:
                out[i] = np.fromiter((np.nan if v is None else v for v in values), dtype=float, count=n)
    return out


def _numpy_mats(panel: dict[str, Any]) -> dict[str, Any]:
    cached = panel.get("np_mats")
    if cached:
        return cached
    mats = {key: _np_matrix(panel, key) for key in FACTOR_BY_KEY}
    mats["_ret_next"] = _np_matrix(panel, "_ret_next")
    mats["_amount"] = _matrix_from_lists(panel["amount"], panel["symbols"], len(panel["dates"]))
    panel["np_mats"] = mats
    return mats


def _np_zscore(values: Any) -> Any:
    med = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - med))
    if mad > 0:
        spread = 1.4826 * mad
        values = np.clip(values, med - 3 * spread, med + 3 * spread)
    mean = np.nanmean(values)
    sd = np.nanstd(values)
    if not sd or not np.isfinite(sd):
        return np.zeros_like(values)
    return (values - mean) / sd


def _board_numpy(panel: dict[str, Any]) -> dict[str, Any]:
    mats = _numpy_mats(panel)
    dates = panel["dates"]
    n = len(dates)
    ns = len(panel["symbols"])
    start = max(21, n - 1 - MAX_HISTORY)
    end = n - 2
    symbol_idx = {s: i for i, s in enumerate(panel["symbols"])}
    st_mask = np.array([s in panel["st"] or s in panel["suspended"] for s in panel["symbols"]], dtype=bool)
    listed_days = []
    for symbol in panel["symbols"]:
        try:
            listed_days.append(date.fromisoformat(panel["list_date"].get(symbol) or "1900-01-01").toordinal())
        except ValueError:
            listed_days.append(0)
    listed_days = np.array(listed_days)
    liq_ok = np.isfinite(mats["liquidity"]) & (mats["liquidity"] >= MIN_AMOUNT)
    daily = {k: [] for k in FACTOR_BY_KEY}
    monthly = {k: [] for k in FACTOR_BY_KEY}
    ic_series = {k: [] for k in FACTOR_BY_KEY}
    crowd_series = {k: [] for k in FACTOR_BY_KEY}
    level_series = {k: [] for k in FACTOR_BY_KEY}
    monthly_state: dict[str, tuple[set[int], set[int], str]] = {}
    amount = mats["_amount"]
    ret_next = mats["_ret_next"]
    for i in range(start, end + 1):
        day_ord = date.fromisoformat(dates[i]).toordinal()
        list_ok = (day_ord - listed_days) >= 60
        base = ~st_mask & list_ok & liq_ok[:, i]
        for key, meta in FACTOR_BY_KEY.items():
            raw = mats[key][:, i]
            valid = base & np.isfinite(raw)
            count = int(valid.sum())
            if count < 20:
                continue
            idx = np.where(valid)[0]
            values = raw[idx]
            level_series[key].append(float(np.nanmedian(values)))
            z = _np_zscore(values)
            sign = -1.0 if meta["direction"] == "low" else 1.0
            scores = z * sign
            order = np.argsort(scores, kind="stable")
            k = max(1, int(count * 0.2))
            top_idx = idx[order[-k:]]
            bottom_idx = idx[order[:k]]
            top_r = ret_next[top_idx, i]
            bottom_r = ret_next[bottom_idx, i]
            top_r = top_r[np.isfinite(top_r)]
            bottom_r = bottom_r[np.isfinite(bottom_r)]
            if len(top_r) and len(bottom_r):
                daily[key].append(float(top_r.mean() - bottom_r.mean()))
            rets = ret_next[idx, i]
            ok = np.isfinite(rets) & np.isfinite(values)
            if int(ok.sum()) >= 5:
                xs, ys = values[ok], rets[ok]
                if xs.std() > 0 and ys.std() > 0:
                    ic_series[key].append(float(np.corrcoef(xs, ys)[0, 1]))
            total_amount = float(np.nansum(amount[idx, i]))
            top_amount = float(np.nansum(amount[top_idx, i]))
            if total_amount > 0:
                crowd_series[key].append(top_amount / total_amount)
            month = _month_key(dates[i])
            prev = monthly_state.get(key)
            if prev is None or prev[2] != month:
                old_long, old_short = (prev[0], prev[1]) if prev else (set(), set())
                turnover = 0.0
                if old_long:
                    turnover += len(old_long - set(top_idx.tolist())) / max(1, len(old_long))
                if old_short:
                    turnover += len(old_short - set(bottom_idx.tolist())) / max(1, len(old_short))
                cost = turnover * COST_ONE_WAY
                monthly_state[key] = (set(top_idx.tolist()), set(bottom_idx.tolist()), month)
            else:
                top_idx, bottom_idx = np.array(sorted(prev[0])), np.array(sorted(prev[1]))
                cost = 0.0
            mt = ret_next[top_idx, i]
            mb = ret_next[bottom_idx, i]
            mt = mt[np.isfinite(mt)]
            mb = mb[np.isfinite(mb)]
            if len(mt) and len(mb):
                monthly[key].append(float(mt.mean() - mb.mean() - cost))
    level_pct = {}
    for key, values in level_series.items():
        if values:
            last = values[-1]
            level_pct[key] = sum(1 for v in values if v <= last) / len(values) * 100
    return {
        "daily": daily, "monthly": monthly, "ic": ic_series, "crowd": crowd_series,
        "level_pct": level_pct, "latest_raw": {},
    }


def _board_cache_path(data_date: str, range_key: str) -> Path:
    return _BOARD_CACHE_ROOT / f"board_{data_date}_{range_key}.json"


def _load_board_payload(data_date: str, range_key: str) -> dict[str, Any] | None:
    key = (data_date, range_key)
    now = time.time()
    with _CACHE_LOCK:
        hit = _BOARD_PAYLOAD_CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    path = _board_cache_path(data_date, range_key)
    try:
        wrapped = json.loads(path.read_text(encoding="utf-8"))
        if wrapped.get("version") != _BOARD_CACHE_VERSION:
            return None
        payload = wrapped.get("payload")
        if not isinstance(payload, dict) or payload.get("data_date") != data_date:
            return None
        with _CACHE_LOCK:
            _BOARD_PAYLOAD_CACHE[key] = (now, payload)
        return payload
    except (OSError, ValueError, TypeError):
        return None


def _save_board_payload(data_date: str, range_key: str, payload: dict[str, Any]) -> None:
    key = (data_date, range_key)
    with _CACHE_LOCK:
        _BOARD_PAYLOAD_CACHE[key] = (time.time(), payload)
    path = _board_cache_path(data_date, range_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps({"version": _BOARD_CACHE_VERSION, "payload": payload}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        # 缓存失败不影响主流程；下次请求重新计算。
        pass


def warm_board(conn: Any) -> None:
    """启动预热：把 board 的 1m/1y 响应写入内存与磁盘缓存。"""
    for range_key in ("1m", "1y"):
        factor_board(conn, range_key)


def factor_board(conn: Any, range_key: str = "1m") -> dict[str, Any]:
    range_key = "1y" if range_key == "1y" else "1m"
    row = rules.one(conn, "SELECT MAX(trade_date)::text AS d FROM md_daily_bar WHERE adjust='hfq'")
    data_date = _date((row or {}).get("d"))
    if data_date:
        cached = _load_board_payload(data_date, range_key)
        if cached is not None:
            return cached
    panel = _load_panel(conn, "board")
    cache_key = (panel["data_date"], "board")
    now = time.time()
    with _CACHE_LOCK:
        hit = _BOARD_CACHE.get(cache_key)
    if hit and now - hit[0] < _CACHE_TTL:
        payload = _board_payload(panel, hit[1], range_key)
        _save_board_payload(panel["data_date"], range_key, payload)
        return payload
    if np is not None:
        board = _board_numpy(panel)
        with _CACHE_LOCK:
            _BOARD_CACHE[cache_key] = (now, board)
        payload = _board_payload(panel, board, range_key)
        _save_board_payload(panel["data_date"], range_key, payload)
        return payload
    dates = panel["dates"]
    n = len(dates)
    start = max(21, n - 1 - MAX_HISTORY)
    end = n - 2
    monthly: dict[str, list[float]] = {k: [] for k in FACTOR_BY_KEY}
    daily: dict[str, list[float]] = {k: [] for k in FACTOR_BY_KEY}
    ic_series: dict[str, list[float]] = {k: [] for k in FACTOR_BY_KEY}
    crowd_series: dict[str, list[float]] = {k: [] for k in FACTOR_BY_KEY}
    level_series: dict[str, list[float]] = {k: [] for k in FACTOR_BY_KEY}
    monthly_state: dict[str, tuple[set[str], set[str], str]] = {}
    latest_raw: dict[str, dict[str, float]] = {}

    for i in range(start, end + 1):
        raws = _cross_section(panel, i, FACTOR_BY_KEY.keys())
        for key, meta in FACTOR_BY_KEY.items():
            values = raws.get(key) or {}
            if len(values) < 20:
                continue
            ordered_values = sorted(values.values())
            level_series[key].append(ordered_values[len(ordered_values) // 2])
            z = _standardize(values)
            sign = -1.0 if meta["direction"] == "low" else 1.0
            directed = {s: v * sign for s, v in z.items()}
            ordered = sorted(directed.items(), key=lambda kv: kv[1], reverse=True)
            k = max(1, int(len(ordered) * 0.2))
            top = {s for s, _ in ordered[:k]}
            bottom = {s for s, _ in ordered[-k:]}
            rets = {s: _ret_next(panel, s, i) for s in set(top) | set(bottom)}
            top_r = [rets[s] for s in top if rets.get(s) is not None]
            bot_r = [rets[s] for s in bottom if rets.get(s) is not None]
            if top_r and bot_r:
                daily[key].append(sum(top_r) / len(top_r) - sum(bot_r) / len(bot_r))
            # IC：原始因子值与下一日收益的 Pearson；只用当天有值且可交易的样本。
            xs, ys = [], []
            for symbol, value in values.items():
                r = _ret_next(panel, symbol, i)
                if r is not None:
                    xs.append(value)
                    ys.append(r)
            ic = _pearson(xs, ys)
            if ic is not None:
                ic_series[key].append(ic)
            # 拥挤度：多头组合成交额占全市场成交额。
            total_amount = sum((panel["amount"].get(s) or [None] * n)[i] or 0.0 for s in values)
            top_amount = sum((panel["amount"].get(s) or [None] * n)[i] or 0.0 for s in top)
            if total_amount > 0:
                crowd_series[key].append(top_amount / total_amount)
            # 月度调仓多空收益。
            month = _month_key(dates[i])
            prev = monthly_state.get(key)
            if prev is None or prev[2] != month:
                old_long, old_short = (prev[0], prev[1]) if prev else (set(), set())
                turnover = 0.0
                if old_long:
                    turnover += len(old_long - top) / max(1, len(old_long))
                if old_short:
                    turnover += len(old_short - bottom) / max(1, len(old_short))
                cost = turnover * COST_ONE_WAY
                monthly_state[key] = (top, bottom, month)
            else:
                top, bottom = prev[0], prev[1]
                cost = 0.0
            mt = [(_ret_next(panel, s, i) or 0.0) for s in top if _ret_next(panel, s, i) is not None]
            mb = [(_ret_next(panel, s, i) or 0.0) for s in bottom if _ret_next(panel, s, i) is not None]
            if mt and mb:
                monthly[key].append(sum(mt) / len(mt) - sum(mb) / len(mb) - cost)
        if i == n - 2:
            for key, meta in FACTOR_BY_KEY.items():
                latest_raw[key] = dict(raws.get(key) or {})

    level_pct = {}
    for key, values in level_series.items():
        if values:
            last = values[-1]
            level_pct[key] = sum(1 for v in values if v <= last) / len(values) * 100
    board = {
        "daily": daily,
        "monthly": monthly,
        "ic": ic_series,
        "crowd": crowd_series,
        "level_pct": level_pct,
        "latest_raw": latest_raw,
    }
    with _CACHE_LOCK:
        _BOARD_CACHE[cache_key] = (now, board)
    payload = _board_payload(panel, board, range_key)
    _save_board_payload(panel["data_date"], range_key, payload)
    return payload


def _board_payload(panel: dict[str, Any], board: dict[str, Any], range_key: str) -> dict[str, Any]:
    factors = []
    for key, meta in FACTOR_BY_KEY.items():
        dvals = board["daily"].get(key) or []
        mvals = board["monthly"].get(key) or []
        r1 = _compound(dvals[-20:]) if len(dvals) >= 20 else _compound(dvals)
        r2 = _compound(mvals[-250:]) if len(mvals) >= 250 else _compound(mvals)
        current_pct = round(board.get("level_pct", {}).get(key), 1) if board.get("level_pct", {}).get(key) is not None else None
        ic = board["ic"].get(key) or []
        crowd = board["crowd"].get(key) or []
        crowd_now = crowd[-1] if crowd else None
        crowd_pct = (sum(1 for v in crowd if crowd_now is not None and v <= crowd_now) / len(crowd) * 100) if crowd else None
        factors.append({
            **meta,
            "return_1m": _pct(r1),
            "return_1y": _pct(r2),
            "percentile": current_pct,
            "ic_mean": round(sum(ic[-60:]) / len(ic[-60:]), 3) if ic[-60:] else None,
            "ic_win": round(sum(1 for v in ic[-60:] if v > 0) / len(ic[-60:]) * 100, 0) if ic[-60:] else None,
            "crowding": round(crowd_now * 100, 1) if crowd_now is not None else None,
            "crowding_percentile": round(crowd_pct, 0) if crowd_pct is not None else None,
            "crowding_level": "high" if (crowd_pct or 0) >= 80 else "mid" if (crowd_pct or 0) >= 60 else "low",
            "series": _date_series(panel, dvals[-20:] if range_key == "1m" else mvals[-250:]),
        })
    ordered = sorted(factors, key=lambda f: (f.get("return_1m") is None, -(f.get("return_1m") or 0)))
    style = _market_style(factors)
    return {
        "range": "1m" if range_key != "1y" else "1y",
        "range_label": "近 1 月" if range_key != "1y" else "近 1 年",
        "range_label_en": "Last month" if range_key != "1y" else "Last year",
        "factors": ordered,
        "style": style,
        "correlations": _correlation_matrix(board["daily"]),
        "correlation_keys": list(FACTOR_BY_KEY),
        "meta": {
            "universe": "全市场总市值前 500",
            "universe_en": "Top 500 by market cap",
            "definition": "做多因子前 20% 等权、做空后 20% 等权；近 1 月逐日累计，近 1 年按月调仓并扣单边 0.1% 成本。",
            "percentile_definition": "分位只描述该因子当前取值在当日横截面中的位置，不表达好坏。",
            "frequency": "每交易日收盘后更新",
            "frequency_en": "Updated after each close",
            "risk_free": RISK_FREE,
        },
        "data_date": panel["data_date"],
        "disclaimer": "历史数据，不代表未来；不构成投资建议。",
    }


def _market_style(factors: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [f for f in factors if f.get("return_1m") is not None]
    top = sorted(valid, key=lambda f: f["return_1m"], reverse=True)[:2]
    tags = [f["name"] for f in top[:3]]
    if len(top) >= 2 and top[0]["return_1m"] > 0 and top[1]["return_1m"] > 0:
        key = "attack"
    elif len(top) >= 2 and top[0]["return_1m"] < 0 and top[1]["return_1m"] < 0:
        key = "defense"
    else:
        key = "balanced"
    label = {"attack": "进攻", "defense": "防御", "balanced": "均衡"}[key]
    label_en = {"attack": "Offensive", "defense": "Defensive", "balanced": "Balanced"}[key]
    if len(top) < 2:
        sentence = "因子样本不足，暂不判断市场风格。"
        sentence_en = "Not enough factor history to judge the current style."
    else:
        zh, en = _STYLE_TEXT[key]
        sentence = zh.format(a=top[0]["name"], b=top[1]["name"], tags="、".join(tags))
        sentence_en = en.format(a=top[0]["name_en"], b=top[1]["name_en"], tags=", ".join(f["name_en"] for f in top[:3]))
    return {
        "key": key, "label": label, "label_en": label_en, "sentence": sentence, "sentence_en": sentence_en,
        "tags": tags, "tags_en": [f["name_en"] for f in top[:3]],
        "strongest": top[0]["key"] if top else None,
        "strongest_name": top[0]["name"] if top else None,
        "strongest_name_en": top[0]["name_en"] if top else None,
        "note": "只描述当下，不代表接下来。", "note_en": "Describes the present only; it does not predict what comes next.",
        "method": "取 6 个因子近 20 日多空收益排序：前二均为正→进攻，均为负→防御，其余→均衡。",
        "method_en": "Ranks six factors by 20-day long-short return: top two positive → offensive, both negative → defensive, otherwise balanced.",
    }


def factor_detail(conn: Any, key: str) -> dict[str, Any] | None:
    if key not in FACTOR_BY_KEY:
        return None
    board = factor_board(conn, "1m")
    panel = _load_panel(conn, "board")
    item = next((f for f in board["factors"] if f["key"] == key), None)
    if not item:
        return None
    meta = FACTOR_BY_KEY[key]
    # factor_board 的公开响应不暴露原始截面；这里重新取最新一天。
    latest_idx = max(21, len(panel["dates"]) - 2)
    values = _cross_section(panel, latest_idx, [key], require_liquidity=False).get(key, {})
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    top = [{"code": s, "name": panel["name"].get(s, s), "value": float(round(v, 4))} for s, v in ordered[:5]]
    bottom = [{"code": s, "name": panel["name"].get(s, s), "value": float(round(v, 4))} for s, v in ordered[-5:]]
    ic = item.get("ic_mean")
    ic_win = item.get("ic_win")
    crowd_pct = item.get("crowding_percentile")
    if ic is None:
        effectiveness = "历史 IC 样本不足，暂不判断有效性。"
        effectiveness_en = "Not enough IC history to judge efficacy."
    elif ic >= 0.03 and (ic_win or 0) >= 55:
        effectiveness = f"近 60 日 IC 均值 {ic:.3f}，方向命中 {int(ic_win or 0)}%，历史有效性尚可。"
        effectiveness_en = f"60-day IC mean {ic:.3f}, hit rate {int(ic_win or 0)}%; efficacy is acceptable."
    elif ic <= -0.02:
        effectiveness = f"近 60 日 IC 均值 {ic:.3f}，方向偏反向，历史有效性走弱。"
        effectiveness_en = f"60-day IC mean {ic:.3f}; the direction has weakened."
    else:
        effectiveness = f"近 60 日 IC 均值 {ic:.3f}，方向命中 {int(ic_win or 0)}%，有效性一般。"
        effectiveness_en = f"60-day IC mean {ic:.3f}, hit rate {int(ic_win or 0)}%; efficacy is average."
    if crowd_pct is None:
        crowding = "拥挤度样本不足，暂不判断。"
        crowding_en = "Not enough crowding history to judge."
    elif crowd_pct >= 80:
        crowding = f"多头成交额占全市场 {item.get('crowding')}%，历史分位 {int(crowd_pct)}%，拥挤度偏高。"
        crowding_en = f"Long book is {item.get('crowding')}% of market turnover, at the {int(crowd_pct)}th percentile; crowding is high."
    else:
        crowding = f"多头成交额占全市场 {item.get('crowding')}%，历史分位 {int(crowd_pct)}%，拥挤度未到偏高区间。"
        crowding_en = f"Long book is {item.get('crowding')}% of market turnover, at the {int(crowd_pct)}th percentile; crowding is not high."
    if (crowd_pct or 0) >= 80:
        fails = "拥挤度回落或风格反转时，多空收益可能先于基本面收敛，需要复核。"
        fails_en = "If crowding falls or style reverses, the long-short spread may converge before fundamentals do."
    elif ic is not None and ic < 0:
        fails = "当 IC 继续走弱、或与主流因子相关性明显上升时，这套方向容易失效。"
        fails_en = "The direction can fail if IC keeps weakening or correlation with mainstream factors rises."
    else:
        fails = "当市场风格切换、该因子与动量/波动因子的相关性显著上升时，多空收益可能收敛。"
        fails_en = "The spread can converge if market style changes or correlation with momentum/volatility rises."
    return {
        **item,
        "explain": meta["plain"] + "。分位只描述取值大小，不表达好坏。",
        "explain_en": meta["plain_en"] + ". The percentile describes the value's position, not whether it is good.",
        "conclusions": [
            {"key": "history", "label": "历史有效性", "label_en": "Historical efficacy", "text": effectiveness, "text_en": effectiveness_en},
            {"key": "crowding", "label": "拥挤度", "label_en": "Crowding", "text": crowding, "text_en": crowding_en},
            {"key": "failure", "label": "何时失效", "label_en": "When it can fail", "text": fails, "text_en": fails_en},
        ],
        "top": top,
        "bottom": bottom,
        "footer": "分位只描述取值大小，不代表好坏；历史数据不代表未来。",
        "data_date": board["data_date"],
    }


def _overview_counts(conn: Any, user_id: int) -> dict[str, Any]:
    strategies = list_strategies(conn, user_id).get("items") or []
    drafts = list_drafts(conn, user_id).get("items") or []
    backtests = list_backtests(conn, user_id).get("items") or []
    papers = list_papers(conn, user_id).get("items") or []
    latest = backtests[0].get("range") if backtests else None
    return {
        "strategies": len(strategies), "drafts": len(drafts), "backtests": len(backtests),
        "papers": sum(1 for p in papers if str(p.get("status")) == "active"),
        "latest_backtest": latest,
    }


def _focus(conn: Any, user_id: int, board: dict[str, Any], counts: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in (list_strategies(conn, user_id).get("items") or []):
        deviation = _num(row.get("deviation"))
        status = str(row.get("status") or "tracking")
        if status != "tracking" or (deviation is not None and abs(deviation) >= 1):
            items.append({
                "type": "strategy", "id": row.get("id"), "title": f"策略「{row.get('name')}」需要关注",
                "title_en": f"Strategy “{row.get('name')}” needs attention",
                "detail": f"相对回测偏离 {deviation:+.2f}%" if deviation is not None else "策略状态为跟进关注",
                "detail_en": f"Deviation vs backtest {deviation:+.2f}%" if deviation is not None else "Strategy is marked for attention",
                "deviation": abs(deviation or 0), "link": f"/quant/strategies/{row.get('id')}",
                "severity": 0,
            })
    for row in (list_papers(conn, user_id).get("items") or []):
        deviation = _num(row.get("deviation"))
        if deviation is not None and abs(deviation) >= 1:
            items.append({
                "type": "paper", "id": row.get("id"), "title": f"模拟盘「{row.get('name')}」偏离回测",
                "title_en": f"Paper account “{row.get('name')}” deviates from backtest",
                "detail": f"累计偏离 {deviation:+.2f}%，可查看持仓与交易记录",
                "detail_en": f"Deviation {deviation:+.2f}%; view positions and trades",
                "deviation": abs(deviation), "link": f"/quant/papers/{row.get('id')}", "severity": 1,
            })
    for factor in board.get("factors") or []:
        if factor.get("crowding_level") == "high":
            items.append({
                "type": "factor", "id": factor["key"], "title": f"因子「{factor['name']}」拥挤度偏高",
                "title_en": f"Factor “{factor['name_en']}” is crowded",
                "detail": f"拥挤度历史分位 {int(factor.get('crowding_percentile') or 0)}%",
                "detail_en": f"Crowding percentile {int(factor.get('crowding_percentile') or 0)}%",
                "deviation": factor.get("crowding_percentile") or 0, "link": f"/quant/factors?open={factor['key']}",
                "severity": 2,
            })
    if counts.get("drafts"):
        drafts = rules.rows(
            conn,
            "SELECT id,name FROM invest_quant_draft WHERE user_id=? AND (last_backtest_id IS NULL OR last_backtest_id='') ORDER BY id DESC LIMIT 5",
            (user_id,),
        )
        for row in drafts:
            items.append({
                "type": "todo", "id": row.get("id"), "title": f"草稿「{row.get('name')}」还没有回测",
                "title_en": f"Draft “{row.get('name')}” has no backtest",
                "detail": "用这套配置去回测，结果会保存到回测记录",
                "detail_en": "Run this config to save a backtest record",
                "deviation": 0, "link": f"/quant/strategies?tab=drafts", "severity": 3,
            })
    items.sort(key=lambda x: (x.get("severity", 9), -float(x.get("deviation") or 0)))
    return items


def overview(conn: Any, user_id: int) -> dict[str, Any]:
    board = factor_board(conn, "1m")
    counts = _overview_counts(conn, user_id)
    focus = _focus(conn, user_id, board, counts)
    style = board.get("style") or {}
    strongest = style.get("strongest_name")
    factor_status = f"{len(board.get('factors') or [])} 个 · 今天偏{style.get('label') or '均衡'}"
    factor_status_en = f"{len(board.get('factors') or [])} factors · {style.get('label_en') or 'Balanced'} today"
    if strongest:
        factor_status += f" · 最强 {strongest}"
        factor_status_en += f" · strongest {style.get('strongest_name_en') or strongest}"
    return {
        "data_date": board.get("data_date"),
        "style": style,
        "focus": {"count": len(focus), "items": focus[:6], "empty_text": "今天没有需要处理的"},
        "entries": [
            {
                "key": "factors", "title": "因子", "title_en": "Factors",
                "status": factor_status,
                "status_en": factor_status_en,
                "link": "/quant/factors",
            },
            {
                "key": "strategies", "title": "策略", "title_en": "Strategies",
                "status": f"{counts['strategies']} 个跟踪中 · {counts['drafts']} 个草稿",
                "status_en": f"{counts['strategies']} tracked · {counts['drafts']} drafts",
                "link": "/quant/strategies",
            },
            {
                "key": "backtests", "title": "回测", "title_en": "Backtests",
                "status": f"{counts['backtests']} 份记录 · 最近一份 {counts['latest_backtest'] or '—'}",
                "status_en": f"{counts['backtests']} records · latest {counts['latest_backtest'] or '—'}",
                "link": "/quant/backtests",
            },
            {
                "key": "papers", "title": "模拟盘", "title_en": "Paper trading",
                "status": f"{counts['papers']} 个运行中",
                "status_en": f"{counts['papers']} running",
                "link": "/quant/papers",
            },
            {
                "key": "community", "title": "社区", "title_en": "Community",
                "status": "策略、因子与热点讨论",
                "status_en": "Strategy, factor and market discussions",
                "link": "/community",
            },
        ],
        "counts": counts,
        "disclaimer": "历史数据，不代表未来；不构成投资建议。",
    }


# ---------------------------------------------------------------------------
# 草稿 / 策略 / 模拟盘 / 广场
# ---------------------------------------------------------------------------

def _draft_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"), "name": row.get("name"), "factors": _row_factor_meta(row),
        "universe": row.get("universe"), "universe_name": UNIVERSES.get(row.get("universe"), {}).get("name"),
        "project_id": row.get("project_id"),
        "last_backtest_id": row.get("last_backtest_id"), "created_at": row.get("created_at"),
    }


def list_drafts(conn: Any, user_id: int) -> dict[str, Any]:
    rows = rules.rows(
        conn,
        "SELECT id,name,factors,universe,project_id,last_backtest_id,created_at FROM invest_quant_draft "
        "WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    )
    return {"items": [_draft_payload(r) for r in rows]}


def create_draft(conn: Any, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
    selected = _normalize_factors(body.get("factors"))
    universe = _normalize_universe(body.get("universe"))
    name = str(body.get("name") or " + ".join(FACTOR_BY_KEY[f["key"]]["name"] for f in selected))[:80]
    row = rules.one(
        conn,
        "INSERT INTO invest_quant_draft (user_id,name,factors,universe,project_id,last_backtest_id,created_at,updated_at) "
        "VALUES (?,?,?::jsonb,?,?,?,to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'),to_char(NOW(),'YYYY-MM-DD HH24:MI:SS')) RETURNING *",
        (user_id, name, json.dumps(selected, ensure_ascii=False), universe, body.get("project_id"), body.get("last_backtest_id")),
    )
    return _draft_payload(row or {})


def delete_draft(conn: Any, user_id: int, draft_id: int) -> bool:
    conn.execute("DELETE FROM invest_quant_draft WHERE id=? AND user_id=?", (draft_id, user_id))
    return True


def _strategy_payload(row: dict[str, Any], snap: dict[str, Any] | None = None) -> dict[str, Any]:
    snap = snap or _row_json(row, "last_snapshot", {}) or {}
    deviation = _num((snap or {}).get("deviation"))
    status = str(row.get("status") or "tracking")
    attention = status != "tracking" or (deviation is not None and abs(deviation) >= 1)
    return {
        "id": row.get("id"), "name": row.get("name"), "factors": _row_factor_meta(row),
        "universe": row.get("universe"), "universe_name": UNIVERSES.get(row.get("universe"), {}).get("name"),
        "status": "attention" if attention else "tracking",
        "status_label": "跟进关注" if attention else "跟踪正常",
        "status_label_en": "Needs attention" if attention else "Tracking normally",
        "today": snap.get("today"), "drawdown": snap.get("max_drawdown"),
        "next_rebalance": snap.get("next_rebalance") or "下一个月初",
        "paper_id": row.get("paper_id"), "backtest_id": row.get("backtest_id"),
        "project_id": row.get("project_id"),
        "deviation": deviation, "created_at": row.get("created_at"),
    }


def list_strategies(conn: Any, user_id: int) -> dict[str, Any]:
    rows = rules.rows(
        conn,
        "SELECT * FROM invest_quant_strategy WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    )
    return {"items": [_strategy_payload(r, _strategy_snapshot(conn, user_id, r)) for r in rows]}


def create_strategy(conn: Any, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
    selected = _normalize_factors(body.get("factors"))
    universe = _normalize_universe(body.get("universe"))
    name = str(body.get("name") or " + ".join(FACTOR_BY_KEY[f["key"]]["name"] for f in selected))[:80]
    try:
        from services.invest import quant_re

        supported = quant_re.supports(selected)
    except Exception:
        supported = False
    pid = None
    if supported:
        pid = str(body.get("project_id") or "").strip() or _ensure_project(
            user_id, name, selected, universe
        )
    row = rules.one(
        conn,
        "INSERT INTO invest_quant_strategy (user_id,name,factors,universe,status,project_id,backtest_id,created_at,updated_at) "
        "VALUES (?,?,?::jsonb,?,'tracking',?,?,to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'),to_char(NOW(),'YYYY-MM-DD HH24:MI:SS')) RETURNING *",
        (user_id, name, json.dumps(selected, ensure_ascii=False), universe, pid, body.get("backtest_id")),
    )
    return _strategy_payload(row or {})


def _portfolio_beta(conn: Any, user_id: int) -> tuple[float | None, list[dict[str, Any]], set[str]]:
    holdings = rules.rows(conn, "SELECT code,shares,cost,weight FROM invest_portfolio WHERE user_id=?", (user_id,))
    total = sum((_num(h.get("weight")) or 0) for h in holdings) or 1.0
    weighted = 0.0
    covered = 0.0
    codes: set[str] = set()
    for row in holdings:
        code = str(row.get("code") or "")
        codes.add(code)
        try:
            risk = rules.one(
                conn,
                "SELECT beta_1y FROM md_risk_daily WHERE symbol=? ORDER BY trade_date DESC LIMIT 1",
                (rules._with_suffix(code),),
            )
            beta = _num((risk or {}).get("beta_1y"))
        except Exception:
            beta = None
        weight = (_num(row.get("weight")) or 0) / total
        if beta is not None:
            weighted += beta * weight
            covered += weight
    return (weighted / covered if covered else None), holdings, codes


def strategy_detail(conn: Any, user_id: int, strategy_id: int) -> dict[str, Any] | None:
    row = rules.one(
        conn,
        "SELECT * FROM invest_quant_strategy WHERE id=? AND user_id=?",
        (strategy_id, user_id),
    )
    if not row:
        return None
    payload = _strategy_payload(row, _strategy_snapshot(conn, user_id, row))
    backtest = get_backtest(conn, user_id, str(row["backtest_id"])) if row.get("backtest_id") else None
    beta, holdings, codes = _portfolio_beta(conn, user_id)
    overlap = sum(1 for h in (backtest or {}).get("holdings", []) if h.get("code") in codes)
    risk_compare = [
        {"label": "策略 β", "label_en": "Strategy beta", "value": (backtest or {}).get("metrics", {}).get("beta") if backtest else None},
        {"label": "组合 β", "label_en": "Portfolio beta", "value": round(beta, 2) if beta is not None else None},
        {"label": "持仓重叠", "label_en": "Holding overlap", "value": f"{overlap} 只" if backtest else "待补充"},
    ]
    return {
        **payload,
        "backtest": backtest,
        "paper": paper_detail(conn, user_id, int(row["paper_id"])) if row.get("paper_id") else None,
        "risk_compare": risk_compare,
        "rules": "综合分降序、月度调仓、前 20 只等权；只描述规则运行状态，不构成操作指令。",
    }


def delete_strategy(conn: Any, user_id: int, strategy_id: int) -> bool:
    conn.execute("DELETE FROM invest_quant_strategy WHERE id=? AND user_id=?", (strategy_id, user_id))
    return True


def _quant_projects(user_id: int) -> dict[str, dict[str, Any]]:
    from services.strategy import strategy_store

    projects = strategy_store.list_projects(user_id).get("projects") or []
    return {str(p["id"]): p for p in projects if (p.get("config") or {}).get("quant")}


def _strategy_for_project(conn: Any, user_id: int, project_id: str) -> dict[str, Any] | None:
    return rules.one(
        conn,
        "SELECT * FROM invest_quant_strategy WHERE user_id=? AND project_id=? ORDER BY id DESC LIMIT 1",
        (user_id, project_id),
    )


def _paper_run_return(conn: Any, user_id: int, strategy_row: dict[str, Any] | None, start: str, end: str) -> float | None:
    if not strategy_row or not strategy_row.get("backtest_id"):
        return None
    bt = get_backtest(conn, user_id, str(strategy_row["backtest_id"]))
    if not bt:
        return None
    points = [
        p for p in (bt.get("curve") or [])
        if start <= str(p.get("date")) <= end and p.get("nav") is not None
    ]
    if len(points) < 2 or not points[0]["nav"]:
        return None
    return (float(points[-1]["nav"]) / float(points[0]["nav"]) - 1.0) * 100


def _paper_summary(conn: Any, user_id: int, account: dict[str, Any], strategy_row: dict[str, Any] | None = None) -> dict[str, Any]:
    from services.paper import paper_store

    account_id = int(account["id"])
    initial = float(account.get("initialCash") or 1.0) or 1.0
    try:
        equity = paper_store.list_equity(user_id, account_id).get("equity") or []
    except Exception:
        equity = []
    navs = [float(e.get("totalEquity") or initial) / initial for e in equity] or [1.0]
    cumulative = (navs[-1] - 1.0) * 100
    today = None
    if len(navs) >= 2 and navs[-2]:
        today = (navs[-1] / navs[-2] - 1.0) * 100
    try:
        positions = paper_store.list_positions(user_id, account_id)
    except Exception:
        positions = []
    start = str(account.get("firstSettlementDate") or "")
    end = str(account.get("lastSettledDate") or account.get("nextSettlementDate") or "")
    bt_return = _paper_run_return(conn, user_id, strategy_row, start, end) if start and end else None
    deviation = round(cumulative - bt_return, 2) if bt_return is not None else None
    rets = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1]]
    annual = None
    if len(navs) > 1 and navs[-1] > 0:
        annual = (navs[-1] ** (252.0 / max(1, len(navs) - 1)) - 1.0) * 100
    vol = (_stdev(rets) or 0.0) * math.sqrt(252) * 100
    sharpe = ((annual or 0.0) / 100.0 - RISK_FREE) / (vol / 100.0) if vol > 0 else None
    attention = (deviation is not None and abs(deviation) >= 1) or bool(account.get("lastErrorCode"))
    return {
        "id": account_id,
        "name": account.get("name"),
        "status": account.get("status") or "active",
        "initial_cash": initial,
        "start_date": start,
        "data_date": end,
        "run_days": len(equity),
        "cumulative": _pct(cumulative),
        "today": _pct(today),
        "deviation": deviation,
        "position_count": len(positions),
        "max_drawdown": _pct(_max_drawdown(navs)),
        "annual_return": _pct(annual),
        "volatility": _pct(vol),
        "sharpe": float(round(sharpe, 2)) if sharpe is not None else None,
        "next_settlement": account.get("nextSettlementDate"),
        "attention": attention,
        "positions": positions,
        "equity": equity,
    }


def _is_reusable_paper_project(config: dict[str, Any]) -> bool:
    """根项目/本地降级项目只存回测记录，不能被改造成可执行模拟盘项目。"""
    return bool(
        str(config.get("strategy_code") or "").strip()
        and not config.get("quant_root")
        and not config.get("quant_local_only")
    )


def _strategy_snapshot(conn: Any, user_id: int, row: dict[str, Any]) -> dict[str, Any]:
    summary = None
    if row.get("paper_id"):
        try:
            from services.paper import paper_store

            account = paper_store.get_account(user_id, int(row["paper_id"])).get("account") or {}
            summary = _paper_summary(conn, user_id, account, row)
        except Exception:
            summary = None
    return summary or {}


def create_paper(conn: Any, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
    from services.paper import paper_store
    from services.strategy import strategy_store
    from services.invest import quant_re

    source_type = str(body.get("source_type") or body.get("source") or "draft")
    source_id = body.get("source_id") or body.get("draft_id") or body.get("strategy_id") or body.get("backtest_id")
    factors = None
    universe = "hs300"
    name = str(body.get("name") or "").strip()
    project_id = None
    strategy_row = None
    backtest_id = None
    if source_type == "draft":
        draft = rules.one(conn, "SELECT * FROM invest_quant_draft WHERE id=? AND user_id=?", (source_id, user_id))
        if not draft:
            raise QuantDataError("草稿不存在")
        factors = _row_json(draft, "factors", [])
        universe = draft.get("universe") or "hs300"
        name = name or str(draft.get("name") or "量化模拟盘")
        project_id = draft.get("project_id")
        backtest_id = draft.get("last_backtest_id")
    elif source_type == "strategy":
        strategy_row = rules.one(conn, "SELECT * FROM invest_quant_strategy WHERE id=? AND user_id=?", (source_id, user_id))
        if not strategy_row:
            raise QuantDataError("策略不存在")
        factors = _row_json(strategy_row, "factors", [])
        universe = strategy_row.get("universe") or "hs300"
        name = name or str(strategy_row.get("name") or "量化模拟盘")
        project_id = strategy_row.get("project_id")
        backtest_id = strategy_row.get("backtest_id")
    elif source_type == "backtest":
        bt = get_backtest(conn, user_id, str(source_id))
        if not bt:
            raise QuantDataError("回测记录不存在")
        factors = [{"key": f["key"], "direction": f.get("chosen_direction") or f.get("direction")} for f in bt["factors"]]
        universe = bt.get("universe") or "hs300"
        name = name or f"{bt.get('name')} · 模拟"
        project_id = bt.get("project_id")
        backtest_id = bt.get("id")
    else:
        factors = _normalize_factors(body.get("factors"))
    selected = _normalize_factors(factors)
    if not quant_re.supports(selected):
        raise QuantDataError("RE 暂不支持该因子组合的模拟盘（缺少基本面字段）；可先保存为草稿")
    name = name or " + ".join(FACTOR_BY_KEY[f["key"]]["name"] for f in selected)
    pid = str(project_id or "").strip()
    if pid:
        try:
            source_project = strategy_store.get_project(user_id, pid).get("project") or {}
        except KeyError:
            source_project = {}
        cfg = source_project.get("config") or {}
        # 根项目/本地降级项目只用于存回测记录，不能改成可执行策略；
        # 开模拟盘时新建独立的 paper project，避免污染记录项目。
        if not _is_reusable_paper_project(cfg):
            pid = ""
    if pid:
        _ensure_project(user_id, name, selected, _normalize_universe(universe), project_id=pid)
    else:
        pid = _ensure_project(user_id, name, selected, _normalize_universe(universe))
    capital = _num(body.get("start_capital")) or 1_000_000.0
    account = paper_store.create_account(
        user_id,
        {"strategy_project_id": pid, "name": name, "initial_cash": capital},
    )
    account_id = int(account["id"])
    if source_type == "draft":
        conn.execute("UPDATE invest_quant_draft SET project_id=?, updated_at=to_char(NOW(),'YYYY-MM-DD HH24:MI:SS') WHERE user_id=? AND id=?", (pid, user_id, source_id))
    if strategy_row:
        conn.execute("UPDATE invest_quant_strategy SET paper_id=?, project_id=? WHERE id=?", (account_id, pid, strategy_row["id"]))
    else:
        row = rules.one(
            conn,
            "INSERT INTO invest_quant_strategy (user_id,name,factors,universe,status,project_id,backtest_id,paper_id,created_at,updated_at) "
            "VALUES (?,?,?::jsonb,?,'tracking',?,?,?,to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'),to_char(NOW(),'YYYY-MM-DD HH24:MI:SS')) RETURNING id",
            (user_id, name, json.dumps(selected, ensure_ascii=False), _normalize_universe(universe), pid, backtest_id, account_id),
        )
        if row:
            strategy_row = rules.one(conn, "SELECT * FROM invest_quant_strategy WHERE id=?", (row["id"],))
    return paper_detail(conn, user_id, account_id)


def paper_detail(conn: Any, user_id: int, paper_id: int) -> dict[str, Any] | None:
    from services.paper import paper_store
    from services.strategy import strategy_store

    try:
        data = paper_store.get_account(user_id, int(paper_id))
    except (KeyError, ValueError):
        return None
    account = data.get("account") or {}
    project_id = str(account.get("projectId") or "")
    try:
        project = strategy_store.get_project(user_id, project_id).get("project") or {}
    except KeyError:
        return None
    cfg = project.get("config") or {}
    if not cfg.get("quant"):
        return None
    strategy_row = _strategy_for_project(conn, user_id, project_id)
    summary = _paper_summary(conn, user_id, account, strategy_row)
    positions = []
    total_equity = float(account.get("totalEquity") or 0.0)
    for position in summary.get("positions") or []:
        value = position.get("marketValue")
        positions.append({
            "code": position.get("symbol"),
            "name": position.get("symbol"),
            "weight": round((float(value) / total_equity * 100), 2) if value and total_equity else 0.0,
            "price": position.get("markPrice"),
            "market_value": value,
        })
    try:
        fills = paper_store.list_fills(user_id, int(paper_id), limit=100).get("fills") or []
    except Exception:
        fills = []
    trades = [
        {
            "date": item.get("settlementDate"),
            "code": item.get("symbol"),
            "name": item.get("symbol"),
            "side": "buy" if str(item.get("side") or "").lower() in {"buy", "b"} else "sell",
            "weight_before": 0.0,
            "weight_after": 0.0,
            "weight_delta": 0.0,
            "price": item.get("price"),
            "quantity": item.get("quantity"),
            "simulated": True,
        }
        for item in fills
    ]
    curve = [
        {"date": point.get("date"), "nav": float(point.get("totalEquity") or 0) / (summary.get("initial_cash") or 1)}
        for point in (summary.get("equity") or [])
    ]
    metrics = {
        "cumulative": summary.get("cumulative"),
        "annual_return": summary.get("annual_return"),
        "max_drawdown": summary.get("max_drawdown"),
        "sharpe": summary.get("sharpe"),
        "volatility": summary.get("volatility"),
        "excess": summary.get("deviation"),
    }
    return {
        "id": int(paper_id),
        "name": account.get("name"),
        "status": "running" if account.get("status") == "active" else account.get("status"),
        "start_capital": summary.get("initial_cash"),
        "start_date": summary.get("start_date"),
        "data_date": summary.get("data_date"),
        "run_days": summary.get("run_days") or 0,
        "cumulative": summary.get("cumulative"),
        "today": summary.get("today"),
        "deviation": summary.get("deviation"),
        "metrics": metrics,
        "positions": positions,
        "trades": trades,
        "factors": _row_factor_meta({"factors": cfg.get("quant_factors") or []}),
        "universe": cfg.get("quant_universe") or "hs300",
        "universe_name": UNIVERSES.get(cfg.get("quant_universe") or "hs300", {}).get("name"),
        "curve": curve,
        "message": None if positions else "还没有持仓，等下一次调仓",
        "disclaimer": "模拟盘由 ResearchEngine 结算，只做记账，不接券商、不产生真实委托；历史记录，非建议。",
    }


def list_papers(conn: Any, user_id: int) -> dict[str, Any]:
    from services.paper import paper_store

    projects = _quant_projects(user_id)
    accounts = paper_store.list_accounts(user_id).get("accounts") or []
    items = []
    for account in accounts:
        pid = str(account.get("projectId") or "")
        if pid not in projects:
            continue
        strategy_row = _strategy_for_project(conn, user_id, pid)
        summary = _paper_summary(conn, user_id, account, strategy_row)
        items.append({
            "id": account.get("id"),
            "name": account.get("name"),
            "strategy_name": (strategy_row or {}).get("name") or account.get("projectName") or "—",
            "position_count": summary.get("position_count"),
            "run_days": summary.get("run_days"),
            "cumulative": summary.get("cumulative"),
            "today": summary.get("today"),
            "deviation": summary.get("deviation"),
            "status": account.get("status") or "active",
            "start_date": summary.get("start_date"),
        })
    return {"items": items}


def delete_paper(conn: Any, user_id: int, paper_id: int) -> bool:
    from services.paper import paper_store

    try:
        paper_store.update_account(user_id, int(paper_id), {"status": "closed"})
    except (KeyError, ValueError):
        return False
    return True


# ---------------------------------------------------------------------------
# 策略广场（示例模板；真实社区策略仍走 /api/strategy/plaza）
# ---------------------------------------------------------------------------

def _plaza_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    snap = row.get("snapshot") or {}
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except ValueError:
            snap = {}
    return snap if isinstance(snap, dict) else {}


def _plaza_item(row: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    snap = _plaza_snapshot(row)
    metrics = _h5_metrics(snap.get("metrics") or {})
    curve = snap.get("equity_curve") or []
    values = [float(p.get("value")) for p in curve if isinstance(p, dict) and p.get("value") is not None]
    author = row.get("author") or {}
    factors = snap.get("quant_factors") or []
    date_range = snap.get("date_range") or {}
    item = {
        "id": int(row["id"]),
        "title": row.get("title"),
        "author": author.get("display_name") or author.get("username") or "社区作者",
        "factors": _row_factor_meta({"factors": factors}),
        "universe": str(snap.get("universe") or "").lower(),
        "universe_name": snap.get("universe_label"),
        "annual_return": metrics.get("annual_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "curve": values[-60:],
        "followers": int(row.get("view_count") or 0),
        "followed": False,
        "is_demo": False,
        "range": snap.get("range_label") or (
            f"{date_range.get('start')} ~ {date_range.get('end')}" if date_range else "近 1 年"
        ),
    }
    if detail:
        item.update({
            "metrics": metrics,
            "curve_points": [
                {"date": p.get("date"), "nav": p.get("value")}
                for p in curve if isinstance(p, dict) and p.get("date") and p.get("value") is not None
            ],
            "curve": [
                {"date": p.get("date"), "nav": p.get("value")}
                for p in curve if isinstance(p, dict) and p.get("date") and p.get("value") is not None
            ],
            "note": "区间与基准均来自作者回测快照；不能与其它策略横向比较。",
            "body": row.get("body") or "",
        })
    return item


def list_plaza(conn: Any, user_id: int, sort: str = "followers") -> dict[str, Any]:
    from services.strategy import strategy_plaza_store

    sort_key = {"annual": "annual", "mdd": "mdd", "followers": "views"}.get(sort, "views")
    data = strategy_plaza_store.list_plaza_items(limit=100, sort=sort_key)
    items = [_plaza_item(row) for row in (data.get("items") or [])]
    label = {"annual": "收益榜", "mdd": "回撤榜", "followers": "关注榜"}.get(sort, "关注榜")
    return {
        "items": items,
        "sort": sort,
        "sort_label": label,
        "note": f"当前排序：{label}；年化与回撤取自作者回测快照，未做跨策略统一，不能横向比大小。",
        "disclaimer": "社区策略快照 · 历史数据不代表未来 · 不构成推荐。",
    }


def get_plaza(conn: Any, user_id: int, plaza_id: int) -> dict[str, Any] | None:
    from services.strategy import strategy_plaza_store

    row = strategy_plaza_store.get_plaza_item(int(plaza_id), bump_view=False)
    return _plaza_item(row, detail=True) if row else None


def copy_plaza(conn: Any, user_id: int, plaza_id: int) -> dict[str, Any]:
    from services.strategy import strategy_plaza_store

    row = strategy_plaza_store.get_plaza_item(int(plaza_id), bump_view=False)
    if not row:
        raise QuantDataError("策略不存在")
    snap = _plaza_snapshot(row)
    factors = snap.get("quant_factors") or []
    if not factors:
        raise QuantDataError("该策略没有手机端因子配置，无法复制到草稿")
    return create_draft(conn, user_id, {
        "name": f"{row.get('title')}（副本）", "factors": factors,
        "universe": snap.get("quant_universe") or "hs300",
    })


def follow_plaza(conn: Any, user_id: int, plaza_id: int, followed: bool) -> dict[str, Any]:
    """关注暂不落库：复用现有广场 view_count，前端用本机收藏状态。"""
    from services.strategy import strategy_plaza_store

    row = strategy_plaza_store.get_plaza_item(int(plaza_id), bump_view=False)
    if not row:
        raise QuantDataError("策略不存在")
    return {"followed": bool(followed), "followers": int(row.get("view_count") or 0)}


# ---------------------------------------------------------------------------
# 一句话建策略：AI 负责解析，规则兜底；只翻译，不推荐。
# ---------------------------------------------------------------------------

_PARSE_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("便宜", "低估", "估值", "pe", "市盈率"), "value", "high"),
    (("贵", "高估"), "value", "low"),
    (("涨", "动量", "趋势", "强势"), "momentum", "high"),
    (("跌", "反转", "弱势"), "momentum", "low"),
    (("波动", "稳", "平稳", "低波"), "volatility", "low"),
    (("质量", "roe", "赚钱", "盈利"), "quality", "high"),
    (("成长", "增长", "营收"), "growth", "high"),
    (("流动", "成交", "活跃"), "liquidity", "high"),
)


def _parse_intent_rules(text: str) -> dict[str, Any]:
    q = (text or "").lower()
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for words, key, direction in _PARSE_RULES:
        if key in seen:
            continue
        if any(word in q for word in words):
            seen.add(key)
            found.append({"key": key, "direction": direction})
    understood = " · ".join(
        f"{FACTOR_BY_KEY[f['key']]['name']}（{FACTOR_BY_KEY[f['key']]['low_label'] if f['direction'] == 'low' else FACTOR_BY_KEY[f['key']]['high_label']}）" for f in found
    )
    return {
        "ok": True, "ai": False, "factors": found[:4], "understood": understood,
        "need_more": len(found) < 2,
        "message": None if len(found) >= 2 else "再多说一个方向，就能生成实验。",
    }


def parse_intent(text: str) -> dict[str, Any]:
    q = (text or "").strip()
    if not q:
        raise QuantDataError("请先说一句想要什么")
    try:
        from ai.router import available_task, run_task

        if available_task("invest.condition"):
            out = run_task(
                "invest.condition",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "把用户的一句话映射到量化因子与方向，只输出 JSON："
                            '{"factors":[{"key":"value|momentum|volatility|quality|growth|liquidity","direction":"high|low"}],'
                            '"understood":"..."}。不要推荐股票、不要编造数值；识别不足 2 个时 factors 可为空。'
                        ),
                    },
                    {"role": "user", "content": q},
                ],
            )
            data = out.get("data") if isinstance(out, dict) else None
            if not isinstance(data, dict):
                data = json.loads(str(out.get("content") or "{}"))
            raw = data.get("factors") if isinstance(data, dict) else None
            if isinstance(raw, list):
                selected: list[dict[str, str]] = []
                seen: set[str] = set()
                for item in raw:
                    if isinstance(item, str):
                        item = {"key": item}
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "").strip()
                    meta = FACTOR_BY_KEY.get(key)
                    if not key or not meta or key in seen:
                        continue
                    direction = str(item.get("direction") or "").strip().lower()
                    if direction not in ("high", "low"):
                        direction = meta["direction"]
                    seen.add(key)
                    selected.append({"key": key, "direction": direction})
                selected = selected[:4]
                if selected:
                    understood = " · ".join(
                        f"{FACTOR_BY_KEY[f['key']]['name']}（{FACTOR_BY_KEY[f['key']]['low_label'] if f['direction'] == 'low' else FACTOR_BY_KEY[f['key']]['high_label']}）"
                        for f in selected
                    )
                    return {
                        "ok": True, "ai": True, "factors": selected, "understood": understood,
                        "need_more": len(selected) < 2,
                        "message": None if len(selected) >= 2 else "再多说一个方向，就能生成实验。",
                    }
    except Exception:
        pass
    return _parse_intent_rules(q)


# ---------------------------------------------------------------------------
# AI 点评：按需生成；失败返回 available=false，前端隐藏区块。
# ---------------------------------------------------------------------------

def _ai_points(section: dict[str, Any]) -> list[dict[str, str]]:
    points = section.get("points") or section.get("items") or []
    out = []
    for point in points if isinstance(points, list) else []:
        if isinstance(point, dict):
            label = str(point.get("label") or point.get("k") or point.get("title") or "").strip()
            detail = str(point.get("detail") or point.get("v") or point.get("text") or "").strip()
            if label:
                out.append({"label": label[:24], "detail": detail[:80]})
    if not out and section.get("body"):
        out.append({"label": str(section.get("title") or "要点")[:24], "detail": str(section["body"])[:80]})
    return out[:4]


def _clip50(text: Any) -> str:
    value = str(text or "").strip()
    if len(value) <= 50:
        return value
    return value[:49].rstrip("，。；、,.; ") + "…"


def ai_commentary(
    kind: str,
    payload: dict[str, Any],
    *,
    user_id: int | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    from services.invest import agent_prompts, ai_cache

    task = "invest.backtest" if kind == "backtest" else "invest.paper" if kind == "paper" else "invest.quant"
    default = (
        agent_prompts.BACKTEST_SYSTEM
        if kind == "backtest"
        else agent_prompts.PAPER_COMMENTARY_SYSTEM if kind == "paper" else agent_prompts.QUANT_COMMENTARY_SYSTEM
    )
    prompt = agent_prompts.resolve_prompt(user_id, task, default)
    key = ai_cache.make_key(task, payload, prompt)
    if not refresh:
        cached = ai_cache.get(user_id, "commentary", key)
        if cached:
            return {**cached, "cached": True}
    try:
        from ai.router import available_task, run_task

        if not available_task(task):
            return {"available": False}
        out = run_task(
            task,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        data = out.get("data") if isinstance(out, dict) else None
        if not isinstance(data, dict):
            data = json.loads(str(out.get("content") or "{}"))
        summary = str(data.get("summary") or "").strip()
        if not summary:
            for section in data.get("sections") or []:
                if isinstance(section, dict) and section.get("body"):
                    summary = str(section["body"])
                    break
                if isinstance(section, dict):
                    for point in section.get("points") or []:
                        if isinstance(point, dict) and point.get("detail"):
                            summary = str(point["detail"])
                            break
                    if summary:
                        break
        result = {"available": True, "summary": _clip50(summary or "数据不足，暂无法给出结论。"), "aspects": []}
        ai_cache.put(user_id, "commentary", key, result)
        return result
    except Exception:
        return {"available": False}
