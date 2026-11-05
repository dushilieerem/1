"""F0 constrained next-step runner.

One run executes at most one authorised development test on the selected branch.
Budget, locked view, branch ownership and idempotency are enforced server-side.
F0 never approves, seals or changes gates; those stay human/F5 actions.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from services.core.db import get_conn
from services.workflow_workspace.platform_data import published_view

from . import ledger, service
from .policy import WorkflowError

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quant-factor-f0")
ACTIVE = ("queued", "running")


def _public(row) -> dict:
    return {key: value for key, value in dict(row).items() if key not in ("user_id", "org_id")}


def _topic(uid, org, topic_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s",
            (topic_id, uid, org)).fetchone()
    if not row:
        raise KeyError(topic_id)
    return dict(row)


def _record(uid, org, topic, branch_id, key, status, decision=None, reason="", rounds=0):
    run_id = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO quant_factor_f0_runs
               (id,user_id,org_id,project_id,topic_id,branch_id,idempotency_key,status,
                decision,rounds,stop_reason,view_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (run_id, uid, org, topic["project_id"], topic["id"], branch_id, key, status,
             service.store.encode(decision or {}), rounds, reason, topic["view_id"]))
        row = c.execute("SELECT * FROM quant_factor_f0_runs WHERE id=%s", (run_id,)).fetchone()
    return dict(row)


def start(uid, org, topic_id, branch_id, idempotency_key):
    key = str(idempotency_key or "").strip()
    if not 1 <= len(key) <= 100:
        raise WorkflowError("请提供 1—100 字符的幂等键")
    topic = _topic(uid, org, topic_id)
    with get_conn() as c:
        branch = c.execute(
            "SELECT * FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s",
            (branch_id, uid, org, topic_id)).fetchone()
        if not branch:
            raise KeyError(branch_id)
        existing = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND idempotency_key=%s",
            (uid, org, topic_id, key)).fetchone()
    if existing:
        return _public(existing)
    if topic["status"] != "active":
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "topic_" + topic["status"]},
                               "课题处于暂停/归档状态，F0 不再调度"))
    if topic["view_id"] != published_view()["view_id"]:
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "locked_view_drift"},
                               "课题锁定视图与当前发布视图不一致，F0 停止"))
    with get_conn() as c:
        used = c.execute("SELECT COUNT(*) AS n FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s",
                         (uid, org, topic["project_id"])).fetchone()["n"]
    remaining = int(topic["max_trials"]) - int(used)
    if remaining <= 0:
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "budget_exhausted"},
                               "课题试验预算已用尽，F0 停止"))
    trials = ledger._trials(uid, org, topic_id)
    latest = trials[-1] if trials else None
    if latest and latest.get("outcome") == "passed":
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "development_passed"},
                               "研发已通过，超出 F0 授权：等待人工复核/封存，不自动提交", rounds=0))
    decision = {"action": "run_development_test", "round": 1,
                "source_branch": branch["source"], "remaining_budget": remaining}
    if latest and latest.get("outcome") in ("failed", "error"):
        with get_conn() as c:
            child = c.execute(
                "SELECT id FROM quant_factor_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s AND parent_id=%s AND source='agent'",
                (uid, org, topic_id, branch_id)).fetchone()
        if child:
            return _public(_record(uid, org, topic, branch_id, key, "stopped",
                                   {"action": "stop", "reason": "derive_already_exists"},
                                   "失败后已派生分支，等待人工确认修订或换方向", rounds=0))
        decision = {"action": "derive_branch", "from_trial": latest["trial_no"],
                    "from_outcome": latest["outcome"], "source_branch": branch["source"],
                    "remaining_budget": remaining}
    row = _record(uid, org, topic, branch_id, key, "queued", decision)
    POOL.submit(run, uid, org, row["id"])
    return _public(row)


def run(uid, org, run_id):
    try:
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s",
                (run_id, uid, org)).fetchone()
            if not row or row["status"] not in ACTIVE:
                return
            c.execute("UPDATE quant_factor_f0_runs SET status='running',updated_at=NOW() WHERE id=%s", (run_id,))
        decision = row["decision"] or {}
        if decision.get("action") == "derive_branch":
            with get_conn() as c:
                parent = c.execute(
                    "SELECT * FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s",
                    (row["branch_id"], uid, org)).fetchone()
                child_id = str(uuid.uuid4())
                c.execute(
                    """INSERT INTO quant_factor_branches
                       (id,user_id,org_id,topic_id,parent_id,source,owner_id,hypothesis_version,implementation_version)
                       VALUES (%s,%s,%s,%s,%s,'agent',%s,%s,%s)""",
                    (child_id, uid, org, row["topic_id"], row["branch_id"], uid,
                     int(parent["hypothesis_version"]) + 1, int(parent["implementation_version"]) + 1))
                c.execute(
                    "UPDATE quant_factor_f0_runs SET status='completed',rounds=1,decision=decision||%s::jsonb,updated_at=NOW() WHERE id=%s AND status='running'",
                    (service.store.encode({"branch_id": child_id}), run_id))
            return
        candidate = service.create(uid, org, row["project_id"])
        deadline = time.monotonic() + 2400
        while candidate["status"].endswith("_running") and time.monotonic() < deadline:
            time.sleep(2)
            candidate = service.current(uid, org, candidate["id"])
        if candidate["status"].endswith("_running"):
            raise WorkflowError("研发检验超时，F0 停止")
        with get_conn() as c:
            c.execute(
                """UPDATE quant_factor_f0_runs
                   SET status='completed',rounds=1,
                       decision=%s::jsonb,updated_at=NOW(),stop_reason=''
                   WHERE id=%s AND status='running'""",
                (service.store.encode({"action": "run_development_test",
                                       "candidate_id": candidate["id"],
                                       "candidate_status": candidate["status"]}), run_id))
    except Exception as exc:
        with get_conn() as c:
            c.execute(
                "UPDATE quant_factor_f0_runs SET status='stopped',stop_reason=%s,updated_at=NOW() WHERE id=%s AND status IN ('queued','running')",
                (str(exc)[:1000], run_id))


def read(uid, org, run_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s",
            (run_id, uid, org)).fetchone()
    if not row:
        raise KeyError(run_id)
    return _public(row)


__all__ = ["read", "run", "start"]
