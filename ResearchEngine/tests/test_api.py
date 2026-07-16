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


@pytest.fixture()
def market_data_dir(tmp_path, monkeypatch):
    """生成最小行情和 CSI300 基准数据。"""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2022-01-03", periods=90)
    symbols = [f"S{i:03d}" for i in range(12)]
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (90, 12)), axis=0))
    for name, values in (
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
