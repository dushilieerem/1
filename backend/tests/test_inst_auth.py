# -*- coding: utf-8 -*-
"""机构端权限矩阵与令牌边界（无数据库依赖的单测）。

覆盖需求文档 §2.2 的九工作区权限，以及"个人版令牌不能进机构端"的隔离约束。
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")

from app.deps import require_quant_researcher, require_quant_reviewer  # noqa: E402
from services.auth.auth_store import decode_token, issue_token  # noqa: E402
from services.institution.inst_store import (  # noqa: E402
    QUANT_ROLES,
    ROLE_LABELS,
    WORKSPACES,
    _org_payload,
    issue_inst_token,
    issue_quant_token,
    login_inst,
    login_quant,
    permissions_for,
    user_from_inst_authorization,
    user_from_quant_authorization,
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
    "quant_researcher": {
        "overview": "none",
        "ideas": "none",
        "research": "none",
        "debate": "none",
        "portfolio": "none",
        "approvals": "none",
        "execution": "none",
        "monitor": "none",
        "about": "none",
    },
    "quant_reviewer": {
        "overview": "none",
        "ideas": "none",
        "research": "none",
        "debate": "none",
        "portfolio": "none",
        "approvals": "none",
        "execution": "none",
        "monitor": "none",
        "about": "none",
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


class QuantSessionTest(unittest.TestCase):
    def test_quant_role_has_no_subjective_workspace_access(self):
        self.assertIn("quant_researcher", QUANT_ROLES)
        self.assertIn("quant_reviewer", QUANT_ROLES)
        self.assertEqual(set(permissions_for("quant_researcher").values()), {"none"})
        self.assertEqual(set(permissions_for("quant_reviewer").values()), {"none"})
        self.assertEqual(
            [w for w in workspaces_for("quant_researcher") if w["visible"]], []
        )
        self.assertEqual(
            [w for w in workspaces_for("quant_reviewer") if w["visible"]], []
        )

    def test_quant_token_has_product_and_org(self):
        token = issue_quant_token(
            {"id": 7, "username": "cx_quant", "role": "user"},
            {"org_id": 9, "role": "quant_researcher"},
        )
        payload = decode_token(token)
        self.assertEqual(payload["scope"], "inst")
        self.assertEqual(payload["product"], "quant")
        self.assertEqual(payload["org_id"], 9)
        self.assertEqual(payload["inst_role"], "quant_researcher")

    def test_subjective_inst_token_is_rejected_by_quant_session(self):
        token = issue_inst_token(
            {"id": 7, "username": "inst_manager", "role": "user"},
            {"org_id": 3, "role": "manager"},
        )
        self.assertIsNone(user_from_quant_authorization(f"Bearer {token}"))

    def test_quant_token_requires_quant_role(self):
        with self.assertRaises(PermissionError):
            issue_quant_token(
                {"id": 7, "username": "inst_manager", "role": "user"},
                {"org_id": 3, "role": "manager"},
            )

    def test_login_quant_rejects_non_quant_member(self):
        from unittest.mock import patch

        with patch(
            "services.institution.inst_store.authenticate_user",
            return_value={"id": 7, "username": "cx_quant", "role": "user"},
        ), patch(
            "services.institution.inst_store.get_membership",
            return_value={"org_id": 9, "role": "manager"},
        ):
            with self.assertRaises(PermissionError):
                login_quant(username="cx_quant", password="x")

    def test_reviewer_and_researcher_capabilities_are_separate(self):
        from fastapi import HTTPException

        researcher = {"role": "quant_researcher", "can_write": True, "can_review": False}
        reviewer = {"role": "quant_reviewer", "can_write": False, "can_review": True}
        self.assertIs(require_quant_researcher(researcher), researcher)
        self.assertIs(require_quant_reviewer(reviewer), reviewer)
        with self.assertRaises(HTTPException):
            require_quant_researcher(reviewer)
        with self.assertRaises(HTTPException):
            require_quant_reviewer(researcher)

    def test_reviewer_token_has_review_product(self):
        token = issue_quant_token(
            {"id": 8, "username": "cx_quant_reviewer", "role": "user"},
            {"org_id": 9, "role": "quant_reviewer"},
        )
        payload = decode_token(token)
        self.assertEqual(payload["product"], "quant")
        self.assertEqual(payload["inst_role"], "quant_reviewer")

    def test_subjective_login_rejects_quant_role(self):
        from unittest.mock import patch

        with patch(
            "services.institution.inst_store.authenticate_user",
            return_value={"id": 7, "username": "cx_quant", "role": "user"},
        ), patch(
            "services.institution.inst_store.get_membership",
            return_value={"org_id": 9, "role": "quant_researcher"},
        ):
            with self.assertRaises(PermissionError):
                login_inst(username="cx_quant", password="x")


if __name__ == "__main__":
    unittest.main()
