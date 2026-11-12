#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 迁移门禁：在空 PostgreSQL 上建基础 schema 后按顺序 apply 全部迁移。

生产启动走 bootstrap_schemas() 的同一顺序；这里提前暴露缺表、FK 顺序、
重复约束和 checksum 漂移，避免到发布时才发现迁移失败。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    from services.auth.auth_store import ensure_schema
    from services.core.migrations import MIGRATIONS_DIR, apply_migrations, status
    from services.factor.detect_store import ensure_detect_schema
    from services.institution.inst_store import ensure_inst_schema
    from services.invest.schema import ensure_invest_schema
    from services.marketdata.schema import ensure_marketdata_schema

    ensure_schema()
    ensure_inst_schema()
    ensure_detect_schema()
    ensure_marketdata_schema(include_indexes=False)
    ensure_invest_schema()
    applied = apply_migrations()
    check = status()
    known = {p.stem for p in Path(MIGRATIONS_DIR).glob("*.sql")}
    orphans = sorted(set(check.get("applied") or []) - known)
    if orphans:
        print(f"[migration-smoke] 数据库存在无文件迁移: {orphans}", file=sys.stderr)
        return 1
    if not check.get("ok") or check.get("pending"):
        print(f"[migration-smoke] pending after apply: {check}", file=sys.stderr)
        return 1
    print(f"[migration-smoke] applied={applied.get('applied')} head={check.get('head')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
