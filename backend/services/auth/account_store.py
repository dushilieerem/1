# -*- coding: utf-8 -*-
"""账号注销：匿名化用户行 + 清理个人业务数据（可审计）。

设计口径：
- 不硬删 users 行：社区帖子/评论保留，作者显示为「已注销用户」。
- 个人数据（自选、组合、模拟盘、策略、因子、知识库、通知等）物理删除。
- 用户名改成 deleted_<id>，邮箱/资料清空，状态置 disabled，token_version 递增使旧令牌失效。
"""
from __future__ import annotations

import uuid
from typing import Any

from services.auth.auth_store import verify_password
from services.core.db import get_conn

# (表名, 所有权列)。表不存在时跳过，便于在旧库/分环境安全执行。
PURGE_TABLES: tuple[tuple[str, str], ...] = (
    ("invest_watchlist", "user_id"),
    ("invest_event", "user_id"),
    ("invest_event_log", "user_id"),
    ("invest_portfolio", "user_id"),
    ("invest_portfolio_meta", "user_id"),
    ("invest_portfolio_trade", "user_id"),
    ("invest_risk_profile", "user_id"),
    ("portfolio", "user_id"),
    ("portfolio_meta", "user_id"),
    ("risk_profiles", "user_id"),
    ("watchlist", "user_id"),
    ("user_watchlists", "user_id"),
    ("user_watchlist_symbols", "user_id"),
    ("paper_accounts", "user_id"),
    ("paper_positions", "user_id"),
    ("paper_orders", "user_id"),
    ("paper_fills", "user_id"),
    ("paper_settlements", "user_id"),
    ("paper_settlement_attempts", "user_id"),
    ("paper_equity_daily", "user_id"),
    ("strategy_projects", "user_id"),
    ("strategy_runs", "user_id"),
    ("strategy_plaza_items", "author_id"),
    ("user_strategy_libraries", "user_id"),
    ("user_library_strategies", "user_id"),
    ("user_library_strategy_versions", "user_id"),
    ("user_factor_libraries", "user_id"),
    ("user_library_factors", "user_id"),
    ("user_custom_factors", "user_id"),
    ("factor_trial_records", "user_id"),
    ("detect_projects", "user_id"),
    ("detect_runs", "user_id"),
    ("ai_conversations", "user_id"),
    ("ai_messages", "user_id"),
    ("ai_chain_state", "user_id"),
    ("ai_research_runs", "user_id"),
    ("ai_usage", "user_id"),
    ("kh_chats", "created_by"),
    ("kh_files", "created_by"),
    ("kh_documents", "created_by"),
    ("kh_collections", "owner_id"),
    ("notifications", "user_id"),
    ("post_favorites", "user_id"),
    ("post_votes", "user_id"),
    ("comment_votes", "user_id"),
    ("user_follows", "follower_id"),
    ("user_follows", "following_id"),
    ("password_reset_tokens", "user_id"),
    ("auth_login_failures", "username"),
)

CONFIRM_WORDS = {"注销", "delete", "DELETE"}


def validate_deletion_request(*, username: str, password_hash: str, password: str, confirm: str) -> None:
    """纯校验：密码 + 确认词（用户名或“注销”/DELETE）。"""
    if not password:
        raise ValueError("请输入登录密码")
    if not verify_password(password, password_hash or ""):
        raise PermissionError("密码不正确")
    text = (confirm or "").strip()
    if text not in CONFIRM_WORDS and text != username:
        raise ValueError("请输入用户名或「注销」确认")


def _existing_tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    ).fetchall()
    return {str(r["table_name"]) for r in rows}


def delete_account(
    user_id: int,
    *,
    password: str,
    confirm: str,
    ip: str | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
        if not row:
            raise LookupError("账号不存在")
        user = dict(row)
        if user.get("status") != "active":
            raise ValueError("账号已停用，无法重复注销")
        validate_deletion_request(
            username=str(user.get("username") or ""),
            password_hash=str(user.get("password_hash") or ""),
            password=password,
            confirm=confirm,
        )
        tables = _existing_tables(conn)
        purged: dict[str, int] = {}
        for table, column in PURGE_TABLES:
            if table not in tables:
                continue
            value: Any = user_id
            if column == "username":
                value = str(user.get("username") or "")
            # 用 savepoint 包住单表删除：某张表被 FK 拦住时只回滚这一条，
            # 不会把整个事务置为 aborted（PostgreSQL 的硬约束）。
            conn.execute("SAVEPOINT purge_table")
            try:
                result = conn.execute(f"DELETE FROM {table} WHERE {column}=%s", (value,))
                conn.execute("RELEASE SAVEPOINT purge_table")
                purged[table] = int(getattr(result, "rowcount", 0) or 0)
            except Exception:
                conn.execute("ROLLBACK TO SAVEPOINT purge_table")
                conn.execute("RELEASE SAVEPOINT purge_table")
                purged.setdefault(f"{table}.skipped", 0)
        new_username = f"deleted_{user_id}"
        if conn.execute("SELECT 1 FROM users WHERE username=%s", (new_username,)).fetchone():
            new_username = f"deleted_{user_id}_{uuid.uuid4().hex[:6]}"
        conn.execute(
            """
            UPDATE users
               SET username=%s,
                   email=NULL,
                   password_hash=%s,
                   status='disabled',
                   display_name='已注销用户',
                   avatar_url=NULL,
                   cover_url=NULL,
                   headline='',
                   bio='',
                   ai_quota_daily=0,
                   token_version=token_version+1,
                   updated_at=NOW()
             WHERE id=%s
            """,
            (new_username, "!", user_id),
        )
        conn.execute("DELETE FROM auth_login_failures WHERE username=%s", (str(user.get("username") or ""),))
    return {
        "ok": True,
        "username": new_username,
        "purged": purged,
        "message": "账号已注销：个人数据已删除，社区内容保留并匿名化显示。",
        "ip": ip,
    }
