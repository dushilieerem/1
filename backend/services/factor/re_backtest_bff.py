# -*- coding: utf-8 -*-
"""检测/自定义因子回测 BFF：本机直连 RE（绕过浏览器→Vite→代理链路）。

对齐 ResearchEngine 异步契约：POST 提交拿 run_id，再轮询 GET，直至终态。
"""
from __future__ import annotations

import time
from typing import Any

from services.core.lan_http import get_json, post_json_with_status
from services.core.re_config import RE_BASE

RE_URL = f"{RE_BASE}/api/backtest/factor"
# 10y CSI300 实测约 90s；给足余量，避免 urllib 先掐断
DEFAULT_TIMEOUT_SEC = 1800

_SV_ONLY_KEYS = (
    "_svquant_ui",
    "_svquantDraftFactor",
    "_svquantDraftFactors",
)


def _looks_like_result(data: Any) -> bool:
    return isinstance(data, dict) and (
        "metrics" in data
        or "equity_curve" in data
        or "factor_analysis" in data
        or "date_range" in data
    )


def _poll_factor_run(run_id: str, *, timeout: float | int) -> dict[str, Any]:
    url = f"{RE_BASE}/api/backtest/factor/{run_id}"
    deadline = time.monotonic() + float(timeout)
    delay = 1.0
    while time.monotonic() < deadline:
        time.sleep(delay)
        try:
            task = get_json(url, timeout=60)
        except RuntimeError as exc:
            msg = str(exc)
            if "HTTP Error 404" in msg:
                raise RuntimeError("检测任务已过期或不存在") from exc
            raise
        if not isinstance(task, dict):
            raise RuntimeError("轮询返回非 JSON 对象")
        status = str(task.get("status") or "")
        if status == "succeeded":
            result = task.get("result")
            if not _looks_like_result(result):
                raise RuntimeError("检测已完成但未返回结果")
            return result  # type: ignore[return-value]
        if status == "failed":
            raise RuntimeError(str(task.get("error") or "检测失败"))
        if status == "cancelled":
            raise RuntimeError("检测已取消")
        delay = 2.0 if delay < 1.5 else 3.0
    raise RuntimeError("检测超时")


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
        # 提交本身应很快；长等待在轮询里
        status, data = post_json_with_status(RE_URL, body, timeout=120)
    except RuntimeError as exc:
        raise RuntimeError(str(exc).replace("HTTP Error ", "RE HTTP ", 1)) from exc

    if not isinstance(data, dict):
        raise RuntimeError("RE 提交返回非 JSON 对象")

    # 兼容旧同步：直接回报表
    if status == 200 and _looks_like_result(data) and not data.get("run_id"):
        return data

    run_id = str(data.get("run_id") or "").strip()
    if status in (200, 202) and run_id:
        return _poll_factor_run(run_id, timeout=timeout)

    if status == 200 and _looks_like_result(data):
        return data

    err = data.get("error") or data.get("detail") or f"RE HTTP {status}"
    raise RuntimeError(str(err).replace("HTTP Error ", "RE HTTP ", 1))
