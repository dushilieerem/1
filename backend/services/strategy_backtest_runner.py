"""Run one frozen strategy recipe against RE and append a strategy trial."""
from __future__ import annotations

import hashlib
import json
import os
import uuid

from services.core.db import get_conn
from services.core.lan_http import request_json
from services.core.re_config import RE_BASE
from services.workflow_workspace.platform_data import published_view

from . import strategy_backtest, strategy_gates, strategy_research


def _base():
    return (os.environ.get("STRATEGY_RE_BASE") or RE_BASE).rstrip("/")


def _payload(topic, branch):
    recipe = branch["recipe"]
    factors = recipe.get("factors") or []
    if any(f.get("code") for f in factors):
        body = {"strategy_code": strategy_backtest.build_code(recipe)}
    else:
        body = {"factor_refs": [{"library": f.get("library") or "主因子库",
                                 "factor": f.get("factor"),
                                 "direction": f.get("direction", "positive")} for f in factors]}
    body.update({
        "engine_mode": "vectorized", "universe": topic["universe"], "benchmark": topic["benchmark"],
        "start": str(topic["development_start"]), "end": str(topic["development_end"]),
        "top_n": int(recipe["top_n"]), "rebalance_days": int(recipe["rebalance_days"]),
        "commission_rate": float(topic["cost_bps"]) / 10000.0,
        "stamp_tax": 0.0, "slippage_rate": 0.0, "initial_capital": 1000000,
        "include_positions": False, "include_rebalance_logs": False,
        "execution_timing": "next_open", "filter_limit_up": True, "filter_suspended": True,
    })
    return body


def run_trial(uid, org, branch_id):
    with get_conn() as c:
        branch = c.execute(
            "SELECT * FROM strategy_branches WHERE id=%s AND user_id=%s AND org_id=%s",
            (branch_id, uid, org)).fetchone()
        if not branch:
            raise KeyError(branch_id)
        topic = c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",
                          (branch["topic_id"], uid, org)).fetchone()
    branch, topic = dict(branch), dict(topic)
    if topic["view_id"] != published_view()["view_id"]:
        raise ValueError("课题锁定视图与当前发布视图不一致")
    with get_conn() as c:
        existing = [dict(r) for r in c.execute(
            "SELECT * FROM strategy_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no",
            (uid, org, topic["id"])).fetchall()]
    prior = next((t for t in reversed(existing)
                  if t["branch_id"] == branch_id
                  and t["implementation_hash"] == branch["implementation_hash"]
                  and t["view_id"] == topic["view_id"]), None)
    trial_no = max((int(t["trial_no"]) for t in existing), default=0) + 1
    if prior:
        trial_id = str(uuid.uuid4())
        with get_conn() as c:
            c.execute(
                """INSERT INTO strategy_trials
                   (id,user_id,org_id,topic_id,branch_id,trial_no,recipe,implementation_hash,outcome,
                    metrics,gate,report_id,rerun_of,view_id,release_ids,view_manifest_sha256,contract_revision,as_of,report)
                   VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'rerun',%s::jsonb,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)""",
                (trial_id, uid, org, topic["id"], branch_id, trial_no,
                 json.dumps(branch["recipe"], ensure_ascii=False), branch["implementation_hash"],
                 json.dumps(prior["metrics"], ensure_ascii=False), json.dumps(prior["gate"], ensure_ascii=False),
                 prior["report_id"], prior["id"], topic["view_id"],
                 json.dumps(topic["release_ids"], ensure_ascii=False),
                 topic["view_manifest_sha256"], topic["contract_revision"], topic["as_of"],
                 json.dumps(prior.get("report") or {}, ensure_ascii=False)))
        return {"trial_id": trial_id, "trial_no": trial_no, "outcome": "rerun",
                "metrics": prior["metrics"], "gate": prior["gate"], "report_id": prior["report_id"],
                "rerun_of": prior["id"]}
    k = sum(1 for t in existing if t["outcome"] in ("passed", "failed") or
            (t["outcome"] in ("error", "timeout") and t["metrics"]))
    if k >= int(topic["max_trials"]):
        raise ValueError("策略课题 K 已达预算")
    payload = _payload(topic, branch)
    status, _, data = request_json(_base() + "/api/backtest/strategy", method="POST",
                                   payload=payload, timeout=600)
    if status != 200 or not isinstance(data, dict) or data.get("error"):
        raise ValueError("策略回测失败：" + str((data or {}).get("error") or status)[:500])
    metrics = data.get("metrics") or {}
    # The trial being run will count, so the IR bar is the K after this test.
    gate = strategy_gates.evaluate(data, k + 1)
    any_failed = any(c["passed"] is False for c in gate["checks"])
    outcome = "passed" if gate["passed"] and gate["complete"] else "failed" if any_failed else "error"
    gate["policy_status"] = ("passed" if gate["passed"] and gate["complete"]
                             else "incomplete_pending_diagnostics" if not any_failed
                             else "failed")
    trial_id = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO strategy_trials
               (id,user_id,org_id,topic_id,branch_id,trial_no,recipe,implementation_hash,outcome,
                metrics,gate,report_id,view_id,release_ids,view_manifest_sha256,contract_revision,as_of,report)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)""",
            (trial_id, uid, org, topic["id"], branch_id, trial_no,
             json.dumps(branch["recipe"], ensure_ascii=False), branch["implementation_hash"], outcome,
             json.dumps(metrics, ensure_ascii=False), json.dumps(gate, ensure_ascii=False),
             "strategy_" + trial_id, topic["view_id"], json.dumps(topic["release_ids"], ensure_ascii=False),
             topic["view_manifest_sha256"], topic["contract_revision"], topic["as_of"],
             json.dumps({k: data.get(k) for k in ("date_range", "equity_curve", "benchmark_curve",
                                                   "annual_returns", "assumptions", "final_equity") }
                        | {"period_excess": data.get("excess_return")}, ensure_ascii=False)))
    return {"trial_id": trial_id, "trial_no": trial_no, "outcome": outcome,
            "metrics": metrics, "gate": gate, "report_id": "strategy_" + trial_id,
            "meta": data.get("meta")}


__all__ = ["run_trial"]
