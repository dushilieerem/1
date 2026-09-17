"""ARBR、PSY、VR 与 VROC 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "arbr_sentiment_a_share_event": (
        "ArbrSentimentAShareEventStrategy",
        frozenset({"open", "high", "low", "close"}),
    ),
    "psy_sentiment_a_share_event": (
        "PsySentimentAShareEventStrategy",
        frozenset({"close"}),
    ),
    "volume_ratio_a_share_event": (
        "VolumeRatioAShareEventStrategy",
        frozenset({"close", "volume"}),
    ),
    "volume_rate_of_change_a_share_event": (
        "VolumeRateOfChangeAShareEventStrategy",
        frozenset({"close", "volume"}),
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
            f"0000{index:02d}.SZ": 1_000_000
            + 10_000 * index
            + steps * 500
            + 30_000 * np.sin(steps / (8.0 + index))
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


def test_core_formulas_match_emotion_factor_references():
    index = pd.bdate_range("2023-01-02", periods=260)
    steps = np.arange(len(index), dtype=float)
    close = pd.Series(
        np.linspace(10.0, 42.0, len(index)) + 1.5 * np.sin(steps / 4.0),
        index=index,
        name="close",
    )
    open_ = close * 0.998
    high = close * 1.02
    low = close * 0.98
    volume = pd.Series(1_000_000 + steps * 2_000, index=index, name="volume")

    arbr = _strategy("arbr_sentiment_a_share_event")
    actual_arbr = arbr._arbr(open_, high, low, close)
    ar = (high - open_).rolling(26).sum() / (open_ - low).rolling(26).sum() * 100
    previous_close = close.shift()
    br_up = (high - previous_close).clip(lower=0)
    br_down = (previous_close - low).clip(lower=0)
    br = br_up.rolling(26).sum() / br_down.rolling(26).sum() * 100
    expected_arbr = pd.DataFrame({"ar": ar, "br": br, "arbr": ar - br}, index=index)
    pd.testing.assert_frame_equal(actual_arbr, expected_arbr)

    psy = _strategy("psy_sentiment_a_share_event")
    pd.testing.assert_series_equal(
        psy._psy(close),
        ((close.diff() > 0).rolling(12).mean() * 100).rename(close.name),
    )

    vr = _strategy("volume_ratio_a_share_event")
    actual_vr = vr._vr(close, volume)
    change = close.diff()
    up = volume.where(change > 0, 0.0)
    down = volume.where(change < 0, 0.0)
    flat = volume.where(change == 0, 0.0)
    expected_vr = (
        up.rolling(26).sum() + flat.rolling(26).sum() / 2
    ) / (down.rolling(26).sum() + flat.rolling(26).sum() / 2)
    pd.testing.assert_series_equal(actual_vr, expected_vr)

    vroc = _strategy("volume_rate_of_change_a_share_event")
    pd.testing.assert_series_equal(vroc._vroc(volume), volume.pct_change(12) * 100)


def test_indicators_are_causal_when_future_extreme_bars_are_appended():
    panels = _panels(days=190, symbols=1)
    close = panels["close"].iloc[:, 0]
    open_ = panels["open"].iloc[:, 0]
    high = panels["high"].iloc[:, 0]
    low = panels["low"].iloc[:, 0]
    volume = panels["volume"].iloc[:, 0]
    future_index = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=20)
    future_close = pd.Series(10_000.0, index=future_index, name=close.name)
    future_open = pd.Series(9_900.0, index=future_index, name=open_.name)
    future_high = pd.Series(12_000.0, index=future_index, name=high.name)
    future_low = pd.Series(9_000.0, index=future_index, name=low.name)
    future_volume = pd.Series(99_000_000.0, index=future_index, name=volume.name)

    arbr = _strategy("arbr_sentiment_a_share_event")
    pd.testing.assert_frame_equal(
        arbr._arbr(open_, high, low, close),
        arbr._arbr(
            pd.concat([open_, future_open]),
            pd.concat([high, future_high]),
            pd.concat([low, future_low]),
            pd.concat([close, future_close]),
        ).iloc[: len(close)],
    )
    psy = _strategy("psy_sentiment_a_share_event")
    pd.testing.assert_series_equal(
        psy._psy(close), psy._psy(pd.concat([close, future_close])).iloc[: len(close)]
    )
    vr = _strategy("volume_ratio_a_share_event")
    pd.testing.assert_series_equal(
        vr._vr(close, volume),
        vr._vr(
            pd.concat([close, future_close]),
            pd.concat([volume, future_volume]),
        ).iloc[: len(close)],
    )
    vroc = _strategy("volume_rate_of_change_a_share_event")
    pd.testing.assert_series_equal(
        vroc._vroc(volume),
        vroc._vroc(pd.concat([volume, future_volume])).iloc[: len(volume)],
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


def test_volume_strategies_do_not_create_candidates_on_non_positive_latest_volume():
    panels = _panels(days=100, symbols=1)
    panels["volume"].iloc[-1, 0] = 0.0
    history = {
        field: frame for field, frame in panels.items() if field in {"close", "volume"}
    }
    assert _strategy("volume_ratio_a_share_event")()._metrics(history, ["000000.SZ"]) == {}
    assert _strategy("volume_rate_of_change_a_share_event")()._metrics(
        history, ["000000.SZ"]
    ) == {}


def test_strategies_do_not_reuse_an_earlier_bar_when_latest_price_is_missing():
    panels = _panels(days=100, symbols=1)
    panels["close"].iloc[-1, 0] = np.nan
    arbr_history = {
        field: panels[field] for field in ["open", "high", "low", "close"]
    }
    close_history = {"close": panels["close"]}
    volume_history = {"close": panels["close"], "volume": panels["volume"]}
    assert _strategy("arbr_sentiment_a_share_event")()._metrics(
        arbr_history, ["000000.SZ"]
    ) == {}
    assert _strategy("psy_sentiment_a_share_event")()._metrics(
        close_history, ["000000.SZ"]
    ) == {}
    assert _strategy("volume_ratio_a_share_event")()._metrics(
        volume_history, ["000000.SZ"]
    ) == {}
    assert _strategy("volume_rate_of_change_a_share_event")()._metrics(
        volume_history, ["000000.SZ"]
    ) == {}


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
        ("arbr_sentiment_a_share_event", {"high", "low", "close"}),
        ("psy_sentiment_a_share_event", set()),
        ("volume_ratio_a_share_event", {"close"}),
        ("volume_rate_of_change_a_share_event", {"close"}),
    ],
)
def test_strategies_reject_missing_required_fields(strategy_id, fields):
    with pytest.raises(ValueError, match="缺少数据字段"):
        _strategy(strategy_id)().initialize(_Context(fields))
