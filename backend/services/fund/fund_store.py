# -*- coding: utf-8 -*-
"""基金会计、净值、申赎与报送（X01–X06，默认口径）。

默认假设（未接基金合同/监管口径前的基线，可在产品配置中覆盖）：
- 管理费 1.5%/年、托管费 0.25%/年，按实际天数/365 从现金计提；
- 申购费 1.0%，赎回费 0.5%；
- 初始净值 1.0000；申赎按 T 日净值确认，T+1 份额/资金可用；
- 报送按“产品代码/日期/资产/负债/份额/净值/费用”基线字段导出，
  附校验与 sha256，供人工复核；不替代监管模板。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from services.core.db import get_conn
from services.marketdata import store as md


def ensure_fund_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_products (
              id                BIGSERIAL PRIMARY KEY,
              owner_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              code              TEXT NOT NULL UNIQUE,
              name              TEXT NOT NULL,
              currency          TEXT NOT NULL DEFAULT 'CNY',
              mgmt_fee          DOUBLE PRECISION NOT NULL DEFAULT 0.015,
              custody_fee       DOUBLE PRECISION NOT NULL DEFAULT 0.0025,
              subscription_fee  DOUBLE PRECISION NOT NULL DEFAULT 0.01,
              redemption_fee    DOUBLE PRECISION NOT NULL DEFAULT 0.005,
              cash              DOUBLE PRECISION NOT NULL DEFAULT 0,
              shares_outstanding DOUBLE PRECISION NOT NULL DEFAULT 0,
              nav_per_share     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
              nav_date          DATE,
              status            TEXT NOT NULL DEFAULT 'active',
              created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_positions (
              id          BIGSERIAL PRIMARY KEY,
              product_id  BIGINT NOT NULL REFERENCES fund_products(id) ON DELETE CASCADE,
              symbol      TEXT NOT NULL,
              qty         DOUBLE PRECISION NOT NULL,
              cost        DOUBLE PRECISION NOT NULL,
              UNIQUE (product_id, symbol)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_nav (
              id            BIGSERIAL PRIMARY KEY,
              product_id    BIGINT NOT NULL REFERENCES fund_products(id) ON DELETE CASCADE,
              date          DATE NOT NULL,
              nav           DOUBLE PRECISION NOT NULL,
              nav_per_share DOUBLE PRECISION NOT NULL,
              shares        DOUBLE PRECISION NOT NULL,
              cash          DOUBLE PRECISION NOT NULL,
              market_value  DOUBLE PRECISION NOT NULL,
              fees_accrued  DOUBLE PRECISION NOT NULL DEFAULT 0,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (product_id, date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_orders (
              id             BIGSERIAL PRIMARY KEY,
              product_id     BIGINT NOT NULL REFERENCES fund_products(id) ON DELETE CASCADE,
              user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              kind           TEXT NOT NULL,
              amount         DOUBLE PRECISION NOT NULL,
              shares         DOUBLE PRECISION NOT NULL,
              fee            DOUBLE PRECISION NOT NULL,
              nav_per_share  DOUBLE PRECISION NOT NULL,
              status         TEXT NOT NULL DEFAULT 'confirmed',
              trade_date     DATE NOT NULL,
              confirm_date   DATE NOT NULL,
              created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT fund_order_kind_chk CHECK (kind IN ('subscribe','redeem'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_journal (
              id          BIGSERIAL PRIMARY KEY,
              product_id  BIGINT NOT NULL REFERENCES fund_products(id) ON DELETE CASCADE,
              date        DATE NOT NULL,
              type        TEXT NOT NULL,
              amount      DOUBLE PRECISION NOT NULL,
              ref         TEXT,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_holdings (
              product_id  BIGINT NOT NULL REFERENCES fund_products(id) ON DELETE CASCADE,
              user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              shares      DOUBLE PRECISION NOT NULL DEFAULT 0,
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (product_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_reports (
              id          BIGSERIAL PRIMARY KEY,
              product_id  BIGINT NOT NULL REFERENCES fund_products(id) ON DELETE CASCADE,
              date        DATE NOT NULL,
              payload     JSONB NOT NULL,
              sha256      TEXT NOT NULL,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (product_id, date)
            )
            """
        )


def _row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at", "nav_date", "trade_date", "confirm_date", "date"):
        if hasattr(out.get(key), "isoformat"):
            out[key] = out[key].isoformat()
    return out


def _product(conn, product_id: int, owner_id: int | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM fund_products WHERE id=%s"
    params: list[Any] = [product_id]
    if owner_id is not None:
        sql += " AND owner_id=%s"
        params.append(owner_id)
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise KeyError(product_id)
    return _row(dict(row))


def create_product(
    owner_id: int,
    *,
    code: str,
    name: str,
    mgmt_fee: float = 0.015,
    custody_fee: float = 0.0025,
    subscription_fee: float = 0.01,
    redemption_fee: float = 0.005,
) -> dict[str, Any]:
    ensure_fund_schema()
    if not (code or "").strip() or not (name or "").strip():
        raise ValueError("产品代码与名称必填")
    for value, label in (
        (mgmt_fee, "管理费"),
        (custody_fee, "托管费"),
        (subscription_fee, "申购费"),
        (redemption_fee, "赎回费"),
    ):
        if not (0 <= float(value) < 1):
            raise ValueError(f"{label} 费率必须在 [0,1)")
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO fund_products
              (owner_id, code, name, mgmt_fee, custody_fee, subscription_fee, redemption_fee)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (int(owner_id), code.strip(), name.strip(), mgmt_fee, custody_fee, subscription_fee, redemption_fee),
        ).fetchone()
    return _row(dict(row))


def list_products(owner_id: int) -> list[dict[str, Any]]:
    ensure_fund_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fund_products WHERE owner_id=%s ORDER BY created_at DESC", (int(owner_id),)
        ).fetchall()
    return [_row(dict(r)) for r in rows]


def get_product(owner_id: int, product_id: int) -> dict[str, Any]:
    ensure_fund_schema()
    with get_conn() as conn:
        product = _product(conn, product_id, owner_id)
        positions = conn.execute(
            "SELECT * FROM fund_positions WHERE product_id=%s ORDER BY symbol", (product_id,)
        ).fetchall()
        product["positions"] = [_row(dict(r)) for r in positions]
    return product


def add_capital(owner_id: int, product_id: int, amount: float, *, note: str = "capital") -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("金额必须大于 0")
    ensure_fund_schema()
    with get_conn() as conn:
        _product(conn, product_id, owner_id)
        conn.execute(
            "UPDATE fund_products SET cash=cash+%s, updated_at=NOW() WHERE id=%s", (amount, product_id)
        )
        conn.execute(
            "INSERT INTO fund_journal (product_id, date, type, amount, ref) VALUES (%s,CURRENT_DATE,'capital',%s,%s)",
            (product_id, amount, note),
        )
        return _product(conn, product_id, owner_id)


def add_position(owner_id: int, product_id: int, *, symbol: str, qty: float, cost: float) -> dict[str, Any]:
    if qty <= 0 or cost < 0:
        raise ValueError("数量必须大于 0，成本不能为负")
    ensure_fund_schema()
    with get_conn() as conn:
        _product(conn, product_id, owner_id)
        conn.execute(
            """
            INSERT INTO fund_positions (product_id, symbol, qty, cost) VALUES (%s,%s,%s,%s)
            ON CONFLICT (product_id, symbol) DO UPDATE SET qty=EXCLUDED.qty, cost=EXCLUDED.cost
            """,
            (product_id, symbol.strip().upper(), qty, cost),
        )
        return _product(conn, product_id, owner_id)


def _market_value(conn, product_id: int, as_of: str) -> tuple[float, list[dict[str, Any]]]:
    rows = conn.execute("SELECT * FROM fund_positions WHERE product_id=%s", (product_id,)).fetchall()
    total = 0.0
    detail: list[dict[str, Any]] = []
    for row in rows:
        pos = dict(row)
        bar = md.latest_bar(pos["symbol"], adjust="none") or {}
        price = bar.get("close")
        value = float(pos["qty"]) * float(price if price is not None else pos["cost"])
        total += value
        detail.append({"symbol": pos["symbol"], "qty": float(pos["qty"]), "price": price, "market_value": value})
    return total, detail


def accrue_fees(conn, product: dict[str, Any], as_of: date) -> float:
    last = product.get("nav_date")
    if not last:
        return 0.0
    if isinstance(last, str):
        last = date.fromisoformat(last[:10])
    days = max(0, (as_of - last).days)
    if days <= 0:
        return 0.0
    annual = float(product["mgmt_fee"]) + float(product["custody_fee"])
    base = float(product["cash"]) + 0.0
    fee = base * annual * days / 365.0
    if fee > 0:
        conn.execute(
            "UPDATE fund_products SET cash=cash-%s WHERE id=%s", (fee, product["id"])
        )
        conn.execute(
            "INSERT INTO fund_journal (product_id, date, type, amount, ref) "
            "VALUES (%s,%s,'fee_accrual',%s,%s)",
            (product["id"], as_of.isoformat(), fee, f"{days}d"),
        )
    return fee


def compute_nav(owner_id: int, product_id: int, *, as_of: str | None = None) -> dict[str, Any]:
    ensure_fund_schema()
    day = date.fromisoformat(as_of) if as_of else date.today()
    with get_conn() as conn:
        product = _product(conn, product_id, owner_id)
        fee = accrue_fees(conn, product, day)
        product = _product(conn, product_id, owner_id)
        market_value, detail = _market_value(conn, product_id, day.isoformat())
        cash = float(product["cash"])
        shares = float(product["shares_outstanding"])
        nav = cash + market_value
        per_share = nav / shares if shares > 0 else 1.0
        conn.execute(
            """
            INSERT INTO fund_nav (product_id, date, nav, nav_per_share, shares, cash, market_value, fees_accrued)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_id, date) DO UPDATE
              SET nav=EXCLUDED.nav, nav_per_share=EXCLUDED.nav_per_share, shares=EXCLUDED.shares,
                  cash=EXCLUDED.cash, market_value=EXCLUDED.market_value,
                  fees_accrued=fund_nav.fees_accrued + EXCLUDED.fees_accrued
            """,
            (product_id, day.isoformat(), nav, per_share, shares, cash, market_value, fee),
        )
        conn.execute(
            "UPDATE fund_products SET nav_per_share=%s, nav_date=%s, updated_at=NOW() WHERE id=%s",
            (per_share, day.isoformat(), product_id),
        )
        row = conn.execute(
            "SELECT * FROM fund_nav WHERE product_id=%s AND date=%s", (product_id, day.isoformat())
        ).fetchone()
    out = _row(dict(row))
    out["positions"] = detail
    return out


def subscribe(product_id: int, user_id: int, *, amount: float, as_of: str | None = None) -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("申购金额必须大于 0")
    ensure_fund_schema()
    day = date.fromisoformat(as_of) if as_of else date.today()
    with get_conn() as conn:
        product = _product(conn, product_id)
        per_share = float(product["nav_per_share"] or 1.0)
        fee = float(product["subscription_fee"]) * amount
        net = amount - fee
        shares = net / per_share if per_share > 0 else 0.0
        confirm = day + timedelta(days=1)
        row = conn.execute(
            """
            INSERT INTO fund_orders
              (product_id, user_id, kind, amount, shares, fee, nav_per_share, status, trade_date, confirm_date)
            VALUES (%s,%s,'subscribe',%s,%s,%s,%s,'confirmed',%s,%s) RETURNING *
            """,
            (product_id, int(user_id), amount, shares, fee, per_share, day.isoformat(), confirm.isoformat()),
        ).fetchone()
        conn.execute(
            "UPDATE fund_products SET cash=cash+%s, shares_outstanding=shares_outstanding+%s, "
            "updated_at=NOW() WHERE id=%s",
            (amount, shares, product_id),
        )
        conn.execute(
            "INSERT INTO fund_journal (product_id, date, type, amount, ref) VALUES (%s,%s,'subscribe',%s,%s)",
            (product_id, day.isoformat(), amount, f"order:{row['id']}"),
        )
        conn.execute(
            "INSERT INTO fund_journal (product_id, date, type, amount, ref) VALUES (%s,%s,'subscribe_fee',%s,%s)",
            (product_id, day.isoformat(), fee, f"order:{row['id']}"),
        )
        conn.execute(
            """
            INSERT INTO fund_holdings (product_id, user_id, shares) VALUES (%s,%s,%s)
            ON CONFLICT (product_id, user_id) DO UPDATE
              SET shares=fund_holdings.shares+EXCLUDED.shares, updated_at=NOW()
            """,
            (product_id, int(user_id), shares),
        )
    return _row(dict(row))


def redeem(product_id: int, user_id: int, *, shares: float, as_of: str | None = None) -> dict[str, Any]:
    if shares <= 0:
        raise ValueError("赎回份额必须大于 0")
    ensure_fund_schema()
    day = date.fromisoformat(as_of) if as_of else date.today()
    with get_conn() as conn:
        product = _product(conn, product_id)
        holding = conn.execute(
            "SELECT shares FROM fund_holdings WHERE product_id=%s AND user_id=%s",
            (product_id, int(user_id)),
        ).fetchone()
        owned = float(holding["shares"]) if holding else 0.0
        if shares > owned:
            raise ValueError("赎回份额超过持有人可用份额")
        if shares > float(product["shares_outstanding"]):
            raise ValueError("赎回份额超过总份额")
        per_share = float(product["nav_per_share"] or 1.0)
        gross = shares * per_share
        fee = float(product["redemption_fee"]) * gross
        amount = gross - fee
        confirm = day + timedelta(days=1)
        row = conn.execute(
            """
            INSERT INTO fund_orders
              (product_id, user_id, kind, amount, shares, fee, nav_per_share, status, trade_date, confirm_date)
            VALUES (%s,%s,'redeem',%s,%s,%s,%s,'confirmed',%s,%s) RETURNING *
            """,
            (product_id, int(user_id), amount, shares, fee, per_share, day.isoformat(), confirm.isoformat()),
        ).fetchone()
        if amount > float(product["cash"]):
            raise ValueError("组合现金不足，无法赎回")
        conn.execute(
            "UPDATE fund_products SET cash=cash-%s, shares_outstanding=shares_outstanding-%s, "
            "updated_at=NOW() WHERE id=%s",
            (amount, shares, product_id),
        )
        conn.execute(
            "INSERT INTO fund_journal (product_id, date, type, amount, ref) VALUES (%s,%s,'redeem',%s,%s)",
            (product_id, day.isoformat(), amount, f"order:{row['id']}"),
        )
        conn.execute(
            "INSERT INTO fund_journal (product_id, date, type, amount, ref) VALUES (%s,%s,'redeem_fee',%s,%s)",
            (product_id, day.isoformat(), fee, f"order:{row['id']}"),
        )
        conn.execute(
            "UPDATE fund_holdings SET shares=shares-%s, updated_at=NOW() WHERE product_id=%s AND user_id=%s",
            (shares, product_id, int(user_id)),
        )
    return _row(dict(row))


def list_orders(product_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    ensure_fund_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fund_orders WHERE product_id=%s ORDER BY created_at DESC LIMIT %s",
            (product_id, max(1, min(limit, 500))),
        ).fetchall()
    return [_row(dict(r)) for r in rows]


def build_report(owner_id: int, product_id: int, *, as_of: str | None = None) -> dict[str, Any]:
    """X05/X06：报送基线包（JSON + 校验 + sha256）。"""
    ensure_fund_schema()
    day = date.fromisoformat(as_of) if as_of else date.today()
    nav = compute_nav(owner_id, product_id, as_of=day.isoformat())
    with get_conn() as conn:
        product = _product(conn, product_id, owner_id)
        orders = conn.execute(
            "SELECT * FROM fund_orders WHERE product_id=%s ORDER BY id", (product_id,)
        ).fetchall()
        journal = conn.execute(
            "SELECT * FROM fund_journal WHERE product_id=%s ORDER BY id", (product_id,)
        ).fetchall()
        payload = {
            "report_version": "cn-baseline-v1",
            "product": {
                "code": product["code"],
                "name": product["name"],
                "currency": product["currency"],
                "fees": {
                    "management": product["mgmt_fee"],
                    "custody": product["custody_fee"],
                    "subscription": product["subscription_fee"],
                    "redemption": product["redemption_fee"],
                },
            },
            "as_of": day.isoformat(),
            "nav": {
                "nav": nav["nav"],
                "nav_per_share": nav["nav_per_share"],
                "shares": nav["shares"],
                "cash": nav["cash"],
                "market_value": nav["market_value"],
                "fees_accrued": nav["fees_accrued"],
            },
            "positions": nav["positions"],
            "orders": [_row(dict(r)) for r in orders],
            "journal": [_row(dict(r)) for r in journal],
            "checks": [],
        }
        checks = payload["checks"]
        checks.append({"key": "cash_non_negative", "ok": float(nav["cash"]) >= 0})
        checks.append({"key": "shares_non_negative", "ok": float(nav["shares"]) >= 0})
        checks.append(
            {
                "key": "nav_identity",
                "ok": abs(float(nav["nav"]) - (float(nav["cash"]) + float(nav["market_value"]))) < 1e-6,
            }
        )
        payload["checks"] = checks
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO fund_reports (product_id, date, payload, sha256) VALUES (%s,%s,%s::jsonb,%s)
            ON CONFLICT (product_id, date) DO UPDATE SET payload=EXCLUDED.payload, sha256=EXCLUDED.sha256
            """,
            (product_id, day.isoformat(), json.dumps(payload, ensure_ascii=False, default=str), digest),
        )
    return {"sha256": digest, "payload": payload}
