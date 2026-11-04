#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性初始化机构量化复核开发账号（仅 *_dev）。

- 创建独立 cx_quant_reviewer 用户（若已存在则拒绝，不重置密码）
- 绑定到独立 quant-dev 机构，角色 quant_reviewer
- 密码只写入指定私有 JSON 文件（600），不打印到 stdout
- 不改 quant_researcher 账号，不清库，不碰真实机构
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys

import psycopg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from services.auth.auth_store import hash_password  # noqa: E402
from services.core.env_config import env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="cx_quant_reviewer")
    parser.add_argument("--org-code", default="quant-dev")
    parser.add_argument("--org-name", default="量化开发机构")
    parser.add_argument("--org-name-en", default="Quant Dev Org")
    parser.add_argument(
        "--secrets-file",
        default="/home/dev01/project/SVQuant-zxd-factor/.runtime/secrets/quant-reviewer.json",
    )
    args = parser.parse_args()

    url = env("DATABASE_URL", "") or ""
    db = url.rsplit("/", 1)[-1]
    if not db.endswith("_dev") or db == "svquant":
        print(f"拒绝：DATABASE_URL 指向 {db!r}，只允许 *_dev", file=sys.stderr)
        return 2
    out_dir = os.path.dirname(args.secrets_file)
    if not os.path.isdir(out_dir):
        print(f"拒绝：私有凭据目录不存在 {out_dir}", file=sys.stderr)
        return 2
    if os.path.exists(args.secrets_file):
        print(f"拒绝：凭据文件已存在 {args.secrets_file}（不覆盖）", file=sys.stderr)
        return 2

    password = secrets.token_urlsafe(18)
    tmp_file = f"{args.secrets_file}.tmp-{os.getpid()}"
    fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(
                {"username": args.username, "password": password},
                fh,
                ensure_ascii=False,
            )
            fh.write("\n")
        os.chmod(tmp_file, 0o600)

        with psycopg.connect(url) as conn:
            if conn.execute(
                "SELECT 1 FROM users WHERE username=%s", (args.username,)
            ).fetchone():
                print(f"拒绝：用户 {args.username!r} 已存在，不重置密码", file=sys.stderr)
                return 3
            uid = int(
                conn.execute(
                    "INSERT INTO users (username,password_hash,role,status,display_name) "
                    "VALUES (%s,%s,'user','active','量化研究复核') RETURNING id",
                    (args.username, hash_password(password)),
                ).fetchone()[0]
            )
            org_id = int(
                conn.execute(
                    "INSERT INTO inst_orgs (code,name_cn,name_en) VALUES (%s,%s,%s) "
                    "ON CONFLICT (code) DO UPDATE SET name_cn=EXCLUDED.name_cn,"
                    "name_en=EXCLUDED.name_en RETURNING id",
                    (args.org_code, args.org_name, args.org_name_en),
                ).fetchone()[0]
            )
            rows = conn.execute(
                "SELECT org_id, role FROM inst_members WHERE user_id=%s AND status='active'",
                (uid,),
            ).fetchall()
            if rows:
                raise RuntimeError(f"新用户已有机构成员关系 {rows!r}")
            member_id = int(
                conn.execute(
                    "INSERT INTO inst_members (org_id,user_id,role,title_cn,status) "
                    "VALUES (%s,%s,'quant_reviewer','量化研究复核','active') RETURNING id",
                    (org_id, uid),
                ).fetchone()[0]
            )
            conn.commit()

        os.replace(tmp_file, args.secrets_file)
        os.chmod(args.secrets_file, 0o600)
    except Exception as exc:  # noqa: BLE001
        try:
            os.unlink(tmp_file)
        except OSError:
            pass
        print(f"失败：{exc}", file=sys.stderr)
        return 4

    print(
        f"OK user={args.username}(id={uid}) org={args.org_code}(id={org_id}) "
        f"role=quant_reviewer member_id={member_id} db={db} "
        f"secret={args.secrets_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
