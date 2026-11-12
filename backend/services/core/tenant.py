# -*- coding: utf-8 -*-
"""租户上下文值对象：服务层只接受 (user_id, org_id) 的明确组合。

机构/量化查询必须同时按 user_id 与 org_id 过滤；用值对象替代裸 int 参数，
避免 uid/org 顺序传错，也为后续 RLS 的 app.user_id/app.org_id 做准备。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Tenant:
    user_id: int
    org_id: int

    def __post_init__(self) -> None:
        for name, value in (("user_id", self.user_id), ("org_id", self.org_id)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} 必须是正整数")

    @classmethod
    def from_pair(cls, user_id: int, org_id: int) -> "Tenant":
        return cls(int(user_id), int(org_id))

    @classmethod
    def from_ctx(cls, ctx: dict[str, Any]) -> "Tenant":
        org = ctx.get("org") or {}
        org_id = org.get("id") if isinstance(org, dict) else None
        user = ctx.get("user") or {}
        user_id = user.get("id") if isinstance(user, dict) else None
        if user_id is None:
            user_id = ctx.get("user_id")
        if user_id is None or org_id is None:
            raise ValueError("租户上下文缺少 user.id 或 org.id")
        return cls(int(user_id), int(org_id))

    def params(self) -> tuple[int, int]:
        return self.user_id, self.org_id


@dataclass(frozen=True, slots=True)
class OrgScope:
    """只按机构隔离的读取（机构端服务没有个人 user 维度）。"""
    org_id: int

    def __post_init__(self) -> None:
        if isinstance(self.org_id, bool) or not isinstance(self.org_id, int) or self.org_id <= 0:
            raise ValueError("org_id 必须是正整数")


__all__ = ["OrgScope", "Tenant"]
