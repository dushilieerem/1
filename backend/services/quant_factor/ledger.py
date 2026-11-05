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

from typing import Iterable

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
    "sealed_request_error",
]
