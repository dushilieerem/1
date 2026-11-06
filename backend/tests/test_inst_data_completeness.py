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
    assert any("一致行动人" in x for x in out["governance"]["missing"])


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


def test_build_research_includes_peers_history_and_net_debt() -> None:
    company = {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "market": "CN",
        "industry": "食品饮料",
        "data_status": "real",
        "ref_price": 1400,
    }
    built = svc._build_research(company, mode="valuation")
    facts = built["facts"]
    assert len(facts["financials"]) > 8
    assert facts["peer_summary"]["count"] > 0
    assert facts["peer_summary"]["revenue_yoy_median"] is not None
    assert facts["history_summary"]["annual_points"] >= 1
    assert facts["data_completeness"]["governance"]["level"] == "partial"
    assert facts["data_completeness"]["governance"]["gate_cap"] == "fail"
    assert facts["holder_summary"]["is_control_known"] is False
    assert facts["valuation_extra"]["net_debt_proxy"] is not None
    valuation = built["valuation"] or {}
    assert "equity_value" in valuation
    assert valuation.get("net_debt_proxy")


def test_governance_holders_do_not_unlock_gate() -> None:
    out = svc._data_completeness(
        ind={"industry_code": "801120.SI"},
        peers=[{"symbol": "A"}],
        history={"periods": 40},
        fin=[{"report_date": "2025-12-31"}],
        val={"pe_ttm": 10},
        holders={"report_date": "2025-12-31", "top10_ratio_pct": 72.24},
        segments={"report_date": "2025-12-31"},
        audit={"report_date": "2025-12-31", "opinion_type": "标准无保留意见", "red_flag": False},
    )
    assert out["governance"]["level"] == "partial"
    assert out["governance"]["gate_cap"] == "fail"
    assert any("前十大股东" in x for x in out["governance"]["have"])
    assert any("分部收入" in x for x in out["business_model"]["have"])
    assert any("审计意见类型" in x for x in out["financial"]["have"])
    # 治理 partial 但 gate_cap=fail，仍然必须 fail
    gated = svc._apply_data_gate({"gate": "pass"}, out["governance"])
    assert gated["gate"] == "fail"


def test_data_platform_pilot_access() -> None:
    from services.core.db import get_conn
    from services.institution import data_platform

    with get_conn() as conn:
        holders = data_platform.holder_summary(conn, "600519.SH", "2026-11-06")
        segments = data_platform.segment_summary(
            conn, "600519.SH", "2026-11-06", consolidated_revenue=168837900000
        )
        audit = data_platform.audit_summary(conn, "600519.SH", "2026-11-06")
    assert holders and holders["count"] == 10
    assert holders["top10_ratio_pct"] > 0
    assert holders["is_control_known"] is False
    assert "前十大" in holders["note"]
    assert segments and segments["types"]
    assert any(block.get("revenue_vs_consolidated_pct") is not None for block in segments["types"].values())
    assert audit and audit["is_standard"] is True
    assert audit["red_flag"] is False
