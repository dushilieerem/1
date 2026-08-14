"""ResearchEngine 因子回测 API 测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from researchengine.api import app
from researchengine.api.market_data import _market_symbol, _panel_symbol
from researchengine.api.runner import (
    _compute_quantile_metrics,
    _display_instrument,
    _sample_positions,
    _serialize_rebalance_logs,
)


client = TestClient(app)

COMBO_FACTOR_CODE = '''def volume_20d(self, window: int = 20):
    return self.volume / self.volume.rolling(window).mean()

def amount_20d(self, window: int = 20):
    return self.amount / self.amount.rolling(window).mean()

def combo_factor(self):
    return 0.5 * self.volume_20d() + 0.5 * self.amount_20d()'''

BUILTIN_COMBO_FACTOR_CODE = '''def combo_factor(self):
    return 0.5 * self.kurtosis20() + 0.5 * self.alpha158_kmid()'''

STRATEGY_CODE = '''import pandas as pd

class EqualWeightMomentum:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        top_n = 3
        momentum = self.close.pct_change(20)
        ranks = momentum.rank(axis=1, ascending=False, method="first")
        weights = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        weights[ranks <= top_n] = 1.0 / top_n
        return weights'''

STRUCTURED_STRATEGY_CODE = '''from quantcore import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class CompositeFactorStrategy(FactorPortfolioStrategy):
    selector = TopN(3)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(15)

    @factor
    def momentum_20d(self):
        return self.close.pct_change(20)

    @factor
    def value_ep(self):
        return 1.0 / self.pe_ttm

    @signal
    def score(self):
        return 0.6 * self.rank(self.momentum_20d()) + 0.4 * self.rank(self.value_ep())'''


@pytest.fixture()
def market_data_dir(tmp_path, monkeypatch):
    """生成最小行情和 CSI300 基准数据。"""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2022-01-03", periods=90)
    symbols = [f"S{i:03d}" for i in range(12)]
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (90, 12)), axis=0))
    for name, values in (
        ("open", close * 0.995),
        ("high", close * 1.01),
        ("low", close * 0.99),
        ("close", close),
        ("volume", rng.uniform(1e6, 1e7, (90, 12))),
        ("amount", rng.uniform(1e8, 1e9, (90, 12))),
        ("total_mv", rng.uniform(1e10, 5e10, (90, 12))),
    ):
        frame = pd.DataFrame(values, index=dates, columns=symbols)
        frame.index.name = "datetime"
        frame.reset_index().to_parquet(tmp_path / f"{name}.parquet", index=False)

    display_dir = tmp_path / "display"
    display_dir.mkdir()
    display_columns = pd.MultiIndex.from_product(
        [symbols, ["open", "high", "low", "close"]]
    )
    display = pd.DataFrame(index=dates, columns=display_columns, dtype=float)
    for index, symbol in enumerate(symbols):
        # 与研究行情刻意使用不同数值，确保接口确实读取展示专用文件。
        display[(symbol, "open")] = close[:, index] + 10.0
        display[(symbol, "high")] = close[:, index] + 12.0
        display[(symbol, "low")] = close[:, index] + 8.0
        display[(symbol, "close")] = close[:, index] + 11.0
    display.index.name = "date"
    display.to_parquet(display_dir / "unadjusted_price.parquet")

    pd.DataFrame({
        "code": symbols,
        "name": [f"股票{i:03d}" for i in range(12)],
        "industry": ["银行"] * 6 + ["医药"] * 6,
    }).to_parquet(tmp_path / "stock_info.parquet", index=False)

    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    benchmark_close = np.linspace(4000.0, 4300.0, len(dates))
    benchmark = pd.DataFrame(
        {
            "open": benchmark_close * 0.995,
            "high": benchmark_close * 1.01,
            "low": benchmark_close * 0.99,
            "close": benchmark_close,
        },
        index=dates,
    )
    benchmark.to_parquet(benchmark_dir / "index_price_000300.SH.parquet")
    pd.DataFrame(
        {symbol: [1 / len(symbols)] for symbol in symbols}, index=[dates[0]]
    ).to_parquet(benchmark_dir / "index_weights_000905.SH.parquet")
    pd.DataFrame(
        {
            symbol: [1 / len(symbols), 0.5 if symbol in {"S000", "S001"} else float("nan")]
            for symbol in symbols
        },
        index=[dates[0], dates[-1]],
    ).to_parquet(benchmark_dir / "index_weights_000300.SH.parquet")
    monkeypatch.setenv("SVQUANT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SVQUANT_BACKTEST_CACHE_DIR", str(tmp_path / "backtest_cache"))
    return tmp_path


@pytest.fixture()
def supermind_api_data_dir(tmp_path, monkeypatch):
    """将已验证的 SuperMind fixture 转为 API 可读取的字段 Parquet。"""
    fixture_dir = (
        Path(__file__).resolve().parents[2]
        / "QuantCore"
        / "tests"
        / "fixtures"
        / "supermind"
    )
    market_cap = pd.read_csv(fixture_dir / "market_cap.csv", index_col=0)
    factor_dates = pd.to_datetime(
        [str(value).split(" ")[0] for value in market_cap.columns],
        format="%Y/%m/%d",
    )
    factor_values = market_cap.T
    factor_values.index = factor_dates
    factor_values.columns = market_cap.index.astype(str)

    close = pd.read_csv(fixture_dir / "price.csv", index_col=0)
    close.index = pd.to_datetime(close.index, format="%Y/%m/%d")
    close = close.loc[:, factor_values.columns]

    def write_field(name, frame):
        frame = frame.copy()
        frame.index.name = "datetime"
        frame.reset_index().to_parquet(tmp_path / f"{name}.parquet", index=False)

    for field in ("close", "total_mv"):
        write_field(field, close if field == "close" else factor_values)

    display_dir = tmp_path / "display"
    display_dir.mkdir()
    display_columns = pd.MultiIndex.from_product(
        [close.columns, ["open", "high", "low", "close"]]
    )
    display = pd.DataFrame(index=close.index, columns=display_columns, dtype=float)
    for symbol in close.columns:
        for field in ("open", "high", "low", "close"):
            display[(symbol, field)] = close[symbol]
    display.index.name = "date"
    display.to_parquet(display_dir / "unadjusted_price.parquet")

    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    benchmark_close = close.mean(axis=1)
    benchmark = pd.DataFrame(
        {
            "open": benchmark_close,
            "high": benchmark_close,
            "low": benchmark_close,
            "close": benchmark_close,
        },
        index=benchmark_close.index,
    )
    benchmark.to_parquet(benchmark_dir / "index_price_000300.SH.parquet")

    monkeypatch.setenv("SVQUANT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SVQUANT_BACKTEST_CACHE_DIR", str(tmp_path / "backtest_cache"))
    monkeypatch.setenv("SVQUANT_BACKTEST_CACHE_ENABLED", "false")
    return {
        "root": tmp_path,
        "factor_values": factor_values,
        "close": close,
        "benchmark_close": benchmark_close,
    }


def _request_payload():
    return {
        "factor_code": COMBO_FACTOR_CODE,
        "factor_name": "combo_factor",
        "universe": "CSI500",
        "portfolio_type": "long_only",
        "rebalance_days": 15,
        "groups": 3,
        "benchmark": "CSI300",
        "analysis_level": "full",
    }


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_factor_backtest_minimal_builtin_request_uses_web_defaults():
    from researchengine.api.schemas import FactorBacktestRequest

    request = FactorBacktestRequest(
        library_name="momentum_lib",
        factor_name="momentum_5d",
    )

    assert request.portfolio_type == "long_only"
    assert request.universe == "CSI300"
    assert request.rebalance_days == 1
    assert request.commission_rate == 0.0
    assert request.stamp_tax == 0.0
    assert request.slippage_rate == 0.0


def test_daily_bars_returns_filtered_ohlc(market_data_dir):
    response = client.get(
        "/api/market-data/daily/S000",
        params={"start": "2022-01-05", "end": "2022-01-07"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "S000"
    assert body["name"] == "股票000"
    assert len(body["bars"]) == 3
    assert body["date_range"] == {"start": "2022-01-05", "end": "2022-01-07"}
    assert set(body["bars"][0]) == {"date", "open", "high", "low", "close"}
    assert body["bars"][0]["open"] == pytest.approx(body["bars"][0]["close"] - 1.0)


def test_market_data_symbols_returns_sorted_stock_codes(market_data_dir):
    response = client.get("/api/market-data/symbols")

    assert response.status_code == 200
    assert response.json() == {
        "symbols": [
            {"symbol": f"S{i:03d}", "name": f"股票{i:03d}"}
            for i in range(12)
        ],
        "unmapped_count": 0,
    }


def test_market_data_indices_returns_available_indices(market_data_dir):
    response = client.get("/api/market-data/indices")

    assert response.status_code == 200
    assert response.json() == {
        "indices": [{"code": "000300.SH", "name": "沪深300"}],
    }


def test_index_constituents_returns_latest_snapshot(market_data_dir):
    response = client.get("/api/market-data/indices/000300.SH/constituents")

    assert response.status_code == 200
    assert response.json() == {
        "index": {"code": "000300.SH", "name": "沪深300"},
        "constituents": [
            {"symbol": "S000", "name": "股票000"},
            {"symbol": "S001", "name": "股票001"},
        ],
        "unmapped_count": 0,
    }


def test_index_constituents_rejects_unknown_code(market_data_dir):
    assert client.get("/api/market-data/indices/000001.SH/constituents").status_code == 404


def test_market_symbol_conversion():
    assert _market_symbol("000001") == "000001.SZ"
    assert _market_symbol("600519") == "600519.SH"
    assert _market_symbol("430047") == "430047.BJ"
    assert _market_symbol("920000") == "920000.BJ"
    assert _panel_symbol("000001.SZ") == "000001"


def test_daily_bars_returns_not_found_or_invalid_range(market_data_dir):
    assert client.get("/api/market-data/daily/UNKNOWN").status_code == 404
    assert client.get(
        "/api/market-data/daily/S000",
        params={"start": "2022-01-07", "end": "2022-01-05"},
    ).status_code == 422


def test_daily_bars_returns_service_unavailable_when_field_missing(market_data_dir):
    path = market_data_dir / "display" / "unadjusted_price.parquet"
    display = pd.read_parquet(path)
    display = display.loc[:, display.columns.get_level_values(1) != "high"]
    display.to_parquet(path)
    response = client.get("/api/market-data/daily/S000")
    assert response.status_code == 503


def test_factor_backtest_groups_and_benchmark(market_data_dir):
    response = client.post("/api/backtest/factor", json=_request_payload())
    assert response.status_code == 200
    assert response.headers["X-SVQuant-Cache"] == "MISS"
    body = response.json()
    assert body["error"] is None
    assert body["benchmark_curve"][0]["value"] == pytest.approx(1.0)
    assert body["meta"]["rebalance_days"] == 15
    assert body["meta"]["groups"] == 3
    assert body["meta"]["benchmark"] == "CSI300"
    assert body["meta"]["factor_price_adjustment"] == "unadjusted"
    assert body["meta"]["factor_price_fields"] == ["open", "high", "low", "close"]
    assert body["meta"]["factor_price_source"].replace("\\", "/").endswith(
        "display/unadjusted_price.parquet"
    )
    assert body["meta"]["factor_price_precision"] == "source_precision_no_rounding"
    assert body["meta"]["return_price_adjustment"] == "hfq"
    assert body["meta"]["return_price_source"] == "data_engine.close"
    assert body["meta"]["return_price_precision"] == "source_precision_no_rounding"
    assert body["factor_analysis"]["definition"]["grouping_method"] == "pd.qcut_raw_value"
    assert body["factor_analysis"]["cumulative_series"][0]["layer1"] == pytest.approx(1.0)
    assert len(body["factor_analysis"]["cumulative_series"]) > 0
    assert "layer3" in body["factor_analysis"]["cumulative_series"][-1]
    assert len(body["factor_analysis"]["ic_series"]) > 0
    assert len(body["factor_analysis"]["cumulative_ic_series"]) == len(
        body["factor_analysis"]["ic_series"]
    )
    assert body["factor_analysis"]["cumulative_ic_series"][-1]["value"] == pytest.approx(
        sum(point["value"] for point in body["factor_analysis"]["ic_series"])
    )
    assert len(body["factor_analysis"]["rolling_ir_series"]) > 0
    assert len(body["factor_analysis"]["industry_equity_curves"]) == 2
    industry_groups = body["factor_analysis"]["industry_group_equity_curves"]
    assert len(industry_groups) == 2
    assert set(industry_groups[0]["points"][-1]["groups"]) == {"G1", "G2", "G3"}
    quantile_metrics = body["factor_analysis"]["quantile_metrics"]
    assert [item["quantile"] for item in quantile_metrics] == [
        "Q1", "Q2", "Q3", "benchmark"
    ]
    assert set(quantile_metrics[0]) == {
        "quantile",
        "annual_return",
        "volatility",
        "sharpe",
        "max_drawdown",
        "annual_excess_return",
        "excess_volatility",
        "information_ratio",
        "benchmark_win_rate",
    }
    assert all(
        item["annual_return"] is not None
        and item["annual_excess_return"] is not None
        for item in quantile_metrics[:-1]
    )
    benchmark_metrics = quantile_metrics[-1]
    assert benchmark_metrics["annual_return"] is not None
    assert benchmark_metrics["volatility"] is not None
    assert benchmark_metrics["sharpe"] is not None
    assert benchmark_metrics["max_drawdown"] is not None
    assert benchmark_metrics["annual_excess_return"] is None
    assert benchmark_metrics["excess_volatility"] is None
    assert benchmark_metrics["information_ratio"] is None
    assert benchmark_metrics["benchmark_win_rate"] is None
    assert len(body["benchmark_curve"]) > 0
    assert body["excess_return"] is not None


def test_factor_backtest_supermind_fixture_matches_qcut_and_metric_contract(
    supermind_api_data_dir,
):
    """通过真实 API 端点验证 qcut、首笔收益和分组/基准指标口径。"""
    factor_values = supermind_api_data_dir["factor_values"]
    close = supermind_api_data_dir["close"]
    benchmark_close = supermind_api_data_dir["benchmark_close"]
    symbols = list(close.columns)

    expected_returns = {}
    expected_equity = {}
    for group_number in range(1, 6):
        raw = []
        for row_number in range(1, len(close)):
            labels = 5 - pd.qcut(
                factor_values.iloc[row_number - 1],
                5,
                labels=False,
            )
            members = [
                symbol for symbol in symbols
                if labels.loc[symbol] == group_number
            ]
            daily = (
                close.iloc[row_number][members]
                / close.iloc[row_number - 1][members]
                - 1.0
            ).mean()
            raw.append(float(daily))
        raw_returns = pd.Series(raw, index=close.index[1:])
        display_returns = raw_returns.copy()
        display_returns.iloc[0] = 0.0
        expected_returns[group_number] = raw_returns
        expected_equity[group_number] = (1.0 + display_returns).cumprod()

    benchmark_curve = benchmark_close.loc[close.index[1:]]
    benchmark_curve = benchmark_curve / benchmark_curve.iloc[0]
    benchmark_returns = benchmark_curve.pct_change().dropna()

    response = client.post(
        "/api/backtest/factor",
        json={
            "factor_code": "def market_cap(self):\n    return self.total_mv",
            "factor_name": "market_cap",
            "universe_snapshot": {
                "asset_id": "supermind-fixture",
                "version": "1",
                "content_hash": "fixture",
                "symbols": symbols,
            },
            "start": "2026-04-01",
            "end": "2026-04-30",
            "portfolio_type": "long_only",
            "rebalance_days": 1,
            "groups": 5,
            "benchmark": "CSI300",
            "analysis_level": "core",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["factor_price_adjustment"] == "unadjusted"
    assert body["meta"]["return_price_adjustment"] == "hfq"
    assert body["meta"]["factor_price_source"].replace("\\", "/").endswith(
        "display/unadjusted_price.parquet"
    )
    assert body["meta"]["factor_price_precision"] == "source_precision_no_rounding"
    assert body["factor_analysis"]["definition"]["grouping_method"] == "pd.qcut_raw_value"
    assert body["factor_analysis"]["definition"]["group_order"] == (
        "Q1_highest_factor_value_QN_lowest_factor_value"
    )

    points = body["factor_analysis"]["cumulative_series"]
    assert [point["date"] for point in points] == [
        date.strftime("%Y-%m-%d") for date in close.index[1:]
    ]
    assert all(point["layer1"] == pytest.approx(1.0) for point in points[:1])
    for group_number in range(1, 6):
        values = [point[f"layer{group_number}"] for point in points]
        assert values == pytest.approx(expected_equity[group_number].tolist())

    metrics = {
        item["quantile"]: item
        for item in body["factor_analysis"]["quantile_metrics"]
    }
    for group_number in range(1, 6):
        raw = expected_returns[group_number]
        expected_annual = (1.0 + raw).prod() ** (252 / len(raw)) - 1.0
        expected_volatility = raw.std(ddof=1) * np.sqrt(252)
        expected_sharpe = raw.mean() / raw.std(ddof=1) * np.sqrt(252)
        expected_drawdown = (
            expected_equity[group_number]
            / expected_equity[group_number].cummax()
            - 1.0
        ).min()
        actual = metrics[f"Q{group_number}"]
        assert actual["annual_return"] == pytest.approx(expected_annual, abs=1e-12)
        assert actual["volatility"] == pytest.approx(expected_volatility, abs=1e-12)
        assert actual["sharpe"] == pytest.approx(expected_sharpe, abs=1e-12)
        assert actual["max_drawdown"] == pytest.approx(expected_drawdown, abs=1e-12)

    assert body["metrics"]["annual_return"] == pytest.approx(
        (1.0 + expected_returns[1]).prod() ** (252 / len(expected_returns[1])) - 1.0,
        abs=1e-12,
    )

    benchmark = metrics["benchmark"]
    assert benchmark["annual_return"] == pytest.approx(
        (1.0 + benchmark_returns).prod() ** (252 / len(expected_returns[1])) - 1.0,
        abs=1e-12,
    )
    assert benchmark["volatility"] == pytest.approx(
        benchmark_returns.std(ddof=0) * np.sqrt(252), abs=1e-12
    )
    assert benchmark["sharpe"] == pytest.approx(
        benchmark_returns.mean() / benchmark_returns.std(ddof=0) * np.sqrt(252),
        abs=1e-12,
    )


def test_quantile_metrics_return_absolute_and_relative_benchmark_metrics():
    dates = pd.date_range("2022-01-03", periods=4, freq="B")
    layered_equity = pd.DataFrame(
        {
            "layer1": [1.0, 1.10, 1.00, 1.20],
            "layer2": [1.0, 1.00, 1.05, 1.10],
        },
        index=dates,
    )
    benchmark_equity = pd.Series([1.0, 1.05, 1.00, 1.10], index=dates)
    layered_returns = pd.DataFrame(
        {
            # 第一项模拟因子信号日到入场日的额外收益。
            "layer1": [0.03, 0.10, -1 / 11, 0.20],
            "layer2": [0.01, 0.00, 0.05, 10 / 105],
        },
        index=dates,
    )

    metrics = _compute_quantile_metrics(
        layered_equity,
        benchmark_equity,
        periods_per_year=4,
        layered_returns=layered_returns,
    )

    q1 = metrics[0]
    group_returns = layered_returns["layer1"]
    benchmark_returns = benchmark_equity.pct_change().dropna()
    aligned = pd.concat(
        [group_returns.rename("group"), benchmark_returns.rename("benchmark")],
        axis=1,
        join="inner",
    ).dropna()
    excess = aligned["group"] - aligned["benchmark"]
    assert q1.quantile == "Q1"
    assert q1.annual_return == pytest.approx(
        (1.0 + group_returns).prod() ** (4 / len(group_returns)) - 1
    )
    assert q1.volatility == pytest.approx(group_returns.std(ddof=1) * 2)
    assert q1.annual_excess_return == pytest.approx(excess.mean() * 4)
    assert q1.excess_volatility == pytest.approx(excess.std() * 2)
    assert q1.benchmark_win_rate == pytest.approx((excess > 0).mean())

    benchmark = metrics[-1]
    assert benchmark.quantile == "benchmark"
    assert benchmark.annual_return == pytest.approx(
        (1.0 + benchmark_returns).prod() ** (4 / len(layered_returns)) - 1
    )
    assert benchmark.volatility == pytest.approx(benchmark_returns.std(ddof=0) * 2)
    assert benchmark.sharpe == pytest.approx(
        benchmark_returns.mean() / benchmark_returns.std(ddof=0) * 2
    )
    assert benchmark.annual_excess_return is None
    assert benchmark.excess_volatility is None
    assert benchmark.information_ratio is None
    assert benchmark.benchmark_win_rate is None


def test_factor_backtest_uses_pre_start_history_for_rolling_factor(market_data_dir):
    payload = _request_payload()
    payload.update({
        "factor_code": "def momentum_20d(self):\n    return self.close.pct_change(20)",
        "factor_name": "momentum_20d",
        "start": "2022-02-01",
        "end": "2022-03-31",
        "analysis_level": "core",
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    # 20 日动量在收益区间首日就有预热值；净值从首个持有日开始，
    # 而不是等到收益区间内再滚满 20 天。
    assert body["date_range"] == {"start": "2022-02-02", "end": "2022-03-31"}


def test_factor_backtest_accepts_factor_preprocessing_options(market_data_dir):
    payload = _request_payload()
    payload.update({
        "winsorize": 1,
        "standardize": 2,
        "analysis_level": "core",
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["factor_analysis"]["definition"]["factor_preprocess"] == {
        "winsorize": 1,
        "standardize": 2,
        "order": ["winsorize", "standardize"],
        "axis": "cross_sectional",
    }


def test_experiment_uses_unadjusted_ohlc_for_factor_values(market_data_dir):
    from quantcore import BaseFactor
    from quantcore.factor.tool import preprocess_factor_values
    from researchengine import ConfigManager, Experiment

    class OhlcMean(BaseFactor):
        name = "ohlc_mean_unadjusted"

        def compute(self, data):
            return (data.open + data.high + data.low + data.close) / 4.0

    config = ConfigManager()
    config.set("data_dir", str(market_data_dir))
    config.set("factor_analysis.level", "core")
    config.set("groups", 3)
    config.set("long_short", False)
    config.set("factor_preprocess.winsorize", 1)
    config.set("factor_preprocess.standardize", 2)
    result = Experiment(
        factor=OhlcMean(),
        universe="CSI500",
        start_date="2022-02-01",
        end_date="2022-02-04",
        config=config,
    ).run()

    display = pd.read_parquet(
        market_data_dir / "display" / "unadjusted_price.parquet"
    )
    expected = pd.DataFrame(
        {
            symbol: sum(
                display[(symbol, field)]
                for field in ("open", "high", "low", "close")
            ) / 4.0
            for symbol in result.factor_values.columns
        },
        index=display.index,
    )
    expected = expected.reindex(
        index=result.factor_values.index,
        columns=result.factor_values.columns,
    )
    expected = preprocess_factor_values(
        expected,
        winsorize=1,
        standardize=2,
    )
    pd.testing.assert_frame_equal(
        result.factor_values,
        expected,
        check_names=False,
    )
    assert result.meta["factor_price_adjustment"] == "unadjusted"
    assert result.meta["factor_price_fields"] == ["open", "high", "low", "close"]
    assert result.meta["return_price_adjustment"] == "hfq"
    assert result.meta["factor_preprocess"] == {
        "winsorize": 1,
        "standardize": 2,
        "order": ["winsorize", "standardize"],
        "axis": "cross_sectional",
    }

    hfq_close = pd.read_parquet(market_data_dir / "close.parquet").set_index("datetime")
    hfq_returns = hfq_close.pct_change(fill_method=None).reindex(
        index=result.positions.index,
        columns=result.positions.columns,
    )
    expected_returns = (result.positions * hfq_returns).sum(axis=1)
    expected_display_returns = expected_returns.copy()
    expected_display_returns.iloc[0] = 0.0
    pd.testing.assert_series_equal(
        result.equity_curve,
        (1.0 + expected_display_returns).cumprod(),
        check_names=False,
    )


def test_factor_backtest_loads_builtin_factor_library(market_data_dir):
    payload = _request_payload()
    payload.pop("factor_code")
    payload.update({
        "library_name": "risk_indicators",
        "factor_name": "kurtosis60",
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_factor_backtest_loads_classic_indicator_library(market_data_dir):
    payload = _request_payload()
    payload.pop("factor_code")
    payload.update({
        "library_name": "classic_indicators",
        "factor_name": "bbi",
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    assert response.json()["error"] is None


@pytest.mark.parametrize(
    ("library_name", "factor_name"),
    [
        ("momentum_lib", "momentum_5d"),
        ("volatility_lib", "parkinson_volatility"),
    ],
)
def test_factor_backtest_loads_every_library_registered_in_index_yaml(
    market_data_dir, monkeypatch, library_name, factor_name
):
    """API 库注册必须跟随 index.yaml，而不是 runner 中的重复名单。"""
    monkeypatch.setenv(
        "SVQUANT_FACTOR_DIR",
        str(Path(__file__).resolve().parents[2] / "Factor" / "libraries"),
    )
    payload = _request_payload()
    payload.pop("factor_code")
    payload.update({"library_name": library_name, "factor_name": factor_name})
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_factor_api_lists_libraries_registered_in_index_yaml():
    from researchengine.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert {"momentum_5d", "parkinson_volatility"}.issubset(names)


def test_factor_api_lists_factor_libraries():
    response = client.get("/api/factor-libraries")

    assert response.status_code == 200
    payload = response.json()
    assert "libraries" in payload
    assert "factors" not in payload
    libraries = {item["name"]: item for item in payload["libraries"]}
    assert {"momentum_lib", "volatility_lib", "worldquant_alpha101"}.issubset(libraries)
    assert libraries["momentum_lib"]["factor_count"] == 18

    # /api/factors 只保留指定库因子资源，不再承担因子库目录功能。
    assert client.get("/api/factors").status_code == 404


def test_factor_api_lists_factors_for_one_library():
    response = client.get("/api/factors/classic_indicators")

    assert response.status_code == 200
    payload = response.json()
    assert payload["library_name"] == "classic_indicators"
    names = {item["name"] for item in payload["factors"]}
    assert {"ma", "macd", "rsi"}.issubset(names)

    missing = client.get("/api/factors/not_a_factor_library")
    assert missing.status_code == 404


def test_factor_api_registry_uses_index_yaml_as_its_only_source(tmp_path, monkeypatch):
    """替换索引后，API 注册范围应随 YAML 变化，而非依赖硬编码库名。"""
    library_name = "temporary_indexed_lib"
    (tmp_path / f"{library_name}.py").write_text(
        "from quantcore import FactorLibrary\n\n"
        "class TemporaryIndexedLibrary(FactorLibrary):\n"
        "    def temporary_factor(self):\n"
        "        return self.close\n",
        encoding="utf-8",
    )
    (tmp_path / "index.yaml").write_text(
        "libraries:\n"
        f"  {library_name}:\n"
        f"    file: {library_name}.py\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SVQUANT_FACTOR_DIR", str(tmp_path))

    from researchengine.factor_catalog import sync_catalog
    from researchengine.api.runner import (
        _load_factor_from_builtin_library,
        builtin_factor_library_names,
    )

    sync_catalog(factor_dir=tmp_path)
    assert builtin_factor_library_names() == (library_name,)
    assert _load_factor_from_builtin_library(library_name, "temporary_factor").name == (
        "temporary_factor"
    )


def test_builtin_factor_loader_rejects_unsynchronized_index(tmp_path, monkeypatch):
    """源码已有因子但 index.yaml 未同步时，API 不应静默加载。"""
    library_name = "stale_indexed_lib"
    (tmp_path / f"{library_name}.py").write_text(
        "from quantcore import FactorLibrary\n\n"
        "class StaleIndexedLibrary(FactorLibrary):\n"
        "    def first_factor(self):\n"
        "        return self.close\n",
        encoding="utf-8",
    )
    (tmp_path / "index.yaml").write_text(
        "libraries:\n"
        f"  {library_name}:\n"
        f"    file: {library_name}.py\n"
        "    class: StaleIndexedLibrary\n"
        "    factor_count: 0\n"
        "    factors: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SVQUANT_FACTOR_DIR", str(tmp_path))

    from researchengine.api.runner import _load_builtin_factor_library

    with pytest.raises(ValueError, match="未同步"):
        _load_builtin_factor_library(library_name)


def test_factor_backtest_custom_factor_can_combine_builtin_library_methods(market_data_dir):
    payload = _request_payload()
    payload.update({
        "factor_code": BUILTIN_COMBO_FACTOR_CODE,
        "factor_name": "combo_factor",
        "library_name": ["risk_indicators", "alpha_features"],
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_factor_backtest_requires_exactly_one_factor_source(market_data_dir):
    payload = _request_payload()
    payload.pop("factor_code")
    assert client.post("/api/backtest/factor", json=payload).status_code == 422

    payload = _request_payload()
    payload.pop("factor_code")
    payload["library_name"] = ["risk_indicators", "alpha_features"]
    assert client.post("/api/backtest/factor", json=payload).status_code == 422


def test_factor_backtest_accesses_csi300_close(market_data_dir):
    payload = _request_payload()
    payload["factor_code"] = '''def relative_to_csi300(self):
    return self.close.pct_change(5).sub(self.csi300.close.pct_change(5), axis=0)'''
    payload["factor_name"] = "relative_to_csi300"
    response = client.post("/api/backtest/factor", json=payload)
    assert response.status_code == 200
    assert response.json()["error"] is None


def test_factor_backtest_rejects_index_series_as_stock_factor(market_data_dir):
    payload = _request_payload()
    payload["factor_code"] = '''def index_close(self):
    return self.csi300.close'''
    payload["factor_name"] = "index_close"
    response = client.post("/api/backtest/factor", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "不能直接作为股票因子返回" in body["error"]


def test_factor_backtest_without_industry_mapping_returns_empty_curves(market_data_dir):
    (market_data_dir / "stock_info.parquet").unlink()
    response = client.post("/api/backtest/factor", json=_request_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["factor_analysis"]["industry_equity_curves"] == []
    assert body["factor_analysis"]["industry_group_equity_curves"] == []

    cached_response = client.post("/api/backtest/factor", json=_request_payload())
    assert cached_response.headers["X-SVQuant-Cache"] == "HIT"
    assert cached_response.json() == body


def test_factor_backtest_defaults_to_core_analysis(market_data_dir):
    payload = _request_payload()
    payload.pop("analysis_level")
    response = client.post("/api/backtest/factor", json=payload)
    body = response.json()
    assert body["error"] is None
    analysis = body["factor_analysis"]
    assert analysis["definition"]["analysis_level"] == "core"
    assert set(analysis["layered_returns"]) >= {"layer1", "layer2", "layer3"}
    assert [item["quantile"] for item in analysis["quantile_metrics"]] == [
        "Q1", "Q2", "Q3", "benchmark"
    ]
    assert analysis["industry_equity_curves"] == []
    assert analysis["ic_series"] == []
    assert body["meta"]["timings_seconds"]["api_total"] >= 0


def test_data_change_invalidates_cache(market_data_dir):
    first = client.post("/api/backtest/factor", json=_request_payload())
    assert first.headers["X-SVQuant-Cache"] == "MISS"
    path = market_data_dir / "volume.parquet"
    path.touch()
    second = client.post("/api/backtest/factor", json=_request_payload())
    assert second.headers["X-SVQuant-Cache"] == "MISS"


@pytest.mark.parametrize(
    "removed_field",
    ["backtest_period", "data_dir", "backtest_engine", "initial_capital", "include_equity", "include_factor_values",
     "include_positions", "rebalance", "stock_num"],
)
def test_removed_factor_request_fields_are_rejected(market_data_dir, removed_field):
    response = client.post(
        "/api/backtest/factor", json={**_request_payload(), removed_field: "legacy"}
    )
    assert response.status_code == 422


def test_invalid_factor_code_returns_error(market_data_dir):
    response = client.post(
        "/api/backtest/factor",
        json={"factor_code": "this is not Python", "factor_name": "bad"},
    )
    assert response.status_code == 200
    assert response.json()["error"] is not None


def test_strategy_backtest_returns_equity_and_positions(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": STRATEGY_CODE,
            "benchmark": "CSI300",
            "stamp_tax": 0.001,
            "include_positions": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"] == {
        "strategy": "EqualWeightMomentum",
        "universe": "CSI500",
        "benchmark": "CSI300",
        "engine_mode": "vectorized",
        "strategy_id": None,
        "strategy_version": None,
        "code_hash": None,
    }
    assert body["metrics"]["total_return"] is not None
    assert len(body["equity_curve"]) > 0
    assert len(body["benchmark_curve"]) > 0
    assert body["excess_return"] is not None
    assert body["equity_curve"][0]["value"] == pytest.approx(1.0)
    assert body["benchmark_curve"][0]["value"] == pytest.approx(1.0)
    assert body["positions"]
    assert body["rebalance_logs"] is None


def test_strategy_backtest_routes_catalog_event_strategy_to_event_engine(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_id": "donchian_a_share_event", "engine_mode": "event"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["engine_mode"] == "event"
    assert body["event_positions"]
    assert body["events"]
    assert body["orders"] == []
    assert body["fills"] == []
    assert body["assumptions"]["execution"] == "same_session_open_after_before_open"


def test_strategy_backtest_injects_benchmark_ohlc_for_ichimoku(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_id": "hosoda_ichimoku_a_share_event", "engine_mode": "event"},
    )

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_event_strategy_reports_missing_benchmark_ohlc_field(market_data_dir):
    path = market_data_dir / "benchmark" / "index_price_000300.SH.parquet"
    benchmark = pd.read_parquet(path).drop(columns="open")
    benchmark.to_parquet(path)

    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_id": "hosoda_ichimoku_a_share_event", "engine_mode": "event"},
    )

    assert response.status_code == 200
    assert response.json()["error"] == "ValueError: 基准 CSI300 缺少日线字段: ['open']"


def test_strategy_backtest_rejects_mismatched_catalog_engine_mode(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_id": "donchian_a_share_event", "engine_mode": "vectorized"},
    )

    assert response.status_code == 200
    assert "execution_mode" in response.json()["error"]


def test_event_strategy_reports_symbols_missing_from_selected_universe(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''class SingleStockStrategy:
    fixed_symbols = ("S999",)

    def initialize(self, context):
        pass''',
            "engine_mode": "event",
            "universe": "CSI500",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] == "ValueError: 策略固定标的行情不可用: ['S999']"


def test_event_strategy_accepts_exchange_code_against_raw_panel_symbols(market_data_dir):
    for field in ("open", "high", "low", "close"):
        path = market_data_dir / f"{field}.parquet"
        panel = pd.read_parquet(path)
        panel["600519"] = 100.0
        panel.to_parquet(path, index=False)
    constituents_path = market_data_dir / "benchmark" / "index_weights_000300.SH.parquet"
    constituents = pd.read_parquet(constituents_path)
    constituents["600519"] = 1
    constituents.to_parquet(constituents_path)

    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''class SingleStockStrategy:
    fixed_symbols = ("600519.SH",)

    def initialize(self, context):
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        context.orders.target_quantity("600519.SH", 100)''',
            "engine_mode": "event",
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["fills"][0]["symbol"] == "600519.SH"
    assert response.json()["meta"]["trading_symbols"] == ["600519.SH"]


def test_fixed_event_strategy_ignores_selected_universe(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''class SingleStockStrategy:
    fixed_symbols = ("S002",)

    def initialize(self, context):
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        context.orders.target_quantity("S002", 100)''',
            "engine_mode": "event",
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["fills"][0]["symbol"] == "S002"


def test_legacy_event_symbol_ignores_selected_universe(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''class SingleStockStrategy:
    def __init__(self):
        self.symbol = "S002"

    def initialize(self, context):
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        context.orders.target_quantity(self.symbol, 100)''',
            "engine_mode": "event",
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["meta"]["trading_symbols"] == ["S002"]


def test_declared_symbols_ignores_selected_universe(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''class BasketStrategy:
    symbols = ("S002", "S003")

    def initialize(self, context):
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        context.orders.target_quantity("S002", 100)''',
            "engine_mode": "event",
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["meta"]["trading_symbols"] == ["S002", "S003"]


def test_pair_strategy_ignores_selected_universe(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''import pandas as pd

class PairStrategy:
    pair_symbols = ("S002", "S003")

    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        assert list(self.close.columns) == ["S002", "S003"]
        return pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)''',
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["meta"]["trading_symbols"] == ["S002", "S003"]


def test_legacy_pair_strategy_ignores_selected_universe(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''import pandas as pd

class PairStrategy:
    def __init__(self, close, stock_a="S002", stock_b="S003"):
        self.close = close
        self.stock_a = stock_a
        self.stock_b = stock_b

    def generate_signals(self):
        assert list(self.close.columns) == ["S002", "S003"]
        return pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)''',
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["meta"]["trading_symbols"] == ["S002", "S003"]


def test_vectorized_strategy_receives_exchange_code_columns(market_data_dir):
    path = market_data_dir / "close.parquet"
    close = pd.read_parquet(path)
    close["600519"] = 100.0
    close.to_parquet(path, index=False)
    constituents_path = market_data_dir / "benchmark" / "index_weights_000300.SH.parquet"
    constituents = pd.read_parquet(constituents_path)
    constituents["600519"] = 1
    constituents.to_parquet(constituents_path)

    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''import pandas as pd

class ExchangeCodeStrategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        assert "600519.SH" in self.close.columns
        assert "600519" not in self.close.columns
        return pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)''',
            "universe": "CSI300",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_strategy_backtest_returns_rebalance_logs_on_demand(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": STRATEGY_CODE,
            "benchmark": "CSI300",
            "include_rebalance_logs": True,
        },
    )

    assert response.status_code == 200
    logs = response.json()["rebalance_logs"]
    assert logs
    trade = logs[0]["trades"][0]
    assert set(trade) == {"symbol", "name", "side", "previous_weight", "target_weight", "weight_change"}
    assert trade["side"] in {"buy", "sell"}


def test_strategy_backtest_returns_vectorized_execution_timeline_on_demand(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": STRATEGY_CODE, "include_execution_timeline": True},
    )

    assert response.status_code == 200
    timeline = response.json()["execution_timeline"]
    assert timeline
    assert timeline[0]["type"] == "rebalance"
    assert timeline[0]["payload"]["trades"]


def test_strategy_backtest_returns_event_execution_timeline_on_demand(market_data_dir):
    strategy_code = '''class DailyBuy:
    def initialize(self, context):
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        context.orders.target_quantity("S000", 100)'''
    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": strategy_code,
            "engine_mode": "event",
            "include_execution_timeline": True,
        },
    )

    assert response.status_code == 200
    timeline = response.json()["execution_timeline"]
    assert timeline
    assert {item["type"] for item in timeline} >= {"audit", "order", "fill", "position"}


def test_strategy_response_instruments_include_exchange_code_and_name():
    stock_names = {"000001": "平安银行"}
    positions = pd.DataFrame(
        {"000001": [1.0]}, index=pd.to_datetime(["2024-01-02"])
    )
    logs = pd.DataFrame(
        [{
            "symbol": "000001",
            "side": "buy",
            "previous_weight": 0.0,
            "target_weight": 1.0,
            "weight_change": 1.0,
        }],
        index=pd.to_datetime(["2024-01-02"]),
    )

    holding = _sample_positions(positions, stock_names)[0].holdings[0]
    trade = _serialize_rebalance_logs(logs, stock_names)[0].trades[0]

    assert holding.model_dump() == {
        "symbol": "000001.SZ", "name": "平安银行", "weight": 1.0,
    }
    assert trade.model_dump()["symbol"] == "000001.SZ"
    assert trade.model_dump()["name"] == "平安银行"


def test_display_instrument_accepts_exchange_code_panel_symbol():
    assert _display_instrument("600519.SH", {"600519": "贵州茅台"}) == (
        "600519.SH", "贵州茅台",
    )


def test_strategy_catalog_lists_and_runs_saved_version(market_data_dir, tmp_path, monkeypatch):
    strategy_dir = tmp_path / "strategies"
    strategy_dir.mkdir()
    (strategy_dir / "equal_weight_v1.py").write_text(STRATEGY_CODE, encoding="utf-8")
    (strategy_dir / "index.yaml").write_text(
        """version: 2
strategies:
  equal_weight:
    name: 等权动量
    strategy_type: momentum
    execution_mode: vectorized
    current_version: v1
    tags: [momentum]
    versions:
      v1:
        file: equal_weight_v1.py
        entrypoint: EqualWeightMomentum
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SVQUANT_STRATEGY_DIR", str(strategy_dir))

    listed = client.get("/api/strategies")
    assert listed.status_code == 200
    assert listed.json() == {
        "strategies": [{
            "id": "equal_weight",
            "name": "等权动量",
            "strategy_type": "momentum",
            "execution_mode": "vectorized",
            "current_version": "v1",
            "entrypoint": "EqualWeightMomentum",
            "tags": ["momentum"],
        }]
    }

    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_id": "equal_weight"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["error"] is None
    assert body["meta"]["strategy_id"] == "equal_weight"
    assert body["meta"]["strategy_version"] == "v1"
    assert len(body["meta"]["code_hash"]) == 64


def test_strategy_catalog_rejects_unknown_version_and_mixed_source(market_data_dir, tmp_path, monkeypatch):
    strategy_dir = tmp_path / "strategies"
    strategy_dir.mkdir()
    (strategy_dir / "index.yaml").write_text(
        """version: 2
strategies:
  empty:
    name: 空策略
    strategy_type: test
    execution_mode: vectorized
    current_version: v1
    versions:
      v1:
        file: missing.py
        entrypoint: Missing
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SVQUANT_STRATEGY_DIR", str(strategy_dir))

    response = client.post("/api/backtest/strategy", json={"strategy_id": "empty"})
    assert response.status_code == 200
    assert "策略源码不存在" in response.json()["error"]

    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_id": "empty", "strategy_code": STRATEGY_CODE},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "strategy_id",
    [
        "dual_moving_average",
        "cross_sectional_momentum",
        "short_term_reversal",
        "low_volatility",
        "donchian_breakout",
    ],
)
def test_builtin_strategy_library_entries_run_with_close_panel(market_data_dir, strategy_id):
    response = client.post("/api/backtest/strategy", json={"strategy_id": strategy_id})

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["strategy_id"] == strategy_id
    assert body["meta"]["strategy_version"] == "v1"


def test_strategy_backtest_returns_business_error_for_invalid_contract(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": "class Invalid:\n    pass"},
    )
    assert response.status_code == 200
    assert "generate_signals" in response.json()["error"]


def test_strategy_backtest_returns_business_error_when_benchmark_is_unavailable(market_data_dir):
    (market_data_dir / "benchmark" / "index_price_000300.SH.parquet").unlink()
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": STRATEGY_CODE, "benchmark": "CSI300"},
    )
    assert response.status_code == 200
    assert "index_price_000300.SH.parquet" in response.json()["error"]


def test_strategy_backtest_rejects_unknown_fields(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": STRATEGY_CODE, "unknown": True},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "removed_field",
    ["strategy_params", "factor_code", "factor_name", "data_dir", "backtest_engine", "include_equity"],
)
def test_strategy_backtest_rejects_removed_request_fields(market_data_dir, removed_field):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": STRATEGY_CODE, removed_field: "legacy"},
    )
    assert response.status_code == 422


def test_structured_factor_portfolio_strategy_backtest(market_data_dir):
    pe_ttm = pd.DataFrame(
        np.linspace(5.0, 30.0, 90 * 12).reshape(90, 12),
        index=pd.bdate_range("2022-01-03", periods=90),
        columns=[f"S{i:03d}" for i in range(12)],
    )
    pe_ttm.index.name = "datetime"
    pe_ttm.reset_index().to_parquet(market_data_dir / "pe_ttm.parquet", index=False)

    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": STRUCTURED_STRATEGY_CODE, "include_positions": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["strategy"] == "CompositeFactorStrategy"
    assert body["positions"]


def test_factor_api_reads_current_market_data_layout(market_data_dir):
    import shutil

    current = market_data_dir / "current"
    panels = current / "panels"
    metadata = current / "metadata"
    panels.mkdir(parents=True)
    metadata.mkdir()
    for path in market_data_dir.glob("*.parquet"):
        target_dir = metadata if path.name == "stock_info.parquet" else panels
        shutil.copy2(path, target_dir / path.name)
    shutil.copytree(market_data_dir / "display", current / "display")
    shutil.copytree(market_data_dir / "benchmark", current / "benchmark")

    response = client.post("/api/backtest/factor", json=_request_payload())
    assert response.status_code == 200
    assert response.json()["error"] is None
