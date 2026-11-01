#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M13：为演示机构补齐 24 家公司研究深度并输出覆盖摘要。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.db import get_conn  # noqa: E402
from services.institution import depth  # noqa: E402
from services.institution.inst_service import ensure_and_seed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", type=int, default=None)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    info = ensure_and_seed(args.org_id)
    if not info.get("ok"):
        print("机构未初始化：", info, file=sys.stderr)
        return 2
    org_id = int(info["org_id"])
    with get_conn() as conn:
        manager = conn.execute(
            "SELECT id FROM inst_members WHERE org_id=%s AND role='manager' ORDER BY id LIMIT 1", (org_id,)
        ).fetchone()
        partner = conn.execute(
            "SELECT id FROM inst_members WHERE org_id=%s AND role='partner' ORDER BY id LIMIT 1", (org_id,)
        ).fetchone()
    if not manager or not partner:
        print("缺少 manager/partner 成员，先跑 INST_SEED_DEMO=1", file=sys.stderr)
        return 3
    if args.summary_only:
        out = {"org_id": org_id, "summary": depth.summarize(org_id)}
    else:
        out = depth.refresh(org_id, manager_id=int(manager["id"]), partner_id=int(partner["id"]))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
