# -*- coding: utf-8 -*-
"""机构端权限矩阵与令牌边界（无数据库依赖的单测）。

覆盖需求文档 §2.2 的九工作区权限，以及"个人版令牌不能进机构端"的隔离约束。
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")

from services.auth.auth_store import decode_token, issue_token  # noqa: E402
from services.institution.inst_store import (  # noqa: E402
    ROLE_LABELS,
    WORKSPACES,
    _org_payload,
    issue_inst_token,
    permissions_for,
    user_from_inst_authorization,
    workspaces_for,
)

# 需求文档 §2.2：● 写 / ○ 读 / ◇ 仅摘要 / — 无
EXPECTED = {
    "manager": {
        "overview": "read",
        "ideas": "write",
        "research": "write",
        "debate": "write",
        "portfolio": "read",
        "approvals": "write",
        "execution": "read",
        "monitor": "write",
        "about": "read",
    },
    "partner": {
        "overview": "read",
        "ideas": "read",
        "research": "read",
        "debate": "read",
        "portfolio": "write",
        "approvals": "write",
        "execution": "read",
        "monitor": "write",
        "about": "read",
    },
    "chairman": {
        "overview": "read",
        "ideas": "none",
        "research": "digest",
        "debate": "digest",
        "portfolio": "read",
        "approvals": "write",
        "execution": "digest",
        "monitor": "read",
        "about": "read",
    },
    "risk": {
        "overview": "read",
        "ideas": "none",
        "research": "read",
        "debate": "read",
        "portfolio": "write",
        "approvals": "write",
        "execution": "write",
        "monitor": "write",
        "about": "read",
    },
    "execution": {
        "overview": "read",
        "ideas": "none",
        "research": "none",
        "debate": "none",
        "portfolio": "read",
        "approvals": "read",
        "execution": "write",
        "monitor": "read",
        "about": "read",
    },
    "monitoring": {
        "overview": "read",
        "ideas": "none",
        "research": "digest",
        "debate": "none",
        "portfolio": "write",
        "approvals": "digest",
        "execution": "read",
        "monitor": "write",
        "about": "read",
    },
}


class PermissionMatrixTest(unittest.TestCase):
    def test_six_roles_and_nine_workspaces(self):
        self.assertEqual(set(EXPECTED), set(ROLE_LABELS))
        self.assertEqual(len(WORKSPACES), 9)

    def test_each_role_matches_requirement_matrix(self):
        for role, expected in EXPECTED.items():
            with self.subTest(role=role):
                self.assertEqual(permissions_for(role), expected)

    def test_unknown_role_fails_closed(self):
        perms = permissions_for("intern")  # type: ignore[arg-type]
        self.assertEqual(set(perms), set(WORKSPACES))
        self.assertTrue(all(v == "none" for v in perms.values()))

    def test_hidden_workspaces_are_not_visible(self):
        for role, expected in EXPECTED.items():
            visible = {w["key"] for w in workspaces_for(role) if w["visible"]}
            self.assertEqual(visible, {k for k, v in expected.items() if v != "none"})
            for item in workspaces_for(role):
                self.assertEqual(item["path"], f"/inst/{item['key']}")

    def test_org_payload_uses_org_id_not_member_id(self):
        # 回归：成员 ID 与机构 ID 不同时，会话里的 org.id 必须是机构 ID。
        payload = _org_payload(
            {"id": 99, "org_id": 7, "code": "sunvalley", "name_cn": "旸谷资本", "name_en": ""}
        )
        self.assertEqual(payload["id"], 7)


class TokenBoundaryTest(unittest.TestCase):
    def test_inst_token_carries_scope_and_org(self):
        token = issue_inst_token(
            {"id": 7, "username": "inst_manager", "role": "user"},
            {"org_id": 3, "role": "manager"},
        )
        payload = decode_token(token)
        self.assertEqual(payload["scope"], "inst")
        self.assertEqual(payload["org_id"], 3)
        self.assertEqual(payload["inst_role"], "manager")
        self.assertEqual(payload["sub"], "7")

    def test_personal_token_is_rejected_by_inst_session(self):
        token = issue_token({"id": 7, "username": "inst_manager", "role": "user"})
        self.assertIsNone(user_from_inst_authorization(f"Bearer {token}"))

    def test_inst_token_cannot_override_identity_claims(self):
        token = issue_inst_token(
            {"id": 7, "username": "inst_manager", "role": "user"},
            {"org_id": 3, "role": "manager"},
        )
        payload = decode_token(token)
        self.assertEqual(payload["role"], "user")
        self.assertEqual(payload["sub"], "7")

    def test_missing_header_returns_none(self):
        self.assertIsNone(user_from_inst_authorization(None))
        self.assertIsNone(user_from_inst_authorization("Bearer not-a-jwt"))


if __name__ == "__main__":
    unittest.main()
