"""Rule engine + read models for the Invest H5.

Everything here is deterministic and computed from the local SQLite cache.
No LLM, no generated opinions: each sentence is backed by a number in the DB.
"""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Iterable

DATA_DATE = date.today().isoformat()  # fallback when a DB has no bars
DISCLAIMER = "收盘数据 · 非实时 · 非投资建议"
DISCLAIMER_EN = "EOD data · not real-time · not investment advice"

# H5 市场切换：A 股代码为 6 位数字，美股代码带交易所后缀（如 AAPL.O）
US_EN_NAMES: dict[str, str] = {
    "AAPL.O": "Apple", "MSFT.O": "Microsoft", "NVDA.O": "NVIDIA", "AMZN.O": "Amazon",
    "GOOGL.O": "Alphabet A", "GOOG.O": "Alphabet C", "META.O": "Meta", "TSLA.O": "Tesla",
    "AVGO.O": "Broadcom", "AMD.O": "AMD", "NFLX.O": "Netflix", "INTC.O": "Intel",
    "JPM.N": "JPMorgan", "BAC.N": "Bank of America", "V.N": "Visa", "MA.N": "Mastercard",
    "KO.N": "Coca-Cola", "PEP.O": "PepsiCo", "WMT.N": "Walmart", "DIS.N": "Disney",
    "XOM.N": "Exxon Mobil", "CVX.N": "Chevron", "UNH.N": "UnitedHealth", "JNJ.N": "Johnson & Johnson",
}

US_GLOSSARY = [
    {"term": "PE percentile", "text": "Where current P/E sits in its own history; lower is usually cheaper, but it does not predict returns."},
    {"term": "Crowding", "text": "Volume and turnover heat in a sector; crowded names tend to swing more in the short run."},
    {"term": "Base rate", "text": "How often similar setups happened before; use a distribution instead of a gut feeling."},
    {"term": "Max drawdown", "text": "Largest peak-to-trough decline, a measure of holding experience."},
    {"term": "Turnover", "text": "How frequently a stock is traded; very high turnover can signal emotional trading."},
    {"term": "Beta", "text": "Sensitivity to broad-market moves; higher beta means larger swings with the index."},
    {"term": "Allocation gap", "text": "Difference between target and current weight; shown for context, not a trade instruction."},
    {"term": "ROE", "text": "Return on equity, a measure of how efficiently capital is used."},
]


def normalize_market(market: str | None) -> str:
    return "US" if str(market or "").strip().upper() == "US" else "CN"


def _market_sql(market: str) -> str:
    return "market='US'" if normalize_market(market) == "US" else "COALESCE(market,'CN')='CN'"


def _is_us_code(code: str | None) -> bool:
    return "." in str(code or "")


def _display_name(stock: dict[str, Any], market: str | None = None) -> str:
    code = str(stock.get("code") or "")
    if normalize_market(market) == "US" or _is_us_code(code):
        mapped = US_EN_NAMES.get(code)
        if mapped:
            return mapped
        name = str(stock.get("name") or "").strip()
        # 英文模式优先英文名；数据平台美股 name 多为中文时回退到 ticker。
        if name and not re.search(r"[一-鿿]", name):
            return name
        return code.split(".")[0]
    return str(stock.get("name") or code)


def _display_industry(stock: dict[str, Any], market: str | None = None) -> str:
    raw = str(stock.get("industry") or "")
    if normalize_market(market) == "US" or _is_us_code(stock.get("code")):
        return "US equity" if not raw or raw == "未分类" else raw
    return raw


def _market_date(conn: Any, market: str) -> str:
    if normalize_market(market) == "US":
        try:
            row = conn.execute(
                "SELECT MAX(updated_at) AS d FROM stocks WHERE market='US' AND price IS NOT NULL"
            ).fetchone()
            if row and row.get("d"):
                return str(row["d"])[:10]
        except Exception:
            pass
    return latest_date(conn)


def _us_coverage(quotes: bool) -> dict[str, bool]:
    """美股覆盖标记：除行情外，其余数据源当前明确不提供。"""
    return {
        "quotes": quotes, "fundamentals": False, "valuation": False,
        "news": False, "industry": False, "index": False,
    }


def _market_meta(conn: Any, market: str) -> dict[str, Any]:
    if normalize_market(market) == "US":
        data_date = _market_date(conn, "US")
        start = date.fromisoformat(data_date)
        age = max(0, (date.today() - start).days)
        weekdays = sum(1 for n in range(1, age + 1) if (start + timedelta(days=n)).weekday() < 5)
        try:
            has_us = bool(conn.execute("SELECT 1 FROM stocks WHERE market='US' LIMIT 1").fetchone())
        except Exception:
            has_us = False
        return {
            "dataDate": data_date,
            "dataSource": "Public EOD (US)" if has_us else "US coverage unavailable",
            "isDemo": False,
            "ageDays": age, "ageTradingDays": weekdays, "isStale": weekdays > 1,
        }
    meta = data_meta(conn)
    data_date = meta["dataDate"]
    start = date.fromisoformat(data_date)
    age = max(0, (date.today() - start).days)
    weekdays = sum(1 for n in range(1, age + 1) if (start + timedelta(days=n)).weekday() < 5)
    return {**meta, "ageDays": age, "ageTradingDays": weekdays, "isStale": weekdays > 1}


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
        # 2026 年部分大盘股与沪深300相关性显著下降，近零 Beta 可能是真实样本期特征；
        # 不再用 abs<0.1 直接丢弃，交给 _sensitivity 按区间解释，并标注样本期。
        if beta is None:
            return None
        try:
            return float(beta) if math.isfinite(float(beta)) else None
        except (TypeError, ValueError):
            return None
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
    note = "按近一年 Beta 分档：<0.8 低、0.8–1.2 中、1.2–1.5 较高、≥1.5 高；仅描述历史敏感度。"
    if abs(beta) < 0.1:
        note = (
            "近一年 Beta 接近 0，说明该股与沪深300的日收益相关性很低；"
            "这不等于低风险，可能是个股独立行情或样本期结构性背离，仅作历史描述。"
        )
    display_beta = 0.0 if abs(beta) < 0.005 else round(beta, 2)
    return {
        "available": True,
        "level": level,
        "beta": display_beta,
        "note": note,
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
    is_us = str(stock.get("market") or "").upper() == "US" or (
        not stock.get("market") and _is_us_code(stock.get("code"))
    )
    market = "US" if is_us else "CN"
    meta = _market_meta(conn, market) if is_us else data_meta(conn)
    display_name = _display_name(stock, market)
    display_industry = _display_industry(stock, market)
    if stock.get("beta") is None:
        # beta 不在 invest_stocks 快照里，从风险日表取最新一条；缺失时仍显示待补充。
        try:
            risk = one(
                conn,
                "SELECT beta_1y FROM md_risk_daily WHERE symbol=? ORDER BY trade_date DESC LIMIT 1",
                (_with_suffix(stock["code"]),),
            )
            if risk and risk.get("beta_1y") is not None:
                stock["beta"] = float(risk["beta_1y"])
        except Exception:
            pass
    if not stock.get("price"):
        # 全市场检索可以命中，但池外标的可能尚未同步日线；给出明确空态而不是 500。
        return {
            "quote": {
                "code": stock["code"], "name": display_name, "industry": display_industry,
                "asset": stock.get("asset"), "market": stock.get("market") or ("US" if is_us else "CN"),
                "price": None, "prevClose": None,
                "change": None, "changePct": None, "open": None, "high": None, "low": None,
                "marketCap": stock.get("market_cap"), "pe": stock.get("pe_ttm"), "pb": stock.get("pb"),
                "dividendYield": stock.get("dividend_yield"), "turnover": stock.get("turnover"),
                "volume": stock.get("volume"), "amount": stock.get("amount"), "beta": stock.get("beta"),
                "updatedAt": stock.get("updated_at"), "nextReportDate": stock.get("next_report_date"),
                "nextReportDateAvailable": bool(stock.get("next_report_date")),
            },
            "chart": {"period": period, "bars": [], "ma5": [], "ma10": [], "ma20": []},
            "technical": {
                "ma5": None, "ma10": None, "ma20": None, "drawdown": None, "return20": None,
                "volumeRatio": None, "trend": "Data pending" if is_us else "数据暂缺",
                "summary": (
                    ["No EOD close is available for this ticker yet; sync its daily bars before technical read-through."]
                    if is_us else ["该标的暂无可用收盘行情；请先同步该标的日线，再做技术面判断。"]
                ),
            },
            "summary": (
                ["No EOD close is available. Only reference data is shown; valuation, technical and financial comparisons are unavailable."]
                if is_us else ["该标的暂无可用收盘行情；当前只能展示证券主数据，不能做估值分位、技术面与财务对比。"]
            ),
            "valuation": {
                "pe": stock.get("pe_ttm"), "pb": stock.get("pb"), "pePercentile": None,
                "pbPercentile": None, "industryPe": None, "samples": 0,
                "label": "No valuation data" if is_us else "无估值数据",
            },
            "financials": [],
            "report": None,
            "risks": [
                {
                    "title": "Quote missing" if is_us else "行情数据暂缺",
                    "detail": (
                        "Daily bars have not been synced for this ticker; do not infer from empty data."
                        if is_us else "该标的尚未同步日线；不要基于空数据做判断。"
                    ),
                    "level": "amber",
                }
            ],
            "news": rows(conn, "SELECT * FROM news WHERE code=? ORDER BY published_at DESC LIMIT 6", (code,)),
            "todayNews": rows(conn, "SELECT * FROM news WHERE code=? ORDER BY published_at DESC LIMIT 3", (code,)),
            "earningsFlash": (
                {"available": False, "highlights": [], "concerns": [], "consensusGap": "Financial data not available"}
                if is_us else _earnings_flash(None, None)
            ),
            "institutionalView": (
                {"available": False, "ratings": [], "target": None, "forecast": None,
                 "note": "Institutional ratings, target prices and forecasts are not available for US names (no free stable source)."}
                if is_us else _institutional_view()
            ),
            "sensitivity": (
                {"available": False, "level": None, "beta": None, "note": "Beta data not available"}
                if is_us else _sensitivity(None)
            ),
            "sentiment": (
                {"available": False, "note": "US news source not available (no free stable source)", "source": "News headlines"}
                if is_us else _sentiment([], None)
            ),
            "dataDate": meta["dataDate"],
            "disclaimer": DISCLAIMER_EN if is_us else DISCLAIMER,
            "isDemo": meta["isDemo"],
            "dataSource": meta["dataSource"],
            **({"coverage": _us_coverage(False)} if is_us else {}),
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
    avg_vol = sum(float(b.get("volume") or 0) for b in daily[-20:]) / max(1, len(daily[-20:]))
    vol_ratio = float(stock.get("volume") or 0) / avg_vol if avg_vol else 0
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
    if is_us:
        if dd <= -15:
            risks.append({
                "title": "Weak trend",
                "detail": f"Price is {dd:.1f}% below its 180-day high and sits {'below' if ma20_daily and stock['price'] < ma20_daily else 'above'} MA20.",
                "level": "red",
            })
        if vol_ratio >= 1.5:
            risks.append({
                "title": "Volume spike",
                "detail": f"Volume is {vol_ratio:.1f}x the 20-day average; watch the direction of the move.",
                "level": "amber",
            })
        if not risks:
            risks.append({
                "title": "No rule-based risk triggered",
                "detail": "Trend and volume did not cross the preset thresholds; fundamentals and valuation are not available for US names (no free stable source).",
                "level": "green",
            })
    else:
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
    if is_us:
        if daily_closes:
            summary.append(
                f"Price is {dd:.1f}% vs its 180-day high and {'above' if ma20_daily and stock['price'] >= ma20_daily else 'below'} MA20; "
                f"20-day change {ret20:+.1f}%."
            )
        summary.append("Fundamentals, valuation and news are not available for US names (no free stable source); only EOD quotes and technical context are shown.")
        fins = []
        latest = prev = None
    else:
        if stock["asset"] != "etf" and pe_pct is not None:
            summary.append(f"当前 PE {stock['pe_ttm']:.2f}x，处于近 3 年 {pe_pct:.1f}% 分位；PB {stock['pb']:.2f}x。")
        if latest:
            summary.append(f"{latest['period']} 营收 {latest['revenue']:.0f} 亿元（同比 {latest['revenue_yoy']:+.1f}%），归母净利 {latest['net_profit']:.0f} 亿元（同比 {latest['profit_yoy']:+.1f}%）。")
            summary.append(f"毛利率 {latest['gross_margin']:.1f}%，ROE {latest['roe']:.1f}%。")
        if daily_closes:
            summary.append(f"股价较近 180 日高点回撤 {dd:.1f}%，现价{'低于' if ma20_daily and stock['price'] < ma20_daily else '高于'} MA20；近 20 日涨跌 {ret20:+.1f}%。")

    beta_value = stock.get("beta")
    prev_close = float(stock.get("prev_close") or stock["price"])
    q = {
        "code": stock["code"], "name": display_name, "industry": display_industry,
        "asset": stock["asset"], "market": stock.get("market") or ("US" if is_us else "CN"),
        "price": stock["price"], "prevClose": stock.get("prev_close"),
        "change": float(stock["price"]) - prev_close, "changePct": pct(float(stock["price"]), prev_close),
        "open": stock["open"], "high": stock["high"], "low": stock["low"],
        "marketCap": stock["market_cap"], "pe": stock["pe_ttm"], "pb": stock["pb"],
        "dividendYield": stock["dividend_yield"], "turnover": stock["turnover"],
        "volume": stock["volume"], "amount": stock["amount"], "beta": beta_value,
        "updatedAt": stock["updated_at"], "nextReportDate": stock["next_report_date"],
        "nextReportDateAvailable": bool(stock.get("next_report_date")),
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
        "trend": (
            ("Above MA20" if ma20_daily and stock["price"] >= ma20_daily else "Below MA20")
            if is_us else ("偏强" if ma20_daily and stock["price"] >= ma20_daily else "偏弱")
        ),
        "summary": summary,
    }
    valuation = {
        "pe": stock["pe_ttm"], "pb": stock["pb"], "pePercentile": pe_pct, "pbPercentile": pb_pct,
        "industryPe": peer["pe"] if peer else None, "samples": len(pe_vals),
        "label": ("No valuation data" if is_us else ("近 3 年历史分位" if pe_vals else "无估值数据")),
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
    news = [] if is_us else rows(conn, "SELECT * FROM news WHERE code=? ORDER BY published_at DESC LIMIT 6", (code,))
    meta = _market_meta(conn, "US") if is_us else data_meta(conn)
    return {
        "quote": q, "chart": chart, "technical": technical, "summary": summary,
        "valuation": valuation, "financials": fins, "report": report, "risks": risks,
        "news": news, "todayNews": news[:3],
        "earningsFlash": (
            {"available": False, "highlights": [], "concerns": [], "consensusGap": "Financial data not available"}
            if is_us else _earnings_flash(latest, prev)
        ),
        "institutionalView": (
            {"available": False, "ratings": [], "target": None, "forecast": None,
             "note": "Institutional ratings, target prices and forecasts are not available for US names (no free stable source)."}
            if is_us else _institutional_view()
        ),
        "sensitivity": (
            {"available": False, "level": None, "beta": None, "note": "Beta data not available"}
            if is_us else _sensitivity(beta_value)
        ),
        "sentiment": (
            {"available": False, "note": "US news source not available (no free stable source)", "source": "News headlines"}
            if is_us else _sentiment(news, stock.get("turnover"))
        ),
        "dataDate": meta["dataDate"] if is_us else (all_bars[-1]["date"] if all_bars else meta["dataDate"]),
        "disclaimer": DISCLAIMER_EN if is_us else DISCLAIMER,
        "isDemo": meta["isDemo"], "dataSource": meta["dataSource"],
        **({"coverage": _us_coverage(True)} if is_us else {}),
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
        "detailAvailable": _topic_detail_available(conn, str(topic_id)),
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
                                s.asset, s.amount AS stock_amount, s.pe_ttm,
                                ri.name AS industry_name, ri.level AS industry_level
                         FROM portfolio p
                         LEFT JOIN stocks s ON s.code=p.code
                         LEFT JOIN LATERAL (
                           SELECT name, level FROM ref_industry
                            WHERE industry_code=s.industry
                            ORDER BY level ASC LIMIT 1
                         ) ri ON TRUE
                         WHERE p.user_id=?""", (user_id,))


def _holding_value(h: dict[str, Any]) -> float:
    if str(h.get("code")) == "CASH":
        return float(h.get("shares") or 0)
    return float(h.get("shares") or 0) * float(h.get("price") or 0)


def portfolio_weights(holdings: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    """按当前市值折算权重（%）；总市值为 0 时返回空权重。"""
    total = sum(_holding_value(h) for h in holdings)
    if total <= 0:
        return 0.0, {}
    return total, {str(h["code"]): _holding_value(h) / total * 100 for h in holdings}


RISK_WEIGHTS = {
    "concentration": 30,
    "industry": 25,
    "penetration": 15,
    "correlation": 15,
    "valuation": 10,
    "turnover": 5,
}
LIQUIDITY_AMOUNT_FLOOR = 50_000_000  # 日均成交额 < 5000 万视为低流动性


def _industry_label(h: dict[str, Any]) -> tuple[str, str]:
    """返回（常用名，完整名）。常用名优先一级行业，完整名放 tooltip。"""
    raw = h.get("stock_industry") or h.get("industry")
    name = h.get("industry_name")
    if name:
        level = h.get("industry_level")
        full = f"申万{level}级：{name}" if level else f"行业：{name}"
        # stock_industry 可能是 801780.SI 这类行业代码；代码不作为常用名
        raw_text = str(raw) if raw else ""
        is_code = raw_text.split(".")[0].isdigit()
        common = raw_text if raw_text and not is_code else name
        return str(common), full
    name = raw or "其他"
    return str(name), str(name)


def _corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 5:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return cov / math.sqrt(va * vb)


def _mean_correlation(conn: Any, stock_values: list[tuple[dict[str, Any], float]]) -> float | None:
    """持仓两两日收益相关系数均值；样本不足返回 None。"""
    series: dict[str, dict[str, float]] = {}
    for h, _ in stock_values:
        bars = stock_bars(conn, str(h["code"]), 180)
        if len(bars) < 30:
            continue
        series[str(h["code"])] = {str(b["date"]): float(b["close"]) for b in bars if b.get("close") is not None}
    if len(series) < 2:
        return None
    common = set.intersection(*[set(v) for v in series.values()])
    dates = sorted(common)[-60:]
    if len(dates) < 20:
        return None
    returns: dict[str, list[float]] = {}
    for code, closes in series.items():
        vals = [closes[d] for d in dates]
        returns[code] = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
    codes = list(returns)
    pairs = []
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            value = _corr(returns[codes[i]], returns[codes[j]])
            if value is not None:
                pairs.append(value)
    return sum(pairs) / len(pairs) if pairs else None


def _weighted_pe_percentile(conn: Any, stock_values: list[tuple[dict[str, Any], float]]) -> tuple[float | None, float]:
    """权重加权的 PE 历史分位；返回（分位，覆盖权重）。"""
    acc = 0.0
    covered = 0.0
    since = (date.today() - timedelta(days=365 * 3)).isoformat()
    for h, _ in stock_values:
        pe = h.get("pe_ttm")
        if pe is None or float(pe) <= 0:
            continue
        try:
            hist = [
                float(r["pe_ttm"])
                for r in conn.execute(
                    # 直接走 md_valuation_daily(symbol,trade_date) 主键/索引；
                    # valuations 视图对 code 做 split_part，生产会全表扫描 1500 万行。
                    "SELECT pe_ttm FROM md_valuation_daily "
                    "WHERE symbol=? AND trade_date>=?::date AND pe_ttm > 0",
                    (_with_suffix(h["code"]), since),
                ).fetchall()
                if r.get("pe_ttm") is not None
            ]
        except Exception:
            continue
        if len(hist) < 60:
            continue
        p = percentile(hist, float(pe))
        if p is None:
            continue
        acc += p * float(h["weight"])
        covered += float(h["weight"])
    return (acc / covered if covered > 0 else None), covered


def _risk_band(score: int) -> tuple[str, str]:
    if score <= 40:
        return "分散", "green"
    if score <= 70:
        return "偏集中", "amber"
    if score <= 85:
        return "较集中", "orange"
    return "高度集中", "red"


def _diag_item(
    key: str,
    title: str,
    value: float,
    threshold: float,
    high_above: float,
    evidence: str,
    impact: str,
    *,
    digits: int = 1,
) -> dict[str, Any] | None:
    excess = value - threshold
    if excess <= 0:
        return None
    level = "high" if excess > high_above else "medium"
    return {
        "id": key,
        "title": title,
        "level": level,
        "value": round(value, digits),
        "threshold": threshold,
        "excess": round(excess, digits),
        "evidence": evidence,
        "detail": evidence,
        "impact": impact,
    }


def _stress_scenarios(industries: dict[str, float], beta: float) -> list[dict[str, Any]]:
    def group_weight(names: Iterable[str]) -> float:
        return sum(industries.get(name, 0) for name in names)

    rate_affected = {"银行": -0.02, "房地产": -0.03, "非银金融": -0.02}
    rate_hit = sum(industries.get(name, 0) * shock for name, shock in rate_affected.items())
    # 申万一级里新能源/消费分散在多个行业，按常用行业组聚合
    new_energy = group_weight(("新能源", "电力设备", "有色金属"))
    consumer = group_weight(("食品饮料", "家用电器", "商贸零售", "社会服务", "纺织服饰", "美容护理"))
    scenarios = [
        {"key": "market", "name": "沪深 300 −10%", "value": round((beta or 0.87) * -10, 1)},
        {"key": "rate", "name": "利率 +50bp", "value": round(rate_hit, 1) if rate_hit else None},
        {"key": "newenergy", "name": "新能源 −15%", "value": round(new_energy * -0.15, 1) if new_energy else None},
        {"key": "consumer", "name": "消费 −10%", "value": round(consumer * -0.10, 1) if consumer else None},
    ]
    scenarios.sort(key=lambda s: (s["value"] is None, -abs(s["value"] or 0)))
    return scenarios


def _attribution_summary(items: list[dict[str, Any]], daily_change: float, benchmark: float | None) -> str:
    positive = sorted([i for i in items if float(i["contributionPct"]) > 0], key=lambda i: -float(i["contributionPct"]))
    negative = sorted([i for i in items if float(i["contributionPct"]) < 0], key=lambda i: float(i["contributionPct"]))
    parts = []
    if positive:
        parts.append("、".join(str(i["name"]) for i in positive[:2]) + "贡献主要收益")
    if negative:
        parts.append(f"{negative[0]['name']}形成拖累")
    text = "，".join(parts) + "。" if parts else "今日各持仓贡献接近 0。"
    if benchmark is not None:
        diff = daily_change - benchmark
        verb = "跑赢" if diff > 0.005 else ("跑输" if diff < -0.005 else "持平")
        text += f"整体 {signed(daily_change, 2)}，{verb}沪深300（{signed(benchmark, 2)}）。"
    return text


def build_portfolio(conn: Any, user_id: int, *, include_penetration: bool = True) -> dict[str, Any]:
    holdings = portfolio_rows(conn, user_id)
    meta = one(conn, "SELECT * FROM portfolio_meta WHERE user_id=?", (user_id,)) or {
        "trade_cost_pct": 0.4, "annual_turnover": 35, "impact_cost_pct": 0.08,
    }
    data_meta_value = data_meta(conn)
    if not holdings:
        return {
            "totalValue": 0, "totalCost": 0, "dailyPnl": 0, "dailyChange": 0,
            "totalPnl": 0, "totalPnlPct": None,
            "riskScore": 0, "riskLabel": "未导入", "riskTone": "gray",
            "riskNote": "分数越高，代表风险越集中", "riskSummary": "尚未导入持仓。",
            "riskMethod": {"items": [], "coveragePct": 0, "note": "导入持仓后计算。"},
            "kpis": [{"label": "总资产", "value": "0 万"}, {"label": "前三大持仓", "value": "—"},
                     {"label": "最大行业暴露", "value": "—"}, {"label": "历史最大回撤", "value": "—"}],
            "holdings": [], "attribution": {"items": [], "total": 0, "needReview": False, "summary": "",
                                            "benchmark": None, "note": "贡献 = 权重 × 涨跌",
                                            "explain": {"meaning": "导入持仓后解释今日涨跌来源。",
                                                        "risk": "尚未导入，无法判断贡献集中度。",
                                                        "next": "先导入持仓，再看归因。"}},
            "diagnosis": [], "diagnosisExplain": {"meaning": "导入持仓后生成体检结论。",
                                                  "risk": "尚未导入，无法做结构风险判断。",
                                                  "next": "先导入持仓，再看诊断。"},
            "exposure": [], "exposureAll": [], "recentTrades": [],
            "deviation": [], "targetConfigured": False, "stress": [],
            "costs": {"tradeCostPct": meta["trade_cost_pct"], "annualTurnover": meta["annual_turnover"],
                      "impactCostPct": meta["impact_cost_pct"], "turnoverCostPct": 0, "extraCost": 0.5},
            "summary": "尚未导入持仓；导入后才能做集中度、行业暴露与压力测试。",
            "beta": 0, "penetration": None, "dataDate": latest_date(conn), "disclaimer": DISCLAIMER,
            **data_meta_value,
        }

    values: list[tuple[dict[str, Any], float, float]] = []
    for h in holdings:
        if str(h["code"]) == "CASH":
            value, price, change = float(h["shares"] or 0), 1.0, 0.0
        else:
            price = float(h.get("price") or 0)
            value = float(h["shares"] or 0) * price
            change = pct(price, float(h.get("prev_close") or price))
        values.append((h, value, change))
    total = sum(v for _, v, _ in values) or 1
    for h, value, _ in values:
        h["value"] = value
        h["weight"] = value / total * 100
    stock_values = [(h, v) for h, v, _ in values if str(h["code"]) != "CASH"]
    stock_values.sort(key=lambda x: x[1], reverse=True)

    total_cost = sum(
        (float(h["shares"] or 0) if str(h["code"]) == "CASH" else float(h["shares"] or 0) * float(h["cost"] or 0))
        for h, _, _ in values
    )
    daily_pnl = sum(v * change / 100 for _, v, change in values)
    prev_total = total - daily_pnl
    daily_change = daily_pnl / prev_total * 100 if prev_total > 0 else sum(
        h["weight"] * change / 100 for h, _, change in values
    )
    total_pnl = total - total_cost
    total_pnl_pct = total_pnl / total_cost * 100 if total_cost > 0 else None

    top3 = sum(h["weight"] for h, _ in stock_values[:3])
    max_single = stock_values[0][0]["weight"] if stock_values else 0.0
    industries: dict[str, float] = {}
    industry_full: dict[str, str] = {}
    for h, _ in stock_values:
        common, full = _industry_label(h)
        industries[common] = industries.get(common, 0) + h["weight"]
        industry_full.setdefault(common, full)
    industry_ranked = sorted(industries.items(), key=lambda x: x[1], reverse=True)
    top2_industry = sum(w for _, w in industry_ranked[:2])
    max_ind = industry_ranked[0][1] if industry_ranked else 0.0
    beta = sum((float(h.get("beta") or 0)) * h["weight"] / 100 for h, _ in stock_values)
    weighted_dd = 0.0
    for h, _ in stock_values:
        bars = stock_bars(conn, str(h["code"]), 180)
        if bars:
            weighted_dd += max_drawdown([float(b["close"]) for b in bars]) * h["weight"] / 100

    # 归因：权重 × 当日涨跌，合计与组合今日收益交叉校验
    attribution_items = [
        {
            "code": h["code"],
            "name": h.get("name") or ("现金" if str(h["code"]) == "CASH" else h["code"]),
            "weight": round(h["weight"], 1),
            "changePct": round(change, 2),
            "contributionPct": round(h["weight"] * change / 100, 2),
            "isCash": str(h["code"]) == "CASH",
        }
        for h, _, change in values
    ]
    attribution_items.sort(key=lambda x: x["contributionPct"], reverse=True)
    contribution_total = sum(i["contributionPct"] for i in attribution_items)
    benchmark_row = one(conn, "SELECT price, prev_close FROM indices WHERE code LIKE '000300%' LIMIT 1")
    benchmark_name = "沪深300"
    if not benchmark_row:
        benchmark_row = one(conn, "SELECT price, prev_close FROM stocks WHERE code='510300' LIMIT 1")
        benchmark_name = "沪深300（ETF 代理）"
    benchmark_change = None
    if benchmark_row and benchmark_row.get("price") is not None and benchmark_row.get("prev_close"):
        benchmark_change = pct(float(benchmark_row["price"]), float(benchmark_row["prev_close"]))

    # 穿透（可选，较慢；首页/扫描可跳过）
    penetration = None
    if include_penetration and stock_values:
        try:
            from services.invest import agent_tools as _agent_tools
            penetration = _agent_tools.portfolio_penetration(conn, user_id, top=30)
        except Exception:
            penetration = None
    lt_top3 = float(penetration["top3"]) if penetration and penetration.get("top3") is not None else top3
    lt_coverage = float(penetration.get("coveragePct") or 0) if penetration else 100.0
    # 有 ETF 但穿透覆盖为 0 时，直接持仓 top3 不能冒充穿透结果
    pen_usable = True
    if penetration is not None:
        pen_usable = float(penetration.get("etfWeight") or 0) <= 0 or lt_coverage > 0

    corr = _mean_correlation(conn, stock_values)
    pe_pct, pe_covered = _weighted_pe_percentile(conn, stock_values)
    illiquid_weight = sum(
        h["weight"] for h, _ in stock_values
        if h.get("stock_amount") is not None and float(h["stock_amount"]) < LIQUIDITY_AMOUNT_FLOOR
    )
    has_amount = any(h.get("stock_amount") is not None for h, _ in stock_values)
    turnover_cost = round(float(meta["annual_turnover"]) / 100 * float(meta["trade_cost_pct"]), 2)

    diagnosis: list[dict[str, Any]] = []
    for item in (
        _diag_item("single", "单票集中", max_single, 30, 5,
                   f"最大单一持仓 {max_single:.1f}%（阈值 30%）。",
                   "重仓单只股票的波动会直接放大组合净值。"),
        _diag_item("top3", "前三大持仓偏高", top3, 60, 8,
                   f"前三大合计 {top3:.1f}%（阈值 60%）。",
                   "重仓股波动会放大净值波动。"),
        _diag_item("industry", "行业集中度偏高", top2_industry, 40, 8,
                   f"{' + '.join(name for name, _ in industry_ranked[:2])} 合计 {top2_industry:.1f}%（阈值 40%）。" if industry_ranked else "",
                   "单一行业回撤会直接拖累组合。"),
        _diag_item("penetration", "穿透后集中度更高", lt_top3, 65, 6,
                   f"穿透后前三大 {lt_top3:.1f}%（阈值 65%，覆盖 {lt_coverage:.0f}%）。"
                   + ("仅覆盖已穿透部分。" if lt_coverage < 99.9 else ""),
                   "表面分散会低估实际暴露。") if pen_usable else None,
        _diag_item("correlation", "持仓相关性偏高", corr or 0.0, 0.65, 0.10,
                   f"持仓两两相关系数均值 {corr:.2f}（阈值 0.65）。" if corr is not None else "",
                   "相关性高时，分散配置可能同时回撤。", digits=2),
        _diag_item("liquidity", "低流动性持仓偏高", illiquid_weight if has_amount else 0.0, 15, 5,
                   f"日均成交 < 5000 万的标的权重 {illiquid_weight:.1f}%（阈值 15%）。",
                   "极端行情下可能难以及时成交。"),
        _diag_item("valuation", "估值分位偏高", pe_pct or 0.0, 85, 7,
                   f"权重加权 PE 历史分位 {pe_pct:.0f}%（阈值 85%，覆盖 {pe_covered:.0f}%）。" if pe_pct is not None else "",
                   "高估值对盈利不及预期更敏感。"),
        _diag_item("turnover", "换手成本偏高", turnover_cost, 0.5, 0.5,
                   f"年化换手 × 单边成本 = {turnover_cost:.2f}%（阈值 0.50%）。",
                   "频繁调仓会侵蚀收益。", digits=2),
    ):
        if item is not None:
            diagnosis.append(item)
    diagnosis.sort(key=lambda d: (0 if d["level"] == "high" else 1, -d["excess"]))
    hidden_count = max(0, len(diagnosis) - 5)
    diagnosis = diagnosis[:5]

    # 风险分：6 项加权；缺失项按可用权重重新归一，并给出覆盖率
    sub_scores = [
        ("concentration", "集中度", max_single / 30, top3 / 60, f"最大单票 {max_single:.1f}%，前三大 {top3:.1f}%"),
        ("industry", "行业集中", top2_industry / 40, None, f"前两大行业 {top2_industry:.1f}%"),
        ("penetration", "ETF 穿透", lt_top3 / 65 if pen_usable else None, None,
         f"穿透后前三大 {lt_top3:.1f}%" if pen_usable else "穿透覆盖不足"),
        ("correlation", "相关性", corr / 0.65 if corr is not None else None, None,
         f"两两相关系数均值 {corr:.2f}" if corr is not None else "样本不足"),
        ("valuation", "估值分位", pe_pct / 85 if pe_pct is not None else None, None,
         f"加权 PE 分位 {pe_pct:.0f}%" if pe_pct is not None else "数据待补充"),
        ("turnover", "换手成本", turnover_cost / 0.5, None, f"年化换手成本 {turnover_cost:.2f}%"),
    ]
    risk_items = []
    weighted_score = 0.0
    available_weight = 0.0
    for key, label, raw, raw2, detail in sub_scores:
        raw_value = max(raw, raw2) if raw2 is not None else raw
        available = raw_value is not None
        score_part = round(max(0.0, min(100.0, raw_value * 100)), 0) if available else None
        weight = RISK_WEIGHTS[key]
        risk_items.append({
            "key": key, "label": label, "weight": weight, "score": score_part,
            "available": available, "detail": detail,
        })
        if available:
            weighted_score += score_part * weight
            available_weight += weight
    risk_score = round(weighted_score / available_weight) if available_weight else 0
    risk_label, risk_tone = _risk_band(risk_score)
    ranked_risks = sorted(
        [i for i in risk_items if i["available"] and i["score"] >= 50],
        key=lambda i: i["weight"] * (i["score"] or 0), reverse=True,
    )
    risk_summary = (
        f"风险主要来自「{' + '.join(i['label'] for i in ranked_risks[:2])}」，不是来自市场整体。"
        if ranked_risks else "持仓结构相对分散；主要不确定性来自市场整体波动。"
    )

    # 行业暴露：最多 6 条，其余合并「其他」
    exposure_all = [{"name": k, "weight": round(v, 1), "fullName": industry_full.get(k, k)}
                    for k, v in industry_ranked]
    if any(str(h["code"]) == "CASH" for h, _, _ in values):
        cash = sum(h["weight"] for h, _, _ in values if str(h["code"]) == "CASH")
        exposure_all.append({"name": "现金", "weight": round(cash, 1), "fullName": "现金"})
        exposure_all.sort(key=lambda x: x["weight"], reverse=True)
    exposure = exposure_all[:6]
    if len(exposure_all) > 6:
        exposure.append({"name": "其他", "weight": round(sum(x["weight"] for x in exposure_all[6:]), 1),
                         "fullName": "其余行业合并"})

    target_configured = any(float(h.get("target_weight") or 0) > 0 for h, _, _ in values)
    deviation = []
    if target_configured:
        for h, _, _ in values:
            target = float(h.get("target_weight") or 0)
            diff = h["weight"] - target
            deviation.append({
                "code": h["code"],
                "name": h.get("name") or ("现金" if str(h["code"]) == "CASH" else h["code"]),
                "current": round(h["weight"], 1),
                "target": round(target, 1),
                "diff": round(diff, 1),
                "status": "超配" if diff > 0.5 else ("低配" if diff < -0.5 else "达标"),
            })
        deviation.sort(key=lambda x: abs(x["diff"]), reverse=True)

    stress = _stress_scenarios(industries, beta)

    recent_trades: list[dict[str, Any]] = []
    try:
        for r in conn.execute(
            "SELECT trade_date, code, name, weight_delta, amount FROM invest_portfolio_trade "
            "WHERE user_id=? ORDER BY trade_date DESC, id DESC LIMIT 5",
            (user_id,),
        ).fetchall():
            recent_trades.append({
                "date": str(r["trade_date"])[:10],
                "code": r["code"],
                "name": r.get("name") or r["code"],
                "weightDelta": round(float(r.get("weight_delta") or 0), 1),
                "amount": round(float(r.get("amount") or 0), 0),
            })
    except Exception:
        recent_trades = []

    cash_weight = sum(h["weight"] for h, _, _ in values if str(h["code"]) == "CASH")
    holdings_out = []
    for h, value, change in values:
        is_cash = str(h["code"]) == "CASH"
        common, full = _industry_label(h) if not is_cash else ("现金", "现金")
        price = float(h.get("price") or 0)
        cost = float(h.get("cost") or 0)
        pnl_pct = (price / cost - 1) * 100 if cost > 0 and price > 0 else None
        pnl_amount = (price - cost) * float(h["shares"] or 0) if cost > 0 and price > 0 else None
        holdings_out.append({
            "code": h["code"], "name": h.get("name") or ("现金" if is_cash else h["code"]),
            "industry": common, "industryFull": full,
            "weight": round(h["weight"], 1), "value": round(value, 0),
            "shares": h["shares"], "cost": h["cost"], "price": round(price, 3),
            "todayPct": None if is_cash else round(change, 2),
            "todayPnl": 0 if is_cash else round(value * change / 100, 0),
            "pnlPct": None if is_cash else (round(pnl_pct, 1) if pnl_pct is not None else None),
            "pnlAmount": 0 if is_cash else (round(pnl_amount, 0) if pnl_amount is not None else None),
            "targetWeight": round(float(h.get("target_weight") or 0), 1),
            "isCash": is_cash,
        })
    holdings_out.sort(key=lambda h: h["weight"], reverse=True)

    kpis = [
        {"label": "总资产", "value": f"{total/10000:.1f} 万"},
        {"label": "前三大持仓", "value": f"{top3:.0f}%"},
        {"label": "最大行业暴露", "value": f"{max_ind:.0f}%"},
        {"label": "历史最大回撤", "value": f"{weighted_dd:.1f}%"},
    ]

    diagnosis_explain = {
        "meaning": (
            f"当前有 {len(diagnosis)} 项体检指标越过阈值，最靠前的是「{diagnosis[0]['title']}」。"
            if diagnosis else "当前没有指标越过预设阈值，持仓结构未触发体检提示。"
        ),
        "risk": (
            "越线项越靠前，组合越容易受单一标的、行业或成本影响；这是结构风险，不预测涨跌。"
            if diagnosis else "未触发阈值不等于没有风险；市场整体波动、流动性等仍可能影响组合。"
        ),
        "next": (
            "先看前几项的依据与影响，再结合「压力测试与成本」和「AI 深度解读」；不构成调仓建议。"
            if diagnosis else "可继续看压力测试与配置偏离；若后续权重变化，体检结果会重新计算。"
        ),
        "meaning_en": (
            f"{len(diagnosis)} checks are above their thresholds; the top one is \"{diagnosis[0]['title']}\"."
            if diagnosis else "No check is above its preset threshold; the portfolio structure has not triggered a flag."
        ),
        "risk_en": (
            "Flags closer to the top have more influence on the portfolio through a single name, sector or cost base; "
            "this is structural risk, not a price forecast."
            if diagnosis else "No flag does not mean no risk; market volatility and liquidity can still affect the portfolio."
        ),
        "next_en": (
            "Review the top flags and their evidence, then use stress/cost and AI deep-dive; this is not a rebalancing recommendation."
            if diagnosis else "Continue with stress testing and allocation drift; diagnosis is recalculated when weights change."
        ),
    }
    attribution_explain = {
        "meaning": (
            "今日涨跌 = 各持仓「权重 × 当日涨跌」的合计；贡献越大的标的，对今天净值影响越大。"
        ),
        "risk": (
            "贡献集中在少数标的时，单日净值更依赖它们的事件与波动；归因待核时说明数据口径存在差异。"
        ),
        "next": (
            "把贡献前几名与自己的持仓预期对照，再看它们是否有公告/财报；归因只解释今天，不预测明天。"
        ),
        "meaning_en": (
            "Today's return = sum of each holding's weight × daily move; larger contributors have more impact on NAV today."
        ),
        "risk_en": (
            "When contribution is concentrated in a few names, daily NAV depends more on their events and volatility; "
            "a review flag means data conventions differ."
        ),
        "next_en": (
            "Compare top contributors with your thesis and check for filings/earnings; attribution explains today only."
        ),
    }

    return {
        "totalValue": round(total, 0), "totalCost": round(total_cost, 0),
        "dailyPnl": round(daily_pnl, 0), "dailyChange": round(daily_change, 2),
        "totalPnl": round(total_pnl, 0),
        "totalPnlPct": round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
        "riskScore": risk_score, "riskLabel": risk_label, "riskTone": risk_tone,
        "riskNote": "分数只反映持仓结构，不预测盈亏；分数越高，代表风险越集中。",
        "riskSummary": risk_summary,
        "riskMethod": {"items": risk_items, "coveragePct": round(available_weight, 0),
                       "note": "按 6 项加权；数据缺失项不参与计算，覆盖率 = 可用权重之和。"},
        "kpis": kpis,
        "holdings": holdings_out,
        "attribution": {
            "items": attribution_items, "total": round(contribution_total, 2),
            "needReview": abs(contribution_total - daily_change) > 0.1,
            "benchmark": {"name": benchmark_name,
                          "changePct": round(benchmark_change, 2) if benchmark_change is not None else None},
            "summary": _attribution_summary(attribution_items, daily_change, benchmark_change),
            "note": "贡献 = 权重 × 涨跌；合计与组合今日收益误差 > 0.1pct 时标注「归因待核」。",
            "explain": attribution_explain,
        },
        "diagnosis": diagnosis, "diagnosisHidden": hidden_count,
        "diagnosisExplain": diagnosis_explain,
        "exposure": exposure, "exposureAll": exposure_all,
        "recentTrades": recent_trades,
        "deviation": deviation, "targetConfigured": target_configured,
        "stress": stress,
        "costs": {
            "tradeCostPct": meta["trade_cost_pct"], "annualTurnover": meta["annual_turnover"],
            "impactCostPct": meta["impact_cost_pct"], "turnoverCostPct": turnover_cost, "extraCost": 0.5,
        },
        "summary": risk_summary, "beta": round(beta, 2),
        "penetration": penetration,
        "cashWeight": round(cash_weight, 1),
        "dataDate": latest_date(conn), "disclaimer": DISCLAIMER,
        **data_meta_value,
    }


def record_portfolio_trades(conn: Any, user_id: int, before: list[dict[str, Any]],
                            after: list[dict[str, Any]]) -> None:
    """导入持仓后记录权重变化。首次导入（无旧市值）不记录。"""
    old_total, old_weights = portfolio_weights(before)
    new_total, new_weights = portfolio_weights(after)
    if old_total <= 0 or new_total <= 0:
        return
    names = {
        str(h["code"]): (h.get("name") or ("现金" if str(h["code"]) == "CASH" else h["code"]))
        for h in after
    }
    today = date.today().isoformat()
    for code in set(old_weights) | set(new_weights):
        before_w = old_weights.get(code, 0.0)
        after_w = new_weights.get(code, 0.0)
        delta = after_w - before_w
        if abs(delta) < 0.1:
            continue
        conn.execute(
            "INSERT INTO invest_portfolio_trade "
            "(user_id, trade_date, code, name, weight_before, weight_after, weight_delta, amount) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, today, code, names.get(code, code), round(before_w, 2), round(after_w, 2),
             round(delta, 2), round(delta / 100 * new_total, 0)),
        )


def _index_bars(conn: Any, limit: int) -> list[dict[str, Any]]:
    try:
        rows_ = rows(
            conn,
            """SELECT * FROM (
                 SELECT trade_date::text AS date, close
                   FROM md_index_bar
                  WHERE split_part(index_code, '.', 1)='000300' AND close IS NOT NULL
                  ORDER BY trade_date DESC LIMIT ?
               ) t ORDER BY date ASC""",
            (limit,),
        )
        if rows_:
            return rows_
    except Exception:
        pass
    return [{"date": b["date"], "close": b["close"]} for b in stock_bars(conn, "510300", limit)]


def portfolio_nav(conn: Any, user_id: int, period: str = "1m") -> dict[str, Any]:
    """按当前持仓回溯净值曲线（买入并持有假设），与沪深 300 对比。"""
    days = {"1m": 22, "3m": 66, "1y": 250}.get(period, 22)
    holdings = portfolio_rows(conn, user_id)
    total, weights = portfolio_weights(holdings)
    if total <= 0:
        return {"period": period, "dates": [], "portfolio": [], "benchmark": [],
                "benchmarkName": "沪深300", "coveragePct": 0,
                "note": "尚未导入持仓。"}
    cash_weight = weights.get("CASH", 0.0)
    benchmark_bars = _index_bars(conn, days + 5)
    master_dates = [str(b["date"]) for b in benchmark_bars][-days:]
    series: dict[str, dict[str, float]] = {}
    included_weight = 0.0
    for h in holdings:
        code = str(h["code"])
        if code == "CASH":
            continue
        bars = stock_bars(conn, code, days + 20)
        if len(bars) < max(2, days // 2):
            continue
        mapping = {str(b["date"]): float(b["close"]) for b in bars if b.get("close") is not None}
        series[code] = mapping
        included_weight += weights.get(code, 0.0)
    if not series:
        return {"period": period, "dates": [], "portfolio": [], "benchmark": [],
                "benchmarkName": "沪深300", "coveragePct": 0,
                "note": "持仓历史行情不足，暂不能回溯。"}
    if not master_dates:
        master_dates = sorted(set.union(*[set(m) for m in series.values()]))[-days:]
    scale = (100 - cash_weight) / included_weight if included_weight > 0 else 0
    bases: dict[str, float | None] = {}
    for code, mapping in series.items():
        base = next((mapping[d] for d in master_dates if d in mapping), None)
        bases[code] = base
    portfolio_points: list[float | None] = []
    benchmark_points: list[float | None] = []
    benchmark_map = {str(b["date"]): float(b["close"]) for b in benchmark_bars if b.get("close") is not None}
    bench_base = None
    for d in master_dates:
        if bench_base is None and d in benchmark_map:
            bench_base = benchmark_map[d]
        benchmark_points.append(
            round((benchmark_map[d] / bench_base - 1) * 100, 2)
            if bench_base and d in benchmark_map else None
        )
        value = cash_weight
        valid = True
        for h in holdings:
            code = str(h["code"])
            if code == "CASH":
                continue
            mapping = series.get(code)
            if not mapping:
                continue
            weight = weights.get(code, 0.0)
            if weight <= 0:
                continue
            # 用最近一个不晚于目标日期的收盘价，避免停牌造成空洞
            price = None
            for back in range(0, 8):
                probe = (date.fromisoformat(d) - timedelta(days=back)).isoformat()
                if probe in mapping:
                    price = mapping[probe]
                    break
            base = bases.get(code)
            if price is None or not base:
                valid = False
                break
            value += weight * scale * (price / base)
        portfolio_points.append(round(value - 100, 2) if valid else None)
    pairs = [(d, p, b) for d, p, b in zip(master_dates, portfolio_points, benchmark_points) if p is not None]
    return {
        "period": period,
        "dates": [p[0] for p in pairs],
        "portfolio": [p[1] for p in pairs],
        "benchmark": [p[2] for p in pairs],
        "benchmarkName": "沪深300",
        "coveragePct": round(included_weight, 1),
        "note": "按当前持仓回溯（买入并持有假设），不代表真实历史成交；未覆盖持仓不计入。",
    }


def build_home_us(conn: Any, user_id: int) -> dict[str, Any]:
    """英文版首页：美股 EOD 广度 + 自选异动 + 领涨领跌；无指数/主题数据。"""
    meta = _market_meta(conn, "US")
    data_date = meta["dataDate"]
    stocks = rows(conn, "SELECT * FROM stocks WHERE market='US' AND asset='stock' AND price IS NOT NULL")
    if not stocks:
        return {
            **meta, "user": {"id": user_id, "name": "Demo user"}, "hasQuotes": False,
            "coverage": _us_coverage(False), "daily": [],
            "review": {
                "title": "US quotes unavailable",
                "summary": (
                    "This data view does not contain US quote rows. US financials, valuation, "
                    "news and indices are also not available. Switch to 中文 for A-share coverage."
                ),
                "facts": [
                    "No US tickers with a latest price were found in the current service-layer snapshot.",
                    "The page does not fill missing quotes with 0.",
                    "Ask the data platform to publish US quotes before relying on English mode.",
                ],
            },
            "indices": [], "topics": [], "watchlist": [], "glossary": US_GLOSSARY,
            "portfolioSnapshot": {"hasHoldings": False, "holdingCount": 0, "dailyChange": None,
                                   "totalValue": 0, "riskScore": 0, "lastCheckupDate": None},
            "marketPulse": {"asOf": data_date, "status": "close", "statusLabel": "收盘",
                             "statusLabelEn": "Close", "indices": [],
                             "turnover": {"value": None, "change": None, "available": False,
                                          "note": "US quotes are not connected."}},
            "learn": {"title": "Valuation percentile: expensive versus what?",
                       "titleEn": "Valuation percentile: expensive versus what?", "link": "/learn"},
            "disclaimer": DISCLAIMER_EN, "market": "US",
        }
    by_code = {s["code"]: s for s in stocks}
    watch = rows(conn, "SELECT * FROM watchlist WHERE user_id=?", (user_id,))
    watch_cards = []
    for w in watch:
        s = by_code.get(w["code"])
        if s:
            watch_cards.append({
                "code": s["code"], "name": _display_name(s, "US"), "price": s["price"],
                "changePct": pct(float(s["price"]), float(s.get("prev_close") or s["price"])),
                "group": w["group_name"],
            })
    pool = [s for s in stocks if s.get("prev_close")]
    changes = [pct(float(s["price"]), float(s["prev_close"])) for s in pool]
    advancers = sum(1 for x in changes if x > 0)
    decliners = sum(1 for x in changes if x < 0)
    average = sum(changes) / len(changes) if changes else 0.0
    liquid = sorted(stocks, key=lambda s: float(s.get("amount") or 0), reverse=True)[:500]
    gainers = sorted(liquid, key=lambda s: pct(float(s["price"]), float(s.get("prev_close") or s["price"])), reverse=True)[:5]
    losers = sorted(liquid, key=lambda s: pct(float(s["price"]), float(s.get("prev_close") or s["price"])))[:5]

    daily: list[dict[str, Any]] = []
    if watch_cards:
        s = max(watch_cards, key=lambda x: abs(float(x["changePct"])))
        daily.append({
            "source": "stock",
            "tag": "Watchlist · move",
            "title": f"{s['name']} {float(s['changePct']):+.2f}%",
            "detail": f"Last close {float(s['price']):.2f}; open the ticker for chart and risk context.",
            "link": {"type": "stock", "id": s["code"]},
        })
    if gainers:
        s = gainers[0]
        daily.append({
            "source": "stock",
            "tag": "US · top gainer",
            "title": f"{_display_name(s, 'US')} {pct(float(s['price']), float(s['prev_close'])):+.2f}%",
            "detail": f"Among the most active US names; last close {float(s['price']):.2f}.",
            "link": {"type": "stock", "id": s["code"]},
        })
    daily.append({
        "source": "market",
        "tag": "US · breadth",
        "title": f"{advancers} up / {decliners} down",
        "detail": f"Average move {average:+.2f}% across {len(changes)} US tickers with EOD data.",
        "link": None,
    })
    if losers and len(daily) < 3:
        s = losers[0]
        daily.append({
            "source": "stock",
            "tag": "US · top loser",
            "title": f"{_display_name(s, 'US')} {pct(float(s['price']), float(s['prev_close'])):+.2f}%",
            "detail": f"Among the most active US names; last close {float(s['price']):.2f}.",
            "link": {"type": "stock", "id": s["code"]},
        })
    daily = daily[:3]

    portfolio = _home_portfolio(conn, user_id)
    review = {
        "title": "US close",
        "line": _clip_home(
            f"{advancers} up / {decliners} down, average {average:+.2f}%." if changes else "No US breadth snapshot yet.",
            30,
        ),
        "summary": (
            f"US EOD snapshot {data_date}: {advancers} advancers vs {decliners} decliners, "
            f"average move {average:+.2f}%. This build covers quotes and charts only; "
            "fundamentals, valuation, news and US indices are not available (no free stable source)."
        ),
        "facts": [
            f"{len(stocks)} US tickers have a latest price; {sum(1 for s in stocks if s.get('amount'))} have dollar volume.",
            "Most active names are ranked by latest dollar volume to avoid illiquid microcaps.",
            "Data is an end-of-day snapshot, not real-time.",
        ],
    }
    return {
        **meta, "user": {"id": user_id, "name": "Demo user"}, "hasQuotes": True,
        "coverage": _us_coverage(True), "daily": daily, "review": review,
        "portfolioSnapshot": portfolio,
        "marketPulse": {
            "asOf": data_date, "status": "close", "statusLabel": "收盘", "statusLabelEn": "Close",
            "indices": [], "turnover": {"value": None, "change": None, "available": False,
                                        "note": "US index and consolidated turnover are not connected."},
        },
        "indices": [], "topics": [], "watchlist": watch_cards,
        "learn": {"title": "Valuation percentile: expensive versus what?",
                   "titleEn": "Valuation percentile: expensive versus what?", "link": "/learn"},
        "glossary": US_GLOSSARY,
        "disclaimer": DISCLAIMER_EN, "market": "US",
    }



HOME_INDICES = (
    ("000001.SH", "上证指数", "SSE Composite"),
    ("399001.SZ", "深证成指", "SZSE Component"),
    ("399006.SZ", "创业板指", "ChiNext"),
)


def _home_index_quote(conn: Any, code: str, data_date: str) -> tuple[float | None, float | None]:
    bars = rows(
        conn,
        "SELECT trade_date, close FROM md_index_bar WHERE index_code=? AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 2",
        (code, data_date),
    )
    if bars and bars[0].get("close") is not None:
        latest = float(bars[0]["close"])
        prev = float(bars[1]["close"]) if len(bars) > 1 and bars[1].get("close") is not None else None
        return latest, pct(latest, prev) if prev else None
    # 兼容旧 indices 表；没有对应代码时明确 unavailable，不用别的指数冒充。
    row = one(conn, "SELECT price, prev_close FROM indices WHERE code=? LIMIT 1", (code,))
    if row and row.get("price") is not None:
        latest = float(row["price"])
        prev = float(row["prev_close"]) if row.get("prev_close") is not None else None
        return latest, pct(latest, prev) if prev else None
    return None, None


def _home_market(conn: Any, data_date: str) -> dict[str, Any]:
    indices = []
    for code, label, label_en in HOME_INDICES:
        value, change = _home_index_quote(conn, code, data_date)
        indices.append({
            "code": code, "label": label, "label_en": label_en,
            "value": round(value, 2) if value is not None else None,
            "change": round(change, 2) if change is not None else None,
            "available": value is not None,
        })
    now = datetime.now()
    amount: float | None = None
    prev_amount: float | None = None
    turnover_note = ""
    basis = "stocks"
    if data_date == now.date().isoformat() and now.hour < 10:
        turnover_note = "10:00 前成交额未成形"
    else:
        # 数据平台已补 000001.SH / 399001.SZ 的指数 amount；优先用指数口径。
        index_row = one(
            conn,
            "SELECT SUM(amount) AS amt, COUNT(amount) AS n FROM md_index_bar "
            "WHERE trade_date=? AND index_code IN ('000001.SH','399001.SZ') AND amount IS NOT NULL",
            (data_date,),
        )
        if index_row and index_row.get("amt") is not None and int(index_row.get("n") or 0) >= 2:
            amount = float(index_row["amt"]) / 1e8
            basis = "index"
            prev_date = one(
                conn,
                "SELECT MAX(trade_date) AS d FROM md_index_bar "
                "WHERE trade_date < ? AND index_code IN ('000001.SH','399001.SZ') AND amount IS NOT NULL",
                (data_date,),
            )
            if prev_date and prev_date.get("d"):
                prev = one(
                    conn,
                    "SELECT SUM(amount) AS amt, COUNT(amount) AS n FROM md_index_bar "
                    "WHERE trade_date=? AND index_code IN ('000001.SH','399001.SZ') AND amount IS NOT NULL",
                    (prev_date["d"],),
                )
                if prev and prev.get("amt") is not None and int(prev.get("n") or 0) >= 2:
                    prev_amount = float(prev["amt"]) / 1e8
        else:
            row = one(
                conn,
                "SELECT SUM(amount) AS amt FROM md_daily_bar WHERE trade_date=? AND adjust='none' "
                "AND split_part(symbol,'.',2) IN ('SH','SZ') AND amount IS NOT NULL",
                (data_date,),
            )
            if row and row.get("amt") is not None:
                amount = float(row["amt"]) / 1e8
            prev_date = one(
                conn,
                "SELECT MAX(trade_date) AS d FROM md_daily_bar WHERE trade_date < ?",
                (data_date,),
            )
            if prev_date and prev_date.get("d"):
                prev = one(
                    conn,
                    "SELECT SUM(amount) AS amt FROM md_daily_bar WHERE trade_date=? AND adjust='none' "
                    "AND split_part(symbol,'.',2) IN ('SH','SZ') AND amount IS NOT NULL",
                    (prev_date["d"],),
                )
                if prev and prev.get("amt") is not None:
                    prev_amount = float(prev["amt"]) / 1e8
    turnover_change = pct(amount, prev_amount) if amount is not None and prev_amount else None
    is_rest = date.today().weekday() >= 5
    return {
        "asOf": data_date,
        "status": "rest" if is_rest else "close",
        "statusLabel": "休市" if is_rest else "收盘",
        "statusLabelEn": "Closed" if is_rest else "Close",
        "indices": indices,
        "turnover": {
            "value": round(amount, 1) if amount is not None else None,
            "change": round(turnover_change, 2) if turnover_change is not None else None,
            "available": amount is not None,
            "basis": basis if amount is not None else None,
            "basisLabel": (
                "沪深两市成交额（指数口径）" if amount is not None and basis == "index"
                else "行情汇总口径，非交易所官方" if amount is not None else ""
            ),
            "basisLabelEn": (
                "SSE + SZSE turnover (index basis)" if amount is not None and basis == "index"
                else "Stock-sum basis, not exchange official" if amount is not None else ""
            ),
            "note": turnover_note,
        },
    }


def _home_portfolio(conn: Any, user_id: int, pf: dict[str, Any] | None = None) -> dict[str, Any]:
    if pf is None:
        try:
            held = portfolio_rows(conn, user_id)
        except Exception:
            held = []
        if not held:
            return {
                "hasHoldings": False, "holdingCount": 0, "dailyChange": None,
                "totalValue": 0, "riskScore": 0, "lastCheckupDate": None,
            }
        pf = build_portfolio(conn, user_id, include_penetration=False)
    meta = one(conn, "SELECT updated_at FROM portfolio_meta WHERE user_id=?", (user_id,))
    last_checkup = str(meta.get("updated_at") or "")[:10] if meta else None
    if not last_checkup:
        trade = one(conn, "SELECT MAX(created_at) AS d FROM invest_portfolio_trade WHERE user_id=?", (user_id,))
        if trade and trade.get("d"):
            last_checkup = str(trade["d"])[:10]
    holdings = pf.get("holdings") or []
    return {
        "hasHoldings": bool(holdings),
        "holdingCount": len(holdings),
        "dailyChange": round(float(pf.get("dailyChange") or 0), 2) if holdings else None,
        "totalValue": round(float(pf.get("totalValue") or 0), 0),
        "riskScore": pf.get("riskScore"),
        "lastCheckupDate": last_checkup,
    }


def _clip_home(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _topic_risk_tags(topic: dict[str, Any]) -> list[dict[str, str]]:
    """用现有估值/成交分位给出可解释的风险标签；没有阈值触发时展示真实分位，不用“数据待验证”兜底。"""
    tags: list[dict[str, str]] = []
    valuation = topic.get("valuation_percentile")
    turnover = topic.get("turnover_percentile")
    if valuation is not None:
        value = float(valuation)
        if value >= 85:
            tags.append({"label": "估值偏高", "label_en": "Valuation elevated", "tone": "red"})
        elif value >= 70:
            tags.append({"label": "估值不低", "label_en": "Valuation not cheap", "tone": "amber"})
        else:
            tags.append({"label": f"估值分位 {value:.0f}%", "label_en": f"Valuation percentile {value:.0f}%", "tone": "gray"})
    elif turnover is not None:
        tags.append({"label": f"成交分位 {float(turnover):.0f}%", "label_en": f"Turnover percentile {float(turnover):.0f}%", "tone": "gray"})
    if turnover is not None and float(turnover) >= 80:
        tags.append({"label": "拥挤度高", "label_en": "Crowded", "tone": "amber"})
    if not tags:
        heat = float(topic.get("heat") or 0)
        tags.append({"label": f"热度 {heat:.0f}", "label_en": f"Heat {heat:.0f}", "tone": "gray"})
    return tags


def _home_daily(conn: Any, user_id: int, data_date: str, pf: dict[str, Any],
                market: dict[str, Any], by_code: dict[str, dict[str, Any]],
                watch_codes: set[str]) -> list[dict[str, Any]]:
    daily: list[dict[str, Any]] = []
    today = date.fromisoformat(data_date)
    holding_codes = {str(h["code"]) for h in (pf.get("holdings") or []) if str(h["code"]) != "CASH"}
    pool_codes = watch_codes | holding_codes
    pool = [s for s in by_code.values() if str(s.get("code")) in pool_codes and s.get("price") is not None]
    upcoming = [
        s for s in pool
        if s.get("next_report_date")
        and data_date <= str(s["next_report_date"])
        and (date.fromisoformat(str(s["next_report_date"])) - today).days <= 7
    ]
    stock_event = None
    if upcoming:
        s = min(upcoming, key=lambda x: str(x["next_report_date"]))
        days = (date.fromisoformat(str(s["next_report_date"])) - today).days
        stock_event = {
            "source": "stock",
            "tag": "自选 · 事件",
            "title": f"{s['name']} {str(s['next_report_date'])[5:]} 预约披露",
            "detail": _clip_home(f"距预约披露 {days} 天，关注财报与现金流。", 40),
            "link": {"type": "stock", "id": s["code"]},
        }
    elif pool:
        s = max(pool, key=lambda x: abs(pct(x["price"], x.get("prev_close") or x["price"])))
        change = pct(s["price"], s.get("prev_close") or s["price"])
        stock_event = {
            "source": "stock",
            "tag": "自选 / 持仓 · 异动",
            "title": f"{s['name']} {change:+.2f}%",
            "detail": _clip_home(f"今日{'上涨' if change >= 0 else '下跌'}{abs(change):.2f}%，先看估值与风险。", 40),
            "link": {"type": "stock", "id": s["code"]},
        }
    if stock_event:
        daily.append(stock_event)

    diagnosis = pf.get("diagnosis") or []
    if diagnosis:
        d = diagnosis[0]
        evidence = str(d.get("evidence") or "").rstrip("。；;，, ")
        daily.append({
            "source": "portfolio",
            "tag": "组合 · 体检",
            "title": str(d.get("title") or "组合体检提示"),
            "detail": _clip_home(f"{evidence}，超出阈值 {d.get('excess')}。", 40),
            "link": {"type": "portfolio"},
        })
    elif pf.get("deviation"):
        d = max(pf["deviation"], key=lambda x: abs(float(x.get("diff") or 0)))
        daily.append({
            "source": "portfolio",
            "tag": "组合 · 偏离",
            "title": f"{d['name']} {float(d['diff']):+.1f}%",
            "detail": _clip_home(f"当前 {d['current']}%，目标 {d['target']}%；只展示偏离。", 40),
            "link": {"type": "portfolio"},
        })

    turnover = market.get("turnover") or {}
    if turnover.get("available"):
        change = turnover.get("change")
        detail = f"较上一交易日 {change:+.1f}%" if change is not None else "成交额已更新"
        daily.append({
            "source": "market",
            "tag": "市场 · 成交",
            "title": f"两市成交额 {float(turnover['value']) / 10000:.2f} 万亿",
            "detail": _clip_home(detail, 40),
            "link": None,
        })
    else:
        changes = [pct(s["price"], s.get("prev_close") or s["price"]) for s in by_code.values() if s.get("price") is not None]
        up = sum(1 for x in changes if x > 0)
        down = sum(1 for x in changes if x < 0)
        daily.append({
            "source": "market",
            "tag": "市场 · 广度",
            "title": f"涨跌家数 {up} / {down}",
            "detail": "上涨与下跌家数接近，市场分化。" if up and down and abs(up - down) / max(up + down, 1) < 0.2 else "涨跌家数差距扩大，注意结构分化。",
            "link": None,
        })
    return daily[:3]


def _home_review_line(conn: Any, pf: dict[str, Any], market: dict[str, Any]) -> str:
    index_change = None
    row = one(conn, "SELECT price, prev_close FROM indices WHERE code LIKE '000300%' LIMIT 1")
    if row and row.get("price") is not None and row.get("prev_close"):
        index_change = pct(float(row["price"]), float(row["prev_close"]))
    turnover = market.get("turnover") or {}
    if index_change is not None and pf.get("holdings"):
        return _clip_home(f"沪深300 {index_change:+.2f}%，组合 {float(pf.get('dailyChange') or 0):+.2f}%。", 30)
    if index_change is not None:
        if turnover.get("available"):
            return _clip_home(f"沪深300 {index_change:+.2f}%，成交额 {float(turnover.get('value') or 0) / 10000:.2f} 万亿。", 30)
        return _clip_home(f"沪深300 {index_change:+.2f}%。", 30)
    if turnover.get("available"):
        return _clip_home(f"两市成交额 {float(turnover['value']) / 10000:.2f} 万亿，较昨日 {float(turnover.get('change') or 0):+.1f}%。", 30)
    return "今日还没有可用的市场快照。"

def build_home(conn: Any, user_id: int, market: str = "CN") -> dict[str, Any]:
    if normalize_market(market) == "US":
        return build_home_us(conn, user_id)
    stocks = rows(conn, "SELECT * FROM stocks WHERE COALESCE(market,'CN')='CN'")
    by_code = {s["code"]: s for s in stocks}
    meta = data_meta(conn)
    data_date = meta["dataDate"]
    meta_info = build_meta(conn)
    watch = rows(conn, "SELECT * FROM watchlist WHERE user_id=?", (user_id,))
    watch_codes = {str(w["code"]) for w in watch}
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
        topic_cards.append({
            "id": t["id"], "name": t["name"], "summary": t["summary"], "heat": t["heat"],
            "valuationPercentile": t["valuation_percentile"],
            "turnoverPercentile": t.get("turnover_percentile"),
            "riskTags": _topic_risk_tags(t),
            "spark": [b["close"] for b in reversed(bars)],
            "detailAvailable": _topic_detail_available(conn, str(t["id"])),
        })

    pf = build_portfolio(conn, user_id, include_penetration=False)
    portfolio = _home_portfolio(conn, user_id, pf)
    market_pulse = _home_market(conn, data_date)
    daily = _home_daily(conn, user_id, data_date, pf, market_pulse, by_code, watch_codes)
    etf = by_code.get("510300")
    review = {
        "title": "收盘复盘",
        "line": _home_review_line(conn, pf, market_pulse),
        "summary": (
            f"沪深 300 ETF 收盘 {etf['price']:.3f}（{pct(etf['price'], etf['prev_close']):+.2f}%）；"
            f"你的组合今日 {signed(pf['dailyChange'])}，风险主要来自行业集中。"
            if pf["holdings"] else
            f"沪深 300 ETF 收盘 {etf['price']:.3f}（{pct(etf['price'], etf['prev_close']):+.2f}%）；"
            "尚未导入组合，先做一次体检。"
        ) if etf else "",
        "facts": [
            f"组合总资产 {pf['totalValue']/10000:.1f} 万元，风险分 {pf['riskScore']}。" if pf["holdings"] else "尚未导入组合，去「组合」页导入 CSV 或手工持仓。",
            f"前三大持仓 {pf['kpis'][1]['value']}，最大行业 {pf['kpis'][2]['value']}。" if pf["holdings"] else "导入后才能计算集中度、行业暴露与配置偏离。",
            "数据为收盘后快照，不是实时行情。",
        ],
    }
    indices = [
        {"name": i["label"], "labelEn": i["label_en"], "value": i["value"],
         "change": i["change"], "available": i["available"]}
        for i in market_pulse["indices"]
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
    return {
        "dataDate": data_date, "dataSource": meta["dataSource"], "isDemo": meta["isDemo"],
        "ageDays": meta_info["ageDays"], "isStale": meta_info["isStale"],
        "user": {"id": user_id, "name": "演示用户"},
        "portfolioSnapshot": portfolio, "marketPulse": market_pulse,
        "daily": daily, "review": review,
        "indices": indices, "topics": topic_cards, "watchlist": watch_cards,
        "learn": {"title": "估值分位：贵不贵，跟什么比？", "titleEn": "Valuation percentile: expensive versus what?", "link": "/learn"},
        "glossary": glossary, "disclaimer": DISCLAIMER, "market": "CN", "hasQuotes": True,
    }

def _topic_detail_available(conn: Any, topic_id: str) -> bool:
    row = one(
        conn,
        "SELECT EXISTS(SELECT 1 FROM topic_bars WHERE topic_id=?) AS bars, "
        "EXISTS(SELECT 1 FROM topic_stocks WHERE topic_id=?) AS stocks",
        (topic_id, topic_id),
    )
    return bool(row and (row.get("bars") or row.get("stocks")))


def build_topics(conn: Any) -> dict[str, Any]:
    topics = rows(conn, "SELECT * FROM topics ORDER BY heat DESC")
    items = []
    for t in topics:
        bars = rows(conn, "SELECT close FROM topic_bars WHERE topic_id=? ORDER BY date DESC LIMIT 30", (t["id"],))
        items.append({
            "id": t["id"], "name": t["name"], "summary": t["summary"], "heat": t["heat"],
            "valuationPercentile": t["valuation_percentile"],
            "turnoverPercentile": t.get("turnover_percentile"),
            "riskTags": _topic_risk_tags(t),
            "spark": [b["close"] for b in reversed(bars)],
            "detailAvailable": _topic_detail_available(conn, str(t["id"])),
        })
    return {"items": items, "dataDate": latest_date(conn), "disclaimer": DISCLAIMER}


def build_watchlist(conn: Any, user_id: int, market: str = "CN") -> dict[str, Any]:
    market = normalize_market(market)
    watch = rows(conn, "SELECT * FROM watchlist WHERE user_id=? ORDER BY created_at ASC", (user_id,))
    groups: dict[str, list[dict[str, Any]]] = {}
    for w in watch:
        s = one(conn, f"SELECT * FROM stocks WHERE code=? AND {_market_sql(market)}", (w["code"],))
        if not s:
            continue
        groups.setdefault(w["group_name"] or ("Default" if market == "US" else "默认"), []).append({
            "code": s["code"], "name": _display_name(s, market),
            "industry": _display_industry(s, market), "price": s["price"],
            "changePct": pct(float(s["price"] or 0), float(s.get("prev_close") or s["price"] or 0)),
        })
    events = rows(conn, "SELECT * FROM events WHERE user_id=? ORDER BY id DESC", (user_id,))
    for e in events:
        t = one(conn, "SELECT name FROM topics WHERE id=?", (e["code"],))
        s = one(conn, "SELECT name FROM stocks WHERE code=?", (e["code"],))
        e["name"] = (t or s or {}).get("name") or e["code"]
    logs = rows(conn, "SELECT * FROM event_logs WHERE user_id=? ORDER BY triggered_at DESC", (user_id,))
    available = True
    if market == "US":
        try:
            available = bool(conn.execute("SELECT 1 FROM stocks WHERE market='US' LIMIT 1").fetchone())
        except Exception:
            available = False
    return {
        "groups": [{"name": k, "items": v} for k, v in groups.items()], "events": events, "logs": logs,
        "market": market, "available": available,
        "disclaimer": (
            "Watch events refresh after the close; no real-time push."
            if market == "US" else "关注事件在收盘后更新；不提供实时推送。"
        ),
    }


def build_search(conn: Any, q: str, market: str = "CN") -> dict[str, Any]:
    market = normalize_market(market)
    q = (q or "").strip()
    if market == "US":
        pool = [
            s for s in rows(conn, "SELECT * FROM stocks WHERE market='US'")
            if s.get("asset") == "stock" and s.get("price") is not None
        ]
        if q:
            lowered = q.lower()
            alias_codes = {
                code for code, name in US_EN_NAMES.items() if lowered in name.lower()
            }
            stocks = [
                s for s in pool
                if lowered in str(s.get("code") or "").lower()
                or lowered in str(s.get("name") or "").lower()
                or s["code"] in alias_codes
            ][:8]
        else:
            stocks = []
        by_code = {s["code"]: s for s in pool}

        def us_card(s: dict[str, Any], reason: str) -> dict[str, Any]:
            return {
                "type": "stock", "id": s["code"], "name": _display_name(s, "US"),
                "sub": f"{s['code']} · US equity", "market": "US", "price": s["price"],
                "changePct": pct(float(s["price"]), float(s.get("prev_close") or s["price"])),
                "reason": reason,
            }

        results = [
            {"type": "stock", "id": s["code"], "name": _display_name(s, "US"),
             "sub": f"{s['code']} · US equity", "market": "US", "price": s["price"],
             "changePct": pct(float(s["price"]), float(s.get("prev_close") or s["price"]))}
            for s in stocks
        ]
        presets = []
        if not q:
            liquid = sorted(pool, key=lambda s: float(s.get("amount") or 0), reverse=True)[:8]
            gainers = sorted(
                pool, key=lambda s: pct(float(s["price"]), float(s.get("prev_close") or s["price"])), reverse=True
            )[:8]
            majors = [by_code[c] for c in US_EN_NAMES if c in by_code][:8]
            presets = [
                {
                    "key": "active", "label": "Most active",
                    "desc": "Ranked by latest dollar volume",
                    "items": [us_card(s, f"Volume ${float(s.get('amount') or 0)/1e9:.1f}B") for s in liquid],
                },
                {
                    "key": "gainers", "label": "Top gainers",
                    "desc": "Ranked by latest session change",
                    "items": [us_card(s, f"{pct(float(s['price']), float(s.get('prev_close') or s['price'])):+.1f}%") for s in gainers],
                },
                {
                    "key": "majors", "label": "US majors",
                    "desc": "Liquid large-cap reference names",
                    "items": [us_card(s, _display_name(s, "US")) for s in majors],
                },
            ]
        available = bool(pool)
        if not q and not available:
            presets = []
        return {
            "q": q, "results": results, "presets": presets, "market": "US",
            "available": available,
            "note": (
                "US quote data is not available in the current data view. Switch to 中文 for A-share coverage."
                if not available else ""
            ),
        }

    stocks = []
    if q:
        like = f"%{q}%"
        stocks = rows(conn, """SELECT * FROM stocks WHERE COALESCE(market,'CN')='CN' AND
                              (name LIKE ? OR code LIKE ? OR pinyin LIKE ? OR industry LIKE ?)
                              LIMIT 8""", (like, like, like, like))
    topics = rows(conn, "SELECT * FROM topics WHERE name LIKE ? LIMIT 4", (f"%{q}%",)) if q else []
    results = [{"type": "stock", "id": s["code"], "name": s["name"], "sub": f"{s['code']} · {s['industry']}",
                "market": "CN", "price": s["price"], "changePct": pct(s["price"], s["prev_close"])} for s in stocks]
    # 热点详情缺少 bars/成分数据时，搜索不放出主题入口，避免点进去是空页。
    results += [
        {"type": "topic", "id": t["id"], "name": t["name"], "sub": "行业 / 主题",
         "price": None, "changePct": None}
        for t in topics if _topic_detail_available(conn, str(t["id"]))
    ]

    presets = []
    if not q:
        # 只用服务层快照字段，避免每次搜索对全市场逐股扫 750 天 bars/valuations
        pool = [
            s for s in rows(conn, "SELECT * FROM stocks WHERE COALESCE(market,'CN')='CN'")
            if s["asset"] == "stock" and s.get("price") is not None
        ]

        def card(s: dict[str, Any], reason: str) -> dict[str, Any]:
            return {
                "type": "stock", "id": s["code"], "name": s["name"],
                "sub": f"{s['code']} · {s['industry']}", "market": "CN", "price": s["price"],
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
    return {"q": q, "results": results, "presets": presets, "market": "CN", "available": True}


def build_news(conn: Any, kind: str | None = None, market: str = "CN") -> dict[str, Any]:
    if normalize_market(market) == "US":
        return {
            "items": [],
            "market": "US",
            "note": "US news coverage is not available (no free stable source). This build only ships US quotes and charts.",
            "disclaimer": "News coverage coming later; not investment advice.",
            "isDemo": False, "demoKinds": [],
        }
    if kind and kind != "all":
        items = rows(conn, "SELECT * FROM news WHERE kind=? ORDER BY published_at DESC LIMIT 20", (kind,))
    else:
        items = rows(conn, "SELECT * FROM news ORDER BY published_at DESC LIMIT 20")
    real = conn.execute(
        "SELECT COUNT(*) AS n FROM news WHERE id LIKE 'doc-%' OR id LIKE 'news-%' OR id LIKE 'ann-%' "
        "OR id LIKE 'rep-%' OR id LIKE 'cninfo-%' OR id LIKE 'sina%'"
    ).fetchone()["n"]
    seed_news = conn.execute(
        "SELECT COUNT(*) AS n FROM news WHERE kind='news' AND id NOT LIKE 'news-%' "
        "AND id NOT LIKE 'cninfo-%' AND id NOT LIKE 'sina%'"
    ).fetchone()["n"]
    return {"items": items, "disclaimer": "公告/研报仅保留标题、来源、时间与原文链接；非投资建议。",
            "isDemo": not bool(real), "demoKinds": ["news"] if seed_news else [], "market": "CN"}


def build_meta(conn: Any, market: str = "CN") -> dict[str, Any]:
    market = normalize_market(market)
    meta = _market_meta(conn, market)
    row = conn.execute("SELECT value FROM meta WHERE key='updated_at'").fetchone()
    view_row = conn.execute("SELECT value FROM meta WHERE key='dataView'").fetchone()
    return {
        "dataDate": meta["dataDate"], "dataView": view_row["value"] if view_row else None,
        "source": meta["dataSource"], "market": market,
        "isDemo": meta["isDemo"],
        "disclaimer": DISCLAIMER_EN if market == "US" else DISCLAIMER,
        "updatedAt": row["value"] if row else meta["dataDate"],
        "ageDays": meta["ageDays"], "ageTradingDays": meta["ageTradingDays"],
        "isStale": meta["isStale"],
    }


def coverage_status(stale_count: int, total: int) -> str:
    """全市场日线覆盖：零星停牌/新股只提示，超过 2% 才判失败。"""
    if total <= 0:
        return "fail"
    if stale_count <= 0:
        return "pass"
    return "warn" if stale_count / total <= 0.02 else "fail"


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
    # 全市场切换日常有零星停牌/新股未更新；少量缺口只提示，不把整页判为异常。
    stale_ratio = len(stale) / len(pool) if pool else 1.0
    bars_status = coverage_status(len(stale), len(pool))
    checks = [{
        "key": "bars",
        "label": "日线覆盖",
        "status": bars_status,
        "detail": f"CN {latest_by_market.get('CN','—')} / US {latest_by_market.get('US','—')}；有日线 {len(pool)}/{len(stocks)} 只，未更新 {len(stale)}"
                  + ("（≤2% 仅提示；超过 2% 才判失败）" if 0 < stale_ratio <= 0.02 else ""),
    }]
    pool_cn = [s for s in pool if market_of(s["code"]) == "CN"]
    pool_codes = [s["code"] for s in pool_cn]
    # 直接读 fin_income_statement 的 symbol 索引，避免 financials 视图对 90 万行做
    # code 变换 + DISTINCT；H5 的 code 不带交易所后缀，这里统一去掉后缀。
    fin_codes = {
        (symbol.split(".", 1)[0] if "." in symbol else symbol)
        for symbol in (
            r["symbol"] for r in rows(conn, "SELECT DISTINCT symbol FROM fin_income_statement")
        )
    }
    no_fin = [c for c in pool_codes if c not in fin_codes]
    fin_cov = (len(pool_codes) - len(no_fin)) / len(pool_codes) if pool_codes else 1.0
    fin_latest_row = conn.execute(
        "SELECT MAX(report_date) AS d FROM fin_income_statement"
    ).fetchone()
    fin_latest = (fin_latest_row or {}).get("d") or "—"
    checks.append({
        "key": "financials",
        "label": "已披露财务",
        "status": "pass" if fin_cov >= 0.95 else ("warn" if fin_cov >= 0.8 else "fail"),
        "detail": (
            f"A 股有财务 {len(pool_codes) - len(no_fin)}/{len(pool_codes)} 只"
            f"（{fin_cov:.1%}）；最新报告期 {fin_latest}；"
            f"缺 {len(no_fin)} 只（新股/未披露/无财务口径）；美股无财务源，已排除"
        ),
    })
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
