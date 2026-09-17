"""AO、BOP、Choppiness 与 Coppock 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "awesome_oscillator_a_share_event": "AwesomeOscillatorAShareEventStrategy",
    "balance_of_power_a_share_event": "BalanceOfPowerAShareEventStrategy",
    "choppiness_breakout_a_share_event": "ChoppinessBreakoutAShareEventStrategy",
    "coppock_curve_a_share_event": "CoppockCurveAShareEventStrategy",
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=220, symbols=12):
    dates = pd.bdate_range("2023-01-02", periods=days)
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    steps = np.arange(days, dtype=float)
    close = pd.DataFrame(
        {
            code: 20 + steps * (0.02 + index * 0.001) + np.sin(steps / (4 + index))
            for index, code in enumerate(codes)
        },
        index=dates,
    )
    open_ = close * (1.0 + 0.003 * np.sin(steps[:, None] / 3.0))
    open_.columns = codes
    return {
        "open": open_,
        "high": pd.DataFrame(np.maximum(open_, close) + 0.2, index=dates, columns=codes),
        "low": pd.DataFrame(np.minimum(open_, close) - 0.2, index=dates, columns=codes),
        "close": close,
    }


def test_four_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id, entrypoint in STRATEGIES.items():
        assert assets[strategy_id]["execution_mode"] == "event"
        strategy_class = _strategy(strategy_id)
        assert strategy_class.__name__ == entrypoint
        assert strategy_class.required_fields == frozenset({"open", "high", "low", "close"})


def test_awesome_oscillator_and_balance_of_power_match_reference_formulae():
    close = pd.Series(np.linspace(10.0, 30.0, 80) + np.sin(np.arange(80)), dtype=float)
    open_ = close - np.cos(np.arange(80)) * 0.2
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.5
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.5

    ao_class = _strategy("awesome_oscillator_a_share_event")
    actual_ao = ao_class._awesome_oscillator(high, low, 5, 34)
    midpoint = (high + low) / 2.0
    expected_ao = midpoint.rolling(5).mean() - midpoint.rolling(34).mean()
    pd.testing.assert_series_equal(actual_ao, expected_ao)

    bop_class = _strategy("balance_of_power_a_share_event")
    actual_bop = bop_class._balance_of_power(open_, high, low, close)
    expected_bop = (close - open_) / (high - low + 1e-10)
    pd.testing.assert_series_equal(actual_bop, expected_bop)


def test_choppiness_and_coppock_match_reference_formulae():
    close = pd.Series(np.linspace(10.0, 30.0, 80) + np.sin(np.arange(80)), dtype=float)
    high, low = close + 0.8, close - 0.7

    choppiness_class = _strategy("choppiness_breakout_a_share_event")
    actual_choppiness = choppiness_class._choppiness_index(high, low, close, 14)
    previous_close = close.shift()
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    expected_choppiness = 100.0 * np.log10(
        (true_range.rolling(14).sum() / (high.rolling(14).max() - low.rolling(14).min() + 1e-10)).clip(lower=1e-10)
    ) / np.log10(14)
    pd.testing.assert_series_equal(actual_choppiness, expected_choppiness)

    coppock_class = _strategy("coppock_curve_a_share_event")
    actual_coppock = coppock_class._coppock_curve(close, 11, 14, 10)
    rate_of_change = close.pct_change(11) * 100.0 + close.pct_change(14) * 100.0
    weights = np.arange(1, 11, dtype=float)
    expected_coppock = rate_of_change.rolling(10).apply(
        lambda values: np.dot(values, weights) / weights.sum(), raw=True
    )
    pd.testing.assert_series_equal(actual_coppock, expected_coppock)


def test_indicators_do_not_change_when_a_future_bar_is_appended():
    panels = _panels(days=100, symbols=1)
    open_ = panels["open"].iloc[:, 0]
    high = panels["high"].iloc[:, 0]
    low = panels["low"].iloc[:, 0]
    close = panels["close"].iloc[:, 0]
    future_index = close.index[-1] + pd.offsets.BDay()

    def append(series, value):
        return pd.concat([series, pd.Series([value], index=[future_index])])

    calculations = [
        (
            _strategy("awesome_oscillator_a_share_event")._awesome_oscillator(high, low),
            _strategy("awesome_oscillator_a_share_event")._awesome_oscillator(
                append(high, 10_000.0), append(low, 1.0)
            ),
        ),
        (
            _strategy("balance_of_power_a_share_event")._balance_of_power(open_, high, low, close),
            _strategy("balance_of_power_a_share_event")._balance_of_power(
                append(open_, 1.0), append(high, 10_000.0), append(low, 0.1), append(close, 9_000.0)
            ),
        ),
        (
            _strategy("choppiness_breakout_a_share_event")._choppiness_index(high, low, close),
            _strategy("choppiness_breakout_a_share_event")._choppiness_index(
                append(high, 10_000.0), append(low, 0.1), append(close, 9_000.0)
            ),
        ),
        (
            _strategy("coppock_curve_a_share_event")._coppock_curve(close),
            _strategy("coppock_curve_a_share_event")._coppock_curve(append(close, 9_000.0)),
        ),
    ]
    for original, extended in calculations:
        pd.testing.assert_series_equal(
            original, extended.iloc[:-1], check_freq=False, check_names=False
        )


def test_event_strategies_run_with_previous_close_visibility_and_valid_positions():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"
        assert all(len(snapshot.positions) <= 10 for snapshot in result.position_snapshots)
        assert all(quantity >= 0 for snapshot in result.position_snapshots for quantity in snapshot.positions.values())


@pytest.mark.parametrize("strategy_id", STRATEGIES)
def test_strategies_reject_missing_required_fields(strategy_id):
    strategy = _strategy(strategy_id)()

    class Data:
        fields = frozenset({"open", "low", "close"})

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

        def history(self, requested, fields, count):
            return {}

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
