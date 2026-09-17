"""TEMA、SMI、Ulcer Index 与 STC 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "triple_exponential_moving_average_a_share_event": (
        "TripleExponentialMovingAverageAShareEventStrategy",
        frozenset({"close"}),
    ),
    "stochastic_momentum_index_a_share_event": (
        "StochasticMomentumIndexAShareEventStrategy",
        frozenset({"high", "low", "close"}),
    ),
    "ulcer_index_low_drawdown_a_share_event": (
        "UlcerIndexLowDrawdownAShareEventStrategy",
        frozenset({"close"}),
    ),
    "schaff_trend_cycle_a_share_event": (
        "SchaffTrendCycleAShareEventStrategy",
        frozenset({"close"}),
    ),
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=360, symbols=12):
    dates = pd.bdate_range("2023-01-02", periods=days)
    steps = np.arange(days, dtype=float)
    close = pd.DataFrame(
        {
            f"0000{index:02d}.SZ": 20
            + steps * (0.025 + index * 0.0007)
            + 1.5 * np.sin(steps / (4.0 + index / 5))
            for index in range(symbols)
        },
        index=dates,
    )
    return {
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
    }


def test_four_strategies_are_catalogued_with_real_field_contracts():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id, (entrypoint, required_fields) in STRATEGIES.items():
        assert assets[strategy_id]["execution_mode"] == "event"
        strategy_class = _strategy(strategy_id)
        assert strategy_class.__name__ == entrypoint
        assert strategy_class.execution_mode == "event"
        assert strategy_class.required_fields == required_fields
        assert len(StrategyCatalog().load(strategy_id).code_hash) == 64


def test_core_formulas_match_independent_reference_calculations():
    index = pd.bdate_range("2023-01-02", periods=260)
    steps = np.arange(len(index), dtype=float)
    close = pd.Series(
        np.linspace(10.0, 42.0, len(index)) + 1.5 * np.sin(steps / 4.0),
        index=index,
        name="close",
    )
    high = close * 1.02
    low = close * 0.98

    tema_class = _strategy("triple_exponential_moving_average_a_share_event")
    actual_tema = tema_class._tema(close)
    ema1 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema2 = ema1.ewm(span=20, adjust=False, min_periods=20).mean()
    ema3 = ema2.ewm(span=20, adjust=False, min_periods=20).mean()
    pd.testing.assert_series_equal(actual_tema, 3 * ema1 - 3 * ema2 + ema3)

    smi_class = _strategy("stochastic_momentum_index_a_share_event")
    actual_smi = smi_class._smi(high, low, close)
    highest = high.rolling(14, min_periods=14).max()
    lowest = low.rolling(14, min_periods=14).min()
    midpoint = (highest + lowest) / 2
    half_range = (highest - lowest) / 2
    smooth_distance = (close - midpoint).ewm(
        span=3, adjust=False, min_periods=3
    ).mean().ewm(span=3, adjust=False, min_periods=3).mean()
    smooth_range = half_range.ewm(
        span=3, adjust=False, min_periods=3
    ).mean().ewm(span=3, adjust=False, min_periods=3).mean()
    expected_smi = 100 * smooth_distance / smooth_range.where(smooth_range.ne(0))
    pd.testing.assert_series_equal(actual_smi, expected_smi)

    ulcer_class = _strategy("ulcer_index_low_drawdown_a_share_event")
    actual_ulcer = ulcer_class._ulcer_index(close)
    rolling_max = close.rolling(14, min_periods=14).max()
    drawdown_pct = 100 * (close - rolling_max) / (rolling_max.abs() + 1e-10)
    expected_ulcer = drawdown_pct.pow(2).rolling(
        14, min_periods=14
    ).mean().pow(0.5)
    pd.testing.assert_series_equal(actual_ulcer, expected_ulcer)

    stc_class = _strategy("schaff_trend_cycle_a_share_event")
    actual_stc = stc_class._stc(close)
    fast = close.ewm(span=23, adjust=False, min_periods=23).mean()
    slow = close.ewm(span=50, adjust=False, min_periods=50).mean()
    macd = fast - slow
    first_low = macd.rolling(10, min_periods=10).min()
    first_high = macd.rolling(10, min_periods=10).max()
    first_range = first_high - first_low
    first_value = (100 * (macd - first_low) / first_range).where(first_range > 0)
    first_smoothed = first_value.ewm(
        span=3, adjust=False, min_periods=3
    ).mean()
    second_low = first_smoothed.rolling(10, min_periods=10).min()
    second_high = first_smoothed.rolling(10, min_periods=10).max()
    second_range = second_high - second_low
    second_value = (
        100 * (first_smoothed - second_low) / second_range
    ).where(second_range > 0)
    expected_stc = second_value.ewm(
        span=3, adjust=False, min_periods=3
    ).mean()
    pd.testing.assert_series_equal(actual_stc, expected_stc)


def test_indicators_do_not_change_when_a_future_extreme_bar_is_appended():
    index = pd.bdate_range("2023-01-02", periods=260)
    steps = np.arange(len(index), dtype=float)
    close = pd.Series(
        np.linspace(10.0, 30.0, len(index)) + np.sin(steps / 4.0),
        index=index,
    )
    high = close * 1.02
    low = close * 0.98
    future_index = close.index[-1] + pd.offsets.BDay()
    extended_close = pd.concat([close, pd.Series([9_000.0], index=[future_index])])
    extended_high = pd.concat([high, pd.Series([9_100.0], index=[future_index])])
    extended_low = pd.concat([low, pd.Series([8_900.0], index=[future_index])])

    tema_class = _strategy("triple_exponential_moving_average_a_share_event")
    pd.testing.assert_series_equal(
        tema_class._tema(close),
        tema_class._tema(extended_close).iloc[:-1],
        check_freq=False,
    )

    smi_class = _strategy("stochastic_momentum_index_a_share_event")
    pd.testing.assert_series_equal(
        smi_class._smi(high, low, close),
        smi_class._smi(extended_high, extended_low, extended_close).iloc[:-1],
        check_freq=False,
    )

    ulcer_class = _strategy("ulcer_index_low_drawdown_a_share_event")
    pd.testing.assert_series_equal(
        ulcer_class._ulcer_index(close),
        ulcer_class._ulcer_index(extended_close).iloc[:-1],
        check_freq=False,
    )

    stc_class = _strategy("schaff_trend_cycle_a_share_event")
    pd.testing.assert_series_equal(
        stc_class._stc(close),
        stc_class._stc(extended_close).iloc[:-1],
        check_freq=False,
    )


def test_event_strategies_run_with_previous_close_visibility_and_valid_positions():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"
        assert all(
            sum(quantity > 0 for quantity in snapshot.positions.values()) <= 10
            for snapshot in result.position_snapshots
        )
        assert all(
            quantity >= 0
            for snapshot in result.position_snapshots
            for quantity in snapshot.positions.values()
        )
        assert all(
            order.target_value is None or order.target_value >= 0
            for order in result.orders
        )


@pytest.mark.parametrize("strategy_id", STRATEGIES)
def test_strategies_reject_missing_declared_fields(strategy_id):
    strategy = _strategy(strategy_id)()
    required_fields = STRATEGIES[strategy_id][1]

    class Data:
        fields = frozenset({"open", "high", "low", "close"} - required_fields)

    class Context:
        data = Data()

    with pytest.raises(ValueError, match="策略缺少数据字段"):
        strategy.initialize(Context())


@pytest.mark.parametrize("strategy_id", STRATEGIES)
def test_rebalance_respects_holding_and_weight_limits(strategy_id):
    strategy = _strategy(strategy_id)(max_holdings=3, single_weight=0.2)
    symbols = [f"0000{i:02d}.SZ" for i in range(8)]
    strategy._metrics = lambda history, requested: {
        symbol: {"close": 10.0, "entry": True, "exit": False, "score": float(index)}
        for index, symbol in enumerate(requested)
    }

    class Data:
        fields = frozenset({"open", "high", "low", "close"})

        def __init__(self):
            self.symbols = symbols

        @staticmethod
        def history(requested, fields, count):
            return {field: pd.DataFrame() for field in fields}

    class Portfolio:
        positions = {}
        cash = 1_000_000.0

        @staticmethod
        def quantity(symbol):
            return 0

    class Orders:
        def __init__(self):
            self.targets = []

        def target_value(self, symbol, value):
            self.targets.append((symbol, value))

        @staticmethod
        def close(symbol):
            raise AssertionError("空仓不应提交平仓订单")

    class Context:
        data = Data()
        portfolio = Portfolio()
        orders = Orders()

    context = Context()
    strategy.rebalance(context)
    assert len(context.orders.targets) == 3
    assert all(value == pytest.approx(200_000.0) for _, value in context.orders.targets)
