"""``NativeEngine`` - 自研向量化回测后端。

逐字复刻 :func:`researchengine.portfolio.build_factor_portfolio` 的净值数学（固定本金口径
``equity = 1.0 + port_ret.cumsum()``），保证默认路径（``cost=0``）与现状逐位一致。
``cost > 0`` 时按换手率 ``|Δ权重|`` 计入手续费/滑点（build_factor_portfolio 原不扣成本，
属本引擎的增强，不影响默认 parity）。
"""

from __future__ import annotations

import pandas as pd

from quantcore.backtest.adapter.interfaces import IBacktestEngine
from quantcore.backtest.adapter.signals import BacktestConfig, BacktestSignals
from quantcore.backtest.result import BacktestResult


class NativeEngine(IBacktestEngine):
    """自研向量化回测引擎。"""

    name: str = "native"

    def run(
        self,
        signals: BacktestSignals,
        config: BacktestConfig,
    ) -> BacktestResult:
        target = signals.target_weights
        close = signals.close

        ret = close.pct_change(fill_method=None)

        # 实际持有权重 = 上一日收盘的目标权重（t 收盘调仓，t+1 起持有），区间内 ffill
        held = target.ffill().shift(1).fillna(0.0)
        port_ret = (held * ret).sum(axis=1)

        # 可选成本（默认 0 -> 与 build_factor_portfolio 逐位一致）
        if config.commission_rate or config.slippage_rate:
            turnover = held.diff().abs().sum(axis=1).fillna(0.0)
            port_ret = port_ret - turnover * (config.commission_rate + config.slippage_rate)

        # 去掉首日（无持仓）
        port_ret = port_ret.iloc[1:]
        port_ret = port_ret.dropna()

        equity = 1.0 + port_ret.cumsum()
        positions = held.loc[port_ret.index].copy()
        return BacktestResult(
            equity_curve=equity,
            returns=port_ret,
            positions=positions,
        )
