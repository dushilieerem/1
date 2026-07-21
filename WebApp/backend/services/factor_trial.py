# -*- coding: utf-8 -*-
"""自定义因子试算：转发到 YGQuant RE（本机不存行情）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from services.backtest_range import build_factor_backtest_payload

RE_URL = "http://192.168.3.64:9527/api/backtest/factor"


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
    # 允许只写 return …，补成方法体
    if not code.lstrip().startswith("def "):
        if "return" not in code:
            code = f"return {code}"
        code = f"def {factor_name}(self):\n    \"\"\"trial\"\"\"\n    " + "\n    ".join(code.splitlines())

    payload = build_factor_backtest_payload(
        factor_code=code,
        factor_name=factor_name,
        universe=universe,
        period=period,
    )
    req = urllib.request.Request(
        RE_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"RE HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"RE 不可达: {exc.reason}") from exc

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
