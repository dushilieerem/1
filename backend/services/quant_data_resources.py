"""M5 read-only data resources: catalogue, view lineage, quality and requests."""
from __future__ import annotations

import json
import os
import uuid

import yaml
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


FREQUENCY = {
    "minute_bars": "1 分钟",
    "daily_bars": "日频", "daily_bars_unadjusted": "日频", "ifind_daily_bars_unadjusted": "日频",
    "etf_daily": "日频", "us_stock_quotes_bfq": "日频", "us_stock_quotes_hfq": "日频",
    "valuation": "日频", "valuation_daily": "日频", "ifind_valuation": "日频",
    "index_price": "日频", "ifind_index_price": "日频", "index_weights": "日频",
    "ifind_index_weights": "日频", "index_membership": "日频（成分按公告）",
    "industry_daily": "日频", "industry_membership_history": "日频（历史生效日）",
    "security_status_daily": "日频", "limit_prices": "日频", "margin_daily": "日频",
    "fund_flow_daily": "日频", "fund_flow_candidate": "日频", "northbound_flow_daily": "日频",
    "northbound_holdings_quarterly": "季度", "risk_daily": "日频",
    "calendar": "日历", "us_stock_calendar": "日历", "ifind_calendar": "日历",
    "news": "日更", "us_stock": "快照", "us_stock_snapshot": "快照",
    "security_master": "快照", "ifind_security_master": "快照",
    "us_stock_universe": "快照", "universe": "快照",
    "analyst_consensus_snapshot": "快照",
    "financial_balance": "报告期/公告日", "financial_cashflow": "报告期/公告日",
    "financial_income": "报告期/公告日", "free_financial_income": "报告期/公告日",
    "per_share": "报告期/公告日", "pershare_index": "报告期/公告日",
    "holder_num": "报告期/公告日", "capital": "公告日", "dividend_actions": "公告日",
    "buyback_plan": "公告日", "buyback_execution": "公告日",
    "industry_code_map": "快照", "sector_concept": "快照",
    "us_fundamentals_sec": "报告期/公告日",
}


_VIEW_CACHE: dict[str, tuple[int, dict]] = {}


def _view_yaml(view_id: str) -> dict:
    for path in (DATA_HOME / "views").glob("*.yaml"):
        if path.stem != view_id:
            continue
        mtime = path.stat().st_mtime_ns
        cached = _VIEW_CACHE.get(view_id)
        if cached and cached[0] == mtime:
            return cached[1]
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        _VIEW_CACHE[view_id] = (mtime, data)
        return data
    return {}


def _pit_label(rule: str) -> str:
    rule = str(rule or "").strip()
    if rule == "date <= as_of":
        return "历史时点（date ≤ as_of）"
    if rule == "latest_only":
        return "仅最新快照"
    if "announce" in rule:
        return "按公告日"
    return rule or "待确认"


def _dataset_view_meta(view_id: str, name: str) -> dict:
    entry = (_view_yaml(view_id).get("datasets") or {}).get(name) or {}
    return {
        "published": bool(entry),
        "release": entry.get("release") or "",
        "pit_rule": entry.get("pit_rule") or "",
        "pit_label": _pit_label(entry.get("pit_rule")),
        "batch_created_at": entry.get("created_at") or "",
        "frequency": FREQUENCY.get(name, "待确认"),
    }


def _published_views() -> set[str]:
    return {path.stem for path in (DATA_HOME / "views").glob("*.yaml")}


def catalogue(uid: int, org: int, all_members: bool = False):
    monitor = _read_json("docs/monitor-data.json")
    view_id, _ = _current_view()
    try:
        quality = _read_json(f"ops/quality/{view_id}.json")
    except (FileNotFoundError, ValueError):
        quality = {"view_id": view_id, "datasets": {}, "ok": None}
    with get_conn() as c:
        factor_where, factor_params = "org_id=%s AND view_id=%s", [org, view_id]
        strategy_where, strategy_params = "org_id=%s AND view_id=%s", [org, view_id]
        if not all_members:
            factor_where += " AND user_id=%s"
            factor_params.append(uid)
            strategy_where += " AND user_id=%s"
            strategy_params.append(uid)
        factor_locked = c.execute(
            f"SELECT COUNT(*) AS n FROM quant_factor_topics WHERE {factor_where}",
            tuple(factor_params)).fetchone()["n"]
        strategy_locked = c.execute(
            f"SELECT COUNT(*) AS n FROM strategy_topics WHERE {strategy_where}",
            tuple(strategy_params)).fetchone()["n"]
    datasets = []
    for item in monitor.get("datasets") or []:
        name = item.get("name")
        q = (quality.get("datasets") or {}).get(name) or {}
        meta = _dataset_view_meta(view_id, name)
        datasets.append({
            "name": name, "label": item.get("label"), "topic": item.get("topic"),
            "source": item.get("source"), "provenance": item.get("provenance"),
            "description": item.get("desc"), "rows": item.get("rows"),
            "start": item.get("start"), "end": item.get("end"), "updated": item.get("updated"),
            "field_count": item.get("field_count"),
            **meta,
            "quality_ok": q.get("ok"), "quality_checks": q.get("results") or [],
            "limitations": KNOWN_LIMITS.get(name, []),
        })
    checked = sum(1 for d in datasets if d["quality_ok"] is not None)
    passed = sum(1 for d in datasets if d["quality_ok"] is True)
    failed = sum(1 for d in datasets if d["quality_ok"] is False)
    return {
        "view_id": view_id, "generated_at": monitor.get("generated_at"),
        "summary": monitor.get("summary"), "quality_checked_at": quality.get("checked_at"),
        "quality_ok": quality.get("ok"),
        "quality_summary": {"checked": checked, "passed": passed, "failed": failed,
                            "unchecked": len(datasets) - checked, "total": len(datasets)},
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
    meta = _dataset_view_meta(view_id, name)
    return {
        "view_id": view_id, "name": name, "label": item.get("label"), "topic": item.get("topic"),
        **meta,
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
        meta = _view_yaml(vid)
        rows.append({
            "view_id": vid, "current": vid == current,
            "published_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "created_at": meta.get("created_at") or "",
            "contract_version": meta.get("contract_version") or "",
            "dataset_count": len(meta.get("datasets") or {}),
        })
    return {"current": current, "views": rows}


def view_usage(uid: int, org: int, view_id: str, all_members: bool = False):
    if view_id not in _published_views():
        raise KeyError(view_id)
    factor_where, factor_params = "t.org_id=%s AND t.view_id=%s", [org, view_id]
    strategy_where, strategy_params = "org_id=%s AND view_id=%s", [org, view_id]
    if not all_members:
        factor_where += " AND t.user_id=%s"
        factor_params.append(uid)
        strategy_where += " AND user_id=%s"
        strategy_params.append(uid)
    with get_conn() as c:
        factors = [dict(r) for r in c.execute(
            f"""SELECT t.id,t.display_no,p.name AS project_name
               FROM quant_factor_topics t
               JOIN detect_projects p ON p.user_id=t.user_id AND p.id=t.project_id
               WHERE {factor_where}
               ORDER BY t.display_no""", tuple(factor_params)).fetchall()]
        strategies = [dict(r) for r in c.execute(
            f"""SELECT id,display_no,name FROM strategy_topics
               WHERE {strategy_where} ORDER BY display_no""",
            tuple(strategy_params)).fetchall()]
    return {
        "view_id": view_id,
        "factor_topics": [{"id": r["id"], "label": f"T{r['display_no']}", "name": r["project_name"]} for r in factors],
        "strategy_topics": [{"id": r["id"], "label": f"S{r['display_no']}", "name": r["name"]} for r in strategies],
    }


RELATED_TABLES = {
    "factor_topic": "quant_factor_topics",
    "strategy_topic": "strategy_topics",
    "portfolio_plan": "portfolio_plans",
}
TRANSITIONS = {
    "submitted": {"in_progress", "delivered", "unsupported"},
    "in_progress": {"delivered", "unsupported"},
    "delivered": set(),
    "unsupported": set(),
}


def _related(uid: int, org: int, related_type: str, related_id: str) -> bool:
    table = RELATED_TABLES.get(related_type)
    if not table or not related_id:
        return False
    with get_conn() as c:
        row = c.execute(
            f"SELECT 1 FROM {table} WHERE id=%s AND user_id=%s AND org_id=%s",
            (related_id, uid, org)).fetchone()
    return bool(row)


def list_requests(uid: int, org: int, all_members: bool = False):
    """Member-private by default; research managers see the whole org for handling."""
    where, params = "r.org_id=%s", [org]
    if not all_members:
        where += " AND r.user_id=%s"
        params.append(uid)
    with get_conn() as c:
        rows = c.execute(
            f"""SELECT r.id,r.title,r.purpose,r.period,r.frequency,r.fields,r.related_type,
                      r.related_id,r.delivered_view,r.status,r.note,r.handled_at,
                      r.created_at,r.updated_at,
                      COALESCE(fp.name, st.name, pp.name, '') AS related_name
               FROM quant_data_requests r
               LEFT JOIN quant_factor_topics ft
                 ON r.related_type='factor_topic' AND ft.id=r.related_id
                AND ft.user_id=r.user_id AND ft.org_id=r.org_id
               LEFT JOIN detect_projects fp
                 ON fp.user_id=ft.user_id AND fp.id=ft.project_id
               LEFT JOIN strategy_topics st
                 ON r.related_type='strategy_topic' AND st.id=r.related_id
                AND st.user_id=r.user_id AND st.org_id=r.org_id
               LEFT JOIN portfolio_plans pp
                 ON r.related_type='portfolio_plan' AND pp.id=r.related_id
                AND pp.user_id=r.user_id AND pp.org_id=r.org_id
               WHERE {where} ORDER BY r.created_at DESC""", tuple(params)).fetchall()
    return [dict(r) for r in rows]


def submit_request(uid: int, org: int, payload: dict):
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("请填写需要的数据")
    related_type = str(payload.get("related_type") or "").strip()
    related_id = str(payload.get("related_id") or "").strip()
    if related_type not in RELATED_TABLES:
        related_type, related_id = "", ""
    elif not related_id or not _related(uid, org, related_type, related_id):
        raise ValueError("关联对象不存在或不属于当前成员")
    rid = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO quant_data_requests
               (id,user_id,org_id,title,purpose,period,frequency,fields,related_type,related_id,status,note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'submitted','已记录；由数据业务处理并回填状态')""",
            (rid, uid, org, title[:300], str(payload.get("purpose") or "")[:100],
             str(payload.get("period") or "")[:200], str(payload.get("frequency") or "")[:100],
             str(payload.get("fields") or "")[:2000], related_type, related_id[:100]))
        row = c.execute("SELECT * FROM quant_data_requests WHERE id=%s", (rid,)).fetchone()
    return {k: v for k, v in dict(row).items() if k not in ("user_id", "org_id")}


def update_request(uid: int, org: int, req_id: str, payload: dict):
    status = str(payload.get("status") or "").strip()
    note = str(payload.get("note") or "").strip()
    delivered_view = str(payload.get("delivered_view") or "").strip()
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_data_requests WHERE id=%s AND org_id=%s FOR UPDATE",
            (req_id, org)).fetchone()
        if not row:
            raise KeyError(req_id)
        current = row["status"]
        if status not in TRANSITIONS:
            raise ValueError("状态只能是 in_progress / delivered / unsupported")
        if status not in TRANSITIONS[current]:
            raise ValueError(f"当前状态 {current} 不能改为 {status}")
        if status == "unsupported" and not note:
            raise ValueError("不予支持必须填写原因")
        if status == "delivered":
            if not delivered_view:
                raise ValueError("发布必须填写可用视图版本")
            if delivered_view not in _published_views():
                raise ValueError("交付视图不存在或未发布")
        c.execute(
            """UPDATE quant_data_requests
               SET status=%s,note=%s,delivered_view=%s,handled_by=%s,handled_at=NOW(),updated_at=NOW()
               WHERE id=%s AND org_id=%s""",
            (status, note[:2000], delivered_view[:100], uid, req_id, org))
        out = c.execute("SELECT * FROM quant_data_requests WHERE id=%s", (req_id,)).fetchone()
    return {k: v for k, v in dict(out).items() if k not in ("user_id", "org_id")}


__all__ = ["catalogue", "dataset", "list_requests", "submit_request", "update_request", "view_usage", "views"]
