# -*- coding: utf-8 -*-
"""run_backtest 工具：结构化提交策略回测并读取真实结果。

提交与轮询复用现有 ResearchEngine 网关（services.core.re_http_gateway.forward_re，
地址来自 backend/.env 的 YG_RE_BASE），本模块不实现回测计算。

RE 契约（2026-10 实测，见 docs/archify/AC3-找到回测入口.md）：
- POST /api/backtest/strategy：strategy_code 与 strategy_id 必须且只能提供一个；
  快时同步 200+完整结果，慢时 202+run_id（GET 轮询至 succeeded/failed/cancelled）。
- 指标以 RE 实际返回为准；RE 未提供的字段一律列入 missing_metrics，不伪造。
"""
from __future__ import annotations

import os
import time
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from services.core.re_http_gateway import forward_re

_SUBMIT_PATH = "/api/backtest/strategy"
_SUBMIT_TIMEOUT_SEC = 120.0

# 展示层关注的指标全集；RE 缺哪个就进 missing_metrics
_VIEW_METRICS = (
    "total_return",
    "annual_return",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "volatility",
    "win_rate",
    "turnover",
    "ic",
    "rank_ic",
)

_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def _poll_interval_sec() -> float:
    raw = (os.environ.get("SVQUANT_AGENT_BACKTEST_POLL_SEC") or "3").strip()
    try:
        return max(0.5, min(30.0, float(raw)))
    except ValueError:
        return 3.0


def _wait_timeout_sec() -> float:
    raw = (os.environ.get("SVQUANT_AGENT_BACKTEST_TIMEOUT_SEC") or "900").strip()
    try:
        return max(30.0, min(3600.0, float(raw)))
    except ValueError:
        return 900.0


class RunBacktestInput(BaseModel):
    """run_backtest 工具输入；字段与 RE 现有契约一一对应，不新增私有字段。"""

    strategy_id: str | None = None
    strategy_code: str | None = None
    start: str
    end: str
    universe: str = "CSI300"
    benchmark: str = "CSI300"
    initial_capital: int = 1_000_000
    commission_rate: float | None = None
    stamp_tax: float | None = None
    slippage_rate: float | None = None
    include_positions: bool = False

    @field_validator("strategy_id", "strategy_code", "start", "end", "universe", "benchmark")
    @classmethod
    def _strip_nonempty(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("start", "end")
    @classmethod
    def _date_format(cls, v: Any) -> str:
        if v is None:
            raise ValueError("日期不能为空")
        s = str(v)
        try:
            time.strptime(s, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"日期须为 YYYY-MM-DD 格式，收到 {s!r}") from exc
        return s

    @model_validator(mode="after")
    def _check_xor_and_range(self) -> "RunBacktestInput":
        if bool(self.strategy_id) == bool(self.strategy_code):
            raise ValueError("strategy_code 与 strategy_id 必须且只能提供一个")
        if self.start >= self.end:
            raise ValueError(f"start（{self.start}）必须早于 end（{self.end}）")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital 必须为正数")
        return self


def build_payload(inp: RunBacktestInput) -> dict[str, Any]:
    """只传有值字段，其余交给 RE 默认。"""
    payload: dict[str, Any] = {
        "universe": inp.universe,
        "start": inp.start,
        "end": inp.end,
        "benchmark": inp.benchmark,
        "initial_capital": inp.initial_capital,
        "include_positions": inp.include_positions,
    }
    if inp.strategy_id:
        payload["strategy_id"] = inp.strategy_id
    else:
        payload["strategy_code"] = inp.strategy_code
    for key in ("commission_rate", "stamp_tax", "slippage_rate"):
        val = getattr(inp, key)
        if val is not None:
            payload[key] = val
    return payload


def _looks_like_result(data: Any) -> bool:
    return isinstance(data, dict) and (
        "metrics" in data or "equity_curve" in data
    )


def _normalize_result(
    data: dict[str, Any],
    *,
    status: str,
    mode: str,
    run_id: str | None,
    elapsed_sec: float,
) -> dict[str, Any]:
    metrics_raw = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    metrics = {k: metrics_raw[k] for k in _VIEW_METRICS if metrics_raw.get(k) is not None}
    missing = [k for k in _VIEW_METRICS if k not in metrics]
    curve = data.get("equity_curve") or []
    preview = []
    if isinstance(curve, list) and curve:
        for idx in (0, -1):
            point = curve[idx]
            if isinstance(point, dict):
                preview.append(
                    {"date": point.get("date"), "value": point.get("value")}
                )
    return {
        "ok": status == "succeeded",
        "tool": "run_backtest",
        "status": status,
        "mode": mode,
        "run_id": run_id,
        "elapsed_sec": round(elapsed_sec, 1),
        "metrics": metrics,
        "missing_metrics": missing,
        "equity_points": len(curve) if isinstance(curve, list) else 0,
        "equity_curve_preview": preview,
        "result_ref": (
            {"poll_path": f"{_SUBMIT_PATH}/{run_id}", "note": "完整结果经本站轮询接口获取"}
            if run_id
            else None
        ),
        "date_range": data.get("date_range"),
        "error": data.get("error") if data.get("error") else None,
    }


def _submit(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """提交回测。返回 (mode, data)：mode 为 sync（直接给结果）或 async（data 含 run_id）。"""
    status, _headers, data = forward_re(
        "POST", _SUBMIT_PATH, payload=payload, timeout=_SUBMIT_TIMEOUT_SEC
    )
    if not isinstance(data, dict):
        raise RuntimeError(f"RE 返回非 JSON 对象（HTTP {status}）")
    if 200 <= status < 300 and not data.get("run_id") and _looks_like_result(data):
        return "sync", data
    if status in (200, 202) and str(data.get("run_id") or "").strip():
        return "async", data
    err = data.get("error") or data.get("detail") or f"RE HTTP {status}"
    if isinstance(err, list):
        err = json_dumps_safe(err)
    raise RuntimeError(str(err))


def json_dumps_safe(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


def _poll(run_id: str, *, deadline: float) -> dict[str, Any]:
    """轮询 RE 至终态；超时返回 status=timeout（不吞真实结果）。"""
    interval = _poll_interval_sec()
    t0 = time.monotonic()
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        time.sleep(interval)
        status, _headers, data = forward_re(
            "GET", f"{_SUBMIT_PATH}/{run_id}", timeout=60
        )
        if not isinstance(data, dict):
            continue
        last = data
        st = str(data.get("status") or "").strip()
        if st in _TERMINAL_STATUSES:
            if st == "succeeded" and not _looks_like_result(data.get("result") or data):
                raise RuntimeError("回测完成但未返回结果")
            return {"status": st, "data": data, "elapsed": time.monotonic() - t0}
    return {"status": "timeout", "data": last, "elapsed": time.monotonic() - t0}


def run_backtest(params: dict[str, Any], *, user_id: int | None = None) -> dict[str, Any]:
    """工具入口：校验 → 提交 → （必要时）轮询 → 规范化结果。

    不抛业务异常：失败/超时都以 {"ok": False, "status": ..., "error": ...} 返回，
    方便 Agent 直接把错误转述给用户。
    """
    _ = user_id  # 预留：调用方（router）已用 require_user 校验身份
    try:
        inp = RunBacktestInput(**(params or {}))
    except Exception as exc:  # pydantic ValidationError 及字段类型错误
        return {
            "ok": False,
            "tool": "run_backtest",
            "status": "invalid_params",
            "error": str(exc),
        }

    t0 = time.monotonic()
    try:
        mode, data = _submit(build_payload(inp))
    except RuntimeError as exc:
        return {
            "ok": False,
            "tool": "run_backtest",
            "status": "submit_failed",
            "error": f"回测提交失败：{exc}",
        }
    except Exception as exc:  # noqa: BLE001 — 网络层异常统一转述
        return {
            "ok": False,
            "tool": "run_backtest",
            "status": "submit_failed",
            "error": f"回测提交异常：{exc}",
        }

    if mode == "sync":
        return _normalize_result(
            data, status="succeeded", mode="sync", run_id=None,
            elapsed_sec=time.monotonic() - t0,
        )

    run_id = str(data["run_id"]).strip()
    out = _poll(run_id, deadline=time.monotonic() + _wait_timeout_sec())
    if out["status"] == "timeout":
        return {
            "ok": False,
            "tool": "run_backtest",
            "status": "timeout",
            "mode": "async",
            "run_id": run_id,
            "elapsed_sec": round(out["elapsed"], 1),
            "result_ref": {"poll_path": f"{_SUBMIT_PATH}/{run_id}"},
            "error": f"轮询超时（>{_wait_timeout_sec():.0f}s），任务可能仍在执行，可稍后用 result_ref 查询",
        }
    st = out["status"]
    inner = out["data"]
    if st != "succeeded":
        st_label = {"failed": "失败", "cancelled": "已取消"}.get(st, st)
        return {
            "ok": False,
            "tool": "run_backtest",
            "status": st,
            "mode": "async",
            "run_id": run_id,
            "elapsed_sec": round(out["elapsed"], 1),
            "error": str(inner.get("error") or f"回测{st_label}"),
        }
    result = inner.get("result") if isinstance(inner.get("result"), dict) else inner
    return _normalize_result(
        result, status="succeeded", mode="async", run_id=run_id,
        elapsed_sec=out["elapsed"],
    )
