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

        # 内网默认免鉴权，便于 Try it out；需要强制登录时设 KH_REQUIRE_AUTH=1
        op["security"] = []

        paths.setdefault(oa_path, {})[method] = op

    return {
        "openapi": "3.1.0",
        "info": {
            "title": cat.get("title") or "KnowledgeHub API",
            "version": cat.get("version") or "0.1.0",
            "description": (
                (cat.get("note") or "")
                + "\n\n**当前内网模式：无需 Authorize 即可 Try it out。**"
                + "\n若服务端设置环境变量 `KH_REQUIRE_AUTH=1`，则需填入 admin JWT。"
            ),
        },
        "servers": [
            {"url": "http://192.168.3.32:8766", "description": "LAN API"},
            {"url": "/", "description": "同源（经 9531 代理）"},
        ],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "可选。默认免登录；强制鉴权时再填。",
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
