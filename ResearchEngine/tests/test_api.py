"""ResearchEngine 因子回测 API 测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from researchengine.api import app


client = TestClient(app)

COMBO_FACTOR_CODE = '''def volume_20d(self, window: int = 20):
    return self.volume / self.volume.rolling(window).mean()

def amount_20d(self, window: int = 20):
    return self.amount / self.amount.rolling(window).mean()

def combo_factor(self):
    return 0.5 * self.volume_20d() + 0.5 * self.amount_20d()'''

BUILTIN_COMBO_FACTOR_CODE = '''def combo_factor(self):
    return 0.5 * self.jq_kurtosis20() + 0.5 * self.qlib_alpha158_kmid()'''

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

    pd.DataFrame({
        "code": symbols,
        "industry": ["银行"] * 6 + ["医药"] * 6,
    }).to_parquet(tmp_path / "stock_info.parquet", index=False)

    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    benchmark = pd.DataFrame(
        {"000300_close": np.linspace(4000.0, 4300.0, len(dates))}, index=dates
    )
    benchmark.to_parquet(benchmark_dir / "index_000300.parquet")
    pd.DataFrame(
        {symbol: [1] for symbol in symbols}, index=[dates[-1]]
    ).to_parquet(benchmark_dir / "CSI500_constituents.parquet")
    monkeypatch.setenv("SVQUANT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SVQUANT_BACKTEST_CACHE_DIR", str(tmp_path / "backtest_cache"))
    return tmp_path


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


def test_factor_backtest_groups_and_benchmark(market_data_dir):
    response = client.post("/api/backtest/factor", json=_request_payload())
    assert response.status_code == 200
    assert response.headers["X-SVQuant-Cache"] == "MISS"
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["rebalance_days"] == 15
    assert body["meta"]["groups"] == 3
    assert body["meta"]["benchmark"] == "CSI300"
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
    assert len(body["benchmark_curve"]) > 0
    assert body["excess_return"] is not None


def test_factor_backtest_loads_builtin_factor_library(market_data_dir):
    payload = _request_payload()
    payload.pop("factor_code")
    payload.update({
        "library_name": "jq_compat_risk",
        "factor_name": "jq_kurtosis60",
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_factor_backtest_custom_factor_can_combine_builtin_library_methods(market_data_dir):
    payload = _request_payload()
    payload.update({
        "factor_code": BUILTIN_COMBO_FACTOR_CODE,
        "factor_name": "combo_factor",
        "library_name": ["jq_compat_risk", "qlib_alpha"],
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
    payload["library_name"] = ["jq_compat_risk", "qlib_alpha"]
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
    }
    assert body["metrics"]["total_return"] is not None
    assert len(body["equity_curve"]) > 0
    assert len(body["benchmark_curve"]) > 0
    assert body["excess_return"] is not None
    assert body["positions"]


def test_strategy_backtest_returns_business_error_for_invalid_contract(market_data_dir):
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": "class Invalid:\n    pass"},
    )
    assert response.status_code == 200
    assert "generate_signals" in response.json()["error"]


def test_strategy_backtest_returns_business_error_when_benchmark_is_unavailable(market_data_dir):
    (market_data_dir / "benchmark" / "index_000300.parquet").unlink()
    response = client.post(
        "/api/backtest/strategy",
        json={"strategy_code": STRATEGY_CODE, "benchmark": "CSI300"},
    )
    assert response.status_code == 200
    assert "index_000300.parquet" in response.json()["error"]


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
