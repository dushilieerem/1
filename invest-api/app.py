"""Invest H5 demo API.

Run:
  conda run -n svquant python -m uvicorn app:app --host 0.0.0.0 --port 8767
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

# 复用 backend/ai/router（L2 任务路由层）；只在函数内延迟导入，避免启动强依赖。
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if _BACKEND_DIR.is_dir() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import auth
import rules
from deps import get_db, optional_user, now_ts, require_user
from seed import DB_PATH, seed

if os.getenv("INVEST_ENV") == "production" and not os.getenv("INVEST_JWT_SECRET"):
    raise RuntimeError("生产环境必须设置 INVEST_JWT_SECRET（至少 32 位随机值）")

seed(force=os.getenv("INVEST_RESEED", "0") == "1")

app = FastAPI(
    title="SVQuant Invest API",
    version="0.1.0",
    docs_url=None if os.getenv("INVEST_ENV") == "production" else "/docs",
    redoc_url=None if os.getenv("INVEST_ENV") == "production" else "/redoc",
    openapi_url=None if os.getenv("INVEST_ENV") == "production" else "/openapi.json",
)
origins = [x.strip() for x in (os.getenv("INVEST_CORS_ORIGINS") or
                               "http://127.0.0.1:9540,http://localhost:9540").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

_LOGIN_HITS: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_and_login_limit(request: Request, call_next):
    # Small in-process login guard for the demo.  Production should use
    # Nginx/WAF/Redis-backed rate limiting and CAPTCHA.
    if request.url.path in ("/api/auth/login", "/api/auth/register", "/api/auth/sso") and request.method == "POST":
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown")
        now = time.time()
        hits = _LOGIN_HITS[ip]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= 20:
            return JSONResponse(status_code=429, content={"detail": "操作过于频繁，请稍后再试"})
        hits.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.url.path.startswith("/api/auth") or request.url.path.startswith("/api/invest/account"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


def audit_event(conn: sqlite3.Connection, request: Request, action: str,
                username: str | None = None, detail: str | None = None) -> None:
    """Best-effort auth audit; never let logging break login/register."""
    try:
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown")
        conn.execute("INSERT INTO auth_events (ts, action, username, ip, detail) VALUES (?,?,?,?,?)",
                     (time.strftime("%Y-%m-%d %H:%M:%S"), action, username, ip, detail))
        conn.commit()
    except Exception:
        pass


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


@app.get("/api/health")
def health(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    try:
        meta = rules.build_meta(conn)
        data_date = meta.get("dataDate")
    except Exception:
        data_date = None
    return {"ok": True, "service": "invest-api", "dataDate": data_date}


@app.post("/api/auth/login")
def login(request: Request, body: dict[str, Any] = Body(...),
          conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    username = str(body.get("username") or "")
    try:
        out = auth.login(username, str(body.get("password") or ""))
        audit_event(conn, request, "login", out["user"].get("username"), f"mode={out.get('mode')}")
        return out
    except ValueError as exc:
        audit_event(conn, request, "login_failed", username, str(exc)[:160])
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/register")
def register(request: Request, body: dict[str, Any] = Body(...),
             conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    username = str(body.get("username") or "")
    try:
        out = auth.register(
            username,
            str(body.get("password") or ""),
            str(body["email"]) if body.get("email") else None,
            str(body["display_name"]) if body.get("display_name") else None,
        )
        audit_event(conn, request, "register", out["user"].get("username"), f"mode={out.get('mode')}")
        return out
    except ValueError as exc:
        audit_event(conn, request, "register_failed", username, str(exc)[:160])
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/sso")
def sso(request: Request, body: dict[str, Any] = Body(...),
        conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    try:
        out = auth.sso(str(body.get("token") or ""))
        audit_event(conn, request, "sso", out["user"].get("username"), "main-site token exchange")
        return out
    except ValueError as exc:
        audit_event(conn, request, "sso_failed", None, str(exc)[:160])
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {"user": user, "mode": "demo" if user.get("username") == "demo" else "svquant"}


@app.get("/api/invest/meta")
def meta(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_meta(conn)


@app.get("/api/invest/data-quality")
def data_quality(user: dict[str, Any] = Depends(require_user),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_data_quality(conn)


@app.get("/api/invest/glossary")
def glossary() -> dict[str, Any]:
    return {"items": GLOSSARY}


@app.get("/api/invest/home")
def home(user: dict[str, Any] = Depends(require_user), conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_home(conn, int(user["id"]))


@app.get("/api/invest/topic/{topic_id}")
def topic(topic_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    data = rules.build_topic(conn, topic_id)
    if not data:
        raise HTTPException(status_code=404, detail="主题不存在")
    return data


@app.get("/api/invest/stock/{code}")
def stock(code: str, period: str = Query("daily"), conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    if period not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="period 必须是 daily/weekly/monthly")
    data = rules.build_stock(conn, code, period)
    if not data:
        raise HTTPException(status_code=404, detail="标的未收录")
    return data


@app.get("/api/invest/search")
def search(q: str = Query(""), conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_search(conn, q)


@app.get("/api/invest/news")
def news(kind: str | None = Query(None), conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_news(conn, kind)


@app.get("/api/invest/watchlist")
def watchlist(user: dict[str, Any] = Depends(require_user), conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_watchlist(conn, int(user["id"]))


@app.post("/api/invest/watchlist")
def add_watchlist(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user),
                  conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    code = str(body.get("code") or "")
    if not conn.execute("SELECT 1 FROM stocks WHERE code=?", (code,)).fetchone():
        raise HTTPException(status_code=404, detail="标的未收录")
    conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?,?,?)",
                 (int(user["id"]), code, str(body.get("group") or "默认"), now_ts()))
    conn.commit()
    return rules.build_watchlist(conn, int(user["id"]))


@app.delete("/api/invest/watchlist/{code}")
def remove_watchlist(code: str, user: dict[str, Any] = Depends(require_user),
                     conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    conn.execute("DELETE FROM watchlist WHERE user_id=? AND code=?", (int(user["id"]), code))
    conn.commit()
    return rules.build_watchlist(conn, int(user["id"]))


@app.post("/api/invest/events")
def add_event(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user),
              conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    code = str(body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少标的")
    conn.execute("INSERT INTO events (user_id, code, type, condition, status, created_at) VALUES (?,?,?,?,?,?)",
                 (int(user["id"]), code, str(body.get("type") or "价格"),
                  str(body.get("condition") or "收盘后检查"), "active", now_ts()))
    conn.commit()
    return rules.build_watchlist(conn, int(user["id"]))


@app.post("/api/invest/risk-profile")
def risk_profile(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    level = str(body.get("level") or "稳健型")
    score = int(body.get("score") or 62)
    answers = json.dumps(body.get("answers") or {}, ensure_ascii=False)
    conn.execute("INSERT OR REPLACE INTO risk_profiles VALUES (?,?,?,?,?)",
                 (int(user["id"]), level, score, answers, now_ts()))
    conn.commit()
    return {"level": level, "score": score}


@app.get("/api/invest/risk-profile")
def get_risk_profile(user: dict[str, Any] = Depends(require_user),
                     conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM risk_profiles WHERE user_id=?", (int(user["id"]),)).fetchone()
    if not row:
        return {"level": None, "score": None}
    return {"level": row["level"], "score": row["score"],
            "answers": json.loads(row["answers"] or "{}"), "updatedAt": row["updated_at"]}


@app.get("/api/invest/portfolio")
def portfolio(user: dict[str, Any] = Depends(require_user),
              conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    return rules.build_portfolio(conn, int(user["id"]))


@app.post("/api/invest/portfolio/import")
def import_portfolio(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user),
                     conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    uid = int(user["id"])
    items = body.get("holdings")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="holdings 不能为空")
    old_targets = {r["code"]: r["target_weight"] for r in
                   conn.execute("SELECT code, target_weight FROM portfolio WHERE user_id=?", (uid,)).fetchall()}
    prepared = []
    total = 0.0
    for item in items:
        code = str(item.get("code") or "").strip()
        shares = float(item.get("shares") or 0)
        cost = float(item.get("cost") or 0)
        if code == "CASH":
            value = shares
            industry = "现金"
            name = "现金"
        else:
            s = conn.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
            if not s:
                raise HTTPException(status_code=400, detail=f"标的未收录：{code}")
            value = shares * float(s["price"])
            industry = s["industry"]
            name = s["name"]
        total += value
        prepared.append((code, shares, cost or (value / shares if shares else 1), value, industry))
    if total <= 0:
        raise HTTPException(status_code=400, detail="持仓市值必须大于 0")
    conn.execute("DELETE FROM portfolio WHERE user_id=?", (uid,))
    for code, shares, cost, value, industry in prepared:
        weight = value / total * 100
        target = float(old_targets.get(code, weight))
        conn.execute("INSERT INTO portfolio VALUES (?,?,?,?,?,?,?)",
                     (uid, code, shares, cost, round(weight, 2), round(target, 2), industry))
    conn.commit()
    return rules.build_portfolio(conn, uid)


@app.get("/api/invest/account/export")
def export_account(request: Request, user: dict[str, Any] = Depends(require_user),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    uid = int(user["id"])
    watch = [dict(r) for r in conn.execute("SELECT * FROM watchlist WHERE user_id=?", (uid,)).fetchall()]
    events = [dict(r) for r in conn.execute("SELECT * FROM events WHERE user_id=?", (uid,)).fetchall()]
    logs = [dict(r) for r in conn.execute("SELECT * FROM event_logs WHERE user_id=?", (uid,)).fetchall()]
    portfolio = [dict(r) for r in conn.execute("SELECT * FROM portfolio WHERE user_id=?", (uid,)).fetchall()]
    risk = conn.execute("SELECT * FROM risk_profiles WHERE user_id=?", (uid,)).fetchone()
    audit = [{"ts": r["ts"], "action": r["action"], "detail": r["detail"]}
             for r in conn.execute("SELECT ts, action, detail FROM auth_events WHERE username=? ORDER BY id DESC LIMIT 100",
                                   (user.get("username"),)).fetchall()]
    audit_event(conn, request, "export", user.get("username"), "account export")
    return {
        "generatedAt": rules.build_meta(conn)["updatedAt"],
        "note": "仅导出 Invest 本地数据；SVQuant 账号本身需在主站处理。",
        "user": user,
        "watchlist": watch,
        "events": events,
        "eventLogs": logs,
        "portfolio": portfolio,
        "riskProfile": dict(risk) if risk else None,
        "authEvents": audit,
    }


@app.delete("/api/invest/account/data")
def delete_invest_data(request: Request, user: dict[str, Any] = Depends(require_user),
                       conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    uid = int(user["id"])
    for table in ("watchlist", "events", "event_logs", "portfolio", "risk_profiles"):
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
    conn.commit()
    audit_event(conn, request, "delete_invest_data", user.get("username"), "local Invest data only")
    return {"ok": True, "deleted": ["watchlist", "events", "event_logs", "portfolio", "risk_profile"]}


# AI 能力接口（复用 backend/ai/router 的 TaskSpec）。放在文件末尾导入，避免与 app 依赖循环。
try:
    from ai_endpoints import router as invest_ai_router

    app.include_router(invest_ai_router)
except Exception as _exc:  # 无 LLM 配置时仍允许 Invest 主流程运行
    print(f"[invest-api] AI 能力未加载: {_exc}")
