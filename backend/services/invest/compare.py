# -*- coding: utf-8 -*-
"""多标的对比：名称解析与同口径结构化结果。

设计约束（对应 11.6 多标的对比）：
- 指标全部来自服务端已算好的行情/财务/估值/资金流，前端不补算；
- 最多 3 只，缺失值保留 None 并由 UI 显示 “—”；
- 不做排序打分、不给“更值得买”的结论；跨行业只描述各自水平；
- 公告/研报未接入时明确标注，不用估算或占位内容补齐。
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from services.invest import rules

DISCLAIMER = "以上对比仅描述数据差异，不构成投资建议。"
MAX_CODES = 3

_SPLIT = re.compile(r"\s*(?:和|与|跟|同|vs\.?|versus|、|,|，|及)\s*", flags=re.I)
_LEADING = re.compile(r"^(?:请|帮我|帮忙|麻烦|给我)?\s*(?:对比|比较|看看|查一下|分析)\s*")

# 常见简称/别名，只用于解析，不改变证券主数据。
ALIASES = {
    "茅台": "贵州茅台",
    "宁德": "宁德时代",
    "比亚迪": "比亚迪",
    "招行": "招商银行",
    "平安": "中国平安",
    "五粮液": "五粮液",
    "中免": "中国中免",
}


class StockNotFound(ValueError):
    def __init__(self, term: str, suggestions: list[dict[str, str]] | None = None):
        super().__init__(f"未收录标的：{term}")
        self.term = term
        self.suggestions = suggestions or []


def _clean(term: str) -> str:
    # 只去掉包裹符号和首尾“的”，不要把“标的A”这类名称中间的“的”删掉。
    value = re.sub(r"[\s　\[\]【】（）()]+", "", str(term or "")).strip()
    return re.sub(r"^的+|的+$", "", value)


def parse_compare_query(query: str) -> list[str]:
    """剥离意图词后切出 2–3 个标的，顺序保留。"""
    text = _LEADING.sub("", str(query or "").strip())
    text = re.sub(
        r"(?:的(?:估值|财务|基本面|行情|风险|数据)|哪个好|怎么样|如何|多标的对比|对比|比较|一下).*$",
        "",
        text,
    )
    parts = [_clean(p) for p in _SPLIT.split(text)]
    out: list[str] = []
    for part in parts:
        if not part or part in out:
            continue
        # “宁德时代和比亚迪对比” 已经剥离；仍含意图词时只保留前段。
        if any(word and word in part for word in ("对比", "比较", "哪个好")):
            part = re.split(r"对比|比较|哪个好", part)[0].strip()
        if part:
            out.append(part)
    return out[:MAX_CODES]


def _lookup(conn: Any, term: str) -> dict[str, Any] | None:
    term = _clean(term)
    if not term:
        return None
    bare = term.upper().split(".")[0] if re.search(r"\.(SH|SZ|BJ)$", term, re.I) else term
    row = rules.one(
        conn,
        "SELECT code, name, industry FROM stocks WHERE code=? OR code=? OR name=? LIMIT 1",
        (term, bare, term),
    )
    if row:
        return row
    alias = ALIASES.get(term)
    if alias:
        row = rules.one(conn, "SELECT code, name, industry FROM stocks WHERE name=? LIMIT 1", (alias,))
        if row:
            return row
    like = f"%{term}%"
    row = rules.one(
        conn,
        "SELECT code, name, industry FROM stocks "
        "WHERE name LIKE ? OR pinyin LIKE ? ORDER BY LENGTH(name) ASC, code ASC LIMIT 1",
        (like, like),
    )
    return row


def _suggestions(conn: Any, term: str) -> list[dict[str, str]]:
    term = _clean(term)
    if not term:
        return []
    rows = rules.rows(conn, "SELECT code, name FROM stocks WHERE COALESCE(market,'CN')='CN'")
    names = {str(r.get("name") or ""): r for r in rows if r.get("name")}
    hits = difflib.get_close_matches(term, list(names), n=3, cutoff=0.45)
    if not hits:
        hits = [name for name in names if term in name][:3]
    return [{"code": str(names[name].get("code")), "name": name} for name in hits]


def suggestions(conn: Any, term: str) -> list[dict[str, str]]:
    """名称未命中时给 2–3 个候选，供前端做“您想找的是不是”。"""
    return _suggestions(conn, term)


def resolve_stock(conn: Any, term: str) -> dict[str, Any]:
    row = _lookup(conn, term)
    if not row:
        raise StockNotFound(_clean(term), _suggestions(conn, term))
    return row


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Any, base: Any) -> float | None:
    v, b = _num(value), _num(base)
    if v is None or not b:
        return None
    return (v / b - 1) * 100


def _five_day_return(stock: dict[str, Any]) -> float | None:
    bars = (stock.get("chart") or {}).get("bars") or []
    closes = [_num(b.get("close")) for b in bars]
    closes = [c for c in closes if c is not None]
    return _pct(closes[-1], closes[-6]) if len(closes) >= 6 else None


def _yi(value: Any) -> float | None:
    n = _num(value)
    return n / 1e8 if n is not None else None


def _single_quarter_yoy(fins: list[dict[str, Any]]) -> float | None:
    """财报为年内累计口径；用同季累计差计算单季营收同比。"""
    values: dict[tuple[int, int], float] = {}
    for row in fins:
        match = re.fullmatch(r"(\d{4})Q([1-4])", str(row.get("period") or ""))
        revenue = _num(row.get("revenue"))
        if match and revenue is not None:
            values[(int(match.group(1)), int(match.group(2)))] = revenue
    if not values:
        return None
    year, quarter = max(values)
    current = values[(year, quarter)] - (values.get((year, quarter - 1), 0.0) if quarter > 1 else 0.0)
    prior = values.get((year - 1, quarter))
    if prior is None:
        return None
    prior_base = prior - (values.get((year - 1, quarter - 1), 0.0) if quarter > 1 else 0.0)
    return _pct(current, prior_base)


def _item(code: str, stock: dict[str, Any]) -> dict[str, Any]:
    quote = stock.get("quote") or {}
    report = stock.get("report") or {}
    valuation = stock.get("valuation") or {}
    technical = stock.get("technical") or {}
    cash = ((stock.get("statements") or {}).get("cashflow") or {})
    flow = stock.get("fundFlow") or {}
    return {
        "code": quote.get("code") or code,
        "name": quote.get("name") or code,
        "industry": quote.get("industry"),
        "asset": quote.get("asset"),
        "price": _num(quote.get("price")),
        "changePct": _num(quote.get("changePct")),
        "return5": _five_day_return(stock),
        "amountYi": _yi(quote.get("amount")),
        "turnover": _num(quote.get("turnover")),
        "revenue": _num(report.get("revenue")),
        "revenueYoY": _num(report.get("revenueYoY")),
        "quarterRevenueYoY": _single_quarter_yoy(stock.get("financials") or []),
        "netProfit": _num(report.get("netProfit")),
        "profitYoY": _num(report.get("profitYoY")),
        "grossMargin": _num(report.get("grossMargin")),
        "roe": _num(report.get("roe")),
        "ocfYi": _yi(cash.get("operating_cf")),
        "pe": _num(valuation.get("pe")),
        "pb": _num(valuation.get("pb")),
        "pePercentile": _num(valuation.get("pePercentile")),
        "dividendYield": _num(quote.get("dividendYield")),
        "fund20Yi": _num(flow.get("twenty_day")),
        "drawdown": _num(technical.get("drawdown")),
        "risks": stock.get("risks") or [],
        "dataDate": stock.get("dataDate"),
    }


def _rows(specs: list[tuple[str, str, str, str]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for key, label, label_en, fmt in specs:
        values = [item.get(key) for item in items]
        if all(v is None for v in values):
            continue
        out.append({
            "key": key,
            "label": label,
            "label_en": label_en,
            "fmt": fmt,
            "values": values,
            "missing": [items[i]["name"] for i, v in enumerate(values) if v is None],
        })
    return out


def _dimension(key: str, title: str, title_en: str, rows: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [
        {"code": item["code"], "name": item["name"], "labels": [r["label"] for r in rows if item.get(r["key"]) is None]}
        for item in items
    ]
    return {
        "key": key,
        "title": title,
        "title_en": title_en,
        "rows": rows,
        "missing": [m for m in missing if m["labels"]],
    }


def _highlights(item: dict[str, Any]) -> dict[str, Any]:
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []

    def add(target: list[dict[str, Any]], zh: str, en: str, tone: str, source: str) -> None:
        target.append({"text": zh, "text_en": en, "tone": tone, "source": source})

    if item["revenueYoY"] is not None and item["revenueYoY"] > 0:
        add(positive, f"营收同比 {item['revenueYoY']:+.1f}%，收入仍在增长", f"Revenue {item['revenueYoY']:+.1f}% YoY, still growing", "good", "财报")
    if item["profitYoY"] is not None and item["profitYoY"] > 0:
        add(positive, f"归母净利同比 {item['profitYoY']:+.1f}%", f"Net profit {item['profitYoY']:+.1f}% YoY", "good", "财报")
    if item["grossMargin"] is not None and item["grossMargin"] >= 30:
        add(positive, f"毛利率 {item['grossMargin']:.1f}%，处于较高水平", f"Gross margin {item['grossMargin']:.1f}%, relatively high", "good", "财报")
    if item["pePercentile"] is not None and item["pePercentile"] <= 30:
        add(positive, f"PE 分位 {item['pePercentile']:.0f}%，处于近 3 年较低位置", f"PE percentile {item['pePercentile']:.0f}%, low versus its 3-year history", "good", "估值")
    if item["fund20Yi"] is not None and item["fund20Yi"] > 0:
        add(positive, f"近 20 日主力净流入 {item['fund20Yi']:+.2f} 亿元", f"Main net inflow {item['fund20Yi']:+.2f} CNY 100m over 20 days", "good", "资金流")
    if item["return5"] is not None and item["return5"] > 0:
        add(positive, f"近 5 日涨跌 {item['return5']:+.1f}%", f"5-day return {item['return5']:+.1f}%", "good", "行情")

    if item["revenueYoY"] is not None and item["revenueYoY"] < 0:
        add(negative, f"营收同比 {item['revenueYoY']:+.1f}%，收入承压", f"Revenue {item['revenueYoY']:+.1f}% YoY, under pressure", "amber", "财报")
    if item["profitYoY"] is not None and item["profitYoY"] < 0:
        add(negative, f"归母净利同比 {item['profitYoY']:+.1f}%", f"Net profit {item['profitYoY']:+.1f}% YoY", "amber", "财报")
    if item["pePercentile"] is not None and item["pePercentile"] >= 70:
        add(negative, f"PE 分位 {item['pePercentile']:.0f}%，处于近 3 年较高位置", f"PE percentile {item['pePercentile']:.0f}%, high versus its 3-year history", "amber", "估值")
    if item["fund20Yi"] is not None and item["fund20Yi"] < 0:
        add(negative, f"近 20 日主力净流出 {abs(item['fund20Yi']):.2f} 亿元", f"Main net outflow {abs(item['fund20Yi']):.2f} CNY 100m over 20 days", "amber", "资金流")
    if item["drawdown"] is not None and item["drawdown"] <= -15:
        add(negative, f"较近 180 日高点回撤 {item['drawdown']:.1f}%", f"{item['drawdown']:.1f}% below its 180-day high", "amber", "行情")
    for risk in item["risks"][:3]:
        if str(risk.get("level")) == "green":
            continue
        title = str(risk.get("title") or "")
        detail = str(risk.get("detail") or "")
        if not title and not detail:
            continue
        add(negative, f"{title}：{detail}" if detail else title, f"{title}: {detail}" if detail else title, "amber", "规则风险")
    return {"code": item["code"], "name": item["name"], "positive": positive[:5], "negative": negative[:5]}


def _summary(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if len(items) < 2:
        return out

    def line(key: str, label: str, label_en: str, fmt: str) -> None:
        vals = [(x["name"], x.get(key)) for x in items if x.get(key) is not None]
        if len(vals) < 2:
            return
        if fmt == "pct":
            zh = "，".join(f"{n} {v:+.1f}%" for n, v in vals)
            en = ", ".join(f"{n} {v:+.1f}%" for n, v in vals)
        elif fmt == "x":
            zh = "，".join(f"{n} {v:.1f}x" for n, v in vals)
            en = ", ".join(f"{n} {v:.1f}x" for n, v in vals)
        elif fmt == "pctile":
            zh = "，".join(f"{n} {v:.0f}%" for n, v in vals)
            en = ", ".join(f"{n} {v:.0f}%" for n, v in vals)
        else:
            zh = "，".join(f"{n} {v:.2f}" for n, v in vals)
            en = ", ".join(f"{n} {v:.2f}" for n, v in vals)
        out.append({"text": f"{label}：{zh}。", "text_en": f"{label_en}: {en}."})

    line("revenueYoY", "营收同比", "Revenue YoY", "pct")
    line("quarterRevenueYoY", "单季营收同比", "Single-quarter revenue YoY", "pct")
    line("profitYoY", "净利同比", "Net profit YoY", "pct")
    line("grossMargin", "毛利率", "Gross margin", "pct")
    line("pe", "PE(TTM)", "PE (TTM)", "x")
    line("pePercentile", "PE 分位", "PE percentile", "pctile")
    line("return5", "近 5 日涨跌", "5-day return", "pct")
    line("fund20Yi", "近 20 日主力净流入（亿元）", "20-day main net inflow (CNY 100m)", "num")

    industries = {x.get("industry") for x in items if x.get("industry")}
    tail: list[dict[str, str]] = []
    if len(industries) > 1:
        tail.append({
            "text": "标的属于不同行业，以上只描述各自水平，不并排比大小。",
            "text_en": "The names are in different industries; the figures describe each on its own basis and are not ranked.",
        })
    tail.append({
        "text": "接下来看：下一期财报的营收、毛利率与经营现金流是否延续；公告/研报数据接入后再补充事件面。",
        "text_en": "Next: watch revenue, gross margin and operating cash flow in the next report; event coverage will follow once filings and research data are available.",
    })
    return (out[: max(0, 6 - len(tail))] + tail)[:6]


def build_compare(conn: Any, codes: list[str]) -> dict[str, Any]:
    if not 2 <= len(codes) <= MAX_CODES:
        raise ValueError("一次最多对比 3 只，至少 2 只")
    items: list[dict[str, Any]] = []
    for code in codes:
        stock = rules.build_stock(conn, code)
        if not stock:
            raise StockNotFound(code)
        items.append(_item(code, stock))

    dimensions = [
        _dimension(
            "market", "行情表现", "Market performance",
            _rows([
                ("price", "最新价", "Price", "price"),
                ("changePct", "当日涨跌", "Day change", "pct"),
                ("return5", "5 日涨跌", "5-day return", "pct"),
                ("amountYi", "成交额（亿元）", "Turnover (CNY 100m)", "num"),
                ("turnover", "换手率", "Turnover rate", "pct"),
            ], items),
            items,
        ),
        _dimension(
            "financial", "财务表现", "Financial performance",
            _rows([
                ("revenue", "营业收入（亿元）", "Revenue (CNY 100m)", "num"),
                ("revenueYoY", "营收同比", "Revenue YoY", "pct"),
                ("quarterRevenueYoY", "单季营收同比", "Single-quarter revenue YoY", "pct"),
                ("netProfit", "归母净利润（亿元）", "Net profit (CNY 100m)", "num"),
                ("profitYoY", "净利同比", "Net profit YoY", "pct"),
                ("grossMargin", "销售毛利率", "Gross margin", "pct"),
                ("roe", "ROE", "ROE", "pct"),
                ("ocfYi", "经营现金流净额（亿元）", "Operating cash flow (CNY 100m)", "num"),
            ], items),
            items,
        ),
        _dimension(
            "valuation", "估值水平", "Valuation",
            _rows([
                ("pe", "PE(TTM)", "PE (TTM)", "x"),
                ("pb", "PB", "PB", "x"),
                ("pePercentile", "PE 分位", "PE percentile", "pctile"),
                ("dividendYield", "股息率", "Dividend yield", "pct"),
            ], items),
            items,
        ),
    ]
    highlights = [_highlights(item) for item in items]
    summary = _summary(items)
    card = {
        "summary": "，".join(x["name"] for x in items) + " 的同口径数据差异如下。",
        "sections": [
            {
                "title": "行情",
                "items": [
                    {"k": r["label"], "v": " / ".join("—" if v is None else f"{v:.2f}" for v in r["values"])}
                    for r in dimensions[0]["rows"][:3]
                ],
            },
            {
                "title": "财务与估值",
                "items": [
                    {"k": r["label"], "v": " / ".join("—" if v is None else f"{v:.2f}" for v in r["values"])}
                    for r in (dimensions[1]["rows"] + dimensions[2]["rows"])[:4]
                ],
            },
        ],
        "disclaimer": DISCLAIMER,
        "meta": {"dataSource": "行情 / 财报 / 估值 / 资金流"},
    }
    has_etf = any(item.get("asset") == "etf" for item in items)
    note = "公告与研报数据尚未接入；亮点与风险仅基于财报、行情、估值分位与资金流。"
    note_en = "Filings and research notes are not yet connected; highlights and risks use financials, quotes, valuation percentiles and fund flow only."
    if has_etf:
        note += " 含 ETF：建议先穿透底层持仓再比较，ETF 本身没有完整财务指标。"
        note_en += " ETF included: look through to the underlying holdings first; an ETF has no full set of financial statements."
    return {
        "ok": True,
        "codes": [item["code"] for item in items],
        "items": items,
        "dimensions": dimensions,
        "highlights": highlights,
        "summary": summary,
        "card": card,
        "note": note,
        "note_en": note_en,
        "dataDate": max((str(x.get("dataDate") or "") for x in items), default=""),
        "disclaimer": DISCLAIMER,
    }
