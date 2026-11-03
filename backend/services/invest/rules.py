"""Rule engine + read models for the Invest H5.

Everything here is deterministic and computed from the local SQLite cache.
No LLM, no generated opinions: each sentence is backed by a number in the DB.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from datetime import date, datetime
from statistics import median
from typing import Any, Iterable

DATA_DATE = date.today().isoformat()  # fallback when a DB has no bars
DISCLAIMER = "收盘数据 · 非实时 · 非投资建议"


def rows(conn: Any, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, tuple(args)).fetchall()]


def one(conn: Any, sql: str, args: Iterable[Any] = ()) -> dict[str, Any] | None:
    r = conn.execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else 0.0


def signed(value: float, digits: int = 1) -> str:
    text = f"{value:+.{digits}f}"
    if text.startswith("-0.") and float(text) == 0:
        text = text[1:]
    return f"{text}%"


def latest_date(conn: Any) -> str:
    try:
        meta = conn.execute("SELECT value FROM meta WHERE key='dataDate'").fetchone()
        if meta and meta.get("value"):
            return str(meta["value"])[:10]
    except Exception:
        pass
    row = conn.execute("SELECT MAX(date) AS d FROM bars").fetchone()
    return (row["d"] if row and row["d"] else DATA_DATE) or DATA_DATE


def data_meta(conn: Any) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM meta WHERE key='source'").fetchone()
    source = row["value"] if row else "seed"
    latest = latest_date(conn)
    if source == "live":
        return {"dataDate": latest, "dataSource": "公开 EOD（腾讯 / 东方财富）", "isDemo": False}
    return {"dataDate": latest, "dataSource": "本地演示数据", "isDemo": True}


def ma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - n:i + 1]) / n)
    return out


def percentile(values: list[float], current: float) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean or current is None:
        return None
    return sum(1 for v in clean if v <= current) / len(clean) * 100


def max_drawdown(values: list[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        if peak:
            worst = min(worst, v / peak - 1)
    return worst * 100


def volatility(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    rets = [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1]]
    if not rets:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252) * 100


def aggregate(bars: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "daily":
        return bars
    groups: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for b in bars:
        d = date.fromisoformat(b["date"])
        key = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}" if mode == "weekly" else f"{d.year}-{d.month:02d}"
        groups.setdefault(key, []).append(b)
    out = []
    for _, group in groups.items():
        out.append({
            "date": group[-1]["date"],
            "open": group[0]["open"],
            "high": max(x["high"] for x in group),
            "low": min(x["low"] for x in group),
            "close": group[-1]["close"],
            "volume": sum(x["volume"] for x in group),
            "amount": sum(x["amount"] for x in group),
        })
    return out


def stock_bars(conn: Any, code: str, limit: int = 750) -> list[dict[str, Any]]:
    # 直接走 md_daily_bar 的 (symbol, trade_date, adjust) 主键，避免 bars 视图对全表 split_part
    symbol = _with_suffix(code)
    return rows(
        conn,
        """SELECT * FROM (
             SELECT n.trade_date::text AS date, n.open, n.high, n.low, n.close,
                    COALESCE(n.volume, h.volume) AS volume,
                    COALESCE(n.amount, h.amount) AS amount
               FROM md_daily_bar n
               LEFT JOIN md_daily_bar h
                 ON h.symbol=n.symbol AND h.trade_date=n.trade_date AND h.adjust='hfq'
              WHERE n.symbol=? AND n.adjust='none' AND n.close IS NOT NULL
              ORDER BY n.trade_date DESC LIMIT ?
           ) t ORDER BY date ASC""",
        (symbol, limit),
    )


_POS_WORDS = ("增长", "上调", "回购", "中标", "盈利", "超预期", "分红", "增持", "利好", "突破", "创新高")
_NEG_WORDS = ("下滑", "亏损", "减持", "处罚", "诉讼", "下调", "风险", "退市", "暴雷", "违规", "质押", "商誉", "问询")


def _with_suffix(code: str) -> str:
    raw = str(code or "").upper()
    if "." in raw:
        return raw
    if raw.startswith("6") or raw.startswith("5"):
        return f"{raw}.SH"
    if raw.startswith(("0", "1", "2", "3")):
        return f"{raw}.SZ"
    if raw.startswith(("4", "8")):
        return f"{raw}.BJ"
    return raw


def _beta_or_none(stock: dict[str, Any]) -> float | None:
    beta = stock.get("beta")
    if beta is not None:
        return float(beta)
    if stock.get("asset") == "etf":
        return None
    try:
        from services.marketdata import store as md_store

        risk = md_store.risk_stats(_with_suffix(str(stock.get("code") or "")), index_code="000300.SH")
        beta = risk.get("beta_1y") if risk else None
        # 近零 Beta 多为日期对齐/数据质量问题，宁可不展示
        return float(beta) if beta is not None and abs(float(beta)) >= 0.1 else None
    except Exception:
        return None


def _earnings_flash(latest: dict[str, Any] | None, prev: dict[str, Any] | None) -> dict[str, Any]:
    if not latest:
        return {"available": False, "highlights": [], "concerns": [], "consensusGap": "财务数据待补充"}
    highlights, concerns = [], []
    revenue_yoy = latest.get("revenue_yoy")
    profit_yoy = latest.get("profit_yoy")
    gross = latest.get("gross_margin")
    if revenue_yoy is not None and revenue_yoy > 0:
        highlights.append(f"营收同比 {revenue_yoy:+.1f}%")
    elif revenue_yoy is not None:
        concerns.append(f"营收同比 {revenue_yoy:+.1f}%")
    if profit_yoy is not None and profit_yoy > 0:
        highlights.append(f"归母净利同比 {profit_yoy:+.1f}%")
    elif profit_yoy is not None:
        concerns.append(f"归母净利同比 {profit_yoy:+.1f}%")
    prev_gross = (prev or {}).get("gross_margin")
    if gross is not None and prev_gross is not None:
        if gross > prev_gross:
            highlights.append(f"毛利率较上期改善 {gross - prev_gross:+.1f}pct")
        elif gross < prev_gross:
            concerns.append(f"毛利率较上期下降 {gross - prev_gross:+.1f}pct")
    ocf = latest.get("ocf")
    if ocf is not None:
        (highlights if ocf > 0 else concerns).append(f"经营现金流 {ocf:.1f} 亿元")
    if not highlights:
        highlights.append("暂未识别出明确亮点")
    if not concerns:
        concerns.append("暂未识别出明确隐忧")
    return {
        "available": True,
        "period": latest.get("period"),
        "highlights": highlights[:3],
        "concerns": concerns[:3],
        "consensusGap": "一致预期数据待补充，当前未做“与预期差”判断",
    }


def _institutional_view() -> dict[str, Any]:
    return {
        "available": False,
        "ratings": [],
        "target": None,
        "forecast": None,
        "note": "机构评级 / 目标价 / 盈利预测数据待补充；本模块不由 AI 生成。",
    }


def _sensitivity(beta: float | None) -> dict[str, Any]:
    if beta is None:
        return {"available": False, "level": None, "beta": None, "note": "Beta 数据待补充"}
    if beta < 0.8:
        level = "低"
    elif beta < 1.2:
        level = "中"
    elif beta < 1.5:
        level = "较高"
    else:
        level = "高"
    return {
        "available": True,
        "level": level,
        "beta": round(beta, 2),
        "note": "按近一年 Beta 分档：<0.8 低、0.8–1.2 中、1.2–1.5 较高、≥1.5 高；仅描述历史敏感度。",
    }


def _sentiment(news: list[dict[str, Any]], turnover: float | None) -> dict[str, Any]:
    if not news:
        return {"available": False, "note": "暂无可用于情绪估算的资讯", "source": "资讯标题词典"}
    pos = neu = neg = 0
    top_event = ""
    for item in news:
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        p = sum(1 for w in _POS_WORDS if w in text)
        n = sum(1 for w in _NEG_WORDS if w in text)
        if p > n:
            pos += 1
        elif n > p:
            neg += 1
            if not top_event:
                top_event = str(item.get("title") or "")
        else:
            neu += 1
    total = max(1, len(news))
    heat = min(100.0, len(news) * 12 + (float(turnover or 0) * 2))
    if neg >= pos + 2:
        label = "偏负面"
    elif pos >= neg + 2:
        label = "偏正面"
    else:
        label = "中性/分歧"
    return {
        "available": True,
        "positive": round(pos / total * 100, 1),
        "neutral": round(neu / total * 100, 1),
        "negative": round(neg / total * 100, 1),
        "heat": round(heat, 1),
        "label": label,
        "topEvent": top_event,
        "source": "资讯标题词典",
        "note": "基于关联资讯标题/摘要的关键词规则估算，覆盖有限，不是全量舆情；只做描述，不预测方向。",
    }


def build_stock(conn: Any, code: str, period: str = "daily") -> dict[str, Any] | None:
    stock = one(conn, "SELECT * FROM stocks WHERE code=?", (code,))
    if not stock:
        return None
    meta = data_meta(conn)
    if not stock.get("price"):
        # 全市场检索可以命中，但池外标的可能尚未同步日线；给出明确空态而不是 500。
        return {
            "quote": {
                "code": stock["code"], "name": stock["name"], "industry": stock.get("industry"),
                "asset": stock.get("asset"), "price": None, "prevClose": None,
                "change": None, "changePct": None, "open": None, "high": None, "low": None,
                "marketCap": stock.get("market_cap"), "pe": stock.get("pe_ttm"), "pb": stock.get("pb"),
                "dividendYield": stock.get("dividend_yield"), "turnover": stock.get("turnover"),
                "volume": stock.get("volume"), "amount": stock.get("amount"), "beta": stock.get("beta"),
                "updatedAt": stock.get("updated_at"), "nextReportDate": stock.get("next_report_date"),
            },
            "chart": {"period": period, "bars": [], "ma5": [], "ma10": [], "ma20": []},
            "technical": {
                "ma5": None, "ma10": None, "ma20": None, "drawdown": None, "return20": None,
                "volumeRatio": None, "trend": "数据暂缺",
                "summary": ["该标的暂无可用收盘行情；请先同步该标的日线，再做技术面判断。"],
            },
            "summary": ["该标的暂无可用收盘行情；当前只能展示证券主数据，不能做估值分位、技术面与财务对比。"],
            "valuation": {
                "pe": stock.get("pe_ttm"), "pb": stock.get("pb"), "pePercentile": None,
                "pbPercentile": None, "industryPe": None, "samples": 0, "label": "无估值数据",
            },
            "financials": [],
            "report": None,
            "risks": [
                {"title": "行情数据暂缺", "detail": "该标的尚未同步日线；不要基于空数据做判断。", "level": "amber"}
            ],
            "news": rows(conn, "SELECT * FROM news WHERE code=? ORDER BY published_at DESC LIMIT 6", (code,)),
            "todayNews": rows(conn, "SELECT * FROM news WHERE code=? ORDER BY published_at DESC LIMIT 3", (code,)),
            "earningsFlash": _earnings_flash(None, None),
            "institutionalView": _institutional_view(),
            "sensitivity": _sensitivity(None),
            "sentiment": _sentiment([], None),
            "dataDate": meta["dataDate"],
            "disclaimer": DISCLAIMER,
            "isDemo": meta["isDemo"],
            "dataSource": meta["dataSource"],
        }
    all_bars = stock_bars(conn, code)
    chart_bars = aggregate(all_bars, period)
    chart_bars = chart_bars[-180:]
    closes = [b["close"] for b in chart_bars]
    ma5 = ma(closes, 5)
    ma10 = ma(closes, 10)
    ma20 = ma(closes, 20)

    daily = all_bars[-180:]
    daily_closes = [b["close"] for b in daily]
    ma20_daily = ma(daily_closes, 20)[-1] if daily_closes else None
    high_180 = max(daily_closes) if daily_closes else stock["price"]
    dd = (stock["price"] / high_180 - 1) * 100 if high_180 else 0
    avg_vol = sum(b["volume"] for b in daily[-20:]) / max(1, len(daily[-20:]))
    vol_ratio = stock["volume"] / avg_vol if avg_vol else 0
    ret20 = pct(stock["price"], daily_closes[-21]) if len(daily_closes) > 21 else 0

    valuations = rows(conn, """SELECT pe_ttm, pb FROM (
                                 SELECT pe_ttm, pb_mrq AS pb, trade_date AS date
                                   FROM md_valuation_daily
                                  WHERE symbol=? ORDER BY trade_date DESC LIMIT 750
                               ) t ORDER BY date ASC""", (_with_suffix(code),))
    pe_vals = [v["pe_ttm"] for v in valuations if v["pe_ttm"] is not None]
    pb_vals = [v["pb"] for v in valuations if v["pb"] is not None]
    pe_pct = percentile(pe_vals, stock["pe_ttm"])
    pb_pct = percentile(pb_vals, stock["pb"])
    peer = one(conn, "SELECT AVG(pe_ttm) AS pe FROM stocks WHERE industry=? AND pe_ttm IS NOT NULL AND code<>?",
               (stock["industry"], code))

    fins = rows(conn, "SELECT * FROM financials WHERE code=? AND report_date<=? ORDER BY period ASC", (code, latest_date(conn)))
    if stock["asset"] == "etf":
        fins = []
    latest = fins[-1] if fins else None
    prev = fins[-2] if len(fins) > 1 else None

    risks = []
    if pe_pct is not None and pe_pct >= 70:
        risks.append({"title": "估值分位偏高", "detail": f"当前 PE {stock['pe_ttm']:.2f}x，处于近 3 年 {pe_pct:.1f}% 分位。", "level": "amber"})
    if dd <= -15:
        risks.append({"title": "趋势偏弱", "detail": f"较近 180 日高点回撤 {dd:.1f}%，现价位于 MA20 {'下方' if ma20_daily and stock['price'] < ma20_daily else '上方'}。", "level": "red"})
    if vol_ratio >= 1.5:
        risks.append({"title": "成交放大", "detail": f"成交量为 20 日均量的 {vol_ratio:.1f} 倍，关注放量方向。", "level": "amber"})
    if latest and prev and latest.get("gross_margin") is not None and prev.get("gross_margin") is not None:
        if latest["gross_margin"] < prev["gross_margin"]:
            risks.append({"title": "毛利率下滑", "detail": f"最新报告期毛利率 {latest['gross_margin']:.1f}%，较上期 {prev['gross_margin']:.1f}% 下降。", "level": "amber"})
    if not risks:
        risks.append({"title": "暂未触发规则风险", "detail": "估值、趋势、成交与毛利率未同时触发预设阈值；仍需独立判断。", "level": "green"})

    summary = []
    if stock["asset"] != "etf" and pe_pct is not None:
        summary.append(f"当前 PE {stock['pe_ttm']:.2f}x，处于近 3 年 {pe_pct:.1f}% 分位；PB {stock['pb']:.2f}x。")
    if latest:
        summary.append(f"{latest['period']} 营收 {latest['revenue']:.0f} 亿元（同比 {latest['revenue_yoy']:+.1f}%），归母净利 {latest['net_profit']:.0f} 亿元（同比 {latest['profit_yoy']:+.1f}%）。")
        summary.append(f"毛利率 {latest['gross_margin']:.1f}%，ROE {latest['roe']:.1f}%。")
    if daily_closes:
        summary.append(f"股价较近 180 日高点回撤 {dd:.1f}%，现价{'低于' if ma20_daily and stock['price'] < ma20_daily else '高于'} MA20；近 20 日涨跌 {ret20:+.1f}%。")

    beta_value = stock.get("beta")
    q = {
        "code": stock["code"], "name": stock["name"], "industry": stock["industry"],
        "asset": stock["asset"], "price": stock["price"], "prevClose": stock["prev_close"],
        "change": stock["price"] - stock["prev_close"], "changePct": pct(stock["price"], stock["prev_close"]),
        "open": stock["open"], "high": stock["high"], "low": stock["low"],
        "marketCap": stock["market_cap"], "pe": stock["pe_ttm"], "pb": stock["pb"],
        "dividendYield": stock["dividend_yield"], "turnover": stock["turnover"],
        "volume": stock["volume"], "amount": stock["amount"], "beta": beta_value,
        "updatedAt": stock["updated_at"], "nextReportDate": stock["next_report_date"],
    }
    chart = {
        "period": period,
        "bars": [{"time": b["date"], "open": b["open"], "high": b["high"], "low": b["low"],
                  "close": b["close"], "volume": b["volume"]} for b in chart_bars],
        "ma5": [{"time": b["date"], "value": v} for b, v in zip(chart_bars, ma5) if v is not None],
        "ma10": [{"time": b["date"], "value": v} for b, v in zip(chart_bars, ma10) if v is not None],
        "ma20": [{"time": b["date"], "value": v} for b, v in zip(chart_bars, ma20) if v is not None],
    }
    technical = {
        "ma5": ma5[-1] if ma5 else None, "ma10": ma10[-1] if ma10 else None, "ma20": ma20[-1] if ma20 else None,
        "drawdown": dd, "return20": ret20, "volumeRatio": vol_ratio,
        "trend": "偏强" if ma20_daily and stock["price"] >= ma20_daily else "偏弱",
        "summary": summary,
    }
    valuation = {
        "pe": stock["pe_ttm"], "pb": stock["pb"], "pePercentile": pe_pct, "pbPercentile": pb_pct,
        "industryPe": peer["pe"] if peer else None, "samples": len(pe_vals),
        "label": "近 3 年历史分位" if pe_vals else "无估值数据",
    }
    report = None
    if latest:
        report = {
            "period": latest["period"], "reportDate": latest["report_date"],
            "revenue": latest["revenue"], "revenueYoY": latest["revenue_yoy"],
            "netProfit": latest["net_profit"], "profitYoY": latest["profit_yoy"],
            "grossMargin": latest["gross_margin"], "roe": latest["roe"], "ocf": latest["ocf"],
            "prev": prev,
        }
    news = rows(conn, "SELECT * FROM news WHERE code=? ORDER BY published_at DESC LIMIT 6", (code,))
    meta = data_meta(conn)
    return {
        "quote": q, "chart": chart, "technical": technical, "summary": summary,
        "valuation": valuation, "financials": fins, "report": report, "risks": risks,
        "news": news, "todayNews": news[:3],
        "earningsFlash": _earnings_flash(latest, prev),
        "institutionalView": _institutional_view(),
        "sensitivity": _sensitivity(beta_value),
        "sentiment": _sentiment(news, stock.get("turnover")),
        "dataDate": all_bars[-1]["date"] if all_bars else meta["dataDate"],
        "disclaimer": DISCLAIMER, "isDemo": meta["isDemo"], "dataSource": meta["dataSource"],
    }


def build_topic(conn: Any, topic_id: str) -> dict[str, Any] | None:
    topic = one(conn, "SELECT * FROM topics WHERE id=?", (topic_id,))
    if not topic:
        return None
    bars = rows(conn, "SELECT * FROM topic_bars WHERE topic_id=? ORDER BY date ASC", (topic_id,))
    closes = [b["close"] for b in bars]
    base = compute_base_rate(bars)
    meta = data_meta(conn)
    vp = topic["valuation_percentile"] or 0
    tp = topic["turnover_percentile"] or 0
    heat = topic["heat"] or 0
    as_of = (topic["updated_at"] or meta["dataDate"])[:10]
    stocks = rows(conn, """SELECT s.* FROM topic_stocks ts JOIN stocks s ON s.code=ts.code WHERE ts.topic_id=?""", (topic_id,))
    stock_cards = []
    for s in stocks:
        stock_cards.append({"code": s["code"], "name": s["name"], "industry": s["industry"],
                            "price": s["price"], "changePct": pct(s["price"], s["prev_close"])})
    news = rows(conn, """SELECT * FROM news WHERE topic_id=? OR code IN (SELECT code FROM topic_stocks WHERE topic_id=?)
                         ORDER BY published_at DESC LIMIT 6""", (topic_id, topic_id))
    news_is_demo = not bool(conn.execute(
        "SELECT 1 FROM news WHERE id LIKE 'doc-%' OR id LIKE 'news-%' OR id LIKE 'ann-%' OR id LIKE 'rep-%' LIMIT 1").fetchone())
    facts = [
        {"title": "订单/政策", "detail": topic["summary"], "source": "公开信息", "date": as_of},
        {"title": "估值位置", "detail": f"等权代理指数估值处于近 3 年 {vp:.0f}% 分位，成交热度 {tp:.0f}% 分位。", "source": "行情数据", "date": as_of},
        {"title": "历史分布", "detail": f"高估值 + 高换手条件下，未来 20 日收益中位数 {base['medianReturn']:+.1f}%，样本 {base['sample']} 次。", "source": "历史统计", "date": as_of},
    ]
    key_points = [
        f"热度 {heat:.0f}，估值 {vp:.0f}% 分位，拥挤度 {tp:.0f}% 分位。",
        "热度与估值是两件事，不能用热度代替安全边际。",
        "若后续订单/政策不及预期，估值与盈利可能同时承压。",
    ]
    risks = [
        {"title": "估值与拥挤度组合", "detail": f"估值 {vp:.0f}% 分位、拥挤度 {tp:.0f}% 分位；不同组合的历史分布差异很大，样本不代表未来。"},
        {"title": "主题成分差异", "detail": "同名主题内个股基本面差异大，板块涨跌不等于个股同涨同跌。"},
    ]
    spark = [{"time": b["date"], "value": b["close"]} for b in bars[-60:]]
    return {
        "id": topic["id"], "name": topic["name"], "summary": topic["summary"],
        "heat": topic["heat"], "valuationPercentile": topic["valuation_percentile"],
        "turnoverPercentile": topic["turnover_percentile"], "updatedAt": topic["updated_at"],
        "facts": facts, "keyPoints": key_points, "risks": risks, "baseRate": base,
        "stocks": stock_cards, "news": news, "spark": spark, "disclaimer": DISCLAIMER,
        "isDemo": meta["isDemo"], "dataSource": "等权代理：成分股收盘数据" if not meta["isDemo"] else "主题演示数据",
        "newsIsDemo": news_is_demo,
    }


def _cut(values: list[float], pct: float) -> float:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return 0.0
    idx = min(len(clean) - 1, max(0, int(len(clean) * pct / 100) - 1))
    return clean[idx]


def compute_base_rate(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if len(bars) < 60:
        return {"medianReturn": 0, "maxDrawdown": 0, "winRate": 0, "sample": 0, "period": "样本不足", "note": "样本不足"}
    entries: list[int] = []
    threshold = 80
    for threshold in (80, 70, 60, 50):
        vcut = _cut([b["valuation"] or 0 for b in bars], threshold)
        tcut = _cut([b["turnover"] or 0 for b in bars], threshold)
        entries = [i for i, b in enumerate(bars)
                   if (b["valuation"] or 0) >= vcut and (b["turnover"] or 0) >= tcut and i + 20 < len(bars)]
        if len(entries) >= 8:
            break
    if not entries:
        return {"medianReturn": 0, "maxDrawdown": 0, "winRate": 0, "sample": 0, "period": "样本不足", "note": "样本不足"}
    rets, dds = [], []
    for i in entries:
        entry = bars[i]["close"]
        fwd = bars[i + 1:i + 21]
        rets.append((fwd[-1]["close"] / entry - 1) * 100)
        peak = entry
        worst = 0.0
        for x in fwd:
            peak = max(peak, x["close"])
            worst = min(worst, x["close"] / peak - 1)
        dds.append(worst * 100)
    return {
        "medianReturn": round(median(rets), 1),
        "maxDrawdown": round(median(dds), 1),
        "winRate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 0),
        "sample": len(entries), "period": f"近 3 年 · 估值/换手 ≥ {threshold}% 分位",
        "note": "历史分布不是预测；样本偏差与结构变化需考虑。",
    }


def portfolio_rows(conn: Any, user_id: int) -> list[dict[str, Any]]:
    return rows(conn, """SELECT p.*, s.name, s.industry AS stock_industry, s.price, s.prev_close, s.beta,
                                s.asset FROM portfolio p LEFT JOIN stocks s ON s.code=p.code
                         WHERE p.user_id=?""", (user_id,))


def build_portfolio(conn: Any, user_id: int) -> dict[str, Any]:
    holdings = portfolio_rows(conn, user_id)
    if not holdings:
        return {
            "totalValue": 0, "riskScore": 0, "riskLabel": "未导入", "dailyChange": 0,
            "kpis": [{"label": "总资产", "value": "0 万"}, {"label": "前三大持仓", "value": "—"},
                     {"label": "最大行业暴露", "value": "—"}, {"label": "历史最大回撤", "value": "—"}],
            "holdings": [], "diagnosis": [], "exposure": [], "deviation": [], "stress": [],
            "costs": {"tradeCostPct": 0, "annualTurnover": 0, "impactCostPct": 0, "extraCost": 0},
            "summary": "尚未导入持仓；导入后才能做集中度、行业暴露与压力测试。",
            "beta": 0, "dataDate": latest_date(conn), "disclaimer": DISCLAIMER,
        }
    values = []
    for h in holdings:
        if h["code"] == "CASH":
            value = h["shares"] or 0
            price = 1.0
            change = 0.0
        else:
            value = (h["shares"] or 0) * (h["price"] or 0)
            price = h["price"] or 0
            change = pct(price, h["prev_close"] or price)
        values.append((h, value, change))
    total = sum(v for _, v, _ in values) or 1
    for h, value, _ in values:
        h["value"] = value
        h["weight"] = value / total * 100
    stock_values = [(h, v) for h, v, _ in values if h["code"] != "CASH"]
    top3 = sum(h["weight"] for h, _ in sorted(stock_values, key=lambda x: x[1], reverse=True)[:3])
    industries: dict[str, float] = {}
    for h, _ in stock_values:
        ind = h["stock_industry"] or h["industry"] or "其他"
        industries[ind] = industries.get(ind, 0) + h["weight"]
    max_ind = max(industries.values()) if industries else 0
    beta = sum((h["beta"] or 0) * h["weight"] / 100 for h, _ in stock_values)
    daily_change = sum(h["weight"] * c / 100 for h, _, c in values)
    weighted_dd = 0.0
    for h, _ in stock_values:
        bars = stock_bars(conn, h["code"], 180)
        if bars:
            weighted_dd += max_drawdown([b["close"] for b in bars]) * h["weight"] / 100

    score = round(min(95, max(20, 18 + top3 * 0.55 + max_ind * 0.45 + abs(weighted_dd) * 0.6)))
    label = "偏集中" if score >= 65 else "相对均衡"
    diagnosis = []
    if max_ind >= 24:
        diagnosis.append({"title": "行业集中度偏高", "detail": f"最大行业 {max(industries, key=industries.get)} 占 {max_ind:.0f}%；单行业波动会被放大。", "evidence": f"行业暴露：{max(industries, key=industries.get)} {max_ind:.0f}%", "risk": "行业回撤会直接拖累组合。"})
    if top3 >= 60:
        diagnosis.append({"title": "前三大持仓占比偏高", "detail": f"前三大合计 {top3:.0f}%，重仓股波动会显著影响组合。", "evidence": f"前三大 {top3:.0f}%", "risk": "个股事件可能造成较大净值波动。"})
    devs = []
    for h, _, _ in values:
        diff = h["weight"] - (h["target_weight"] or 0)
        if abs(diff) >= 3:
            devs.append((h, diff))
    if devs:
        h, diff = max(devs, key=lambda x: abs(x[1]))
        diagnosis.append({"title": "配置偏离超过阈值", "detail": f"{h['name'] or h['code']} 当前 {h['weight']:.0f}%，目标 {h['target_weight']:.0f}%，偏离 {diff:+.0f}%。", "evidence": f"目标 vs 当前偏离 {diff:+.0f}%", "risk": "偏离只展示，不构成调仓建议；是否调整由你决定。"})
    meta = one(conn, "SELECT * FROM portfolio_meta WHERE user_id=?", (user_id,)) or {"trade_cost_pct": 0.4, "annual_turnover": 35, "impact_cost_pct": 0.08}
    if meta["annual_turnover"] >= 30:
        diagnosis.append({"title": "换手与成本需要关注", "detail": f"示例年化换手 {meta['annual_turnover']:.0f}%，预估再平衡成本 {meta['trade_cost_pct']:.1f}%。", "evidence": f"单次冲击成本约 {meta['impact_cost_pct']:.2f}%", "risk": "频繁调仓会侵蚀收益。"})

    exposure = [{"name": k, "weight": round(v, 1)} for k, v in sorted(industries.items(), key=lambda x: x[1], reverse=True)]
    if any(h["code"] == "CASH" for h, _, _ in values):
        cash = sum(h["weight"] for h, _, _ in values if h["code"] == "CASH")
        exposure.append({"name": "现金", "weight": round(cash, 1)})
    deviation = []
    for h, _, _ in values:
        diff = h["weight"] - (h["target_weight"] or 0)
        deviation.append({"name": h["name"] or ("现金" if h["code"] == "CASH" else h["code"]),
                          "current": round(h["weight"], 1), "target": h["target_weight"],
                          "diff": round(diff, 1), "status": "超配" if diff > 0.5 else ("低配" if diff < -0.5 else "达标")})
    stress = [
        {"name": "沪深 300 −10%", "value": round(beta * -10, 1)},
        {"name": "利率 +50bp", "value": -2.4},
        {"name": "新能源 −15%", "value": round(industries.get("新能源", 0) * -0.15, 1)},
        {"name": "消费 −10%", "value": round(industries.get("食品饮料", 0) * -0.10, 1)},
    ]
    kpis = [
        {"label": "总资产", "value": f"{total/10000:.1f} 万"},
        {"label": "前三大持仓", "value": f"{top3:.0f}%"},
        {"label": "最大行业暴露", "value": f"{max_ind:.0f}%"},
        {"label": "历史最大回撤", "value": f"{weighted_dd:.1f}%"},
    ]
    summary = f"风险主要来自{'行业集中' if max_ind >= 24 else '个股与市场波动'}，不是来自市场整体。"
    return {
        "totalValue": total, "riskScore": score, "riskLabel": label, "dailyChange": daily_change,
        "kpis": kpis, "holdings": [{"code": h["code"], "name": h["name"] or ("现金" if h["code"] == "CASH" else h["code"]),
                                    "industry": h["stock_industry"] or h["industry"] or "现金",
                                    "weight": round(h["weight"], 1), "value": round(h["value"], 0),
                                    "shares": h["shares"], "cost": h["cost"], "price": h.get("price") or 1,
                                    "pnlPct": round((h.get("price") or 1) / h["cost"] * 100 - 100, 1) if h["cost"] else 0}
                                   for h, _, _ in values],
        "diagnosis": diagnosis, "exposure": exposure, "deviation": deviation, "stress": stress,
        "costs": {"tradeCostPct": meta["trade_cost_pct"], "annualTurnover": meta["annual_turnover"],
                  "impactCostPct": meta["impact_cost_pct"], "extraCost": 0.5},
        "summary": summary, "beta": round(beta, 2), "dataDate": latest_date(conn), "disclaimer": DISCLAIMER,
    }


def build_home(conn: Any, user_id: int) -> dict[str, Any]:
    stocks = rows(conn, "SELECT * FROM stocks")
    by_code = {s["code"]: s for s in stocks}
    meta = data_meta(conn)
    data_date = meta["dataDate"]
    meta_info = build_meta(conn)
    real_today = date.fromisoformat(data_date)
    watch = rows(conn, "SELECT * FROM watchlist WHERE user_id=?", (user_id,))
    watch_cards = []
    for w in watch:
        s = by_code.get(w["code"])
        if s:
            watch_cards.append({"code": s["code"], "name": s["name"], "price": s["price"],
                                "changePct": pct(s["price"], s["prev_close"]), "group": w["group_name"]})
    topics = rows(conn, "SELECT * FROM topics ORDER BY heat DESC LIMIT 3")
    topic_cards = []
    for t in topics:
        bars = rows(conn, "SELECT close FROM topic_bars WHERE topic_id=? ORDER BY date DESC LIMIT 30", (t["id"],))
        topic_cards.append({"id": t["id"], "name": t["name"], "summary": t["summary"], "heat": t["heat"],
                            "valuationPercentile": t["valuation_percentile"],
                            "spark": [b["close"] for b in reversed(bars)]})

    daily = []
    watch_codes = {w["code"] for w in watch}
    upcoming = [s for s in by_code.values()
                if s["code"] in watch_codes and s["next_report_date"] and s["next_report_date"] >= data_date]
    if upcoming:
        s = sorted(upcoming, key=lambda x: x["next_report_date"])[0]
        days = (date.fromisoformat(s["next_report_date"]) - real_today).days
        when = "今天预计披露" if days == 0 else (f"距预计披露还有 {days} 天" if days > 0 else f"已于 {s['next_report_date']} 披露")
        daily.append({"tag": "自选 · 财报", "title": f"{s['name']}：{s['next_report_date']} 预计披露",
                      "detail": f"{when}，关注毛利率与现金流。",
                      "link": {"type": "stock", "id": s["code"]}})
    if watch_cards:
        s = max(watch_cards, key=lambda x: abs(x["changePct"]))
        daily.append({"tag": "自选 · 异动", "title": f"{s['name']} {s['changePct']:+.2f}%",
                      "detail": f"收盘 {s['price']:.2f} 元；打开个股查看估值与风险。",
                      "link": {"type": "stock", "id": s["code"]}})
    pf = build_portfolio(conn, user_id)
    if pf["deviation"]:
        d = max(pf["deviation"], key=lambda x: abs(x["diff"]))
        daily.append({"tag": "组合 · 偏离", "title": f"{d['name']} {d['diff']:+.0f}%",
                      "detail": f"当前 {d['current']}%，目标 {d['target']}%；只展示偏离，不构成调仓建议。",
                      "link": {"type": "portfolio"}})
    t = max(topics, key=lambda x: x["valuation_percentile"])
    daily.append({"tag": "市场 · 热度", "title": f"{t['name']} 估值 {t['valuation_percentile']:.0f}% 分位",
                  "detail": f"热度 {t['heat']:.0f}；先看历史 base rate，再决定要不要追。",
                  "link": {"type": "topic", "id": t["id"]}})
    daily = daily[:3]

    etf = by_code.get("510300")
    review = {
        "title": "收盘复盘",
        "summary": (f"沪深 300 ETF 收盘 {etf['price']:.3f}（{pct(etf['price'], etf['prev_close']):+.2f}%）；你的组合今日 {signed(pf['dailyChange'])}，风险主要来自行业集中。" if pf["holdings"] else f"沪深 300 ETF 收盘 {etf['price']:.3f}（{pct(etf['price'], etf['prev_close']):+.2f}%）；尚未导入组合，先做一次体检。") if etf else "",
        "facts": [
            f"组合总资产 {pf['totalValue']/10000:.1f} 万元，风险分 {pf['riskScore']}。" if pf["holdings"] else "尚未导入组合，去「组合」页导入 CSV 或手工持仓。",
            f"前三大持仓 {pf['kpis'][1]['value']}，最大行业 {pf['kpis'][2]['value']}。" if pf["holdings"] else "导入后才能计算集中度、行业暴露与配置偏离。",
            "数据为收盘后快照，不是实时行情。",
        ],
    }
    idx_rows = rows(conn, "SELECT * FROM indices ORDER BY code")
    indices = [{"name": r["name"], "value": f"{r['price']:.1f}", "change": pct(r["price"], r["prev_close"])}
               for r in idx_rows]
    if not indices:
        indices = [
            {"name": "沪深 300", "value": "4128.6", "change": 0.68},
            {"name": "创业板指", "value": "2214.8", "change": 1.12},
        ]
    glossary = [
        {"term": "PE 分位", "text": "当前市盈率在过去 N 年里的位置；分位越低通常越“便宜”，但不预测涨跌。"},
        {"term": "拥挤度", "text": "板块成交 / 换手的热度；拥挤度偏高，短期波动通常更大。"},
        {"term": "base rate", "text": "历史上类似情况出现的频率，用分布替代“我感觉”。"},
        {"term": "最大回撤", "text": "从阶段高点到之后低点的最大跌幅，衡量持有体验。"},
        {"term": "换手率", "text": "一段时间内股票被交易的频繁程度；过高可能伴随情绪化交易。"},
        {"term": "beta", "text": "股价对大盘系统性波动的敏感度；数值越高越“跟涨跟跌”。"},
        {"term": "配置偏离", "text": "目标权重与当前权重的差；只展示，不构成调仓建议。"},
        {"term": "ROE", "text": "净资产收益率，衡量股东投入资本的盈利效率。"},
    ]
    return {"dataDate": data_date, "dataSource": meta["dataSource"], "isDemo": meta["isDemo"],
            "ageDays": meta_info["ageDays"], "isStale": meta_info["isStale"],
            "user": {"id": user_id, "name": "演示用户"}, "daily": daily, "review": review,
            "indices": indices, "topics": topic_cards, "watchlist": watch_cards, "glossary": glossary,
            "disclaimer": DISCLAIMER}


def build_watchlist(conn: Any, user_id: int) -> dict[str, Any]:
    watch = rows(conn, "SELECT * FROM watchlist WHERE user_id=? ORDER BY created_at ASC", (user_id,))
    groups: dict[str, list[dict[str, Any]]] = {}
    for w in watch:
        s = one(conn, "SELECT * FROM stocks WHERE code=?", (w["code"],))
        if not s:
            continue
        groups.setdefault(w["group_name"] or "默认", []).append({
            "code": s["code"], "name": s["name"], "industry": s["industry"], "price": s["price"],
            "changePct": pct(s["price"], s["prev_close"]),
        })
    events = rows(conn, "SELECT * FROM events WHERE user_id=? ORDER BY id DESC", (user_id,))
    for e in events:
        t = one(conn, "SELECT name FROM topics WHERE id=?", (e["code"],))
        s = one(conn, "SELECT name FROM stocks WHERE code=?", (e["code"],))
        e["name"] = (t or s or {}).get("name") or e["code"]
    logs = rows(conn, "SELECT * FROM event_logs WHERE user_id=? ORDER BY triggered_at DESC", (user_id,))
    return {"groups": [{"name": k, "items": v} for k, v in groups.items()], "events": events, "logs": logs,
            "disclaimer": "关注事件在收盘后更新；不提供实时推送。"}


def build_search(conn: Any, q: str) -> dict[str, Any]:
    q = (q or "").strip()
    stocks = []
    if q:
        like = f"%{q}%"
        stocks = rows(conn, """SELECT * FROM stocks WHERE name LIKE ? OR code LIKE ? OR pinyin LIKE ? OR industry LIKE ?
                              LIMIT 8""", (like, like, like, like))
    topics = rows(conn, "SELECT * FROM topics WHERE name LIKE ? LIMIT 4", (f"%{q}%",)) if q else []
    results = [{"type": "stock", "id": s["code"], "name": s["name"], "sub": f"{s['code']} · {s['industry']}",
                "price": s["price"], "changePct": pct(s["price"], s["prev_close"])} for s in stocks]
    results += [{"type": "topic", "id": t["id"], "name": t["name"], "sub": "行业 / 主题",
                 "price": None, "changePct": None} for t in topics]

    presets = []
    if not q:
        # 只用服务层快照字段，避免每次搜索对全市场逐股扫 750 天 bars/valuations
        pool = [
            s for s in rows(conn, "SELECT * FROM stocks")
            if s["asset"] == "stock" and s.get("price") is not None
        ]

        def card(s: dict[str, Any], reason: str) -> dict[str, Any]:
            return {
                "type": "stock", "id": s["code"], "name": s["name"],
                "sub": f"{s['code']} · {s['industry']}", "price": s["price"],
                "changePct": pct(s["price"], s["prev_close"]), "reason": reason,
            }

        low_pe = sorted(
            [s for s in pool if s.get("pe_ttm") is not None and s["pe_ttm"] > 0],
            key=lambda s: s["pe_ttm"],
        )[:5]
        momentum = sorted(
            pool, key=lambda s: pct(s["price"], s["prev_close"]), reverse=True
        )[:5]
        dividend = sorted(
            [s for s in pool if s.get("dividend_yield") is not None and s["dividend_yield"] > 0],
            key=lambda s: s["dividend_yield"], reverse=True,
        )[:5]
        presets = [
            {
                "key": "low_pe", "label": "低估值", "desc": "按当前 PE 快照从低到高（非历史分位）",
                "items": [card(s, f"PE {s['pe_ttm']:.1f}x") for s in low_pe],
            },
            {
                "key": "momentum", "label": "今日强势", "desc": "按当日涨幅快照（非 20 日动量）",
                "items": [card(s, f"今日 {pct(s['price'], s['prev_close']):+.1f}%") for s in momentum],
            },
            {
                "key": "dividend", "label": "高股息", "desc": "按当前股息率快照从高到低",
                "items": [card(s, f"股息率 {s['dividend_yield']:.2f}%") for s in dividend],
            },
        ]
    return {"results": results, "presets": presets}


def build_data_quality(conn: Any) -> dict[str, Any]:
    latest = latest_date(conn)
    stocks = rows(conn, "SELECT code, name, asset, price, pe_ttm, updated_at FROM stocks")
    pool = [s for s in stocks if s["asset"] != "etf" and s["price"] is not None]
    # A 股/美股交易日不同，按各自市场的最新快照判断“未更新”。
    def market_of(code: str) -> str:
        return "US" if "." in code else "CN"
    latest_by_market = {m: max((s.get("updated_at") or "")[:10] for s in pool if market_of(s["code"]) == m)
                        for m in {market_of(s["code"]) for s in pool}}
    stale = [s["code"] for s in pool if (s.get("updated_at") or "")[:10] != latest_by_market.get(market_of(s["code"]))]
    checks = [{
        "key": "bars",
        "label": "日线覆盖",
        "status": "fail" if not pool or stale else "pass",
        "detail": f"CN {latest_by_market.get('CN','—')} / US {latest_by_market.get('US','—')}；有日线 {len(pool)}/{len(stocks)} 只，未更新 {len(stale)}",
    }]
    pool_codes = [s["code"] for s in pool]
    fin_codes = {r["code"] for r in rows(conn, "SELECT DISTINCT code FROM financials")}
    no_fin = [c for c in pool_codes if c not in fin_codes]
    fin_cov = (len(pool_codes) - len(no_fin)) / len(pool_codes) if pool_codes else 1.0
    checks.append({
        "key": "financials",
        "label": "已披露财务",
        "status": "pass" if not no_fin else ("warn" if fin_cov > 0 else "fail"),
        "detail": f"有财务 {len(pool_codes) - len(no_fin)}/{len(pool_codes)} 只；最新 {latest}",
    })
    pool_cn = [s for s in pool if market_of(s["code"]) == "CN"]
    no_val = [s["code"] for s in pool_cn if s.get("pe_ttm") is None]
    checks.append({
        "key": "valuations",
        "label": "估值快照（A 股）",
        "status": "pass" if not no_val else ("warn" if len(no_val) < max(1, len(pool_cn) // 2) else "fail"),
        "detail": f"A 股估值缺失 {len(no_val)}/{len(pool_cn)}；美股无估值源，已排除",
    })
    etf_bad = [s["code"] for s in stocks if s["asset"] == "etf" and s.get("pe_ttm") is not None]
    checks.append({"key": "etf", "label": "ETF 口径", "status": "fail" if etf_bad else "pass",
                   "detail": "ETF 不适用财务/估值" if not etf_bad else f"ETF 混入财务/估值：{', '.join(etf_bad)}"})
    age = max(0, (date.today() - date.fromisoformat(latest)).days)
    checks.append({"key": "freshness", "label": "数据新鲜度",
                   "status": "pass" if age <= 2 else ("warn" if age <= 7 else "fail"),
                   "detail": f"数据日 {latest}，距今 {age} 天；超过 2 天提示，超过 7 天判失败"})
    return {"ok": all(c["status"] != "fail" for c in checks), "dataDate": latest,
            "ageDays": age, "stocks": len(stocks), "checks": checks}
