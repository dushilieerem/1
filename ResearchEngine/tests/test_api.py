"""ResearchEngine 因子回测 API 测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from researchengine.api import app
from researchengine.api.market_data import _market_symbol, _panel_symbol
from researchengine.api.runner import _sample_positions, _serialize_rebalance_logs


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

    pd.DataFrame({
        "code": symbols,
        "name": [f"股票{i:03d}" for i in range(12)],
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
    pd.DataFrame(
        {
            symbol: [1, int(symbol in {"S000", "S001"})]
            for symbol in symbols
        },
        index=[dates[-2], dates[-1]],
    ).to_parquet(benchmark_dir / "CSI300_constituents.parquet")
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
    assert body["bars"][0]["open"] == pytest.approx(body["bars"][0]["close"] * 0.995)


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
    assert _panel_symbol("000001.SZ") == "000001"


def test_daily_bars_returns_not_found_or_invalid_range(market_data_dir):
    assert client.get("/api/market-data/daily/UNKNOWN").status_code == 404
    assert client.get(
        "/api/market-data/daily/S000",
        params={"start": "2022-01-07", "end": "2022-01-05"},
    ).status_code == 422


def test_daily_bars_returns_service_unavailable_when_field_missing(market_data_dir):
    (market_data_dir / "high.parquet").unlink()
    response = client.get("/api/market-data/daily/S000")
    assert response.status_code == 503


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
        "library_name": "risk_indicators",
        "factor_name": "kurtosis60",
    })
    response = client.post("/api/backtest/factor", json=payload)

    assert response.status_code == 200
    assert response.json()["error"] is None


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
    required_symbols = frozenset({"S999"})

    def initialize(self, context):
        pass''',
            "engine_mode": "event",
            "universe": "CSI500",
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] == (
        "ValueError: 策略所需标的不在所选股票池 CSI500: ['S999']；"
        "请调整股票池或策略标的后重试"
    )


def test_event_strategy_accepts_exchange_code_against_raw_panel_symbols(market_data_dir):
    for field in ("open", "high", "low", "close"):
        path = market_data_dir / f"{field}.parquet"
        panel = pd.read_parquet(path)
        panel["600519"] = 100.0
        panel.to_parquet(path, index=False)
    constituents_path = market_data_dir / "benchmark" / "CSI300_constituents.parquet"
    constituents = pd.read_parquet(constituents_path)
    constituents["600519"] = 1
    constituents.to_parquet(constituents_path)

    response = client.post(
        "/api/backtest/strategy",
        json={
            "strategy_code": '''class SingleStockStrategy:
    required_symbols = frozenset({"600519.SH"})

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
    shutil.copytree(market_data_dir / "benchmark", current / "benchmark")

    response = client.post("/api/backtest/factor", json=_request_payload())
    assert response.status_code == 200
    assert response.json()["error"] is None
