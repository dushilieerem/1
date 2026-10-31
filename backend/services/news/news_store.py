# -*- coding: utf-8 -*-
"""资讯聚合：news_items 表 + 列表 API + 小样种子。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Json

from services.core.db import get_conn

VALID_CATEGORIES = frozenset(
    {"flash", "market", "announce", "research", "policy", "global"}
)
VALID_SOURCES = frozenset(
    {"cls", "eastmoney", "cninfo", "10jqka", "wallstreetcn", "bloomberg"}
)

# 三类视图 FIFO 上限：新入库后删最旧，超出部分淘汰
# 要闻流 = 全表；电报 = is_flash；公告 = category=announce
NEWS_CAP_FEED = 15_000
NEWS_CAP_FLASH = 10_000
NEWS_CAP_ANNOUNCE = 2_000

SOURCE_LABELS = {
    "cls": "财联社",
    "eastmoney": "东方财富",
    "em_research": "东方财富·研报",
    "em_policy": "东方财富·政策",
    "cninfo": "巨潮资讯",
    "10jqka": "同花顺",
    "wallstreetcn": "华尔街见闻",
    "bloomberg": "彭博社",
}


def ensure_news_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
              id              BIGSERIAL PRIMARY KEY,
              title           TEXT NOT NULL,
              summary         TEXT NOT NULL DEFAULT '',
              body            TEXT NOT NULL DEFAULT '',
              published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              source          TEXT NOT NULL,
              category        TEXT NOT NULL,
              url             TEXT NOT NULL DEFAULT '',
              symbols         JSONB NOT NULL DEFAULT '[]'::jsonb,
              themes          JSONB NOT NULL DEFAULT '[]'::jsonb,
              industries      JSONB NOT NULL DEFAULT '[]'::jsonb,
              raw_hash        TEXT NOT NULL,
              is_flash        BOOLEAN NOT NULL DEFAULT FALSE,
              is_featured     BOOLEAN NOT NULL DEFAULT FALSE,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT news_items_raw_hash_uq UNIQUE (raw_hash)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_published
              ON news_items (published_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_category_published
              ON news_items (category, published_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_source_published
              ON news_items (source, published_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_themes_gin
              ON news_items USING GIN (themes)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_symbols_gin
              ON news_items USING GIN (symbols)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_industries_gin
              ON news_items USING GIN (industries)
            """
        )


        # P1-C05：中文子串检索用 pg_trgm 加速 ILIKE；扩展不可用时忽略。
        try:
            with conn.transaction():
                conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                for name, col in (
                    ("idx_news_title_trgm", "title"),
                    ("idx_news_summary_trgm", "summary"),
                ):
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS {name} ON news_items USING gin ({col} gin_trgm_ops)"
                    )
        except Exception:
            pass

def _search_pattern(q: str | None) -> str | None:
    raw = (q or "").strip()
    if not raw:
        return None
    raw = raw[:80]
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _row_to_item(r: dict[str, Any]) -> dict[str, Any]:
    def _arr(v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str) and v.strip():
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                return []
        return []

    src = (r.get("source") or "").strip()
    pub = r.get("published_at")
    return {
        "id": int(r["id"]),
        "title": r.get("title") or "",
        "summary": r.get("summary") or "",
        "body": r.get("body") or "",
        "publishedAt": pub.isoformat() if hasattr(pub, "isoformat") else str(pub or ""),
        "source": src,
        "sourceLabel": SOURCE_LABELS.get(src, src),
        "category": r.get("category") or "",
        "url": r.get("url") or "",
        "symbols": _arr(r.get("symbols")),
        "themes": _arr(r.get("themes")),
        "industries": _arr(r.get("industries")),
        "isFlash": bool(r.get("is_flash")),
        "isFeatured": bool(r.get("is_featured")),
    }


def get_news(news_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM news_items WHERE id = %s",
            (int(news_id),),
        ).fetchone()
    if not row:
        raise KeyError(news_id)
    return {"ok": True, "item": _row_to_item(dict(row))}


def _parse_tag_list(
    raw: str | list[str] | None,
    *,
    max_n: int = 8,
    max_len: int = 40,
) -> list[str]:
    parts: list[str] = []
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        for x in raw:
            parts.extend(str(x).split(","))
    else:
        parts = str(raw).split(",")
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = p.strip()[:max_len]
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_n:
            break
    return out


def _all_jsonb_contains(col: str, tags: list[str], params: list[Any]) -> str:
    """标签筛选取交集：一篇资讯必须包含本维度的全部已选标签。"""
    if not tags:
        return ""
    params.append(json.dumps(tags, ensure_ascii=False))
    return f" AND {col} @> %s::jsonb"


def list_news(
    *,
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    mode: str | None = None,
    theme: str | list[str] | None = None,
    symbol: str | list[str] | None = None,
    industry: str | list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    try:
        ensure_news_within_caps()
    except Exception:
        pass
    params: list[Any] = []
    where = "WHERE 1=1"
    cat = (category or "").strip()
    if cat and cat != "all":
        if cat not in VALID_CATEGORIES:
            raise ValueError(f"无效分类: {category}")
        where += " AND category = %s"
        params.append(cat)
    src = (source or "").strip()
    if src and src != "all":
        if src not in VALID_SOURCES:
            raise ValueError(f"无效来源: {source}")
        where += " AND source = %s"
        params.append(src)
    m = (mode or "").strip().lower()
    if m == "flash":
        where += " AND is_flash = TRUE"
    elif m == "announce":
        where += " AND category = 'announce'"
    themes_f = _parse_tag_list(theme)
    symbols_f = _parse_tag_list(symbol, max_len=32)
    industries_f = _parse_tag_list(industry)
    where += _all_jsonb_contains("themes", themes_f, params)
    where += _all_jsonb_contains("symbols", symbols_f, params)
    where += _all_jsonb_contains("industries", industries_f, params)
    pattern = _search_pattern(q)
    if pattern:
        search_clauses = [
            "title ILIKE %s ESCAPE '\\' OR "
            "summary ILIKE %s ESCAPE '\\' OR "
            "COALESCE(body, '') ILIKE %s ESCAPE '\\'",
        ]
        params.extend([pattern, pattern, pattern])
        # 关联标的和题材可能只存在于结构化标签中，不能依赖它们碰巧出现在正文。
        # 按数组元素搜索，避免把 JSON 的引号、方括号当成用户可检索的内容。
        for col in ("symbols", "themes", "industries"):
            search_clauses.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                f"{col}) AS search_tag(value) "
                "WHERE search_tag.value ILIKE %s ESCAPE '\\')"
            )
            params.append(pattern)
        where += " AND (" + " OR ".join(search_clauses) + ")"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM news_items
            {where}
            ORDER BY is_featured DESC, published_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            params,
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM news_items {where}",
            params[:-2],
        ).fetchone()["c"]
    return {
        "ok": True,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "q": (q or "").strip()[:80] or None,
        "theme": themes_f or None,
        "symbol": symbols_f or None,
        "industry": industries_f or None,
        "items": [_row_to_item(dict(r)) for r in rows],
    }


def _seed_rows() -> list[dict[str, Any]]:
    """≥10 条；覆盖六源；时间相对「现在」便于排序。"""
    now = datetime.now(timezone(timedelta(hours=8)))

    def t(minutes_ago: int) -> datetime:
        return now - timedelta(minutes=minutes_ago)

    return [
        {
            "title": "创业板指涨超 5%，算力硬件股爆发，CPO / 元件领涨",
            "summary": "午后主要指数全线走强；光迅科技触及涨停，中际旭创、新易盛、天孚通信等光模块方向活跃。",
            "source": "cls",
            "category": "flash",
            "url": "https://www.cls.cn/",
            "symbols": ["300308.SZ", "300502.SZ"],
            "themes": ["CPO", "算力"],
            "published_at": t(20),
            "is_flash": True,
            "is_featured": True,
            "raw_hash": "seed:cls:cpo-rally",
        },
        {
            "title": "电子特气概念午后反弹，昊华科技触及涨停",
            "summary": "存储芯片耗材需求预期上修，气体与材料方向联动走强。",
            "source": "cls",
            "category": "flash",
            "url": "https://www.cls.cn/",
            "symbols": ["600378.SH"],
            "themes": ["电子特气"],
            "published_at": t(35),
            "is_flash": True,
            "is_featured": False,
            "raw_hash": "seed:cls:gas",
        },
        {
            "title": "药明康德上调全年业绩指引，CXO 板块景气持续验证",
            "summary": "公司上调收入指引区间，板块内相关标的跟涨。",
            "source": "eastmoney",
            "category": "research",
            "url": "https://www.eastmoney.com/",
            "symbols": ["603259.SH"],
            "themes": ["CRO"],
            "published_at": t(90),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:em:wuxi",
        },
        {
            "title": "东方财富：新能源行业周报摘要（演示）",
            "summary": "装机与排产数据跟踪；关注政策与盈利兑现节奏。",
            "source": "eastmoney",
            "category": "research",
            "url": "https://www.eastmoney.com/",
            "symbols": [],
            "themes": ["新能源"],
            "published_at": t(180),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:em:ne-week",
        },
        {
            "title": "厦门象屿：间接控股子公司租赁仓库起火事故的公告",
            "summary": "事故无人员伤亡，受损货物已投保；公司称不影响长期经营能力。",
            "source": "cninfo",
            "category": "announce",
            "url": "https://www.cninfo.com.cn/new/index.jsp",
            "symbols": ["600057.SH"],
            "themes": ["公告"],
            "published_at": t(55),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:cninfo:600057",
        },
        {
            "title": "江阴银行：关于副行长辞职的公告",
            "summary": "法定信披演示条目，代码与标题对齐巨潮风格。",
            "source": "cninfo",
            "category": "announce",
            "url": "https://www.cninfo.com.cn/new/index.jsp",
            "symbols": ["002807.SZ"],
            "themes": ["公告"],
            "published_at": t(200),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:cninfo:002807",
        },
        {
            "title": "同花顺热点：CPO / PCB / 算力租赁登上头条概念",
            "summary": "盘面题材轮动加快，光通信与算力硬件成为当日主线之一。",
            "source": "10jqka",
            "category": "market",
            "url": "https://www.10jqka.com.cn/",
            "symbols": ["002463.SZ"],
            "themes": ["CPO", "题材"],
            "published_at": t(70),
            "is_flash": True,
            "is_featured": False,
            "raw_hash": "seed:ths:cpo-hot",
        },
        {
            "title": "沪深京成交额超 1.5 万亿，较上日此时放量约 400 亿",
            "summary": "量能回升支撑题材扩散；预计全天成交或逼近 2 万亿。",
            "source": "10jqka",
            "category": "flash",
            "url": "https://www.10jqka.com.cn/",
            "symbols": [],
            "themes": ["量能"],
            "published_at": t(40),
            "is_flash": True,
            "is_featured": False,
            "raw_hash": "seed:ths:turnover",
        },
        {
            "title": "SK 海力士联手闪迪发布全球首个 HBF 标准，谷歌加入生态",
            "summary": "高带宽闪存标准规范落地，AI 存储叙事升温。",
            "source": "wallstreetcn",
            "category": "global",
            "url": "https://wallstreetcn.com/",
            "symbols": [],
            "themes": ["AI存储", "海外"],
            "published_at": t(60),
            "is_flash": False,
            "is_featured": True,
            "raw_hash": "seed:wscn:hbf",
        },
        {
            "title": "罕见干预操作：美日联手稳汇率，市场担忧套利交易逆转",
            "summary": "宏观流动性与汇率联动升温，风险资产情绪受扰动。",
            "source": "wallstreetcn",
            "category": "policy",
            "url": "https://wallstreetcn.com/",
            "symbols": [],
            "themes": ["宏观", "汇率"],
            "published_at": t(240),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:wscn:fx",
        },
        {
            "title": "Amazon tops $3 trillion as AWS demand outruns supply",
            "summary": "AWS 多年期合同与产能预订提振美股科技股风险偏好，对 A 股算力映射仍有外溢。",
            "source": "bloomberg",
            "category": "global",
            "url": "https://www.bloomberg.com/asia",
            "symbols": [],
            "themes": ["美股", "云计算"],
            "published_at": t(120),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:bbg:amzn",
        },
        {
            "title": "Fed officials signal caution on further rate cuts",
            "summary": "海外利率路径预期扰动全球风险偏好（演示摘要，原文见外链）。",
            "source": "bloomberg",
            "category": "policy",
            "url": "https://www.bloomberg.com/asia",
            "symbols": [],
            "themes": ["美联储", "海外"],
            "published_at": t(300),
            "is_flash": False,
            "is_featured": False,
            "raw_hash": "seed:bbg:fed",
        },
    ]


def seed_sample_news() -> int:
    """仅当库完全为空时写入演示小样；已有真源则不再种演示。"""
    from services.news.news_tag_dict import enrich_news_tags

    rows = _seed_rows()
    inserted = 0
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM news_items").fetchone()["c"]
        if int(n) > 0:
            return 0
        for row in rows:
            themes, industries = enrich_news_tags(
                title=row["title"],
                summary=row["summary"],
                themes=list(row.get("themes") or []),
            )
            cur = conn.execute(
                """
                INSERT INTO news_items (
                  title, summary, body, published_at, source, category, url,
                  symbols, themes, industries, raw_hash, is_flash, is_featured
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (raw_hash) DO NOTHING
                """,
                (
                    row["title"],
                    row["summary"],
                    row["summary"]
                    + "\n\n（站内演示正文）本条为 SVQuant 资讯小样；关联代码可跳转 K 线，源站链接仅作参考。",
                    row["published_at"],
                    row["source"],
                    row["category"],
                    row["url"],
                    Json(row["symbols"]),
                    Json(themes),
                    Json(industries),
                    row["raw_hash"],
                    row["is_flash"],
                    row["is_featured"],
                ),
            )
            if cur.rowcount:
                inserted += 1
    return inserted


def _prune_by_window(conn: Any, *, where_sql: str, cap: int) -> int:
    """按 published_at DESC, id DESC 保留最新 cap 条，删更旧的。where_sql 为空则全表。"""
    if cap <= 0:
        return 0
    filter_sql = f"WHERE {where_sql}" if where_sql.strip() else ""
    cur = conn.execute(
        f"""
        DELETE FROM news_items
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     ORDER BY published_at DESC NULLS LAST, id DESC
                   ) AS rn
            FROM news_items
            {filter_sql}
          ) ranked
          WHERE rn > %s
        )
        """,
        (int(cap),),
    )
    return int(cur.rowcount or 0)


def enforce_news_retention(
    *,
    cap_feed: int = NEWS_CAP_FEED,
    cap_flash: int = NEWS_CAP_FLASH,
    cap_announce: int = NEWS_CAP_ANNOUNCE,
) -> dict[str, int]:
    """
    FIFO 上限：入库后淘汰最旧。
    - 公告表 category=announce → cap_announce
    - 电报快讯 is_flash → cap_flash
    - 要闻流（全表）→ cap_feed
    顺序：先裁分桶，再裁全表，避免全表先砍误伤分桶配额。
    """
    with get_conn() as conn:
        pruned_announce = _prune_by_window(
            conn, where_sql="category = 'announce'", cap=cap_announce
        )
        pruned_flash = _prune_by_window(
            conn, where_sql="is_flash = TRUE", cap=cap_flash
        )
        pruned_feed = _prune_by_window(conn, where_sql="", cap=cap_feed)
    return {
        "prunedAnnounce": pruned_announce,
        "prunedFlash": pruned_flash,
        "prunedFeed": pruned_feed,
        "capFeed": int(cap_feed),
        "capFlash": int(cap_flash),
        "capAnnounce": int(cap_announce),
    }


def ensure_news_within_caps() -> dict[str, int] | None:
    """超限才裁剪；列表/写入前可调用，避免 UI 短暂显示超上限。"""
    with get_conn() as conn:
        feed = int(
            conn.execute("SELECT COUNT(*) AS n FROM news_items").fetchone()["n"]
        )
        flash = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM news_items WHERE is_flash = TRUE"
            ).fetchone()["n"]
        )
        announce = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM news_items WHERE category = 'announce'"
            ).fetchone()["n"]
        )
    if (
        feed <= NEWS_CAP_FEED
        and flash <= NEWS_CAP_FLASH
        and announce <= NEWS_CAP_ANNOUNCE
    ):
        return None
    return enforce_news_retention()


# —— P1-C07：抓取健康（每次 ingest 留痕，管理端可看各源最近成功/失败）——


def ensure_ingest_runs_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_ingest_runs (
              id          BIGSERIAL PRIMARY KEY,
              finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              ok          BOOLEAN NOT NULL,
              fetched     INT NOT NULL DEFAULT 0,
              upserted    INT NOT NULL DEFAULT 0,
              sources     JSONB NOT NULL DEFAULT '{}'::jsonb,
              errors      JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_ingest_runs_finished "
            "ON news_ingest_runs (finished_at DESC)"
        )


def record_ingest_run(result: dict[str, Any]) -> None:
    """保存一次 ingest 结果（调度与手动触发都会走这里）。"""
    ensure_ingest_runs_schema()
    sources = result.get("sources") if isinstance(result.get("sources"), dict) else {}
    errors = result.get("errors") if isinstance(result.get("errors"), dict) else {}
    per_source_ok = all(bool(v.get("ok")) for v in sources.values()) if sources else False
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO news_ingest_runs (ok, fetched, upserted, sources, errors)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                per_source_ok,
                int(result.get("fetched") or 0),
                int(result.get("upserted") or 0),
                json.dumps(sources, ensure_ascii=False),
                json.dumps(errors, ensure_ascii=False),
            ),
        )


def ingest_health(limit: int = 20) -> dict[str, Any]:
    """最近 N 次抓取 + 各源最后状态；超过 2 个调度周期未跑则告警。"""
    from services.core.env_config import env

    ensure_ingest_runs_schema()
    limit = max(1, min(100, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, finished_at, ok, fetched, upserted, sources, errors
            FROM news_ingest_runs
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    per_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        sources = row.get("sources") or {}
        errors = row.get("errors") or {}
        if isinstance(sources, str):
            sources = json.loads(sources)
        if isinstance(errors, str):
            errors = json.loads(errors)
        for sid, info in sources.items():
            if sid in per_source:
                continue
            per_source[sid] = {
                "source": sid,
                "label": SOURCE_LABELS.get(sid, sid),
                "ok": bool((info or {}).get("ok")),
                "count": int((info or {}).get("count") or 0),
                "error": (info or {}).get("error") or errors.get(sid),
                "finished_at": row["finished_at"].isoformat(),
            }

    warnings: list[str] = []
    if not rows:
        warnings.append("尚无抓取记录")
        last_at = None
    else:
        last_at = rows[0]["finished_at"]
        try:
            interval = int(env("NEWS_INGEST_INTERVAL_SEC", "900") or "900")
        except (TypeError, ValueError):
            interval = 900
        if interval > 0:
            age = datetime.now(timezone.utc) - last_at.astimezone(timezone.utc)
            if age.total_seconds() > interval * 2:
                warnings.append(f"已 {round(age.total_seconds() / 60)} 分钟未抓取")
        failing = [k for k, v in per_source.items() if not v["ok"]]
        if failing:
            warnings.append("最近失败源：" + "、".join(failing))
    for sid in ("cls", "eastmoney", "cninfo", "10jqka", "wallstreetcn"):
        if sid not in per_source:
            warnings.append(f"{sid} 最近没有抓取记录")

    return {
        "ok": not warnings,
        "warnings": warnings,
        "last_finished_at": last_at.isoformat() if last_at else None,
        "runs": [
            {
                "id": int(r["id"]),
                "finished_at": r["finished_at"].isoformat(),
                "ok": bool(r["ok"]),
                "fetched": int(r["fetched"] or 0),
                "upserted": int(r["upserted"] or 0),
                "errors": r.get("errors") or {},
            }
            for r in rows
        ],
        "sources": [per_source[k] for k in sorted(per_source)],
    }
