"""``VectorBTEngine`` - 基于 vectorbt 的向量化回测后端。

懒加载 ``vectorbt``：未安装时本模块仍可导入，仅在 :meth:`run` 调用时报清晰的安装提示。
把 :class:`BacktestSignals.target_weights` 透传给 ``vbt.Portfolio.from_orders`` 的
``size_type="targetpercent"``，与 :class:`NativeEngine` 同一信号契约。

口径对齐：取 ``pf.returns()`` 去 NaN 后 ``1 + cumsum``，与 Native 的 ``1.0 + port_ret.cumsum()``
同构；因 vectorbt 撮合时序与自研 ``shift(1)`` 约定存在 1 bar 偏差，两者数值接近但不逐位相等
（见 ``test_native_vs_vectorbt_parity`` 的松容差）。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from quantcore.backtest.adapter.interfaces import IBacktestEngine
from quantcore.backtest.adapter.signals import BacktestConfig, BacktestSignals
from quantcore.backtest.result import BacktestResult, rebalance_logs_from_targets


class VectorBTEngine(IBacktestEngine):
    """vectorbt 回测后端。"""

    name: str = "vectorbt"

    def run(
        self,
        signals: BacktestSignals,
        config: BacktestConfig,
    ) -> BacktestResult:
        try:
            import vectorbt as vbt
        except ImportError as exc:  # pragma: no cover - 装了才跑得到
            raise ImportError(
                "VectorBTEngine 需要 vectorbt：在项目 Conda 环境执行 "
                "`pip install -U vectorbt`（Python 3.13 可能需独立 3.11 环境）。"
            ) from exc

        target = signals.target_weights
        close = signals.close

        pf = vbt.Portfolio.from_orders(
            close,
            target,
            size_type="targetpercent",
            group_by=config.group_by,
            cash_sharing=config.group_by,
            init_cash=config.initial_capital,
            fees=config.commission_rate,
            slippage=config.slippage_rate,
            freq=config.freq,
            # min_commission（每笔最低）vectorbt 原生不支持，按比例近似已足够研究用途
        )

        # 收益序列（去首行/NaN，与 Native 同构）
        returns = pf.returns()
        if isinstance(returns, pd.DataFrame):
            returns = returns.iloc[:, 0]
        returns = returns.iloc[1:].dropna()
        equity = 1.0 + returns.cumsum()

        # 持仓权重：按各标的市值 / 组合总市值（用于换手率指标；取不到则置 None）
        positions: Optional[pd.DataFrame] = None
        try:
            total_val = pf.value()
            if isinstance(total_val, pd.DataFrame):
                total_val = total_val.iloc[:, 0]
            asset_val = pf.asset_value(group_by=False)
            positions = asset_val.div(total_val, axis=0)
            positions = positions.reindex(index=returns.index)
        except Exception:  # pragma: no cover - 版本差异不致命
            positions = None

        return BacktestResult(
            equity_curve=equity,
            returns=returns,
            positions=positions,
            rebalance_logs=rebalance_logs_from_targets(target),
        )
