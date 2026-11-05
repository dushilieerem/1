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
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s AND user_id=%s AND org_id=%s",
            (topic_id, uid, org)).fetchone()
    if not row:
        raise KeyError(topic_id)
    return dict(row)


def _trials(uid: int, org: int, topic_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no",
            (uid, org, topic_id)).fetchall()
    return [dict(row) for row in rows]


def _branches(uid: int, org: int, topic_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quant_factor_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at",
            (uid, org, topic_id)).fetchall()
    return [dict(row) for row in rows]


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
    contract_revision = str(payload.get("contract_revision") or "")
    as_of = _as_date(payload["as_of"], "as_of") if payload.get("as_of") else None
    topic_id, branch_id = str(uuid.uuid4()), str(uuid.uuid4())
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9110, uid))
        existing = c.execute(
            "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s",
            (uid, org, project_id)).fetchone()
        if existing:
            return {"topic": _public(existing), "created": False}
        if not c.execute("SELECT id FROM detect_projects WHERE user_id=%s AND id=%s",
                         (uid, project_id)).fetchone():
            raise KeyError(project_id)
        c.execute(
            """INSERT INTO quant_factor_topics
               (id,user_id,org_id,project_id,view_id,release_id,contract_revision,as_of,
                development_start,development_end,validation_start,validation_end,
                primary_holding_period,policy_version,max_trials,max_sealed)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (topic_id, uid, org, project_id, view_id, release_id, contract_revision, as_of,
             development_start, development_end, validation_start, validation_end,
             holding, policy_version, max_trials, max_sealed))
        c.execute(
            """INSERT INTO quant_factor_branches
               (id,user_id,org_id,topic_id,source,owner_id,hypothesis_version,implementation_version)
               VALUES (%s,%s,%s,%s,'manual',%s,1,1)""",
            (branch_id, uid, org, topic_id, uid))
        row = c.execute(
            "SELECT * FROM quant_factor_topics WHERE id=%s", (topic_id,)).fetchone()
    return {"topic": _public(row), "created": True}


def list_topics(uid: int, org: int, project_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at",
            (uid, org, project_id)).fetchall()
    return [_public(row) for row in rows]


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
               (id,user_id,org_id,topic_id,parent_id,source,owner_id,hypothesis_version,implementation_version)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (branch_id, uid, org, topic["id"], parent_id, source, uid, hypothesis, implementation))
        row = c.execute("SELECT * FROM quant_factor_branches WHERE id=%s", (branch_id,)).fetchone()
    return _public(row)


def list_branches(uid: int, org: int, topic_id: str) -> list[dict]:
    _topic(uid, org, topic_id)
    return [_public(row) for row in _branches(uid, org, topic_id)]


def ledger_view(uid: int, org: int, topic_id: str) -> dict:
    topic = _topic(uid, org, topic_id)
    trials = _trials(uid, org, topic_id)
    k = current_k(trials, topic["primary_holding_period"])
    return {
        "topic": _public(topic),
        "branches": [_public(row) for row in _branches(uid, org, topic_id)],
        "trials": [_public(row) for row in trials],
        "k": k,
        "threshold": threshold(k) if k >= 1 else None,
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
    if outcome not in set(COUNTED_OUTCOMES) | set(CONDITIONAL_OUTCOMES) | set(RERUN_OUTCOMES):
        raise ValueError("outcome 不合法")
    kind = str(payload.get("kind") or "research").strip()
    if kind not in DIAGNOSTIC_KINDS | EDIT_KINDS | RERUN_KINDS | SEALED_KINDS | {"research", "manual", "agent", "iteration"}:
        raise ValueError("kind 不合法")
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
    view_id = str(payload.get("view_id") or topic["view_id"])
    if view_id != topic["view_id"]:
        raise ValueError("试验数据视图必须与课题锁定的 view_id 一致")
    release_id = str(payload.get("release_id") or topic["release_id"] or "")
    contract_revision = str(payload.get("contract_revision") or topic["contract_revision"] or "")
    as_of = _as_date(payload["as_of"], "as_of") if payload.get("as_of") else topic.get("as_of")
    trial_id = str(uuid.uuid4())
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9111, uid))
        trial_no = c.execute(
            "SELECT COALESCE(MAX(trial_no),0)+1 AS n FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND project_id=%s",
            (uid, org, topic["project_id"])).fetchone()["n"]
        prior = c.execute(
            """SELECT id,implementation_hash,release_id,view_id,parameters
               FROM quant_factor_trials
               WHERE user_id=%s AND org_id=%s AND project_id=%s
                 AND implementation_hash=%s AND release_id=%s AND view_id=%s
                 AND parameters=%s::jsonb
               ORDER BY trial_no DESC LIMIT 1""",
            (uid, org, topic["project_id"], implementation_hash, release_id, view_id,
             json.dumps(parameters, ensure_ascii=False, sort_keys=True))).fetchone()
        rerun_of = None
        if prior and is_deterministic_rerun(
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
                returned_metrics,rerun_of,holding_period,view_id,release_id,contract_revision,as_of)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (trial_id, uid, org, topic["project_id"], topic_id, branch_id, trial_no, kind,
             implementation_hash, json.dumps(parameters, ensure_ascii=False),
             json.dumps(result_summary, ensure_ascii=False), payload.get("report_id"),
             executor, outcome, returned_metrics, rerun_of, holding, view_id,
             release_id, contract_revision, as_of))
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
    "append_trial",
    "create_branch",
    "create_topic",
    "ledger_view",
    "list_branches",
    "list_topics",
    "sealed_request_error",
    "threshold_view",
]
