# -*- coding: utf-8 -*-
"""契约测试共用 HTTP 客户端。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

BASE = (os.environ.get("CONTRACT_BASE") or "http://127.0.0.1:8766").rstrip("/")


def req(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    timeout: float = 60,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw


def login(username: str = "max", password: str = "123456") -> str:
    st, data = req("POST", "/api/auth/login", body={"username": username, "password": password})
    assert st == 200, data
    assert isinstance(data, dict) and data.get("token"), data
    return str(data["token"])


def assert_keys(payload: Any, *keys: str) -> None:
    assert isinstance(payload, dict), payload
    for k in keys:
        assert k in payload, f"missing key {k!r} in {list(payload)[:20]}"


def assert_error(status: int, payload: Any, expect_status: int) -> None:
    assert status == expect_status, (status, payload)
    assert isinstance(payload, dict) and "error" in payload, payload
