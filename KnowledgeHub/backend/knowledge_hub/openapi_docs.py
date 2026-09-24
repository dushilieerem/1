# -*- coding: utf-8 -*-
"""OpenAPI 3.1 + Swagger UI（对齐同事 Research API /docs 形态）。"""
from __future__ import annotations

from typing import Any

from knowledge_hub.store import api_catalog


def openapi_spec() -> dict[str, Any]:
    cat = api_catalog()
    paths: dict[str, Any] = {}
    for ep in cat.get("endpoints") or []:
        method = str(ep.get("method") or "GET").lower()
        raw_path = str(ep.get("path") or "")
        # OpenAPI path params
        oa_path = raw_path.replace("{id}", "{id}")
        op: dict[str, Any] = {
            "summary": ep.get("summary") or ep.get("id"),
            "operationId": ep.get("id"),
            "tags": ["KnowledgeHub"],
            "responses": {
                "200": {
                    "description": "OK",
                    "content": {
                        "application/json": {
                            "example": ep.get("responseExample") or {"ok": True},
                        }
                    },
                },
                "401": {"description": "未登录"},
                "403": {"description": "非管理员"},
            },
        }
        if ep.get("status") == "planned":
            op["deprecated"] = False
            op["description"] = "（待接 / planned）" + str(ep.get("summary") or "")
        else:
            op["description"] = str(ep.get("summary") or "")

        if "{id}" in oa_path:
            op["parameters"] = [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                }
            ]

        if method in ("post", "put", "patch") and ep.get("request") is not None:
            op["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "example": ep.get("request"),
                        "schema": {"type": "object"},
                    }
                },
            }
        elif method in ("post", "put") and ep.get("request") is None:
            # ingest 等空 body
            op["requestBody"] = {
                "required": False,
                "content": {
                    "application/json": {
                        "example": {},
                        "schema": {"type": "object"},
                    }
                },
            }

        # 默认需要 admin JWT；仅显式 KH_ALLOW_ANON_ADMIN=1 时可匿名调试。
        op["security"] = [{"BearerAuth": []}]

        paths.setdefault(oa_path, {})[method] = op

    return {
        "openapi": "3.1.0",
        "info": {
            "title": cat.get("title") or "KnowledgeHub API",
            "version": cat.get("version") or "0.1.0",
            "description": (
                (cat.get("note") or "")
                + "\n\n**默认安全模式：KnowledgeHub 管理 API 需要 admin JWT。**"
                + "\n仅当服务端显式设置 `KH_ALLOW_ANON_ADMIN=1` 时，才允许匿名调试。"
            ),
        },
        "servers": [
            {"url": "/", "description": "同源 SVQuant API"},
        ],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "必填。需要 admin JWT；仅显式匿名调试模式可不填。",
                }
            }
        },
        "paths": paths,
    }


def swagger_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KnowledgeHub API · Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css"/>
  <style>
    body { margin: 0; background: #fafafa; }
    .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/api/kh/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      persistAuthorization: true,
      tryItOutEnabled: true,
      displayRequestDuration: true,
    });
  </script>
</body>
</html>
"""
