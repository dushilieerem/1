"""生成样本宽表面板数据（与真实 ``price.CSV`` 同格式）。

运行：``python examples/gen_data.py``

在 ``data/price.CSV`` 生成一张 Wind/Choice 风格的宽表：
3 行表头（代码 / 名称 / 字段）、GBK 编码、每只标的多字段列
（开盘价/最高价/最低价/收盘价/总市值），供 :class:`WideCSVProvider` 读取。

无真实数据时可用本脚本生成样例以跑通流程；有真实数据时直接用根目录
``data/price.CSV``。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "price.CSV"

#: 沪深各 15 只样本代码（6 位代码）
SYMBOLS = (
    [f"600{i:03d}.SH" for i in range(1, 16)]
    + [f"000{i:03d}.SZ" for i in range(1, 16)]
)
NAMES = [f"样本{i:03d}" for i in range(len(SYMBOLS))]
START, END = "2024-01-02", "2025-12-31"
DAYS = 120
SEED = 42

#: (标准字段, 中文字段名)
FIELDS = [
    ("open", "开盘价(元)"),
    ("high", "最高价(元)"),
    ("low", "最低价(元)"),
    ("close", "收盘价(元)"),
    ("market_cap", "总市值(元)"),
]


def _gen_panels(rng):
    dates = pd.bdate_range(START, END)[:DAYS]
    n = len(dates)
    panels = {}
    closes = {}
    for sym in SYMBOLS:
        drift = rng.uniform(0.1, 0.3) / 252
        vol = rng.uniform(0.2, 0.4) / np.sqrt(252)
        mom = rng.uniform(0.03, 0.08)
        rets = np.zeros(n)
        for t in range(1, n):
            hist = rets[max(0, t - 20):t].mean()
            rets[t] = drift + mom * hist + rng.normal(0, vol)
        closes[sym] = 20.0 * np.exp(np.cumsum(rets))

    close_df = pd.DataFrame(closes, index=dates)
    panels["close"] = close_df
    panels["open"] = close_df.shift(1).fillna(close_df) * (1 + rng.normal(0, 0.002, close_df.shape))
    panels["high"] = np.maximum(panels["open"], close_df) * (1 + np.abs(rng.normal(0, 0.004, close_df.shape)))
    panels["low"] = np.minimum(panels["open"], close_df) * (1 - np.abs(rng.normal(0, 0.004, close_df.shape)))
    # 总市值：收盘价 × 随机股本
    shares = pd.Series(rng.uniform(5e8, 5e9, len(SYMBOLS)), index=SYMBOLS)
    panels["market_cap"] = close_df * shares
    return panels


def main() -> None:
    rng = np.random.default_rng(SEED)
    panels = _gen_panels(rng)
    dates = panels["close"].index

    # 组装 MultiIndex 列：(代码, 名称, 字段)，每只标的 5 个字段连续排列
    data = {}
    for sym, name in zip(SYMBOLS, NAMES):
        for fkey, fstr in FIELDS:
            data[(sym, name, fstr)] = panels[fkey][sym].values
    wide = pd.DataFrame(data, index=dates)
    wide.index.name = None

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(OUT, encoding="gbk")
    print(f"已生成宽表: {OUT}")
    print(f"  日期 {dates[0].date()} ~ {dates[-1].date()}（{len(dates)} 天）"
          f"| 标的 {len(SYMBOLS)} | 字段 {[f for f, _ in FIELDS]}")


if __name__ == "__main__":
    main()
