# -*- coding: utf-8 -*-
"""H5 条件选股：中文条件解析 + 全市场筛选。

只使用服务层已有数据：
- invest_stocks：价格/市值/PE/股息/行业；
- md_valuation_daily：近 5 年 PE 分位；
- fin_indicator / fin_income_statement：ROE、近 3 年净利润；
- md_daily_bar(hfq)：涨幅、回撤、60 日新高、均线、量能、连阳。

资金流（主力净流入/连续流入）当前数据平台未提供，解析会标记为
``supported=false``，不伪造数据，也不执行该条件。
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable

from services.invest import rules

DATA_DISCLAIMER = "历史 EOD 数据 · 不含实时与资金流 · 非投资建议"


def _num(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _op(text: str, default: str = "max") -> str:
    # 先归一否定式，避免“不超过”被“超过”误判为下限。
    normalized = (
        (text or "").replace("不低于", "≥").replace("不少于", "≥")
        .replace("不高于", "≤").replace("不超过", "≤")
    )
    if re.search(r"大于等于|大于|高于|超过|>=|>|≥", normalized):
        return "min"
    if re.search(r"小于等于|小于|低于|少于|<=|<|≤", normalized):
        return "max"
    return default


def _value(text: str) -> float | None:
    # 条件里常带“近 5 日”“60 日”等窗口数字，阈值取最后一个数字。
    matches = re.findall(r"(-?\d+(?:\.\d+)?)", text)
    return float(matches[-1]) if matches else None


_SPECS: tuple[dict[str, Any], ...] = (
    {
        "key": "pe_percentile", "label": "PE 分位", "label_en": "PE percentile",
        "pattern": r"(?:PE|市盈率).{0,8}?分位|估值分位", "unit": "%",
        "metric": "pe_percentile",
    },
    {
        "key": "max_drawdown_1y", "label": "近 1 年最大回撤", "label_en": "1Y max drawdown",
        "pattern": r"(?:近)?1年最大回撤|最大回撤", "unit": "%",
        "metric": "max_drawdown_1y",
    },
    {
        "key": "drawdown_60d_high", "label": "较 60 日高点回撤", "label_en": "Drawdown from 60D high",
        "pattern": r"较?60日高点回撤|60日高点", "unit": "%",
        "metric": "drawdown_60d_high",
    },
    {
        "key": "profit_growth_years", "label": "近 3 年净利润连续增长", "label_en": "Profit growth streak",
        "pattern": r"(?:近)?(\d+)年.{0,6}净利润.{0,6}(?:连续增长|逐年增长|增长)",
        "unit": "年", "metric": "profit_growth_years", "bool": True,
    },
    {
        "key": "high_60d", "label": "创 60 日新高", "label_en": "60-day high",
        "pattern": r"(?:收盘价)?创(\d+)日新高", "unit": "日", "metric": "high_60d", "bool": True,
    },
    {
        "key": "above_ma60", "label": "站上 60 日均线", "label_en": "Above MA60",
        "pattern": r"站上(\d+)日均线", "unit": "日", "metric": "above_ma60", "bool": True,
    },
    {
        "key": "volume_ratio_5d", "label": "成交量放大", "label_en": "Volume expansion",
        "pattern": r"成交量.{0,12}?(\d+(?:\.\d+)?)倍", "unit": "倍", "metric": "volume_ratio_5d",
    },
    {
        "key": "volume_expand_5d", "label": "成交额较前 5 日放大", "label_en": "Turnover expansion",
        "pattern": r"成交额.{0,10}?(?:较|比)?前?(\d+)日.{0,6}(?:放大|增加)", "unit": "日",
        "metric": "volume_expand_5d", "bool": True,
    },
    {
        "key": "up_days_3", "label": "近 3 日连续收阳", "label_en": "Consecutive up days",
        "pattern": r"近(\d+)日连续收阳", "unit": "日", "metric": "up_days_3", "bool": True,
    },
    {
        "key": "return_20d", "label": "近 20 日涨幅", "label_en": "20-day return",
        "pattern": r"(?:近)?(\d+)日涨幅", "unit": "%", "metric": "return_20d",
    },
    {
        "key": "market_cap", "label": "总市值", "label_en": "Market cap",
        "pattern": r"总市值", "unit": "亿", "metric": "market_cap",
    },
    {
        "key": "dividend_yield", "label": "股息率", "label_en": "Dividend yield",
        "pattern": r"股息率", "unit": "%", "metric": "dividend_yield",
    },
    {
        "key": "roe", "label": "ROE", "label_en": "ROE",
        "pattern": r"ROE", "unit": "%", "metric": "roe",
    },
    {
        "key": "pe", "label": "PE(TTM)", "label_en": "PE (TTM)",
        "pattern": r"(?:^|[^分位])PE(?:\(TTM\)|TTM)?", "unit": "倍", "metric": "pe_ttm",
    },
    {
        "key": "main_inflow_days", "label": "主力连续净流入", "label_en": "Consecutive main inflow",
        "pattern": r"连续(\d+)日为正", "unit": "日", "metric": "main_inflow_days", "force_op": "min",
        "supported": False, "reason": "资金流数据源暂未接入",
    },
    {
        "key": "main_net_inflow_5d", "label": "5 日主力净流入", "label_en": "5-day main net inflow",
        "pattern": r"主力净流入|净流入", "unit": "万", "metric": "main_net_inflow_5d",
        "supported": False, "reason": "资金流数据源暂未接入",
    },
    {
        "key": "industry", "label": "行业", "label_en": "Industry",
        "pattern": r"行业(?:是|为|=|：|:)\s*([^\s，,；;]+)", "unit": "",
        "metric": "industry", "text_value": True,
    },
)

_SPEC_BY_KEY = {s["key"]: s for s in _SPECS}


def _format_condition(cond: dict[str, Any]) -> str:
    label = cond.get("label") or cond["key"]
    unit = cond.get("unit") or ""
    value = cond.get("value")
    if cond.get("bool"):
        if cond.get("key") == "profit_growth_years":
            return f"近 {int(value or 0)} 年净利润连续增长"
        return label
    if cond.get("op") == "min":
        return f"{label} ≥ {value}{unit}"
    if cond.get("op") == "max":
        return f"{label} ≤ {value}{unit}"
    return f"{label} {value}{unit}"


def _parse_segment(segment: str) -> dict[str, Any] | None:
    text = _norm(segment)
    if not text:
        return None
    for spec in _SPECS:
        m = re.search(spec["pattern"], text, flags=re.I)
        if not m:
            continue
        # PE 分位优先于普通 PE
        if spec["key"] == "pe" and "分位" in text:
            continue
        if spec.get("text_value"):
            value = m.group(1) if m.groups() else ""
            cond = {
                "key": spec["key"], "label": spec["label"], "label_en": spec["label_en"],
                "op": "eq", "value": value, "unit": spec.get("unit", ""), "text": segment,
                "supported": spec.get("supported", True), "supported_reason": spec.get("reason"),
                "bool": False,
            }
        else:
            value = _value(text)
            if value is None and spec["key"] not in {"high_60d", "above_ma60", "volume_expand_5d"}:
                continue
            is_bool = bool(spec.get("bool"))
            op = "bool" if is_bool else spec.get("force_op") or ("min" if _op(text) == "min" else "max")
            cond = {
                "key": spec["key"], "label": spec["label"], "label_en": spec["label_en"],
                "op": op, "value": value, "unit": spec.get("unit", ""), "text": segment,
                "supported": spec.get("supported", True), "supported_reason": spec.get("reason"),
                "bool": is_bool,
            }
        cond["text"] = _format_condition(cond)
        return cond
    return None


def _suggestions(text: str) -> list[str]:
    if any(k in text for k in ("涨", "动量", "强势")):
        return ["近 20 日涨幅大于 10%", "站上 60 日均线", "成交量大于 5 日均量 1.5 倍"]
    if any(k in text for k in ("估值", "PE", "市盈率", "便宜")):
        return ["PE 分位低于 30%", "总市值小于 200 亿", "ROE 大于 10%"]
    if any(k in text for k in ("分红", "股息")):
        return ["股息率大于 3%", "PE 分位低于 30%", "近 1 年最大回撤小于 25%"]
    return ["PE 分位低于 30%", "近 20 日涨幅大于 10%", "ROE 大于 10%"]


def parse_query(query: str) -> dict[str, Any]:
    raw = (query or "").strip()
    cleaned = re.sub(r"^(请|帮我|帮忙|麻烦)?\s*(找|筛选|选|看看|查一下)\s*", "", raw)
    cleaned = re.sub(r"(的)?(股票|标的|个股)$", "", cleaned).strip()
    # “小市值弹性：总市值…” 这类方向名不是条件，去掉冒号前的短标题。
    cleaned = re.sub(r"^[^：:，,；;]{1,12}[：:]", "", cleaned)
    segments = [s for s in re.split(r"[，,；;]|并且|以及|而且|且", cleaned) if s.strip()]
    conditions: list[dict[str, Any]] = []
    unrecognized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for segment in segments:
        cond = _parse_segment(segment)
        if not cond:
            if re.search(r"帮我|筛选|股票|标的|一下", segment):
                continue
            unrecognized.append({"text": segment.strip(), "suggestions": _suggestions(segment)[:2]})
            continue
        # 同一条件同方向重复出现时只保留一次；不同方向保留用于冲突检测。
        marker = f"{cond['key']}:{cond['op']}:{cond.get('value')}"
        if marker in seen and cond["key"] not in {"industry"}:
            continue
        seen.add(marker)
        conditions.append(cond)
    conflicts: list[str] = []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for cond in conditions:
        by_key.setdefault(cond["key"], []).append(cond)
    for key, items in by_key.items():
        mins = [c for c in items if c["op"] == "min"]
        maxs = [c for c in items if c["op"] == "max"]
        if mins and maxs:
            if max(c["value"] for c in maxs) < min(c["value"] for c in mins):
                conflicts.append(f"「{items[0]['label']}」同时设置了下限与上限，且区间为空")
    unsupported = [c for c in conditions if not c.get("supported", True)]
    return {
        "ok": True,
        "query": raw,
        "conditions": conditions,
        "unrecognized": unrecognized,
        "conflicts": conflicts,
        "unsupported": unsupported,
        "all_recognized": bool(conditions) and not unrecognized and not conflicts and not unsupported,
        "need_more": not conditions,
        "message": None if conditions else "暂时没识别出可执行条件，可以补充估值、涨幅、ROE、市值等关键词。",
        "disclaimer": DATA_DISCLAIMER,
    }


def _condition_ok(cond: dict[str, Any], item: dict[str, Any]) -> bool:
    key = cond["key"]
    value = cond.get("value")
    actual = item.get("pe_ttm") if key == "pe" else item.get(key)
    if key == "industry":
        return bool(value) and str(value) in str(actual or "")
    if cond.get("bool"):
        if key == "profit_growth_years":
            return int(item.get("profit_growth_years") or 0) >= int(value or 0)
        return bool(actual)
    if actual is None or value is None:
        return False
    if cond["op"] == "min":
        return float(actual) >= float(value)
    if cond["op"] == "max":
        return float(actual) <= float(value)
    return False


def _base_candidates(conn: Any) -> list[dict[str, Any]]:
    rows = rules.rows(
        conn,
        "SELECT code,name,industry,price,prev_close,market_cap,pe_ttm,dividend_yield "
        "FROM invest_stocks WHERE price IS NOT NULL AND code NOT LIKE '%.%' "
        "AND (asset IS NULL OR asset <> 'etf')",
    )
    out = []
    for row in rows:
        price, prev = _num(row.get("price")), _num(row.get("prev_close"))
        out.append({
            "code": str(row.get("code")),
            "name": row.get("name") or row.get("code"),
            "industry": row.get("industry") or "未分类",
            "price": price,
            "change_pct": (price / prev - 1) * 100 if price and prev else None,
            "market_cap": _num(row.get("market_cap")),
            "pe_ttm": _num(row.get("pe_ttm")),
            "dividend_yield": _num(row.get("dividend_yield")),
        })
    return out


def _symbol(code: str) -> str:
    return rules._with_suffix(code)


def _load_roe(conn: Any, codes: list[str], data_date: str) -> dict[str, float | None]:
    if not codes:
        return {}
    symbols = [_symbol(c) for c in codes]
    rows = rules.rows(
        conn,
        "SELECT DISTINCT ON (symbol) symbol, roe FROM fin_indicator "
        "WHERE symbol = ANY(?) AND notice_date <= ?::date "
        "ORDER BY symbol, report_date DESC, notice_date DESC",
        (symbols, data_date),
    )
    return {str(r["symbol"]).split(".")[0]: (round(v * 100, 6) if (v := _num(r.get("roe"))) is not None else None) for r in rows}


def _load_profit_growth(conn: Any, codes: list[str], data_date: str, years_count: int = 3) -> dict[str, int]:
    if not codes:
        return {}
    symbols = [_symbol(c) for c in codes]
    year = int(data_date[:4])
    years_count = max(1, min(10, int(years_count or 3)))
    years = [year - n for n in range(1, years_count + 1)]
    rows = rules.rows(
        conn,
        "SELECT symbol, EXTRACT(YEAR FROM report_date)::int AS y, net_profit "
        "FROM fin_income_statement WHERE symbol = ANY(?) "
        "AND EXTRACT(MONTH FROM report_date)=12 AND EXTRACT(DAY FROM report_date)=31 "
        "AND EXTRACT(YEAR FROM report_date) = ANY(?) ORDER BY symbol, report_date",
        (symbols, years),
    )
    by: dict[str, dict[int, float]] = {}
    for row in rows:
        symbol = str(row["symbol"]).split(".")[0]
        value = _num(row.get("net_profit"))
        if value is not None:
            by.setdefault(symbol, {})[int(row["y"])] = value
    out: dict[str, int] = {}
    for code, values in by.items():
        seq = [values.get(y) for y in years]  # 2025,2024,2023 倒序
        if any(v is None or v <= 0 for v in seq):
            out[code] = 0
            continue
        streak = 0
        # 从旧到新逐年递增
        ordered = list(reversed(seq))
        for i in range(1, len(ordered)):
            if ordered[i] > ordered[i - 1]:
                streak += 1
            else:
                break
        out[code] = streak + 1 if streak else 0
    return out


def _load_pe_percentiles(conn: Any, codes: list[str], data_date: str) -> dict[str, float]:
    if not codes:
        return {}
    symbols = [_symbol(c) for c in codes]
    since = (date.fromisoformat(data_date) - timedelta(days=365 * 5)).isoformat()
    rows = rules.rows(
        conn,
        """
        WITH latest AS (
          SELECT symbol, pe_ttm FROM md_valuation_daily
          WHERE trade_date = (SELECT MAX(trade_date) FROM md_valuation_daily)
            AND symbol = ANY(?) AND pe_ttm > 0
        ), hist AS (
          SELECT symbol, pe_ttm FROM md_valuation_daily
          WHERE trade_date >= ?::date AND symbol = ANY(?) AND pe_ttm > 0
        )
        SELECT h.symbol, COUNT(*) AS n,
               SUM(CASE WHEN h.pe_ttm <= l.pe_ttm THEN 1 ELSE 0 END) AS le
        FROM hist h JOIN latest l ON l.symbol=h.symbol
        GROUP BY h.symbol
        """,
        (symbols, since, symbols),
    )
    return {
        str(r["symbol"]).split(".")[0]: float(r["le"]) / float(r["n"]) * 100
        for r in rows if r.get("n")
    }


def _load_bars(conn: Any, codes: list[str], data_date: str, window: int = 60) -> dict[str, list[dict[str, Any]]]:
    if not codes:
        return {}
    symbols = [_symbol(c) for c in codes]
    since = (date.fromisoformat(data_date) - timedelta(days=max(30, window * 2))).isoformat()
    out: dict[str, list[dict[str, Any]]] = {}
    for start in range(0, len(symbols), 1000):
        chunk = symbols[start:start + 1000]
        for row in rules.rows(
            conn,
            "SELECT symbol, trade_date::text AS d, open, close, volume, amount "
            "FROM md_daily_bar WHERE adjust='hfq' AND trade_date BETWEEN ?::date AND ?::date "
            "AND symbol = ANY(?) ORDER BY symbol, trade_date",
            (since, data_date, chunk),
        ):
            code = str(row["symbol"]).split(".")[0]
            out.setdefault(code, []).append({
                "open": _num(row.get("open")), "close": _num(row.get("close")),
                "volume": _num(row.get("volume")), "amount": _num(row.get("amount")),
            })
    return out


def _bar_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [r["close"] for r in rows if r.get("close") is not None]
    if len(closes) < 3:
        return {}
    out: dict[str, Any] = {}
    if len(closes) >= 21 and closes[-21]:
        out["return_20d"] = (closes[-1] / closes[-21] - 1) * 100
    window = closes[-250:]
    peak, worst = -math.inf, 0.0
    for value in window:
        peak = max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1)
    out["max_drawdown_1y"] = abs(worst) * 100
    recent = rows[-60:]
    high60 = max((r["close"] for r in recent if r.get("close") is not None), default=None)
    if high60:
        out["high_60d"] = closes[-1] >= high60
        out["drawdown_60d_high"] = max(0.0, (1 - closes[-1] / high60) * 100)
        out["above_ma60"] = closes[-1] > sum(closes[-60:]) / len(closes[-60:])
    vols = [r["volume"] for r in rows if r.get("volume") is not None]
    if len(vols) >= 6 and sum(vols[-6:-1]) > 0:
        out["volume_ratio_5d"] = vols[-1] / (sum(vols[-6:-1]) / 5)
    amts = [r["amount"] for r in rows if r.get("amount") is not None]
    if len(amts) >= 6 and sum(amts[-6:-1]) > 0:
        out["volume_expand_5d"] = amts[-1] / (sum(amts[-6:-1]) / 5) > 1.2
    last3 = rows[-3:]
    out["up_days_3"] = len(last3) == 3 and all(
        r.get("close") is not None and r.get("open") is not None and r["close"] > r["open"] for r in last3
    )
    return out


def _diagnostic(conditions: list[dict[str, Any]], base: list[dict[str, Any]], matched: list[dict[str, Any]],
                counts: dict[str, int] | None = None) -> dict[str, Any] | None:
    if matched:
        return None
    # 找到从 base 开始逐条加条件时第一次归零的条件
    current = list(base)
    blocking = None
    if counts:
        for cond in conditions:
            if counts.get(cond["key"]) == 0:
                blocking = cond
                break
    if blocking is None:
        for cond in conditions:
            current = [item for item in current if _condition_ok(cond, item)]
            if not current:
                blocking = cond
                break
    if not blocking and conditions:
        blocking = conditions[-1]
    if not blocking:
        return None
    label = blocking.get("label") or blocking.get("key")
    key = blocking.get("key")
    value = blocking.get("value")
    widened = None
    if value is not None and not blocking.get("bool"):
        widened = round(float(value) * 1.2, 2) if blocking.get("op") == "max" else round(float(value) * 0.8, 2)
    options = [f"去掉「{label}」"]
    actions: list[dict[str, Any]] = [{"type": "remove", "key": key, "label": options[0]}]
    if widened is not None:
        options.append(f"把「{label}」放宽 20%")
        actions.append({"type": "widen", "key": key, "value": widened, "label": options[-1]})
    options.append("换一个更宽的条件，例如总市值小于 500 亿")
    actions.append({"type": "replace", "key": key, "query": "总市值小于 500 亿", "label": options[-1]})
    return {"blocking": label, "blocking_key": key, "relax_options": options, "relax_actions": actions}


def normalize_conditions(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """把前端回传的标签条件恢复成服务端标准结构（用于删标签后重筛）。"""
    out: list[dict[str, Any]] = []
    for raw in items:
        key = str(raw.get("key") or "")
        spec = _SPEC_BY_KEY.get(key)
        if not spec:
            continue
        value = raw.get("value")
        if spec.get("text_value"):
            cond = {
                "key": key, "label": spec["label"], "label_en": spec["label_en"],
                "op": "eq", "value": str(value or ""), "unit": spec.get("unit", ""),
                "text": f"{spec['label']} {value}", "supported": spec.get("supported", True),
                "supported_reason": spec.get("reason"), "bool": False,
            }
            out.append(cond)
            continue
        if spec.get("bool"):
            op = "bool"
        else:
            op = str(raw.get("op") or ("min" if spec.get("force_op") == "min" else "max"))
            if op not in {"min", "max"}:
                op = "max"
            if _num(value) is None:
                continue
            value = _num(value)
        cond = {
            "key": key, "label": spec["label"], "label_en": spec["label_en"],
            "op": op, "value": value, "unit": spec.get("unit", ""), "text": "",
            "supported": spec.get("supported", True), "supported_reason": spec.get("reason"),
            "bool": bool(spec.get("bool")),
        }
        cond["text"] = _format_condition(cond)
        out.append(cond)
    return out


def screen_conditions(conn: Any, conditions: list[dict[str, Any]], *, limit: int = 200) -> dict[str, Any]:
    data_date = rules.latest_date(conn)
    base = _base_candidates(conn)
    if not base:
        return {"ok": False, "status": "empty", "message": "行情快照为空，暂不能筛选。", "conditions": conditions}

    # 先用快照字段过滤，缩小后续财务/估值/行情查询范围。
    cheap_keys = {"market_cap", "dividend_yield", "pe", "industry"}
    current = base
    stage_counts: dict[str, int] = {}
    for cond in conditions:
        if cond["key"] in cheap_keys:
            current = [item for item in current if _condition_ok(cond, item)]
            stage_counts[cond["key"]] = len(current)
    if not current:
        diag = _diagnostic(conditions, base, current, stage_counts)
        return {"ok": True, "status": "empty", "count": 0, "conditions": conditions, "diagnostic": diag,
                "summary": [], "risk": DATA_DISCLAIMER, "disclaimer": DATA_DISCLAIMER}

    # 按“快照 → 财务 → 估值 → 行情”顺序逐层收窄：后续查询只跑存活标的。
    for cond in conditions:
        if cond["key"] == "roe":
            if not current:
                break
            roe = _load_roe(conn, [item["code"] for item in current], data_date)
            for item in current:
                item["roe"] = roe.get(item["code"])
            current = [item for item in current if _condition_ok(cond, item)]
            stage_counts[cond["key"]] = len(current)
        elif cond["key"] == "profit_growth_years":
            if not current:
                break
            streak = _load_profit_growth(conn, [item["code"] for item in current], data_date, int(cond.get("value") or 3))
            for item in current:
                item["profit_growth_years"] = streak.get(item["code"], 0)
            current = [item for item in current if _condition_ok(cond, item)]
            stage_counts[cond["key"]] = len(current)
    if any(c["key"] == "pe_percentile" for c in conditions) and current:
        pcts = _load_pe_percentiles(conn, [item["code"] for item in current], data_date)
        for item in current:
            item["pe_percentile"] = pcts.get(item["code"])
        current = [item for item in current if _condition_ok(next(c for c in conditions if c["key"] == "pe_percentile"), item)]
        stage_counts["pe_percentile"] = len(current)
    bar_keys = {"return_20d", "max_drawdown_1y", "high_60d", "above_ma60", "volume_ratio_5d",
                "drawdown_60d_high", "up_days_3", "volume_expand_5d"}
    bar_conds = [c for c in conditions if c["key"] in bar_keys]
    if bar_conds and current:
        keys = {c["key"] for c in bar_conds}
        if "max_drawdown_1y" in keys:
            window = 260
        elif keys & {"high_60d", "above_ma60", "drawdown_60d_high"}:
            window = 65
        elif "return_20d" in keys:
            window = 25
        else:
            window = 10
        bars = _load_bars(conn, [item["code"] for item in current], data_date, window)
        for item in current:
            item.update(_bar_metrics(bars.get(item["code"], [])))
        for cond in bar_conds:
            stage_counts[cond["key"]] = sum(1 for item in current if _condition_ok(cond, item))
        current = [item for item in current if all(_condition_ok(c, item) for c in bar_conds)]

    matched = [item for item in current if all(_condition_ok(c, item) for c in conditions)]
    matched.sort(key=lambda x: (x.get("market_cap") or 0), reverse=True)
    if not matched:
        diag = _diagnostic(conditions, base, matched, stage_counts)
        return {"ok": True, "status": "empty", "count": 0, "conditions": conditions, "diagnostic": diag,
                "summary": [], "risk": DATA_DISCLAIMER, "disclaimer": DATA_DISCLAIMER}
    if len(matched) > limit:
        return {
            "ok": True, "status": "too_broad", "count": len(matched), "conditions": conditions,
            "diagnostic": {
                "blocking": "条件偏松", "blocking_key": "",
                "suggestion": "当前范围超过 200 只，再补一条估值、盈利或成交条件即可收窄。",
                "relax_options": [
                    "加一条 PE 分位低于 30%", "加一条 ROE 大于 10%", "加一条总市值小于 200 亿",
                ],
                "relax_actions": [
                    {"type": "add", "query": "PE 分位低于 30%", "label": "加一条 PE 分位低于 30%"},
                    {"type": "add", "query": "ROE 大于 10%", "label": "加一条 ROE 大于 10%"},
                    {"type": "add", "query": "总市值小于 200 亿", "label": "加一条总市值小于 200 亿"},
                ],
            },
            "summary": [], "risk": DATA_DISCLAIMER, "disclaimer": DATA_DISCLAIMER,
        }

    industries: dict[str, int] = {}
    for item in matched:
        industries[item["industry"]] = industries.get(item["industry"], 0) + 1
    industry_distribution = [
        {"name": k, "count": v, "pct": round(v / len(matched) * 100, 1)}
        for k, v in sorted(industries.items(), key=lambda kv: kv[1], reverse=True)
    ]
    caps = [item["market_cap"] for item in matched if item.get("market_cap") is not None]
    pe_pcts = [item["pe_percentile"] for item in matched if item.get("pe_percentile") is not None]
    roes = [item["roe"] for item in matched if item.get("roe") is not None]
    summary = [f"共筛出 {len(matched)} 只，按条件逐项过滤。"]
    if caps:
        extra = []
        if pe_pcts:
            extra.append(f"PE 分位中位数 {median(pe_pcts):.0f}%")
        if roes:
            extra.append(f"ROE 中位数 {median(roes):.1f}%")
        suffix = f"；{'，'.join(extra)}" if extra else ""
        summary.append(f"总市值中位数 {median(caps):.0f} 亿，区间 {min(caps):.0f}–{max(caps):.0f} 亿{suffix}。")
    if industry_distribution:
        top = industry_distribution[0]
        summary.append(f"行业集中在{top['name']}（{top['count']} 只，占 {top['pct']:.0f}%）。")
    items = [
        {
            **item,
            "pe_percentile": round(item["pe_percentile"], 1) if item.get("pe_percentile") is not None else None,
            "roe": round(item["roe"], 2) if item.get("roe") is not None else None,
            "change_pct": round(item["change_pct"], 2) if item.get("change_pct") is not None else None,
        }
        for item in matched
    ]
    return {
        "ok": True, "status": "ok", "count": len(matched), "conditions": conditions,
        "items": items, "summary": summary,
        "risk": "筛选基于历史 EOD 数据，不含实时与资金流；结果非投资建议。",
        "industry_distribution": industry_distribution,
        "followups": ["这批股票属于哪些行业", "按 ROE 从高到低看", "把条件放宽一点"],
        "disclaimer": DATA_DISCLAIMER,
    }


__all__ = ["parse_query", "normalize_conditions", "screen_conditions", "DATA_DISCLAIMER"]
