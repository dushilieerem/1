"""V5 P0 trial-ledger counting rules (pure logic, no database).

K is the number of development-interval tests whose results the researcher or
agent could see.  The ledger records every event; only events that satisfy the
rules below advance K.

Counting table (product decision 10.1-2):

===============  ==========================================  ==========
event            example                                     counts K?
===============  ==========================================  ==========
passed test      development gate passed                     yes
failed test      development gate failed                     yes
error/timeout    any development metric was returned         yes
error/timeout    no development metric returned              no
cancelled        no development metric returned              no
rerun            same hash + data release + parameters       no
static check     compile, syntax check, smoke test           no
sealed test      one holdout per candidate, <=3 per topic    no
manual edit      only when followed by a counted test        yes (the test)
===============  ==========================================  ==========

A manual code change is not itself a trial: the next completed test after the
change is a new trial and counts once.  Each parameter/window variant is a
separate trial and counts separately.  Only the topic's pre-registered primary
holding period counts; diagnostic horizons in the same report do not add K.  If
the topic has a primary holding period and a row has no horizon, the row is
rejected rather than silently counted or dropped.

Trust boundary: ``rerun_of``, ``kind='rerun'`` and edit markers are ledger
fields written by the server after it compares implementation hash, data
release, view and parameters.  They must never be accepted from an API request
body.  ``is_deterministic_rerun`` is the pure comparison helper the append path
must use; the client cannot self-report a rerun to avoid K.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Iterable

from services.core.db import get_conn
from services.core.tenant import Tenant
from . import repo

from .metrics import threshold

DIAGNOSTIC_KINDS = frozenset({"static_check", "compile", "smoke", "smoke_test"})
EDIT_KINDS = frozenset({"manual_edit", "code_edit", "edit"})
RERUN_KINDS = frozenset({"rerun"})
SEALED_KINDS = frozenset({"sealed", "sealed_validation", "holdout_validation"})
COUNTED_OUTCOMES = frozenset({"passed", "failed"})
CONDITIONAL_OUTCOMES = frozenset({"error", "timeout", "cancelled", "canceled"})
RERUN_OUTCOMES = frozenset({"rerun"})
MAX_SEALED_PER_TOPIC = 3


def _kind(trial: dict) -> str:
    return str(trial.get("kind") or "research").strip().lower()


def _outcome(trial: dict) -> str:
    return str(trial.get("outcome") or trial.get("status") or "").strip().lower()


def _holding_period(trial: dict):
    for key in ("holding_period", "holding_period_days", "horizon"):
        if trial.get(key) is not None:
            return trial[key]
    return None


def _returned_metrics(trial: dict) -> bool:
    if "returned_metrics" in trial:
        return bool(trial["returned_metrics"])
    metrics = trial.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return True
    result = trial.get("result")
    return isinstance(result, dict) and bool(result.get("metrics"))


def _trial_no(trial: dict) -> int:
    value = trial.get("trial_no", trial.get("k"))
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("试验序号 trial_no 必须是大于等于 1 的整数")
    return value


def is_sealed(trial: dict) -> bool:
    """A sealed/holdout validation is recorded separately and never adds K."""
    return _kind(trial) in SEALED_KINDS


def is_deterministic_rerun(original: dict, trial: dict) -> bool:
    """Server-side test: same implementation, data release, view and parameters.

    Any missing identity field fails closed (returns False), so an incomplete
    payload cannot claim a free rerun.  The append path must compute this from
    stored values and set ``rerun_of`` itself; never trust a request field.
    """
    if not isinstance(original, dict) or not isinstance(trial, dict):
        raise TypeError("original 和 trial 必须是字典")
    for key in ("implementation_hash", "data_release_id", "parameters"):
        if original.get(key) is None or trial.get(key) is None:
            return False
        if original[key] != trial[key]:
            return False
    if "view_id" in original and "view_id" in trial:
        if original.get("view_id") is None or original["view_id"] != trial["view_id"]:
            return False
    return True


def counts_toward_k(trial: dict, primary_holding_period=None) -> bool:
    """Return whether one ledger row advances the topic's K."""
    if not isinstance(trial, dict):
        raise TypeError("trial 必须是字典")
    kind = _kind(trial)
    if kind in DIAGNOSTIC_KINDS or kind in EDIT_KINDS or kind in RERUN_KINDS or kind in SEALED_KINDS:
        return False
    if trial.get("rerun_of") is not None:
        return False
    outcome = _outcome(trial)
    if outcome in RERUN_OUTCOMES:
        return False
    if primary_holding_period is not None:
        holding = _holding_period(trial)
        if holding is None:
            raise ValueError("课题已登记主持有期，但试验缺少持有期，不能判断是否计入 K")
        if int(holding) != int(primary_holding_period):
            return False
    if outcome in COUNTED_OUTCOMES:
        return True
    if outcome in CONDITIONAL_OUTCOMES:
        return _returned_metrics(trial)
    raise ValueError(f"未知的试验结果 outcome={outcome!r}，不能静默计入或排除 K")


def _validated_trial_nos(trials: Iterable[dict]) -> list[int]:
    numbers = [_trial_no(trial) for trial in trials]
    if len(numbers) != len(set(numbers)):
        raise ValueError("台账中存在重复试验序号，只追加台账不允许重复行")
    return numbers


def current_k(trials: Iterable[dict], primary_holding_period=None) -> int:
    """Count countable trials; duplicate or malformed trial numbers are defects."""
    trials = list(trials)
    _validated_trial_nos(trials)
    return sum(1 for trial in trials if counts_toward_k(trial, primary_holding_period))


def next_trial_no(trials: Iterable[dict]) -> int:
    """Next ledger row number (includes reruns and other non-counting rows)."""
    trials = list(trials)
    numbers = _validated_trial_nos(trials)
    return max(numbers, default=0) + 1


def k_after_append(trials: Iterable[dict], trial: dict, primary_holding_period=None) -> int:
    """K after appending one proposed row; rerun/static/sealed rows add zero."""
    trials = list(trials)
    current = current_k(trials, primary_holding_period)
    return current + (1 if counts_toward_k(trial, primary_holding_period) else 0)


def k_summary(trials: Iterable[dict], submitted_k: int, primary_holding_period=None) -> dict:
    """Show submission-time K next to current K, with both thresholds.

    ``submitted_k`` must be at least 1: before a candidate is submitted there is
    no submission-time K, so pre-submission UI should show "尚未提交" and not
    call this function with 0.
    """
    if isinstance(submitted_k, bool) or not isinstance(submitted_k, int) or submitted_k < 1:
        raise ValueError("提交时 K 必须是大于等于 1 的整数")
    trials = list(trials)
    current = current_k(trials, primary_holding_period)
    return {
        "submitted_k": submitted_k,
        "current_k": current,
        "threshold_submitted": threshold(submitted_k),
        "threshold_current": threshold(current),
        "changed": current != submitted_k,
    }


def sealed_request_error(trials: Iterable[dict], candidate_id: str,
                         limit: int = MAX_SEALED_PER_TOPIC) -> str | None:
    """Return the blocking reason for a new sealed request, or None.

    One candidate may be sealed once; a topic may consume at most three sealed
    checks.  Any recorded sealed row counts toward the topic cap.
    """
    if not candidate_id:
        raise ValueError("candidate_id 不能为空")
    sealed = [trial for trial in trials if is_sealed(trial)]
    if any(str(trial.get("candidate_id")) == str(candidate_id) for trial in sealed):
        return "同一候选只允许一次封存验证"
    if len(sealed) >= limit:
        return f"课题封存验证已达上限 {limit} 次"
    return None


def can_request_sealed(trials: Iterable[dict], candidate_id: str,
                       limit: int = MAX_SEALED_PER_TOPIC) -> bool:
    return sealed_request_error(trials, candidate_id, limit) is None


def _public(row) -> dict:
    return {key: value for key, value in dict(row).items() if key not in ("user_id", "org_id")}


def _as_date(value, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} 必须是 YYYY-MM-DD 日期") from None


def _as_int(value, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{field} 必须是 {low}—{high} 的整数")
    return value


def _topic(uid: int, org: int, topic_id: str) -> dict:
    return repo.topic(Tenant.from_pair(uid, org), topic_id)


def _trials(uid: int, org: int, topic_id: str) -> list[dict]:
    return repo.trials(Tenant.from_pair(uid, org), topic_id)


def _branches(uid: int, org: int, topic_id: str) -> list[dict]:
    return repo.branches(Tenant.from_pair(uid, org), topic_id)


def create_topic(uid: int, org: int, project_id: str, payload: dict) -> dict:
    """Create the one topic bound to a project and its default manual branch."""
    view_id = str(payload.get("view_id") or "").strip()
    if not view_id:
        raise ValueError("view_id 不能为空")
    development_start = _as_date(payload.get("development_start"), "development_start")
    development_end = _as_date(payload.get("development_end"), "development_end")
    validation_start = _as_date(payload.get("validation_start"), "validation_start")
    validation_end = _as_date(payload.get("validation_end"), "validation_end")
    if not (development_start <= development_end < validation_start <= validation_end):
        raise ValueError("区间必须满足研发开始≤研发结束<封存开始≤封存结束")
    holding = _as_int(payload.get("primary_holding_period"), "primary_holding_period", 1, 20)
    max_trials = _as_int(payload.get("max_trials"), "max_trials", 1, 1000)
    max_sealed = _as_int(payload.get("max_sealed", 3), "max_sealed", 1, 3)
    policy_version = str(payload.get("policy_version") or "").strip()
    if not policy_version:
        raise ValueError("policy_version 不能为空")
    release_id = str(payload.get("release_id") or "")
    release_ids = payload.get("release_ids") or {}
    if not isinstance(release_ids, dict):
        raise ValueError("release_ids 必须是 JSON 对象")
    view_manifest_sha256 = str(payload.get("view_manifest_sha256") or "")
    contract_revision = str(payload.get("contract_revision") or "")
    as_of = _as_date(payload["as_of"], "as_of") if payload.get("as_of") else None
    topic_id, branch_id = str(uuid.uuid4()), str(uuid.uuid4())
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9106, uid))
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9110, uid))
        existing = c.execute(
            "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",
            (uid, org, project_id)).fetchone()
        if existing:
            return {"topic": _public(existing), "created": False}
        project_row=c.execute("SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE",(uid,project_id)).fetchone()
        if not project_row:raise KeyError(project_id)
        from services.factor.detect_store import _row_project
        from services.workflow_workspace.platform_data import published_view
        from .research_contract import from_project
        project=_row_project(dict(project_row));view=published_view()
        if view['view_id']!=view_id or view.get('manifest_sha256')!=view_manifest_sha256:
            raise ValueError('数据版本已变化，请重新确认固定版本；未自动切换')
        contract=from_project(uid,org,project,view)
        config=project['config'];config['researchPlan']={**config.get('researchPlan',{}),'researchContract':contract}
        config.update(v5ActiveBranch=branch_id,v5ControlEpoch=str(uuid.uuid4()))
        c.execute('UPDATE detect_projects SET config=%s::jsonb,updated_at=NOW() WHERE user_id=%s AND id=%s',(json.dumps(config,ensure_ascii=False),uid,project_id))
        display_no = c.execute(
            "SELECT COALESCE(MAX(display_no),0)+1 AS n FROM quant_factor_topics WHERE user_id=%s AND org_id=%s",
            (uid, org)).fetchone()["n"]
        c.execute(
            """INSERT INTO quant_factor_topics
               (id,user_id,org_id,project_id,view_id,release_id,release_ids,view_manifest_sha256,
                contract_revision,as_of,development_start,development_end,
                validation_start,validation_end,primary_holding_period,policy_version,
                max_trials,max_sealed,display_no)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (topic_id, uid, org, project_id, view_id, release_id,
             json.dumps(release_ids, ensure_ascii=False), view_manifest_sha256,
             contract_revision, as_of, development_start, development_end,
             validation_start, validation_end, holding, policy_version,
             max_trials, max_sealed, display_no))
        c.execute(
            """INSERT INTO quant_factor_branches
               (id,user_id,org_id,topic_id,source,owner_id,hypothesis_version,implementation_version,title)
               VALUES (%s,%s,%s,%s,'manual',%s,1,1,'初始假设')""",
            (branch_id, uid, org, topic_id, uid))
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s", (topic_id,)).fetchone()
    return {"topic": _public(row), "created": True}


def list_topics(uid: int, org: int, project_id: str) -> list[dict]:
    return [_public(row) for row in repo.topics(Tenant.from_pair(uid, org), project_id)]


def set_topic_status(uid: int, org: int, topic_id: str, status: str) -> dict:
    if status not in ("active", "paused"):
        raise ValueError("课题状态只能是 active 或 paused")
    topic = _topic(uid, org, topic_id)
    if topic["status"] == "archived":
        raise ValueError("已归档课题不能恢复")
    with get_conn() as c:
        c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f"quant-factor-start:{uid}:{org}:{topic_id}",))
        c.execute('SELECT id FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,topic['project_id']))
        c.execute("UPDATE detect_projects SET config=jsonb_set(COALESCE(config,'{}'::jsonb),'{v5ControlEpoch}',to_jsonb(%s::text)),updated_at=NOW() WHERE user_id=%s AND id=%s",(str(uuid.uuid4()),uid,topic['project_id']))
        from .research_advice import close_pending
        close_pending(c,uid,org,topic_id=topic_id,reason='未采用：目标控制版本已变化')
        from . import research_queue
        if status=='paused' and research_queue.enabled():
            queued=c.execute("SELECT id FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND status='queued' AND decision->>'queue_deployment'=%s",(uid,org,topic_id,research_queue.DEPLOYMENT_ID)).fetchall()
            for item in queued:
                if research_queue.cancel(c,'f0',item['id'],uid,org):c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason='用户已暂停并取消排队；历史保留',updated_at=NOW() WHERE id=%s AND status='queued'",(item['id'],))
        row=c.execute('UPDATE quant_factor_topics SET status=%s,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s RETURNING *',(status,topic_id,uid,org)).fetchone()
    return _public(row)


def list_org_topics(uid: int, org: int) -> list[dict]:
    """All topics visible to the current quant member, newest first."""
    with get_conn() as c:
        rows = [dict(row) for row in c.execute(
            """SELECT t.*, p.name AS project_name,
                      p.config->'researchPlan'->>'researchPurpose' AS research_purpose,
                      (SELECT COUNT(*) FROM quant_factor_branches b
                        WHERE b.user_id=t.user_id AND b.org_id=t.org_id AND b.topic_id=t.id) AS branch_count,
                      (SELECT COUNT(*) FROM quant_factor_trials r
                        WHERE r.user_id=t.user_id AND r.org_id=t.org_id AND r.topic_id=t.id) AS trial_count,
                      (SELECT COUNT(*) FROM quant_factor_sealed_validations v
                        WHERE v.user_id=t.user_id AND v.org_id=t.org_id AND v.topic_id=t.id) AS sealed_used,
                      (SELECT r.status FROM quant_factor_f0_runs r
                        WHERE r.user_id=t.user_id AND r.org_id=t.org_id AND r.topic_id=t.id
                        ORDER BY r.created_at DESC LIMIT 1) AS dispatch_status,
                      (SELECT r.stop_reason FROM quant_factor_f0_runs r
                        WHERE r.user_id=t.user_id AND r.org_id=t.org_id AND r.topic_id=t.id
                        ORDER BY r.created_at DESC LIMIT 1) AS dispatch_stop_reason,
                      (SELECT r.decision->'technical_wait'->>'kind' FROM quant_factor_f0_runs r
                        WHERE r.user_id=t.user_id AND r.org_id=t.org_id AND r.topic_id=t.id
                        ORDER BY r.created_at DESC LIMIT 1) AS dispatch_technical_wait,
                      (SELECT COUNT(DISTINCT c.id) FROM quant_factor_candidates c
                        JOIN quant_factor_trials r
                          ON r.user_id=c.user_id AND r.org_id=c.org_id
                         AND r.report_id='qf_'||c.id||'_development'
                        WHERE c.user_id=t.user_id AND c.org_id=t.org_id AND r.topic_id=t.id
                          AND c.archive->'review'->>'status'='requested'
                          AND COALESCE(c.archive->'review'->>'purpose','research_admission')='research_admission') AS pending_review,
                      (SELECT COUNT(DISTINCT c.id) FROM quant_factor_candidates c
                        JOIN quant_factor_trials r
                          ON r.user_id=c.user_id AND r.org_id=c.org_id
                         AND r.report_id='qf_'||c.id||'_development'
                        WHERE c.user_id=t.user_id AND c.org_id=t.org_id AND r.topic_id=t.id
                          AND c.archive->'review'->>'status'='requested'
                          AND c.archive->'review'->>'purpose'='research_feedback_only') AS pending_feedback,
                      (SELECT COUNT(*) FROM quant_factor_sealed_validations v
                        WHERE v.user_id=t.user_id AND v.org_id=t.org_id AND v.topic_id=t.id
                          AND v.status='passed') AS sealed_passed,
                      (SELECT COUNT(*) FROM quant_factor_sealed_validations v
                        WHERE v.user_id=t.user_id AND v.org_id=t.org_id AND v.topic_id=t.id
                          AND v.status IN ('queued','running')) AS sealed_running,
                      (SELECT COUNT(*) FROM quant_factor_sealed_validations v
                        WHERE v.user_id=t.user_id AND v.org_id=t.org_id AND v.topic_id=t.id
                          AND v.status IN ('failed','error')) AS sealed_failed,
                      (SELECT COUNT(*) FROM quant_factor_candidates c
                        WHERE c.user_id=t.user_id AND c.org_id=t.org_id
                          AND c.project_id=t.project_id
                          AND c.archive->>'approved'='true') AS approved_count,
                      (SELECT COUNT(*) FROM quant_factor_candidates c
                        WHERE c.user_id=t.user_id AND c.org_id=t.org_id AND c.project_id=t.project_id
                          AND c.archive->>'approved'='true'
                          AND c.archive->'research_asset'->>'schema'='quant.research-asset.v1'
                          AND c.archive->'research_asset'->>'snapshot_hash'=c.snapshot_hash) AS registered_count,
                      (SELECT r.outcome FROM quant_factor_trials r
                        WHERE r.user_id=t.user_id AND r.org_id=t.org_id AND r.topic_id=t.id
                        ORDER BY r.trial_no DESC LIMIT 1) AS latest_outcome
               FROM quant_factor_topics t
               JOIN detect_projects p ON p.user_id=t.user_id AND p.id=t.project_id
               WHERE t.user_id=%s AND t.org_id=%s
               ORDER BY t.created_at DESC""",
            (uid, org)).fetchall()]
    out = []
    for row in rows:
        item = _public(row)
        item["k"] = current_k(_trials(uid, org, row["id"]), row["primary_holding_period"])
        out.append(item)
    return out


def create_branch(uid: int, org: int, topic_id: str, payload: dict) -> dict:
    topic = _topic(uid, org, topic_id)
    source = str(payload.get("source") or "").strip()
    if source not in ("agent", "manual"):
        raise ValueError("source 必须是 agent 或 manual")
    parent_id = payload.get("parent_id") or None
    if parent_id:
        with get_conn() as c:
            parent = c.execute(
                "SELECT id FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s",
                (parent_id, uid, org, topic_id)).fetchone()
        if not parent:
            raise KeyError(parent_id)
    hypothesis = _as_int(payload.get("hypothesis_version", 1), "hypothesis_version", 1, 100000)
    implementation = _as_int(payload.get("implementation_version", 1), "implementation_version", 1, 100000)
    branch_id = str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO quant_factor_branches
               (id,user_id,org_id,topic_id,parent_id,source,owner_id,hypothesis_version,implementation_version,title)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (branch_id, uid, org, topic["id"], parent_id, source, uid, hypothesis, implementation,
             str(payload.get("title") or "").strip()[:60]))
        row = c.execute("SELECT * FROM quant_factor_branches WHERE id=%s", (branch_id,)).fetchone()
    return _public(row)


def list_branches(uid: int, org: int, topic_id: str) -> list[dict]:
    _topic(uid, org, topic_id)
    return [_public(row) for row in _branches(uid, org, topic_id)]


def _lock_workbench(c,uid,org,topic,allow_paused_orchestrator=False):
    c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
    c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f"quant-factor-start:{uid}:{org}:{topic['id']}",))
    project=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,topic['project_id'])).fetchone()
    if not project:raise KeyError(topic['project_id'])
    current_topic=c.execute('SELECT status FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s',(topic['id'],uid,org)).fetchone()
    paused_takeover=allow_paused_orchestrator and current_topic and current_topic['status']=='paused'
    for table,clause in [('quant_factor_f0_runs',"status IN ('queued','running')"),('quant_factor_candidates',"status LIKE '%%_running'"),('quant_factor_agent_jobs',"status IN ('queued','running')"),('quant_factor_iterations',"status IN ('queued','running')"),('quant_factor_sealed_validations',"status IN ('queued','running')")]:
        if paused_takeover and table in ('quant_factor_f0_runs','quant_factor_agent_jobs'):continue
        if c.execute('SELECT id FROM '+table+' WHERE user_id=%s AND org_id=%s AND project_id=%s AND '+clause+' LIMIT 1',(uid,org,topic['project_id'])).fetchone():raise ValueError('当前仍有研究或检验在运行，请先等待结束或暂停接管')
    pending=c.execute("SELECT id FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s AND (archive->'review'->>'status'='requested' OR archive->'research_asset' IS NOT NULL) LIMIT 1",(uid,org,topic['project_id'])).fetchone()
    if pending:raise ValueError('当前有待复核或已登记版本；请先结束复核，已登记成果请从因子库另建研究任务')
    if paused_takeover:
        c.execute("UPDATE quant_factor_agent_jobs SET status='cancelled',input=input||%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('queued','running')",(json.dumps({'superseded_by_manual_takeover':True}),json.dumps([{'action':'manual_takeover','message':'人工已接手，旧建议不再自动回填；迟到产物保留供查看。'}],ensure_ascii=False),uid,org,topic['project_id']))
        c.execute("UPDATE quant_factor_f0_runs SET status='stopped',stop_reason='人工已暂停并接手，迟到建议不写入当前工程',updated_at=NOW() WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('queued','running')",(uid,org,topic['project_id']))
    return dict(project)


def takeover_branch(uid:int,org:int,topic_id:str,parent_id:str,candidate_id=None,acknowledged=False,expected_control_epoch=None)->dict:
    """Explicitly fork the selected frozen definition; never relabel an old candidate."""
    if acknowledged is not True:raise ValueError('请明确确认所选候选及接手分支')
    topic=_topic(uid,org,topic_id)
    with get_conn() as c:
        project=_lock_workbench(c,uid,org,topic,allow_paused_orchestrator=True)
        if expected_control_epoch is not None and (project.get('config') or {}).get('v5ControlEpoch')!=expected_control_epoch:raise ValueError('工作控制版本已变化，请重新核对接手对象，未覆盖当前工程')
        parent=c.execute('SELECT * FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s',(parent_id,uid,org,topic_id)).fetchone()
        if not parent:raise KeyError(parent_id)
        if not candidate_id:raise ValueError('请明确选择此分支的冻结候选，再从该版本接手修订')
        candidate=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s AND project_id=%s FOR UPDATE',(candidate_id,uid,org,topic['project_id'])).fetchone()
        if not candidate:raise KeyError(candidate_id)
        trial=c.execute("SELECT id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s AND branch_id=%s AND report_id=%s LIMIT 1",(uid,org,topic_id,parent_id,'qf_'+candidate_id+'_development')).fetchone()
        if not trial or (candidate.get('evidence') or {}).get('branch_id') not in (None,parent_id):raise ValueError('所选候选与父分支不一致，未接手其他分支')
        from .presentation import checkout_config
        branch_id=str(uuid.uuid4());config=checkout_config(project.get('config') or {},dict(candidate),branch_id);config['v5ControlEpoch']=str(uuid.uuid4())
        c.execute("""INSERT INTO quant_factor_branches
            (id,user_id,org_id,topic_id,parent_id,source,owner_id,hypothesis_version,implementation_version,title)
            VALUES (%s,%s,%s,%s,%s,'manual',%s,%s,%s,'人工接手')""",(branch_id,uid,org,topic_id,parent_id,uid,int(parent['hypothesis_version'])+1,int(parent['implementation_version'])))
        c.execute('UPDATE detect_projects SET config=%s::jsonb,updated_at=NOW() WHERE user_id=%s AND id=%s',(json.dumps(config,ensure_ascii=False),uid,topic['project_id']))
        row=dict(c.execute('SELECT * FROM quant_factor_branches WHERE id=%s',(branch_id,)).fetchone())
    return {**_public(row),'source_candidate_id':candidate_id,'requires_new_validation':True}


def activate_branch(uid:int,org:int,topic_id:str,branch_id:str,acknowledged=False,expected_active_branch=None)->dict:
    """Bind only an explicitly confirmed working draft. GET/navigation never calls this."""
    if acknowledged is not True:raise ValueError('请确认当前工作稿与目标分支后再写入')
    topic=_topic(uid,org,topic_id)
    with get_conn() as c:
        project=_lock_workbench(c,uid,org,topic);config=dict(project.get('config') or {})
        if config.get('v5ActiveBranch')!=expected_active_branch:raise ValueError('工作分支已变化，请重新读取并确认，未覆盖其他分支')
        branch=c.execute('SELECT id,source FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s',(branch_id,uid,org,topic_id)).fetchone()
        if not branch:raise KeyError(branch_id)
        recorded=c.execute('SELECT id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s AND branch_id=%s LIMIT 1',(uid,org,topic_id,branch_id)).fetchone()
        if recorded:raise ValueError('该分支已有冻结试验，请选择明确候选并接手为新修订，不能将当前工程稿覆盖过去')
        config['v5ActiveBranch']=branch_id;config['v5ControlEpoch']=str(uuid.uuid4())
        c.execute('UPDATE detect_projects SET config=%s::jsonb,updated_at=NOW() WHERE user_id=%s AND id=%s',(json.dumps(config,ensure_ascii=False),uid,topic['project_id']))
    return {'topic_id':topic_id,'branch_id':branch_id,'source':branch['source'],'binding_confirmed':True,'control_epoch':config['v5ControlEpoch']}


def handback_branch(uid:int,org:int,topic_id:str)->dict:
    _topic(uid,org,topic_id)
    raise ValueError('请从已保存的人工版本明确交回研究系统；此旧入口不会清除当前分支')


def _branch_labels(uid: int, org: int, topic_id: str, branches: list[dict]) -> dict:
    """Stable V5 labels: root H1, revisions H2/H3, parallel children H2a/H2b."""
    by_parent = {}
    for b in sorted(branches, key=lambda x: (x.get("created_at").isoformat() if hasattr(x.get("created_at"), "isoformat") else str(x.get("created_at") or ""), str(x["id"]))):
        by_parent.setdefault(b.get("parent_id"), []).append(b)
    labels = {}
    revision = [1]
    letters = "abcdefghijklmnopqrstuvwxyz"

    def visit(parent, parent_label):
        parallel = 0
        for child in by_parent.get(parent["id"] if parent else None, []):
            is_parallel = child.get("source") == "manual" or (
                parent is not None and int(child.get("hypothesis_version") or 1) <= int(parent.get("hypothesis_version") or 1))
            if parent is None:
                label = "H1" if parallel == 0 else "H1" + letters[min(parallel, 25)]
                parallel += 1
            elif is_parallel:
                label = parent_label + letters[min(parallel, 25)]
                parallel += 1
            else:
                revision[0] += 1
                label = "H" + str(revision[0])
            labels[child["id"]] = label
            visit(child, label)

    visit(None, "")
    return labels


def _short_title(text: object, limit: int = 22) -> str:
    """把完整假设压成研究树可读的短标题；历史空标题不再显示“未命名”。"""
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    for mark in ("。", "；", ";", "，", ","):
        if mark in value:
            value = value.split(mark, 1)[0]
            break
    return value[:limit] + ("…" if len(value) > limit else "")


def _branch_titles(uid: int, org: int, topic_id: str) -> dict:
    titles = {}
    with get_conn() as c:
        rows = c.execute(
            "SELECT decision FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at",
            (uid, org, topic_id)).fetchall()
    for row in rows:
        for step in (row.get("decision") or {}).get("steps") or []:
            result = step.get("result") or {}
            decision = step.get("decision") or {}
            bid = result.get("branch_id")
            title = decision.get("next_hypothesis") or result.get("hypothesis")
            if bid and isinstance(title, str) and title.strip():
                titles[bid] = title.strip()
    return titles


def _branch_reviews(uid: int, org: int, topic_id: str) -> dict:
    with get_conn() as c:
        rows = c.execute(
            """SELECT r.branch_id,c.id AS candidate_id,c.archive->'review'->>'status' AS review_status
               FROM quant_factor_candidates c
               JOIN quant_factor_trials r
                 ON r.user_id=c.user_id AND r.org_id=c.org_id
                AND r.report_id='qf_'||c.id||'_development'
               WHERE c.user_id=%s AND c.org_id=%s AND r.topic_id=%s
               ORDER BY c.updated_at""",
            (uid, org, topic_id)).fetchall()
    out = {}
    for row in rows:
        out[row["branch_id"]] = {"candidate_id": row["candidate_id"], "review_status": row["review_status"]}
    return out


def _branch_sealed(uid: int, org: int, topic_id: str) -> dict:
    with get_conn() as c:
        rows = c.execute(
            """SELECT t.branch_id, s.status, s.created_at
               FROM quant_factor_sealed_validations s
               JOIN quant_factor_trials t
                 ON t.user_id=s.user_id AND t.org_id=s.org_id
                AND t.report_id='qf_' || s.candidate_id || '_development'
               WHERE s.user_id=%s AND s.org_id=%s AND s.topic_id=%s
               ORDER BY s.created_at""",
            (uid, org, topic_id)).fetchall()
    latest = {}
    for row in rows:
        latest[row["branch_id"]] = row["status"]
    return latest


def ledger_view(uid: int, org: int, topic_id: str) -> dict:
    topic = _topic(uid, org, topic_id)
    trials = _trials(uid, org, topic_id)
    branches = [_public(row) for row in _branches(uid, org, topic_id)]
    labels = _branch_labels(uid, org, topic_id, branches)
    titles = _branch_titles(uid, org, topic_id)
    sealed = _branch_sealed(uid, org, topic_id)
    reviews = _branch_reviews(uid, org, topic_id)
    children = {}
    for b in branches:
        children.setdefault(b.get("parent_id"), []).append(b["id"])
    latest_trial = {}
    for t in trials:
        latest_trial[t["branch_id"]] = t
    for b in branches:
        b["display_label"] = labels.get(b["id"], "H?")
        title = str(b.get("title") or "").strip()
        if not title:
            title = _short_title(titles.get(b["id"]))
        if not title:
            if b.get("source") == "manual":
                title = "人工接手" if b.get("parent_id") else "初始假设"
            else:
                title = f"假设 v{b.get('hypothesis_version', 1)}"
        b["display_title"] = title
        b["hypothesis_text"] = titles.get(b["id"]) or ""
        from .presentation import branch_sources
        b.update(branch_sources(b,latest_trial.get(b['id'])))
        b["source_label"] = "人工" if b.get("source") == "manual" else "Agent"
        s_status = sealed.get(b["id"])
        review = reviews.get(b["id"]) or {}
        t = latest_trial.get(b["id"])
        if review.get("review_status") == "requested":
            b["display_status"] = "待复核"
        elif b.get("status") in ("archived", "rejected", "submitted", "approved"):
            b["display_status"] = {"archived": "已归档", "rejected": "已驳回",
                                   "submitted": "待复核", "approved": "已入库"}[b["status"]]
        elif s_status == "failed":
            b["display_status"] = "封存失败，待复盘"
        elif s_status == "passed":
            b["display_status"] = "封存通过，待提交"
        elif children.get(b["id"]):
            b["display_status"] = "已派生修订"
        elif t and t.get("outcome") == "passed":
            b["display_status"] = "研发通过"
        elif t and t.get("outcome") == "failed":
            b["display_status"] = "未达标"
        elif t:
            b["display_status"] = t.get("outcome") or "已执行"
        else:
            if b.get("source") == "manual":
                b["display_status"] = "人工接手，待检验" if b.get("parent_id") else "待启动"
            else:
                b["display_status"] = "待检验"
    for trial in trials:
        trial['branch_label']=labels.get(trial.get('branch_id'))
    with get_conn() as c:
        f0 = c.execute(
            "SELECT status,stop_reason,created_at FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC LIMIT 1",
            (uid, org, topic_id)).fetchone()
    with get_conn() as c:
        work=c.execute("SELECT config->>'v5ActiveBranch' AS branch_id FROM detect_projects WHERE user_id=%s AND id=%s",(uid,topic['project_id'])).fetchone()
    dispatch = None
    if f0:
        dispatch = {"status": f0["status"], "stop_reason": f0["stop_reason"] or ""}
    k = current_k(trials, topic["primary_holding_period"])
    return {
        "topic": _public(topic),
        "active_branch_id": (work or {}).get('branch_id'),
        "branches": branches,
        "trials": [_public(row) for row in trials],
        "dispatch": dispatch,
        "k": k,
        # Before any counted trial the bar is still the K=1 threshold (t*=1.96), never null.
        "threshold": threshold(max(k, 1)),
        "threshold_k": max(k, 1),
        "threshold_next_if_counted": threshold(max(1, k + 1)),
        "next_trial_no": next_trial_no(trials),
    }


def append_trial(uid: int, org: int, topic_id: str, payload: dict) -> dict:
    """Append one trial. rerun_of and returned_metrics are server-derived."""
    topic = _topic(uid, org, topic_id)
    branch_id = str(payload.get("branch_id") or "").strip()
    if not branch_id:
        raise ValueError("branch_id 不能为空")
    with get_conn() as c:
        branch = c.execute(
            "SELECT id FROM quant_factor_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s",
            (branch_id, uid, org, topic_id)).fetchone()
    if not branch:
        raise KeyError(branch_id)
    implementation_hash = str(payload.get("implementation_hash") or "").strip()
    if not implementation_hash:
        raise ValueError("implementation_hash 不能为空")
    executor = str(payload.get("executor") or "").strip()
    if executor not in ("human", "agent", "service"):
        raise ValueError("executor 必须是 human、agent 或 service")
    outcome = str(payload.get("outcome") or "").strip()
    if outcome not in set(COUNTED_OUTCOMES) | set(CONDITIONAL_OUTCOMES):
        raise ValueError("outcome 不合法；rerun 只能由服务端派生")
    kind = str(payload.get("kind") or "research").strip()
    if kind not in {"research", "manual", "agent", "iteration"}:
        raise ValueError("kind 不合法；诊断/封存/rerun 不能通过 trials 写入")
    parameters = payload.get("parameters") or {}
    result_summary = payload.get("result_summary") or {}
    if not isinstance(parameters, dict) or not isinstance(result_summary, dict):
        raise ValueError("parameters 和 result_summary 必须是 JSON 对象")
    metrics = result_summary.get("metrics")
    nested = result_summary.get("result")
    returned_metrics = bool(isinstance(metrics, dict) and metrics) or bool(
        isinstance(nested, dict) and isinstance(nested.get("metrics"), dict) and nested["metrics"])
    holding = _as_int(payload.get("holding_period", topic["primary_holding_period"]),
                      "holding_period", 1, 20)
    # Reproducibility fields come only from the topic lock, never from the request.
    view_id = topic["view_id"]
    release_id = str(topic["release_id"] or "")
    release_ids = topic.get("release_ids") or {}
    if not isinstance(release_ids, dict):
        raise ValueError("课题 release_ids 数据损坏")
    view_manifest_sha256 = str(topic.get("view_manifest_sha256") or "")
    contract_revision = str(topic["contract_revision"] or "")
    as_of = topic.get("as_of")
    trial_id = str(uuid.uuid4())
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9106, uid))
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9111, uid))
        trial_no = c.execute(
            "SELECT COALESCE(MAX(trial_no),0)+1 AS n FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND project_id=%s",
            (uid, org, topic["project_id"])).fetchone()["n"]
        prior = c.execute(
            """SELECT id,implementation_hash,release_id,release_ids,view_manifest_sha256,view_id,parameters
               FROM quant_factor_trials
               WHERE user_id=%s AND org_id=%s AND project_id=%s
                 AND implementation_hash=%s AND release_id=%s AND view_id=%s
                 AND parameters=%s::jsonb
               ORDER BY trial_no DESC LIMIT 1""",
            (uid, org, topic["project_id"], implementation_hash, release_id, view_id,
             json.dumps(parameters, ensure_ascii=False, sort_keys=True))).fetchone()
        rerun_of = None
        if prior and prior["release_ids"] == release_ids and prior["view_manifest_sha256"] == view_manifest_sha256 and is_deterministic_rerun(
                {"implementation_hash": prior["implementation_hash"],
                 "data_release_id": prior["release_id"],
                 "view_id": prior["view_id"], "parameters": prior["parameters"]},
                {"implementation_hash": implementation_hash, "data_release_id": release_id,
                 "view_id": view_id, "parameters": parameters}):
            rerun_of = prior["id"]
        c.execute(
            """INSERT INTO quant_factor_trials
               (id,user_id,org_id,project_id,topic_id,branch_id,trial_no,kind,
                implementation_hash,parameters,result_summary,report_id,executor,outcome,
                returned_metrics,rerun_of,holding_period,view_id,release_id,release_ids,
                view_manifest_sha256,contract_revision,as_of,f0_run_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
            (trial_id, uid, org, topic["project_id"], topic_id, branch_id, trial_no, kind,
             implementation_hash, json.dumps(parameters, ensure_ascii=False),
             json.dumps(result_summary, ensure_ascii=False), payload.get("report_id"),
             executor, outcome, returned_metrics, rerun_of, holding, view_id,
             release_id, json.dumps(release_ids, ensure_ascii=False),
             view_manifest_sha256, contract_revision, as_of, payload.get("f0_run_id")))
        row = c.execute("SELECT * FROM quant_factor_trials WHERE id=%s", (trial_id,)).fetchone()
    return _public(row)


def threshold_view(uid: int, org: int, topic_id: str, k: int | None = None) -> dict:
    topic = _topic(uid, org, topic_id)
    trials = _trials(uid, org, topic_id)
    current = current_k(trials, topic["primary_holding_period"])
    if isinstance(k, str) and k.isdigit():
        k = int(k)
    selected = current if k is None else _as_int(k, "k", 1, 100000)
    return {"k": selected, "current_k": current, "threshold": threshold(selected)}


__all__ = [
    "COUNTED_OUTCOMES",
    "CONDITIONAL_OUTCOMES",
    "DIAGNOSTIC_KINDS",
    "EDIT_KINDS",
    "MAX_SEALED_PER_TOPIC",
    "SEALED_KINDS",
    "can_request_sealed",
    "counts_toward_k",
    "current_k",
    "is_deterministic_rerun",
    "is_sealed",
    "k_after_append",
    "k_summary",
    "next_trial_no",
    "activate_branch",
    "append_trial",
    "create_branch",
    "create_topic",
    "ledger_view",
    "list_branches",
    "list_org_topics",
    "set_topic_status",
    "list_topics",
    "sealed_request_error",
    "threshold_view",
]
