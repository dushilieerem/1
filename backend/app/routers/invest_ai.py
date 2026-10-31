# -*- coding: utf-8 -*-
"""Invest H5 · AI 能力接口（复用 backend/ai/router 的 TaskSpec）。

合规边界：
- 前置红线：命中买卖点/目标价/收益承诺/自动交易等关键词，直接固定话术，不进模型。
- 后置扫描：模型输出再校验，去掉越界句。
- 数据 grounding：只把 SQLite 中已有的结构化数据传给模型；数据缺失时要求模型明说。
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.deps import require_user
from services.invest import rules
from services.invest.db import PGConn, invest_conn

router = APIRouter(prefix="/api/invest/ai", tags=["invest-ai"])

RED_LINE = (
    "合规红线：不提供买卖点、目标价、涨跌预测、仓位指令、收益承诺；"
    "不自动交易、不代客理财。若用户要求上述内容，改为说明风险与可查看的数据。"
)

BLOCK_MESSAGE = (
    "我们不提供买卖点、目标价、涨跌预测、仓位指令或收益承诺，也不代客理财、不自动交易。"
    "可以改为：看估值与财务数据、看组合风险、设置关注事件。"
)

# 前置：明确要求交易动作/收益承诺的表达
PRE_BLOCK = (
    "买入", "卖出", "买点", "卖点", "目标价", "会涨", "会跌", "保证收益", "稳赚",
    "必涨", "抄底", "梭哈", "满仓", "加杠杆", "自动交易", "自动下单", "代客理财",
    "帮我下单", "帮我卖出", "帮我买入",
)

# 后置：只拦截“真正给出交易结论”的表达，避免把“不提供目标价/买入建议”误判
_POST_PATTERNS = (
    # 否定句（不建议买入 / 不能保证收益）不应误伤
    re.compile(r"(?<!不)(?<!不能)(?<!无法)(建议|可以|应该|应当)\s*(买入|卖出|加仓|减仓)"),
    re.compile(r"目标价[为是]?\s*[¥￥$]?\s*\d"),
    re.compile(
        r"(?<!不)(?<!不能)(?<!无法)"
        r"(保证(?:收益|盈利|赚钱|上涨|不赔)|稳赚|必涨|必跌|会涨到|会跌到|建议满仓|建议抄底)"
    ),
)


def compliance_block(text: str) -> bool:
    q = (text or "").strip()
    return any(k in q for k in PRE_BLOCK)


def post_scan(text: str) -> str:
    raw = text or ""
    if any(p.search(raw) for p in _POST_PATTERNS):
        return BLOCK_MESSAGE
    return raw


def _card_system() -> str:
    return (
        "你是 SVQuant Invest 的数据解读助手。只使用用户输入 JSON 中的数据，不得补造任何数字或事实；"
        "数据缺失时明确写“数据缺失/待补充”。只输出 JSON，不要 markdown。"
        '结构：{"summary":"一句话结论","sections":[{"key":"...","title":"...","type":"text","body":"..."}],'
        '"disclaimer":"AI 生成 · 非投资建议","meta":{"dataSource":"..."}}。'
        "summary 与 sections 只描述事实、口径与风险，不写买卖建议、目标价、涨跌预测或收益承诺。"
        + RED_LINE
    )


def _call(task_id: str, payload: dict[str, Any], system: str | None = None) -> dict[str, Any]:
    try:
        from ai.router import available_task, run_task
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI 路由层不可用：{exc}") from exc
    if not available_task(task_id):
        raise HTTPException(status_code=503, detail="AI 未配置（缺少 LLM 网关或 Key）")
    try:
        out = run_task(
            task_id,
            messages=[
                {"role": "system", "content": system or _card_system()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{exc}") from exc
    data = out.get("data")
    if isinstance(data, dict):
        text = json.dumps(data, ensure_ascii=False)
        if post_scan(text) == BLOCK_MESSAGE:
            return {"card": {"summary": BLOCK_MESSAGE, "sections": []}, "blocked": True, "raw": out}
        return {"card": data, "raw": out}
    content = str(out.get("content") or "")
    if post_scan(content) == BLOCK_MESSAGE:
        return {"card": {"summary": BLOCK_MESSAGE, "sections": []}, "blocked": True, "raw": out}
    return {"card": {"summary": content, "sections": []}, "raw": out}


def _stock_context(conn: PGConn, code: str) -> dict[str, Any]:
    data = rules.build_stock(conn, code)
    if not data:
        raise HTTPException(status_code=404, detail="标的未收录")
    return {
        "quote": data.get("quote"),
        "technical": data.get("technical"),
        "valuation": data.get("valuation"),
        "summary": data.get("summary"),
        "report": data.get("report"),
        "risks": data.get("risks"),
        "news": [{"title": n.get("title"), "published_at": n.get("published_at"), "source": n.get("source")} for n in (data.get("news") or [])[:6]],
        "dataDate": data.get("dataDate"),
        "dataSource": data.get("dataSource"),
    }


@router.get("/status")
def status() -> dict[str, Any]:
    try:
        from ai.router import available_task
        tasks = ["invest.intent", "invest.daily", "invest.stock", "invest.portfolio", "invest.announcement", "invest.condition"]
        return {"ok": True, "enabled": {t: available_task(t) for t in tasks}}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


@router.post("/intent")
def intent(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")
    if compliance_block(q):
        return {"ok": True, "intent": "compliance_block", "answer": BLOCK_MESSAGE, "slots": {}}
    try:
        from ai.router import run_task
        out = run_task(
            "invest.intent",
            messages=[
                {
                    "role": "system",
                    "content": "只输出 JSON：{\"intent\":\"...\",\"slots\":{}}。意图枚举：brief/review/stock/portfolio/debate/compare/announcement/condition/glossary/compliance_block/chat。缺槽位放 need_clarify。",
                },
                {"role": "user", "content": q},
            ],
        )
        data = out.get("data") or {}
        return {"ok": True, **data}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"意图识别失败：{exc}") from exc


@router.post("/chat")
def chat(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")
    if compliance_block(q):
        return {"ok": True, "blocked": True, "intent": "compliance_block", "card": {"summary": BLOCK_MESSAGE, "sections": []}}
    # 先做意图路由；失败则按 chat 处理
    try:
        from ai.router import run_task
        out = run_task(
            "invest.intent",
            messages=[
                {"role": "system", "content": "只输出 JSON：{\"intent\":\"...\",\"slots\":{}}。意图枚举：brief/review/stock/portfolio/debate/compare/announcement/condition/glossary/compliance_block/chat。"},
                {"role": "user", "content": q},
            ],
        )
        routed = out.get("data") or {}
    except Exception:
        routed = {"intent": "chat", "slots": {}}
    intent_name = str(routed.get("intent") or "chat")
    if intent_name == "compliance_block":
        return {"ok": True, "blocked": True, "intent": intent_name, "card": {"summary": BLOCK_MESSAGE, "sections": []}}
    if intent_name in {"stock", "debate", "compare"}:
        slots = routed.get("slots") or {}
        code = str(slots.get("stock") or slots.get("symbol") or slots.get("company") or "").strip()
        if not code:
            return {"ok": True, "intent": intent_name, "need_clarify": ["stock"], "card": {"summary": "请补充要看的股票名称或代码。", "sections": []}}
        # 允许用户输入名称：用搜索找第一个匹配
        stock = conn.execute("SELECT code FROM stocks WHERE code=? OR name=? LIMIT 1", (code, code)).fetchone()
        if not stock:
            like = f"%{code}%"
            stock = conn.execute("SELECT code FROM stocks WHERE code LIKE ? OR name LIKE ? ORDER BY code LIMIT 1", (like, like)).fetchone()
        if not stock:
            return {"ok": True, "intent": intent_name, "card": {"summary": f"未收录标的：{code}", "sections": []}}
        return {"ok": True, "intent": intent_name, **_call("invest.stock", _stock_context(conn, str(stock[0])))}
    if intent_name in {"portfolio"}:
        data = rules.build_portfolio(conn, int(user["id"]))
        return {"ok": True, "intent": intent_name, **_call("invest.portfolio", data)}
    if intent_name in {"brief", "review"}:
        data = rules.build_home(conn, int(user["id"]))
        return {"ok": True, "intent": intent_name, **_call("invest.daily", data)}
    if intent_name == "condition":
        return {"ok": True, "intent": intent_name, **_call("invest.condition", {"query": q})}
    return {
        "ok": True,
        "intent": intent_name,
        "card": {
            "summary": "我目前可以解读个股、组合、日报和公告。请补充要看的标的或问题。",
            "sections": [],
        },
    }


@router.post("/stock/{code}")
def stock_ai(code: str, user: dict[str, Any] = Depends(require_user), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return {"ok": True, **_call("invest.stock", _stock_context(conn, code))}


@router.post("/daily")
def daily_ai(user: dict[str, Any] = Depends(require_user), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return {"ok": True, **_call("invest.daily", rules.build_home(conn, int(user["id"])))}


@router.post("/portfolio")
def portfolio_ai(user: dict[str, Any] = Depends(require_user), conn: PGConn = Depends(invest_conn)) -> dict[str, Any]:
    return {"ok": True, **_call("invest.portfolio", rules.build_portfolio(conn, int(user["id"])))}


@router.post("/announcement")
def announcement_ai(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    title = str(body.get("title") or "").strip()
    summary = str(body.get("summary") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")
    payload = {"title": title[:500], "summary": summary[:4000]}
    return {"ok": True, **_call("invest.announcement", payload)}


@router.post("/condition")
def condition_ai(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")
    if compliance_block(q):
        return {"ok": True, "blocked": True, "conditions": [], "explain": BLOCK_MESSAGE}
    return {"ok": True, **_call("invest.condition", {"query": q})}
