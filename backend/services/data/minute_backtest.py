# -*- coding: utf-8 -*-
"""分钟级回测基线（P1-D02）。

用于验证分钟数据在回测链路中的可用性与性能：单标的、双均线/动量择时，
逐 bar 计算持仓与收益。不替代 ResearchEngine 的横截面因子回测。
"""
from __future__ import annotations

import math
from typing import Any

from services.data.marketdata_store import MINUTE_FREQS, minute_bars


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    window: list[float] = []
    for i, v in enumerate(values):
        window.append(v)
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            out[i] = sum(window) / period
    return out


def run_minute_backtest(
    bars: list[dict[str, Any]],
    *,
    freq: str = "1m",
    lookback: int = 20,
    fee_rate: float = 0.0,
) -> dict[str, Any]:
    """价格上穿 SMA(lookback) 持有，下穿空仓；按 bar 计收益。"""
    freq = (freq or "1m").lower()
    if freq not in MINUTE_FREQS:
        raise ValueError(f"不支持的频率: {freq}")
    if lookback < 1:
        raise ValueError("lookback 必须 >= 1")
    closes: list[float] = []
    times: list[str] = []
    for bar in bars:
        close = bar.get("close")
        if close is None:
            continue
        closes.append(float(close))
        times.append(str(bar.get("time") or ""))
    if len(closes) <= lookback:
        raise ValueError("分钟数据不足以完成回测（需大于 lookback+1 根）")

    sma = _sma(closes, lookback)
    position = 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    returns: list[float] = []
    trades = 0
    for i in range(1, len(closes)):
        signal = 1.0 if sma[i] is not None and closes[i] > sma[i] else 0.0
        bar_ret = closes[i] / closes[i - 1] - 1.0
        if signal != position and fee_rate > 0:
            equity *= 1.0 - abs(signal - position) * fee_rate
            trades += 1
        position = signal
        r = bar_ret * position
        equity *= 1.0 + r
        returns.append(r)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)

    mean = sum(returns) / len(returns) if returns else 0.0
    var = sum((r - mean) ** 2 for r in returns) / len(returns) if returns else 0.0
    std = math.sqrt(var)
    # 年化按 A 股 242 交易日估算
    bars_per_day = max(1, 240 // MINUTE_FREQS[freq])
    ann_factor = 242 * bars_per_day
    sharpe = (mean / std * math.sqrt(ann_factor)) if std > 0 else None
    total_return = equity - 1.0
    annual_return = (
        (1.0 + total_return) ** (ann_factor / max(1, len(returns))) - 1.0
        if total_return > -1
        else -1.0
    )
    return {
        "ok": True,
        "frequency": freq,
        "lookback": int(lookback),
        "feeRate": float(fee_rate),
        "bars": len(returns),
        "start": times[0] if times else None,
        "end": times[-1] if times else None,
        "metrics": {
            "total_return": round(total_return, 6),
            "annual_return": round(annual_return, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe": round(sharpe, 4) if sharpe is not None else None,
            "trades": trades,
        },
    }


def backtest_symbol(
    symbol: str,
    *,
    freq: str = "1m",
    lookback: int = 20,
    fee_rate: float = 0.0,
    days: int = 5,
) -> dict[str, Any]:
    data = minute_bars(symbol, limit_days=max(1, min(30, int(days))), freq=freq)
    out = run_minute_backtest(
        data.get("items") or [], freq=freq, lookback=lookback, fee_rate=fee_rate
    )
    out["symbol"] = data.get("symbol")
    out["data_version"] = data.get("data_version")
    return out
