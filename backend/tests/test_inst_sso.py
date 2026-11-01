# -*- coding: utf-8 -*-
"""S01/S02：机构 SSO 与多机构切换。"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from services.auth.auth_store import decode_token, ensure_schema, issue_token  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution.inst_store import ensure_inst_schema  # noqa: E402

ensure_schema()
ensure_inst_schema()


def _setup():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        user = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id, username, role, status",
            (f"sso_{tag}",),
        ).fetchone()
        orgs = []
        for suffix in ("a", "b"):
            org = conn.execute(
                "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
                (f"sso-{tag}-{suffix}", f"机构{suffix} {tag}"),
            ).fetchone()
            conn.execute(
                "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,'manager')",
                (org["id"], user["id"]),
            )
            orgs.append(int(org["id"]))
    public = {
        "id": int(user["id"]),
        "username": str(user["username"]),
        "role": str(user["role"]),
        "status": str(user["status"]),
    }
    return public, orgs


def test_sso_and_multi_org_switch() -> None:
    user, orgs = _setup()
    token = issue_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    try:
        listed = client.get("/api/inst/auth/orgs", headers=headers)
        assert listed.status_code == 200, listed.text
        assert {o["org_id"] for o in listed.json()["orgs"]} == set(orgs)

        ambiguous = client.post("/api/inst/auth/sso", json={}, headers=headers)
        assert ambiguous.status_code == 409
        assert len(ambiguous.json()["orgs"]) == 2

        first = client.post("/api/inst/auth/sso", json={"org_id": orgs[0]}, headers=headers)
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["membership"]["org_id"] == orgs[0]
        decoded = decode_token(payload["token"])
        assert decoded["scope"] == "inst" and int(decoded["org_id"]) == orgs[0]

        switched = client.post("/api/inst/auth/switch", json={"org_id": orgs[1]}, headers=headers)
        assert switched.status_code == 200, switched.text
        assert int(decode_token(switched.json()["token"])["org_id"]) == orgs[1]

        denied = client.post("/api/inst/auth/switch", json={"org_id": 10**9}, headers=headers)
        assert denied.status_code == 403
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM inst_orgs WHERE id = ANY(%s)", (orgs,))
            conn.execute("DELETE FROM users WHERE id=%s", (user["id"],))
