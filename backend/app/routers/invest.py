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
from services.invest import agent_prompts, agent_tools
from services.invest import condition as condition_service
from services.invest import etf as etf_service
from services.invest import glossary as glossary_service
from services.invest import quant
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
def meta(market: str = Query("CN"), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return {**rules.build_meta(conn, market), "disabledModules": sorted(disabled_modules())}


@router.get("/data-quality")
def data_quality(conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_data_quality(conn)


@router.get("/glossary")
def glossary(
    category: str = Query(""),
    q: str = Query(""),
) -> dict[str, Any]:
    return glossary_service.list_terms(category=category, q=q)


@router.get("/home", dependencies=[Depends(_guard("home"))])
def home(
    market: str = Query("CN"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return rules.build_home(conn, _uid(user), market)


@router.get("/topics", dependencies=[Depends(_guard("topic"))])
def topics(conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return rules.build_topics(conn)


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
        raise HTTPException(
            status_code=404,
            detail="US ticker not available in the current data view" if "." in code else "标的未收录",
        )
    if "." not in code:
        data["behavior"] = agent_tools.behavior_alert_from_stock(conn, code, data)
    return data


@router.get("/search", dependencies=[Depends(_guard("search"))])
def search(
    q: str = Query(""),
    market: str = Query("CN"),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return rules.build_search(conn, q, market)


@router.get("/news", dependencies=[Depends(_guard("news"))])
def news(
    kind: str | None = Query(None),
    market: str = Query("CN"),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return rules.build_news(conn, kind, market)


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


@router.get("/event-logs")
def event_logs(
    limit: int = Query(50, ge=1, le=200),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    items = rules.rows(
        conn,
        "SELECT id, code, title, detail, triggered_at, read FROM invest_event_log "
        "WHERE user_id=? ORDER BY triggered_at DESC LIMIT ?",
        (_uid(user), limit),
    )
    return {"items": items, "unread": sum(1 for x in items if not x.get("read"))}


@router.post("/event-logs/read")
def event_logs_read(
    body: dict[str, Any] | None = Body(None),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    payload = body or {}
    if payload.get("all"):
        conn.execute("UPDATE invest_event_log SET read=TRUE WHERE user_id=?", (_uid(user),))
    elif payload.get("id") is not None:
        conn.execute(
            "UPDATE invest_event_log SET read=TRUE WHERE user_id=? AND id=?",
            (_uid(user), int(payload["id"])),
        )
    conn.commit()
    return {"ok": True}


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


# ---------------------------------------------------------------------------
# AI Agent 管理：展示 H5 可用 Agent，按用户保存提示词覆盖
# ---------------------------------------------------------------------------

@router.get("/agents")
def agents(
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    return agent_prompts.list_agents(_uid(user))


@router.put("/agents/{task_id}")
def agent_prompt_save(
    task_id: str,
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    try:
        data = agent_prompts.save_prompt(_uid(user), task_id, str(body.get("prompt") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **data}


# ---------------------------------------------------------------------------
# 量化研究（11.4 功能设计）：因子 / 草稿 / 策略 / 回测 / 模拟盘 / 广场
# ---------------------------------------------------------------------------

def _quant_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except quant.QuantDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/quant/overview")
def quant_overview(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return _quant_call(quant.overview, conn, _uid(user))


@router.get("/quant/factors")
def quant_factors(
    range: str = Query("1m"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return _quant_call(quant.factor_board, conn, range)


@router.get("/quant/factors/{key}")
def quant_factor_detail(
    key: str,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.factor_detail, conn, key)
    if not data:
        raise HTTPException(status_code=404, detail="因子不存在")
    return data


@router.get("/quant/drafts")
def quant_drafts(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return _quant_call(quant.list_drafts, conn, _uid(user))


@router.post("/quant/drafts")
def quant_draft_create(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.create_draft, conn, _uid(user), body)
    conn.commit()
    return data


@router.delete("/quant/drafts/{draft_id}")
def quant_draft_delete(
    draft_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    _quant_call(quant.delete_draft, conn, _uid(user), draft_id)
    conn.commit()
    return {"ok": True}


@router.post("/quant/strategies/parse")
def quant_strategy_parse(
    body: dict[str, Any] = Body(...),
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    return _quant_call(quant.parse_intent, str(body.get("text") or body.get("query") or ""))


@router.get("/quant/strategies")
def quant_strategies(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return _quant_call(quant.list_strategies, conn, _uid(user))


@router.post("/quant/strategies")
def quant_strategy_create(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.create_strategy, conn, _uid(user), body)
    conn.commit()
    return data


@router.get("/quant/strategies/{strategy_id}")
def quant_strategy_detail(
    strategy_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.strategy_detail, conn, _uid(user), strategy_id)
    if not data:
        raise HTTPException(status_code=404, detail="策略不存在")
    conn.commit()
    return data


@router.delete("/quant/strategies/{strategy_id}")
def quant_strategy_delete(
    strategy_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    _quant_call(quant.delete_strategy, conn, _uid(user), strategy_id)
    conn.commit()
    return {"ok": True}


@router.get("/quant/backtests")
def quant_backtests(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return _quant_call(quant.list_backtests, conn, _uid(user))


@router.post("/quant/backtests")
def quant_backtest_create(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(
        quant.run_backtest,
        conn,
        body.get("factors"),
        body.get("universe"),
        persist=True,
        user_id=_uid(user),
        name=body.get("name"),
        project_id=body.get("project_id"),
    )
    conn.commit()
    return data


@router.get("/quant/backtests/{backtest_id}")
def quant_backtest_detail(
    backtest_id: str,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.get_backtest, conn, _uid(user), backtest_id)
    if not data:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    return data


@router.post("/quant/backtests/{backtest_id}/commentary")
def quant_backtest_commentary(
    backtest_id: str,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    data = _quant_call(quant.get_backtest, conn, _uid(user), backtest_id)
    if not data:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    payload = {
        "name": data.get("name"), "factors": data.get("factors"), "universe": data.get("universe"),
        "period": {"start": data.get("start_date"), "end": data.get("end_date")},
        "metrics": data.get("metrics"), "assumptions": data.get("assumptions"),
        "holdings": data.get("holdings"),
        "note": "历史回测结果，非真实收益；AI 不得改算任何数值。",
    }
    return _quant_call(quant.ai_commentary, "backtest", payload, user_id=_uid(user), refresh=refresh)


@router.get("/quant/papers")
def quant_papers(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return _quant_call(quant.list_papers, conn, _uid(user))


@router.post("/quant/papers")
def quant_paper_create(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.create_paper, conn, _uid(user), body)
    conn.commit()
    return data


@router.get("/quant/papers/{paper_id}")
def quant_paper_detail(
    paper_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.paper_detail, conn, _uid(user), paper_id)
    if not data:
        raise HTTPException(status_code=404, detail="模拟盘不存在")
    conn.commit()
    return data


@router.post("/quant/papers/{paper_id}/commentary")
def quant_paper_commentary(
    paper_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    data = _quant_call(quant.paper_detail, conn, _uid(user), paper_id)
    if not data:
        raise HTTPException(status_code=404, detail="模拟盘不存在")
    return _quant_call(quant.ai_commentary, "paper", data, user_id=_uid(user), refresh=refresh)


@router.delete("/quant/papers/{paper_id}")
def quant_paper_delete(
    paper_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    _quant_call(quant.delete_paper, conn, _uid(user), paper_id)
    conn.commit()
    return {"ok": True}


@router.get("/quant/plaza")
def quant_plaza(
    sort: str = Query("followers"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.list_plaza, conn, _uid(user), sort)
    conn.commit()
    return data


@router.get("/quant/plaza/{plaza_id}")
def quant_plaza_detail(
    plaza_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.get_plaza, conn, _uid(user), plaza_id)
    if not data:
        raise HTTPException(status_code=404, detail="策略不存在")
    conn.commit()
    return data


@router.post("/quant/plaza/{plaza_id}/copy")
def quant_plaza_copy(
    plaza_id: int,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    data = _quant_call(quant.copy_plaza, conn, _uid(user), plaza_id)
    conn.commit()
    return data


@router.post("/quant/plaza/{plaza_id}/follow")
def quant_plaza_follow(
    plaza_id: int,
    body: dict[str, Any] | None = Body(None),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    payload = body or {}
    data = _quant_call(quant.follow_plaza, conn, _uid(user), plaza_id, bool(payload.get("followed", True)))
    conn.commit()
    return data


@router.get("/watchlist")
def watchlist(
    market: str = Query("CN"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    return rules.build_watchlist(conn, _uid(user), market)


@router.post("/watchlist")
def add_watchlist(
    body: dict[str, Any] = Body(...),
    market: str = Query("CN"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    code = str(body.get("code") or "").strip()
    exists = conn.execute("SELECT 1 FROM stocks WHERE code=?", (code,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="标的未收录")
    default_group = "Default" if rules.normalize_market(market) == "US" else "默认"
    conn.execute(
        "INSERT INTO invest_watchlist (user_id, code, group_name, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT (user_id, code) DO NOTHING",
        (_uid(user), code, str(body.get("group") or default_group), _now()),
    )
    conn.commit()
    return rules.build_watchlist(conn, _uid(user), market)


@router.delete("/watchlist/{code}")
def remove_watchlist(
    code: str,
    market: str = Query("CN"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    conn.execute("DELETE FROM invest_watchlist WHERE user_id=? AND code=?", (_uid(user), code))
    conn.commit()
    return rules.build_watchlist(conn, _uid(user), market)


@router.post("/condition/parse")
def parse_condition(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    """解析自然语言选股条件；只解析，不执行。"""
    del user
    return condition_service.parse_query(str(body.get("query") or ""))


@router.post("/condition/screen")
def screen_condition(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """执行条件筛选。

    前端删除标签后回传 ``conditions``；首次请求可只传 ``query``。
    未识别、冲突或资金流等无数据源的条件直接返回 needs_input，绝不猜测执行。
    """
    del user
    query = str(body.get("query") or "").strip()
    parsed: dict[str, Any] | None = None
    raw_conditions = body.get("conditions")
    if isinstance(raw_conditions, list) and raw_conditions:
        conds = condition_service.normalize_conditions([c for c in raw_conditions if isinstance(c, dict)])
        if not conds:
            raise HTTPException(status_code=400, detail="没有可执行条件")
    else:
        parsed = condition_service.parse_query(query)
        conds = parsed["conditions"]
        if not parsed["all_recognized"]:
            message = parsed.get("message")
            if parsed.get("unrecognized"):
                message = "有部分条件暂时无法识别，请按下面的说法调整后重试。"
            elif parsed.get("conflicts"):
                message = "条件之间存在冲突，未执行筛选。"
            elif parsed.get("unsupported"):
                message = "当前版本暂不支持该类条件，未执行筛选。"
            return {**parsed, "status": "needs_input", "message": message}
    unsupported = [c for c in conds if not c.get("supported", True)]
    if unsupported:
        return {
            "ok": True, "status": "needs_input", "conditions": conds,
            "query": query, "unsupported": unsupported,
            "message": "当前版本暂不支持该类条件，未执行筛选。",
            "disclaimer": condition_service.DATA_DISCLAIMER,
        }
    result = condition_service.screen_conditions(conn, conds)
    result["query"] = query
    if parsed:
        result["parsed"] = parsed
    return result


@router.post("/condition/watchlist")
def condition_watchlist(
    body: dict[str, Any] = Body(...),
    market: str = Query("CN"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """把筛选结果批量存为自选分组。"""
    codes = [str(c) for c in (body.get("codes") or []) if str(c).strip()][:200]
    if not codes:
        raise HTTPException(status_code=400, detail="缺少标的")
    group = str(body.get("group") or "条件选股").strip()[:40] or "条件选股"
    existing = {
        str(r["code"]) for r in rules.rows(
            conn, "SELECT code FROM stocks WHERE code = ANY(?)", (codes,)
        )
    }
    kept = [c for c in codes if c in existing]
    added = 0
    for code in kept:
        cur = conn.execute(
            "INSERT INTO invest_watchlist (user_id, code, group_name, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT (user_id, code) DO NOTHING",
            (_uid(user), code, group, _now()),
        )
        added += max(0, int(getattr(cur, "rowcount", 0) or 0))
    conn.commit()
    return {"ok": True, "added": added, "group": group, "watchlist": rules.build_watchlist(conn, _uid(user), market)}


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


@router.get("/portfolio/nav")
def portfolio_nav(
    range: str = Query("1m"),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """组合净值曲线：近 1 月 / 3 月 / 1 年，与沪深 300 对比。"""
    if range not in {"1m", "3m", "1y"}:
        raise HTTPException(status_code=400, detail="range 必须是 1m/3m/1y")
    return rules.portfolio_nav(conn, _uid(user), range)


@router.post("/portfolio/targets")
def portfolio_targets(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    """设置目标配置；合计必须为 100%，全 0 表示清除目标。"""
    uid = _uid(user)
    items = body.get("targets")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="targets 必须是列表")
    existing = {r["code"] for r in conn.execute(
        "SELECT code FROM invest_portfolio WHERE user_id=?", (uid,)
    ).fetchall()}
    parsed: dict[str, float] = {}
    for item in items:
        code = str(item.get("code") or "").strip()
        if code not in existing:
            raise HTTPException(status_code=400, detail=f"持仓中没有 {code}")
        try:
            weight = float(item.get("targetWeight"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{code} 的目标权重无效")
        if weight < 0 or weight > 100:
            raise HTTPException(status_code=400, detail="目标权重必须在 0–100 之间")
        parsed[code] = weight
    total = sum(parsed.values())
    if total > 0 and abs(total - 100) > 0.1:
        raise HTTPException(status_code=400, detail=f"目标权重合计需为 100%（当前 {total:.1f}%）")
    if parsed and set(parsed) != existing:
        raise HTTPException(status_code=400, detail="需提交全部持仓的目标权重，避免合计口径不一致")
    for code, weight in parsed.items():
        conn.execute(
            "UPDATE invest_portfolio SET target_weight=? WHERE user_id=? AND code=?",
            (round(weight, 2), uid, code),
        )
    conn.commit()
    return rules.build_portfolio(conn, uid)


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
    before = rules.portfolio_rows(conn, uid)
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
        # 没有历史目标就不自动把当前权重当目标；由用户在「设定目标配置」里明确设置。
        target = float(old_targets.get(code, 0))
        conn.execute(
            "INSERT INTO invest_portfolio (user_id, code, shares, cost, weight, target_weight, industry) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, code, shares, cost, round(weight, 2), round(target, 2), industry),
        )
    after = rules.portfolio_rows(conn, uid)
    rules.record_portfolio_trades(conn, uid, before, after)
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
