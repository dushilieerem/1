"""唐奇安风格均线多头排列策略迁移验收测试。"""

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("donchian_bullish_ma_alignment_a_share_event")
    namespace = {"__name__": "donchian_bullish_ma_alignment_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_ma_alignment_requires_all_averages_and_positive_slopes():
    strategy = _strategy_class()()
    close = pd.Series(list(range(30, 71)) + [95 + index * 0.25 for index in range(20)], dtype=float)
    signal = strategy._signal(close)

    assert signal is not None
    assert signal["bullish"]
    assert signal["entry"]
    assert strategy._should_exit(signal, average_cost=signal["close"] / 1.31)


def test_ma_alignment_strategy_runs_with_daily_ohlc_panels():
    dates = pd.bdate_range("2024-01-02", periods=100)
    prices = pd.Series(list(range(1, 80)) + [79.0] * 21, index=dates)
    panels = {field: pd.DataFrame({"000858.SZ": prices}, index=dates) for field in ("open", "high", "low", "close")}

    result = EventBacktestEngine(panels).run(_strategy_class()())

    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
