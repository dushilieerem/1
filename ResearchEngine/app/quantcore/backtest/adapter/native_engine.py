"""``NativeEngine`` - 自研向量化回测后端。

统一实现前一日目标权重对应下一交易日收盘收益的向量化语义：收益序列保留首个信号
持有期，展示净值在第二个交易日归一为 1 后按复利累计。``cost > 0`` 时按换手率
``|Δ权重|`` 计入手续费/滑点。
"""

from __future__ import annotations

import pandas as pd

from app.quantcore.backtest.adapter.interfaces import IBacktestEngine
from app.quantcore.backtest.adapter.signals import BacktestConfig, BacktestSignals
from app.quantcore.backtest.result import BacktestResult, rebalance_logs_from_targets


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

        # t 收盘形成目标权重；该权重承担 t -> t+1 的收盘收益。
        # returns 保留首个信号日到次日的收益，供因子指标使用；equity 则
        # 在次日收盘归一为 1，与 Supermind/Alphalens 分层曲线一致。
        held = target.ffill().shift(1).fillna(0.0)
        port_ret = (held * ret).sum(axis=1)

        # 可选成本（默认 0 -> 与 build_factor_portfolio 逐位一致）
        if config.commission_rate or config.slippage_rate or config.stamp_tax:
            weight_change = held.diff().fillna(0.0)
            turnover = weight_change.abs().sum(axis=1)
            sell_turnover = (-weight_change.clip(upper=0.0)).sum(axis=1)
            port_ret = port_ret - turnover * (
                config.commission_rate + config.slippage_rate
            ) - sell_turnover * config.stamp_tax

        # 去掉信号日。首个保留日包含首个信号产生的收益。
        port_ret = port_ret.iloc[1:]
        port_ret = port_ret.dropna()

        # 展示曲线不计首个信号日的收益：在次日收盘归一为 1，后续复利。
        display_returns = port_ret.copy()
        display_returns.iloc[0] = 0.0
        equity = (1.0 + display_returns).cumprod()
        positions = held.loc[port_ret.index].copy()
        return BacktestResult(
            equity_curve=equity,
            returns=port_ret,
            positions=positions,
            rebalance_logs=rebalance_logs_from_targets(target),
        )
