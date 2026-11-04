# -*- coding: utf-8 -*-
"""SVQuant FastAPI 入口（对齐旧 api_server 路径与响应形状）。"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

# backend root + KnowledgeHub/backend（knowledge_hub 包）
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_KH_BACKEND = _BACKEND_ROOT.parent / "KnowledgeHub" / "backend"
for _p in (_BACKEND_ROOT, _KH_BACKEND):
    s = str(_p)
    if _p.is_dir() and s not in sys.path:
        sys.path.insert(0, s)

from app.bootstrap import bootstrap_schemas  # noqa: E402
from app.errors import install_exception_handlers  # noqa: E402
from app.routers import (  # noqa: E402
    admin_logs,
    admin_users,
    support,
    research_assets,
    billing,
    fund,
    agent,
    ai,
    ai_backtest,
    ai_factor_generation,
    ai_strategy_generation,
    ai_transcription,
    auth,
    community,
    detect,
    factor,
    health,
    inst,
    inst_quant,
    inst_workflow,
    invest,
    invest_ai,
    kh,
    market_data,
    metrics,
    news,
    paper,
    re_gateway,
    strategy,
    watchlists,
)
from services.core.env_config import env  # noqa: E402
from services.core.public_switches import docs_enabled  # noqa: E402
from services.core.rate_limit import enforce_rate_limit_key  # noqa: E402


def _configure_threadpool() -> None:
    try:
        import anyio.to_thread

        raw = env("SVQUANT_THREADPOOL_TOKENS", "80") or "80"
        tokens = max(40, min(200, int(raw)))
        anyio.to_thread.current_default_thread_limiter().total_tokens = tokens
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_threadpool()
    bootstrap_schemas()
    yield


def _cors_origins() -> list[str]:
    # 允许跨域的前端来源白名单；逗号分隔配置在 CORS_ORIGINS。
    # 开发默认仅允许本机前端（前端经 Vite 代理访问 /api，本身同源，此白名单主要约束直连 API 的场景）。
    raw = env("CORS_ORIGINS", "") or ""
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if "*" in origins:
        return ["*"]
    return origins or ["http://127.0.0.1:9530", "http://localhost:9530"]


app = FastAPI(
    title="SVQuant",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled() else None,
    redoc_url=None,
    openapi_url="/openapi.json" if docs_enabled() else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

install_exception_handlers(app)


def _csp_policy() -> str:
    return (
        env(
            "CONTENT_SECURITY_POLICY",
            "default-src 'self'; img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "connect-src 'self' https: http: ws: wss:; frame-ancestors 'self';",
        )
        or ""
    ).strip()


_WRITE_SKIP_PREFIXES = ("/api/auth/", "/api/health")


@app.middleware("http")
async def api_v1_alias(request: Request, call_next):
    """P1-O01：/api/v1/* 作为 /api/* 的兼容别名。"""
    path = request.url.path
    if path.startswith("/api/v1/"):
        request.scope["path"] = path[len("/api/v1"):]
    return await call_next(request)


@app.middleware("http")
async def write_rate_limit(request: Request, call_next):
    """P0-06：所有非 GET API 默认按用户/IP 限流（单 worker；多实例见 D-06）。"""
    method = request.method.upper()
    path = request.url.path
    if method not in {"POST", "PUT", "PATCH", "DELETE"} or not path.startswith("/api/"):
        return await call_next(request)
    if any(path.startswith(prefix) for prefix in _WRITE_SKIP_PREFIXES):
        return await call_next(request)
    identity = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        try:
            from services.auth.auth_store import decode_token

            identity = f"u:{decode_token(auth.split(None, 1)[1].strip()).get('sub')}"
        except Exception:
            identity = None
    if not identity:
        xf = request.headers.get("x-forwarded-for") or ""
        identity = f"ip:{(xf.split(',')[0].strip() if xf else (request.client.host if request.client else 'unknown'))}"
    try:
        limit = max(1, int(env("WRITE_RATE_LIMIT", "120") or "120"))
    except (TypeError, ValueError):
        limit = 120
    try:
        enforce_rate_limit_key(identity, scope="write", limit=limit, window_sec=60)
    except HTTPException as exc:
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
            headers=exc.headers or {"Retry-After": "60"},
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    csp = _csp_policy()
    if csp:
        response.headers.setdefault("Content-Security-Policy", csp)
    return response

for mod in (
    health,
    auth,
    inst,
    inst_quant,
    inst_workflow,
    invest,
    invest_ai,
    detect,
    strategy,
    paper,
    factor,
    re_gateway,
    news,
    watchlists,
    community,
    agent,
    ai,
    ai_backtest,
    ai_factor_generation,
    ai_strategy_generation,
    ai_transcription,
    kh,
    market_data,
    metrics,
    admin_logs,
    admin_users,
    support,
    research_assets,
    billing,
    fund,
):
    app.include_router(mod.router)


app.include_router(support.admin_router)
app.include_router(billing.admin_router)

_AUDIT_SKIP_PREFIXES = (
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/health",
    "/favicon",
)


def _client_ip(request: Request) -> str | None:
    xf = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def _should_audit(method: str, path: str, status: int) -> bool:
    if method == "OPTIONS":
        return False
    if not path.startswith("/api/"):
        return False
    for pref in _AUDIT_SKIP_PREFIXES:
        if path.startswith(pref):
            return False
    # 登录/注册由路由显式写业务审计，避免与中间件重复
    if path in (
        "/api/auth/login",
        "/api/auth/register",
        "/api/inst/auth/login",
    ):
        return False
    # 管理页轮询自身不记，避免刷屏
    if method == "GET" and path.startswith("/api/admin/logs"):
        return False
    # 成功只读请求默认不记；写操作与错误必记
    if method == "GET" and status < 400:
        return False
    return True


@app.middleware("http")
async def audit_access_log(request: Request, call_next) -> Response:
    """API 写操作与错误落入审计表，供管理员页面查看。"""
    import time

    t0 = time.perf_counter()
    response: Response | None = None
    err: Exception | None = None
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        err = exc
        raise
    finally:
        try:
            path = request.url.path or ""
            method = (request.method or "GET").upper()
            status = (
                int(response.status_code)
                if response is not None
                else (500 if err else 0)
            )
            if _should_audit(method, path, status):
                from services.auth.auth_store import user_from_authorization
                from services.core.audit_log_store import infer_action, write_audit
                import uuid

                rid = (
                    request.headers.get("x-request-id")
                    or request.headers.get("X-Request-Id")
                    or uuid.uuid4().hex[:16]
                )
                if response is not None and "x-request-id" not in {
                    k.lower() for k in response.headers.keys()
                }:
                    response.headers["X-Request-Id"] = rid

                auth = request.headers.get("authorization") or request.headers.get(
                    "Authorization"
                )
                user = user_from_authorization(auth) if auth else None
                ms = int((time.perf_counter() - t0) * 1000)
                action = infer_action(method, path)
                detail = None
                if status >= 400:
                    detail = f"HTTP {status}"
                # 无有效登录用户时由 write_audit 落「游客」
                write_audit(
                    action=action,
                    user_id=int(user["id"]) if user and user.get("id") is not None else None,
                    username=str(user.get("username") or "") if user else None,
                    role=str(user.get("role") or "") if user else None,
                    method=method,
                    path=path,
                    resource=path,
                    status_code=status or None,
                    duration_ms=ms,
                    ip=_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                    detail=detail,
                    request_id=rid,
                )
        except Exception:
            pass


@app.middleware("http")
async def cache_control_headers(request: Request, call_next) -> Response:
    """对齐旧 _send_json 的防缓存头（已显式设置的响应不覆盖）。"""
    response = await call_next(request)
    lower = {k.lower() for k in response.headers.keys()}
    if "cache-control" not in lower:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization"
    return response
