"""四因子计算：动量(momentum)、市盈率(pe)、市净率(pb)、净资产收益率(roe)。

输出统一长表：columns=[date, ticker, factor, value]，便于入库与按日截面处理。
因子原始值不做取向（方向由 evaluation 根据 IC 符号决定），保证可复现、可解释。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACTOR_NAMES = ["momentum", "pe", "pb", "roe"]


def compute_factors(prices: pd.DataFrame, fundamentals: dict, momentum_window: int = 20) -> pd.DataFrame:
    """返回长表因子值。prices 为收盘价面板；fundamentals 含 pe/pb/roe 面板。"""
    mom = prices.pct_change(momentum_window)            # 20 日动量（原始收益）
    pe = fundamentals.get("pe")
    pb = fundamentals.get("pb")
    roe = fundamentals.get("roe")

    parts = []
    for name, panel in [("momentum", mom), ("pe", pe), ("pb", pb), ("roe", roe)]:
        if panel is None:
            continue
        long = panel.stack().reset_index()
        long.columns = ["date", "ticker", "value"]
        long["factor"] = name
        parts.append(long)

    out = pd.concat(parts, ignore_index=True)
    out = out.dropna(subset=["value"])
    out["date"] = pd.to_datetime(out["date"])
    return out[["date", "ticker", "factor", "value"]]


def factor_wide(factor_long: pd.DataFrame) -> dict:
    """长表 -> {factor: DataFrame(date x ticker)}。"""
    out = {}
    for f in factor_long["factor"].unique():
        sub = factor_long[factor_long["factor"] == f]
        wide = sub.pivot(index="date", columns="ticker", values="value")
        out[f] = wide.sort_index()
    return out


if __name__ == "__main__":
    from data_source import fetch_data
    d = fetch_data({"tushare": {"source": "synthetic"}, "research": {"universe_size": 10}})
    fl = compute_factors(d["prices"], d["fundamentals"])
    print(fl.head(), "\n因子:", fl["factor"].unique().tolist())
