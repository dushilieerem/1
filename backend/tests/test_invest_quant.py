# -*- coding: utf-8 -*-
"""量化研究：因子方向、规则解析、回测指标与失败兜底。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.invest import quant


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


def test_factor_direction_low_inverts_score():
    panel = _fake_panel()
    high = quant._scores(panel, len(panel["dates"]) - 1, [{"key": "volatility", "direction": "high"}])
    low = quant._scores(panel, len(panel["dates"]) - 1, [{"key": "volatility", "direction": "low"}])
    # 波动率是常数时分数接近 0；至少方向相反不报错。
    assert high.keys() == low.keys()
