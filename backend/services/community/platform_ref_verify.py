# -*- coding: utf-8 -*-
"""P1-A05：社区 platform_ref 服务端回查。

客户端提交的指标引用不再直接视为 verified：
- 带 ref_id（检测/策略运行 id）时回查该用户自己的运行记录，比对指标；
- 无 ref_id 或回查不到 → metrics_verified=False（标注"未通过服务端校验"）；
- 比对不一致 → metrics_verified=False，并给出差异说明。

只读，不改帖子；异常一律降级为未验证，不阻塞发帖。
"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn

_TOL = 0.02  # 展示值四舍五入后允许 2% 相对误差


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return True  # 引用没给该指标，不做无依据的否定
    scale = max(abs(a), abs(b), 1e-6)
    return abs(a - b) / scale <= _TOL or abs(a - b) <= 0.0005


def _load_run(user_id: int, source: str, ref_id: str) -> dict[str, Any] | None:
    if source == "factor_detect":
        with get_conn() as conn:
            row = conn.execute(
                "SELECT result, request FROM detect_runs WHERE user_id = %s AND id = %s",
                (int(user_id), ref_id),
            ).fetchone()
        return dict(row) if row else None
    if source == "strategy_report":
        with get_conn() as conn:
            row = conn.execute(
                "SELECT result, request FROM strategy_runs WHERE user_id = %s AND id = %s",
                (int(user_id), ref_id),
            ).fetchone()
        return dict(row) if row else None
    return None


def _actual_metrics(run: dict[str, Any], source: str) -> dict[str, float | None]:
    result = run.get("result") or {}
    if isinstance(result, str):
        import json

        result = json.loads(result)
    metrics = result.get("metrics") if isinstance(result, dict) else None
    metrics = metrics if isinstance(metrics, dict) else {}
    out = {
        "annual_return": _num(metrics.get("annual_return")),
        "sharpe": _num(metrics.get("sharpe")),
        "max_drawdown": _num(metrics.get("max_drawdown")),
        "win_rate": _num(metrics.get("win_rate")),
        "total_return": _num(metrics.get("total_return") or metrics.get("cumulative_return")),
        "excess_return": _num(result.get("excess_return")),
        "rank_ic": _num(metrics.get("rank_ic") or metrics.get("ic")),
    }
    if source == "factor_detect":
        out["rank_ic"] = _num(metrics.get("rank_ic") or metrics.get("ic"))
    return out


def verify_platform_ref(
    user_id: int, platform_ref: Any
) -> dict[str, Any] | None:
    """返回带 metrics_verified / verify_note 的引用副本。"""
    if not isinstance(platform_ref, dict):
        return platform_ref
    ref = dict(platform_ref)
    source = str(ref.get("source") or "").strip()
    ref_id = str(ref.get("ref_id") or ref.get("refId") or "").strip()
    ref["metrics_verified"] = False
    if source not in ("factor_detect", "strategy_report"):
        # 其它来源（手工填写等）没有可回查的运行记录
        ref["verify_note"] = "该来源不支持服务端回查"
        return ref
    if not ref_id:
        ref["verify_note"] = "引用缺少运行 id，无法回查"
        return ref
    try:
        run = _load_run(int(user_id), source, ref_id)
    except Exception as exc:  # noqa: BLE001
        ref["verify_note"] = f"回查失败：{exc}"
        return ref
    if run is None:
        ref["verify_note"] = "未找到对应用户的运行记录"
        return ref

    actual = _actual_metrics(run, source)
    claimed = ref.get("metrics") if isinstance(ref.get("metrics"), dict) else {}
    diffs: list[str] = []
    for key, claimed_value in claimed.items():
        cv = _num(claimed_value)
        if cv is None:
            continue
        if key not in actual:
            continue
        if not _close(cv, actual[key]):
            diffs.append(f"{key}: 引用 {cv} ≠ 记录 {actual[key]}")
    if diffs:
        ref["verify_note"] = "指标与运行记录不一致：" + "；".join(diffs[:4])
        return ref

    ref["metrics_verified"] = True
    ref["verify_note"] = "已回查运行记录"
    return ref
