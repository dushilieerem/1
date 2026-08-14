"""FEAT-018 的因子、向量化策略 API 集成验证。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from researchengine.api import app


client = TestClient(app)


@pytest.fixture()
def research_assets_market_data(tmp_path, monkeypatch):
    dates = pd.bdate_range("2024-01-02", periods=40)
    symbols = ["S000", "S001", "S002"]
    close = pd.DataFrame({
        "S000": np.linspace(100, 120, len(dates)),
        "S001": np.linspace(100, 140, len(dates)),
        "S002": np.linspace(100, 110, len(dates)),
    }, index=dates)
    for field, values in {
        "open": close * 0.99, "high": close * 1.01, "low": close * 0.98,
        "close": close, "volume": close * 1000, "amount": close * 10000,
    }.items():
        values.index.name = "datetime"
        values.reset_index().to_parquet(tmp_path / f"{field}.parquet", index=False)
    display_dir = tmp_path / "display"
    display_dir.mkdir()
    display_columns = pd.MultiIndex.from_product(
        [symbols, ["open", "high", "low", "close"]]
    )
    display = pd.DataFrame(index=dates, columns=display_columns, dtype=float)
    for symbol in symbols:
        for field in ("open", "high", "low", "close"):
            display[(symbol, field)] = close[symbol]
    display.index.name = "date"
    display.to_parquet(display_dir / "unadjusted_price.parquet")
    pd.DataFrame({"code": symbols, "name": symbols}).to_parquet(
        tmp_path / "stock_info.parquet", index=False
    )

    monkeypatch.setenv("SVQUANT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SVQUANT_BACKTEST_CACHE_DIR", str(tmp_path / "cache"))
    return dates


def test_factor_backtest_uses_webapp_resolved_snapshots(research_assets_market_data):
    response = client.post("/api/backtest/factor", json={
        "factor_code": "def close_change(self):\n    return self.close.pct_change()",
        "factor_name": "close_change", "portfolio_type": "long_only", "groups": 2,
        "universe_snapshot": {
            "asset_id": "selected", "version": "v3", "content_hash": "universe-hash",
            "symbols": ["S000", "S001"], "membership_mode": "static",
        },
        "benchmark_snapshot": {
            "asset_id": "selected_equal", "version": "v3", "content_hash": "benchmark-hash",
            "weights": {"S000": 0.25, "S001": 0.75}, "pricing": "close_to_close",
        },
    })

    body = response.json()
    assert response.status_code == 200
    assert body["error"] is None
    assert body["meta"]["universe_asset"]["constituent_count"] == 2
    assert body["meta"]["benchmark_asset"]["pricing"] == "close_to_close"
    dates = research_assets_market_data
    start = pd.Timestamp(body["benchmark_curve"][0]["date"])
    close = pd.DataFrame({
        "S000": np.linspace(100, 120, len(dates)),
        "S001": np.linspace(100, 140, len(dates)),
    }, index=dates).loc[start:]
    expected = (1 + close.pct_change().iloc[1:].dot(pd.Series({"S000": 0.25, "S001": 0.75}))).prod()
    assert body["benchmark_curve"][-1]["value"] == pytest.approx(expected)


def test_vectorized_strategy_uses_assets_and_rejects_mixed_source(research_assets_market_data):
    strategy_code = """import pandas as pd
class EqualWeight:
    def __init__(self, close): self.close = close
    def generate_signals(self):
        return pd.DataFrame(0.5, index=self.close.index, columns=self.close.columns)
"""
    response = client.post("/api/backtest/strategy", json={
        "strategy_code": strategy_code,
        "universe_snapshot": {
            "asset_id": "selected", "version": "v3", "content_hash": "universe-hash",
            "symbols": ["S000", "S001"],
        },
        "benchmark_snapshot": {
            "asset_id": "selected_equal", "version": "v3", "content_hash": "benchmark-hash",
            "weights": {"S000": 0.25, "S001": 0.75},
        },
    })
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["universe"] == "selected"
    assert body["meta"]["benchmark_asset"]["constituent_count"] == 2

    invalid = client.post("/api/backtest/strategy", json={
        "strategy_code": strategy_code, "universe": "CSI500",
        "universe_snapshot": {
            "asset_id": "selected", "version": "v3", "content_hash": "universe-hash",
            "symbols": ["S000", "S001"],
        },
    })
    assert invalid.status_code == 422
