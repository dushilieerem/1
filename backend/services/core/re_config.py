# -*- coding: utf-8 -*-
"""ResearchEngine 基址：统一从 backend/.env 的 YG_RE_BASE 读取。"""
from __future__ import annotations

from urllib.parse import urlparse

from services.core.env_config import env, load_env

load_env()
RE_BASE = (env("YG_RE_BASE") or "").strip().rstrip("/")
if not RE_BASE:
    raise RuntimeError("backend/.env 未配置 YG_RE_BASE")

_parsed = urlparse(RE_BASE)
if _parsed.scheme not in {"http", "https"} or not _parsed.netloc:
    raise RuntimeError("backend/.env 的 YG_RE_BASE 必须是完整的 http(s) URL")


def re_host() -> str:
    """主机名/IP，供 NO_PROXY 直连白名单。"""
    host = urlparse(RE_BASE).hostname
    if not host:
        raise RuntimeError("YG_RE_BASE 缺少主机名")
    return host
