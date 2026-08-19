# -*- coding: utf-8 -*-
"""检测/自定义因子回测 BFF：本机直连 RE（绕过浏览器→Vite→代理链路）。"""
from __future__ import annotations

from typing import Any

from services.core.lan_http import post_json

RE_URL = "http://192.168.3.64:9527/api/backtest/factor"
# 10y CSI300 实测约 90s；给足余量，避免 urllib 先掐断
DEFAULT_TIMEOUT_SEC = 1800

_SV_ONLY_KEYS = (
    "_svquant_ui",
    "_svquantDraftFactor",
    "_svquantDraftFactors",
)


def forward_factor_backtest(
    payload: dict[str, Any],
    *,
    timeout: float | int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """转发到 RE /api/backtest/factor；去掉仅本站落库字段。"""
    body = {k: v for k, v in (payload or {}).items() if k not in _SV_ONLY_KEYS}
    # 空 factor_code 会触发 RE 走 UserFactorLibrary 空壳路径
    fc = body.get("factor_code")
    if fc is None or (isinstance(fc, str) and not fc.strip()):
        body.pop("factor_code", None)
    if body.get("library_name") is None:
        body.pop("library_name", None)
    if "factor_name" not in body or not str(body.get("factor_name") or "").strip():
        raise ValueError("factor_name 不能为空")
    if not body.get("factor_code") and not body.get("library_name"):
        raise ValueError("须提供 factor_code 或 library_name")
    try:
        return post_json(RE_URL, body, timeout=timeout)
    except RuntimeError as exc:
        raise RuntimeError(str(exc).replace("HTTP Error ", "RE HTTP ", 1)) from exc
