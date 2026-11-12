# -*- coding: utf-8 -*-
"""H5 量化研究 → ResearchEngine 适配层。

只做三件事：把 2–4 个手机端因子翻译成 RE 策略源码、提交现有
``/api/backtest/strategy`` 同步入口、把 RE 结果映射成手机端展示结构。
不实现第二套因子/回测引擎；RE 不可用或因子不在 RE DSL 内时返回 None，
由调用方明确降级并标注来源。
"""
from __future__ import annotations

from typing import Any

# RE 向量化策略 DSL 目前可表达的因子；ROE / 营收同比不在 RE 字段表内。
RE_SUPPORTED = frozenset({"value", "momentum", "volatility", "liquidity"})

_FACTOR_CODE = {
    "value": "1.0 / self.pe_ttm",
    "momentum": "self.close.shift(1).pct_change(20)",
    "volatility": "-self.close.pct_change().rolling(20).std()",
    "liquidity": "self.amount.rolling(20).mean()",
}

_UNIVERSE = {"hs300": "CSI300", "zz500": "CSI500", "all": "ALL_A"}


def supports(factors: list[dict[str, str]]) -> bool:
    return bool(factors) and all(str(f.get("key")) in RE_SUPPORTED for f in factors)


def unsupported_keys(factors: list[dict[str, str]]) -> list[str]:
    return [str(f.get("key")) for f in factors if str(f.get("key")) not in RE_SUPPORTED]


def build_strategy_code(factors: list[dict[str, str]]) -> str:
    """生成与用户 Web 策略同构的 RE 向量化策略源码。"""
    if not supports(factors):
        return ""
    methods: list[str] = []
    names: list[str] = []
    for index, factor in enumerate(factors):
        key = str(factor.get("key"))
        expr = _FACTOR_CODE[key]
        direction = str(factor.get("direction") or "")
        if direction == "low":
            expr = f"-({expr})"
        name = f"f_{index}_{key}"
        names.append(name)
        methods.append(
            f"    @factor\n"
            f"    def {name}(self):\n"
            f"        \"\"\"H5: {key} ({direction or 'default'})\"\"\"\n"
            f"        return {expr}\n"
        )
    signal = " +\n            ".join(f"self.rank(self.{name}())" for name in names)
    return (
        "from app.services.strategy.vectorized.factor_strategy import (\n"
        "    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,\n"
        ")\n\n"
        "UNIVERSE = \"CSI300\"\n"
        "BENCHMARK = \"CSI300\"\n"
        "TOP_N = 20\n"
        "REBALANCE_DAYS = 20\n\n"
        "class H5QuantStrategy(FactorPortfolioStrategy):\n"
        "    selector = TopN(TOP_N)\n"
        "    weighting = EqualWeight()\n"
        "    rebalance = EveryNTradingDays(REBALANCE_DAYS)\n\n"
        + "\n".join(methods)
        + "\n"
        "    @signal\n"
        "    def score(self):\n"
        f"        return (\n            {signal}\n        ) / {len(names)}\n"
    )


def _pct(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return round(n * 100, 2) if abs(n) <= 2 else round(n, 2)


def _curve(points: Any) -> list[dict[str, Any]]:
    out = []
    for point in points if isinstance(points, list) else []:
        if not isinstance(point, dict):
            continue
        value = point.get("value")
        date = point.get("date")
        if date is None or value is None:
            continue
        try:
            out.append({"date": str(date), "value": float(value)})
        except (TypeError, ValueError):
            continue
    return out


def _forward_re(method: str, path: str, **kwargs: Any) -> tuple[int, dict[str, str], Any]:
    from services.core.re_http_gateway import forward_re

    return forward_re(method, path, **kwargs)


def run_re_strategy(
    *,
    factors: list[dict[str, str]],
    universe: str,
    start_date: str | None,
    end_date: str | None,
    name: str,
) -> dict[str, Any] | None:
    """调用 RE 同步策略回测；返回手机端结构。

    因子不在 RE DSL 内时返回 None；RE 不可达、返回 HTTP 错误、异步 run_id
    或缺少净值时抛出 ``RuntimeError``，由调用方记录诊断并决定是否本地降级。
    """
    if not supports(factors):
        return None
    code = build_strategy_code(factors)
    if not code:
        return None
    uni = _UNIVERSE.get(universe, "CSI300")
    payload = {
        "strategy_code": code,
        "engine_mode": "vectorized",
        "universe": uni,
        "start": start_date,
        "end": end_date,
        "benchmark": "CSI300" if uni != "CSI500" else "CSI500",
        "commission_rate": 0.001,
        "stamp_tax": 0.0,
        "slippage_rate": 0.0,
        "initial_capital": 1_000_000,
        "include_positions": True,
        "include_rebalance_logs": True,
        "filter_suspended": True,
        "filter_st": True,
        "filter_limit_up": True,
        "filter_limit_down": False,
        "execution_timing": "next_close",
    }
    try:
        status, _headers, data = _forward_re(
            "POST", "/api/backtest/strategy", payload=payload, timeout=120
        )
    except Exception as exc:
        raise RuntimeError(f"RE strategy backtest failed: {exc}") from exc
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"RE strategy backtest returned HTTP {status}")
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    if data.get("run_id"):
        # RE 当前策略回测是同步入口；出现 run_id 说明契约变化，交给调用方降级。
        raise RuntimeError("RE returned async run_id; this BFF expects sync strategy backtests")
    metrics = data.get("metrics") or {}
    curve = _curve(data.get("equity_curve"))
    if not curve:
        raise RuntimeError("RE strategy backtest missing equity_curve")
    bench = _curve(data.get("benchmark_curve"))
    bench_by_date = {p["date"]: p["value"] for p in bench}
    curve = [
        {"date": p["date"], "nav": p["value"], "benchmark": bench_by_date.get(p["date"])}
        for p in curve
    ]
    total = metrics.get("total_return")
    if total is None:
        total = metrics.get("cumulative_return")
    if total is None and len(curve) > 1 and curve[0]["nav"]:
        total = curve[-1]["nav"] / curve[0]["nav"] - 1
    mapped = {
        "cumulative": _pct(total),
        "annual_return": _pct(metrics.get("annual_return")),
        "max_drawdown": _pct(metrics.get("max_drawdown")),
        "sharpe": metrics.get("sharpe"),
        "win_rate": _pct(metrics.get("win_rate")),
        "trade_count": metrics.get("trade_count") or len(data.get("rebalance_logs") or []),
        "volatility": _pct(metrics.get("volatility") or metrics.get("annual_vol")),
        "beta": metrics.get("beta"),
        "alpha": _pct(metrics.get("alpha")),
        "benchmark_return": _pct(metrics.get("benchmark_return")),
        "excess": _pct(metrics.get("excess_return") or data.get("excess_return")),
        "turnover_cost": None,
    }
    if mapped["cumulative"] is None:
        mapped["cumulative"] = _pct(total)
    if mapped["benchmark_return"] is None and len(bench) > 1 and bench[0]["value"]:
        mapped["benchmark_return"] = _pct(bench[-1]["value"] / bench[0]["value"] - 1)
    if mapped["excess"] is None and mapped["cumulative"] is not None and mapped["benchmark_return"] is not None:
        mapped["excess"] = round(mapped["cumulative"] - mapped["benchmark_return"], 2)
    positions = data.get("positions") or []
    holdings = []
    if positions and isinstance(positions[-1], dict):
        holdings = [
            {"code": h.get("symbol"), "name": h.get("name") or h.get("symbol")}
            for h in (positions[-1].get("holdings") or [])
        ]
    if not holdings:
        logs = data.get("rebalance_logs") or []
        if logs and isinstance(logs[-1], dict):
            holdings = [
                {"code": t.get("symbol"), "name": t.get("name") or t.get("symbol")}
                for t in (logs[-1].get("trades") or [])
                if (t.get("target_weight") or 0) > 0
            ]
    start = (data.get("date_range") or {}).get("start") or start_date
    end = (data.get("date_range") or {}).get("end") or end_date
    return {
        "name": name,
        "metrics": mapped,
        "curve": curve,
        "start_date": start,
        "end_date": end,
        "holdings": holdings,
        "engine": "re",
        "benchmark": "index",
        "shortened": False,
        "assumptions": {
            "universe": uni,
            "universe_en": uni,
            "rebalance": "月度（20 交易日）",
            "rebalance_en": "Monthly (20 trading days)",
            "holdings": 20,
            "weighting": "等权",
            "weighting_en": "Equal weight",
            "cost": "单边 0.1%",
            "cost_en": "0.1% one-way",
            "dividend": "含分红（RE 复权价）",
            "dividend_en": "Dividends included (RE adjusted prices)",
            "exclusions": "剔除 ST、停牌、涨停",
            "exclusions_en": "Excludes ST, suspended and limit-up names",
            "benchmark": "沪深300" if uni != "CSI500" else "中证500",
            "benchmark_en": "CSI 300" if uni != "CSI500" else "CSI 500",
            "shortened": False,
            "factor_count": len(factors),
            "engine": "ResearchEngine",
        },
    }
