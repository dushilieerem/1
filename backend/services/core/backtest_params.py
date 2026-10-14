# -*- coding: utf-8 -*-
"""回测请求参数的公共校验。

SVQuant 转发回测请求时是**黑名单透传**（除 ``_svquant_ui`` 一类本站字段外原样
发给 ResearchEngine），所以参数不在这里登记也能通。但 RE 端用的是 pydantic
``extra="forbid"`` 加 Literal 枚举，非法取值会在 RE 变成 422，错误信息晦涩、
还白跑一次跨服务往返。这里在转发前先校验一次，把错误挡在 SVQuant 侧。

刻意**不**在这里补默认值：默认值归 RE 定义，SVQuant 再写一份会有两个来源，
RE 改默认时这边不会跟着变。字段缺失就照原样透传，由 RE 兜底。

因子与策略两条转发路径（``services/factor/re_factor_async_proxy.py`` 与
``app/routers/re_gateway.py``）共用本模块，避免规则写两份后漂移。
"""
from __future__ import annotations

from typing import Any

#: 成交时点：信号恒在 T 日收盘产生。
#: same_close = T 日收盘价成交；next_close = T+1 日收盘价成交（RE 默认）；
#: next_open = T+1 日开盘价成交。
VALID_EXECUTION_TIMING: tuple[str, ...] = ("same_close", "next_close", "next_open")


def validate_execution_timing(body: dict[str, Any]) -> None:
    """校验 ``execution_timing``；非法取值抛 ``ValueError``（调用方转 400）。

    缺失、``null`` 或空白一律视为「没传」并**删掉该键**，由 RE 用它自己的默认值。
    不能只是留着不动：RE 的字段是 Literal 枚举，``null`` 和空白串都会让它报 422。
    同理就地去掉首尾空白，避免 ``" next_open"`` 穿透过去。
    """

    raw = body.get("execution_timing")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        body.pop("execution_timing", None)
        return
    value = str(raw).strip()
    if value not in VALID_EXECUTION_TIMING:
        raise ValueError(
            "execution_timing 仅支持 " + " / ".join(VALID_EXECUTION_TIMING)
            + f"，得到 {raw!r}"
        )
    body["execution_timing"] = value


__all__ = ["VALID_EXECUTION_TIMING", "validate_execution_timing"]
