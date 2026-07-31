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
from quantcore.backtest.result import BacktestResult, rebalance_logs_from_targets


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

        # t 收盘生成信号，t+1 收盘成交并作为净值起点，t+2 起承担价格收益。
        executed = target.ffill().shift(1).fillna(0.0)
        held = executed.shift(1).fillna(0.0)
        port_ret = (held * ret).sum(axis=1)

        # 可选成本（默认 0 -> 与 build_factor_portfolio 逐位一致）
        if config.commission_rate or config.slippage_rate or config.stamp_tax:
            # 成交成本记入随后的持有期，保证建仓日净值为 1。
            weight_change = executed.diff().fillna(0.0).shift(1).fillna(0.0)
            turnover = weight_change.abs().sum(axis=1)
            sell_turnover = (-weight_change.clip(upper=0.0)).sum(axis=1)
            port_ret = port_ret - turnover * (
                config.commission_rate + config.slippage_rate
            ) - sell_turnover * config.stamp_tax

        # 去掉信号日；首个保留日为收盘建仓日，收益为 0。
        port_ret = port_ret.iloc[1:]
        port_ret = port_ret.dropna()

        equity = 1.0 + port_ret.cumsum()
        positions = executed.loc[port_ret.index].copy()
        return BacktestResult(
            equity_curve=equity,
            returns=port_ret,
            positions=positions,
            rebalance_logs=rebalance_logs_from_targets(target),
        )
