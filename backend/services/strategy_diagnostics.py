"""Robustness diagnostics (2x cost, 3x3 neighbourhood). Never advances K."""
from __future__ import annotations

import json
import uuid

from services.core.db import get_conn
from services.core.lan_http import request_json
from services.workflow_workspace.platform_data import published_view

from . import strategy_backtest_runner as runner
from . import strategy_gates, strategy_research


def _load(uid, org, branch_id):
    with get_conn() as c:
        branch = c.execute("SELECT * FROM strategy_branches WHERE id=%s AND user_id=%s AND org_id=%s",
                           (branch_id, uid, org)).fetchone()
        if not branch:
            raise KeyError(branch_id)
        topic = c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",
                          (branch["topic_id"], uid, org)).fetchone()
    branch, topic = dict(branch), dict(topic)
    if topic["view_id"] != published_view()["view_id"]:
        raise ValueError("课题锁定视图与当前发布视图不一致")
    return topic, branch


def _call(topic, branch, *, top_n=None, rebalance_days=None, double_cost=False):
    payload = runner._payload(topic, branch)
    if top_n is not None:
        payload["top_n"] = int(top_n)
    if rebalance_days is not None:
        payload["rebalance_days"] = int(rebalance_days)
    if double_cost:
        payload["commission_rate"] = float(payload.get("commission_rate") or 0) * 2
    status, _, data = request_json(runner._base() + "/api/backtest/strategy", method="POST",
                                   payload=payload, timeout=600)
    if status != 200 or not isinstance(data, dict) or data.get("error"):
        raise ValueError("策略诊断回测失败：" + str((data or {}).get("error") or status)[:300])
    return data


def _save(uid, org, topic, branch, kind, payload):
    did = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO strategy_diagnostics(id,user_id,org_id,topic_id,branch_id,kind,payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (did, uid, org, topic["id"], branch["id"], kind, json.dumps(payload, ensure_ascii=False)))
    return {"id": did, "kind": kind, **payload}


def cost_2x(uid, org, branch_id):
    topic, branch = _load(uid, org, branch_id)
    data = _call(topic, branch, double_cost=True)
    excess = data.get("excess_return")
    payload = {"excess": excess, "passed": isinstance(excess, (int, float)) and float(excess) > 0,
               "commission_rate": (runner._payload(topic, branch).get("commission_rate") or 0) * 2}
    return _save(uid, org, topic, branch, "cost_2x", payload)


def neighborhood(uid, org, branch_id):
    topic, branch = _load(uid, org, branch_id)
    rc = branch["recipe"]
    top = int(rc["top_n"])
    cells = []
    for n in (max(5, top - 20), top, min(300, top + 20)):
        for reb in (5, 10, 20):
            data = _call(topic, branch, top_n=n, rebalance_days=reb)
            derived = strategy_gates.metrics_from_result(data)
            excess = data.get("excess_return")
            ir = derived["ir"]
            passed = (isinstance(excess, (int, float)) and float(excess) >= strategy_gates.POLICY["neighborhood_excess"]
                      and ir is not None and ir >= strategy_gates.POLICY["neighborhood_ir"])
            cells.append({"top_n": n, "rebalance_days": reb, "excess": excess,
                          "ir": ir, "passed": bool(passed)})
    payload = {"cells": cells, "passed_cells": sum(1 for c in cells if c["passed"]),
               "required": strategy_gates.POLICY["neighborhood_cells"]}
    return _save(uid, org, topic, branch, "neighborhood", payload)


def latest(uid, org, branch_id):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT kind,payload,created_at FROM strategy_diagnostics
               WHERE user_id=%s AND org_id=%s AND branch_id=%s ORDER BY created_at DESC""",
            (uid, org, branch_id)).fetchall()]
    out = {}
    for r in rows:
        out.setdefault(r["kind"], r)
    return out


def merged_gate(trial, diagnostics):
    """Fill the two robustness checks from the newest diagnostics without rewriting the trial."""
    gate = dict(trial.get("gate") or {})
    if not gate.get("checks"):
        return gate
    checks = [dict(c) for c in gate["checks"]]
    by_name = {c.get("name"): c for c in checks}
    cost = diagnostics.get("cost_2x")
    if cost:
        c = by_name.get("2 倍成本下超额")
        if c:
            c["actual"] = cost["payload"].get("excess")
            c["passed"] = bool(cost["payload"].get("passed"))
    nb = diagnostics.get("neighborhood")
    if nb:
        c = by_name.get("参数邻域达标")
        if c:
            c["actual"] = nb["payload"].get("passed_cells")
            c["passed"] = int(nb["payload"].get("passed_cells") or 0) >= int(nb["payload"].get("required") or 6)
    pending = [c["name"] for c in checks if c.get("passed") is None]
    return {**gate, "checks": checks, "pending": pending,
            "complete": not pending, "passed": not pending and all(c["passed"] is True for c in checks)}


__all__ = ["cost_2x", "latest", "merged_gate", "neighborhood"]
