"""Connors RSI(2)、Supertrend、HMA 与 Williams Alligator 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "connors_rsi2_a_share_event": (
        "ConnorsRsi2AShareEventStrategy",
        frozenset({"close"}),
    ),
    "supertrend_a_share_event": (
        "SupertrendAShareEventStrategy",
        frozenset({"high", "low", "close"}),
    ),
    "hull_moving_average_a_share_event": (
        "HullMovingAverageAShareEventStrategy",
        frozenset({"close"}),
    ),
    "williams_alligator_a_share_event": (
        "WilliamsAlligatorAShareEventStrategy",
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
            + steps * (0.018 + index * 0.0007)
            + 1.5 * np.sin(steps / (3.5 + index / 4))
            + 0.4 * np.cos(steps / (8 + index))
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


def test_core_indicator_formulas_match_reference_calculations():
    close = pd.Series(
        np.linspace(10.0, 42.0, 160) + 1.5 * np.sin(np.arange(160) / 4.0),
        index=pd.bdate_range("2023-01-02", periods=160),
        name="close",
    )
    high = close * 1.02
    low = close * 0.98

    rsi_class = _strategy("connors_rsi2_a_share_event")
    actual_rsi = rsi_class._rsi(close, 2)
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    average_gain = gains.ewm(alpha=0.5, adjust=False, min_periods=2).mean()
    average_loss = losses.ewm(alpha=0.5, adjust=False, min_periods=2).mean()
    expected_rsi = 100 - 100 / (1 + average_gain / average_loss.replace(0, float("nan")))
    expected_rsi = expected_rsi.where(average_loss > 0, 100.0)
    pd.testing.assert_series_equal(actual_rsi, expected_rsi)

    supertrend_class = _strategy("supertrend_a_share_event")
    actual_supertrend = supertrend_class._supertrend(high, low, close, 10, 3.0)
    previous_close = close.shift()
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    expected_atr = true_range.ewm(alpha=0.1, adjust=False, min_periods=10).mean()
    pd.testing.assert_series_equal(
        actual_supertrend["atr"], expected_atr, check_names=False
    )
    valid_direction = actual_supertrend["direction"].dropna()
    assert set(valid_direction.unique()).issubset({-1.0, 1.0})
    positive = actual_supertrend["direction"] > 0
    assert (
        actual_supertrend.loc[positive, "supertrend"]
        == actual_supertrend.loc[positive, "lower"]
    ).all()

    hma_class = _strategy("hull_moving_average_a_share_event")
    actual_hma = hma_class._hull_moving_average(close, 20)

    def wma(series, window):
        weights = np.arange(1, window + 1, dtype=float)
        return series.rolling(window, min_periods=window).apply(
            lambda values: float(np.dot(values, weights) / weights.sum()),
            raw=True,
        )

    expected_hma = wma(2 * wma(close, 10) - wma(close, 20), 4)
    pd.testing.assert_series_equal(actual_hma, expected_hma)

    alligator_class = _strategy("williams_alligator_a_share_event")
    actual_alligator = alligator_class._alligator(high, low, close)
    midpoint = (high + low) / 2
    expected_alligator = pd.DataFrame(
        {
            "jaw": midpoint.ewm(alpha=1 / 13, adjust=False, min_periods=13).mean().shift(8),
            "teeth": midpoint.ewm(alpha=1 / 8, adjust=False, min_periods=8).mean().shift(5),
            "lips": midpoint.ewm(alpha=1 / 5, adjust=False, min_periods=5).mean().shift(3),
        },
        index=close.index,
    )
    pd.testing.assert_frame_equal(actual_alligator, expected_alligator)


def test_indicators_do_not_change_when_a_future_extreme_bar_is_appended():
    close = pd.Series(
        np.linspace(10.0, 30.0, 160) + np.sin(np.arange(160) / 4.0),
        index=pd.bdate_range("2023-01-02", periods=160),
    )
    future_index = close.index[-1] + pd.offsets.BDay()
    extended_close = pd.concat([close, pd.Series([9_000.0], index=[future_index])])
    high = close * 1.02
    low = close * 0.98
    extended_high = pd.concat([high, pd.Series([9_100.0], index=[future_index])])
    extended_low = pd.concat([low, pd.Series([8_900.0], index=[future_index])])

    rsi_class = _strategy("connors_rsi2_a_share_event")
    pd.testing.assert_series_equal(
        rsi_class._rsi(close),
        rsi_class._rsi(extended_close).iloc[:-1],
        check_freq=False,
    )

    supertrend_class = _strategy("supertrend_a_share_event")
    pd.testing.assert_frame_equal(
        supertrend_class._supertrend(high, low, close),
        supertrend_class._supertrend(extended_high, extended_low, extended_close).iloc[:-1],
        check_freq=False,
    )

    hma_class = _strategy("hull_moving_average_a_share_event")
    pd.testing.assert_series_equal(
        hma_class._hull_moving_average(close),
        hma_class._hull_moving_average(extended_close).iloc[:-1],
        check_freq=False,
    )

    alligator_class = _strategy("williams_alligator_a_share_event")
    pd.testing.assert_frame_equal(
        alligator_class._alligator(high, low, close),
        alligator_class._alligator(extended_high, extended_low, extended_close).iloc[:-1],
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
