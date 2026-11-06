"""M5 read-only data resources: catalogue, view lineage, quality and requests."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.core.db import get_conn

DATA_HOME = Path(os.environ.get("SVQUANT_DATA_HOME") or "/home/dev01/project/svquant-data")

KNOWN_LIMITS = {
    "industry_membership_history": ["申万官方生效日 + 当前 vintage，可能被后续修订覆盖，不是无修订 PIT"],
    "industry_daily": ["latest_only；历史回测不要使用"],
    "index_membership": ["000300/000905 有历史权重；399317/399101/399303 仅最新快照；399303 confidence=medium；000015 仅 2026-09-30 起锚点"],
    "valuation_daily": ["pe_ttm 有前视；回测用 pe_ttm_pit；2026-10-08 后 carry-forward；total_mv 为真总市值"],
    "fund_flow_daily": ["东财口径；close/change_pct 为观察日回溯复权，不能算收益"],
    "fund_flow_candidate": ["东财口径；close/change_pct 为观察日回溯复权，不能算收益"],
    "analyst_consensus_snapshot": ["仅当前快照（forward-only），没有历史"],
    "us_fundamentals_sec": ["单位混用；跨公司比较需过滤 unit='USD'"],
}


def _read_json(rel: str):
    path = (DATA_HOME / rel).resolve()
    if not str(path).startswith(str(DATA_HOME.resolve())):
        raise ValueError("数据目录越界")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _current_view():
    link = DATA_HOME / "views" / "current"
    target = Path(os.path.realpath(link))
    view_id = target.parent.name if target.name == "materialized" else target.name
    return view_id, target


def catalogue(uid: int, org: int):
    monitor = _read_json("docs/monitor-data.json")
    view_id, _ = _current_view()
    try:
        quality = _read_json(f"ops/quality/{view_id}.json")
    except (FileNotFoundError, ValueError):
        quality = {"view_id": view_id, "datasets": {}, "ok": None}
    with get_conn() as c:
        factor_locked = c.execute(
            "SELECT COUNT(*) AS n FROM quant_factor_topics WHERE org_id=%s AND view_id=%s", (org, view_id)).fetchone()["n"]
        strategy_locked = c.execute(
            "SELECT COUNT(*) AS n FROM strategy_topics WHERE org_id=%s AND view_id=%s", (org, view_id)).fetchone()["n"]
    datasets = []
    for item in monitor.get("datasets") or []:
        name = item.get("name")
        q = (quality.get("datasets") or {}).get(name) or {}
        datasets.append({
            "name": name, "label": item.get("label"), "topic": item.get("topic"),
            "source": item.get("source"), "provenance": item.get("provenance"),
            "description": item.get("desc"), "rows": item.get("rows"),
            "start": item.get("start"), "end": item.get("end"), "updated": item.get("updated"),
            "field_count": item.get("field_count"),
            "quality_ok": q.get("ok"), "quality_checks": q.get("results") or [],
            "limitations": KNOWN_LIMITS.get(name, []),
        })
    return {
        "view_id": view_id, "generated_at": monitor.get("generated_at"),
        "summary": monitor.get("summary"), "quality_checked_at": quality.get("checked_at"),
        "quality_ok": quality.get("ok"),
        "locked_by": {"factor_topics": factor_locked, "strategy_topics": strategy_locked},
        "datasets": datasets,
    }


def dataset(uid: int, org: int, name: str):
    monitor = _read_json("docs/monitor-data.json")
    item = next((x for x in monitor.get("datasets") or [] if x.get("name") == name), None)
    if not item:
        raise KeyError(name)
    view_id, _ = _current_view()
    quality = {}
    try:
        quality = (_read_json(f"ops/quality/{view_id}.json").get("datasets") or {}).get(name) or {}
    except (FileNotFoundError, ValueError):
        pass
    return {
        "view_id": view_id, "name": name, "label": item.get("label"), "topic": item.get("topic"),
        "source": item.get("source"), "provenance": item.get("provenance"),
        "description": item.get("desc"), "rows": item.get("rows"),
        "start": item.get("start"), "end": item.get("end"), "updated": item.get("updated"),
        "fields": item.get("fields") or [],
        "quality_ok": quality.get("ok"), "quality_checks": quality.get("results") or [],
        "limitations": KNOWN_LIMITS.get(name, []),
    }


def views(uid: int, org: int):
    current, _ = _current_view()
    rows = []
    for path in sorted((DATA_HOME / "views").glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True):
        vid = path.stem
        rows.append({
            "view_id": vid, "current": vid == current,
            "published_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return {"current": current, "views": rows}


def list_requests(uid: int, org: int):
    with get_conn() as c:
        rows = c.execute(
            """SELECT id,title,purpose,period,fields,status,note,created_at,updated_at
               FROM quant_data_requests WHERE org_id=%s ORDER BY created_at DESC""", (org,)).fetchall()
    return [dict(r) for r in rows]


def submit_request(uid: int, org: int, payload: dict):
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("请填写需要的数据")
    rid = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO quant_data_requests(id,user_id,org_id,title,purpose,period,fields,status,note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'submitted','已记录；由开发同步数据业务处理')""",
            (rid, uid, org, title[:300], str(payload.get("purpose") or "")[:100],
             str(payload.get("period") or "")[:200], str(payload.get("fields") or "")[:2000]))
        row = c.execute("SELECT * FROM quant_data_requests WHERE id=%s", (rid,)).fetchone()
    return {k: v for k, v in dict(row).items() if k not in ("user_id", "org_id")}


__all__ = ["catalogue", "dataset", "list_requests", "submit_request", "views"]
