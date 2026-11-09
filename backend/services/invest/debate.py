# -*- coding: utf-8 -*-
"""多空辩论：数据驱动的利多/利空两组证据，不站队。

只使用财报、行情、估值分位、资金流与规则风险；公告/研报未接入时不补造。
"""
from __future__ import annotations

from typing import Any

from services.invest import rules

DEBATE_FOOTER = "双方都有证据，不构成任何方向的建议。"
DEBATE_FOOTER_EN = "Both sides have evidence; this is not a recommendation in either direction."


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _point(zh: str, en: str, source: str, tone: str = "gray") -> dict[str, str]:
    return {"text": zh[:80], "text_en": en[:140], "source": source, "tone": tone}


def build_debate(conn: Any, code: str) -> dict[str, Any] | None:
    stock = rules.build_stock(conn, code)
    if not stock:
        return None
    quote = stock.get("quote") or {}
    report = stock.get("report") or {}
    valuation = stock.get("valuation") or {}
    technical = stock.get("technical") or {}
    flow = stock.get("fundFlow") or {}
    bull: list[dict[str, str]] = []
    bear: list[dict[str, str]] = []

    revenue_yoy = _num(report.get("revenueYoY"))
    profit_yoy = _num(report.get("profitYoY"))
    gross = _num(report.get("grossMargin"))
    roe = _num(report.get("roe"))
    pe_pct = _num(valuation.get("pePercentile"))
    ret20 = _num(technical.get("return20"))
    flow20 = _num(flow.get("twenty_day"))
    drawdown = _num(technical.get("drawdown"))

    if revenue_yoy is not None:
        if revenue_yoy > 0:
            bull.append(_point(f"营收同比 {revenue_yoy:+.1f}%，收入仍在增长", f"Revenue {revenue_yoy:+.1f}% YoY, still growing", "财报", "green"))
        else:
            bear.append(_point(f"营收同比 {revenue_yoy:+.1f}%，收入承压", f"Revenue {revenue_yoy:+.1f}% YoY, under pressure", "财报", "amber"))
    if profit_yoy is not None:
        if profit_yoy > 0:
            bull.append(_point(f"归母净利同比 {profit_yoy:+.1f}%，利润增长", f"Net profit {profit_yoy:+.1f}% YoY", "财报", "green"))
        else:
            bear.append(_point(f"归母净利同比 {profit_yoy:+.1f}%，利润下滑", f"Net profit {profit_yoy:+.1f}% YoY, declining", "财报", "amber"))
    if gross is not None:
        if gross >= 30:
            bull.append(_point(f"毛利率 {gross:.1f}%，盈利空间相对充足", f"Gross margin {gross:.1f}%, relatively ample", "财报", "green"))
        elif gross < 15:
            bear.append(_point(f"毛利率仅 {gross:.1f}%，盈利空间偏薄", f"Gross margin only {gross:.1f}%, thin", "财报", "amber"))
    if roe is not None and roe >= 12:
        bull.append(_point(f"ROE {roe:.1f}%，资本回报较高", f"ROE {roe:.1f}%, relatively high return on equity", "财报", "green"))
    if pe_pct is not None:
        if pe_pct <= 30:
            bull.append(_point(f"PE 分位 {pe_pct:.0f}%，处于近 3 年较低位置", f"PE percentile {pe_pct:.0f}%, low versus its 3-year history", "估值", "green"))
        elif pe_pct >= 70:
            bear.append(_point(f"PE 分位 {pe_pct:.0f}%，处于近 3 年较高位置", f"PE percentile {pe_pct:.0f}%, high versus its 3-year history", "估值", "amber"))
    if ret20 is not None:
        if ret20 > 0:
            bull.append(_point(f"近 20 日涨跌 {ret20:+.1f}%，价格趋势偏强", f"20-day return {ret20:+.1f}%, positive trend", "行情", "green"))
        else:
            bear.append(_point(f"近 20 日涨跌 {ret20:+.1f}%，价格趋势偏弱", f"20-day return {ret20:+.1f}%, weak trend", "行情", "amber"))
    if flow20 is not None:
        if flow20 > 0:
            bull.append(_point(f"近 20 日主力净流入 {flow20:+.2f} 亿元", f"Main net inflow {flow20:+.2f} CNY 100m over 20 days", "资金流", "green"))
        else:
            bear.append(_point(f"近 20 日主力净流出 {abs(flow20):.2f} 亿元", f"Main net outflow {abs(flow20):.2f} CNY 100m over 20 days", "资金流", "amber"))
    if drawdown is not None and drawdown <= -15:
        bear.append(_point(f"较近 180 日高点回撤 {drawdown:.1f}%", f"{drawdown:.1f}% below its 180-day high", "行情", "amber"))
    for risk in (stock.get("risks") or [])[:3]:
        if str(risk.get("level")) == "green":
            continue
        title = str(risk.get("title") or "")
        detail = str(risk.get("detail") or "")
        if not title and not detail:
            continue
        bear.append(_point(f"{title}：{detail}" if detail else title, f"{title}: {detail}" if detail else title, "规则风险", "amber"))

    # 每侧最多 4 条，避免把同一数据重复讲两遍。
    bull = bull[:4]
    bear = bear[:4]
    name = quote.get("name") or code
    return {
        "ok": True,
        "code": quote.get("code") or code,
        "name": name,
        "bull": bull,
        "bear": bear,
        "available": bool(bull or bear),
        "note": "公告与研报数据尚未接入；以上仅基于财报、行情、估值分位、资金流与规则风险。",
        "note_en": "Filings and research notes are not yet connected; the points use financials, quotes, valuation percentiles, fund flow and rule-based risks only.",
        "footer": DEBATE_FOOTER,
        "footer_en": DEBATE_FOOTER_EN,
        "card": {
            "summary": f"{name}的利多与利空均有数据依据，不站队。",
            "sections": [
                {"title": "利多", "items": [{"v": p["text"], "tone": "green"} for p in bull]},
                {"title": "利空", "items": [{"v": p["text"], "tone": "amber"} for p in bear]},
            ],
            "disclaimer": DEBATE_FOOTER,
            "meta": {"dataSource": "财报 / 行情 / 估值 / 资金流 / 规则风险"},
        },
        "disclaimer": DEBATE_FOOTER,
    }
