# -*- coding: utf-8 -*-
"""投资管理合并：K 线周期、持仓自动扫描、单票论点台账重新生成。"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")
os.environ.setdefault("RE_CATALOG_SYNC_ENABLED", "0")
os.environ.setdefault("SVQUANT_PANEL_DAILY_ENABLED", "0")
os.environ.setdefault("SVQUANT_PAPER_TRADING_ENABLED", "0")
os.environ.setdefault("NEWS_INGEST_INTERVAL_SEC", "0")
os.environ.setdefault("RE_CATALOG_WARM_ENABLED", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg.types.json import Jsonb  # noqa: E402

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()


@pytest.fixture(scope="module")
def fixture():
    tag = uuid.uuid4().hex[:8]
    symbol = f"HLD{tag[:4].upper()}.SH"
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"hold-{tag}", f"持仓管理测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        user = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING *",
            (f"inst_hold_{tag}",),
        ).fetchone()
        member = conn.execute(
            "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,'manager') RETURNING *",
            (org_id, int(user["id"])),
        ).fetchone()
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, industry, ref_price) "
            "VALUES (%s,%s,'持仓管理测试公司','CN','测试行业',100) RETURNING id",
            (org_id, symbol),
        ).fetchone()
        company_id = int(company["id"])
        portfolio = conn.execute(
            "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
            "VALUES (%s,'MAIN','持仓测试组合','CNY',1000000,500000) RETURNING id",
            (org_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_position_snapshot (portfolio_id, symbol, qty, cost, market_value, weight, as_of) "
            "VALUES (%s,%s,1000,100,80000,0.08,%s)",
            (int(portfolio["id"]), symbol, date.today()),
        )
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no) VALUES (%s,%s,%s) RETURNING id",
            (org_id, company_id, f"HLD-{tag}"),
        ).fetchone()
        version = conn.execute(
            "INSERT INTO inst_research_version "
            "(case_id, version_no, status, six_dim, valuation, conclusion, evidence_ids) "
            "VALUES (%s,1,'approved',%s,NULL,'论点测试结论','[]'::jsonb) RETURNING id",
            (
                int(case["id"]),
                Jsonb([{"key": "industry", "summary": "行业景气向上"}, {"key": "financial", "summary": "现金流健康"}]),
            ),
        ).fetchone()
        proposal = conn.execute(
            "INSERT INTO inst_proposal (org_id, case_id, company_id, direction, target_weight, current_version_no, status, created_by) "
            "VALUES (%s,%s,%s,'buy',0.05,1,'executed',%s) RETURNING id",
            (org_id, int(case["id"]), company_id, int(member["id"])),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_proposal_version (proposal_id, version_no, snapshot, status, created_by) "
            "VALUES (%s,1,%s,'authorized',%s)",
            (
                int(proposal["id"]),
                Jsonb(
                    {
                        "investment_opinion": "关键假设成立才持有",
                        "monitoring": ["季度财报后复核"],
                        "research_version_id": int(version["id"]),
                    }
                ),
                int(member["id"]),
            ),
        )
        conn.execute(
            "INSERT INTO inst_thesis_ledger "
            "(org_id, company_id, symbol, thesis, key_assumptions, kpis, falsifiers, review_due, created_by) "
            "VALUES (%s,%s,%s,'旧论点','[]'::jsonb,'[]'::jsonb,'[]'::jsonb,%s,%s)",
            (org_id, company_id, symbol, date.today() - timedelta(days=3), int(member["id"])),
        )
        for day, close in ((date(2026, 1, 5), 100), (date(2026, 1, 6), 90), (date(2026, 1, 12), 80)):
            conn.execute(
                "INSERT INTO md_daily_bar (symbol, trade_date, open, high, low, close, volume, adjust) "
                "VALUES (%s,%s,%s,%s,%s,%s,1000,'none')",
                (symbol, day, close, close + 2, close - 2, close),
            )
    yield {
        "org_id": org_id,
        "company_id": company_id,
        "member_id": int(member["id"]),
        "symbol": symbol,
        "proposal_id": int(proposal["id"]),
        "user_id": int(user["id"]),
    }
    with get_conn() as conn:
        conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='inst_audit_event_worm')"
            " THEN ALTER TABLE inst_audit_event DISABLE TRIGGER inst_audit_event_worm; END IF; END $$"
        )
        conn.execute("DELETE FROM md_daily_bar WHERE symbol=%s", (symbol,))
        conn.execute("DELETE FROM inst_orgs WHERE id=%s", (org_id,))
        conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='inst_audit_event_worm')"
            " THEN ALTER TABLE inst_audit_event ENABLE TRIGGER inst_audit_event_worm; END IF; END $$"
        )
        conn.execute("DELETE FROM users WHERE id=%s", (int(user["id"]),))


def test_company_bars_periods(fixture) -> None:
    day = svc.company_bars(fixture["org_id"], fixture["company_id"], period="day")
    assert day["available"] is True
    assert len(day["items"]) == 3
    week = svc.company_bars(fixture["org_id"], fixture["company_id"], period="week")
    assert len(week["items"]) == 2
    assert week["items"][0]["open"] == 100
    assert week["items"][0]["close"] == 90
    month = svc.company_bars(fixture["org_id"], fixture["company_id"], period="month")
    assert len(month["items"]) == 1
    assert month["items"][0]["high"] == 102
    minute = svc.company_bars(fixture["org_id"], fixture["company_id"], period="5min")
    assert minute["available"] is False
    assert minute["items"] == []
    assert "分钟线" in minute["note"]


def test_scan_holdings_creates_events_once(fixture) -> None:
    first = svc.scan_holdings(fixture["org_id"], actor_member_id=fixture["member_id"])
    kinds = {e["type"] for e in first["events"]}
    assert kinds == {"thesis", "price"}, first
    again = svc.scan_holdings(fixture["org_id"], actor_member_id=fixture["member_id"])
    assert again["created"] == 0


def test_refresh_thesis_from_latest_proposal(fixture) -> None:
    out = svc.refresh_thesis(
        fixture["org_id"], fixture["company_id"], actor_member_id=fixture["member_id"]
    )
    assert out["thesis"] == "关键假设成立才持有"
    assert out["falsifiers"] == ["季度财报后复核"]
    assert out["key_assumptions"] == ["行业景气向上", "现金流健康"]
    assert out["proposal_id"] == fixture["proposal_id"]
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM inst_thesis_ledger WHERE org_id=%s AND company_id=%s",
            (fixture["org_id"], fixture["company_id"]),
        ).fetchone()["n"]
    assert int(count) == 2
