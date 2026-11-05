"""AC-04 sealed validation: one holdout per candidate, F5 executor.

The researcher may request once and later sees only status/decision. Reviewer
and manager can read the full result. The worker uses the topic's locked
validation interval and data snapshot; it never reuses the development window.
"""
from __future__ import annotations

import copy
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from services.core.db import get_conn
from services.factor.re_factor_async_proxy import proxy_get_factor_run, proxy_submit_factor_backtest

from . import ledger, service, store
from .policy import WorkflowError, evaluate

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quant-factor-sealed")
ACTIVE = ("queued", "running")


def _public(row: dict, full: bool) -> dict:
    out = {key: value for key, value in row.items() if key not in ("user_id", "org_id")}
    if not full:
        out.pop("result", None)
    return out


def _topic(uid: int, org: int, topic_id: str) -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s",
            (topic_id, uid, org)).fetchone()
    if not row:
        raise KeyError(topic_id)
    return dict(row)


def _candidate(uid: int, org: int, cid: str) -> dict:
    row = store.read(uid, org, cid)
    return row


def request(uid: int, org: int, cid: str) -> dict:
    cand = _candidate(uid, org, cid)
    if cand["status"] != "development_passed":
        raise WorkflowError("只有研发检验通过的候选可以申请封存验证")
    with get_conn() as c:
        topic = c.execute(
            "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",
            (uid, org, cand["project_id"])).fetchone()
        if not topic:
            raise WorkflowError("候选没有对应的 V5 课题台账，不能封存")
        sealed = c.execute(
            "SELECT COUNT(*) AS n FROM quant_factor_sealed_validations WHERE user_id=%s AND org_id=%s AND topic_id=%s",
            (uid, org, topic["id"])).fetchone()["n"]
        if sealed >= int(topic["max_sealed"]):
            raise WorkflowError(f"课题封存验证已达上限 {topic['max_sealed']} 次")
        existing = c.execute(
            "SELECT * FROM quant_factor_sealed_validations WHERE candidate_id=%s", (cid,)).fetchone()
        if existing:
            raise WorkflowError("同一候选只允许一次封存验证")
        trial_ids = [row["id"] for row in c.execute(
            "SELECT id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no",
            (uid, org, topic["id"])).fetchall()]
        sid = str(uuid.uuid4())
        c.execute(
            """INSERT INTO quant_factor_sealed_validations
               (id,candidate_id,user_id,org_id,project_id,topic_id,snapshot_hash,status,
                executor,view_id,release_ids,view_manifest_sha256,contract_revision,as_of,trial_ids)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'queued','F5',%s,%s::jsonb,%s,%s,%s,%s::jsonb)""",
            (sid, cid, uid, org, cand["project_id"], topic["id"], cand["snapshot_hash"],
             topic["view_id"], store.encode(topic.get("release_ids") or {}),
             topic.get("view_manifest_sha256") or "", topic.get("contract_revision") or "",
             topic.get("as_of"), store.encode(trial_ids)))
        row = c.execute("SELECT * FROM quant_factor_sealed_validations WHERE id=%s", (sid,)).fetchone()
    POOL.submit(run, uid, org, sid)
    return _public(dict(row), False)


def run(uid: int, org: int, sid: str) -> None:
    try:
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM quant_factor_sealed_validations WHERE id=%s AND user_id=%s AND org_id=%s",
                (sid, uid, org)).fetchone()
            if not row or row["status"] not in ACTIVE:
                return
            c.execute("UPDATE quant_factor_sealed_validations SET status='running',updated_at=NOW() WHERE id=%s", (sid,))
        cand = _candidate(uid, org, row["candidate_id"])
        topic = _topic(uid, org, row["topic_id"])
        snap = cand["snapshot"]
        plan = snap["plan"]
        req = copy.deepcopy(snap["request"])
        req.update(start=plan["validationStart"], end=plan["validationEnd"])
        status, _, task = proxy_submit_factor_backtest(req)
        if status not in (200, 202) or not isinstance(task, dict) or not task.get("run_id"):
            raise WorkflowError("封存计算提交失败，可重试")
        rid = task["run_id"]
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            status, _, data = proxy_get_factor_run(rid)
            if status == 200 and isinstance(data, dict) and data.get("status") in ("succeeded", "failed", "cancelled"):
                if data["status"] != "succeeded":
                    raise WorkflowError("封存计算未成功：" + str(data.get("error") or data.get("status"))[:500])
                result = data.get("result") or {}
                trial_rows = ledger._trials(uid, org, topic["id"])
                k = ledger.current_k(trial_rows, topic["primary_holding_period"])
                gate = evaluate(result, snap["rules"], k)
                with get_conn() as c:
                    c.execute(
                        """UPDATE quant_factor_sealed_validations
                           SET status=%s,result=%s::jsonb,report_id=%s,evaluated_at=NOW(),updated_at=NOW()
                           WHERE id=%s AND status='running'""",
                        ("passed" if gate["passed"] else "failed",
                         store.encode({"result": result, "gate": gate, "run_id": rid}),
                         "sealed_" + sid, sid))
                return
            time.sleep(2)
        raise WorkflowError("封存计算超时，可重试")
    except Exception as exc:
        with get_conn() as c:
            c.execute(
                "UPDATE quant_factor_sealed_validations SET status='error',result=%s::jsonb,updated_at=NOW() WHERE id=%s AND status IN ('queued','running')",
                (store.encode({"error": str(exc)[:1000]}), sid))


def detail(uid: int, org: int, cid: str, full: bool) -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_sealed_validations WHERE candidate_id=%s AND org_id=%s",
            (cid, org)).fetchone()
    if not row:
        raise KeyError(cid)
    return _public(dict(row), full)


def status(uid: int, org: int, cid: str, full: bool) -> dict:
    return detail(uid, org, cid, full)


__all__ = ["detail", "request", "run", "status"]
