# -*- coding: utf-8 -*-
"""Pytest 全局环境：为不经过 FastAPI lifespan 的用例准备只读/服务层 schema。

CI 的 backend-check 会启动空 PostgreSQL；机构/量化用例会直接查询
`ref_security_industry`、`md_*` 等服务层表，而生产由 lifespan 的
bootstrap_schemas 建表。这里只建表、不灌演示数据，保证测试与生产口径一致。
"""
from __future__ import annotations

import os


def pytest_sessionstart(session) -> None:
    _ = session
    if os.environ.get("SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP") == "1":
        return
    if not (os.environ.get("DATABASE_URL") or "").strip():
        return
    from services.marketdata.schema import ensure_marketdata_schema

    # 建表即可；索引由 ETL/生产启动单独创建，避免测试启动时锁大表。
    ensure_marketdata_schema(include_indexes=False)
