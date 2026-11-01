# -*- coding: utf-8 -*-
"""执行前校验与异常分类（C3：纸面执行闭环）。

纯函数：输入授权/组合/行情状态，输出检查项与阻断原因。
真实券商/QMT 适配仍需外部环境；这里覆盖不依赖券商的校验、异常登记与对账。
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _check(key: str, label: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"key": key, "label": label, "ok": bool(ok), "detail": detail}


def evaluate(
    *,
    auth_status: str,
    valid_until: str | None,
    direction: str,
    price: float,
    price_low: float | None,
    price_high: float | None,
    cash: float,
    cost: float,
    qty: int,
    position_qty: float,
    suspended: bool = False,
    is_st: bool = False,
    duplicate_order: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    now = today or date.today()
    checks: list[dict[str, Any]] = [
        _check("authorization", "授权有效", auth_status == "qualified", f"状态：{auth_status}"),
        _check(
            "validity",
            "授权未过期",
            not valid_until or str(valid_until)[:10] >= now.isoformat(),
            f"有效期：{valid_until or '—'}",
        ),
        _check("price", "成交价有效", price > 0, f"价格：{price}"),
        _check(
            "price_range",
            "成交价在授权区间内",
            (price_low is None or price >= float(price_low))
            and (price_high is None or price <= float(price_high)),
            f"{price_low} - {price_high}（成交 {price}）",
        ),
        _check("lot", "数量形成一手", qty > 0, f"数量：{qty}"),
        _check(
            "tradable",
            "标的可交易（非停牌/ST）",
            not suspended and not is_st,
            "停牌" if suspended else ("ST" if is_st else "正常"),
        ),
    ]
    if direction == "buy":
        checks.append(_check("cash", "现金充足", cost <= cash, f"需要 {cost:.2f} / 可用 {cash:.2f}"))
    else:
        checks.append(
            _check("position", "有可卖持仓", position_qty >= qty, f"持仓 {position_qty} / 卖出 {qty}")
        )
    if duplicate_order:
        checks.append(_check("duplicate", "未重复执行", False, "该授权已有成交订单（幂等返回）"))

    blocking = [c["key"] for c in checks if not c["ok"]]
    return {
        "checks": checks,
        "ok": not blocking,
        "blocking": blocking,
        "duplicate_order": duplicate_order,
    }


EXCEPTION_TYPES = {
    "authorization": "auth_invalid",
    "validity": "expired",
    "price": "price_invalid",
    "price_range": "price_out_of_range",
    "lot": "lot_invalid",
    "tradable": "suspended_or_st",
    "cash": "cash_short",
    "position": "position_short",
    "duplicate": "duplicate_order",
}


def exception_types(blocking: list[str]) -> list[str]:
    return [EXCEPTION_TYPES.get(key, key) for key in blocking]


__all__ = ["evaluate", "exception_types", "EXCEPTION_TYPES"]
