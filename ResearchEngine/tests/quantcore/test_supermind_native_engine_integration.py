"""NativeEngine 使用 Supermind 导出 CSV 的确定性集成测试。"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.quantcore.backtest.adapter import BacktestConfig, BacktestSignals, NativeEngine


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "supermind"


def _load_fixture():
    market_cap = pd.read_csv(FIXTURE_DIR / "market_cap.csv", index_col=0)
    market_cap.columns = pd.to_datetime(
        market_cap.columns.str.split(" ").str[0], format="%Y/%m/%d"
    )
    factor_values = market_cap.T
    close = pd.read_csv(FIXTURE_DIR / "price.csv", index_col=0)
    close.index = pd.to_datetime(close.index, format="%Y/%m/%d")
    return factor_values, close.loc[:, factor_values.columns]


def _quantile_targets(factor_values, group_number):
    """按 Supermind 的完整精度原值 qcut 构造某一个分位组合目标权重。"""
    target = pd.DataFrame(0.0, index=factor_values.index, columns=factor_values.columns)
    for date, values in factor_values.iterrows():
        groups = 5 - pd.qcut(values, 5, labels=False)
        selected = groups[groups == group_number].index
        target.loc[date, selected] = 1.0 / len(selected)
    return target


def _metrics(metric_returns, equity):
    values = metric_returns.to_numpy(dtype=float)
    volatility = np.std(values, ddof=1) * np.sqrt(252)
    cumulative = equity.iloc[-1] - 1.0
    annual = (np.prod(1.0 + values) ** (252.0 / len(values))) - 1.0
    sharpe = np.mean(values) / np.std(values, ddof=1) * np.sqrt(252)
    max_drawdown = (1.0 - equity / equity.cummax()).max()
    return cumulative, annual, volatility, sharpe, max_drawdown


def test_native_engine_matches_verified_supermind_market_cap_curves_and_metrics():
    """NativeEngine 的统一时序必须复现 2026 年 4 月市值五分位结果。"""
    factor_values, close = _load_fixture()
    engine = NativeEngine()
    results = {}
    for group_number in range(1, 6):
        target = _quantile_targets(factor_values, group_number)
        results[group_number] = engine.run(
            BacktestSignals(target_weights=target, close=close), BacktestConfig()
        )

    assert results[1].equity_curve.index[0] == pd.Timestamp("2026-04-02")
    assert results[1].equity_curve.index[-1] == pd.Timestamp("2026-04-30")
    assert results[1].equity_curve.iloc[0] == pytest.approx(1.0)
    assert [results[group].equity_curve.iloc[-1] for group in range(1, 6)] == pytest.approx([
        1.0658749009676845,
        1.0551068698710455,
        1.0496690531790194,
        1.0218372111258456,
        1.0336993833166006,
    ])

    expected = {
        1: (0.06587490096768445, 1.1072668607529956, 0.10799187005474441, 6.963423364669206, 0.008476483731850282),
        2: (0.055106869871045516, 0.6927427026055744, 0.17587909682891123, 3.078454437793592, 0.012329991722449751),
        3: (0.04966905317901937, 0.657475735831512, 0.15802186203731397, 3.2749063615095713, 0.00885410233560413),
        4: (0.02183721112584558, 0.15898088192931148, 0.16329003935336253, 0.9804558170458678, 0.014453974403871306),
        5: (0.033699383316600606, 0.3041452395809605, 0.17059264204109023, 1.6378218951871442, 0.01620841727200084),
    }
    for group_number, expected_metrics in expected.items():
        actual = _metrics(
            results[group_number].returns, results[group_number].equity_curve
        )
        assert actual == pytest.approx(expected_metrics, abs=1e-12)
