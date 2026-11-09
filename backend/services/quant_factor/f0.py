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

from . import decision_engine, f0_agent, ledger, service
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
    # Serialize logical starts across HTTP workers, including different retry keys.
    # Keep this transaction open until the accepted run is durably recorded.
    with get_conn() as lock:
        lock.execute("SELECT pg_advisory_xact_lock(%s,%s)",(9106,uid))
        lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                     (f"quant-factor-start:{uid}:{org}:{topic_id}",))
        return _start_locked(uid, org, topic_id, branch_id, idempotency_key)


def _start_locked(uid, org, topic_id, branch_id, idempotency_key):
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
    with get_conn() as c:
        active = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
            (uid, org, topic_id)).fetchone()
    if active:
        return _public(active)
    if topic["status"] != "active":
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "topic_" + topic["status"]},
                               "课题处于暂停/归档状态，F0 不再调度"))
    if service.control_status(uid, org)["paused"]:
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "global_pause"},
                               "研究负责人已暂停全部：不启动新的自动研究动作"))
    if topic["view_id"] != published_view()["view_id"]:
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "locked_view_drift"},
                               "课题锁定视图与当前发布视图不一致，F0 停止"))
    k_now = ledger.current_k(ledger._trials(uid, org, topic_id), topic["primary_holding_period"])
    remaining = int(topic["max_trials"]) - k_now
    if remaining <= 0:
        return _public(_record(uid, org, topic, branch_id, key, "stopped",
                               {"action": "stop", "reason": "budget_exhausted"},
                               "课题试验预算已用尽，F0 停止"))
    row = _record(uid, org, topic, branch_id, key, "queued", {"action": "decide"})
    POOL.submit(run, uid, org, row["id"])
    return _public(row)


def run(uid, org, run_id):
    try:
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE",
                (run_id, uid, org)).fetchone()
            if not row or row["status"] != 'queued':
                return
            c.execute("UPDATE quant_factor_f0_runs SET status='running',updated_at=NOW() WHERE id=%s", (run_id,))
        topic = _topic(uid, org, row["topic_id"])
        steps = []
        current_steps = list((row.get("decision") or {}).get("steps") or [])
        def execute_step(decision, step):
            with get_conn() as c:
                c.execute("UPDATE quant_factor_f0_runs SET decision=%s::jsonb,updated_at=NOW() WHERE id=%s AND status='running'",
                          (service.store.encode({"steps": current_steps, "current_action": decision.action}), run_id))
            return f0_agent.execute(uid, org, run_id, topic, decision, step)

        def on_step(step, entry, current):
            nonlocal current_steps
            current_steps = list(current)
            with get_conn() as c:
                c.execute("UPDATE quant_factor_f0_runs SET rounds=%s,decision=%s::jsonb,updated_at=NOW() WHERE id=%s AND status='running'",
                          (step, service.store.encode({"steps": current}), run_id))

        # A reused frozen candidate can carry a completed test that never reached the ledger;
        # record it before deciding so K and the trial evidence are truthful.
        service.recover_pending(uid, org, topic["project_id"],recovery_only=bool((row.get("decision") or {}).get("recovery_only")))
        service.backfill_terminal_trials(uid, org, topic["project_id"], "agent", run_id)
        if (row.get("decision") or {}).get("recovery_only"):
            with get_conn() as c:
                c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason=%s,updated_at=NOW() WHERE id=%s AND status='running'",('locked_view_drift：原结果已恢复，等待固定数据版本计算能力；未发新研究',run_id))
            return
        k0 = ledger.current_k(ledger._trials(uid, org, topic["id"]), topic["primary_holding_period"])
        max_steps = min(max(0, 12 - len(current_steps)), max(1, int(topic["max_trials"]) - k0 + 2))

        def before_step(step):
            current = _topic(uid, org, topic["id"])
            if current["status"] != "active":
                return "课题已暂停/归档，F0 停止"
            return ""

        streak = [0]

        def stop_when(decision, result):
            if result.get("action") == "request_seal":
                return "封存完成，交人工审查"
            if result.get("candidate_status") == "development_failed":
                streak[0] += 1
            else:
                streak[0] = 0
            if streak[0] >= 3:
                return "连续 3 次研发失败且无实质修订，停止等待人工复盘"
            return ""

        steps, stop_reason = decision_engine.run_steps(
            decide=lambda step: f0_agent.decide(uid, org, topic, run_id),
            execute=execute_step,
            max_steps=max_steps,
            before_step=before_step,
            stop_when=stop_when,
            on_step=on_step,
            initial_steps=current_steps)
        with get_conn() as c:
            c.execute("""UPDATE quant_factor_f0_runs
                       SET status='stopped',rounds=%s,stop_reason=%s,updated_at=NOW()
                       WHERE id=%s AND status='running'""",
                      (len(steps), stop_reason, run_id))
    except Exception as exc:
        with get_conn() as c:
            c.execute(
                "UPDATE quant_factor_f0_runs SET status='failed',stop_reason=%s,updated_at=NOW() WHERE id=%s AND status IN ('queued','running')",
                (str(exc)[:1000], run_id))


def mark_interrupted():
    """Called on BFF startup: no in-process worker survived, so running runs are interrupted."""
    with get_conn() as c:
        return c.execute(
            "UPDATE quant_factor_f0_runs SET status='stopped',stop_reason='服务重启，任务已中断；可一键继续',updated_at=NOW() WHERE status IN ('queued','running')").rowcount


def resume(uid, org, run_id):
    original = read(uid, org, run_id)
    topic_id = original["topic_id"]
    with get_conn() as lock:
        lock.execute("SELECT pg_advisory_xact_lock(%s,%s)",(9106,uid))
        lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                     (f"quant-factor-start:{uid}:{org}:{topic_id}",))
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE",
                (run_id, uid, org)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["status"] in ACTIVE:
                return _public(row)
            if row["status"] not in ("stopped", "failed"):
                raise WorkflowError("只有已中断或停止的运行可以继续")
            active = c.execute(
                "SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
                (uid, org, topic_id)).fetchone()
            if active:
                return _public(active)
            topic = _topic(uid, org, topic_id)
            if topic["status"] != 'active' or service.control_status(uid, org)["paused"]:
                raise WorkflowError("研究已暂停，请先恢复任务与自动研究")
            recovery_only=topic["view_id"] != published_view()["view_id"]
            if recovery_only and (not service.locked_view_available(topic) or not service.has_recoverable_run(uid,org,topic['project_id'])):
                raise WorkflowError("固定数据版本目前无法确认或无原任务可恢复；不会用当前数据替换原计划")
            if int(row.get('rounds') or 0) >= 12:
                raise WorkflowError("此运行已达到决策次数上限，原记录保留，请人工复盘")
            decision=dict(row.get('decision') or {});decision['recovery_only']=recovery_only
            c.execute("UPDATE quant_factor_f0_runs SET status='queued',stop_reason='',decision=%s::jsonb,updated_at=NOW() WHERE id=%s", (service.store.encode(decision),run_id))
        POOL.submit(run, uid, org, run_id)
        return read(uid, org, run_id)


def latest(uid, org, topic_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC LIMIT 1",
            (uid, org, topic_id)).fetchone()
    return _public(row) if row else None


def read(uid, org, run_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_f0_runs WHERE id=%s AND user_id=%s AND org_id=%s",
            (run_id, uid, org)).fetchone()
    if not row:
        raise KeyError(run_id)
    return _public(row)


__all__ = ["latest", "mark_interrupted", "read", "resume", "run", "start"]
