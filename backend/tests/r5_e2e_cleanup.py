# -*- coding: utf-8 -*-
"""R5 E2E final cleanup: remove all R5_TEST_* data from the test database.

Run from backend/ directory: python tests/r5_e2e_cleanup.py
Uses the same DB config as the backend (services.core.db). Never targets
non-test databases: refuses to run when database name is not expected.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.core.db import get_conn  # noqa: E402
from services.core.env_config import env  # noqa: E402

PREFIX = "R5_TEST_%"

# 允许清理的库名（测试库）；其余一律拒绝，防止误连。
ALLOWED_DB = {"svquant", "svquant_test"}


def table_has_column(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s",
        (table, column),
    )
    return cur.fetchone() is not None


def delete_where(cur, table: str, where: str, args: tuple) -> int:
    cur.execute(f"DELETE FROM {table} WHERE {where}", args)
    return cur.rowcount or 0


def first_value(row):
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def main() -> int:
    db_name = env("DATABASE_URL", "").rsplit("/", 1)[-1].split("?")[0]
    if db_name not in ALLOWED_DB:
        print(json.dumps({"error": f"refusing to clean database '{db_name}'"}))
        return 2

    counts: dict[str, int] = {}
    user_ids: list[int] = []

    with get_conn(autocommit=False) as conn:
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE username LIKE %s", (PREFIX,))
        user_ids = [int(first_value(r)) for r in cur.fetchall()]
        counts["r5_users_found"] = len(user_ids)

        def by_users(table: str, column: str = "user_id") -> int:
            if not user_ids or not table_has_column(cur, table, column):
                return 0
            return delete_where(cur, table, f"{column} = ANY(%s)", (user_ids,))

        # 帖子相关：先子后父
        if user_ids:
            cur.execute("SELECT id FROM posts WHERE author_id = ANY(%s)", (user_ids,))
            post_ids = [int(first_value(r)) for r in cur.fetchall()]
            if post_ids:
                counts["post_votes"] = delete_where(cur, "post_votes", "post_id = ANY(%s)", (post_ids,))
                counts["post_favorites"] = delete_where(cur, "post_favorites", "post_id = ANY(%s)", (post_ids,))
                counts["post_comments"] = delete_where(cur, "post_comments", "post_id = ANY(%s)", (post_ids,))
                counts["community_reports"] = delete_where(cur, "community_reports", "post_id = ANY(%s)", (post_ids,))
                counts["posts"] = delete_where(cur, "posts", "id = ANY(%s)", (post_ids,))
            # 评论点赞按用户清理（评论正文已随帖删除）
            counts["comment_votes"] = by_users("comment_votes", "user_id")
            counts["notifications"] = by_users("notifications", "user_id")

        counts["strategy_runs"] = by_users("strategy_runs")
        counts["strategy_projects"] = by_users("strategy_projects")
        counts["strategy_plaza_items"] = by_users("strategy_plaza_items", "author_id") or by_users("strategy_plaza_items", "user_id")
        counts["user_strategy_libraries"] = by_users("user_strategy_libraries")
        counts["user_library_strategies"] = by_users("user_library_strategies")
        counts["user_custom_factors"] = by_users("user_custom_factors")
        counts["user_factor_libraries"] = by_users("user_factor_libraries")
        counts["user_library_factors"] = by_users("user_library_factors", "library_id")
        counts["detect_runs"] = by_users("detect_runs")
        counts["detect_projects"] = by_users("detect_projects")
        counts["user_watchlists"] = by_users("user_watchlists")

        # KH 集合按前缀（E2E 正常路径已通过 API 删除，此处兜底）
        if table_has_column(cur, "kh_documents", "collection_id"):
            counts["kh_documents"] = delete_where(
                cur,
                "kh_documents",
                "collection_id IN (SELECT id FROM kh_collections WHERE name LIKE %s)",
                (PREFIX,),
            )
        counts["kh_collections"] = delete_where(cur, "kh_collections", "name LIKE %s", (PREFIX,))

        # 用户行最后删除
        if user_ids:
            counts["users"] = delete_where(cur, "users", "id = ANY(%s)", (user_ids,))

        conn.commit()

    # 残留复核
    residual: dict[str, int] = {}
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE username LIKE %s", (PREFIX,))
        residual["users"] = int(first_value(cur.fetchone()))
        for table, column in (("posts", "title"), ("strategy_projects", "name"), ("kh_collections", "name")):
            if table_has_column(cur, table, column):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE %s", (PREFIX,))
                residual[table] = int(first_value(cur.fetchone()))
        for table, column in (("strategy_runs", "name"), ("user_factor_libraries", "name"), ("user_watchlists", "name")):
            if table_has_column(cur, table, column):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE %s", (PREFIX,))
                residual[table] = int(first_value(cur.fetchone()))

    result = {"ok": all(v == 0 for v in residual.values()), "deleted": counts, "residual": residual}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
