"""S5 sealed validation and S6 review for strategy candidates."""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from services.core.db import get_conn
from services.core.lan_http import request_json
from services.workflow_workspace.platform_data import published_view

from . import strategy_backtest_runner as runner
from . import strategy_gates, strategy_research

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="strategy-seal")


def _now():
    return datetime.now(timezone.utc)


def _branch_topic(uid, org, bid, lock=False):
    with get_conn() as c:
        branch = c.execute(
            "SELECT * FROM strategy_branches WHERE id=%s AND user_id=%s AND org_id=%s" + (" FOR UPDATE" if lock else ""),
            (bid, uid, org)).fetchone()
        if not branch:
            raise KeyError(bid)
        topic = c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",
                          (branch["topic_id"], uid, org)).fetchone()
    return dict(branch), dict(topic)


def _event(uid, org, topic, branch, action, actor, note=""):
    with get_conn() as c:
        c.execute(
            """INSERT INTO strategy_review_events(id,user_id,org_id,topic_id,branch_id,action,actor_id,note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (str(uuid.uuid4()), uid, org, topic["id"], branch["id"], action, actor, str(note or "")[:2000]))


def _latest_gate(uid, org, topic_id, branch_id):
    led = strategy_research.ledger(uid, org, topic_id)
    trials = [t for t in led["trials"] if t["branch_id"] == branch_id and not t.get("rerun_of")]
    if not trials:
        return None
    return (trials[-1].get("effective_gate") or trials[-1].get("gate") or {})


def _public(row):
    return {k: v for k, v in dict(row).items() if k not in ("user_id", "org_id")}


def request(uid, org, bid, idempotency_key):
    key = str(idempotency_key or "").strip()
    if not 1 <= len(key) <= 100:
        raise ValueError("请提供 1—100 字符的幂等键")
    branch, topic = _branch_topic(uid, org, bid, lock=True)
    if topic["view_id"] != published_view()["view_id"]:
        raise ValueError("课题锁定视图与当前发布视图不一致")
    with get_conn() as c:
        old = c.execute(
            "SELECT * FROM strategy_sealed_validations WHERE user_id=%s AND org_id=%s AND idempotency_key=%s",
            (uid, org, key)).fetchone()
        if old:
            return _public(old)
        used = c.execute("SELECT COUNT(*) AS n FROM strategy_sealed_validations WHERE user_id=%s AND org_id=%s AND topic_id=%s",
                         (uid, org, topic["id"])).fetchone()["n"]
    if branch["status"] != "active":
        raise ValueError("只有进行中的分支可以申请封存")
    if used >= int(topic.get("max_sealed") or 1):
        raise ValueError(f"课题封存验证已达上限 {topic.get('max_sealed') or 1} 次")
    gate = _latest_gate(uid, org, topic["id"], bid)
    if not gate or not gate.get("complete"):
        pending = "、".join(gate.get("pending") or []) if gate else "尚无试验"
        raise ValueError("研发门槛未全部完成，不能申请封存：" + pending)
    if not gate.get("passed"):
        failed = "、".join(c["name"] for c in gate.get("checks") or [] if c.get("passed") is False)
        raise ValueError("研发门槛未全部通过，不能申请封存：" + failed)
    sid = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO strategy_sealed_validations
               (id,branch_id,user_id,org_id,topic_id,status,executor,view_id,release_ids,
                view_manifest_sha256,contract_revision,as_of,idempotency_key)
               VALUES (%s,%s,%s,%s,%s,'queued','S5',%s,%s::jsonb,%s,%s,%s,%s)""",
            (sid, bid, uid, org, topic["id"], topic["view_id"],
             json.dumps(topic["release_ids"], ensure_ascii=False), topic["view_manifest_sha256"],
             topic["contract_revision"], topic["as_of"], key))
        c.execute("UPDATE strategy_branches SET status='frozen',review_status='seal_running',updated_at=NOW() WHERE id=%s", (bid,))
    _event(uid, org, topic, branch, "submit", uid, "申请封存")
    POOL.submit(run, uid, org, sid)
    return read(uid, org, sid)


def run(uid, org, sid):
    try:
        with get_conn() as c:
            row = c.execute("SELECT * FROM strategy_sealed_validations WHERE id=%s AND user_id=%s AND org_id=%s",
                            (sid, uid, org)).fetchone()
            if not row:
                return
            c.execute("UPDATE strategy_sealed_validations SET status='running',updated_at=NOW() WHERE id=%s", (sid,))
        branch, topic = _branch_topic(uid, org, row["branch_id"])
        payload = runner._payload(topic, branch)
        payload.update(start=str(topic["validation_start"]), end=str(topic["validation_end"]))
        status, _, data = request_json(runner._base() + "/api/backtest/strategy", method="POST",
                                       payload=payload, timeout=600)
        if status != 200 or not isinstance(data, dict) or data.get("error"):
            raise ValueError("封存回测失败：" + str((data or {}).get("error") or status)[:300])
        gate = strategy_gates.evaluate(data, 1, sealed=True)
        result = {"metrics": data.get("metrics") or {}, "excess_return": data.get("excess_return"),
                  "start": payload["start"], "end": payload["end"]}
        final = "passed" if gate["complete"] and gate["passed"] else "failed"
        with get_conn() as c:
            c.execute(
                """UPDATE strategy_sealed_validations
                   SET status=%s,result=%s::jsonb,gate=%s::jsonb,report_id=%s,updated_at=NOW() WHERE id=%s""",
                (final, json.dumps(result, ensure_ascii=False), json.dumps(gate, ensure_ascii=False),
                 "strategy_sealed_" + sid, sid))
            c.execute("UPDATE strategy_branches SET review_status=%s,updated_at=NOW() WHERE id=%s",
                      ("sealed_" + final, branch["id"]))
    except Exception as exc:
        with get_conn() as c:
            c.execute("UPDATE strategy_sealed_validations SET status='error',result=%s::jsonb,updated_at=NOW() WHERE id=%s",
                      (json.dumps({"error": str(exc)[:500]}, ensure_ascii=False), sid))
            row = c.execute("SELECT branch_id FROM strategy_sealed_validations WHERE id=%s", (sid,)).fetchone()
            if row:
                c.execute("UPDATE strategy_branches SET review_status='seal_error',updated_at=NOW() WHERE id=%s",
                          (row["branch_id"],))


def read(uid, org, sid):
    with get_conn() as c:
        row = c.execute("SELECT * FROM strategy_sealed_validations WHERE id=%s AND user_id=%s AND org_id=%s",
                        (sid, uid, org)).fetchone()
    if not row:
        raise KeyError(sid)
    return _public(row)


def submit_for_review(uid, org, bid):
    branch, topic = _branch_topic(uid, org, bid, lock=True)
    if branch["status"] != "frozen" or branch["review_status"] != "sealed_passed":
        raise ValueError("只有封存通过的候选可以提交复核")
    with get_conn() as c:
        c.execute("UPDATE strategy_branches SET status='submitted',updated_at=NOW() WHERE id=%s", (bid,))
    _event(uid, org, topic, branch, "submit", uid, "提交独立复核")
    return _public(_branch_topic(uid, org, bid)[0])


def queue(uid, org):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT b.id,b.topic_id,b.hypothesis,b.owner_id,b.version,b.status,b.review_status,b.updated_at,
                      t.name AS topic_name,t.universe,t.benchmark
               FROM strategy_branches b JOIN strategy_topics t
                 ON t.user_id=b.user_id AND t.org_id=b.org_id AND t.id=b.topic_id
               WHERE b.user_id=%s AND b.org_id=%s AND b.status='submitted' AND b.owner_id<>%s
               ORDER BY b.updated_at DESC""", (uid, org, uid)).fetchall()]
    return [_public(r) for r in rows]


def claim(uid, org, bid):
    branch, topic = _branch_topic(uid, org, bid, lock=True)
    if branch["owner_id"] == uid:
        raise ValueError("不能复核自己提交的策略")
    if branch["status"] != "submitted":
        raise ValueError("该候选不在待复核状态")
    if branch["reviewer_id"] not in (None, uid):
        raise ValueError("该候选已指派给其他复核人")
    with get_conn() as c:
        c.execute("UPDATE strategy_branches SET reviewer_id=%s,updated_at=NOW() WHERE id=%s", (uid, bid))
    _event(uid, org, topic, branch, "claim", uid, "领取复核")
    return _public(_branch_topic(uid, org, bid)[0])


def decide(uid, org, bid, decision, note=""):
    if decision not in ("approved", "rejected"):
        raise ValueError("复核决定必须是 approved 或 rejected")
    branch, topic = _branch_topic(uid, org, bid, lock=True)
    if branch["owner_id"] == uid:
        raise ValueError("不能复核自己提交的策略")
    if branch["status"] != "submitted" or branch["reviewer_id"] != uid:
        raise ValueError("请先领取该复核事项")
    if decision == "approved":
        gate = _latest_gate(uid, org, topic["id"], bid)
        if not gate or not gate.get("passed"):
            raise ValueError("研发与稳健性门槛未全部通过，不能入库")
    with get_conn() as c:
        c.execute(
            """UPDATE strategy_branches SET status=%s,review_decision=%s,review_note=%s,reviewed_at=NOW(),updated_at=NOW()
               WHERE id=%s""",
            (decision, decision, str(note or "")[:2000], bid))
    _event(uid, org, topic, branch, "approve" if decision == "approved" else "reject", uid, note)
    return _public(_branch_topic(uid, org, bid)[0])


__all__ = ["claim", "decide", "queue", "read", "request", "submit_for_review"]
