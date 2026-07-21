# -*- coding: utf-8 -*-
"""社区：帖子 + 评论 + 收藏。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from services.db import get_conn

SECTIONS = ("strategy", "factor", "qa", "hotspot", "official")
SECTION_LABELS = {
    "strategy": "策略分享",
    "factor": "因子笔记",
    "qa": "问答",
    "hotspot": "热点分析",
    "official": "官方",
}


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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_post_comments_post ON post_comments (post_id, created_at ASC)"
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


def _iso(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def _row_to_post(row: dict[str, Any], *, favorited: bool | None = None) -> dict[str, Any]:
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
        "status": row.get("status") or "published",
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "author": {
            "id": row.get("author_id"),
            "username": row.get("username"),
            "display_name": row.get("display_name") or row.get("username"),
        },
    }
    if favorited is not None:
        out["favorited"] = favorited
    return out


def _row_to_comment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "post_id": row["post_id"],
        "body": row["body"],
        "created_at": _iso(row.get("created_at")),
        "author": {
            "id": row.get("author_id"),
            "username": row.get("username"),
            "display_name": row.get("display_name") or row.get("username"),
        },
    }


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
    SELECT p.*, u.username, u.display_name,
           COALESCE(cc.cnt, 0) AS comment_count,
           COALESCE(fc.cnt, 0) AS favorite_count
    FROM posts p
    JOIN users u ON u.id = p.author_id
    LEFT JOIN (
      SELECT post_id, COUNT(*) AS cnt FROM post_comments
      WHERE status = 'published' GROUP BY post_id
    ) cc ON cc.post_id = p.id
    LEFT JOIN (
      SELECT post_id, COUNT(*) AS cnt FROM post_favorites GROUP BY post_id
    ) fc ON fc.post_id = p.id
"""


def list_posts(
    *,
    section: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    params: list[Any] = []
    where = "WHERE p.status = 'published'"
    if section and section != "all":
        if section not in SECTIONS:
            raise ValueError(f"无效分区: {section}")
        where += " AND p.section = %s"
        params.append(section)
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            {where}
            ORDER BY p.created_at DESC
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
        "sections": [{"id": k, "label": v} for k, v in SECTION_LABELS.items()],
        "items": [_row_to_post(dict(r)) for r in rows],
    }


def list_hot_posts(*, limit: int = 10) -> dict[str, Any]:
    limit = max(1, min(30, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.status = 'published'
            ORDER BY p.view_count DESC, p.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"ok": True, "items": [_row_to_post(dict(r)) for r in rows]}


def get_post(
    post_id: int,
    *,
    bump_view: bool = True,
    viewer_id: int | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        if bump_view:
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
            WHERE p.id = %s AND p.status = 'published'
            """,
            (post_id,),
        ).fetchone()
        favorited = None
        if viewer_id is not None and row:
            fav = conn.execute(
                """
                SELECT 1 FROM post_favorites
                WHERE user_id = %s AND post_id = %s
                """,
                (viewer_id, post_id),
            ).fetchone()
            favorited = fav is not None
    if not row:
        raise KeyError(f"post not found: {post_id}")
    return {"ok": True, "post": _row_to_post(dict(row), favorited=favorited)}


def create_post(
    author_id: int,
    *,
    title: str,
    body: str,
    section: str,
    code_snippet: str | None = None,
    author_role: str = "user",
) -> dict[str, Any]:
    title = (title or "").strip()
    body = (body or "").strip()
    section = (section or "").strip()
    code = (code_snippet or "").strip() or None
    if not title:
        raise ValueError("标题不能为空")
    if len(title) > 120:
        raise ValueError("标题过长（最多 120 字）")
    if section not in SECTIONS:
        raise ValueError(f"无效分区，可选: {', '.join(SECTIONS)}")
    if section == "official" and author_role != "admin":
        raise ValueError("仅管理员可发布官方内容")
    if not body and not code:
        raise ValueError("正文与代码不能同时为空")
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO posts (author_id, section, title, body, code_snippet, status)
            VALUES (%s, %s, %s, %s, %s, 'published')
            RETURNING id
            """,
            (author_id, section, title, body, code),
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


def list_comments(post_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM posts WHERE id = %s AND status = 'published'",
            (post_id,),
        ).fetchone()
        if not exists:
            raise KeyError(f"post not found: {post_id}")
        rows = conn.execute(
            """
            SELECT c.*, u.username, u.display_name
            FROM post_comments c
            JOIN users u ON u.id = c.author_id
            WHERE c.post_id = %s AND c.status = 'published'
            ORDER BY c.created_at ASC
            """,
            (post_id,),
        ).fetchall()
    items = [_row_to_comment(dict(r)) for r in rows]
    return {"ok": True, "total": len(items), "items": items}


def create_comment(post_id: int, author_id: int, body: str) -> dict[str, Any]:
    body = (body or "").strip()
    if not body:
        raise ValueError("评论不能为空")
    if len(body) > 2000:
        raise ValueError("评论过长（最多 2000 字）")
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM posts WHERE id = %s AND status = 'published'",
            (post_id,),
        ).fetchone()
        if not exists:
            raise KeyError(f"post not found: {post_id}")
        row = conn.execute(
            """
            INSERT INTO post_comments (post_id, author_id, body, status)
            VALUES (%s, %s, %s, 'published')
            RETURNING id
            """,
            (post_id, author_id, body),
        ).fetchone()
        full = conn.execute(
            """
            SELECT c.*, u.username, u.display_name
            FROM post_comments c
            JOIN users u ON u.id = c.author_id
            WHERE c.id = %s
            """,
            (row["id"],),
        ).fetchone()
    return {"ok": True, "comment": _row_to_comment(dict(full))}


def add_favorite(user_id: int, post_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM posts WHERE id = %s AND status = 'published'",
            (post_id,),
        ).fetchone()
        if not exists:
            raise KeyError(f"post not found: {post_id}")
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


def list_my_posts(user_id: int, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS c FROM posts
            WHERE author_id = %s AND status = 'published'
            """,
            (user_id,),
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            {_POST_SELECT}
            WHERE p.author_id = %s AND p.status = 'published'
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "total": int(total),
        "items": [_row_to_post(dict(r)) for r in rows],
    }


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
