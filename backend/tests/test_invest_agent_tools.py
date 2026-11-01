# -*- coding: utf-8 -*-
"""手机端 Agent 工具层：对比、穿透、护栏、量化选股、语音实体校正。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.invest import agent_tools  # noqa: E402


class FakeConn:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.committed = False

    def execute(self, sql, args=()):
        self.executed.append((sql, args))
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return list(self.rows)

    def commit(self):
        self.committed = True


def test_score_candidates_prefers_cheap_high_dividend_and_momentum() -> None:
    rows = [
        {"code": "A", "name": "A", "pe": 8.0, "dividend": 5.0, "momentum": 12.0},
        {"code": "B", "name": "B", "pe": 40.0, "dividend": 1.0, "momentum": -8.0},
        {"code": "C", "name": "C", "pe": 20.0, "dividend": 2.0, "momentum": 2.0},
    ]
    out = agent_tools._score_candidates(rows, top=2)
    assert [r["code"] for r in out] == ["A", "C"]
    assert out[0]["score"] > out[1]["score"]
    assert {p[0] for p in out[0]["parts"]} == {"低估值", "高股息", "20 日动量"}


def test_score_candidates_handles_missing_factors() -> None:
    out = agent_tools._score_candidates(
        [{"code": "A", "pe": None, "dividend": None, "momentum": None}], top=5
    )
    assert out[0]["score"] == 0
    assert out[0]["parts"] == []


def test_correct_entities_exact_name_and_code(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_tools.rules,
        "rows",
        lambda conn, sql, args=(): [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "300750", "name": "宁德时代"},
        ],
    )
    out = agent_tools.correct_entities(FakeConn(), "贵州茅台 600519 怎么看")
    assert {e["code"] for e in out["entities"]} == {"600519"}
    assert out["corrections"] == []


def test_correct_entities_suggests_close_name(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_tools.rules,
        "rows",
        lambda conn, sql, args=(): [{"code": "300750", "name": "宁德时代"}],
    )
    out = agent_tools.correct_entities(FakeConn(), "宁德时带今天怎么样")
    assert out["corrections"][0]["to"] == "宁德时代"


def test_compare_context_extracts_same_fields(monkeypatch) -> None:
    def fake_build_stock(conn, code, period="daily"):
        return {
            "quote": {"code": code, "name": code, "price": 10, "changePct": 1},
            "technical": {"return20": 3, "drawdown": -2, "trend": "偏强"},
            "valuation": {"pe": 12, "pb": 2, "pePercentile": 30},
            "report": {"revenue": 100, "netProfit": 10},
            "dataDate": "2026-10-30",
        }

    monkeypatch.setattr(agent_tools.rules, "build_stock", fake_build_stock)
    out = agent_tools.compare_context(FakeConn(), "600519", "300750")
    assert out["a"]["code"] == "600519"
    assert out["b"]["pe"] == 12
    assert out["a"]["revenue"] == 100


def test_portfolio_penetration_uses_etf_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_tools.rules,
        "portfolio_rows",
        lambda conn, uid: [
            {"code": "510300", "name": "沪深300ETF", "shares": 100, "price": 4.0},
            {"code": "600519", "name": "贵州茅台", "shares": 1, "price": 100.0},
        ],
    )
    monkeypatch.setattr(
        agent_tools.etf,
        "profile",
        lambda code, top=20: {
            "tracking": "index_proxy",
            "constituents": [
                {"symbol": "600519.SH", "weight": 50.0},
                {"symbol": "000001.SZ", "weight": 50.0},
            ],
        },
    )
    monkeypatch.setattr(agent_tools.etf, "is_etf", lambda code: code == "510300")
    monkeypatch.setattr(
        agent_tools.rules,
        "rows",
        lambda conn, sql, args=(): [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "000001", "name": "平安银行"},
        ],
    )
    out = agent_tools.portfolio_penetration(FakeConn(), 1)
    look = {x["code"]: x["weight"] for x in out["lookthrough"]}
    assert look["600519"] == 60.0
    assert look["000001"] == 40.0
    assert out["etfWeight"] == 80.0
    assert out["coveragePct"] == 100.0
