"""DPO、TSI、StochRSI 与 RVI 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.quantcore import EventBacktestEngine
from app.repositories.catalogs.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "dpo_mean_reversion_a_share_event": "DetrendedPriceOscillatorAShareEventStrategy",
    "true_strength_index_a_share_event": "TrueStrengthIndexAShareEventStrategy",
    "stoch_rsi_a_share_event": "StochRsiAShareEventStrategy",
    "relative_volatility_index_a_share_event": "RelativeVolatilityIndexAShareEventStrategy",
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=240, symbols=12):
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
    return {
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
    }


def test_four_strategies_are_catalogued_as_close_only_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id, entrypoint in STRATEGIES.items():
        assert assets[strategy_id]["execution_mode"] == "event"
        strategy_class = _strategy(strategy_id)
        assert strategy_class.__name__ == entrypoint
        assert strategy_class.required_fields == frozenset({"close"})


def test_core_formulas_match_existing_technical_factor_definitions():
    close = pd.Series(np.linspace(10.0, 40.0, 120) + np.sin(np.arange(120) / 3.0), dtype=float)

    dpo_class = _strategy("dpo_mean_reversion_a_share_event")
    actual_dpo = dpo_class._dpo(close, 20)
    expected_dpo = close.shift(11) - close.rolling(20).mean()
    pd.testing.assert_series_equal(actual_dpo, expected_dpo)

    tsi_class = _strategy("true_strength_index_a_share_event")
    actual_tsi = tsi_class._true_strength_index(close, 25, 13)
    momentum = close.diff()
    smooth_momentum = momentum.ewm(span=25, adjust=False).mean().ewm(
        span=13, adjust=False
    ).mean()
    smooth_absolute = momentum.abs().ewm(span=25, adjust=False).mean().ewm(
        span=13, adjust=False
    ).mean()
    expected_tsi = 100 * smooth_momentum / (smooth_absolute + 1e-10)
    pd.testing.assert_series_equal(actual_tsi, expected_tsi)

    stoch_class = _strategy("stoch_rsi_a_share_event")
    actual_stoch = stoch_class._stoch_rsi(close, 14, 14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / (loss + 1e-10))
    expected_stoch = (rsi - rsi.rolling(14).min()) / (
        rsi.rolling(14).max() - rsi.rolling(14).min() + 1e-10
    )
    pd.testing.assert_series_equal(actual_stoch, expected_stoch)

    rvi_class = _strategy("relative_volatility_index_a_share_event")
    actual_rvi = rvi_class._relative_volatility_index(close, 10, 14)
    volatility = close.rolling(10).std(ddof=0)
    direction = close.diff()
    upside = volatility.where(direction > 0, 0.0).ewm(span=14, adjust=False).mean()
    downside = volatility.where(direction < 0, 0.0).ewm(span=14, adjust=False).mean()
    expected_rvi = 100 * upside / (upside + downside + 1e-10)
    pd.testing.assert_series_equal(actual_rvi, expected_rvi)


def test_indicators_do_not_change_when_a_future_bar_is_appended():
    close = pd.Series(
        np.linspace(10.0, 30.0, 120) + np.sin(np.arange(120) / 4.0),
        index=pd.bdate_range("2023-01-02", periods=120),
    )
    future_index = close.index[-1] + pd.offsets.BDay()

    def append(value):
        return pd.concat([close, pd.Series([value], index=[future_index])])

    calculations = [
        (
            _strategy("dpo_mean_reversion_a_share_event")._dpo(close),
            _strategy("dpo_mean_reversion_a_share_event")._dpo(append(9_000.0)),
        ),
        (
            _strategy("true_strength_index_a_share_event")._true_strength_index(close),
            _strategy("true_strength_index_a_share_event")._true_strength_index(append(9_000.0)),
        ),
        (
            _strategy("stoch_rsi_a_share_event")._stoch_rsi(close),
            _strategy("stoch_rsi_a_share_event")._stoch_rsi(append(9_000.0)),
        ),
        (
            _strategy("relative_volatility_index_a_share_event")._relative_volatility_index(close),
            _strategy("relative_volatility_index_a_share_event")._relative_volatility_index(
                append(9_000.0)
            ),
        ),
    ]
    for original, extended in calculations:
        pd.testing.assert_series_equal(
            original,
            extended.iloc[:-1],
            check_freq=False,
            check_names=False,
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


@pytest.mark.parametrize("strategy_id", STRATEGIES)
def test_strategies_reject_missing_close_field(strategy_id):
    strategy = _strategy(strategy_id)()

    class Data:
        fields = frozenset({"open", "high", "low"})

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
        fields = frozenset({"close"})

        def __init__(self):
            self.symbols = symbols

        def history(self, requested, fields, count):
            return {"close": pd.DataFrame()}

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
