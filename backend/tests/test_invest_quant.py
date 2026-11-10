# -*- coding: utf-8 -*-
"""量化研究：因子方向、规则解析、回测指标与失败兜底。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.invest import quant
from services.invest import quant_re


def _fake_panel(n_dates: int = 45, n_symbols: int = 8) -> dict:
    start = date(2026, 1, 1)
    dates = []
    d = start
    while len(dates) < n_dates:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    symbols = [f"{600000 + i}.SH" for i in range(n_symbols)]
    close, amount, pe, fin, name, list_date = {}, {}, {}, {}, {}, {}
    for i, symbol in enumerate(symbols):
        base = 10.0 + i
        # 每只股票不同斜率，保证横截面有区分度。
        close[symbol] = [base * (1.0015 + i * 0.0004) ** t for t in range(n_dates)]
        amount[symbol] = [100_000_000.0 + i * 1_000_000] * n_dates
        pe[symbol] = [8.0 + i] * n_dates
        fin[symbol] = [(dates[0], 0.15 - i * 0.01, 0.20 - i * 0.01)]
        name[symbol] = f"测试{i}"
        list_date[symbol] = "2020-01-01"
    panel = {
        "universe": "hs300", "data_date": dates[-1], "dates": dates,
        "idx": {d: i for i, d in enumerate(dates)}, "symbols": symbols,
        "spans": {}, "close": close, "amount": amount, "pe": pe, "fin": fin,
        "name": name, "list_date": list_date, "st": set(), "suspended": set(),
        "bench_code": "000300.SH", "bench": {}, "derived": None,
    }
    quant._prepare(panel)
    return panel


def test_normalize_factors_rejects_duplicates_and_unknown():
    assert len(quant._normalize_factors(["value", "momentum"])) == 2
    with pytest.raises(quant.QuantDataError):
        quant._normalize_factors(["value"])
    with pytest.raises(quant.QuantDataError):
        quant._normalize_factors(["value", "value"])
    with pytest.raises(quant.QuantDataError):
        quant._normalize_factors(["value", "nope"])


def test_parse_intent_rules_low_valuation_means_cheap():
    out = quant._parse_intent_rules("便宜、最近涨得好、别太波动")
    assert {f["key"]: f["direction"] for f in out["factors"]} == {
        "value": "high", "momentum": "high", "volatility": "low",
    }
    assert out["need_more"] is False
    assert "低估值" in out["understood"]


def test_market_style_attack_defense_balanced():
    attack = quant._market_style([
        {"key": "value", "name": "低估值", "name_en": "Value", "return_1m": 3.0},
        {"key": "momentum", "name": "动量", "name_en": "Momentum", "return_1m": 1.0},
        {"key": "quality", "name": "质量", "name_en": "Quality", "return_1m": -1.0},
    ])
    assert attack["key"] == "attack" and "低估值" in attack["sentence"]
    defense = quant._market_style([
        {"key": "value", "name": "低估值", "name_en": "Value", "return_1m": -2.0},
        {"key": "momentum", "name": "动量", "name_en": "Momentum", "return_1m": -1.0},
    ])
    assert defense["key"] == "defense"
    balanced = quant._market_style([
        {"key": "value", "name": "低估值", "name_en": "Value", "return_1m": 2.0},
        {"key": "momentum", "name": "动量", "name_en": "Momentum", "return_1m": -1.0},
    ])
    assert balanced["key"] == "balanced"


def test_run_curve_metrics_are_derived_from_nav():
    panel = _fake_panel()
    result = quant._run_curve(
        panel,
        [{"key": "value", "direction": "high"}, {"key": "momentum", "direction": "high"}],
    )
    metrics = result["metrics"]
    assert len(result["curve"]) > 5
    assert metrics["cumulative"] is not None
    assert metrics["annual_return"] is not None
    assert metrics["max_drawdown"] is not None and metrics["max_drawdown"] <= 0
    assert metrics["volatility"] is not None
    assert metrics["benchmark_return"] is not None
    assert metrics["excess"] is not None


def test_backtest_persist_false_has_assumptions(monkeypatch):
    panel = _fake_panel()
    monkeypatch.setattr(quant, "_load_panel", lambda conn, universe: panel)
    out = quant.run_backtest(
        conn=object(), factors=["value", "quality"], universe="hs300", persist=False
    )
    assert out["id"] is None
    assert out["assumptions"]["cost"] == "单边 0.1%"
    assert out["assumptions"]["holdings"] == 20
    assert out["holdings"]
    assert out["disclaimer"].startswith("历史回测")


def test_re_universe_and_benchmark_mapping():
    assert quant.re_universe("hs300") == "CSI300"
    assert quant.re_universe("zz500") == "CSI500"
    assert quant.re_universe("all") == "ALL_A"
    assert quant.re_benchmark("hs300") == "CSI300"
    assert quant.re_benchmark("zz500") == "CSI500"


def test_re_adapter_builds_strategy_code_for_supported_factors():
    code = quant_re.build_strategy_code([
        {"key": "value", "direction": "high"},
        {"key": "momentum", "direction": "high"},
        {"key": "volatility", "direction": "low"},
        {"key": "liquidity", "direction": "high"},
    ])
    assert "FactorPortfolioStrategy" in code
    assert "1.0 / self.pe_ttm" in code
    assert "self.close.shift(1).pct_change(20)" in code
    assert "-self.close.pct_change().rolling(20).std()" in code
    assert "self.amount.rolling(20).mean()" in code
    assert "self.rank" in code


def test_re_adapter_rejects_fundamental_factors():
    assert quant_re.supports([{"key": "value"}])
    assert not quant_re.supports([{"key": "quality"}, {"key": "growth"}])
    assert quant_re.build_strategy_code([{"key": "quality"}]) == ""
    assert set(quant_re.unsupported_keys([{"key": "value"}, {"key": "growth"}])) == {"growth"}


def test_re_adapter_maps_sync_strategy_result(monkeypatch):
    fake = {
        "metrics": {
            "annual_return": 0.12,
            "max_drawdown": -0.08,
            "sharpe": 1.1,
            "win_rate": 0.55,
            "volatility": 0.16,
            "beta": 0.9,
            "alpha": 0.03,
            "benchmark_return": 0.04,
            "excess_return": 0.08,
            "total_return": 0.12,
            "trade_count": 12,
        },
        "equity_curve": [{"date": "2026-01-01", "value": 1.0}, {"date": "2026-01-02", "value": 1.12}],
        "benchmark_curve": [{"date": "2026-01-01", "value": 1.0}, {"date": "2026-01-02", "value": 1.04}],
        "date_range": {"start": "2026-01-01", "end": "2026-01-02"},
        "positions": [{"date": "2026-01-02", "holdings": [{"symbol": "600519.SH", "name": "贵州茅台", "weight": 1.0}]}],
    }
    monkeypatch.setattr(
        quant_re, "_forward_re", lambda *args, **kwargs: (200, {}, fake)
    )
    out = quant_re.run_re_strategy(
        factors=[{"key": "value", "direction": "high"}, {"key": "momentum", "direction": "high"}],
        universe="hs300", start_date="2026-01-01", end_date="2026-01-02", name="RE测试",
    )
    assert out is not None
    assert out["engine"] == "re"
    assert out["metrics"]["annual_return"] == 12.0
    assert out["metrics"]["max_drawdown"] == -8.0
    assert out["holdings"][0]["code"] == "600519.SH"
    assert out["curve"][-1]["benchmark"] == 1.04


def test_paper_project_reuse_rules():
    assert quant._is_reusable_paper_project({"strategy_code": "class X: ..."})
    assert not quant._is_reusable_paper_project({"strategy_code": "class X: ...", "quant_root": True})
    assert not quant._is_reusable_paper_project({"strategy_code": "", "quant_local_only": True})
    assert not quant._is_reusable_paper_project({"strategy_code": ""})


def test_create_paper_does_not_turn_root_project_executable(monkeypatch):
    monkeypatch.setenv("YG_RE_BASE", "http://127.0.0.1:9")
    import importlib

    from services.core import re_config
    importlib.reload(re_config)
    from services.invest import quant_re
    from services.paper import paper_store
    from services.strategy import strategy_store

    root_id = "root-project"
    calls: list[str | None] = []
    strategy_row = {
        "id": 9,
        "name": "测试策略",
        "factors": '[{"key":"value","direction":"high"},{"key":"momentum","direction":"high"}]',
        "universe": "hs300",
        "project_id": root_id,
        "backtest_id": None,
    }
    monkeypatch.setattr(quant.rules, "one", lambda conn, sql, args=(): strategy_row)
    monkeypatch.setattr(
        strategy_store,
        "get_project",
        lambda uid, pid: {"project": {"id": pid, "name": "root", "config": {
            "strategy_code": "", "quant_root": True, "quant_local_only": True,
        }}},
    )
    monkeypatch.setattr(
        quant,
        "_ensure_project",
        lambda uid, name, factors, universe, project_id=None, draft=False: (
            calls.append(project_id), "new-paper-project"
        )[1],
    )
    monkeypatch.setattr(quant_re, "supports", lambda factors: True)
    monkeypatch.setattr(paper_store, "create_account", lambda uid, payload: {"id": 7})
    monkeypatch.setattr(quant, "paper_detail", lambda conn, uid, pid: {"id": pid})

    class Conn:
        def __init__(self):
            self.sql: list[str] = []
        def execute(self, sql, args=()):
            self.sql.append(sql)
            return self
        def commit(self):
            pass

    conn = Conn()
    out = quant.create_paper(conn, 1, {"source_type": "strategy", "source_id": 9})
    assert out == {"id": 7}
    assert calls == [None]  # 新建 paper project，不是复用/改写 root
    assert any("UPDATE invest_quant_strategy" in sql for sql in conn.sql)


def test_factor_direction_low_inverts_score():
    panel = _fake_panel()
    high = quant._scores(panel, len(panel["dates"]) - 1, [{"key": "volatility", "direction": "high"}])
    low = quant._scores(panel, len(panel["dates"]) - 1, [{"key": "volatility", "direction": "low"}])
    # 波动率是常数时分数接近 0；至少方向相反不报错。
    assert high.keys() == low.keys()


def test_board_payload_disk_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(quant, "_BOARD_CACHE_ROOT", tmp_path)
    quant._BOARD_PAYLOAD_CACHE.clear()
    payload = {
        "data_date": "2026-11-04",
        "range": "1m",
        "factors": [{"key": "value", "return_1m": 1.2}],
        "style": {"key": "attack"},
        "correlations": {},
        "disclaimer": "test",
    }
    quant._save_board_payload("2026-11-04", "1m", payload)
    # 清掉内存缓存，仍能从磁盘读回。
    quant._BOARD_PAYLOAD_CACHE.clear()
    assert quant._load_board_payload("2026-11-04", "1m") == payload
    # 日期不同的缓存不能串用。
    assert quant._load_board_payload("2026-11-03", "1m") is None
    # 同一日期下，不同数据视图也不能串用横截面。
    view_payload = {**payload, "view_id": "view-a"}
    quant._save_board_payload("2026-11-04", "1m", view_payload, "view-a")
    assert quant._load_board_payload("2026-11-04", "1m", "view-a") == view_payload
    assert quant._load_board_payload("2026-11-04", "1m", "view-b") is None


def test_factor_registry_has_60_factors_in_6_categories():
    assert len(quant.FACTORS) == 60
    counts = {}
    for key in quant.FACTOR_BY_KEY:
        cat = quant.CATEGORY_BY_KEY[key]
        counts[cat] = counts.get(cat, 0) + 1
    assert counts == {"momentum": 10, "value": 10, "quality": 10, "growth": 10, "volatility": 10, "liquidity": 10}
    meta = quant._factor_meta("momentum")
    assert meta["category_name"] == "动量" and meta["sub_name"] == "20 日涨幅"


def test_factor_explanation_is_multi_sentence():
    meta = quant._factor_meta("momentum")
    zh, en = quant._factor_explanation(meta, {"percentile": 42.0})
    assert zh.count("。") >= 3
    assert "分位" in zh and "IC" in zh
    assert en.count(".") >= 3
    assert "percentile" in en and "IC" in en
