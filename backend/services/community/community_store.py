# -*- coding: utf-8 -*-
"""社区：帖子 + 评论（两层）+ 赞踩 + 收藏 + 通知 + 举报。"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from services.core.db import get_conn
from services.community.content_limits import post_body_text

SECTIONS = ("strategy", "factor", "qa", "hotspot", "official")
SECTION_LABELS = {
    "strategy": "策略分享",
    "factor": "因子笔记",
    "qa": "问答",
    "hotspot": "热点分析",
    "official": "官方",
}
# Feed 排序：浏览数 / 收藏数 / 点赞数 / 最新（默认浏览最多）
POST_SORTS = ("views", "favorites", "likes", "newest")
NOTIF_TYPES = ("reply", "mention", "like")
MAX_COMMENT_IMAGES = 3
_MENTION_RE = re.compile(r"@([^\s@]{1,32})")

REPORT_REASONS = ("spam", "abuse", "illegal", "misinfo", "other")
REPORT_REASON_LABELS = {
    "spam": "垃圾广告",
    "abuse": "辱骂骚扰",
    "illegal": "违法违规",
    "misinfo": "虚假误导",
    "other": "其他",
}
REPORT_STATUSES = ("open", "resolved", "dismissed")
REPORT_TARGET_TYPES = ("post", "comment")


def ensure_posts_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
              id            BIGSERIAL PRIMARY KEY,
              author_id     BIGINT NOT NULL REFERENCES users(id),
              section       TEXT NOT NULL,
              title         TEXT NOT NULL,
              body          TEXT NOT NULL DEFAULT '',
              code_snippet  TEXT,
              view_count    INTEGER NOT NULL DEFAULT 0,
              status        TEXT NOT NULL DEFAULT 'published',
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT posts_section_chk CHECK (section IN ('strategy','factor','qa','hotspot','official')),
              CONSTRAINT posts_status_chk CHECK (status IN ('published','hidden','draft'))
            )
            """
        )
        # 已有库升级分区：允许 hotspot
        conn.execute("ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_section_chk")
        conn.execute(
            """
            ALTER TABLE posts ADD CONSTRAINT posts_section_chk
            CHECK (section IN ('strategy','factor','qa','hotspot','official'))
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_posts_created ON posts (created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_posts_section_created ON posts (section, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_posts_views ON posts (view_count DESC)"
        )
        try:
            conn.execute(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE"
            )
        except Exception:
            pass
        try:
            conn.execute(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ"
            )
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS platform_ref JSONB")
        except Exception:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_posts_pinned ON posts (is_pinned DESC, pinned_at DESC NULLS LAST)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS post_comments (
              id            BIGSERIAL PRIMARY KEY,
              post_id       BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              author_id     BIGINT NOT NULL REFERENCES users(id),
              body          TEXT NOT NULL,
              status        TEXT NOT NULL DEFAULT 'published',
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT post_comments_status_chk CHECK (status IN ('published','hidden'))
            )
            """
        )
        try:
            conn.execute(
                "ALTER TABLE post_comments ADD COLUMN IF NOT EXISTS parent_id BIGINT"
            )
        except Exception:
            pass
        try:
            conn.execute(
                "ALTER TABLE post_comments ADD COLUMN IF NOT EXISTS images JSONB DEFAULT '[]'::jsonb"
            )
        except Exception:
            pass
        try:
            conn.execute(
                "ALTER TABLE post_comments ADD COLUMN IF NOT EXISTS reply_to_comment_id BIGINT"
            )
        except Exception:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_post_comments_post ON post_comments (post_id, created_at ASC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_post_comments_parent ON post_comments (parent_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comment_votes (
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              comment_id    BIGINT NOT NULL REFERENCES post_comments(id) ON DELETE CASCADE,
              value         SMALLINT NOT NULL,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, comment_id),
              CONSTRAINT comment_votes_value_chk CHECK (value IN (-1, 1))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_comment_votes_comment ON comment_votes (comment_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
              id            BIGSERIAL PRIMARY KEY,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              actor_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              type          TEXT NOT NULL,
              post_id       BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              comment_id    BIGINT REFERENCES post_comments(id) ON DELETE CASCADE,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              read_at       TIMESTAMPTZ,
              CONSTRAINT notifications_type_chk CHECK (type IN ('reply','mention','like'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications (user_id) WHERE read_at IS NULL"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS post_favorites (
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              post_id       BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, post_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_post_favorites_user ON post_favorites (user_id, created_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS post_votes (
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              post_id       BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              value         SMALLINT NOT NULL,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, post_id),
              CONSTRAINT post_votes_value_chk CHECK (value IN (-1, 1))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_post_votes_post ON post_votes (post_id)"
        )
        # 历史 mention 实为「点回复评论」；迁到 reply。此后 mention 仅用于正文 @
        conn.execute(
            """
            UPDATE notifications
            SET type = 'reply'
            WHERE type = 'mention'
              AND created_at < TIMESTAMPTZ '2026-07-24 00:00:00+08'
            """
        )
        # 清理历史「自己收藏自己」；收藏数按 COUNT 实时算，删行即回落
        conn.execute(
            """
            DELETE FROM post_favorites f
            USING posts p
            WHERE f.post_id = p.id AND f.user_id = p.author_id
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS community_reports (
              id            BIGSERIAL PRIMARY KEY,
              reporter_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              target_type   TEXT NOT NULL,
              post_id       BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              comment_id    BIGINT REFERENCES post_comments(id) ON DELETE CASCADE,
              reason        TEXT NOT NULL,
              detail        TEXT NOT NULL DEFAULT '',
              status        TEXT NOT NULL DEFAULT 'open',
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              resolved_at   TIMESTAMPTZ,
              resolver_id   BIGINT REFERENCES users(id),
              CONSTRAINT community_reports_target_chk
                CHECK (target_type IN ('post','comment')),
              CONSTRAINT community_reports_reason_chk
                CHECK (reason IN ('spam','abuse','illegal','misinfo','other')),
              CONSTRAINT community_reports_status_chk
                CHECK (status IN ('open','resolved','dismissed'))
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_open_uniq
            ON community_reports (
              reporter_id, target_type, post_id, COALESCE(comment_id, 0)
            )
            WHERE status = 'open'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_status_created
            ON community_reports (status, created_at DESC)
            """
        )


def _iso(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def _row_to_post(
    row: dict[str, Any],
    *,
    favorited: bool | None = None,
    my_vote: int | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row["id"],
        "section": row["section"],
        "section_label": SECTION_LABELS.get(row["section"], row["section"]),
        "title": row["title"],
        "body": row.get("body") or "",
        "code_snippet": row.get("code_snippet"),
        "view_count": int(row.get("view_count") or 0),
        "comment_count": int(row.get("comment_count") or 0),
        "favorite_count": int(row.get("favorite_count") or 0),
        "like_count": int(row.get("like_count") or 0),
        "dislike_count": int(row.get("dislike_count") or 0),
        "status": row.get("status") or "published",
        "is_pinned": bool(row.get("is_pinned")),
        "pinned_at": _iso(row.get("pinned_at")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "author": {
            "id": row.get("author_id"),
            "username": row.get("username"),
            "display_name": row.get("display_name") or row.get("username"),
            "avatar_url": row.get("avatar_url") or None,
        },
    }
    pref = _parse_platform_ref(row.get("platform_ref"))
    if pref is not None:
        out["platform_ref"] = pref
    if favorited is not None:
        out["favorited"] = favorited
    if my_vote is not None:
        out["my_vote"] = int(my_vote)
    return out


def _parse_platform_ref(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    from ai.crews._shared.metrics_trust import normalize_platform_ref

    return normalize_platform_ref(raw)


def _dump_platform_ref(raw: Any) -> Any:
    """写入 JSONB；空则 NULL。"""
    from psycopg.types.json import Json

    from ai.crews._shared.metrics_trust import normalize_platform_ref

    ref = normalize_platform_ref(raw) if raw is not None else None
    if not ref:
        return None
    return Json(ref)


def get_post_platform_ref(post_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT platform_ref FROM posts WHERE id = %s",
            (int(post_id),),
        ).fetchone()
    if not row:
        return None
    return _parse_platform_ref(row.get("platform_ref"))


def _parse_images(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) >= MAX_COMMENT_IMAGES:
            break
    return out


def _normalize_images(images: list[str] | None) -> list[str]:
    if not images:
        return []
    out: list[str] = []
    for item in images:
        s = str(item or "").strip()
        if not s:
            continue
        # 限制单张体积（粗略：dataURL 字符数）
        if len(s) > 900_000:
            raise ValueError("评论图片过大，请压缩后重试")
        out.append(s)
        if len(out) >= MAX_COMMENT_IMAGES:
            break
    return out


def _row_to_comment(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row["id"],
        "post_id": row["post_id"],
        "body": row["body"],
        "parent_id": row.get("parent_id"),
        "images": _parse_images(row.get("images")),
        "like_count": int(row.get("like_count") or 0),
        "dislike_count": int(row.get("dislike_count") or 0),
        "my_vote": int(row["my_vote"]) if row.get("my_vote") is not None else 0,
        "created_at": _iso(row.get("created_at")),
        "author": {
            "id": row.get("author_id"),
            "username": row.get("username"),
            "display_name": row.get("display_name") or row.get("username"),
            "avatar_url": row.get("avatar_url") or None,
        },
    }
    if row.get("reply_to_username") or row.get("reply_to_display_name"):
        out["reply_to"] = {
            "id": row.get("reply_to_author_id"),
            "username": row.get("reply_to_username"),
            "display_name": row.get("reply_to_display_name")
            or row.get("reply_to_username"),
        }
    return out


def _insert_notification(
    conn: Any,
    *,
    user_id: int,
    actor_id: int,
    typ: str,
    post_id: int,
    comment_id: int | None,
) -> None:
    if user_id == actor_id:
        return
    if typ not in NOTIF_TYPES:
        return
    conn.execute(
        """
        INSERT INTO notifications (user_id, actor_id, type, post_id, comment_id)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, actor_id, typ, post_id, comment_id),
    )


def _resolve_root_parent(
    conn: Any, post_id: int, parent_id: int
) -> tuple[int, dict[str, Any]]:
    """任意回复上卷到一级评论；返回 (root_id, 被回复评论行)。"""
    parent = conn.execute(
        """
        SELECT id, post_id, parent_id, author_id, body
        FROM post_comments
        WHERE id = %s AND status = 'published'
        """,
        (int(parent_id),),
    ).fetchone()
    if not parent or int(parent["post_id"]) != int(post_id):
        raise ValueError("回复的评论不存在")
    target = dict(parent)
    root_id = int(parent["id"])
    if parent.get("parent_id"):
        root_id = int(parent["parent_id"])
        # 校验 root 仍存在
        root = conn.execute(
            """
            SELECT id FROM post_comments
            WHERE id = %s AND post_id = %s AND status = 'published' AND parent_id IS NULL
            """,
            (root_id, post_id),
        ).fetchone()
        if not root:
            raise ValueError("回复的评论不存在")
    return root_id, target


def _find_mentioned_user_ids(conn: Any, body: str, *, exclude_id: int) -> list[int]:
    """正文 @用户名 / @显示名 → user id（优先 username）。"""
    names = []
    for m in _MENTION_RE.finditer(body or ""):
        name = (m.group(1) or "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return []
    ids: list[int] = []
    for name in names[:10]:
        row = conn.execute(
            "SELECT id FROM users WHERE username = %s LIMIT 1",
            (name,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT id FROM users WHERE display_name = %s LIMIT 1",
                (name,),
            ).fetchone()
        if row and int(row["id"]) != int(exclude_id):
            uid = int(row["id"])
            if uid not in ids:
                ids.append(uid)
    return ids


def seed_sample_posts() -> int:
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
        if n and int(n) > 0:
            return 0
        admin = conn.execute(
            "SELECT id FROM users WHERE username = %s LIMIT 1",
            ("admin",),
        ).fetchone()
        if not admin:
            return 0
        aid = admin["id"]
        samples = [
            (
                "official",
                "欢迎来到 SVQuant 社区",
                "这里分享因子与策略思路。游客可浏览，登录后可发帖。\n\n"
                "内容仅供学习交流，不构成投资建议。",
                None,
            ),
            (
                "factor",
                "因子笔记：如何读 IC 与分层",
                "检测报告里可看日频 IC、累计 IC、分布与滚动 IR；行业页默认 Top5，也可自行勾选。",
                "def momentum_20d(self):\n    return self.close.pct_change(20)",
            ),
            (
                "strategy",
                "策略分享：多空分层的最小示例",
                "思路：按因子分 5 组，做多最高组、做空最低组，观察多空价差。"
                "参数与代码可放在下方代码区。",
                "def combo_factor(self):\n    return 0.5 * self.momentum_20d() + 0.5 * self.volume_20d()",
            ),
            (
                "qa",
                "问答：检测很慢怎么办？",
                "股票池越大、区间越长，耗时越明显。"
                "可先缩小区间或换更小股票池试跑。",
                None,
            ),
        ]
        for section, title, body, code in samples:
            conn.execute(
                """
                INSERT INTO posts (author_id, section, title, body, code_snippet, status)
                VALUES (%s, %s, %s, %s, %s, 'published')
                """,
                (aid, section, title, body, code),
            )
        return len(samples)


_POST_SELECT = """
    SELECT p.*, u.username, u.display_name, u.avatar_url,
           COALESCE(cc.cnt, 0) AS comment_count,
           COALESCE(fc.cnt, 0) AS favorite_count,
           COALESCE(lk.cnt, 0) AS like_count,
           COALESCE(dk.cnt, 0) AS dislike_count
    FROM posts p
    JOIN users u ON u.id = p.author_id
    LEFT JOIN (
      SELECT post_id, COUNT(*) AS cnt FROM post_comments
      WHERE status = 'published' GROUP BY post_id
    ) cc ON cc.post_id = p.id
    LEFT JOIN (
      SELECT post_id, COUNT(*) AS cnt FROM post_favorites GROUP BY post_id
    ) fc ON fc.post_id = p.id
    LEFT JOIN (
      SELECT post_id, COUNT(*) AS cnt FROM post_votes
      WHERE value = 1 GROUP BY post_id
    ) lk ON lk.post_id = p.id
    LEFT JOIN (
      SELECT post_id, COUNT(*) AS cnt FROM post_votes
      WHERE value = -1 GROUP BY post_id
    ) dk ON dk.post_id = p.id
"""


def _search_pattern(q: str | None) -> str | None:
    """标题/正文/代码模糊搜索；转义 LIKE 通配符。"""
    raw = (q or "").strip()
    if not raw:
        return None
    raw = raw[:80]
    escaped = (
        raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def list_posts(
    *,
    section: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    sort_key = (sort or "views").strip().lower()
    if sort_key not in POST_SORTS:
        raise ValueError(f"无效排序: {sort}")
    pin_first = "p.is_pinned DESC, p.pinned_at DESC NULLS LAST, "
    if sort_key == "favorites":
        order_by = f"{pin_first}COALESCE(fc.cnt, 0) DESC, p.created_at DESC, p.id DESC"
    elif sort_key == "likes":
        order_by = f"{pin_first}COALESCE(lk.cnt, 0) DESC, p.created_at DESC, p.id DESC"
    elif sort_key == "newest":
        order_by = f"{pin_first}p.created_at DESC, p.id DESC"
    else:
        order_by = f"{pin_first}p.view_count DESC, p.created_at DESC, p.id DESC"
    params: list[Any] = []
    where = "WHERE p.status = 'published'"
    if section and section != "all":
        if section not in SECTIONS:
            raise ValueError(f"无效分区: {section}")
        where += " AND p.section = %s"
        params.append(section)
    pattern = _search_pattern(q)
    if pattern:
        where += (
            " AND ("
            "p.title ILIKE %s ESCAPE '\\' OR "
            "p.body ILIKE %s ESCAPE '\\' OR "
            "COALESCE(p.code_snippet, '') ILIKE %s ESCAPE '\\'"
            ")"
        )
        params.extend([pattern, pattern, pattern])
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            {where}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
            """,
            params,
        ).fetchall()
        count_params = params[:-2]
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM posts p {where}",
            count_params,
        ).fetchone()["c"]
    return {
        "ok": True,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "sort": sort_key,
        "q": (q or "").strip()[:80] or None,
        "sections": [{"id": k, "label": v} for k, v in SECTION_LABELS.items()],
        "items": [_row_to_post(dict(r)) for r in rows],
    }


def list_hot_posts(*, limit: int = 10, section: str | None = None) -> dict[str, Any]:
    limit = max(1, min(30, int(limit)))
    params: list[Any] = []
    where = "WHERE p.status = 'published'"
    if section and section != "all":
        if section not in SECTIONS:
            raise ValueError(f"无效分区: {section}")
        where += " AND p.section = %s"
        params.append(section)
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            {where}
            ORDER BY p.view_count DESC, p.created_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return {"ok": True, "items": [_row_to_post(dict(r)) for r in rows]}


def get_post(
    post_id: int,
    *,
    bump_view: bool = True,
    viewer_id: int | None = None,
    viewer_role: str = "user",
) -> dict[str, Any]:
    admin = viewer_role == "admin"
    with get_conn() as conn:
        # 先取行判断权限；草稿仅作者/admin 可见，不计浏览
        raw = conn.execute(
            "SELECT id, author_id, status FROM posts WHERE id = %s",
            (post_id,),
        ).fetchone()
        if not raw:
            raise KeyError(f"post not found: {post_id}")
        st = str(raw["status"] or "")
        author_id = int(raw["author_id"])
        is_author = viewer_id is not None and int(viewer_id) == author_id
        if st == "draft":
            if not (is_author or admin):
                raise KeyError(f"post not found: {post_id}")
        elif st == "hidden":
            if not admin:
                raise KeyError(f"post not found: {post_id}")
        elif st != "published":
            raise KeyError(f"post not found: {post_id}")

        if bump_view and st == "published":
            conn.execute(
                """
                UPDATE posts SET view_count = view_count + 1, updated_at = NOW()
                WHERE id = %s AND status = 'published'
                """,
                (post_id,),
            )
        row = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.id = %s
            """,
            (post_id,),
        ).fetchone()
        favorited = None
        my_vote: int | None = None
        if viewer_id is not None and row and st == "published":
            fav = conn.execute(
                """
                SELECT 1 FROM post_favorites
                WHERE user_id = %s AND post_id = %s
                """,
                (viewer_id, post_id),
            ).fetchone()
            favorited = fav is not None
            vote = conn.execute(
                """
                SELECT value FROM post_votes
                WHERE user_id = %s AND post_id = %s
                """,
                (viewer_id, post_id),
            ).fetchone()
            my_vote = int(vote["value"]) if vote else 0
    if not row:
        raise KeyError(f"post not found: {post_id}")
    return {
        "ok": True,
        "post": _row_to_post(dict(row), favorited=favorited, my_vote=my_vote),
    }


def _normalize_post_fields(
    *,
    title: str,
    body: str,
    section: str,
    code_snippet: str | None,
    author_role: str,
    as_draft: bool,
) -> tuple[str, str, str, str | None]:
    title = (title or "").strip()
    body = (body or "").strip()
    if len(post_body_text(body)) > 20_000:
        raise ValueError("正文过长（最多 20000 字符）")
    section = (section or "").strip() or "strategy"
    code = (code_snippet or "").strip() or None
    if len(title) > 120:
        raise ValueError("标题过长（最多 120 字）")
    if section not in SECTIONS:
        raise ValueError(f"无效分区，可选: {', '.join(SECTIONS)}")
    if section == "official" and author_role != "admin":
        raise ValueError("仅管理员可发布官方内容")
    if as_draft:
        if not title:
            title = "未命名草稿"
        return title, body, section, code
    if not title:
        raise ValueError("标题不能为空")
    if not body and not code:
        raise ValueError("正文与代码不能同时为空")
    return title, body, section, code


def create_post(
    author_id: int,
    *,
    title: str,
    body: str,
    section: str,
    code_snippet: str | None = None,
    author_role: str = "user",
    status: str = "published",
    platform_ref: Any = None,
) -> dict[str, Any]:
    status = (status or "published").strip().lower()
    if status not in ("published", "draft"):
        raise ValueError("status 仅支持 published / draft")
    title, body, section, code = _normalize_post_fields(
        title=title,
        body=body,
        section=section,
        code_snippet=code_snippet,
        author_role=author_role,
        as_draft=status == "draft",
    )
    pref = _dump_platform_ref(platform_ref)
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO posts (author_id, section, title, body, code_snippet, status, platform_ref)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (author_id, section, title, body, code, status, pref),
        ).fetchone()
        pid = int(row["id"])
        full = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.id = %s
            """,
            (pid,),
        ).fetchone()
    return {"ok": True, "post": _row_to_post(dict(full))}


def update_post(
    user_id: int,
    post_id: int,
    *,
    title: str,
    body: str,
    section: str,
    code_snippet: str | None = None,
    author_role: str = "user",
    status: str | None = None,
    platform_ref: Any = None,
    clear_platform_ref: bool = False,
) -> dict[str, Any]:
    """作者原地更新；草稿可续写/发布，已发布帖改内容（不可降为草稿）。

    platform_ref：传入 dict 则覆盖；clear_platform_ref=True 清空；
    二者皆否且未传有效引用时保留原列。
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, author_id, status, platform_ref FROM posts WHERE id = %s",
            (post_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"post not found: {post_id}")
        cur_status = str(row["status"] or "")
        if cur_status not in ("published", "draft"):
            raise KeyError(f"post not found: {post_id}")
        if int(row["author_id"]) != int(user_id) and author_role != "admin":
            raise PermissionError("只能编辑自己的帖子")

        next_status = cur_status
        if status is not None:
            want = str(status).strip().lower()
            if want not in ("published", "draft"):
                raise ValueError("status 仅支持 published / draft")
            if cur_status == "published" and want == "draft":
                raise ValueError("已发布帖不能改回草稿")
            next_status = want

        title, body, section, code = _normalize_post_fields(
            title=title,
            body=body,
            section=section,
            code_snippet=code_snippet,
            author_role=author_role,
            as_draft=next_status == "draft",
        )
        if clear_platform_ref:
            pref = None
        elif platform_ref is not None:
            pref = _dump_platform_ref(platform_ref)
            if pref is None and platform_ref:
                # 传入了但规范化失败：保留原值
                pref = row.get("platform_ref")
        else:
            pref = row.get("platform_ref")
        conn.execute(
            """
            UPDATE posts
            SET title = %s, body = %s, section = %s, code_snippet = %s,
                status = %s, platform_ref = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (title, body, section, code, next_status, pref, post_id),
        )
        full = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.id = %s
            """,
            (post_id,),
        ).fetchone()
    return {"ok": True, "post": _row_to_post(dict(full))}


def delete_post(
    user_id: int,
    post_id: int,
    *,
    author_role: str = "user",
) -> dict[str, Any]:
    """已发布 → 软删 hidden；草稿 → 直接删除。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, author_id, status FROM posts WHERE id = %s",
            (post_id,),
        ).fetchone()
        if not row or row["status"] not in ("published", "draft"):
            raise KeyError(f"post not found: {post_id}")
        if int(row["author_id"]) != int(user_id) and author_role != "admin":
            raise PermissionError("只能删除自己的帖子")
        if row["status"] == "draft":
            conn.execute("DELETE FROM posts WHERE id = %s", (post_id,))
            return {"ok": True, "id": int(post_id), "purged": True}
        conn.execute(
            """
            UPDATE posts
            SET status = 'hidden', updated_at = NOW()
            WHERE id = %s
            """,
            (post_id,),
        )
    return {"ok": True, "id": int(post_id)}


def moderate_post(
    post_id: int,
    *,
    author_role: str = "user",
    pinned: bool | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """管理员：置顶/取消置顶、下架/恢复。"""
    if author_role != "admin":
        raise PermissionError("仅管理员可操作")
    if pinned is None and status is None:
        raise ValueError("请指定 pinned 或 status")
    if status is not None and status not in ("published", "hidden"):
        raise ValueError("status 仅支持 published / hidden")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, status, is_pinned FROM posts WHERE id = %s",
            (post_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"post not found: {post_id}")
        if status is not None:
            conn.execute(
                """
                UPDATE posts
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, post_id),
            )
        if pinned is not None:
            if pinned:
                conn.execute(
                    """
                    UPDATE posts
                    SET is_pinned = TRUE,
                        pinned_at = COALESCE(pinned_at, NOW()),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (post_id,),
                )
            else:
                conn.execute(
                    """
                    UPDATE posts
                    SET is_pinned = FALSE, pinned_at = NULL, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (post_id,),
                )
        full = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.id = %s
            """,
            (post_id,),
        ).fetchone()
    return {"ok": True, "post": _row_to_post(dict(full))}


def list_comments(
    post_id: int,
    *,
    viewer_id: int | None = None,
    viewer_role: str = "user",
) -> dict[str, Any]:
    with get_conn() as conn:
        if viewer_role == "admin":
            exists = conn.execute(
                "SELECT id FROM posts WHERE id = %s AND status IN ('published', 'hidden')",
                (post_id,),
            ).fetchone()
        else:
            exists = conn.execute(
                "SELECT id FROM posts WHERE id = %s AND status = 'published'",
                (post_id,),
            ).fetchone()
        if not exists:
            raise KeyError(f"post not found: {post_id}")
        rows = conn.execute(
            """
            SELECT c.*, u.username, u.display_name, u.avatar_url,
                   pu.id AS reply_to_author_id,
                   pu.username AS reply_to_username,
                   pu.display_name AS reply_to_display_name,
                   COALESCE(lk.cnt, 0) AS like_count,
                   COALESCE(dk.cnt, 0) AS dislike_count,
                   mv.value AS my_vote
            FROM post_comments c
            JOIN users u ON u.id = c.author_id
            LEFT JOIN post_comments rtc ON rtc.id = c.reply_to_comment_id
            LEFT JOIN users pu ON pu.id = rtc.author_id
            LEFT JOIN (
              SELECT comment_id, COUNT(*) AS cnt FROM comment_votes
              WHERE value = 1 GROUP BY comment_id
            ) lk ON lk.comment_id = c.id
            LEFT JOIN (
              SELECT comment_id, COUNT(*) AS cnt FROM comment_votes
              WHERE value = -1 GROUP BY comment_id
            ) dk ON dk.comment_id = c.id
            LEFT JOIN comment_votes mv
              ON mv.comment_id = c.id AND mv.user_id = %s
            WHERE c.post_id = %s AND c.status = 'published'
            ORDER BY
              COALESCE(lk.cnt, 0) DESC,
              c.created_at ASC
            """,
            (viewer_id if viewer_id is not None else -1, post_id),
        ).fetchall()
    items = [_row_to_comment(dict(r)) for r in rows]
    return {"ok": True, "total": len(items), "items": items}


def create_comment(
    post_id: int,
    author_id: int,
    body: str,
    *,
    parent_id: int | None = None,
    images: list[str] | None = None,
) -> dict[str, Any]:
    body = (body or "").strip()
    imgs = _normalize_images(images)
    if not body and not imgs:
        raise ValueError("评论不能为空")
    if len(body) > 2000:
        raise ValueError("评论过长（最多 2000 字）")
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id, author_id FROM posts WHERE id = %s AND status = 'published'",
            (post_id,),
        ).fetchone()
        if not exists:
            raise KeyError(f"post not found: {post_id}")
        post_author_id = int(exists["author_id"])

        root_id: int | None = None
        reply_target: dict[str, Any] | None = None
        reply_to_comment_id: int | None = None
        if parent_id is not None:
            root_id, reply_target = _resolve_root_parent(conn, post_id, int(parent_id))
            reply_to_comment_id = int(reply_target["id"])

        row = conn.execute(
            """
            INSERT INTO post_comments
              (post_id, author_id, body, status, parent_id, images, reply_to_comment_id)
            VALUES (%s, %s, %s, 'published', %s, %s::jsonb, %s)
            RETURNING id
            """,
            (
                post_id,
                author_id,
                body,
                root_id,
                json.dumps(imgs),
                reply_to_comment_id,
            ),
        ).fetchone()
        cid = int(row["id"])

        # 消息语义：
        # - reply「回复我的」= 一级评论通知楼主，或点「回复」且正文未 @ 对方
        # - mention「@我的」= 正文出现 @用户名/@显示名（优先于 reply，避免挤进「回复」栏）
        mentioned = set(
            _find_mentioned_user_ids(conn, body, exclude_id=author_id)
        )
        for uid in mentioned:
            _insert_notification(
                conn,
                user_id=uid,
                actor_id=author_id,
                typ="mention",
                post_id=post_id,
                comment_id=cid,
            )

        if reply_target is None:
            if post_author_id not in mentioned:
                _insert_notification(
                    conn,
                    user_id=post_author_id,
                    actor_id=author_id,
                    typ="reply",
                    post_id=post_id,
                    comment_id=cid,
                )
        else:
            target_uid = int(reply_target["author_id"])
            if target_uid not in mentioned:
                _insert_notification(
                    conn,
                    user_id=target_uid,
                    actor_id=author_id,
                    typ="reply",
                    post_id=post_id,
                    comment_id=cid,
                )

        full = conn.execute(
            """
            SELECT c.*, u.username, u.display_name, u.avatar_url,
                   pu.id AS reply_to_author_id,
                   pu.username AS reply_to_username,
                   pu.display_name AS reply_to_display_name,
                   0 AS like_count, 0 AS dislike_count, NULL AS my_vote
            FROM post_comments c
            JOIN users u ON u.id = c.author_id
            LEFT JOIN post_comments rtc ON rtc.id = c.reply_to_comment_id
            LEFT JOIN users pu ON pu.id = rtc.author_id
            WHERE c.id = %s
            """,
            (cid,),
        ).fetchone()
    return {"ok": True, "comment": _row_to_comment(dict(full))}


def set_comment_vote(
    user_id: int, comment_id: int, value: int
) -> dict[str, Any]:
    """value: 1 赞 / -1 踩 / 0 取消。"""
    value = int(value)
    if value not in (-1, 0, 1):
        raise ValueError("无效投票")
    with get_conn() as conn:
        c = conn.execute(
            """
            SELECT id, post_id, author_id, status FROM post_comments WHERE id = %s
            """,
            (comment_id,),
        ).fetchone()
        if not c or c["status"] != "published":
            raise KeyError(f"comment not found: {comment_id}")

        prev = conn.execute(
            """
            SELECT value FROM comment_votes
            WHERE user_id = %s AND comment_id = %s
            """,
            (user_id, comment_id),
        ).fetchone()
        prev_val = int(prev["value"]) if prev else 0

        if value == 0:
            conn.execute(
                "DELETE FROM comment_votes WHERE user_id = %s AND comment_id = %s",
                (user_id, comment_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO comment_votes (user_id, comment_id, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, comment_id) DO UPDATE SET value = EXCLUDED.value
                """,
                (user_id, comment_id, value),
            )
            # 首次赞（或从踩/无切换到赞）通知作者
            if value == 1 and prev_val != 1:
                _insert_notification(
                    conn,
                    user_id=int(c["author_id"]),
                    actor_id=user_id,
                    typ="like",
                    post_id=int(c["post_id"]),
                    comment_id=int(c["id"]),
                )

        like_count = conn.execute(
            "SELECT COUNT(*) AS c FROM comment_votes WHERE comment_id = %s AND value = 1",
            (comment_id,),
        ).fetchone()["c"]
        dislike_count = conn.execute(
            "SELECT COUNT(*) AS c FROM comment_votes WHERE comment_id = %s AND value = -1",
            (comment_id,),
        ).fetchone()["c"]
        my = conn.execute(
            "SELECT value FROM comment_votes WHERE user_id = %s AND comment_id = %s",
            (user_id, comment_id),
        ).fetchone()
    return {
        "ok": True,
        "comment_id": comment_id,
        "like_count": int(like_count),
        "dislike_count": int(dislike_count),
        "my_vote": int(my["value"]) if my else 0,
    }


def set_post_vote(user_id: int, post_id: int, value: int) -> dict[str, Any]:
    """value: 1 赞 / -1 踩 / 0 取消。点赞通知作者；点踩不通知。"""
    value = int(value)
    if value not in (-1, 0, 1):
        raise ValueError("无效投票")
    with get_conn() as conn:
        p = conn.execute(
            """
            SELECT id, author_id, status FROM posts WHERE id = %s
            """,
            (post_id,),
        ).fetchone()
        if not p or p["status"] != "published":
            raise KeyError(f"post not found: {post_id}")

        # 自己的帖不可赞踩：静默返回当前计数
        if int(p["author_id"]) == int(user_id):
            like_count = conn.execute(
                "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND value = 1",
                (post_id,),
            ).fetchone()["c"]
            dislike_count = conn.execute(
                "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND value = -1",
                (post_id,),
            ).fetchone()["c"]
            return {
                "ok": True,
                "post_id": post_id,
                "like_count": int(like_count),
                "dislike_count": int(dislike_count),
                "my_vote": 0,
            }

        prev = conn.execute(
            """
            SELECT value FROM post_votes
            WHERE user_id = %s AND post_id = %s
            """,
            (user_id, post_id),
        ).fetchone()
        prev_val = int(prev["value"]) if prev else 0

        if value == 0:
            conn.execute(
                "DELETE FROM post_votes WHERE user_id = %s AND post_id = %s",
                (user_id, post_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO post_votes (user_id, post_id, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, post_id) DO UPDATE SET value = EXCLUDED.value
                """,
                (user_id, post_id, value),
            )
            if value == 1 and prev_val != 1:
                _insert_notification(
                    conn,
                    user_id=int(p["author_id"]),
                    actor_id=user_id,
                    typ="like",
                    post_id=int(p["id"]),
                    comment_id=None,
                )

        like_count = conn.execute(
            "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND value = 1",
            (post_id,),
        ).fetchone()["c"]
        dislike_count = conn.execute(
            "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND value = -1",
            (post_id,),
        ).fetchone()["c"]
        my = conn.execute(
            "SELECT value FROM post_votes WHERE user_id = %s AND post_id = %s",
            (user_id, post_id),
        ).fetchone()
    return {
        "ok": True,
        "post_id": post_id,
        "like_count": int(like_count),
        "dislike_count": int(dislike_count),
        "my_vote": int(my["value"]) if my else 0,
    }


def list_notifications(
    user_id: int,
    *,
    typ: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    params: list[Any] = [user_id]
    where = "WHERE n.user_id = %s"
    if typ:
        if typ not in NOTIF_TYPES:
            raise ValueError(f"无效类型: {typ}")
        where += " AND n.type = %s"
        params.append(typ)
    params.extend([limit, offset])
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM notifications n {where}",
            params[:-2],
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT n.*,
                   a.username AS actor_username,
                   a.display_name AS actor_display_name,
                   a.avatar_url AS actor_avatar_url,
                   p.title AS post_title,
                   c.body AS comment_body
            FROM notifications n
            JOIN users a ON a.id = n.actor_id
            JOIN posts p ON p.id = n.post_id
            LEFT JOIN post_comments c ON c.id = n.comment_id
            {where}
            ORDER BY n.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        items.append(
            {
                "id": d["id"],
                "type": d["type"],
                "post_id": d["post_id"],
                "comment_id": d.get("comment_id"),
                "post_title": d.get("post_title") or "",
                "comment_body": (d.get("comment_body") or "")[:120],
                "created_at": _iso(d.get("created_at")),
                "read_at": _iso(d.get("read_at")),
                "actor": {
                    "id": d["actor_id"],
                    "username": d.get("actor_username"),
                    "display_name": d.get("actor_display_name")
                    or d.get("actor_username"),
                    "avatar_url": d.get("actor_avatar_url") or None,
                },
            }
        )
    return {"ok": True, "total": int(total), "items": items}


def unread_notification_count(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS c FROM notifications
            WHERE user_id = %s AND read_at IS NULL
            """,
            (user_id,),
        ).fetchone()["c"]
        rows = conn.execute(
            """
            SELECT type, COUNT(*) AS c FROM notifications
            WHERE user_id = %s AND read_at IS NULL
            GROUP BY type
            """,
            (user_id,),
        ).fetchall()
    by_type = {t: 0 for t in NOTIF_TYPES}
    for r in rows:
        by_type[str(r["type"])] = int(r["c"])
    return {"ok": True, "total": int(total), "by_type": by_type}


def mark_notifications_read(
    user_id: int,
    *,
    ids: list[int] | None = None,
    typ: str | None = None,
    all_unread: bool = False,
) -> dict[str, Any]:
    with get_conn() as conn:
        if all_unread:
            conn.execute(
                """
                UPDATE notifications SET read_at = NOW()
                WHERE user_id = %s AND read_at IS NULL
                """,
                (user_id,),
            )
        elif ids:
            conn.execute(
                """
                UPDATE notifications SET read_at = NOW()
                WHERE user_id = %s AND id = ANY(%s) AND read_at IS NULL
                """,
                (user_id, list(ids)),
            )
        elif typ:
            if typ not in NOTIF_TYPES:
                raise ValueError(f"无效类型: {typ}")
            conn.execute(
                """
                UPDATE notifications SET read_at = NOW()
                WHERE user_id = %s AND type = %s AND read_at IS NULL
                """,
                (user_id, typ),
            )
        else:
            raise ValueError("请指定 ids / type / all")
    return unread_notification_count(user_id)


def add_favorite(user_id: int, post_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, author_id FROM posts WHERE id = %s AND status = 'published'",
            (post_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"post not found: {post_id}")
        if int(row["author_id"]) == int(user_id):
            raise ValueError("不能收藏自己的帖子")
        conn.execute(
            """
            INSERT INTO post_favorites (user_id, post_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, post_id) DO NOTHING
            """,
            (user_id, post_id),
        )
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM post_favorites WHERE post_id = %s",
            (post_id,),
        ).fetchone()["c"]
    return {"ok": True, "favorited": True, "favorite_count": int(cnt)}


def remove_favorite(user_id: int, post_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM post_favorites WHERE user_id = %s AND post_id = %s",
            (user_id, post_id),
        )
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM post_favorites WHERE post_id = %s",
            (post_id,),
        ).fetchone()["c"]
    return {"ok": True, "favorited": False, "favorite_count": int(cnt)}


def list_favorites(user_id: int, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM post_favorites WHERE user_id = %s",
            (user_id,),
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            JOIN post_favorites f ON f.post_id = p.id
            WHERE f.user_id = %s AND p.status = 'published'
            ORDER BY f.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "total": int(total),
        "items": [_row_to_post(dict(r), favorited=True) for r in rows],
    }


def list_my_posts(
    user_id: int,
    *,
    status: str = "published",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    status_key = (status or "published").strip().lower()
    if status_key not in ("published", "draft"):
        raise ValueError("status 仅支持 published / draft")
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS c FROM posts
            WHERE author_id = %s AND status = %s
            """,
            (user_id, status_key),
        ).fetchone()["c"]
        order = (
            "p.updated_at DESC, p.id DESC"
            if status_key == "draft"
            else "p.created_at DESC, p.id DESC"
        )
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.author_id = %s AND p.status = %s
            ORDER BY {order}
            LIMIT %s OFFSET %s
            """,
            (user_id, status_key, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "status": status_key,
        "total": int(total),
        "items": [_row_to_post(dict(r)) for r in rows],
    }


def ops_summary(*, author_role: str = "user", days: int = 7) -> dict[str, Any]:
    """管理仓运营看板：近 N 日发帖 / 互动 / 举报待办 + AI 调用（admin only）。"""
    if author_role != "admin":
        raise PermissionError("仅管理员可查看")
    ensure_posts_schema()
    days = max(1, min(90, int(days)))
    with get_conn() as conn:
        posts_7d = conn.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM posts
            WHERE status = 'published'
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (days,),
        ).fetchone()["c"]
        comments_7d = conn.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM post_comments
            WHERE status = 'published'
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (days,),
        ).fetchone()["c"]
        favorites_7d = conn.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM post_favorites
            WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (days,),
        ).fetchone()["c"]
        likes_7d = conn.execute(
            """
            SELECT (
              (SELECT COUNT(*)::int FROM comment_votes
               WHERE value = 1
                 AND created_at >= NOW() - (%s * INTERVAL '1 day'))
              +
              (SELECT COUNT(*)::int FROM post_votes
               WHERE value = 1
                 AND created_at >= NOW() - (%s * INTERVAL '1 day'))
            ) AS c
            """,
            (days, days),
        ).fetchone()["c"]
        reports_open = conn.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM community_reports
            WHERE status = 'open'
            """
        ).fetchone()["c"]
        posts_by_day_rows = conn.execute(
            """
            SELECT to_char(d::date, 'YYYY-MM-DD') AS day, COALESCE(p.c, 0)::int AS posts
            FROM generate_series(
              (CURRENT_DATE - (%s - 1) * INTERVAL '1 day')::date,
              CURRENT_DATE::date,
              '1 day'::interval
            ) AS d
            LEFT JOIN (
              SELECT created_at::date AS day, COUNT(*)::int AS c
              FROM posts
              WHERE status = 'published'
                AND created_at >= CURRENT_DATE - (%s - 1) * INTERVAL '1 day'
              GROUP BY created_at::date
            ) p ON p.day = d::date
            ORDER BY d
            """,
            (days, days),
        ).fetchall()

    from ai.runtime.store import usage_admin_summary

    ai = usage_admin_summary(days=days)
    interactions_7d = int(comments_7d) + int(favorites_7d) + int(likes_7d)
    return {
        "ok": True,
        "days": days,
        "posts_7d": int(posts_7d),
        "comments_7d": int(comments_7d),
        "favorites_7d": int(favorites_7d),
        "likes_7d": int(likes_7d),
        "interactions_7d": interactions_7d,
        "reports_open": int(reports_open),
        "ai_calls_7d": int((ai.get("totals") or {}).get("calls") or 0),
        "ai_users_7d": int((ai.get("totals") or {}).get("users") or 0),
        "ai_tokens_7d": int((ai.get("totals") or {}).get("tokens_in") or 0)
        + int((ai.get("totals") or {}).get("tokens_out") or 0),
        "by_day": [dict(r) for r in posts_by_day_rows],
    }


def list_moderation_posts(
    *,
    author_role: str = "user",
    kind: str = "hidden",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """管理仓：已下架 / 已置顶。"""
    if author_role != "admin":
        raise PermissionError("仅管理员可查看")
    kind_key = (kind or "hidden").strip().lower()
    if kind_key not in ("hidden", "pinned"):
        raise ValueError("kind 仅支持 hidden / pinned")
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    if kind_key == "hidden":
        where = "WHERE p.status = 'hidden'"
        order = "p.updated_at DESC, p.id DESC"
    else:
        where = "WHERE p.is_pinned = TRUE AND p.status = 'published'"
        order = "p.pinned_at DESC NULLS LAST, p.id DESC"
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM posts p {where}",
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            {where}
            ORDER BY {order}
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "kind": kind_key,
        "total": int(total),
        "items": [_row_to_post(dict(r)) for r in rows],
    }


def _row_to_report(row: dict[str, Any]) -> dict[str, Any]:
    reason = str(row.get("reason") or "")
    return {
        "id": int(row["id"]),
        "target_type": row["target_type"],
        "post_id": int(row["post_id"]),
        "comment_id": int(row["comment_id"]) if row.get("comment_id") is not None else None,
        "reason": reason,
        "reason_label": REPORT_REASON_LABELS.get(reason, reason),
        "detail": row.get("detail") or "",
        "status": row.get("status") or "open",
        "created_at": _iso(row.get("created_at")),
        "resolved_at": _iso(row.get("resolved_at")),
        "post_title": row.get("post_title") or "",
        "comment_body": (row.get("comment_body") or "")[:200],
        "reporter": {
            "id": row.get("reporter_id"),
            "username": row.get("reporter_username"),
            "display_name": row.get("reporter_display_name"),
        },
        "resolver_id": row.get("resolver_id"),
    }


def create_report(
    reporter_id: int,
    *,
    target_type: str,
    post_id: int,
    comment_id: int | None = None,
    reason: str,
    detail: str = "",
) -> dict[str, Any]:
    tt = (target_type or "").strip().lower()
    if tt not in REPORT_TARGET_TYPES:
        raise ValueError("target_type 仅支持 post / comment")
    rk = (reason or "").strip().lower()
    if rk not in REPORT_REASONS:
        raise ValueError("无效举报原因")
    detail_s = (detail or "").strip()
    if len(detail_s) > 500:
        raise ValueError("举报说明过长（最多 500 字符）")
    cid = int(comment_id) if comment_id is not None else None
    if tt == "comment" and not cid:
        raise ValueError("举报评论须指定 comment_id")
    if tt == "post":
        cid = None

    with get_conn() as conn:
        post = conn.execute(
            "SELECT id, author_id, status FROM posts WHERE id = %s",
            (int(post_id),),
        ).fetchone()
        if not post:
            raise KeyError(f"post not found: {post_id}")
        if post["status"] not in ("published", "hidden"):
            raise ValueError("该帖不可举报")
        if tt == "post" and int(post["author_id"]) == int(reporter_id):
            raise ValueError("不能举报自己的帖子")

        if tt == "comment":
            crow = conn.execute(
                """
                SELECT id, author_id, post_id, status
                FROM post_comments WHERE id = %s
                """,
                (cid,),
            ).fetchone()
            if not crow or int(crow["post_id"]) != int(post_id):
                raise KeyError(f"comment not found: {cid}")
            if crow["status"] != "published":
                raise ValueError("该评论不可举报")
            if int(crow["author_id"]) == int(reporter_id):
                raise ValueError("不能举报自己的评论")

        exists = conn.execute(
            """
            SELECT id FROM community_reports
            WHERE reporter_id = %s
              AND target_type = %s
              AND post_id = %s
              AND COALESCE(comment_id, 0) = COALESCE(%s, 0)
              AND status = 'open'
            LIMIT 1
            """,
            (int(reporter_id), tt, int(post_id), cid),
        ).fetchone()
        if exists:
            raise ValueError("你已举报过该内容，请等待处理")

        row = conn.execute(
            """
            INSERT INTO community_reports (
              reporter_id, target_type, post_id, comment_id, reason, detail
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, target_type, post_id, comment_id, reason, detail, status, created_at
            """,
            (int(reporter_id), tt, int(post_id), cid, rk, detail_s),
        ).fetchone()

    return {
        "ok": True,
        "report": {
            "id": int(row["id"]),
            "target_type": row["target_type"],
            "post_id": int(row["post_id"]),
            "comment_id": int(row["comment_id"]) if row.get("comment_id") is not None else None,
            "reason": row["reason"],
            "reason_label": REPORT_REASON_LABELS.get(str(row["reason"]), str(row["reason"])),
            "detail": row.get("detail") or "",
            "status": row.get("status") or "open",
            "created_at": _iso(row.get("created_at")),
        },
    }


def list_reports(
    *,
    author_role: str = "user",
    status: str = "open",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if author_role != "admin":
        raise PermissionError("仅管理员可查看举报")
    st = (status or "open").strip().lower()
    if st not in REPORT_STATUSES and st != "all":
        raise ValueError("status 仅支持 open / resolved / dismissed / all")
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    where = "" if st == "all" else "WHERE r.status = %s"
    params_count: list[Any] = [] if st == "all" else [st]
    params_list: list[Any] = list(params_count) + [limit, offset]
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM community_reports r {where}",
            tuple(params_count),
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT
              r.id, r.target_type, r.post_id, r.comment_id,
              r.reason, r.detail, r.status, r.created_at, r.resolved_at,
              r.reporter_id, r.resolver_id,
              p.title AS post_title,
              c.body AS comment_body,
              u.username AS reporter_username,
              u.display_name AS reporter_display_name
            FROM community_reports r
            JOIN posts p ON p.id = r.post_id
            JOIN users u ON u.id = r.reporter_id
            LEFT JOIN post_comments c ON c.id = r.comment_id
            {where}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params_list),
        ).fetchall()
    return {
        "ok": True,
        "status": st,
        "total": int(total),
        "items": [_row_to_report(dict(r)) for r in rows],
    }


def resolve_report(
    report_id: int,
    *,
    author_role: str = "user",
    resolver_id: int,
    status: str = "resolved",
) -> dict[str, Any]:
    if author_role != "admin":
        raise PermissionError("仅管理员可处理举报")
    st = (status or "resolved").strip().lower()
    if st not in ("resolved", "dismissed"):
        raise ValueError("status 仅支持 resolved / dismissed")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, status FROM community_reports WHERE id = %s",
            (int(report_id),),
        ).fetchone()
        if not row:
            raise KeyError(f"report not found: {report_id}")
        if row["status"] != "open":
            raise ValueError("该举报已处理")
        updated = conn.execute(
            """
            UPDATE community_reports
            SET status = %s, resolved_at = NOW(), resolver_id = %s
            WHERE id = %s
            RETURNING id, target_type, post_id, comment_id, reason, detail,
                      status, created_at, resolved_at, resolver_id
            """,
            (st, int(resolver_id), int(report_id)),
        ).fetchone()
    return {
        "ok": True,
        "report": {
            "id": int(updated["id"]),
            "target_type": updated["target_type"],
            "post_id": int(updated["post_id"]),
            "comment_id": int(updated["comment_id"])
            if updated.get("comment_id") is not None
            else None,
            "reason": updated["reason"],
            "reason_label": REPORT_REASON_LABELS.get(
                str(updated["reason"]), str(updated["reason"])
            ),
            "detail": updated.get("detail") or "",
            "status": updated["status"],
            "created_at": _iso(updated.get("created_at")),
            "resolved_at": _iso(updated.get("resolved_at")),
            "resolver_id": updated.get("resolver_id"),
        },
    }


def purge_post(
    post_id: int,
    *,
    author_role: str = "user",
) -> dict[str, Any]:
    """管理员彻底删除（级联评论/收藏/通知）。"""
    if author_role != "admin":
        raise PermissionError("仅管理员可彻底删除")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM posts WHERE id = %s",
            (post_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"post not found: {post_id}")
        conn.execute("DELETE FROM posts WHERE id = %s", (post_id,))
    return {"ok": True, "id": int(post_id), "purged": True}


# 示例帖：每分区 2 条，标题作幂等键
_CURATED: list[tuple[str, str, str, str | None]] = [
    (
        "official",
        "欢迎来到 SVQuant 社区",
        "这里分享策略思路、因子笔记、问答与市场热点。游客可浏览，登录后可发帖、评论与收藏。\n\n"
        "内容仅供学习交流，不构成投资建议。",
        None,
    ),
    (
        "official",
        "社区发帖规范（简版）",
        "1. 标题写清主题，正文尽量给出思路与结论。\n"
        "2. 涉及代码可放在代码区，方便他人复现。\n"
        "3. 「官方」仅平台发布；请勿散播未经验证的荐股信息。",
        None,
    ),
    (
        "strategy",
        "多空分层：用因子分五组做价差观察",
        "做法：按单因子截面分 5 组，做多最高组、做空最低组，看多空价差是否稳定。\n"
        "适合先验证因子方向，再决定是否进入组合。注意换手与成本，短区间结果波动会很大。",
        "def long_short_spread(factor, n_groups=5):\n"
        "    # 伪代码：按因子分位分组后计算多空收益差\n"
        "    q = factor.rank(pct=True)\n"
        "    return q.gt(1 - 1/n_groups).astype(float) - q.lt(1/n_groups).astype(float)",
    ),
    (
        "strategy",
        "动量与低换手的简单叠加思路",
        "思路：中期动量选强势股，再用低换手过滤过度炒作标的，降低追高踩踏风险。\n"
        "落地时建议先单因子看 IC/分层，再等权或打分合成；组合权重与再平衡频率要单独回测。",
        "def combo_score(self):\n"
        "    mom = self.close.pct_change(20)\n"
        "    turn = self.volume / self.volume.rolling(20).mean()\n"
        "    return mom.rank(pct=True) - 0.3 * turn.rank(pct=True)",
    ),
    (
        "factor",
        "因子笔记：如何读 IC 与分层",
        "检测报告里优先看：日频 IC 是否稳定、累计 IC 是否向上、分层是否单调。\n"
        "行业页可先看 Top 行业贡献，再决定要不要做行业中性。短样本上的高 IC 要谨慎解读。",
        "def momentum_20d(self):\n    return self.close.pct_change(20)",
    ),
    (
        "factor",
        "波动率因子：高波与低波各自适用什么场景",
        "低波常与防御、稳态收益相关；高波更偏弹性与主题交易。\n"
        "做因子时建议同时看：IC 方向、分层是否倒挂、以及不同股票池（大盘/中小盘）差异。",
        "def realized_vol_20d(self):\n"
        "    ret = self.close.pct_change()\n"
        "    return ret.rolling(20).std()",
    ),
    (
        "qa",
        "问答：检测很慢怎么办？",
        "股票池越大、区间越长，耗时越明显。\n"
        "建议：先用较小股票池 + 近 3 月试跑确认逻辑，再扩到近 1 年/近 3 年；一次只加必要图表需求。",
        None,
    ),
    (
        "qa",
        "问答：自定义因子试算失败常见原因",
        "常见情况：表达式语法错误、引用了不存在的字段、窗口过长导致有效样本过少。\n"
        "排查顺序：先看报错原文 → 缩小窗口 → 换已知可用字段（如 close/volume）做最小可运行例子。",
        None,
    ),
    (
        "hotspot",
        "热点：如何用事件窗口观察主题扩散",
        "遇到政策或产业链催化时，可把相关标的做成观察池，看事件前后 excess return 与成交放大是否同步。\n"
        "社区讨论建议写清：事件时点、观察池口径、对比基准，避免只贴情绪结论。",
        None,
    ),
    (
        "hotspot",
        "热点：成长风格回暖时关注哪些因子表现",
        "风格切换阶段，动量、成长类因子与价值类因子常出现相对强弱变化。\n"
        "可对比同一区间下不同因子的分层与回撤，记录「哪些因子更贴当前风格」，而不是追单日涨幅。",
        None,
    ),
]


def refresh_demo_feed() -> dict[str, Any]:
    """下架乱码测试帖，并保证每分区至少 2 条示例内容。"""
    hidden = 0
    inserted = 0
    with get_conn() as conn:
        admin = conn.execute(
            "SELECT id FROM users WHERE username = %s LIMIT 1",
            ("admin",),
        ).fetchone()
        if not admin:
            raise RuntimeError("缺少 admin 用户，无法写入示例帖")
        aid = int(admin["id"])
        # 下架明显乱码/占位帖
        rows = conn.execute(
            "SELECT id, title, body FROM posts WHERE status = 'published'"
        ).fetchall()
        for r in rows:
            title = (r["title"] or "").strip()
            body = (r["body"] or "").strip()
            bad = (
                not title
                or set(title.replace(" ", "")) <= {"?", "？", ".", "。", "!"}
                or title.count("?") + title.count("？") >= max(3, len(title) // 2)
                or (len(body) <= 8 and ("?" in body or "？" in body))
            )
            if bad:
                conn.execute(
                    "UPDATE posts SET status = 'hidden', updated_at = NOW() WHERE id = %s",
                    (r["id"],),
                )
                hidden += 1
        for section, title, body, code in _CURATED:
            exists = conn.execute(
                "SELECT id FROM posts WHERE title = %s AND status = 'published' LIMIT 1",
                (title,),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO posts (author_id, section, title, body, code_snippet, status)
                VALUES (%s, %s, %s, %s, %s, 'published')
                """,
                (aid, section, title, body, code),
            )
            inserted += 1
    return {"ok": True, "hidden": hidden, "inserted": inserted}
