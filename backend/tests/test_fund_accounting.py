# -*- coding: utf-8 -*-
"""X01–X06：基金会计、净值、申赎与报送基线。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.fund import fund_store as fund  # noqa: E402
from services.marketdata import store as md  # noqa: E402

ensure_schema()


def _user() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id",
            (f"fund_{uuid.uuid4().hex[:8]}",),
        ).fetchone()
    return int(row["id"])


def _product(owner_id: int) -> dict:
    return fund.create_product(
        owner_id,
        code=f"F{uuid.uuid4().hex[:6]}",
        name="测试私募",
        mgmt_fee=0.015,
        custody_fee=0.0025,
        subscription_fee=0.01,
        redemption_fee=0.005,
    )


def test_nav_subscribe_redeem_and_report(monkeypatch) -> None:
    monkeypatch.setattr(md, "latest_bar", lambda symbol, adjust="none": {"close": 12.0})
    owner = _user()
    investor = _user()
    try:
        product = _product(owner)
        pid = int(product["id"])
        fund.add_capital(owner, pid, 1_000_000)
        fund.add_position(owner, pid, symbol="600519.SH", qty=1000, cost=10)

        nav = fund.compute_nav(owner, pid, as_of="2026-10-30")
        assert nav["market_value"] == pytest.approx(12_000)
        assert nav["nav"] == pytest.approx(1_012_000)
        assert nav["nav_per_share"] == pytest.approx(1.0)

        order = fund.subscribe(pid, investor, amount=101_000, as_of="2026-10-30")
        assert order["fee"] == pytest.approx(1010)
        assert order["shares"] == pytest.approx(99_990)
        assert order["confirm_date"] == "2026-10-31"

        nav2 = fund.compute_nav(owner, pid, as_of="2026-11-29")
        assert nav2["fees_accrued"] > 0
        assert nav2["nav_per_share"] > 0

        redeemed = fund.redeem(pid, investor, shares=10_000, as_of="2026-11-29")
        assert redeemed["shares"] == pytest.approx(10_000)
        assert redeemed["fee"] == pytest.approx(redeemed["amount"] / 0.995 * 0.005, rel=1e-6)

        report = fund.build_report(owner, pid, as_of="2026-11-29")
        assert len(report["sha256"]) == 64
        assert all(c["ok"] for c in report["payload"]["checks"])
        assert report["payload"]["product"]["fees"]["management"] == 0.015
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM fund_products WHERE owner_id=%s", (owner,))
            conn.execute("DELETE FROM users WHERE id IN (%s,%s)", (owner, investor))


def test_validation(monkeypatch) -> None:
    monkeypatch.setattr(md, "latest_bar", lambda symbol, adjust="none": {"close": 10.0})
    owner = _user()
    try:
        product = _product(owner)
        pid = int(product["id"])
        with pytest.raises(ValueError):
            fund.create_product(owner, code="", name="x")
        with pytest.raises(ValueError):
            fund.create_product(owner, code="X1", name="x", mgmt_fee=1.5)
        with pytest.raises(ValueError):
            fund.subscribe(pid, owner, amount=0)
        with pytest.raises(ValueError):
            fund.redeem(pid, owner, shares=1)
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM fund_products WHERE owner_id=%s", (owner,))
            conn.execute("DELETE FROM users WHERE id=%s", (owner,))
