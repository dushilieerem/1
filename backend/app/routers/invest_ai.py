# -*- coding: utf-8 -*-
"""Invest H5 · AI 能力接口（复用 backend/ai/router 的 TaskSpec）。

合规边界：
- 前置红线：命中买卖点/目标价/收益承诺/自动交易等关键词，直接固定话术，不进模型。
- 后置扫描：模型输出再校验，去掉越界句。
- 数据 grounding：只把 SQLite 中已有的结构化数据传给模型；数据缺失时要求模型明说。
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.deps import require_user
from services.invest import agent_prompts, agent_tools, ai_cache, glossary, rules
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
    return agent_prompts.CARD_SYSTEM


def _clip50(text: Any) -> str:
    value = str(text or "").strip()
    if len(value) <= 50:
        return value
    return value[:49].rstrip("，。；、,.; ") + "…"


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("blocked"):
        return result
    card = result.get("card") if isinstance(result.get("card"), dict) else {}
    summary = card.get("summary")
    if not summary:
        for section in card.get("sections") or []:
            if isinstance(section, dict) and section.get("body"):
                summary = section.get("body")
                break
            if isinstance(section, dict) and section.get("title"):
                summary = section.get("title")
                break
    card = {
        "summary": _clip50(summary or "数据不足，暂无法给出结论。"),
        "sections": [],
        "disclaimer": card.get("disclaimer") or "AI 生成 · 非投资建议",
        "meta": card.get("meta") or {"dataSource": "服务端结构化数据"},
    }
    return {**result, "card": card}


def _call(
    task_id: str,
    payload: dict[str, Any],
    system: str | None = None,
    *,
    user_id: int | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    base_prompt = system or (agent_prompts.AGENT_BY_ID.get(task_id) or {}).get("default_prompt") or _card_system()
    prompt = agent_prompts.resolve_prompt(user_id, task_id, base_prompt)
    cache_key = ai_cache.make_key(task_id, payload, prompt)
    if not refresh:
        cached = ai_cache.get(user_id, "call", cache_key)
        if cached:
            return {**cached, "cached": True}
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
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{exc}") from exc
    data = out.get("data")
    if isinstance(data, dict):
        text = json.dumps(data, ensure_ascii=False)
        if post_scan(text) == BLOCK_MESSAGE:
            result = {"card": {"summary": BLOCK_MESSAGE, "sections": []}, "blocked": True}
        else:
            result = {"card": data}
    else:
        content = str(out.get("content") or "")
        if post_scan(content) == BLOCK_MESSAGE:
            result = {"card": {"summary": BLOCK_MESSAGE, "sections": []}, "blocked": True}
        else:
            result = {"card": {"summary": content, "sections": []}}
    result = _compact_result(result)
    ai_cache.put(user_id, "call", cache_key, result)
    return result


_TARGET = {
    "brief": "content",
    "review": "content",
    "stock": "stock",
    "debate": "stock",
    "compare": "compare",
    "portfolio": "portfolio",
    "announcement": "content",
    "condition": "condition",
    "allocation": "portfolio",
    "sip": "portfolio",
    "glossary": "chat",
    "chat": "chat",
    "compliance_block": "guard",
}


def _meta(intent: str) -> dict[str, Any]:
    target = _TARGET.get(intent, "chat")
    hints = {
        "content": ["card"],
        "stock": ["card", "chart", "risks"],
        "compare": ["card", "compare_table"],
        "portfolio": ["card", "diagnosis"],
        "condition": ["card", "conditions"],
        "chat": ["card"],
        "guard": ["blocked"],
    }.get(target, ["card"])
    return {"target_agent": target, "card_hints": hints}


def _chart(conn: PGConn, code: str) -> dict[str, Any]:
    bars = rules.stock_bars(conn, code, 60)
    return {
        "code": code,
        "bars": [{"date": b.get("date"), "close": b.get("close")} for b in bars],
    }


_PORTFOLIO_DEEP_SYSTEM = agent_prompts.PORTFOLIO_DEEP_SYSTEM
_ALLOCATION_SYSTEM = agent_prompts.ALLOCATION_SYSTEM


def _user_context(conn: PGConn, user_id: int) -> dict[str, Any]:
    watch = rules.rows(conn, "SELECT code FROM watchlist WHERE user_id=?", (user_id,))
    profile = rules.one(conn, "SELECT level, score FROM invest_risk_profile WHERE user_id=?", (user_id,)) or {}
    return {
        "watchlist": [x.get("code") for x in watch][:20],
        "risk_profile": {"level": profile.get("level"), "score": profile.get("score")},
    }


def _extract_compare_pair(query: str) -> tuple[str, str]:
    """从「对比宁德时代和茅台」这类中文问句里兜底抽两个标的。"""
    text = (query or "").strip()
    text = re.sub(r"^(请|帮我|帮忙|麻烦)?\s*(对比|比较|看看|查一下|分析)\s*", "", text)
    text = re.sub(r"(的)?(估值|财务|基本面|风险|数据|哪个好|怎么样|如何).*$", "", text)
    parts = [
        p.strip(" 　[]【】（）()的")
        for p in re.split(r"\s*(?:和|与|跟|vs\.?|versus|、|,|，)\s*", text, flags=re.I)
        if p.strip(" 　[]【】（）()的")
    ]
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")


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
        tasks = [
            "invest.intent", "invest.daily", "invest.stock", "invest.portfolio",
            "invest.announcement", "invest.condition", "invest.compare",
            "invest.paper", "invest.quant", "invest.backtest", "invest.allocation",
        ]
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
                    "content": "只输出 JSON：{\"intent\":\"...\",\"slots\":{}}。意图枚举：brief/review/stock/portfolio/debate/compare/announcement/condition/allocation/sip/glossary/compliance_block/chat。缺槽位放 need_clarify。",
                },
                {"role": "user", "content": q},
            ],
        )
        data = out.get("data") or {}
        intent_name = str(data.get("intent") or "chat")
        return {"ok": True, **data, **_meta(intent_name)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"意图识别失败：{exc}") from exc


@router.post("/chat")
def chat(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")
    if compliance_block(q):
        return {
            "ok": True,
            "blocked": True,
            "intent": "compliance_block",
            "card": {"summary": BLOCK_MESSAGE, "sections": []},
            **_meta("compliance_block"),
        }
    # 先做意图路由；失败则按 chat 处理
    try:
        from ai.router import run_task
        out = run_task(
            "invest.intent",
            messages=[
                {"role": "system", "content": "只输出 JSON：{\"intent\":\"...\",\"slots\":{}}。意图枚举：brief/review/stock/portfolio/debate/compare/announcement/condition/allocation/sip/glossary/compliance_block/chat。"},
                {"role": "user", "content": q},
            ],
        )
        routed = out.get("data") or {}
    except Exception:
        routed = {"intent": "chat", "slots": {}}
    intent_name = str(routed.get("intent") or "chat")
    # 中文「对比 A 和 B」在模型缺槽位时仍可确定性路由。
    pair_first, pair_second = _extract_compare_pair(q)
    if pair_first and pair_second and re.search(r"对比|比较|vs\.?|versus", q, flags=re.I):
        intent_name = "compare"
        routed = {"intent": "compare", "slots": {"stock": pair_first, "stock2": pair_second}}
    if intent_name == "compliance_block":
        return {
            "ok": True,
            "blocked": True,
            "intent": intent_name,
            "card": {"summary": BLOCK_MESSAGE, "sections": []},
            **_meta(intent_name),
        }
    if intent_name in {"allocation", "sip"}:
        slots = routed.get("slots") or {}
        horizon = str(slots.get("horizon") or slots.get("period") or "").strip()
        risk_pref = str(slots.get("risk") or slots.get("risk_pref") or slots.get("risk_level") or "").strip()
        if not horizon:
            m = re.search(r"(\d+\s*年(?:以上|以内)?)", q)
            horizon = m.group(1) if m else ""
        if not risk_pref:
            for word in ("保守", "稳健", "平衡", "进取", "激进"):
                if word in q:
                    risk_pref = word
                    break
        missing = [name for name, value in (("horizon", horizon), ("risk", risk_pref)) if not value]
        if missing:
            return {
                "ok": True,
                "intent": intent_name,
                "need_clarify": missing,
                "card": {
                    "summary": "配置/定投需要先确认期限与风险偏好，例如“3 年以上、稳健型”。",
                    "sections": [],
                },
                **_meta(intent_name),
            }
        uid = int(user["id"])
        profile = rules.one(conn, "SELECT * FROM invest_risk_profile WHERE user_id=?", (uid,)) or {}
        pf = rules.build_portfolio(conn, uid)
        payload = {
            "mode": "定投" if intent_name == "sip" else "配置",
            "slots": {"horizon": horizon, "risk_pref": risk_pref, "goal": slots.get("goal")},
            "risk_profile": {
                "level": profile.get("level"),
                "score": profile.get("score"),
            },
            "portfolio": {
                "riskScore": pf.get("riskScore"),
                "riskLabel": pf.get("riskLabel"),
                "exposure": pf.get("exposure"),
                "deviation": pf.get("deviation"),
                "summary": pf.get("summary"),
            },
            "policy": {"max_single_weight": 15, "min_cash_ratio": 10},
            "data_gaps": [] if pf.get("holdings") else ["尚未导入组合，无法计算配置偏离"],
        }
        return {"ok": True, "intent": intent_name, **_meta(intent_name), **_call("invest.allocation", payload, _ALLOCATION_SYSTEM, user_id=int(user["id"]), refresh=refresh)}

    if intent_name == "glossary":
        term = glossary.find_term(q)
        if not term:
            return {
                "ok": True,
                "intent": intent_name,
                "card": {"summary": "术语库暂未收录该术语，可到「学习」页搜索或反馈补充。", "sections": [], "meta": {"dataSource": "术语库"}},
                **_meta(intent_name),
            }
        return {
            "ok": True,
            "intent": intent_name,
            "card": {
                "summary": term["definition"],
                "sections": [
                    {"title": "怎么看", "body": term["how_to"]},
                    {"title": "参考区间", "body": term["range"]},
                    {"title": "例子", "body": term["example"]},
                ],
                "disclaimer": "术语库口径 · 非投资建议",
                "meta": {"dataSource": "术语库"},
            },
            **_meta(intent_name),
        }

    if intent_name == "compare":
        slots = routed.get("slots") or {}
        first = str(slots.get("stock") or slots.get("symbol") or slots.get("company") or "").strip()
        second = str(slots.get("stock2") or slots.get("symbol2") or slots.get("company2") or "").strip()
        if not first or not second:
            parsed_first, parsed_second = _extract_compare_pair(q)
            first = first or parsed_first
            second = second or parsed_second
        if not first or not second:
            return {
                "ok": True,
                "intent": intent_name,
                "need_clarify": [x for x, v in (("stock", first), ("stock2", second)) if not v],
                "card": {"summary": "对比需要两个标的，请补充代码或名称。", "sections": []},
                **_meta(intent_name),
            }
        codes = []
        for name in (first, second):
            hit = conn.execute("SELECT code FROM stocks WHERE code=? OR name=? LIMIT 1", (name, name)).fetchone()
            if not hit:
                like = f"%{name}%"
                hit = conn.execute("SELECT code FROM stocks WHERE code LIKE ? OR name LIKE ? ORDER BY code LIMIT 1", (like, like)).fetchone()
            if not hit:
                return {"ok": True, "intent": intent_name, "card": {"summary": f"未收录标的：{name}", "sections": []}, **_meta(intent_name)}
            codes.append(str(hit["code"]))
        try:
            ctx = agent_tools.compare_context(conn, codes[0], codes[1])
        except ValueError as exc:
            return {"ok": True, "intent": intent_name, "card": {"summary": str(exc), "sections": []}, **_meta(intent_name)}
        return {"ok": True, "intent": intent_name, **_meta(intent_name), **_call("invest.compare", ctx, user_id=int(user["id"]), refresh=refresh)}

    if intent_name in {"stock", "debate"}:
        slots = routed.get("slots") or {}
        code = str(slots.get("stock") or slots.get("symbol") or slots.get("company") or "").strip()
        if not code:
            return {
                "ok": True,
                "intent": intent_name,
                "need_clarify": ["stock"],
                "card": {"summary": "请补充要看的股票名称或代码。", "sections": []},
                **_meta(intent_name),
            }
        # 允许用户输入名称：用搜索找第一个匹配
        stock = conn.execute("SELECT code FROM stocks WHERE code=? OR name=? LIMIT 1", (code, code)).fetchone()
        if not stock:
            like = f"%{code}%"
            stock = conn.execute("SELECT code FROM stocks WHERE code LIKE ? OR name LIKE ? ORDER BY code LIMIT 1", (like, like)).fetchone()
        if not stock:
            return {
                "ok": True,
                "intent": intent_name,
                "card": {"summary": f"未收录标的：{code}", "sections": []},
                **_meta(intent_name),
            }
        stock_ctx = _stock_context(conn, str(stock["code"]))
        stock_ctx["user_context"] = _user_context(conn, int(user["id"]))
        return {
            "ok": True,
            "intent": intent_name,
            "chart": _chart(conn, str(stock["code"])),
            **_meta(intent_name),
            **_call("invest.stock", stock_ctx, user_id=int(user["id"]), refresh=refresh),
        }
    if intent_name in {"portfolio"}:
        data = rules.build_portfolio(conn, int(user["id"]))
        return {"ok": True, "intent": intent_name, **_meta(intent_name), **_call("invest.portfolio", data, user_id=int(user["id"]), refresh=refresh)}
    if intent_name in {"brief", "review"}:
        data = rules.build_home(conn, int(user["id"]))
        data["portfolio"] = rules.build_portfolio(conn, int(user["id"]))
        data["user_context"] = _user_context(conn, int(user["id"]))
        return {"ok": True, "intent": intent_name, **_meta(intent_name), **_call("invest.daily", data, user_id=int(user["id"]), refresh=refresh)}
    if intent_name == "condition":
        return {"ok": True, "intent": intent_name, **_meta(intent_name), **_call("invest.condition", {"query": q}, user_id=int(user["id"]), refresh=refresh)}
    return {
        "ok": True,
        "intent": intent_name,
        "card": {
            "summary": "我目前可以解读个股、组合、日报和公告。请补充要看的标的或问题。",
            "sections": [],
        },
        **_meta(intent_name),
    }


@router.post("/deep")
def deep(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """深度模式：按真实执行顺序返回步骤；不做假动画。"""
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")
    steps: list[dict[str, Any]] = []

    steps.append({"key": "intent", "label": "理解问题与意图", "status": "done"})
    if compliance_block(q):
        steps.append({"key": "guard", "label": "合规前置检查", "status": "blocked"})
        return {
            "ok": True,
            "blocked": True,
            "intent": "compliance_block",
            "card": {"summary": BLOCK_MESSAGE, "sections": []},
            "steps": steps,
            **_meta("compliance_block"),
        }
    steps.append({"key": "guard", "label": "合规前置检查", "status": "done"})

    result = chat({"query": q}, user, conn, refresh=refresh)
    intent_name = str(result.get("intent") or "chat")
    steps[0]["detail"] = f"意图：{intent_name}"
    steps.append(
        {
            "key": "grounding",
            "label": "装载页面数据与证据",
            "status": "done",
            "detail": "已使用个股/组合/日报/术语库的结构化数据",
        }
    )
    steps.append(
        {
            "key": "generate",
            "label": "生成结论与卡片",
            "status": "done" if result.get("card") else "failed",
            "detail": "已生成结构化卡片" if result.get("card") else "未生成卡片",
        }
    )
    steps.append(
        {
            "key": "post_guard",
            "label": "合规后置扫描",
            "status": "blocked" if result.get("blocked") else "done",
            "detail": "命中红线，已替换为固定话术" if result.get("blocked") else "未命中红线",
        }
    )
    evidence = []
    for section in (result.get("card") or {}).get("sections") or []:
        if section.get("body"):
            evidence.append({"title": section.get("title") or "依据", "detail": section.get("body")[:200]})
    return {**result, "steps": steps, "evidence": evidence}


@router.post("/stock/{code}")
def stock_ai(
    code: str,
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    return {"ok": True, **_call("invest.stock", _stock_context(conn, code), user_id=int(user["id"]), refresh=refresh)}


@router.post("/daily")
def daily_ai(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    data = rules.build_home(conn, int(user["id"]))
    data["portfolio"] = rules.build_portfolio(conn, int(user["id"]))
    data["user_context"] = _user_context(conn, int(user["id"]))
    return {"ok": True, **_call("invest.daily", data, user_id=int(user["id"]), refresh=refresh)}


@router.post("/portfolio")
def portfolio_ai(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    return {"ok": True, **_call("invest.portfolio", rules.build_portfolio(conn, int(user["id"])), user_id=int(user["id"]), refresh=refresh)}


@router.post("/portfolio/deep")
def portfolio_deep_ai(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """组合体检的 AI 深度解读：自动生成，50 字结论，可重新生成。"""
    data = rules.build_portfolio(conn, int(user["id"]))
    return {"ok": True, **_call("invest.portfolio", data, system=_PORTFOLIO_DEEP_SYSTEM, user_id=int(user["id"]), refresh=refresh)}


@router.post("/announcement")
def announcement_ai(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    title = str(body.get("title") or "").strip()
    summary = str(body.get("summary") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")
    payload = {"title": title[:500], "summary": summary[:4000]}
    return {"ok": True, **_call("invest.announcement", payload, user_id=int(user["id"]), refresh=refresh)}


@router.post("/condition")
def condition_ai(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")
    if compliance_block(q):
        return {"ok": True, "blocked": True, "conditions": [], "explain": BLOCK_MESSAGE}
    return {"ok": True, **_call("invest.condition", {"query": q}, user_id=int(user["id"]), refresh=refresh)}


@router.post("/compare")
def compare(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    a = str(body.get("a") or body.get("code_a") or "").strip()
    b = str(body.get("b") or body.get("code_b") or "").strip()
    if not a or not b:
        raise HTTPException(status_code=400, detail="需要两个标的代码")
    try:
        ctx = agent_tools.compare_context(conn, a, b)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "compare": ctx, **_call("invest.compare", ctx, user_id=int(user["id"]), refresh=refresh)}


@router.post("/paper")
def paper(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    try:
        account_id = int(body.get("account_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="account_id 无效") from None
    try:
        ctx = agent_tools.paper_review(int(user["id"]), account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "paper": ctx, **_call("invest.paper", ctx, user_id=int(user["id"]), refresh=refresh)}


@router.post("/quant")
def quant(
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    ctx = agent_tools.quant_context(conn, int(user["id"]))
    return {"ok": True, "quant": ctx, **_call("invest.quant", ctx, user_id=int(user["id"]), refresh=refresh)}


_BACKTEST_SYSTEM = agent_prompts.BACKTEST_SYSTEM


@router.post("/backtest")
def backtest_ai(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    payload = {
        "name": str(body.get("name") or "")[:120],
        "universe": str(body.get("universe") or "")[:40],
        "period": body.get("period"),
        "metrics": body.get("metrics") if isinstance(body.get("metrics"), dict) else {},
        "equity_summary": body.get("equity_summary") if isinstance(body.get("equity_summary"), dict) else {},
        "trades": body.get("trades") if isinstance(body.get("trades"), (int, float)) else None,
        "note": "历史回测结果，非真实收益。",
    }
    return {"ok": True, **_call("invest.backtest", payload, _BACKTEST_SYSTEM, user_id=int(user["id"]), refresh=refresh)}


@router.post("/voice")
def voice(
    body: dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(require_user),
    conn: PGConn = Depends(invest_conn),
) -> dict[str, Any]:
    b64 = str(body.get("audio_base64") or "").strip()
    if not b64:
        raise HTTPException(status_code=400, detail="缺少 audio_base64")
    if "," in b64 and b64.lower().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        audio = base64.b64decode(b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 无效") from None
    mime = str(body.get("mime") or "audio/webm").strip() or "audio/webm"
    ext = "webm"
    if "ogg" in mime:
        ext = "ogg"
    elif any(x in mime for x in ("mp4", "m4a", "aac")):
        ext = "m4a"
    elif any(x in mime for x in ("mpeg", "mp3")):
        ext = "mp3"
    elif "wav" in mime:
        ext = "wav"
    from ai.gateway.speech_transcribe import SpeechError, transcribe_bytes

    try:
        out = transcribe_bytes(audio, filename=f"speech.{ext}", content_type=mime)
    except SpeechError as exc:
        status = 503 if getattr(exc, "http_status", 400) == 503 else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    corrected = agent_tools.correct_entities(conn, str(out.get("text") or ""))
    return {"ok": True, "asr": out, "corrected": corrected}
