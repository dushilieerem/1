"""BBI、Mass Index、VHF 与 WVAD 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.quantcore import EventBacktestEngine
from app.repositories.catalogs.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "bbi_trend_a_share_event": (
        "BbiTrendAShareEventStrategy",
        frozenset({"close"}),
    ),
    "mass_index_reversal_a_share_event": (
        "MassIndexReversalAShareEventStrategy",
        frozenset({"high", "low", "close"}),
    ),
    "vhf_trend_a_share_event": (
        "VhfTrendAShareEventStrategy",
        frozenset({"close"}),
    ),
    "wvad_volume_trend_a_share_event": (
        "WvadVolumeTrendAShareEventStrategy",
        frozenset({"open", "high", "low", "close", "volume"}),
    ),
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=320, symbols=12):
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
        "volume": pd.DataFrame(
            {
                symbol: 1_000_000.0 + steps * (1_000.0 + index * 10.0)
                for index, symbol in enumerate(close.columns)
            },
            index=dates,
        ),
    }


def test_four_strategies_are_catalogued_with_real_field_contracts():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id, (entrypoint, required_fields) in STRATEGIES.items():
        assert assets[strategy_id]["execution_mode"] == "event"
        strategy_class = _strategy(strategy_id)
        assert strategy_class.__name__ == entrypoint
        assert strategy_class.execution_mode == "event"
        assert strategy_class.required_fields == required_fields


def test_core_formulas_match_existing_factor_library_definitions():
    index = pd.bdate_range("2023-01-02", periods=180)
    steps = np.arange(len(index), dtype=float)
    close = pd.Series(
        np.linspace(10.0, 42.0, len(index)) + 1.5 * np.sin(steps / 4.0),
        index=index,
        name="close",
    )
    open_ = close * 0.998
    high = close * 1.02
    low = close * 0.98
    volume = pd.Series(1_000_000.0 + steps * 1_000.0, index=index, name="volume")

    bbi_class = _strategy("bbi_trend_a_share_event")
    actual_bbi = bbi_class._bbi(close)
    expected_bbi = sum(
        close.rolling(window, min_periods=window).mean()
        for window in (3, 6, 12, 24)
    ) / 4
    pd.testing.assert_series_equal(actual_bbi, expected_bbi)

    mass_class = _strategy("mass_index_reversal_a_share_event")
    actual_mass = mass_class._mass_index(high, low)
    spread = high - low
    first_average = spread.rolling(9, min_periods=9).mean()
    second_average = first_average.rolling(9, min_periods=9).mean()
    expected_mass = (first_average / second_average.where(second_average.ne(0))).rolling(
        25, min_periods=25
    ).sum()
    pd.testing.assert_series_equal(actual_mass, expected_mass)

    vhf_class = _strategy("vhf_trend_a_share_event")
    actual_vhf = vhf_class._vhf(close)
    expected_vhf = (
        close.rolling(28, min_periods=28).max()
        - close.rolling(28, min_periods=28).min()
    ) / close.diff().abs().rolling(28, min_periods=28).sum()
    pd.testing.assert_series_equal(actual_vhf, expected_vhf)

    wvad_class = _strategy("wvad_volume_trend_a_share_event")
    actual_wvad = wvad_class._wvad(open_, high, low, close, volume)
    expected_wvad = ((close - open_) / (high - low) * volume).rolling(
        24, min_periods=24
    ).sum()
    pd.testing.assert_series_equal(actual_wvad, expected_wvad)


def test_indicators_do_not_change_when_a_future_extreme_bar_is_appended():
    index = pd.bdate_range("2023-01-02", periods=180)
    steps = np.arange(len(index), dtype=float)
    close = pd.Series(
        np.linspace(10.0, 30.0, len(index)) + np.sin(steps / 4.0),
        index=index,
    )
    open_ = close * 0.998
    high = close * 1.02
    low = close * 0.98
    volume = pd.Series(1_000_000.0 + steps * 1_000.0, index=index)
    future_index = close.index[-1] + pd.offsets.BDay()
    extended_close = pd.concat([close, pd.Series([9_000.0], index=[future_index])])
    extended_open = pd.concat([open_, pd.Series([8_950.0], index=[future_index])])
    extended_high = pd.concat([high, pd.Series([9_100.0], index=[future_index])])
    extended_low = pd.concat([low, pd.Series([8_900.0], index=[future_index])])
    extended_volume = pd.concat([volume, pd.Series([9_000_000.0], index=[future_index])])

    bbi_class = _strategy("bbi_trend_a_share_event")
    pd.testing.assert_series_equal(
        bbi_class._bbi(close),
        bbi_class._bbi(extended_close).iloc[:-1],
        check_freq=False,
    )

    mass_class = _strategy("mass_index_reversal_a_share_event")
    pd.testing.assert_series_equal(
        mass_class._mass_index(high, low),
        mass_class._mass_index(extended_high, extended_low).iloc[:-1],
        check_freq=False,
    )

    vhf_class = _strategy("vhf_trend_a_share_event")
    pd.testing.assert_series_equal(
        vhf_class._vhf(close),
        vhf_class._vhf(extended_close).iloc[:-1],
        check_freq=False,
    )

    wvad_class = _strategy("wvad_volume_trend_a_share_event")
    pd.testing.assert_series_equal(
        wvad_class._wvad(open_, high, low, close, volume),
        wvad_class._wvad(
            extended_open,
            extended_high,
            extended_low,
            extended_close,
            extended_volume,
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
        fields = frozenset({"open", "high", "low", "close", "volume"} - required_fields)

    class Context:
        data = Data()

    with pytest.raises(ValueError, match="策略缺少数据字段"):
        strategy.initialize(Context())


def test_wvad_treats_zero_range_bars_as_zero_flow():
    index = pd.bdate_range("2023-01-02", periods=24)
    open_ = pd.Series(10.0, index=index)
    high = pd.Series(10.0, index=index)
    low = pd.Series(10.0, index=index)
    close = pd.Series(10.0, index=index)
    volume = pd.Series(1_000_000.0, index=index)

    result = _strategy("wvad_volume_trend_a_share_event")._wvad(
        open_, high, low, close, volume
    )
    assert result.iloc[-1] == pytest.approx(0.0)


@pytest.mark.parametrize("strategy_id", STRATEGIES)
def test_rebalance_respects_holding_and_weight_limits(strategy_id):
    strategy = _strategy(strategy_id)(max_holdings=3, single_weight=0.2)
    symbols = [f"0000{i:02d}.SZ" for i in range(8)]
    strategy._metrics = lambda history, requested: {
        symbol: {"close": 10.0, "entry": True, "exit": False, "score": float(index)}
        for index, symbol in enumerate(requested)
    }

    class Data:
        fields = frozenset({"open", "high", "low", "close", "volume"})

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
