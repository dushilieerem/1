# -*- coding: utf-8 -*-
"""兼容入口：自定义因子 CRUD 转发到 user_factor_store（须带 user_id）。"""
from __future__ import annotations

from typing import Any

from services import user_factor_store as ufs


def add_custom_factor(*, user_id: int, name: str, body: str, description: str = "") -> dict:
    return ufs.add_user_factor(user_id, name=name, body=body, description=description)


def update_custom_factor(*, user_id: int, name: str, body: str, description: str = "") -> dict:
    return ufs.update_user_factor(user_id, name=name, body=body, description=description)


def delete_custom_factor(*, user_id: int, name: str) -> dict:
    return ufs.delete_user_factor(user_id, name)


def rebuild_custom_lib() -> None:
    ufs.rebuild_custom_lib()


def migrate_legacy() -> dict[str, Any]:
    return ufs.migrate_legacy_custom_to_admin()
