"""结构化因子组合策略测试。"""

import numpy as np
import pandas as pd
import pytest

from app.quantcore.backtest.adapter.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)
from app.quantcore.factor.base import Panel


class CompositeStrategy(FactorPortfolioStrategy):
    selector = TopN(2)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(2)

    @factor
    def momentum(self):
        return self.close.pct_change()

    @factor
    def value(self):
        return 1.0 / self.pe_ttm

    @signal
    def score(self):
        return 0.6 * self.rank(self.momentum()) + 0.4 * self.rank(self.value())


def _panel():
    dates = pd.bdate_range("2024-01-01", periods=4)
    columns = ["A", "B", "C"]
    return Panel({
        "close": pd.DataFrame([[10, 20, 30], [11, 19, 33], [12, 18, 36], [13, 17, 39]], index=dates, columns=columns),
        "pe_ttm": pd.DataFrame([[10, 20, 40], [10, 20, 40], [10, 20, 40], [10, 20, 40]], index=dates, columns=columns),
    })


def test_factor_portfolio_strategy_generates_top_n_weights():
    result = CompositeStrategy().generate_signals(_panel())
    target = result.target_weights
    assert target.iloc[0].notna().all()
    assert target.iloc[0].sum() == 0.0  # 动量窗口尚未形成，首个调仓日空仓
    assert target.iloc[1].isna().all()
    assert target.iloc[2].notna().all()
    assert target.iloc[2].sum() == pytest.approx(1.0)
    assert (target.iloc[2] > 0).sum() == 2


def test_factor_portfolio_helpers_are_cross_sectional():
    values = pd.DataFrame([[1.0, 2.0, 3.0], [5.0, 5.0, 5.0]])
    assert FactorPortfolioStrategy.rank(values).iloc[0, 2] == pytest.approx(1.0)
    assert FactorPortfolioStrategy.zscore(values).iloc[1].eq(0.0).all()
    assert FactorPortfolioStrategy.normalize(values).iloc[0].abs().sum() == pytest.approx(1.0)


def test_factor_portfolio_strategy_requires_one_signal():
    class MissingSignal(FactorPortfolioStrategy):
        @factor
        def alpha(self):
            return self.close

    with pytest.raises(ValueError, match="@signal"):
        MissingSignal().generate_signals(_panel())


def test_factor_portfolio_strategy_all_equal_score_breaks_ties_by_column_order():
    class AllEqualScore(FactorPortfolioStrategy):
        selector = TopN(2)
        rebalance = EveryNTradingDays(1)

        @factor
        def alpha(self):
            return self.close - self.close

        @signal
        def score(self):
            return self.alpha()

    target = AllEqualScore().generate_signals(_panel()).target_weights
    assert target.iloc[:, :2].eq(0.5).all().all()
    assert target.iloc[:, 2:].eq(0.0).all().all()
