"""FEAT-030 四引擎边界与时序契约测试。"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from app.models.factor_backtest import FactorBacktestSpec
from app.services.backtest.engine import BacktestEngine
from app.services.data.engine import DataEngine
from app.services.factor.base import BaseFactor
from app.services.factor.engine import FactorEngine
from app.services.factor.errors import FactorBacktestDataError
from app.services.portfolio.engine import PortfolioEngine
from app.services.metric.engine import MetricEngine


class _ResolvedFactor(BaseFactor):
    name = "resolved_factor"

    def compute(self, data):
        return data.close


def test_factor_engine_initializes_task_data_before_backtest_orchestration(monkeypatch):
    dates = pd.date_range("2026-01-02", periods=2, freq="B")
    data_engine = Mock()
    data_engine.get_task_panels.return_value = {
        "close": pd.DataFrame({"A": [100.0, 101.0]}, index=dates)
    }
    data_engine.get_universe_at.return_value = ["A"]
    data_engine.build_filter_mask.return_value = {
        "mask": pd.DataFrame(True, index=dates, columns=["A"]),
        "status": {},
        "warnings": [],
    }
    monkeypatch.setattr(FactorEngine, "_resolve_factor", lambda *_args: None)
    spec = FactorBacktestSpec(
        factor_name="factor",
        start="2026-01-02",
        end=None,
    )
    monkeypatch.setattr(DataEngine, "_instance", data_engine)

    factor_engine = FactorEngine(spec)

    assert factor_engine.spec is spec
    assert factor_engine.actual_end == "2026-01-05"
    assert not hasattr(factor_engine, "effective_spec")
    assert not hasattr(factor_engine, "panel")
    assert factor_engine.market_field("close").equals(
        data_engine.get_task_panels.return_value["close"]
    )
    assert spec.end is None


def test_factor_engine_resolves_spec_and_stores_current_factor(monkeypatch):
    factor = _ResolvedFactor()
    calls: list[dict] = []

    def load_factor_from_spec(**kwargs):
        calls.append(kwargs)
        return factor

    monkeypatch.setattr(
        "app.services.factor.loader.load_factor_from_spec",
        load_factor_from_spec,
    )
    spec = FactorBacktestSpec(
        factor_name="resolved_factor",
        factor_code="def resolved_factor(self):\n    return self.close",
        library_names=("custom",),
    )

    engine = FactorEngine()
    panel = Mock()
    panel.close = pd.DataFrame({"A": [1.0]})
    values = engine.compute_from_spec(spec, panel)

    expected = panel.close.copy()
    expected.index.name = "date"
    pd.testing.assert_frame_equal(values, expected)
    assert engine.factor_metadata() == {
        "name": "resolved_factor",
        "author": "anonymous",
    }
    assert engine.factors["resolved_factor"] is factor
    assert calls and calls[0]["spec"] is spec
    assert calls[0]["factor_name"] == "resolved_factor"


def test_data_engine_filter_is_optional_and_reports_missing_state():
    dates = pd.date_range("2026-01-02", periods=2, freq="B")
    close = pd.DataFrame({"A": [100.0, 110.0]}, index=dates)

    result = DataEngine().build_filter_mask(
        {"close": close},
        filter_suspended=True,
        filter_limit_up=True,
    )

    assert result["status"] == {
        "is_suspended": "skipped_missing_field",
        "limit_up": "skipped_missing_field",
    }
    assert result["mask"].all().all()
    assert len(result["warnings"]) == 2

    partial = DataEngine().build_filter_mask(
        {
            "close": close,
            "up_and_down_status": pd.DataFrame(
                {"A": ["涨停", None]}, index=dates
            ),
        },
        filter_limit_up=True,
    )
    assert partial["status"]["limit_up"] == "enabled_partial"
    assert any("覆盖不足" in warning for warning in partial["warnings"])
    assert not bool(partial["mask"].loc[dates[0], "A"])
    assert bool(partial["mask"].loc[dates[1], "A"])


def test_factor_engine_masks_before_cross_sectional_preprocessing():
    dates = pd.date_range("2026-01-02", periods=1)
    values = pd.DataFrame([[1.0, 2.0, 1000.0]], index=dates, columns=list("ABC"))
    eligible = pd.DataFrame([[True, True, False]], index=dates, columns=list("ABC"))

    processed = FactorEngine().preprocess(
        values,
        eligibility_mask=eligible,
        winsorize=2,
        standardize=1,
    )

    assert pd.isna(processed.loc[dates[0], "C"])
    assert math.isclose(processed.loc[dates[0], "A"], -1 / 2**0.5, abs_tol=1e-6)
    assert math.isclose(processed.loc[dates[0], "B"], 1 / 2**0.5, abs_tol=1e-6)


def test_portfolio_and_metric_preserve_first_forward_holding_period():
    dates = pd.date_range("2026-01-02", periods=4, freq="B")
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=dates)
    factor = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=dates)

    portfolio = PortfolioEngine().build(
        factor,
        close,
        groups=None,
        portfolio_type="long_only",
        rebalance=1,
        stock_num=1,
    )
    evaluation = MetricEngine().evaluate(portfolio)

    pd.testing.assert_series_equal(
        evaluation["returns"],
        pd.Series([0.1, 0.1, 0.1], index=dates[1:], name=None),
    )
    pd.testing.assert_series_equal(
        evaluation["equity_curve"],
        pd.Series([1.0, 1.1, 1.21], index=dates[1:], name=None),
    )
    assert pd.isna(portfolio["forward_returns"].loc[dates[-1], "A"])
    assert portfolio["positions"].loc[dates[1], "A"] == 1.0


def test_portfolio_skips_rebalance_logs_by_default_and_supports_opt_in():
    dates = pd.date_range("2026-01-02", periods=3, freq="B")
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0], "B": [100.0, 100.0, 100.0]},
        index=dates,
    )
    factor = pd.DataFrame(
        [[2.0, 1.0], [1.0, 2.0], [2.0, 1.0]],
        index=dates,
        columns=["A", "B"],
    )

    default_portfolio = PortfolioEngine().build(
        factor,
        close,
        groups=None,
        portfolio_type="long_only",
        rebalance=1,
        stock_num=1,
    )
    detailed_portfolio = PortfolioEngine().build(
        factor,
        close,
        groups=None,
        portfolio_type="long_only",
        rebalance=1,
        stock_num=1,
        include_rebalance_logs=True,
    )

    assert default_portfolio["rebalance_logs"] is None
    assert not detailed_portfolio["rebalance_logs"].empty


def test_metric_engine_owns_factor_analysis_and_benchmark_alignment():
    dates = pd.date_range("2026-01-02", periods=5, freq="B")
    symbols = list("ABCD")
    close = pd.DataFrame(
        {
            "A": [100.0, 101.0, 102.0, 103.0, 104.0],
            "B": [100.0, 102.0, 104.0, 106.0, 108.0],
            "C": [100.0, 99.0, 98.0, 97.0, 96.0],
            "D": [100.0, 98.0, 96.0, 94.0, 92.0],
        },
        index=dates,
    )
    factor = pd.DataFrame(
        [
            [4.0, 3.0, 2.0, 1.0],
            [4.0, 3.0, 2.0, 1.0],
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
            [4.0, 3.0, 2.0, 1.0],
        ],
        index=dates,
        columns=symbols,
    )
    portfolio = PortfolioEngine().build(
        factor,
        close,
        groups=2,
        portfolio_type="long_only",
        rebalance=1,
        stock_num=2,
    )
    benchmark = pd.Series(
        [1.0, 1.01, 1.02, 1.03],
        index=dates[1:],
    )
    loaded_dates = []

    def load_benchmark(index):
        loaded_dates.extend(index)
        return benchmark

    evaluation = MetricEngine().evaluate_factor_portfolio(
        portfolio,
        analysis_level="core",
        benchmark_loader=load_benchmark,
        groups=2,
    )

    assert loaded_dates == list(dates[1:])
    assert evaluation["benchmark_equity"] is benchmark
    assert "factor_analysis" in evaluation
    assert "long_short_returns" in evaluation["factor_analysis"]
    assert [item.quantile for item in evaluation["quantile_metrics"]] == [
        "Q1", "Q2", "benchmark"
    ]

    with pytest.raises(FactorBacktestDataError, match="指标评价未生成有效基准净值"):
        MetricEngine().evaluate_factor_portfolio(
            portfolio,
            analysis_level="core",
            benchmark_equity=pd.DataFrame(),
            groups=2,
        )


def test_portfolio_aligns_forward_returns_after_full_price_shift():
    dates = pd.date_range("2026-01-02", periods=4, freq="B")
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=dates)
    factor = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=dates[:3])

    portfolio = PortfolioEngine().build(
        factor,
        close,
        groups=None,
        portfolio_type="long_only",
        rebalance=1,
        stock_num=1,
    )

    assert math.isclose(
        portfolio["forward_returns"].loc[dates[2], "A"],
        0.1,
        abs_tol=1e-12,
    )


def test_metric_engine_reports_weight_change_cost_summary():
    dates = pd.date_range("2026-01-02", periods=3, freq="B")
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=dates)
    factor = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=dates)
    portfolio = PortfolioEngine().build(
        factor,
        close,
        groups=None,
        portfolio_type="long_only",
        rebalance=1,
        stock_num=1,
    )

    evaluation = MetricEngine().evaluate(
        portfolio,
        commission_rate=0.01,
        stamp_tax=0.002,
        slippage_rate=0.003,
    )

    summary = evaluation["transaction_summary"]
    assert summary["trade_count"] == 1
    assert summary["total_turnover"] == 1.0
    assert summary["commission_cost"] == pytest.approx(0.0)
    assert summary["stamp_tax_cost"] == pytest.approx(0.0)
    assert summary["slippage_cost"] == pytest.approx(0.0)
    assert summary["total_cost"] == pytest.approx(0.0)
    assert evaluation["metrics"]["total_cost"] == pytest.approx(0.0)


def test_factor_path_does_not_reference_legacy_signal_algorithm():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    engine_source = (root / "app" / "services" / "backtest" / "engine.py").read_text(
        encoding="utf-8"
    )
    factor_source = (root / "app" / "services" / "experiment" / "factor.py").read_text(
        encoding="utf-8"
    )
    assert "FactorQuantileStrategy" not in engine_source
    assert "FactorGroupStrategy" not in engine_source
    assert "NativeEngine" not in engine_source
    assert "_FactorBacktestAlgorithm" not in factor_source
