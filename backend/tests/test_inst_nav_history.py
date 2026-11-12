# -*- coding: utf-8 -*-
"""组合 / 单票净值曲线：纯计算测试，不连库、不读真实行情。"""
from __future__ import annotations

from datetime import datetime

from services.institution import portfolio_service as svc


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, portfolio_row, fills):
        self._portfolio = portfolio_row
        self._fills = fills

    def execute(self, sql, params=None):
        if "FROM inst_portfolio" in sql:
            return _Result([self._portfolio])
        return _Result(self._fills)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _setup(monkeypatch):
    portfolio = {"id": 1, "nav": 1_000_000.0, "cash": 899_000.0}
    fills = [
        {"symbol": "AAA.SZ", "side": "buy", "qty": 100.0, "price": 100.0, "fee": 10.0, "filled_at": datetime(2026, 11, 3, 10, 0)},
        {"symbol": "AAA.SZ", "side": "sell", "qty": 40.0, "price": 110.0, "fee": 5.0, "filled_at": datetime(2026, 11, 5, 10, 0)},
    ]
    bars = {
        "AAA.SZ": [
            {"trade_date": "2026-11-03", "close": 100.0},
            {"trade_date": "2026-11-04", "close": 105.0},
            {"trade_date": "2026-11-05", "close": 110.0},
        ]
    }
    monkeypatch.setattr(svc, "get_conn", lambda: _Conn(portfolio, fills))
    monkeypatch.setattr(svc, "_daily_bars", lambda symbol, start: bars.get(symbol, []))
    return portfolio, fills, bars


def test_nav_history_tracks_cash_and_positions(monkeypatch):
    _setup(monkeypatch)
    out = svc.nav_history(1)
    series = out["series"]
    assert [p["date"] for p in series] == ["2026-11-03", "2026-11-04", "2026-11-05"]
    # 买入当天：现金 1,000,000 - 10,000 - 10 = 989,990；持仓 100×100
    assert series[0]["cash"] == 989_990.0
    assert series[0]["invested"] == 10_000.0
    assert series[0]["nav"] == 999_990.0
    assert series[2]["cash"] == 989_990.0 + 4_400.0 - 5.0
    assert series[2]["invested"] == 60 * 110.0
    assert series[2]["nav"] == series[2]["cash"] + series[2]["invested"]
    assert out["base"] == 1_000_000.0


def test_nav_history_empty_without_fills(monkeypatch):
    monkeypatch.setattr(svc, "get_conn", lambda: _Conn({"id": 1, "nav": 1_000_000.0, "cash": 1_000_000.0}, []))
    out = svc.nav_history(1)
    assert out["series"] == [] and out["base"] == 1_000_000.0


def test_holding_nav_history_uses_net_qty_and_avg_cost(monkeypatch):
    _setup(monkeypatch)
    out = svc.holding_nav_history(1, "AAA.SZ")
    assert out["qty"] == 60.0
    # 成本 = (100×100 + 10 - (40×110 - 5)) / 60
    assert round(out["cost"], 4) == round((10_000 + 10 - 4_400 + 5) / 60, 4)
    assert out["series"][-1]["close"] == 110.0
    assert out["latest"]["pnl"] == round(60 * (110.0 - out["cost"]), 2)


def test_max_drawdown():
    assert svc._max_drawdown([100, 120, 90, 130]) == -25.0
    assert svc._max_drawdown([100, 110, 120]) == 0.0


def test_portfolio_position_pnl_and_today(monkeypatch):
    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(svc, "get_conn", lambda: _Ctx())
    monkeypatch.setattr(
        svc.repo,
        "portfolio",
        lambda scope, conn=None: (
            {"cash": 1_000.0, "nav": 2_000.0},
            [{"symbol": "AAA.SZ", "qty": 10.0, "cost": 100.0, "market_value": 1_000.0}],
        ),
    )
    monkeypatch.setattr(svc, "_idea_questions", lambda pos, scope: None)
    monkeypatch.setattr(svc.md, "latest_bar", lambda symbol, adjust="none": {"close": 110.0, "pre_close": 105.0})
    out = svc.portfolio(1)
    pos = out["positions"][0]
    assert pos["pnl"] == 100.0
    assert round(pos["pnl_pct"], 2) == 10.0
    assert pos["today_pnl"] == 50.0
    assert round(pos["today_pnl_pct"], 4) == round((110 / 105 - 1) * 100, 4)
