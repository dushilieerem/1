# -*- coding: utf-8 -*-
"""初始化社区 Postgres：建表 + 种子 admin。

用法:
  conda activate SVQuant
  cd /d E:\\quant-lab\\SVQuant\\backend
  python scripts/init_community_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auth_store import ensure_schema, seed_admin  # noqa: E402
from services.community_store import ensure_posts_schema, seed_sample_posts  # noqa: E402
from services.db import database_url  # noqa: E402
from services.env_config import load_env  # noqa: E402
from services.user_factor_store import (  # noqa: E402
    ensure_user_factors_schema,
    migrate_legacy_custom_to_admin,
)


def main() -> None:
    load_env()
    print(f"DATABASE_URL → {database_url().split('@')[-1]}")
    ensure_schema()
    print("users 表已就绪")
    result = seed_admin()
    user = result["user"]
    print(
        f"admin: username={user['username']} role={user['role']} "
        f"created={result['created']}"
    )
    ensure_posts_schema()
    print("posts 表已就绪")
    n = seed_sample_posts()
    print(f"种子帖: {n} 条" if n else "种子帖: 已有内容，跳过")
    ensure_user_factors_schema()
    mig = migrate_legacy_custom_to_admin()
    print(f"user_custom_factors 就绪（迁移 {mig.get('migrated', 0)}）")
    print("完成。默认密码见 backend/.env 的 ADMIN_PASSWORD")


if __name__ == "__main__":
    main()
