"""KST 多周期动量策略迁移验收测试。"""

import pandas as pd
import pytest

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("pring_kst_a_share_event")
    namespace = {"__name__": "pring_kst_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_kst_uses_documented_weighted_roc_components():
    strategy = _strategy_class()()
    close = pd.Series(range(100, 180), dtype=float)
    kst, signal = strategy._kst(close)
    expected = sum(
        weight * (100 * (close / close.shift(roc) - 1)).rolling(sma).mean()
        for roc, sma, weight in zip((10, 15, 20, 30), (10, 10, 10, 15), (1, 2, 3, 4))
    )
    assert kst.iloc[-1] == pytest.approx(expected.iloc[-1])
    assert signal.iloc[-1] == pytest.approx(kst.iloc[-9:].mean())


def test_pring_kst_strategy_runs_with_daily_ohlc_panels():
    dates = pd.bdate_range("2024-01-02", periods=190)
    benchmark = pd.Series(range(100, 290), index=dates, dtype=float)
    stock = pd.Series([20 + index * 0.25 + (index % 6) * 0.5 for index in range(len(dates))], index=dates)
    panels = {
        field: pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates)
        for field in ("open", "high", "low", "close")
    }
    result = EventBacktestEngine(panels).run(_strategy_class()(universe=["000001.SZ"]))
    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
