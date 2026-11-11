"""CR102: bounded development evidence, never arbitrary candidate serialization.
No database/network imports. The future adapter must SELECT under actor permissions.
"""
import hashlib
import json
import math

SCHEMA = "quant.research-experience.v1"
CHECKS = {"方向Rank IC", "方向IC", "最大回撤", "有效IC观测数", "方向 NW t", "日度 Rank IC 序列"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value, limit=600):
    return value[:limit] if isinstance(value, str) else ""


def _checks(gate):
    result = []
    for check in gate.get("checks", []):
        if not isinstance(check, dict) or check.get("name") not in CHECKS:
            continue
        result.append({"name": check["name"],
                       "actual": check.get("actual") if finite(check.get("actual")) else None,
                       "threshold": check.get("threshold") if finite(check.get("threshold")) else None,
                       "passed": check.get("passed") if isinstance(check.get("passed"), bool) else None})
    return result


def category(*, checks, numerical_passed, technical_incomplete=False,
             stopped_by_user=False, duplicate=False):
    # Missing/unfinished execution does not establish a market failure.
    if technical_incomplete:
        return "technical_incomplete"
    if stopped_by_user:
        return "stopped_by_user"
    if duplicate:
        return "duplicate_or_no_increment"
    observations = next((c for c in checks if c["name"] == "有效IC观测数"), None)
    if observations is None or observations["actual"] is None or observations["passed"] is not True:
        return "insufficient_evidence"
    if numerical_passed is True:
        return "promising_development"
    if numerical_passed is False and any(c["passed"] is False for c in checks):
        return "unsupported_in_scope"
    return "insufficient_evidence"


def private_development(actor, candidate, trial, topic, *, technical_incomplete=False,
                        stopped_by_user=False, duplicate=False):
    """Only own private rows joined by server; same org alone grants no access.

    The booleans are server-derived execution facts, never fields in an LLM output.
    An explicitly shared asset needs its own frozen-publication adapter; this API
    intentionally never fetches another author's candidate through an asset link.
    """
    uid, org = actor
    for row in (candidate, trial, topic):
        if row.get("user_id") != uid or row.get("org_id") != org:
            raise PermissionError("No access to this private research evidence")
    if candidate["project_id"] != topic["project_id"] or trial.get("project_id") != topic["project_id"] or trial.get("topic_id") != topic["id"]:
        raise ValueError("Evidence does not belong to this task")
    development = (candidate.get("evidence") or {}).get("development") or {}
    report_id = development.get("report_id")
    if not report_id or report_id != trial.get("report_id"):
        raise ValueError("The frozen development report and ledger must match")
    if trial.get("branch_id") != (candidate.get("evidence") or {}).get("branch_id"):
        raise ValueError("The frozen hypothesis and trial must match")
    if str(trial.get("kind") or "").lower() in ("sealed", "sealed_validation", "validation", "holdout", "holdout_validation"):
        raise ValueError("Sealed results are excluded from planning evidence")
    snapshot = candidate["snapshot"]
    request = snapshot["request"]
    gate = development.get("gate") or {}
    if gate.get("evaluation_stage") not in (None, "development"):
        raise ValueError("Only development-stage facts may inform new planning")
    expected_metric = snapshot["rules"].get("icMetric", "ic")
    if expected_metric not in ("rank_ic", "ic") or gate.get("metric_type", expected_metric) != expected_metric:
        raise ValueError("The development metric must match its frozen rules")
    checks = _checks(gate)
    passed = gate.get("numerical_passed")
    if not isinstance(passed, bool):
        required = {"方向Rank IC" if snapshot["rules"].get("icMetric") == "rank_ic" else "方向IC", "最大回撤", "有效IC观测数"}
        if snapshot["rules"].get("icMetric") == "rank_ic":
            required.add("方向 NW t")
        known = {c["name"]: c for c in checks}
        passed = all(known[n]["passed"] for n in required) if required <= known.keys() and all(isinstance(known[n]["passed"], bool) for n in required) else None
    plan = snapshot.get("plan") or {}
    contract = plan.get("researchContract") or {}
    identity = contract.get("data_identity") or {}
    facts = {"evaluation_stage": "development", "metric_type": gate.get("metric_type", snapshot["rules"].get("icMetric", "ic")),
             "checks": checks, "numerical_passed": passed if isinstance(passed, bool) else None,
             "historical_k": gate.get("k_used") if isinstance(gate.get("k_used"), int) and not isinstance(gate.get("k_used"), bool) else None,
             "category": category(checks=checks, numerical_passed=passed,
                                  technical_incomplete=technical_incomplete,
                                  stopped_by_user=stopped_by_user, duplicate=duplicate),
             # Exposure existence is allowed; performance/direction/series are absent.
             "sealed_exposure_recorded": bool((candidate.get("evidence") or {}).get("sealed"))}
    record = {"schema": SCHEMA, "visibility": {"kind": "owner_private", "user_id": uid, "org_id": org},
              "source": {"project_id": topic["project_id"], "topic_id": topic["id"],
                         "candidate_id": candidate["id"], "branch_id": trial["branch_id"],
                         "trial_id": trial["id"], "report_id": report_id,
                         "snapshot_hash": candidate["snapshot_hash"]},
              "scope": {"view_id": topic.get("view_id"), "view_manifest_sha256": topic.get("view_manifest_sha256"),
                        "release_id": topic.get("release_id"), "development": identity.get("development") or ([str(topic["development_start"]), str(topic["development_end"])] if topic.get("development_start") and topic.get("development_end") else None),
                        "sample_identity": digest(identity.get("universe")) if identity.get("universe") else None,
                        "forecast_horizon_sessions": topic.get("primary_holding_period")},
              "hypothesis": _text(plan.get("hypothesis")), "facts": facts,
              "interpretation": None, "limitations": ["仅研发证据；不表示已获准入或未来有效"]}
    record["source_fingerprint"] = digest(record)
    record["evidence_ref"] = "dev_" + digest(record["source"])[:24]
    return record


def bounded_context(records, *, actor, limit=12):
    """Input rows must be already permission-filtered; keep stable unique sources.

    Integration must order records by explicit authorized relevance, not by metric
    magnitude. This function preserves that order and excludes arbitrary payloads.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("Invalid evidence bound")
    out = []
    seen = set()
    for row in records:
        if row.get("schema") != SCHEMA or row.get("visibility") != {"kind": "owner_private", "user_id": actor[0], "org_id": actor[1]}:
            raise PermissionError("The context contains unauthorized research")
        expected = digest({k: v for k, v in row.items() if k not in ("source_fingerprint", "evidence_ref")})
        if expected != row.get("source_fingerprint"):
            raise ValueError("Evidence has changed since extraction")
        ref = row["evidence_ref"]
        if ref not in seen:
            out.append(row); seen.add(ref)
        if len(out) == limit:
            break
    return out
