# -*- coding: utf-8 -*-
"""手机端 Agent 的确定性工具层（计算下沉，不交给模型）。

覆盖能力:
- Agent 4 多标的对比（F21）
- Agent 5 组合穿透（F24）与主动风险扫描（F25）
- Agent 6 收盘后值守扫描（F9/F23 的日频部分）
- Agent 7 行为护栏（F5 追高提醒 + base rate）
- Agent 8 因子看板/轻量选股/策略信号（F26/F27/F29）
- Agent 2 语音文本的金融实体校正

所有函数只读 PG/视图，不改变交易状态。
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from services.invest import etf, rules

DISCLAIMER = "仅为数据解释与风险提示，不构成投资建议。"


def _bare(code: str) -> str:
    return str(code or "").strip().upper().split(".")[0]


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _value(conn: Any, holding: dict[str, Any]) -> float:
    if holding["code"] == "CASH":
        return float(holding.get("shares") or 0)
    return float(holding.get("shares") or 0) * float(holding.get("price") or 0)


# ---------------------------------------------------------------- Agent 4 对比
def compare_context(conn: Any, code_a: str, code_b: str) -> dict[str, Any]:
    """两只标的的同口径指标（缺失字段保留 None，由卡片标注“待补充”）。"""
    data = {}
    for key, code in (("a", code_a), ("b", code_b)):
        stock = rules.build_stock(conn, _bare(code))
        if not stock:
            raise ValueError(f"标的未收录：{code}")
        quote = stock.get("quote") or {}
        technical = stock.get("technical") or {}
        valuation = stock.get("valuation") or {}
        report = stock.get("report") or {}
        data[key] = {
            "code": quote.get("code") or _bare(code),
            "name": quote.get("name") or _bare(code),
            "industry": quote.get("industry"),
            "price": quote.get("price"),
            "changePct": quote.get("changePct"),
            "pe": valuation.get("pe"),
            "pb": valuation.get("pb"),
            "pePercentile": valuation.get("pePercentile"),
            "dividendYield": quote.get("dividendYield"),
            "return20": technical.get("return20"),
            "drawdown": technical.get("drawdown"),
            "trend": technical.get("trend"),
            "revenue": report.get("revenue"),
            "netProfit": report.get("netProfit"),
            "grossMargin": report.get("grossMargin"),
            "roe": report.get("roe"),
            "dataDate": stock.get("dataDate"),
        }
    return {
        "a": data["a"],
        "b": data["b"],
        "note": "同口径对比；只有单边数据时显示“待补充”，不推断谁更好。",
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- Agent 5 穿透
def portfolio_penetration(conn: Any, user_id: int, *, top: int = 30) -> dict[str, Any]:
    """ETF 按跟踪指数代理成分穿透，直接持股保留，输出合并后的底层暴露。"""
    holdings = rules.portfolio_rows(conn, user_id)
    if not holdings:
        return {
            "ok": True,
            "holdings": [],
            "lookthrough": [],
            "etfWeight": 0,
            "coveragePct": 0,
            "unmapped": [],
            "note": "尚未导入持仓。",
            "disclaimer": DISCLAIMER,
        }
    total = sum(_value(conn, h) for h in holdings)
    if total <= 0:
        return {"ok": True, "holdings": [], "lookthrough": [], "etfWeight": 0, "coveragePct": 0, "unmapped": [], "note": "持仓市值为 0。", "disclaimer": DISCLAIMER}

    look: dict[str, float] = defaultdict(float)
    etf_weight = 0.0
    covered = 0.0
    unmapped: list[dict[str, Any]] = []
    cash_weight = 0.0
    for h in holdings:
        weight = _value(conn, h) / total * 100
        code = str(h["code"])
        if code == "CASH":
            cash_weight += weight
            continue
        if not etf.is_etf(code):
            look[_bare(code)] += weight
            continue
        etf_weight += weight
        try:
            profile = etf.profile(code, top=200)
        except ValueError:
            profile = {"tracking": "unmapped", "constituents": []}
        constituents = profile.get("constituents") or []
        if profile.get("tracking") == "index_proxy" and constituents:
            covered += weight
            for item in constituents:
                w = _num(item.get("weight"))
                if w is None:
                    continue
                look[_bare(item.get("symbol"))] += weight * w / 100.0
        else:
            unmapped.append({"code": code, "name": h.get("name") or code, "weight": round(weight, 1)})

    ordered = sorted(look.items(), key=lambda x: x[1], reverse=True)
    names = {}
    try:
        names = {str(row["code"]): row.get("name") for row in rules.rows(conn, "SELECT code, name FROM stocks")}
    except Exception:
        names = {}
    lookthrough = [
        {"code": code, "name": names.get(code) or code, "weight": round(weight, 2)}
        for code, weight in ordered[: max(1, min(top, 100))]
    ]
    top3 = sum(w for _, w in ordered[:3])
    top10 = sum(w for _, w in ordered[:10])
    return {
        "ok": True,
        "holdings": [
            {"code": h["code"], "name": h.get("name") or h["code"], "weight": round(_value(conn, h) / total * 100, 1)}
            for h in holdings
        ],
        "lookthrough": lookthrough,
        "etfWeight": round(etf_weight, 1),
        "coveragePct": round(covered / etf_weight * 100, 1) if etf_weight else 100.0,
        "unmapped": unmapped,
        "cashWeight": round(cash_weight, 1),
        "top3": round(top3, 1),
        "top10": round(top10, 1),
        "note": "ETF 用跟踪指数成分代理穿透；权重缺失的指数无法穿透，已在 unmapped 列出。",
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- Agent 5/6 扫描
def _today_prefix() -> str:
    return date.today().isoformat()


def _log_once(conn: Any, user_id: int, code: str, title: str, detail: str) -> bool:
    today = _today_prefix()
    exists = rules.one(
        conn,
        "SELECT 1 FROM invest_event_log WHERE user_id=? AND code=? AND title=? AND triggered_at LIKE ?",
        (user_id, code, title, f"{today}%"),
    )
    if exists:
        return False
    conn.execute(
        "INSERT INTO invest_event_log (user_id, code, title, detail, triggered_at, read) "
        "VALUES (?,?,?,?,to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),FALSE)",
        (user_id, code, title, detail[:500]),
    )
    return True


def risk_scan(conn: Any, user_id: int, *, persist: bool = True) -> dict[str, Any]:
    """组合诊断 + 自选异常，生成可落库的提醒（同日同标题去重）。"""
    alerts: list[dict[str, Any]] = []
    pf = rules.build_portfolio(conn, user_id, include_penetration=False)
    for item in pf.get("diagnosis") or []:
        alerts.append(
            {
                "code": "PORTFOLIO",
                "level": "amber",
                "title": str(item.get("title") or "组合风险"),
                "detail": str(item.get("detail") or ""),
                "source": "组合诊断",
            }
        )
    watch = rules.rows(
        conn,
        "SELECT w.code, s.name, s.price, s.prev_close FROM watchlist w "
        "LEFT JOIN stocks s ON s.code=w.code WHERE w.user_id=?",
        (user_id,),
    )
    for item in watch:
        price, prev = _num(item.get("price")), _num(item.get("prev_close"))
        if not price or not prev:
            continue
        change = (price / prev - 1) * 100
        if abs(change) >= 5:
            alerts.append(
                {
                    "code": item["code"],
                    "level": "red" if abs(change) >= 8 else "amber",
                    "title": f"{item.get('name') or item['code']} 收盘异动 {change:+.1f}%",
                    "detail": "收盘后快照触发；不构成买卖建议，先核对公告与仓位。",
                    "source": "自选异动",
                }
            )

    # 舆情异常：仅扫描用户显式勾选“舆情异常”的标的，避免对全部自选做重查询
    sentiment_codes = rules.rows(
        conn,
        "SELECT DISTINCT code FROM invest_event WHERE user_id=? AND type='舆情异常' AND status='active'",
        (user_id,),
    )
    for item in sentiment_codes:
        code = str(item.get("code") or "")
        if not code:
            continue
        try:
            stock = rules.build_stock(conn, code)
        except Exception:
            stock = None
        senti = (stock or {}).get("sentiment") or {}
        if not senti.get("available"):
            continue
        if float(senti.get("negative") or 0) >= 60 and float(senti.get("heat") or 0) >= 30:
            alerts.append(
                {
                    "code": code,
                    "level": "amber",
                    "title": f"{(stock or {}).get('quote', {}).get('name') or code} 舆情偏负面",
                    "detail": f"负面占比 {senti.get('negative')}%、热度 {senti.get('heat')}；代表事件：{senti.get('topEvent') or '待补充'}。仅描述，不预测方向。",
                    "source": "舆情异常（资讯标题词典）",
                }
            )

    inserted = 0
    if persist:
        for alert in alerts:
            if _log_once(conn, user_id, alert["code"], alert["title"], alert["detail"]):
                inserted += 1
        conn.commit()
    return {
        "ok": True,
        "alerts": alerts,
        "inserted": inserted,
        "scannedAt": date.today().isoformat(),
        "note": "收盘后扫描；不提供实时推送。",
        "disclaimer": DISCLAIMER,
    }


def watch_scan(conn: Any, user_id: int) -> dict[str, Any]:
    """收盘后扫描：自选异动 + 用户自定义提醒条件，命中写入触发日志。"""
    out = risk_scan(conn, user_id, persist=True)
    try:
        from services.invest import reminders

        scanned = reminders.evaluate(conn, user_id, persist=True)
    except Exception:
        scanned = {"triggered": [], "inserted": 0, "checked": 0}
    out["reminders"] = scanned
    out["inserted"] = int(out.get("inserted") or 0) + int(scanned.get("inserted") or 0)
    return out


# ---------------------------------------------------------------- Agent 7 护栏
def _base_rate_bars(conn: Any, code: str) -> list[dict[str, Any]]:
    """估值/换手与收盘对齐，供 base rate 使用（bars 视图不含这两个字段）。"""
    try:
        rows = rules.rows(
            conn,
            "SELECT * FROM ("
            "  SELECT n.trade_date::text AS date, n.close, v.pe_ttm AS valuation, n.turnover "
            "  FROM md_daily_bar n "
            "  LEFT JOIN md_valuation_daily v ON v.symbol=n.symbol AND v.trade_date=n.trade_date "
            "  WHERE n.symbol=? AND n.adjust='none' "
            "  ORDER BY n.trade_date DESC LIMIT 750"
            ") t ORDER BY date ASC",
            (rules._with_suffix(code),),
        )
        return [r for r in rows if r.get("close")]
    except Exception:
        return []


def behavior_alert(conn: Any, code: str) -> dict[str, Any]:
    stock = rules.build_stock(conn, _bare(code))
    return behavior_alert_from_stock(conn, code, stock)


def behavior_alert_from_stock(conn: Any, code: str, stock: dict[str, Any] | None) -> dict[str, Any]:
    if not stock or not (stock.get("quote") or {}).get("price"):
        return {"ok": True, "triggered": False, "reason": "数据暂缺"}
    quote = stock["quote"]
    valuation = stock.get("valuation") or {}
    technical = stock.get("technical") or {}
    pe_pct = _num(valuation.get("pePercentile"))
    ret20 = _num(technical.get("return20"))
    turnover = _num(quote.get("turnover"))
    hits = []
    if pe_pct is not None and pe_pct >= 80:
        hits.append(f"PE 处于近 3 年 {pe_pct:.0f}% 分位")
    if ret20 is not None and ret20 >= 10:
        hits.append(f"近 20 日涨幅 {ret20:+.1f}%")
    if turnover is not None and turnover >= 5:
        hits.append(f"换手率 {turnover:.1f}%")
    triggered = bool(hits) and (pe_pct is None or pe_pct >= 70 or (ret20 or 0) >= 10)
    bars = _base_rate_bars(conn, _bare(code))
    base = rules.compute_base_rate(bars)
    return {
        "ok": True,
        "triggered": triggered,
        "code": quote.get("code"),
        "name": quote.get("name"),
        "reasons": hits,
        "baseRate": base,
        "note": "热度与估值是两件事；历史分布不是预测。",
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- Agent 2 实体校正
def correct_entities(conn: Any, text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"text": "", "entities": [], "corrections": []}
    stocks = rules.rows(conn, "SELECT code, name FROM stocks WHERE name IS NOT NULL")
    by_name = {str(r["name"]): str(r["code"]) for r in stocks if r.get("name")}
    names = list(by_name)
    entities: list[dict[str, Any]] = []
    corrections: list[dict[str, str]] = []
    for name in names:
        if name and name in raw:
            entities.append({"name": name, "code": by_name[name], "kind": "stock"})
    for code in re.findall(r"\d{6}", raw):
        entities.append({"name": code, "code": code, "kind": "code"})
    tokens: list[str] = []
    for segment in re.findall(r"[一-龥]{2,}", raw):
        for size in range(2, min(5, len(segment)) + 1):
            for start in range(0, len(segment) - size + 1):
                token = segment[start : start + size]
                if token not in by_name:
                    tokens.append(token)
    for token in dict.fromkeys(tokens):
        match = difflib.get_close_matches(token, names, n=1, cutoff=0.75)
        if match and match[0] not in raw:
            corrections.append({"from": token, "to": match[0], "code": by_name[match[0]]})
    uniq: dict[tuple[str, str], dict[str, Any]] = {}
    for item in entities:
        uniq[(item["kind"], item["code"])] = item
    corrected = raw
    applied = []
    for item in corrections[:5]:
        if corrected.count(item["from"]) == 1:
            corrected = corrected.replace(item["from"], item["to"])
            applied.append(item)
    return {
        "text": corrected,
        "rawText": raw,
        "entities": list(uniq.values()),
        "corrections": applied,
    }


# ---------------------------------------------------------------- Agent 3 模拟盘
def paper_review(user_id: int, account_id: int) -> dict[str, Any]:
    from services.paper import paper_store

    try:
        data = paper_store.get_account(user_id, account_id)
    except KeyError:
        raise ValueError("模拟盘账户不存在") from None
    account = data.get("account") or {}
    positions = data.get("positions") or []
    total = _num(account.get("totalEquity")) or 0
    cash = _num(account.get("cash")) or 0
    return {
        "account": {
            "id": account.get("id"),
            "name": account.get("name"),
            "status": account.get("status"),
            "strategyName": account.get("projectName"),
            "cash": round(cash, 0),
            "totalEquity": round(total, 0),
            "cashPct": round(cash / total * 100, 1) if total else None,
            "lastSettledDate": account.get("lastSettledDate"),
        },
        "positions": positions[:20],
        "positionCount": len(positions),
        "note": "模拟盘为日终撮合，非真实成交。",
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- Agent 8 量化
def _score_candidates(rows: list[dict[str, Any]], *, top: int = 20) -> list[dict[str, Any]]:
    """轻量多因子打分：低 PE、高股息、20 日动量（缺失按中性 0）。"""
    if not rows:
        return []
    pe_vals = [1.0 / float(r["pe"]) for r in rows if _num(r.get("pe")) and float(r["pe"]) > 0]
    div_vals = [float(r["dividend"]) for r in rows if _num(r.get("dividend"))]
    mom_vals = [float(r["momentum"]) for r in rows if _num(r.get("momentum"))]
    # 用分位映射避免逐行重算 zscore
    def pct_rank(value: float | None, values: list[float]) -> float:
        if value is None or not values:
            return 0.0
        return sum(1 for v in values if v <= value) / len(values)

    out = []
    for r in rows:
        pe = _num(r.get("pe"))
        div = _num(r.get("dividend"))
        mom = _num(r.get("momentum"))
        score = 0.0
        parts = []
        if pe is not None and pe > 0 and pe_vals:
            v = pct_rank(1.0 / pe, pe_vals)
            score += (v - 0.5) * 2
            parts.append(("低估值", round(v * 100)))
        if div is not None and div_vals:
            v = pct_rank(div, div_vals)
            score += (v - 0.5) * 2
            parts.append(("高股息", round(v * 100)))
        if mom is not None and mom_vals:
            v = pct_rank(mom, mom_vals)
            score += (v - 0.5) * 2
            parts.append(("20 日动量", round(v * 100)))
        out.append({**r, "score": round(score, 3), "parts": parts})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[: max(1, min(top, 100))]


def quant_select(conn: Any, *, top: int = 20) -> dict[str, Any]:
    """从 H5 服务快照 + 日线动量做轻量选股；不执行回测。"""
    base = rules.rows(
        conn,
        "SELECT code, name, industry, pe_ttm AS pe, dividend_yield AS dividend "
        "FROM stocks WHERE price IS NOT NULL AND (asset IS NULL OR asset <> 'etf')",
    )
    momentum: dict[str, float] = {}
    try:
        bars = rules.rows(
            conn,
            """
            WITH d AS (
              SELECT split_part(symbol, '.', 1) AS code, close,
                     row_number() OVER (PARTITION BY symbol ORDER BY trade_date DESC) AS rn
                FROM md_daily_bar
               WHERE adjust='hfq' AND trade_date >= CURRENT_DATE - INTERVAL '120 days'
            )
            SELECT code,
                   MAX(close) FILTER (WHERE rn=1) AS last_close,
                   MAX(close) FILTER (WHERE rn=21) AS close_20
              FROM d WHERE rn <= 21 GROUP BY code
            """,
        )
        for row in bars:
            last, prev = _num(row.get("last_close")), _num(row.get("close_20"))
            if last and prev:
                momentum[str(row["code"])] = (last / prev - 1) * 100
    except Exception:
        momentum = {}
    candidates = []
    for row in base:
        code = str(row["code"])
        candidates.append(
            {
                "code": code,
                "name": row.get("name") or code,
                "industry": row.get("industry"),
                "pe": _num(row.get("pe")),
                "dividend": _num(row.get("dividend")),
                "momentum": momentum.get(code),
            }
        )
    ranked = _score_candidates(candidates, top=top)
    return {
        "ok": True,
        "items": ranked,
        "factors": ["低估值", "高股息", "20 日动量"],
        "note": "轻量规则打分，不是策略回测，也不是推荐；缺失因子按中性处理。",
        "disclaimer": DISCLAIMER,
    }


def quant_signals(user_id: int, *, limit: int = 10) -> dict[str, Any]:
    from services.paper import paper_store

    accounts = paper_store.list_accounts(user_id).get("accounts") or []
    out = []
    for account in accounts[: max(1, limit)]:
        positions = paper_store.list_positions(user_id, int(account["id"]))
        out.append(
            {
                "id": account.get("id"),
                "name": account.get("name"),
                "status": account.get("status"),
                "strategyName": account.get("projectName"),
                "totalEquity": account.get("totalEquity"),
                "cash": account.get("cash"),
                "positionCount": len(positions),
                "positions": [
                    {
                        "symbol": p.get("symbol"),
                        "quantity": p.get("quantity"),
                        "marketValue": p.get("marketValue"),
                    }
                    for p in positions[:10]
                ],
                "lastSettledDate": account.get("lastSettledDate"),
                "signal": "持有" if positions else "空仓",
            }
        )
    return {
        "ok": True,
        "accounts": out,
        "note": "信号来自模拟盘最新持仓，不是实时交易指令。",
        "disclaimer": DISCLAIMER,
    }


def quant_context(conn: Any, user_id: int) -> dict[str, Any]:
    """给 Agent 8 的 AI 解释卡片用的结构化上下文。"""
    return {
        "selection": quant_select(conn, top=10),
        "signals": quant_signals(user_id, limit=5),
        "note": "因子与信号均由工具计算，模型只做解释。",
        "disclaimer": DISCLAIMER,
    }
