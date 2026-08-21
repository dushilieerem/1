"""CCI、MFI、TRIX 与 ROC 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.quantcore import EventBacktestEngine
from app.repositories.catalogs.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "cci_mean_reversion_a_share_event": "CciMeanReversionAShareEventStrategy",
    "money_flow_index_a_share_event": "MoneyFlowIndexAShareEventStrategy",
    "trix_momentum_a_share_event": "TrixMomentumAShareEventStrategy",
    "rate_of_change_momentum_a_share_event": "RateOfChangeMomentumAShareEventStrategy",
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=260, symbols=12):
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
        "volume": pd.DataFrame(
            {
                code: 1_000_000 + (steps % 10) * 10_000 + index * 1_000
                for index, code in enumerate(codes)
            },
            index=dates,
        ),
    }


def test_four_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id in STRATEGIES:
        assert assets[strategy_id]["execution_mode"] == "event"


def test_cci_formula_matches_typical_price_and_mean_deviation():
    strategy_class = _strategy("cci_mean_reversion_a_share_event")
    high = pd.Series([12.0, 13.0, 14.0, 15.0, 16.0])
    low = pd.Series([8.0, 9.0, 10.0, 11.0, 12.0])
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    typical = (high + low + close) / 3.0
    mean = typical.rolling(5).mean()
    deviation = typical.rolling(5).apply(
        lambda values: float(abs(values - values.mean()).mean()), raw=True
    )
    expected = (typical - mean) / (0.015 * deviation)
    actual = strategy_class._cci(high, low, close, window=5)
    assert actual.iloc[-1] == pytest.approx(expected.iloc[-1])


def test_mfi_rising_price_and_volume_reaches_upper_bound():
    strategy_class = _strategy("money_flow_index_a_share_event")
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
    mfi = strategy_class._mfi(close + 1, close - 1, close, pd.Series(100.0, index=close.index), window=3)
    assert mfi.iloc[-1] == pytest.approx(100.0)
    assert mfi.iloc[-1] <= 100.0


def test_trix_and_roc_use_documented_lookbacks():
    close = pd.Series(np.linspace(10.0, 30.0, 40))
    trix_class = _strategy("trix_momentum_a_share_event")
    trix, signal = trix_class._trix(close, window=5, signal_window=3)
    first = close.ewm(span=5, adjust=False, min_periods=5).mean()
    second = first.ewm(span=5, adjust=False, min_periods=5).mean()
    third = second.ewm(span=5, adjust=False, min_periods=5).mean()
    expected_trix = third.pct_change() * 100.0
    expected_signal = expected_trix.ewm(span=3, adjust=False, min_periods=3).mean()
    assert trix.iloc[-1] == pytest.approx(expected_trix.iloc[-1])
    assert signal.iloc[-1] == pytest.approx(expected_signal.iloc[-1])

    roc_class = _strategy("rate_of_change_momentum_a_share_event")
    assert roc_class._roc(close, window=5).iloc[-1] == pytest.approx((30.0 / close.iloc[-6] - 1) * 100)


def test_event_strategies_run_with_their_required_ohlcv_panels():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"


def test_mfi_rejects_panels_without_volume():
    panels = _panels()
    panels.pop("volume")
    with pytest.raises(ValueError, match="MFI 策略缺少数据字段"):
        EventBacktestEngine(panels).run(_strategy("money_flow_index_a_share_event")())
