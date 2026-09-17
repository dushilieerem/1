"""KAMA、McGinley Dynamic、Heikin-Ashi 与 Pivot Point 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "kaufman_adaptive_moving_average_a_share_event": (
        "KaufmanAdaptiveMovingAverageAShareEventStrategy",
        frozenset({"close"}),
    ),
    "mcginley_dynamic_a_share_event": (
        "McGinleyDynamicAShareEventStrategy",
        frozenset({"close"}),
    ),
    "heikin_ashi_trend_a_share_event": (
        "HeikinAshiTrendAShareEventStrategy",
        frozenset({"open", "high", "low", "close"}),
    ),
    "pivot_point_breakout_a_share_event": (
        "PivotPointBreakoutAShareEventStrategy",
        frozenset({"high", "low", "close"}),
    ),
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=280, symbols=12):
    dates = pd.bdate_range("2023-01-02", periods=days)
    steps = np.arange(days, dtype=float)
    close = pd.DataFrame(
        {
            f"0000{index:02d}.SZ": 20
            + steps * (0.02 + index * 0.0008)
            + 1.4 * np.sin(steps / (4.0 + index / 4))
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


def test_core_formulas_match_independent_reference_calculations():
    index = pd.bdate_range("2023-01-02", periods=180)
    close = pd.Series(
        np.linspace(10.0, 42.0, len(index)) + 1.5 * np.sin(np.arange(len(index)) / 4.0),
        index=index,
        name="close",
    )
    open_ = close * 0.998
    high = close * 1.02
    low = close * 0.98

    kama_class = _strategy("kaufman_adaptive_moving_average_a_share_event")
    actual_kama = kama_class._kama(close, 10, 2, 30)
    change = close.diff(10).abs()
    volatility = close.diff().abs().rolling(10, min_periods=10).sum()
    efficiency_ratio = (change / volatility).where(volatility.notna())
    efficiency_ratio = efficiency_ratio.where(volatility.ne(0), 0.0)
    smoothing = (
        efficiency_ratio * (2 / 3 - 2 / 31) + 2 / 31
    ) ** 2
    expected_values = np.full(len(close), np.nan, dtype=float)
    for position in range(len(close)):
        if pd.isna(smoothing.iloc[position]):
            continue
        if position == 0 or pd.isna(expected_values[position - 1]):
            expected_values[position] = close.iloc[position]
        else:
            expected_values[position] = expected_values[position - 1] + smoothing.iloc[position] * (
                close.iloc[position] - expected_values[position - 1]
            )
    expected_kama = pd.Series(expected_values, index=close.index, name="close")
    pd.testing.assert_series_equal(actual_kama, expected_kama)

    mcginley_class = _strategy("mcginley_dynamic_a_share_event")
    actual_mcginley = mcginley_class._mcginley_dynamic(close, 14, 0.6)
    expected_values = np.full(len(close), np.nan, dtype=float)
    for position, price in enumerate(close):
        if position == 0 or pd.isna(expected_values[position - 1]):
            expected_values[position] = price
            continue
        previous = expected_values[position - 1]
        ratio = max(float(price) / max(abs(previous), 1e-8), 1e-8)
        expected_values[position] = previous + (price - previous) / (0.6 * 14 * ratio**4)
    expected_mcginley = pd.Series(expected_values, index=close.index, name="close")
    pd.testing.assert_series_equal(actual_mcginley, expected_mcginley)

    heikin_class = _strategy("heikin_ashi_trend_a_share_event")
    actual_heikin = heikin_class._heikin_ashi(open_, high, low, close)
    expected_close = (open_ + high + low + close) / 4.0
    expected_open = pd.Series(np.nan, index=close.index, dtype=float)
    expected_open.iloc[0] = (open_.iloc[0] + close.iloc[0]) / 2.0
    for position in range(1, len(close)):
        expected_open.iloc[position] = (
            expected_open.iloc[position - 1] + expected_close.iloc[position - 1]
        ) / 2.0
    expected_heikin = pd.DataFrame(
        {
            "open": expected_open,
            "high": pd.concat([high, expected_open, expected_close], axis=1).max(axis=1),
            "low": pd.concat([low, expected_open, expected_close], axis=1).min(axis=1),
            "close": expected_close,
        },
        index=close.index,
    )
    pd.testing.assert_frame_equal(actual_heikin, expected_heikin)

    pivot_class = _strategy("pivot_point_breakout_a_share_event")
    actual_pivots = pivot_class._pivot_levels(high, low, close)
    previous_high = high.shift(1)
    previous_low = low.shift(1)
    previous_close = close.shift(1)
    expected_pivot = (previous_high + previous_low + previous_close) / 3.0
    expected_pivots = pd.DataFrame(
        {
            "pivot": expected_pivot,
            "resistance": 2 * expected_pivot - previous_low,
            "support": 2 * expected_pivot - previous_high,
        },
        index=close.index,
    )
    pd.testing.assert_frame_equal(actual_pivots, expected_pivots)


def test_indicators_do_not_change_when_a_future_extreme_bar_is_appended():
    index = pd.bdate_range("2023-01-02", periods=160)
    close = pd.Series(
        np.linspace(10.0, 30.0, len(index)) + np.sin(np.arange(len(index)) / 4.0),
        index=index,
    )
    open_ = close * 0.998
    high = close * 1.02
    low = close * 0.98
    future_index = close.index[-1] + pd.offsets.BDay()
    extended_close = pd.concat([close, pd.Series([9_000.0], index=[future_index])])
    extended_open = pd.concat([open_, pd.Series([8_950.0], index=[future_index])])
    extended_high = pd.concat([high, pd.Series([9_100.0], index=[future_index])])
    extended_low = pd.concat([low, pd.Series([8_900.0], index=[future_index])])

    kama_class = _strategy("kaufman_adaptive_moving_average_a_share_event")
    pd.testing.assert_series_equal(
        kama_class._kama(close),
        kama_class._kama(extended_close).iloc[:-1],
        check_freq=False,
    )
    mcginley_class = _strategy("mcginley_dynamic_a_share_event")
    pd.testing.assert_series_equal(
        mcginley_class._mcginley_dynamic(close),
        mcginley_class._mcginley_dynamic(extended_close).iloc[:-1],
        check_freq=False,
    )
    heikin_class = _strategy("heikin_ashi_trend_a_share_event")
    pd.testing.assert_frame_equal(
        heikin_class._heikin_ashi(open_, high, low, close),
        heikin_class._heikin_ashi(
            extended_open,
            extended_high,
            extended_low,
            extended_close,
        ).iloc[:-1],
        check_freq=False,
    )
    pivot_class = _strategy("pivot_point_breakout_a_share_event")
    pd.testing.assert_frame_equal(
        pivot_class._pivot_levels(high, low, close),
        pivot_class._pivot_levels(
            extended_high,
            extended_low,
            extended_close,
        ).iloc[:-1],
        check_freq=False,
    )


def test_event_strategies_run_with_previous_close_visibility_and_valid_positions():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"
        assert all(len(snapshot.positions) <= 10 for snapshot in result.position_snapshots)
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
