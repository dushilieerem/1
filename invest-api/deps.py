# -*- coding: utf-8 -*-
"""Invest API 共享依赖（避免 app 与 ai_endpoints 循环导入）。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Iterator

from fastapi import Depends, Header, HTTPException

import auth
import seed as seed_module


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db() -> Iterator[sqlite3.Connection]:
    # 运行时读取 seed.DB_PATH，测试 monkeypatch/reload 后仍指向新库。
    conn = sqlite3.connect(seed_module.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def optional_user(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any] | None:
    return auth.user_from_authorization(authorization)


def require_user(user: dict[str, Any] | None = Depends(optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


__all__ = ["get_db", "now_ts", "optional_user", "require_user"]
