# -*- coding: utf-8 -*-
"""H5 AI 管家创建提醒：解析、缺失追问、多标的、去重与触发文案。"""
from __future__ import annotations

from services.invest import reminders, rules


STOCKS = [
    {"code": "300750", "name": "宁德时代", "price": 246.66, "prev_close": 251.95,
     "pe_ttm": 20.0, "next_report_date": "2026-10-30", "amount": 8e9},
    {"code": "600519", "name": "贵州茅台", "price": 1439.1, "prev_close": 1420.0,
     "pe_ttm": 28.0, "next_report_date": "2026-10-30", "amount": 5e9},
]


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self):
        self.sql: list[str] = []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return FakeCursor([{"ok": 1}])

    def commit(self):
        return None


def _patch(monkeypatch):
    def fake_one(conn, sql, args=()):
        if "FROM stocks" in sql:
            if "name=?" in sql:
                return next((s for s in STOCKS if s["name"] == args[0]), None)
            return next((s for s in STOCKS if s["code"] == args[0]), None)
        if "md_fund_flow_daily" in sql and "LIMIT 1" in sql:
            return {"main_net_inflow": -82_000_000.0}
        return None

    def fake_rows(conn, sql, args=()):
        if "FROM stocks WHERE asset='stock'" in sql:
            text = str(args[0])
            return [{"code": s["code"], "name": s["name"]} for s in STOCKS if s["name"] in text]
        if "FROM stocks WHERE code = ANY" in sql:
            return [{"code": s["code"], "name": s["name"]} for s in STOCKS]
        if "FROM watchlist" in sql:
            return [{"code": "300750"}]
        if "FROM invest_event" in sql:
            return []
        if "md_valuation_daily" in sql:
            return [{"pe_ttm": 10 + i} for i in range(100)]
        if "md_fund_flow_daily" in sql:
            return [{"main_net_inflow": -1e7} for _ in range(5)]
        return []

    monkeypatch.setattr(rules, "one", fake_one)
    monkeypatch.setattr(rules, "rows", fake_rows)
    monkeypatch.setattr(rules, "stock_bars", lambda conn, code, limit=750: [
        {"date": f"2026-09-{i:02d}", "amount": 1e9 + i * 1e7} for i in range(1, 21)
    ])


def test_price_reminder_parses_and_echoes(monkeypatch):
    _patch(monkeypatch)
    out = reminders.parse_query(FakeConn(), "宁德时代跌破 220 提醒我")
    assert out["status"] == "ready"
    rem = out["reminders"][0]
    assert rem["symbol"] == "300750" and rem["type"] == "price"
    assert rem["condition"] == "below" and rem["threshold"] == 220
    assert rem["note"] == "跌破 220 元时提醒"
    assert "宁德时代（300750）" in out["confirm_text"]
    assert "按收盘价" in out["notice"]


def test_missing_threshold_asks_instead_of_guessing(monkeypatch):
    _patch(monkeypatch)
    out = reminders.parse_query(FakeConn(), "宁德时代跌多了提醒我")
    assert out["status"] == "needs_input"
    assert out["missing"] == ["threshold"]
    assert len(out["suggestions"]) >= 2
    assert out["reminders"][0]["threshold"] is None


def test_missing_symbol_uses_session_memory(monkeypatch):
    _patch(monkeypatch)
    out = reminders.parse_query(
        FakeConn(), "跌破 220 提醒我", current={"code": "300750", "name": "宁德时代"}
    )
    assert out["status"] == "ready"
    assert out["reminders"][0]["symbol"] == "300750"


def test_two_symbols_create_two_reminders(monkeypatch):
    _patch(monkeypatch)
    out = reminders.parse_query(FakeConn(), "宁德时代跌破 220，贵州茅台跌 5%，提醒我")
    assert out["status"] == "ready"
    assert [r["symbol"] for r in out["reminders"]] == ["300750", "600519"]
    assert out["reminders"][0]["condition"] == "below"
    assert out["reminders"][1]["condition"] == "lte"
    assert out["reminders"][1]["unit"] == "%"
    assert "这 2 只" in out["confirm_text"]


def test_valuation_and_consecutive_flow(monkeypatch):
    _patch(monkeypatch)
    val = reminders.parse_query(FakeConn(), "宁德时代 PE 分位跌到 20% 以下提醒")
    assert val["reminders"][0]["type"] == "valuation"
    assert val["reminders"][0]["condition"] == "lte"
    assert val["reminders"][0]["threshold"] == 20

    flow = reminders.parse_query(FakeConn(), "宁德时代主力连续 3 天净流出提醒")
    rem = flow["reminders"][0]
    assert rem["type"] == "flow"
    assert rem["condition"] == "consecutive_outflow"
    assert rem["threshold"] == 3 and rem["unit"] == "天"


def test_buy_request_is_blocked_but_converted(monkeypatch):
    _patch(monkeypatch)
    out = reminders.parse_query(FakeConn(), "帮我买入宁德时代 220 元")
    assert out["reminders"][0]["type"] == "price"
    assert "不代下单" in (out["compliance"] or "")


def test_vague_event_becomes_event_plus_heat(monkeypatch):
    _patch(monkeypatch)
    out = reminders.parse_query(FakeConn(), "宁德时代有大事提醒我")
    assert out["status"] == "ready"
    assert {r["type"] for r in out["reminders"]} == {"event", "heat"}


def test_list_reminder_second_line_has_threshold_current_distance(monkeypatch):
    _patch(monkeypatch)

    def fake_rows(conn, sql, args=()):
        if "FROM invest_event" in sql:
            return [{
                "id": 1, "code": "300750", "type": "价格", "condition": "跌破 220 元",
                "condition_op": "below", "threshold": 220, "unit": "元",
                "note": "跌破 220 元时提醒", "status": "active", "source": "ai",
                "created_at": "2026-11-12 10:00:00", "end_date": None,
            }]
        if "FROM stocks WHERE code = ANY" in sql:
            return [{"code": "300750", "name": "宁德时代"}]
        if "FROM watchlist" in sql:
            return [{"code": "300750"}]
        return []

    monkeypatch.setattr(rules, "rows", fake_rows)
    monkeypatch.setattr(rules, "one", lambda conn, sql, args=(): STOCKS[0])
    out = reminders.list_reminders(FakeConn(), 1)
    item = out[0]
    assert item["type_label"] == "价格提醒"
    assert item["source_label"] == "AI 创建"
    assert "跌破 220 元" in item["detail"]
    assert "现价 246.66 元" in item["detail"]
    assert "距触发" in item["detail"]
    assert item["watchlisted"] is True


def test_evaluate_triggers_below_and_writes_log(monkeypatch):
    _patch(monkeypatch)
    conn = FakeConn()

    def fake_rows(conn, sql, args=()):
        if "FROM stocks WHERE code = ANY" in sql:
            return [{"code": "300750", "name": "宁德时代"}]
        if "FROM invest_event" in sql:
            return [{
                "id": 7, "code": "300750", "type": "价格", "condition": "跌破 250 元",
                "condition_op": "below", "threshold": 250, "unit": "元",
                "note": "跌破 250 元时提醒", "status": "active", "source": "ai",
            }]
        return []

    monkeypatch.setattr(rules, "rows", fake_rows)
    monkeypatch.setattr(
        rules, "one",
        lambda conn, sql, args=(): None if "invest_event_log" in sql else STOCKS[0],
    )
    monkeypatch.setattr(rules, "stock_bars", lambda conn, code, limit=750: [
        {"date": "2026-11-11", "amount": 1e9}, {"date": "2026-11-12", "amount": 1.32e9}
    ])
    out = reminders.evaluate(conn, 1)
    assert out["inserted"] == 1
    assert out["triggered"][0]["title"] == "价格提醒 宁德时代 跌破 250 元"
    assert "现价 246.66 元" in out["triggered"][0]["detail"]
    assert "已跌破" in out["triggered"][0]["detail"]
    assert any("INSERT INTO invest_event_log" in sql for sql in conn.sql)
    assert any("UPDATE invest_event SET status='triggered'" in sql for sql in conn.sql)
