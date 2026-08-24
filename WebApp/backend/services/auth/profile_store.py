# -*- coding: utf-8 -*-
"""用户公开主页 + 关注。"""
from __future__ import annotations

from typing import Any

from services.auth.auth_store import ensure_schema as ensure_users_schema, get_user_by_username
from services.core.db import get_conn

MAX_AVATAR_CHARS = 700_000
MAX_COVER_CHARS = 1_200_000
MAX_HEADLINE = 80
MAX_BIO = 2000
MAX_DISPLAY_NAME = 32


def ensure_schema() -> None:
    ensure_users_schema()
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_follows (
              follower_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              following_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (follower_id, following_id),
              CONSTRAINT user_follows_self_chk CHECK (follower_id <> following_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_follows_following ON user_follows (following_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_follows_follower ON user_follows (follower_id, created_at DESC)"
        )


def _normalize_image(data_url: str | None, *, max_chars: int, label: str) -> str | None:
    if data_url is None:
        return None
    s = str(data_url).strip()
    if not s:
        return ""
    if not s.startswith("data:image/"):
        raise ValueError(f"{label}须为图片")
    if len(s) > max_chars:
        raise ValueError(f"{label}过大，请压缩后重试")
    return s


def _profile_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "display_name": row.get("display_name") or row["username"],
        "role": row.get("role") or "user",
        "avatar_url": row.get("avatar_url") or None,
        "cover_url": row.get("cover_url") or None,
        "headline": (row.get("headline") or "")[:MAX_HEADLINE],
        "bio": (row.get("bio") or "")[:MAX_BIO],
        "created_at": row["created_at"].isoformat()
        if hasattr(row.get("created_at"), "isoformat")
        else row.get("created_at"),
    }


def get_public_profile(
    username: str,
    *,
    viewer_id: int | None = None,
) -> dict[str, Any]:
    ensure_schema()
    uname = (username or "").strip()
    row = get_user_by_username(uname)
    if not row or row.get("status") != "active":
        raise KeyError("user not found")
    uid = int(row["id"])
    with get_conn() as conn:
        following = conn.execute(
            "SELECT COUNT(*)::int AS c FROM user_follows WHERE follower_id = %s",
            (uid,),
        ).fetchone()["c"]
        followers = conn.execute(
            "SELECT COUNT(*)::int AS c FROM user_follows WHERE following_id = %s",
            (uid,),
        ).fetchone()["c"]
        posts = conn.execute(
            """
            SELECT COUNT(*)::int AS c FROM posts
            WHERE author_id = %s AND status = 'published'
            """,
            (uid,),
        ).fetchone()["c"]
        is_following = False
        if viewer_id is not None and int(viewer_id) != uid:
            hit = conn.execute(
                """
                SELECT 1 FROM user_follows
                WHERE follower_id = %s AND following_id = %s
                """,
                (int(viewer_id), uid),
            ).fetchone()
            is_following = bool(hit)
    profile = _profile_public(row)
    profile.update(
        {
            "following_count": int(following),
            "followers_count": int(followers),
            "post_count": int(posts),
            "is_self": viewer_id is not None and int(viewer_id) == uid,
            "is_following": is_following,
        }
    )
    return {"ok": True, "profile": profile}


def update_my_profile(
    user_id: int,
    *,
    display_name: str | None = None,
    headline: str | None = None,
    bio: str | None = None,
    avatar_url: str | None = ...,  # type: ignore[assignment]
    cover_url: str | None = ...,  # type: ignore[assignment]
) -> dict[str, Any]:
    """更新本人资料。avatar_url/cover_url 传 Ellipsis 表示不改；传 \"\" 清空。"""
    ensure_schema()
    sets: list[str] = []
    params: list[Any] = []

    if display_name is not None:
        name = str(display_name).strip()[:MAX_DISPLAY_NAME]
        if not name:
            raise ValueError("显示名不能为空")
        sets.append("display_name = %s")
        params.append(name)

    if headline is not None:
        sets.append("headline = %s")
        params.append(str(headline).strip()[:MAX_HEADLINE])

    if bio is not None:
        sets.append("bio = %s")
        params.append(str(bio).strip()[:MAX_BIO])

    if avatar_url is not ...:
        img = _normalize_image(avatar_url, max_chars=MAX_AVATAR_CHARS, label="头像")
        sets.append("avatar_url = %s")
        params.append(img or None)

    if cover_url is not ...:
        img = _normalize_image(cover_url, max_chars=MAX_COVER_CHARS, label="封面")
        sets.append("cover_url = %s")
        params.append(img or None)

    if not sets:
        raise ValueError("没有可更新的字段")

    sets.append("updated_at = NOW()")
    params.append(int(user_id))
    with get_conn() as conn:
        row = conn.execute(
            f"""
            UPDATE users SET {", ".join(sets)}
            WHERE id = %s AND status = 'active'
            RETURNING *
            """,
            tuple(params),
        ).fetchone()
        if not row:
            raise KeyError("user not found")
    return get_public_profile(str(row["username"]), viewer_id=int(user_id))


def follow_user(follower_id: int, username: str) -> dict[str, Any]:
    ensure_schema()
    target = get_user_by_username((username or "").strip())
    if not target or target.get("status") != "active":
        raise KeyError("user not found")
    tid = int(target["id"])
    if tid == int(follower_id):
        raise ValueError("不能关注自己")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_follows (follower_id, following_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (int(follower_id), tid),
        )
    return get_public_profile(str(target["username"]), viewer_id=int(follower_id))


def unfollow_user(follower_id: int, username: str) -> dict[str, Any]:
    ensure_schema()
    target = get_user_by_username((username or "").strip())
    if not target:
        raise KeyError("user not found")
    with get_conn() as conn:
        conn.execute(
            """
            DELETE FROM user_follows
            WHERE follower_id = %s AND following_id = %s
            """,
            (int(follower_id), int(target["id"])),
        )
    return get_public_profile(str(target["username"]), viewer_id=int(follower_id))


def list_user_posts(
    username: str,
    *,
    limit: int = 20,
    offset: int = 0,
    section: str | None = None,
) -> dict[str, Any]:
    """公开主页：该用户已发布帖。section 为空或 all 表示全部。"""
    from services.community.community_store import SECTIONS, _POST_SELECT, _row_to_post

    ensure_schema()
    user = get_user_by_username((username or "").strip())
    if not user or user.get("status") != "active":
        raise KeyError("user not found")
    limit = max(1, min(50, int(limit)))
    offset = max(0, int(offset))
    uid = int(user["id"])
    sec = (section or "").strip().lower()
    if sec in ("", "all"):
        sec = None
    elif sec not in SECTIONS:
        raise ValueError("无效分区")

    where = "p.author_id = %s AND p.status = 'published'"
    params: list[Any] = [uid]
    if sec:
        where += " AND p.section = %s"
        params.append(sec)

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*)::int AS c FROM posts p WHERE {where}",
            tuple(params),
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE {where}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, limit, offset]),
        ).fetchall()
        count_rows = conn.execute(
            """
            SELECT section, COUNT(*)::int AS c
            FROM posts
            WHERE author_id = %s AND status = 'published'
            GROUP BY section
            """,
            (uid,),
        ).fetchall()
    section_counts = {str(r["section"]): int(r["c"]) for r in count_rows}
    return {
        "ok": True,
        "total": int(total),
        "section": sec or "all",
        "section_counts": section_counts,
        "items": [_row_to_post(dict(r)) for r in rows],
    }


def _follow_user_brief(
    row: dict[str, Any],
    *,
    viewer_id: int | None,
    following_ids: set[int],
) -> dict[str, Any]:
    uid = int(row["id"])
    return {
        "id": uid,
        "username": row["username"],
        "display_name": row.get("display_name") or row["username"],
        "avatar_url": row.get("avatar_url") or None,
        "headline": (row.get("headline") or "")[:80],
        "post_count": int(row.get("post_count") or 0),
        "followers_count": int(row.get("followers_count") or 0),
        "following_count": int(row.get("following_count") or 0),
        "is_following": viewer_id is not None
        and uid != int(viewer_id)
        and uid in following_ids,
        "is_self": viewer_id is not None and uid == int(viewer_id),
    }


def list_user_follows(
    username: str,
    *,
    kind: str,
    viewer_id: int | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    """kind=following 看他关注了谁；kind=followers 看谁关注他。"""
    ensure_schema()
    if kind not in ("following", "followers"):
        raise ValueError("无效列表类型")
    user = get_user_by_username((username or "").strip())
    if not user or user.get("status") != "active":
        raise KeyError("user not found")
    limit = max(1, min(50, int(limit)))
    offset = max(0, int(offset))
    uid = int(user["id"])

    # 附带帖数 / 粉丝数，列表行可展示知乎式摘要
    user_stats = """
            COALESCE((
              SELECT COUNT(*)::int FROM posts p
              WHERE p.author_id = u.id AND p.status = 'published'
            ), 0) AS post_count,
            COALESCE((
              SELECT COUNT(*)::int FROM user_follows uf
              WHERE uf.following_id = u.id
            ), 0) AS followers_count,
            COALESCE((
              SELECT COUNT(*)::int FROM user_follows uf
              WHERE uf.follower_id = u.id
            ), 0) AS following_count
    """

    if kind == "following":
        count_sql = (
            "SELECT COUNT(*)::int AS c FROM user_follows WHERE follower_id = %s"
        )
        list_sql = f"""
            SELECT u.id, u.username, u.display_name, u.avatar_url, u.headline,
                   f.created_at,
                   {user_stats}
            FROM user_follows f
            JOIN users u ON u.id = f.following_id AND u.status = 'active'
            WHERE f.follower_id = %s
            ORDER BY f.created_at DESC
            LIMIT %s OFFSET %s
            """
    else:
        count_sql = (
            "SELECT COUNT(*)::int AS c FROM user_follows WHERE following_id = %s"
        )
        list_sql = f"""
            SELECT u.id, u.username, u.display_name, u.avatar_url, u.headline,
                   f.created_at,
                   {user_stats}
            FROM user_follows f
            JOIN users u ON u.id = f.follower_id AND u.status = 'active'
            WHERE f.following_id = %s
            ORDER BY f.created_at DESC
            LIMIT %s OFFSET %s
            """

    with get_conn() as conn:
        total = conn.execute(count_sql, (uid,)).fetchone()["c"]
        rows = conn.execute(list_sql, (uid, limit, offset)).fetchall()
        following_ids: set[int] = set()
        if viewer_id is not None and rows:
            ids = [int(r["id"]) for r in rows]
            placeholders = ",".join(["%s"] * len(ids))
            hits = conn.execute(
                f"""
                SELECT following_id FROM user_follows
                WHERE follower_id = %s AND following_id IN ({placeholders})
                """,
                (int(viewer_id), *ids),
            ).fetchall()
            following_ids = {int(h["following_id"]) for h in hits}

    return {
        "ok": True,
        "kind": kind,
        "total": int(total),
        "items": [
            _follow_user_brief(
                dict(r), viewer_id=viewer_id, following_ids=following_ids
            )
            for r in rows
        ],
    }
