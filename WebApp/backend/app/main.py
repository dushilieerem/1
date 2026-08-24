# -*- coding: utf-8 -*-
"""SVQuant FastAPI 入口（对齐旧 api_server 路径与响应形状）。"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

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
    agent,
    ai,
    auth,
    community,
    detect,
    factor,
    health,
    kh,
    news,
    re_gateway,
    strategy,
    watchlists,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_schemas()
    yield


app = FastAPI(
    title="SVQuant",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

install_exception_handlers(app)

for mod in (
    health,
    auth,
    detect,
    strategy,
    factor,
    re_gateway,
    news,
    watchlists,
    community,
    agent,
    ai,
    kh,
):
    app.include_router(mod.router)


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
