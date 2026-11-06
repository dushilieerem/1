# -*- coding: utf-8 -*-
"""六维数据完备性：10 年摘要、同业中位数、数据闸门与净债务近似。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")
os.environ.setdefault("RE_CATALOG_SYNC_ENABLED", "0")
os.environ.setdefault("SVQUANT_PANEL_DAILY_ENABLED", "0")
os.environ.setdefault("SVQUANT_PAPER_TRADING_ENABLED", "0")
os.environ.setdefault("NEWS_INGEST_INTERVAL_SEC", "0")
os.environ.setdefault("RE_CATALOG_WARM_ENABLED", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution import inst_service as svc  # noqa: E402


def test_history_summary_uses_annual_points() -> None:
    fin = [
        {"report_date": "2025-12-31", "revenue": 121, "gross_margin": 0.3, "roe": 0.12, "operating_cf": 12, "net_profit": 10, "free_cash_flow": 8},
        {"report_date": "2025-09-30", "revenue": 90, "gross_margin": 0.29, "roe": 0.11, "operating_cf": 9, "net_profit": 7, "free_cash_flow": 6},
        {"report_date": "2024-12-31", "revenue": 100, "gross_margin": 0.28, "roe": 0.10, "operating_cf": 8, "net_profit": 8, "free_cash_flow": 5},
    ]
    out = svc._history_summary(fin)
    assert out["annual_points"] == 2
    assert abs(out["revenue_cagr"] - 0.21) < 1e-9
    assert abs(out["gross_margin_median"] - 0.29) < 1e-9
    assert abs(out["roe_median"] - 0.11) < 1e-9
    assert out["fcf_positive_ratio"] == 1.0


def test_peer_summary_skips_missing_values() -> None:
    peers = [
        {"symbol": "A", "revenue_yoy": 0.1, "gross_margin": 0.2, "roe": 0.08, "pe_ttm": 10, "pb_mrq": 1.0},
        {"symbol": "B", "revenue_yoy": 0.3, "gross_margin": 0.4, "roe": 0.12, "pe_ttm": 20, "pb_mrq": 2.0},
        {"symbol": "C", "revenue_yoy": None, "gross_margin": None, "roe": None, "pe_ttm": None, "pb_mrq": None},
    ]
    out = svc._peer_summary(peers)
    assert out["count"] == 3
    assert out["with_financials"] == 2
    assert out["revenue_yoy_median"] == 0.2
    assert out["gross_margin_median"] == 0.30000000000000004 or abs(out["gross_margin_median"] - 0.3) < 1e-9
    assert out["pe_median"] == 15


def test_data_completeness_governance_is_missing() -> None:
    out = svc._data_completeness(
        ind={"industry_code": "801120.SI"},
        peers=[{"symbol": "A"}],
        history={"periods": 40},
        fin=[{"report_date": "2025-12-31"}],
        val={"pe_ttm": 10},
    )
    assert out["governance"]["level"] == "missing"
    assert out["industry"]["level"] == "partial"
    assert out["valuation"]["level"] == "partial"
    assert any("前十大股东" in x for x in out["governance"]["missing"])


def test_data_gate_caps_agent_gate() -> None:
    gov = svc._apply_data_gate({"gate": "pass"}, {"level": "missing"})
    assert gov["gate"] == "fail"
    assert gov["gate_original"] == "pass"
    industry = svc._apply_data_gate({"gate": "pass"}, {"level": "partial"})
    assert industry["gate"] == "watch"
    ok = svc._apply_data_gate({"gate": "pass"}, {"level": "sufficient"})
    assert ok["gate"] == "pass"


def test_memo_decision_capped_by_gates() -> None:
    version = {
        "six_dim": [
            {"key": "governance", "gate": "fail"},
            {"key": "industry", "gate": "watch"},
        ],
        "industry_analysis": {"gate": "watch"},
    }
    out = svc._apply_memo_data_gate({"decision": "proceed", "summary": "买入"}, version)
    assert out["decision"] == "watch"
    assert "governance" in out["data_gate_note"]
    all_pass = svc._apply_memo_data_gate(
        {"decision": "proceed"},
        {"six_dim": [{"key": "industry", "gate": "pass"}], "industry_analysis": {"gate": "pass"}},
    )
    assert all_pass["decision"] == "proceed"


def test_build_research_includes_peers_history_and_net_debt(monkeypatch) -> None:
    company = {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "market": "CN",
        "industry": "食品饮料",
        "data_status": "real",
        "ref_price": 1400,
    }
    # 单测不依赖 CI 空库里的真实行情/财务；固定返回十年财务、同业和估值。
    financials = [
        {
            "report_date": f"{2016 + i}-12-31", "notice_date": f"{2017 + i}-03-31",
            "revenue": 100 + i * 10, "net_profit": 20 + i * 2, "gross_margin": 0.45,
            "roe": 0.20, "operating_cf": 30 + i, "free_cash_flow": 20 + i,
            "total_liabilities": 80.0, "cash": 50.0,
        }
        for i in range(9)
    ]
    peers = [
        {"symbol": "A.SH", "revenue_yoy": 0.1, "gross_margin": 0.4, "roe": 0.12, "pe_ttm": 20, "pb_mrq": 3},
        {"symbol": "B.SH", "revenue_yoy": 0.2, "gross_margin": 0.5, "roe": 0.15, "pe_ttm": 30, "pb_mrq": 4},
    ]
    monkeypatch.setattr(svc.md, "latest_bar", lambda *a, **k: {"close": 1400, "trade_date": "2026-11-05"})
    monkeypatch.setattr(svc.md, "valuation_latest", lambda *a, **k: {"pe_ttm": 25.0, "pb_mrq": 8.0, "dividend_yield_ttm": 0.02, "total_shares": 1_000_000_000})
    monkeypatch.setattr(svc.md, "valuation_percentile", lambda *a, **k: {"pe_percentile": 0.5, "pb_percentile": 0.6})
    monkeypatch.setattr(svc.md, "risk_stats", lambda *a, **k: {"annual_vol": 0.2, "max_drawdown": -0.3})
    monkeypatch.setattr(svc.md, "industry_latest", lambda *a, **k: {"industry_code": "801120.SI", "name": "食品饮料"})
    monkeypatch.setattr(svc.md, "financials", lambda *a, **k: financials)
    monkeypatch.setattr(svc.md, "industry_peers", lambda *a, **k: peers)
    monkeypatch.setattr(svc.md, "share_capital_history", lambda *a, **k: [{"effective_date": "2025-12-31", "total_shares": 1_000_000_000}])
    monkeypatch.setattr(svc.md, "dividend_history", lambda *a, **k: [{"ex_date": "2025-06-30", "cash_per_share": 20}])
    built = svc._build_research(company, mode="valuation")
    facts = built["facts"]
    assert len(facts["financials"]) > 8
    assert facts["peer_summary"]["count"] > 0
    assert facts["peer_summary"]["revenue_yoy_median"] is not None
    assert facts["history_summary"]["annual_points"] >= 1
    assert facts["data_completeness"]["governance"]["level"] == "missing"
    assert facts["valuation_extra"]["net_debt_proxy"] is not None
    valuation = built["valuation"] or {}
    assert "equity_value" in valuation
    assert valuation.get("net_debt_proxy")
