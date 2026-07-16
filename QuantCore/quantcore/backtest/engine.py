"""``BacktestEngine`` - 交易模拟引擎。

依据 ``docs/04-features/FEAT-001-quantcore-core/04-class-design.md`` BacktestEngine 节与 ``docs/04-features/FEAT-001-quantcore-core/05-runtime-flow.md`` 第 4 节：

    属性：
      data_engine: DataEngine
      matching_engine: MatchingEngine
      portfolio: Portfolio
      cost_model: TransactionCost
      start_date: datetime
      end_date: datetime

    方法：
      run(strategy_func) -> BacktestResult
      set_portfolio(portfolio: Portfolio)

运行流程：

    ① 初始化 Portfolio
    ② 按时间逐 bar 推进：
        - 更新盯市价格
        - 策略生成订单 orders = strategy_func(bar, portfolio)
        - MatchingEngine 撮合 -> fills
        - TransactionCost 计算费用
        - Portfolio 更新持仓
        - 记录净值
    ③ 构建 BacktestResult

**关键原则**：BacktestEngine 只做交易模拟，不计算任何指标（Sharpe、IC 等由 MetricEngine）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from quantcore.backtest.cost import TransactionCost
from quantcore.backtest.matching import MatchingEngine
from quantcore.backtest.order import Fill, Order
from quantcore.backtest.portfolio import Portfolio
from quantcore.backtest.result import BacktestResult
from quantcore.data._util import Universe, resolve_universe


class BacktestEngine:
    """交易模拟引擎。"""

    def __init__(
        self,
        data_engine,
        matching_engine: Optional[MatchingEngine] = None,
        portfolio: Optional[Portfolio] = None,
        cost_model: Optional[TransactionCost] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 1_000_000.0,
    ) -> None:
        self.data_engine = data_engine
        self.matching_engine = matching_engine or MatchingEngine()
        self.portfolio = portfolio or Portfolio(initial_capital)
        self.cost_model = cost_model or TransactionCost()
        self.start_date = start_date
        self.end_date = end_date

    def set_portfolio(self, portfolio: Portfolio) -> None:
        self.portfolio = portfolio

    # -- 内部：构建 universe 的 OHLC 宽表（复用 get_panels）--
    def _build_panels(
        self, universe: Universe, start: Optional[str], end: Optional[str]
    ) -> Dict[str, pd.DataFrame]:
        symbols = resolve_universe(self.data_engine, universe)
        panels = self.data_engine.get_panels(
            start, end, ["open", "high", "low", "close"]
        )
        close_df = panels.get("close")
        if close_df is None or close_df.empty:
            return {"open": pd.DataFrame(), "high": pd.DataFrame(),
                    "low": pd.DataFrame(), "close": pd.DataFrame()}
        close_df = close_df.sort_index().reindex(columns=symbols)
        out: Dict[str, pd.DataFrame] = {"close": close_df}
        for f in ("open", "high", "low"):
            df = panels.get(f)
            if df is None or df.empty:
                df = close_df  # 缺字段用 close 近似
            else:
                df = df.reindex(index=close_df.index, columns=symbols)
            out[f] = df
        return out

    def run(
        self,
        strategy_func,
        universe: Optional[Universe] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> BacktestResult:
        """运行交易模拟。

        Parameters
        ----------
        strategy_func:
            ``strategy_func(bar: pd.Series, portfolio: Portfolio) -> List[Order]``。
            ``bar`` 为当前日期的截面 close 序列（索引=标的，``.name``=日期）。
        universe:
            股票池。若为 ``None`` 则用 ``data_engine.get_universe()``。
        start, end:
            起止日期，覆盖实例配置。
        """
        start = start or self.start_date
        end = end or self.end_date
        if universe is None:
            universe = self.data_engine.get_universe()

        panels = self._build_panels(universe, start, end)
        close_df = panels["close"]
        if close_df.empty:
            raise ValueError("回测范围内无可用行情数据，请检查 universe/日期。")

        all_orders: List[Order] = []
        all_fills: List[Fill] = []
        equities: List[float] = []
        timestamps: List[datetime] = []

        for date, close_row in close_df.iterrows():
            # 更新盯市价格
            self.portfolio.update_prices(close_row.dropna().to_dict())

            # 策略生成订单
            orders = strategy_func(close_row, self.portfolio) or []
            for order in orders:
                all_orders.append(order)
                symbol = order.symbol
                if symbol not in close_df.columns:
                    continue
                symbol_bar = pd.Series(
                    {
                        "open": panels["open"].loc[date, symbol],
                        "high": panels["high"].loc[date, symbol],
                        "low": panels["low"].loc[date, symbol],
                        "close": close_row[symbol],
                    },
                    name=date,
                )
                fills = self.matching_engine.match(order, symbol_bar, timestamp=date)
                for fill in fills:
                    commission, slippage = self.cost_model.calculate(
                        order, fill.fill_price
                    )
                    fill.commission = commission
                    fill.slippage = slippage
                    self.portfolio.update(fill)
                    all_fills.append(fill)

            equities.append(self.portfolio.total_value)
            timestamps.append(date)

        equity_curve = pd.Series(equities, index=timestamps, name="equity")
        return BacktestResult(
            portfolio=self.portfolio,
            orders=all_orders,
            fills=all_fills,
            equity_curve=equity_curve,
            timestamps=timestamps,
        )
