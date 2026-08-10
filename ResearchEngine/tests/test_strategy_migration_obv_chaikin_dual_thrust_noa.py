"""OBV、蔡金、Dual Thrust 与净营运资产异象迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantcore import BacktestConfig, EventBacktestEngine, NativeEngine
from researchengine.strategy_catalog import StrategyCatalog


EVENT_STRATEGIES = (
    "granville_obv_a_share_event",
    "chaikin_accumulation_distribution_a_share_event",
    "net_operating_assets_anomaly_a_share_event",
)


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _event_panels(days=300, symbols=10):
    dates = pd.bdate_range("2023-01-02", periods=days)
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    close = pd.DataFrame(
        {
            code: 10 + np.arange(days) * (0.03 + i * 0.001)
            for i, code in enumerate(codes)
        },
        index=dates,
    )
    panels = {
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": pd.DataFrame(1_000_000.0, index=dates, columns=codes),
        "amount": pd.DataFrame(30_000_000.0, index=dates, columns=codes),
        "industry": pd.DataFrame(
            {code: [f"I{i // 5}"] * days for i, code in enumerate(codes)}, index=dates
        ),
        "pe_ratio": pd.DataFrame(
            {code: [8.0 + i] * days for i, code in enumerate(codes)}, index=dates
        ),
        "pb_ratio": pd.DataFrame(
            {code: [0.8 + i * 0.1] * days for i, code in enumerate(codes)}, index=dates
        ),
        "circulating_market_cap": pd.DataFrame(
            {code: [100.0 + i * 10] * days for i, code in enumerate(codes)}, index=dates
        ),
        "market_cap": pd.DataFrame(
            {code: [4_000_000_000.0 + i * 10_000_000] * days for i, code in enumerate(codes)}, index=dates
        ),
        "total_assets": pd.DataFrame(
            {code: [1_000.0 + i * 10] * days for i, code in enumerate(codes)}, index=dates
        ),
        "money_cap": pd.DataFrame(200.0, index=dates, columns=codes),
        "total_liabilities": pd.DataFrame(500.0, index=dates, columns=codes),
        "long_borr": pd.DataFrame(100.0, index=dates, columns=codes),
        "bond_payable": pd.DataFrame(50.0, index=dates, columns=codes),
    }
    return panels


def test_four_strategies_are_catalogued_with_their_execution_modes():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    assert assets["granville_obv_a_share_event"]["execution_mode"] == "event"
    assert assets["chaikin_accumulation_distribution_a_share_event"]["execution_mode"] == "event"
    assert assets["dual_thrust_a_share"]["execution_mode"] == "vectorized"
    assert assets["net_operating_assets_anomaly_a_share_event"]["execution_mode"] == "event"


def test_obv_and_chaikin_formulas_are_migrated():
    obv_class = _strategy("granville_obv_a_share_event")
    close = pd.Series([1.0, 2.0, 2.0, 1.0, 3.0])
    volume = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    pd.testing.assert_series_equal(
        obv_class._obv(close, volume),
        pd.Series([0.0, 20.0, 20.0, -20.0, 30.0]),
        check_names=False,
    )

    chaikin_class = _strategy("chaikin_accumulation_distribution_a_share_event")
    multiplier, money_flow_volume, ad_line, oscillator = chaikin_class._chaikin(
        pd.Series([11.0, 10.0]),
        pd.Series([9.0, 10.0]),
        pd.Series([10.0, 10.0]),
        pd.Series([100.0, 200.0]),
    )
    assert multiplier.iloc[1] == 0.0
    assert money_flow_volume.iloc[0] == 0.0
    assert ad_line.iloc[-1] == 0.0
    assert oscillator.iloc[-1] == 0.0


def test_event_strategies_run_on_their_required_point_in_time_panels():
    panels = _event_panels()
    for strategy_id in EVENT_STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])


def test_noa_formula_and_low_noa_selection():
    strategy_class = _strategy("net_operating_assets_anomaly_a_share_event")
    strategy = strategy_class(min_market_cap=0.0)
    assert strategy._noa(100.0, 20.0, 60.0, 10.0, 5.0) == 0.35

    panels = _event_panels(days=40, symbols=3)
    history = {field: frame.tail(1) for field, frame in panels.items()}
    candidates = strategy._candidates(history, list(panels["close"]))
    assert candidates.iloc[0]["symbol"] == "000000.SZ"
    assert candidates["noa"].is_monotonic_increasing


def test_dual_thrust_uses_previous_range_and_native_engine():
    panels = _event_panels(days=80, symbols=4)
    dual_class = _strategy("dual_thrust_a_share")
    strategy = dual_class(
        panels["open"],
        panels["high"],
        panels["low"],
        panels["close"],
        panels["amount"],
        panels["market_cap"],
        max_holdings=2,
        pool_size=4,
    )
    width = strategy._range(
        pd.DataFrame({"A": [12.0, 13.0, 14.0, 15.0, 16.0]}),
        pd.DataFrame({"A": [8.0, 9.0, 10.0, 11.0, 12.0]}),
        pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0, 14.0]}),
        4,
    )
    assert width.iloc[-1, 0] == 5.0

    signals = strategy.generate_signals()
    assert signals.target_weights.max().max() <= 0.5
    result = NativeEngine().run(signals, BacktestConfig())
    assert not result.equity_curve.empty
