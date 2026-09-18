# -*- coding: utf-8 -*-
"""内置策略库：存 Postgres（无 version 字段）。

权威来源可由 `Strategy/libraries/index.yaml` + 源码文件种子导入；
同事约定源码/目录落本机 PG，不依赖 RE 的按 id 取源码接口。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from services.core.db import get_conn

# backend/services/strategy → SVQuant/
_SVQUANT_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_LIB_DIR = _SVQUANT_ROOT / "Strategy" / "libraries"
INDEX_PATH = STRATEGY_LIB_DIR / "index.yaml"

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
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
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
            SELECT id, name, strategy_type, execution_mode, entrypoint, tags
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
                "entrypoint": str(row.get("entrypoint") or ""),
                "tags": _parse_tags(row.get("tags")),
                "file": "",
                "current_version": "",
                "source": "builtin",
            }
        )
    return {
        "ok": True,
        "total": len(items),
        "items": items,
    }


def get_builtin_strategy(strategy_id: str) -> dict[str, Any]:
    """详情含源码：`strategy_code`；无 version。"""
    sid = (strategy_id or "").strip()
    if not sid:
        raise ValueError("strategy_id 不能为空")
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, strategy_type, execution_mode, entrypoint, tags, source
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
        "entrypoint": str(d.get("entrypoint") or ""),
        "tags": _parse_tags(d.get("tags")),
        "file": "",
        "version": "",
        "strategy_code": code,
        "source": "builtin",
    }

def seed_builtin_strategies_from_yaml(*, replace: bool = True) -> dict[str, Any]:
    """从 Strategy/libraries/index.yaml + .py 写入 builtin_strategies（无 version）。"""
    ensure_builtin_strategies_schema()
    if not INDEX_PATH.is_file():
        raise FileNotFoundError(f"策略库索引不存在: {INDEX_PATH}")
    raw = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8")) or {}
    strategies = raw.get("strategies") or {}
    if not isinstance(strategies, dict):
        raise ValueError("index.yaml strategies 无效")

    upserted = 0
    skipped: list[str] = []
    with get_conn() as conn:
        if replace:
            conn.execute("DELETE FROM builtin_strategies")
        for sid, meta in strategies.items():
            if not isinstance(meta, dict):
                skipped.append(str(sid))
                continue
            cur = str(meta.get("current_version") or "v1")
            versions = meta.get("versions") or {}
            ver = versions.get(cur) if isinstance(versions, dict) else None
            if not isinstance(ver, dict):
                skipped.append(str(sid))
                continue
            file_name = str(ver.get("file") or "").strip()
            entrypoint = str(ver.get("entrypoint") or "")
            path = STRATEGY_LIB_DIR / file_name
            if not file_name or not path.is_file():
                skipped.append(str(sid))
                continue
            if not path.resolve().is_relative_to(STRATEGY_LIB_DIR.resolve()):
                skipped.append(str(sid))
                continue
            source = path.read_text(encoding="utf-8")
            stype = str(meta.get("strategy_type") or "custom")
            tags = list(meta.get("tags") or [])
            conn.execute(
                """
                INSERT INTO builtin_strategies (
                  id, name, strategy_type, execution_mode, entrypoint, tags, source, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s::jsonb, %s, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  strategy_type = EXCLUDED.strategy_type,
                  execution_mode = EXCLUDED.execution_mode,
                  entrypoint = EXCLUDED.entrypoint,
                  tags = EXCLUDED.tags,
                  source = EXCLUDED.source,
                  updated_at = NOW()
                """,
                (
                    str(sid),
                    str(meta.get("name") or sid),
                    stype,
                    str(meta.get("execution_mode") or "vectorized"),
                    entrypoint,
                    json.dumps(tags, ensure_ascii=False),
                    source,
                ),
            )
            upserted += 1

    return {
        "ok": True,
        "upserted": upserted,
        "skipped": skipped,
        "total": upserted,
    }
