#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""幂等初始化量化开发账号：仅限 svquant_dev / *_dev。

不新建用户、不改密码、不删除任何数据：
- 创建/复用独立开发机构（默认 quant-dev）
- 把既有用户绑定为该机构的 quant_researcher
- 若该用户已有其他 active 机构成员关系则拒绝（首期唯一机构绑定）

用法（先应用迁移 0005）：
  cd backend
  python ../scripts/ops/init_inst_quant_dev.py --username cx_quant_57798f
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from services.core.env_config import env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="cx_quant_57798f")
    parser.add_argument("--org-code", default="quant-dev")
    parser.add_argument("--org-name", default="量化开发机构")
    parser.add_argument("--org-name-en", default="Quant Dev Org")
    args = parser.parse_args()

    url = env("DATABASE_URL", "") or ""
    db = url.rsplit("/", 1)[-1]
    if not db.endswith("_dev") or db == "svquant":
        print(f"拒绝：DATABASE_URL 指向 {db!r}，只允许 *_dev", file=sys.stderr)
        return 2

    with psycopg.connect(url) as conn:
        user = conn.execute(
            "SELECT id, username FROM users WHERE username=%s",
            (args.username,),
        ).fetchone()
        if not user:
            print(f"拒绝：用户 {args.username!r} 不存在；脚本不创建用户/密码", file=sys.stderr)
            return 3
        uid = int(user[0])

        rows = conn.execute(
            """
            SELECT m.id, m.org_id, o.code, m.role, m.status
              FROM inst_members m JOIN inst_orgs o ON o.id=m.org_id
             WHERE m.user_id=%s AND m.status='active'
            """,
            (uid,),
        ).fetchall()
        if rows and not all(r[2] == args.org_code for r in rows):
            print(
                f"拒绝：用户已有其他 active 机构成员关系 {rows!r}；请先人工确认唯一绑定",
                file=sys.stderr,
            )
            return 4

        org = conn.execute(
            """
            INSERT INTO inst_orgs (code, name_cn, name_en)
            VALUES (%s,%s,%s)
            ON CONFLICT (code) DO UPDATE SET name_cn=EXCLUDED.name_cn, name_en=EXCLUDED.name_en
            RETURNING id, code
            """,
            (args.org_code, args.org_name, args.org_name_en),
        ).fetchone()
        org_id = int(org[0])
        existing = conn.execute(
            "SELECT id FROM inst_members WHERE org_id=%s AND user_id=%s",
            (org_id, uid),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE inst_members SET role='quant_researcher', status='active', updated_at=NOW() WHERE id=%s",
                (int(existing[0]),),
            )
            member_id = int(existing[0])
        else:
            member_id = int(
                conn.execute(
                    "INSERT INTO inst_members (org_id,user_id,role,title_cn,status) "
                    "VALUES (%s,%s,'quant_researcher','量化研究员','active') RETURNING id",
                    (org_id, uid),
                ).fetchone()[0]
            )
        conn.commit()

    print(
        f"OK user={args.username}(id={uid}) org={args.org_code}(id={org_id}) "
        f"role=quant_researcher member_id={member_id} db={db}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
