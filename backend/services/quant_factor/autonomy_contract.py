"""CR102: deterministic identities and model-output boundary.
Scope below is a SERVER authorization snapshot, never an authority supplied by LLM.
"""
from copy import deepcopy
from datetime import date
from .research_experience import digest


def family_scope(scope):
    # Deliberately excludes project/title/wording/authorization version/sign/windows
    # of implementation. Those changes cannot reset observed search exposure.
    required = ("org_id", "authority_lineage_id", "data_identity", "universe_snapshot", "development", "forecast_horizon_sessions", "ic_metric")
    if any(scope.get(k) is None for k in required):
        raise ValueError("The authorized evaluation scope is incomplete")
    symbols = scope["universe_snapshot"]
    if not isinstance(symbols, list) or not symbols or not all(isinstance(v, str) and v for v in symbols) or len(set(symbols)) != len(symbols):
        raise ValueError("An explicit unique static sample is required")
    horizon = scope["forecast_horizon_sessions"]
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
        raise ValueError("Invalid forecast horizon")
    stable = {k: deepcopy(scope[k]) for k in required}
    required_data = ("view_id", "view_manifest_sha256", "daily_release", "daily_dataset_sha256")
    if not isinstance(scope["data_identity"], dict) or any(not isinstance(scope["data_identity"].get(k), str) or not scope["data_identity"][k] for k in required_data):
        raise ValueError("The fixed data identity is incomplete")
    # Never include per-project IDs, alias names, or unrelated catalogue entries.
    stable["data_identity"] = {k: scope["data_identity"][k] for k in required_data}
    if scope["ic_metric"] not in ("ic", "rank_ic"):
        raise ValueError("The IC metric is not confirmed")
    interval = scope["development"]
    if not isinstance(interval, list) or len(interval) != 2 or any(not isinstance(v, str) for v in interval) or date.fromisoformat(interval[0]) > date.fromisoformat(interval[1]):
        raise ValueError("Invalid development interval")
    stable["universe_snapshot"] = sorted(symbols)
    return stable


def family_key(scope):
    return "qef_" + digest(family_scope(scope))


def input_fingerprint(scope, direction, catalogue, experience, *, reconsider_id=None):
    """A user-requested reconsider identity is explicit; time/polling is absent."""
    return digest({"authority_lineage_id": scope["authority_lineage_id"],
                   "authority_version": scope["version"], "family_id": family_key(scope),
                   "fields": sorted(scope["allowed_fields"]), "direction": direction,
                   "catalogue_fingerprint": catalogue,
                   "experience_fingerprints": sorted(set(row["source_fingerprint"] for row in experience)),
                   "reconsider_id": reconsider_id})


def consumption(rows, *, counts_toward_k):
    """Count the actual linked ledger facts once; never count a label/project name.

    Integration passes ledger.counts_toward_k and holds family lock with append/
    reserve. This does not deduplicate equal source or equal numbers: two exposed
    trials are two facts even when the implementation was identical.
    """
    seen = {}; counted = 0
    for row in rows:
        if not row.get("id"):
            raise ValueError("Missing source trial identity")
        identity = digest(row)
        if row["id"] in seen:
            if seen[row["id"]] != identity:
                raise ValueError("Conflicting versions of the same trial")
            continue
        seen[row["id"]] = identity
        counted += int(counts_toward_k(row))
    return counted


def trial_permission(*, family_k, lineage_used, task_max_trials, overall_used=None, overall_max_trials=None):
    for value in (family_k, lineage_used, task_max_trials):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("Unconfirmed trial count or authorization")
    if task_max_trials < 1:
        raise ValueError("Task trial authorization is required")
    if (overall_used is None) != (overall_max_trials is None):
        raise ValueError("The overall authorization is incomplete")
    if overall_max_trials is not None and any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (overall_used, overall_max_trials)):
        raise ValueError("Invalid overall authorization")
    remaining = max(0, task_max_trials - lineage_used)
    if overall_max_trials is not None:
        remaining = min(remaining, max(0, overall_max_trials - overall_used))
    return {"family_k": family_k, "next_new_trial_k": family_k + 1,
            "task_lineage_used": lineage_used, "task_max_trials": task_max_trials,
            "remaining_authorized_trials": remaining, "allowed": remaining > 0}


def validate_proposal(value, *, scope, evidence_refs, related_research_refs):
    common = {"action", "title", "hypothesis", "mechanism", "expected_effect", "falsification", "required_fields",
              "forecast_horizon_sessions", "why_now", "difference_from_existing", "evidence_refs", "related_research_refs",
              "wait_reason", "change_conditions"}
    if not isinstance(value, dict) or set(value) != common:
        raise ValueError("Proposal must use the declared schema; authority fields are not model output")
    action = value["action"]
    if action not in ("proposal", "wait"):
        raise ValueError("Unknown planning action")
    for key in ("evidence_refs", "related_research_refs", "required_fields"):
        if not isinstance(value[key], list) or not all(isinstance(v, str) and v for v in value[key]) or len(value[key]) != len(set(value[key])):
            raise ValueError("Invalid reference/field list: " + key)
    if not set(value["evidence_refs"]) <= set(evidence_refs) or not set(value["related_research_refs"]) <= set(related_research_refs):
        raise ValueError("The proposal cites evidence outside the authorized input")
    if not set(value["required_fields"]) <= set(scope["allowed_fields"]):
        raise ValueError("The proposal exceeds the frozen fields")
    for key in common - {"action", "required_fields", "forecast_horizon_sessions", "evidence_refs", "related_research_refs"}:
        if not isinstance(value[key], str) or len(value[key]) > 2000:
            raise ValueError("Invalid proposal text: " + key)
    if action == "wait":
        if not value["wait_reason"].strip() or not value["change_conditions"].strip():
            raise ValueError("Wait must state a reason and conditions for change")
    else:
        for key in ("title", "hypothesis", "mechanism", "expected_effect", "falsification", "why_now", "difference_from_existing"):
            if not value[key].strip():
                raise ValueError("Missing executable proposal field: " + key)
        if not value["required_fields"] or not isinstance(value["forecast_horizon_sessions"], int) or isinstance(value["forecast_horizon_sessions"], bool) or value["forecast_horizon_sessions"] != scope["forecast_horizon_sessions"]:
            raise ValueError("The proposal must preserve the forecast horizon and declare fields")
    return deepcopy(value)


def may_apply(planning, authorization):
    # CAS is checked again while the DB row lock is held, AFTER model return.
    return (authorization["enabled"] is True and authorization["member_active"] is True
            and authorization["research_permission"] is True
            and planning["authorization_id"] == authorization["id"]
            and planning["authorization_version"] == authorization["version"])
