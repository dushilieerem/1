# -*- coding: utf-8 -*-
"""技术指标计算（P1-D07）：纯 Python，无 pandas 依赖。

输入为按日期升序的 bars（close/high/low/volume），输出与输入等长的序列，
数据不足的位置为 None。支持 MA/EMA/MACD/RSI/BOLL/KDJ/ATR。
"""
from __future__ import annotations

from typing import Any

SUPPORTED = ("ma", "ema", "macd", "rsi", "boll", "kdj", "atr")


def _sma(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    window: list[float] = []
    for i, v in enumerate(values):
        if v is None:
            window = []
            continue
        window.append(float(v))
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            out[i] = sum(window) / period
    return out


def _ema(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    k = 2 / (period + 1)
    prev: float | None = None
    for i, v in enumerate(values):
        if v is None:
            continue
        prev = float(v) if prev is None else (float(v) - prev) * k + prev
        out[i] = prev
    return out


def _rsi(values: list[float | None], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    gains: list[float] = []
    losses: list[float] = []
    prev: float | None = None
    for i, v in enumerate(values):
        if v is None:
            prev = None
            gains, losses = [], []
            continue
        cur = float(v)
        if prev is not None:
            change = cur - prev
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))
            if len(gains) > period:
                gains.pop(0)
                losses.pop(0)
            if len(gains) == period:
                avg_gain = sum(gains) / period
                avg_loss = sum(losses) / period
                out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        prev = cur
    return out


def _rolling_std(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    window: list[float] = []
    for i, v in enumerate(values):
        if v is None:
            window = []
            continue
        window.append(float(v))
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            mean = sum(window) / period
            var = sum((x - mean) ** 2 for x in window) / period
            out[i] = var ** 0.5
    return out


def _atr(bars: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    trs: list[float | None] = []
    prev_close: float | None = None
    for bar in bars:
        high, low, close = bar.get("high"), bar.get("low"), bar.get("close")
        if high is None or low is None or close is None:
            trs.append(None)
            prev_close = None
            continue
        if prev_close is None:
            trs.append(float(high) - float(low))
        else:
            trs.append(
                max(
                    float(high) - float(low),
                    abs(float(high) - prev_close),
                    abs(float(low) - prev_close),
                )
            )
        prev_close = float(close)
    return _sma(trs, period)


def compute(
    bars: list[dict[str, Any]],
    *,
    indicators: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """返回 {dates, series:{name: [...]}}；未知指标抛 ValueError。"""
    wanted = [x.strip().lower() for x in (indicators or list(SUPPORTED)) if x.strip()]
    unknown = [x for x in wanted if x not in SUPPORTED]
    if unknown:
        raise ValueError(f"不支持的指标: {', '.join(unknown)}")
    p = params or {}

    def _period(key: str, default: int) -> int:
        try:
            return max(1, min(250, int(p.get(key, default))))
        except (TypeError, ValueError):
            return default

    closes = [b.get("close") for b in bars]
    highs = [b.get("high") for b in bars]
    lows = [b.get("low") for b in bars]
    series: dict[str, list[float | None]] = {}

    if "ma" in wanted:
        for n in (5, 10, 20, 60):
            series[f"ma{n}"] = _sma(closes, _period(f"ma{n}", n))
    if "ema" in wanted:
        for n in (12, 26):
            series[f"ema{n}"] = _ema(closes, _period(f"ema{n}", n))
    if "macd" in wanted:
        fast = _period("macd_fast", 12)
        slow = _period("macd_slow", 26)
        signal_n = _period("macd_signal", 9)
        dif = [
            (a - b) if a is not None and b is not None else None
            for a, b in zip(_ema(closes, fast), _ema(closes, slow))
        ]
        dea = _ema(dif, signal_n)
        series["macd_dif"] = dif
        series["macd_dea"] = dea
        series["macd_hist"] = [
            (a - b) * 2 if a is not None and b is not None else None for a, b in zip(dif, dea)
        ]
    if "rsi" in wanted:
        for n in (6, 12, 24):
            series[f"rsi{n}"] = _rsi(closes, _period(f"rsi{n}", n))
    if "boll" in wanted:
        n = _period("boll", 20)
        width = float(p.get("boll_width", 2) or 2)
        mid = _sma(closes, n)
        std = _rolling_std(closes, n)
        series["boll_mid"] = mid
        series["boll_upper"] = [
            (m + width * s) if m is not None and s is not None else None for m, s in zip(mid, std)
        ]
        series["boll_lower"] = [
            (m - width * s) if m is not None and s is not None else None for m, s in zip(mid, std)
        ]
    if "kdj" in wanted:
        n = _period("kdj", 9)
        k_vals: list[float | None] = []
        d_vals: list[float | None] = []
        prev_k = prev_d = 50.0
        for i in range(len(bars)):
            window_high = [h for h in highs[max(0, i - n + 1) : i + 1] if h is not None]
            window_low = [w for w in lows[max(0, i - n + 1) : i + 1] if w is not None]
            close = closes[i]
            if not window_high or not window_low or close is None:
                k_vals.append(None)
                d_vals.append(None)
                continue
            hi, lo = max(window_high), min(window_low)
            rsv = 50.0 if hi == lo else (float(close) - float(lo)) / (float(hi) - float(lo)) * 100
            prev_k = prev_k * 2 / 3 + rsv / 3
            prev_d = prev_d * 2 / 3 + prev_k / 3
            k_vals.append(prev_k)
            d_vals.append(prev_d)
        series["kdj_k"] = k_vals
        series["kdj_d"] = d_vals
        series["kdj_j"] = [
            (3 * k - 2 * d) if k is not None and d is not None else None for k, d in zip(k_vals, d_vals)
        ]
    if "atr" in wanted:
        series["atr"] = _atr(bars, _period("atr", 14))

    return {
        "dates": [str(b.get("date") or b.get("time") or "") for b in bars],
        "series": series,
        "params": p,
    }
