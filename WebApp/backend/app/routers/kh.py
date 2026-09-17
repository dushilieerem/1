# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.deps import optional_user
from knowledge_hub.http_handlers import (
    handle_kh_delete,
    handle_kh_get,
    handle_kh_post,
    handle_kh_put,
)
from knowledge_hub.openapi_docs import openapi_spec, swagger_html

router = APIRouter(tags=["knowledge-hub"])


@router.get("/api/kh/docs", response_class=HTMLResponse)
@router.get("/api/kh/docs/", response_class=HTMLResponse)
def kh_docs() -> HTMLResponse:
    return HTMLResponse(content=swagger_html(), media_type="text/html; charset=utf-8")


@router.get("/api/kh/openapi.json")
def kh_openapi() -> dict:
    return openapi_spec()


@router.post("/api/kh/model-providers/test")
async def kh_model_providers_test(
    request: Request,
    user: dict | None = Depends(optional_user),
) -> JSONResponse:
    """显式路由：模型对话探测（避免 catch-all 旧进程未热更时 404）。"""
    body: dict[str, Any] = {}
    raw = await request.body()
    if raw:
        import json

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid JSON") from None
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="invalid JSON")
        body = parsed
    return _collect_json(handle_kh_post, "/api/kh/model-providers/test", body, user=user)


def _collect_json(fn, *args, **kwargs) -> JSONResponse:
    box: dict[str, Any] = {"status": 200, "payload": {"error": "not found"}}

    def send_json(payload: dict, status: int = 200) -> None:
        box["payload"] = payload
        box["status"] = status

    handled = fn(*args, send_json=send_json, **kwargs)
    if not handled:
        raise HTTPException(status_code=404, detail="not found")
    return JSONResponse(content=box["payload"], status_code=int(box["status"]))


@router.api_route(
    "/api/kh/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def kh_catch_all(
    path: str,
    request: Request,
    user: dict | None = Depends(optional_user),
) -> Response:
    full = f"/api/kh/{path}"
    try:
        method = request.method.upper()
        if method == "GET":
            return _collect_json(handle_kh_get, full, user=user)
        body: dict[str, Any] = {}
        raw = await request.body()
        if raw:
            import json

            try:
                parsed = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="invalid JSON") from None
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="invalid JSON")
            body = parsed
        if method == "POST":
            return _collect_json(handle_kh_post, full, body, user=user)
        if method == "PUT":
            return _collect_json(handle_kh_put, full, body, user=user)
        if method == "DELETE":
            return _collect_json(handle_kh_delete, full, user=user)
        raise HTTPException(status_code=405, detail="method not allowed")
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
