# -*- coding: utf-8 -*-
"""公开运行开关：注册、API 文档、H5 数据模块下线。

默认保持开发/内测行为（全部开启）；公开运行前按
`docs/产品与需求/手机端公开上线检查.md` 用环境变量收紧。
"""
from __future__ import annotations

from services.core.env_config import env

_FALSE = {"0", "false", "no", "off"}


def _on(key: str, default: str = "1") -> bool:
    return str(env(key, default) or default).strip().lower() not in _FALSE


def docs_enabled() -> bool:
    """`/docs` 与 `/openapi.json` 是否公开。公开环境建议 SVQ_DOCS_ENABLED=0。"""
    return _on("SVQ_DOCS_ENABLED", "1")


def registration_open() -> bool:
    """是否允许自助注册。关闭后只允许主站已有账号登录。"""
    return _on("AUTH_REGISTRATION_OPEN", "1")


def disabled_modules() -> set[str]:
    """H5 可临时下线的数据模块：stock,topic,news,search,home（逗号分隔）。"""
    raw = str(env("INVEST_DISABLED_MODULES", "") or "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}
