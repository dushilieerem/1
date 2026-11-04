# -*- coding: utf-8 -*-
"""B2 证据可信层：A-D 分级、版本 hash 与风控 hash 绑定。"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")
os.environ.setdefault("RE_CATALOG_SYNC_ENABLED", "0")
os.environ.setdefault("SVQUANT_PANEL_DAILY_ENABLED", "0")
os.environ.setdefault("SVQUANT_PAPER_TRADING_ENABLED", "0")
os.environ.setdefault("NEWS_INGEST_INTERVAL_SEC", "0")
os.environ.setdefault("RE_CATALOG_WARM_ENABLED", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg.types.json import Jsonb  # noqa: E402

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()


def test_evidence_grade_mapping() -> None:
    assert svc._evidence_grade("ifind:parquet", "financial") == "B"
    assert svc._evidence_grade("ifind:parquet", "market") == "B"
    assert svc._evidence_grade("eastmoney", "fact") == "C"
    assert svc._evidence_grade("agent", "research") == "D"
    assert svc._evidence_grade("annual-report", "filing") == "A"
    assert svc._evidence_grade("x", "news") == "C"


def test_version_hash_and_risk_binding() -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"ev-{tag}", f"证据测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market) "
            "VALUES (%s,%s,'证据测试公司','CN') RETURNING id",
            (org_id, f"EVD{tag[:4].upper()}.SH"),
        ).fetchone()
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no) "
            "VALUES (%s,%s,%s) RETURNING id",
            (org_id, int(company["id"]), f"EV-{tag}"),
        ).fetchone()
        evidence = conn.execute(
            "INSERT INTO inst_evidence "
            "(org_id, case_id, evidence_type, grade, title, quote, source, as_of, available_time) "
            "VALUES (%s,%s,'financial','B','测试财务','营收 1 亿','ifind:parquet',%s,%s) RETURNING id",
            (org_id, int(case["id"]), date.today(), date.today()),
        ).fetchone()
        version = conn.execute(
            "INSERT INTO inst_research_version "
            "(case_id, version_no, status, six_dim, valuation, conclusion, evidence_ids) "
            "VALUES (%s,1,'approved','[]'::jsonb,NULL,'有条件通过',%s) RETURNING *",
            (int(case["id"]), Jsonb([int(evidence["id"])])),
        ).fetchone()
        version = svc._ensure_version_hash(conn, version)
        evidence_hash = svc._hash(svc._evidence_payload(conn, [int(evidence["id"])]))
        snapshot = {
            "research_version_id": int(version["id"]),
            "research_content_hash": version["content_hash"],
            "evidence_hash": evidence_hash,
            "target_weight": 0.02,
            "valid_until": (date.today() + timedelta(days=7)).isoformat(),
            "price_low": None,
            "price_high": None,
        }
        checks = svc._risk_checks(conn, org_id, {"id": 1, "target_weight": 0.02}, {"snapshot": snapshot, "version_no": 1})
        binding = next(c for c in checks if c["key"] == "hash_binding")
        assert binding["status"] == "pass", checks
        assert version["content_hash"]
        assert version["cutoff"]

        snapshot["evidence_hash"] = "tampered"
        checks = svc._risk_checks(conn, org_id, {"id": 1, "target_weight": 0.02}, {"snapshot": snapshot, "version_no": 1})
        binding = next(c for c in checks if c["key"] == "hash_binding")
        assert binding["status"] == "block", checks
