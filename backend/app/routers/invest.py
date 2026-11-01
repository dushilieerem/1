# -*- coding: utf-8 -*-
"""手机 Invest 接口（PostgreSQL 版）。

原 `invest-api` 的 FastAPI + SQLite 已并入主后端：
- 账号/登录/注册/找回密码统一走主站 `/api/auth/*`；
- 行情/财务/估值来自 PG 服务层，读模型见 `services/invest/rules.py`；
- 用户数据落 `invest_*` 表，不再使用 SQLite。
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.deps import require_user
from services.core.db import get_conn
from services.core.public_switches import disabled_modules
from services.invest import agent_tools
from services.invest import etf as etf_service
from services.invest import rules
from services.invest.db import PGConn, invest_conn

router = APIRouter(prefix="/api/invest", tags=["invest"])


def _guard(module: str):
    """数据模块下线开关：命中 INVEST_DISABLED_MODULES 时返回 503。"""

    def dependency() -> None:
        if module in disabled_modules():
            raise HTTPException(status_code=503, detail=f"{module} 模块已临时关闭，请稍后再试")

    return dependency

GLOSSARY = [
    {"term": "PE 分位", "text": "当前市盈率在过去 N 年里的位置；分位越低通常越“便宜”，但不预测涨跌。"},
    {"term": "拥挤度", "text": "板块成交 / 换手的热度；拥挤度偏高，短期波动通常更大。"},
    {"term": "base rate", "text": "历史上类似情况出现的频率，用分布替代“我感觉”。"},
    {"term": "最大回撤", "text": "从阶段高点到之后低点的最大跌幅，衡量持有体验。"},
    {"term": "换手率", "text": "一段时间内股票被交易的频繁程度；过高可能伴随情绪化交易。"},
    {"term": "beta", "text": "股价对大盘系统性波动的敏感度；数值越高越“跟涨跟跌”。"},
    {"term": "配置偏离", "text": "目标权重与当前权重的差；只展示，不构成调仓建议。"},
    {"term": "ROE", "text": "净资产收益率，衡量股东投入资本的盈利效率。"},
]


def _uid(user: dict[str, Any]) -> int:
    return int(user["id"])


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _audit(conn: PGConn, request: Request, user: dict[str, Any], action: str, detail: str) -> None:
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    try:
        conn.execute(
            "INSERT INTO invest_auth_event (ts, action, username, ip, detail) VALUES (?,?,?,?,?)",
            (_now(), action, user.get("username"), ip, detail[:300]),
        )
    except Exception:
        pass


@router.get("/meta")
def meta(conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return {**rules.build_meta(conn), "disabledModules": sorted(disabled_modules())}


@router.get("/data-quality")
def data_quality(conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_data_quality(conn)


@router.get("/glossary")
def glossary() -> dict[str, Any]:
    return {"items": GLOSSARY}


@router.get("/home", dependencies=[Depends(_guard("home"))])
def home(user: dict[str, Any] = Depends(require_user), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_home(conn, _uid(user))


@router.get("/topic/{topic_id}", dependencies=[Depends(_guard("topic"))])
def topic(topic_id: str, conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    data = rules.build_topic(conn, topic_id)
    if not data:
        raise HTTPException(status_code=404, detail="主题不存在")
    return data


@router.get("/stock/{code}", dependencies=[Depends(_guard("stock"))])
def stock(code: str, period: str = Query("daily"), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    if period not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="period 必须是 daily/weekly/monthly")
    data = rules.build_stock(conn, code, period)
    if not data:
        raise HTTPException(status_code=404, detail="标的未收录")
    data["behavior"] = agent_tools.behavior_alert_from_stock(conn, code, data)
    return data


@router.get("/search", dependencies=[Depends(_guard("search"))])
def search(q: str = Query(""), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_search(conn, q)


@router.get("/news", dependencies=[Depends(_guard("news"))])
def news(kind: str | None = Query(None), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_news(conn, kind)


@router.get("/etf/overlap")
def etf_overlap(a: str, b: str) -> dict[str, Any]:
    try:
        return etf_service.overlap(a, b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/etf/{code}")
def etf_profile(code: str, top: int = 20) -> dict[str, Any]:
    """H06/H07：ETF 跟踪指数与代理成分。"""
    try:
        return etf_service.profile(code, top=top)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/portfolio/penetration")
def portfolio_penetration(
    top: int = Query(30, ge=1, le=100),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """F24：ETF 按跟踪指数穿透后的底层暴露。"""
    return agent_tools.portfolio_penetration(conn, _uid(user), top=top)


@router.post("/risk-scan")
def risk_scan(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """F25：组合诊断 + 自选异动的主动扫描（收盘后口径）。"""
    return agent_tools.risk_scan(conn, _uid(user))


@router.post("/events/scan")
def events_scan(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """F9：值守 Agent 的日频扫描入口（脚本/定时任务亦可调用服务层）。"""
    return agent_tools.watch_scan(conn, _uid(user))


@router.get("/quant/select")
def quant_select(
    top: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """F29：轻量多因子规则选股（非回测、非推荐）。"""
    return agent_tools.quant_select(conn, top=top)


@router.get("/quant/signals")
def quant_signals(
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    """F27：模拟盘策略信号监控（最新持仓与现金）。"""
    return agent_tools.quant_signals(_uid(user))


@router.get("/watchlist")
def watchlist(user: dict[str, Any] = Depends(require_user), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_watchlist(conn, _uid(user))


@router.post("/watchlist")
def add_watchlist(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    code = str(body.get("code") or "").strip()
    exists = conn.execute("SELECT 1 FROM stocks WHERE code=?", (code,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="标的未收录")
    conn.execute(
        "INSERT INTO invest_watchlist (user_id, code, group_name, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT (user_id, code) DO NOTHING",
        (_uid(user), code, str(body.get("group") or "默认"), _now()),
    )
    conn.commit()
    return rules.build_watchlist(conn, _uid(user))


@router.delete("/watchlist/{code}")
def remove_watchlist(
    code: str,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    conn.execute("DELETE FROM invest_watchlist WHERE user_id=? AND code=?", (_uid(user), code))
    conn.commit()
    return rules.build_watchlist(conn, _uid(user))


@router.post("/events")
def add_event(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    code = str(body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少标的")
    conn.execute(
        "INSERT INTO invest_event (user_id, code, type, condition, status, created_at) VALUES (?,?,?,?,?,?)",
        (_uid(user), code, str(body.get("type") or "价格"), str(body.get("condition") or "收盘后检查"), "active", _now()),
    )
    conn.commit()
    return rules.build_watchlist(conn, _uid(user))


@router.post("/risk-profile")
def save_risk_profile(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    level = str(body.get("level") or "稳健型")
    score = int(body.get("score") or 62)
    answers = json.dumps(body.get("answers") or {}, ensure_ascii=False)
    conn.execute(
        "INSERT INTO invest_risk_profile (user_id, level, score, answers, updated_at) VALUES (?,?,?,?::jsonb,?) "
        "ON CONFLICT (user_id) DO UPDATE SET level=EXCLUDED.level, score=EXCLUDED.score, "
        "answers=EXCLUDED.answers, updated_at=EXCLUDED.updated_at",
        (_uid(user), level, score, answers, _now()),
    )
    conn.commit()
    return {"level": level, "score": score}


@router.get("/risk-profile")
def get_risk_profile(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM invest_risk_profile WHERE user_id=?", (_uid(user),)).fetchone()
    if not row:
        return {"level": None, "score": None}
    return {
        "level": row["level"],
        "score": row["score"],
        "answers": json.loads(row["answers"] or "{}"),
        "updatedAt": row["updated_at"],
    }


@router.get("/portfolio")
def portfolio(user: dict[str, Any] = Depends(require_user), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_portfolio(conn, _uid(user))


@router.post("/portfolio/import")
def import_portfolio(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    uid = _uid(user)
    items = body.get("holdings")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="holdings 不能为空")
    old_targets = {
        r["code"]: r["target_weight"]
        for r in conn.execute("SELECT code, target_weight FROM invest_portfolio WHERE user_id=?", (uid,)).fetchall()
    }
    prepared = []
    total = 0.0
    for item in items:
        code = str(item.get("code") or "").strip()
        shares = float(item.get("shares") or 0)
        cost = float(item.get("cost") or 0)
        if code == "CASH":
            value = shares
            industry = "现金"
        else:
            s = conn.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
            if not s:
                raise HTTPException(status_code=400, detail=f"标的未收录：{code}")
            value = shares * float(s["price"] or 0)
            industry = s["industry"]
        total += value
        prepared.append((code, shares, cost or (value / shares if shares else 1), value, industry))
    if total <= 0:
        raise HTTPException(status_code=400, detail="持仓市值必须大于 0")
    conn.execute("DELETE FROM invest_portfolio WHERE user_id=?", (uid,))
    for code, shares, cost, value, industry in prepared:
        weight = value / total * 100
        target = float(old_targets.get(code, weight))
        conn.execute(
            "INSERT INTO invest_portfolio (user_id, code, shares, cost, weight, target_weight, industry) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, code, shares, cost, round(weight, 2), round(target, 2), industry),
        )
    conn.commit()
    return rules.build_portfolio(conn, uid)


@router.get("/account/export")
def export_account(
    request: Request,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    uid = _uid(user)
    watch = [dict(r) for r in conn.execute("SELECT * FROM invest_watchlist WHERE user_id=?", (uid,)).fetchall()]
    events = [dict(r) for r in conn.execute("SELECT * FROM invest_event WHERE user_id=?", (uid,)).fetchall()]
    logs = [dict(r) for r in conn.execute("SELECT * FROM invest_event_log WHERE user_id=?", (uid,)).fetchall()]
    pf = [dict(r) for r in conn.execute("SELECT * FROM invest_portfolio WHERE user_id=?", (uid,)).fetchall()]
    risk = conn.execute("SELECT * FROM invest_risk_profile WHERE user_id=?", (uid,)).fetchone()
    audit = [
        {"ts": r["ts"], "action": r["action"], "detail": r["detail"]}
        for r in conn.execute(
            "SELECT ts, action, detail FROM invest_auth_event WHERE username=? ORDER BY id DESC LIMIT 100",
            (user.get("username"),),
        ).fetchall()
    ]
    _audit(conn, request, user, "export", "account export")
    conn.commit()
    return {
        "generatedAt": rules.build_meta(conn)["updatedAt"],
        "note": "仅导出 Invest 数据；SVQuant 账号本身需在主站处理。",
        "user": user,
        "watchlist": watch,
        "events": events,
        "eventLogs": logs,
        "portfolio": pf,
        "riskProfile": dict(risk) if risk else None,
        "authEvents": audit,
    }


@router.delete("/account/data")
def delete_invest_data(
    request: Request,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    uid = _uid(user)
    for table in ("invest_watchlist", "invest_event", "invest_event_log", "invest_portfolio", "invest_portfolio_meta", "invest_risk_profile"):
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
    _audit(conn, request, user, "delete_invest_data", "local Invest data only")
    conn.commit()
    return {"ok": True, "deleted": ["watchlist", "events", "event_logs", "portfolio", "portfolio_meta", "risk_profile"]}
