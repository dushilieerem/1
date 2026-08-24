"""西蒙斯风格配对交易策略迁移验收测试。"""

import pandas as pd

from app.quantcore import BacktestConfig, NativeEngine
from app.repositories.catalogs.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("simons_pairs_trading_research")
    namespace = {"__name__": "simons_pairs_trading_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_pairs_strategy_opens_market_neutral_weights_on_spread_deviation():
    dates = pd.bdate_range("2024-01-02", periods=65)
    close = pd.DataFrame({"600519.SH": [100.0] * 60 + [120.0] * 5, "000858.SZ": [100.0] * 65}, index=dates)
    target = _strategy_class()(close).generate_signals().target_weights

    assert target.iloc[-1]["600519.SH"] == -0.5
    assert target.iloc[-1]["000858.SZ"] == 0.5
    assert target.iloc[-1].sum() == 0.0


def test_pairs_strategy_runs_in_native_vectorized_engine():
    dates = pd.bdate_range("2024-01-02", periods=70)
    close = pd.DataFrame({"600519.SH": [100.0] * 60 + [120.0] * 5 + [100.0] * 5, "000858.SZ": [100.0] * 70}, index=dates)
    result = NativeEngine().run(_strategy_class()(close).generate_signals(), BacktestConfig())

    assert not result.equity_curve.empty
    assert result.positions.iloc[-1].sum() == 0.0
