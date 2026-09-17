# -*- coding: utf-8 -*-
"""ResearchEngine 基址：只认 YG_RE_BASE（backend/.env 或环境变量）。"""
from __future__ import annotations

from urllib.parse import urlparse

from services.core.env_config import env, load_env

# 同事 RE 默认；换机只改 .env 的 YG_RE_BASE，勿再散落硬编码
DEFAULT_YG_RE_BASE = "http://192.168.250.10:9527"

load_env()
RE_BASE = (env("YG_RE_BASE") or DEFAULT_YG_RE_BASE).rstrip("/")


def re_host() -> str:
    """主机名/IP，供 NO_PROXY 直连白名单。"""
    host = urlparse(RE_BASE).hostname
    return host or "192.168.250.10"
