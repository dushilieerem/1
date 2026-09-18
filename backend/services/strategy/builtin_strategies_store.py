# -*- coding: utf-8 -*-
"""内置策略库：Postgres 中的 ResearchEngine 目录镜像。

策略目录的运行时权威来源是 ResearchEngine 的 ``GET /api/strategies``。
``builtin_strategies.source`` 仅保留过渡期已有的源码快照，用于写入回测
记录的 request JSONB；内置策略实际执行时只提交 strategy_id 给 RE。

应用启动和管理员同步都不会再从 SVQuant 的 Strategy 目录读取策略。
"""
from __future__ import annotations

import json
from typing import Any

from services.core.db import get_conn
from services.core.re_http_gateway import forward_re

STRATEGY_TYPE_LABELS = {
    "trend": "趋势",
    "momentum": "动量",
    "reversal": "反转",
    "low_volatility": "低波动",
    "minimum_variance": "最小方差",
    "statistical_arbitrage": "统计套利",
    "value": "价值",
    "value_growth": "价值成长",
    "dividend": "红利",
    "dividend_growth": "红利增长",
    "breakout": "突破",
    "money_flow": "资金流",
    "multi_factor": "多因子",
    "price_action": "价格行为",
    "quality_value": "质量价值",
    "sentiment": "情绪",
    "volatility": "波动",
    "volume_trend": "量价趋势",
    "small_cap": "小市值",
    "custom": "自定义",
}


def ensure_builtin_strategies_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS builtin_strategies (
              id              TEXT PRIMARY KEY,
              name            TEXT NOT NULL,
              strategy_type   TEXT NOT NULL DEFAULT 'custom',
              execution_mode  TEXT NOT NULL DEFAULT 'vectorized',
              entrypoint      TEXT NOT NULL DEFAULT '',
              tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
              source          TEXT NOT NULL DEFAULT '',
              current_version TEXT NOT NULL DEFAULT '',
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # 旧库兼容：目录元数据来自 RE，但回测请求不发送该版本号。
        conn.execute(
            "ALTER TABLE builtin_strategies "
            "ADD COLUMN IF NOT EXISTS current_version TEXT NOT NULL DEFAULT ''"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_builtin_strategies_type "
            "ON builtin_strategies (strategy_type, name)"
        )


def _parse_tags(raw: Any) -> list[Any]:
    tags = raw or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = []
    return list(tags) if isinstance(tags, list) else []


def list_builtin_strategies_from_db() -> dict[str, Any]:
    """列表：不含大字段 source 正文；`source` 固定为 builtin 标记。"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, strategy_type, execution_mode, current_version,
                   entrypoint, tags
            FROM builtin_strategies
            ORDER BY strategy_type, name, id
            """
        ).fetchall()
    items: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        stype = str(row.get("strategy_type") or "custom")
        items.append(
            {
                "id": str(row["id"]),
                "name": str(row.get("name") or row["id"]),
                "strategy_type": stype,
                "strategy_type_label": STRATEGY_TYPE_LABELS.get(stype, stype),
                "execution_mode": str(row.get("execution_mode") or "vectorized"),
                "current_version": str(row.get("current_version") or ""),
                "entrypoint": str(row.get("entrypoint") or ""),
                "tags": _parse_tags(row.get("tags")),
                "file": "",
                "source": "builtin",
            }
        )
    return {
        "ok": True,
        "total": len(items),
        "items": items,
    }


def get_builtin_strategy(strategy_id: str) -> dict[str, Any]:
    """内部详情含过渡期源码快照：``strategy_code``。"""
    sid = (strategy_id or "").strip()
    if not sid:
        raise ValueError("strategy_id 不能为空")
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, strategy_type, execution_mode, current_version,
                   entrypoint, tags, source
            FROM builtin_strategies
            WHERE id = %s
            """,
            (sid,),
        ).fetchone()
    if not row:
        raise KeyError(f"未知策略: {sid}")
    d = dict(row)
    stype = str(d.get("strategy_type") or "custom")
    code = str(d.get("source") or "")
    return {
        "ok": True,
        "id": str(d["id"]),
        "name": str(d.get("name") or d["id"]),
        "strategy_type": stype,
        "strategy_type_label": STRATEGY_TYPE_LABELS.get(stype, stype),
        "execution_mode": str(d.get("execution_mode") or "vectorized"),
        "current_version": str(d.get("current_version") or ""),
        "version": str(d.get("current_version") or ""),
        "entrypoint": str(d.get("entrypoint") or ""),
        "tags": _parse_tags(d.get("tags")),
        "file": "",
        "strategy_code": code,
        "source": "builtin",
    }


def sync_builtin_strategies_from_re() -> dict[str, Any]:
    """从 RE 拉取目录并原子替换本地镜像。

    RE 只提供目录元数据，因此匹配旧 ID 时保留已有的 source 快照；这
    个快照不用于执行，也不会在内置策略页面展示。RE 返回空目录或请求
    失败时，在删除旧镜像之前直接抛错，保证旧快照保持不变。
    """
    ensure_builtin_strategies_schema()
    status, _headers, data = forward_re("GET", "/api/strategies", timeout=60)
    if status < 200 or status >= 300:
        detail = data.get("detail") if isinstance(data, dict) else data
        detail = detail or (data.get("error") if isinstance(data, dict) else "")
        raise RuntimeError(f"ResearchEngine 策略目录请求失败 HTTP {status}: {detail}")
    if not isinstance(data, dict):
        raise ValueError("ResearchEngine 策略目录响应格式无效")
    raw_items = data.get("strategies")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("ResearchEngine 策略目录为空，保留旧目录")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("ResearchEngine 策略目录包含无效条目")
        sid = str(item.get("id") or "").strip()
        if not sid:
            raise ValueError("ResearchEngine 策略目录条目缺少 id")
        if sid in seen:
            raise ValueError(f"ResearchEngine 策略目录存在重复 id: {sid}")
        seen.add(sid)
        rows.append(
            {
                "id": sid,
                "name": str(item.get("name") or sid),
                "strategy_type": str(item.get("strategy_type") or "custom"),
                "execution_mode": str(item.get("execution_mode") or "vectorized"),
                "current_version": str(item.get("current_version") or ""),
                "entrypoint": str(item.get("entrypoint") or ""),
                "tags": _parse_tags(item.get("tags")),
            }
        )

    with get_conn() as conn:
        old_rows = conn.execute(
            "SELECT id, source FROM builtin_strategies"
        ).fetchall()
        old_sources = {
            str(row["id"]): str(row.get("source") or "") for row in old_rows
        }
        # get_conn() 提交/回滚整个事务；任何一条写入失败都会回滚 DELETE。
        conn.execute("DELETE FROM builtin_strategies")
        for row in rows:
            conn.execute(
                """
                INSERT INTO builtin_strategies (
                  id, name, strategy_type, execution_mode, current_version,
                  entrypoint, tags, source, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW()
                )
                """,
                (
                    row["id"],
                    row["name"],
                    row["strategy_type"],
                    row["execution_mode"],
                    row["current_version"],
                    row["entrypoint"],
                    json.dumps(row["tags"], ensure_ascii=False),
                    old_sources.get(row["id"], ""),
                ),
            )

    return {
        "ok": True,
        "source": "research-engine",
        "upserted": len(rows),
        "total": len(rows),
        "skipped": [],
    }
