"""Elder Ray、Klinger、RMI 与 FRAMA 策略迁移验收测试。"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "elder_ray_index_a_share_event": (
        "ElderRayIndexAShareEventStrategy",
        frozenset({"high", "low", "close"}),
    ),
    "klinger_volume_oscillator_a_share_event": (
        "KlingerVolumeOscillatorAShareEventStrategy",
        frozenset({"high", "low", "close", "volume"}),
    ),
    "relative_momentum_index_a_share_event": (
        "RelativeMomentumIndexAShareEventStrategy",
        frozenset({"close"}),
    ),
    "fractal_adaptive_moving_average_a_share_event": (
        "FractalAdaptiveMovingAverageAShareEventStrategy",
        frozenset({"close"}),
    ),
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=260, symbols=12):
    dates = pd.bdate_range("2023-01-02", periods=days)
    steps = np.arange(days, dtype=float)
    close = pd.DataFrame(
        {
            f"0000{index:02d}.SZ": 20
            + steps * (0.02 + index * 0.0008)
            + 1.4 * np.sin(steps / (4.0 + index / 5))
            for index in range(symbols)
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            f"0000{index:02d}.SZ": 1_000_000 + 10_000 * index + steps * 500
            for index in range(symbols)
        },
        index=dates,
    )
    return {
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
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
    volume = pd.Series(1_000_000 + steps * 2_000, index=index, name="volume")

    elder = _strategy("elder_ray_index_a_share_event")
    actual_elder = elder._elder_ray(high, low, close)
    expected_ema = close.ewm(span=13, adjust=False, min_periods=13).mean()
    pd.testing.assert_series_equal(
        actual_elder["ema"], expected_ema.rename("ema")
    )
    pd.testing.assert_series_equal(
        actual_elder["bull_power"], (high - expected_ema).rename("bull_power")
    )
    pd.testing.assert_series_equal(
        actual_elder["bear_power"], (low - expected_ema).rename("bear_power")
    )

    klinger = _strategy("klinger_volume_oscillator_a_share_event")
    actual_klinger = klinger._klinger(high, low, close, volume)
    typical = (high + low + close) / 3.0
    direction = typical.diff().ge(0).astype(float).replace(0.0, -1.0)
    direction.iloc[0] = 0.0
    daily_measure = (high - low).abs()
    cumulative_measure = daily_measure.ewm(
        span=55, adjust=False, min_periods=55
    ).mean()
    ratio = daily_measure / cumulative_measure.where(cumulative_measure > 0)
    volume_force = direction * volume * (2.0 * ratio - 1.0).abs()
    expected_ko = volume_force.ewm(
        span=34, adjust=False, min_periods=34
    ).mean() - volume_force.ewm(
        span=55, adjust=False, min_periods=55
    ).mean()
    expected_signal = expected_ko.ewm(
        span=13, adjust=False, min_periods=13
    ).mean()
    pd.testing.assert_series_equal(
        actual_klinger["ko"], expected_ko.rename("ko")
    )
    pd.testing.assert_series_equal(
        actual_klinger["signal"], expected_signal.rename("signal")
    )

    rmi = _strategy("relative_momentum_index_a_share_event")
    actual_rmi = rmi._rmi(close)
    momentum = close.diff(5)
    gains = momentum.clip(lower=0.0)
    losses = (-momentum).clip(lower=0.0)
    average_gain = gains.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean()
    average_loss = losses.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean()
    expected_rmi = 100.0 - 100.0 / (
        1.0 + average_gain / average_loss.replace(0.0, float("nan"))
    )
    expected_rmi = expected_rmi.where(average_loss > 0, 100.0)
    pd.testing.assert_series_equal(actual_rmi, expected_rmi)

    frama = _strategy("fractal_adaptive_moving_average_a_share_event")
    actual_frama = frama._frama(close)
    expected_frama = _reference_frama(close, 16)
    pd.testing.assert_series_equal(actual_frama, expected_frama)


def _reference_frama(close: pd.Series, window: int) -> pd.Series:
    half = window // 2
    values = close.astype(float).to_numpy()
    output = [float("nan")] * len(values)
    for index in range(window - 1, len(values)):
        current = values[index]
        if index == window - 1 or not math.isfinite(output[index - 1]):
            output[index] = current
            continue
        first = values[index - window + 1 : index - half + 1]
        second = values[index - half + 1 : index + 1]
        full = values[index - window + 1 : index + 1]
        n1 = (max(first) - min(first)) / half
        n2 = (max(second) - min(second)) / half
        n3 = (max(full) - min(full)) / window
        if n3 <= 0 or n1 + n2 <= 0:
            alpha = 1.0
        else:
            dimension = (math.log(n1 + n2) - math.log(n3)) / math.log(2.0)
            alpha = min(1.0, max(0.01, math.exp(-4.6 * (dimension - 1.0))))
        output[index] = alpha * current + (1.0 - alpha) * output[index - 1]
    return pd.Series(output, index=close.index, name=close.name)


def test_indicators_are_causal_when_future_extreme_bars_are_appended():
    panels = _panels(days=190, symbols=1)
    close = panels["close"].iloc[:, 0]
    high = panels["high"].iloc[:, 0]
    low = panels["low"].iloc[:, 0]
    volume = panels["volume"].iloc[:, 0]
    future_index = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=20)
    future_close = pd.Series(10_000.0, index=future_index, name=close.name)
    future_high = pd.Series(12_000.0, index=future_index, name=high.name)
    future_low = pd.Series(9_000.0, index=future_index, name=low.name)
    future_volume = pd.Series(99_000_000.0, index=future_index, name=volume.name)

    elder = _strategy("elder_ray_index_a_share_event")
    pd.testing.assert_frame_equal(
        elder._elder_ray(high, low, close),
        elder._elder_ray(
            pd.concat([high, future_high]),
            pd.concat([low, future_low]),
            pd.concat([close, future_close]),
        ).iloc[: len(close)],
    )
    klinger = _strategy("klinger_volume_oscillator_a_share_event")
    pd.testing.assert_frame_equal(
        klinger._klinger(high, low, close, volume),
        klinger._klinger(
            pd.concat([high, future_high]),
            pd.concat([low, future_low]),
            pd.concat([close, future_close]),
            pd.concat([volume, future_volume]),
        ).iloc[: len(close)],
    )
    rmi = _strategy("relative_momentum_index_a_share_event")
    pd.testing.assert_series_equal(
        rmi._rmi(close), rmi._rmi(pd.concat([close, future_close])).iloc[: len(close)]
    )
    frama = _strategy("fractal_adaptive_moving_average_a_share_event")
    pd.testing.assert_series_equal(
        frama._frama(close),
        frama._frama(pd.concat([close, future_close])).iloc[: len(close)],
    )


def test_four_strategies_run_on_daily_panels_with_previous_close_visibility():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(
            _strategy(strategy_id)(universe=list(panels["close"].columns))
        )
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"
        assert all(
            order.target_value is None or order.target_value >= 0
            for order in result.orders
        )
        assert max(
            sum(quantity > 0 for quantity in snapshot.positions.values())
            for snapshot in result.position_snapshots
        ) <= 10


class _Schedule:
    def daily(self, callback):
        return callback


class _Context:
    def __init__(self, fields):
        self.data = type("Data", (), {"fields": frozenset(fields)})()
        self.schedule = _Schedule()


@pytest.mark.parametrize(
    ("strategy_id", "fields"),
    [
        ("elder_ray_index_a_share_event", {"high", "low"}),
        ("klinger_volume_oscillator_a_share_event", {"high", "low", "close"}),
        ("relative_momentum_index_a_share_event", set()),
        ("fractal_adaptive_moving_average_a_share_event", set()),
    ],
)
def test_strategies_reject_missing_required_fields(strategy_id, fields):
    with pytest.raises(ValueError, match="缺少数据字段"):
        _strategy(strategy_id)().initialize(_Context(fields))
