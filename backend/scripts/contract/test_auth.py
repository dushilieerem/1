# -*- coding: utf-8 -*-
"""health + auth + profile/users 契约。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from http_client import assert_error, assert_keys, login, req  # noqa: E402


def test_health() -> None:
    st, data = req("GET", "/api/health")
    assert st == 200, data
    assert_keys(data, "ok", "service", "port")
    assert data["ok"] is True
    assert data["service"] == "svquant"


def test_login_me() -> None:
    st, bad = req("POST", "/api/auth/login", body={"username": "nope", "password": "x"})
    assert_error(st, bad, 401)

    token = login()
    st, me = req("GET", "/api/auth/me", token=token)
    assert st == 200, me
    assert_keys(me, "ok", "user")
    assert me["user"].get("username")

    st, unauth = req("GET", "/api/auth/me")
    assert_error(st, unauth, 401)


def test_users_profile() -> None:
    token = login()
    st, me = req("GET", "/api/auth/me", token=token)
    username = me["user"]["username"]
    st, prof = req("GET", f"/api/users/{username}", token=token)
    assert st == 200, prof
    assert_keys(prof, "ok", "profile")


def main() -> None:
    test_health()
    test_login_me()
    test_users_profile()
    print("contract.auth OK")


if __name__ == "__main__":
    main()
