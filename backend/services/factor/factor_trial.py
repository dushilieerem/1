# -*- coding: utf-8 -*-
"""自定义因子试算：转发到 YGQuant RE（本机不存行情）。"""
from __future__ import annotations

import re

from services.core.backtest_range import build_factor_backtest_payload
from services.factor.re_backtest_bff import forward_factor_backtest


def trial_via_re(
    *,
    body: str,
    factor_name: str = "trial_factor",
    universe: str = "CSI300",
    period: str = "3m",
) -> dict:
    """用同事 RE 短周期回测做试算。成功条件：无 error 且有 metrics。"""
    code = (body or "").strip()
    if not code:
        raise ValueError("计算表达式不能为空")
    if not code.lstrip().startswith("def "):
        raise ValueError("请写完整函数，例如 def RET_5D_DEMO(self): ...")
    m = re.search(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code, flags=re.M)
    if not m:
        raise ValueError("无法解析函数名，请检查 def 写法")
    if m.group(1) != factor_name:
        raise ValueError(f"因子代码「{factor_name}」须与函数名「{m.group(1)}」一致")

    payload = build_factor_backtest_payload(
        factor_code=code,
        factor_name=factor_name,
        universe=universe,
        period=period,
    )
    try:
        data = forward_factor_backtest(payload, timeout=180)
    except RuntimeError as exc:
        raise RuntimeError(str(exc).replace("HTTP Error ", "RE HTTP ", 1)) from exc

    err = data.get("error")
    if err:
        raise ValueError(str(err))
    metrics = data.get("metrics") or {}
    if not metrics:
        raise ValueError("RE 未返回 metrics，试算失败")
    fa = data.get("factor_analysis") or {}

    def _num(x):
        if x is None:
            return None
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        if v != v:  # NaN
            return None
        return v

    ic = _num(metrics.get("ic"))
    if ic is None:
        ic = _num(fa.get("ic_mean"))
    rank_ic = _num(metrics.get("rank_ic"))
    if rank_ic is None:
        rank_ic = _num(fa.get("rank_ic_mean"))
    sharpe = _num(metrics.get("sharpe"))
    ann = _num(metrics.get("annual_return"))
    # RE 偶发返回全 0 / IC 全空（区间极短或组合未成交）——不算通过
    if ic is None and rank_ic is None and (sharpe is None or sharpe == 0) and (ann is None or ann == 0):
        dr = data.get("date_range") or {}
        raise ValueError(
            "RE 指标无效（IC 空且收益/Sharpe 为 0）。"
            f"区间={dr.get('start')}~{dr.get('end')}。"
            "请改选「近1年/近3年」重试，或检查表达式。"
        )

    return {
        "ok": True,
        "body": body.strip(),
        "source": "ygquant_re",
        "universe": universe,
        "period": period,
        "metrics": metrics,
        "factor_analysis": fa,
        "date_range": data.get("date_range"),
        "stats": {
            "ic": ic,
            "rank_ic": rank_ic,
            "sharpe": sharpe,
            "annual_return": ann,
            "max_drawdown": _num(metrics.get("max_drawdown")),
            "turnover": _num(metrics.get("turnover")),
        },
    }
