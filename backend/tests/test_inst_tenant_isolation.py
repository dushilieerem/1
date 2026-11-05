# -*- coding: utf-8 -*-
"""机构租户隔离回归：跨 org 读取研究案必须为空，列表不得混入其他 org。"""
from __future__ import annotations

import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_service import get_case, list_cases  # noqa: E402
from services.institution.inst_store import ensure_inst_schema  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()


def test_case_is_not_visible_from_another_org() -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org1 = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"tenant-a-{tag}", f"租户 A {tag}"),
        ).fetchone()
        org2 = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"tenant-b-{tag}", f"租户 B {tag}"),
        ).fetchone()
        company1 = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, ref_price) "
            "VALUES (%s,%s,'租户 A 公司','CN',10) RETURNING id",
            (int(org1["id"]), f"A{tag}.SH"),
        ).fetchone()
        company2 = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, ref_price) "
            "VALUES (%s,%s,'租户 B 公司','CN',10) RETURNING id",
            (int(org2["id"]), f"B{tag}.SH"),
        ).fetchone()
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no) "
            "VALUES (%s,%s,%s) RETURNING id",
            (int(org1["id"]), int(company1["id"]), f"CASE-{tag}"),
        ).fetchone()
    try:
        assert get_case(int(org1["id"]), int(case["id"])) is not None
        assert get_case(int(org2["id"]), int(case["id"])) is None
        assert list_cases(int(org2["id"])) == []
        assert any(row["id"] == int(case["id"]) for row in list_cases(int(org1["id"])))
    finally:
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM inst_research_case WHERE org_id IN (%s,%s)",
                (int(org1["id"]), int(org2["id"])),
            )
            conn.execute(
                "DELETE FROM inst_company WHERE org_id IN (%s,%s)",
                (int(org1["id"]), int(org2["id"])),
            )
            conn.execute(
                "DELETE FROM inst_orgs WHERE id IN (%s,%s)",
                (int(org1["id"]), int(org2["id"])),
            )
