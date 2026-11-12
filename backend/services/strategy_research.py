"""M2 strategy research ledger: topics, frozen-recipe branches, append-only trials."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date

from services.core.db import get_conn
from services.factor.code_validation import validated_factor_code
from services.workflow_workspace.platform_data import published_view


def _public(row):
    return {k: v for k, v in dict(row).items() if k not in ("user_id", "org_id")}


def _date(value, name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是 YYYY-MM-DD") from None


def _int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} 必须是 {low}—{high} 的整数")
    return value


def _buffer(value) -> float:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        raise ValueError("buffer 必须是 0—1 的数值") from None
    if not 0 <= v <= 1:
        raise ValueError("buffer 必须在 0 与 1 之间")
    return v


def recipe(payload: dict) -> dict:
    factors = payload.get("factors")
    if not isinstance(factors, list) or not 1 <= len(factors) <= 3:
        raise ValueError("配方必须选择 1—3 个因子")
    clean = []
    for item in factors:
        if isinstance(item, str):
            item = {"factor": item, "direction": "positive"}
        if not isinstance(item, dict) or not str(item.get("factor") or "").strip():
            raise ValueError("因子必须是非空标识")
        if item.get("direction", "positive") not in ("positive", "negative"):
            raise ValueError("因子方向只能是 positive/negative")
        entry = str(item["factor"]).strip()
        row = {"factor": entry, "direction": item.get("direction", "positive"), "library": str(item.get("library") or "主因子库")}
        if item.get("code"):
            row["entry"] = str(item.get("entry") or entry)
            row["code"] = validated_factor_code(str(item["code"]), row["entry"])
        clean.append(row)
    return {
        "factors": clean, "equal_weight": True,
        "top_n": _int(payload.get("top_n"), "top_n", 5, 300),
        "rebalance_days": _int(payload.get("rebalance_days"), "rebalance_days", 1, 60),
        "buffer": _buffer(payload.get("buffer", 0)),
    }


def _recipe_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def create_topic(uid, org, payload):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("课题名称不能为空")
    universe = str(payload.get("universe") or "CSI300")
    benchmark = str(payload.get("benchmark") or "CSI300")
    dev_start = _date(payload.get("development_start"), "development_start")
    dev_end = _date(payload.get("development_end"), "development_end")
    val_start = _date(payload.get("validation_start"), "validation_start")
    val_end = _date(payload.get("validation_end"), "validation_end")
    if not (dev_start <= dev_end < val_start <= val_end):
        raise ValueError("区间必须满足研发开始≤研发结束<封存开始≤封存结束")
    cost = float(payload.get("cost_bps", 10) or 0)
    if not 0 <= cost <= 1000:
        raise ValueError("cost_bps 超出范围")
    view = published_view()
    dates = [d.get("date_max") for d in view["datasets"].values() if d.get("date_max")]
    tid = str(uuid.uuid4())
    with get_conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s,%s)", (9112, uid))
        display_no = c.execute(
            "SELECT COALESCE(MAX(display_no),0)+1 AS n FROM strategy_topics WHERE user_id=%s AND org_id=%s",
            (uid, org)).fetchone()["n"]
        c.execute(
            """INSERT INTO strategy_topics
               (id,user_id,org_id,name,objective,universe,benchmark,development_start,development_end,
                validation_start,validation_end,cost_bps,policy_version,max_trials,view_id,
                release_ids,view_manifest_sha256,contract_revision,as_of,display_no)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
            (tid, uid, org, name, str(payload.get("objective") or ""), universe, benchmark,
             dev_start, dev_end, val_start, val_end, cost,
             str(payload.get("policy_version") or "strategy-v5-p0"),
             _int(payload.get("max_trials"), "max_trials", 1, 1000),
             view["view_id"], json.dumps({k: v.get("release") for k, v in view["datasets"].items()
                                          if v.get("release")}, ensure_ascii=False),
             view.get("manifest_sha256") or "", view.get("contract_revision") or "",
             max(dates) if dates else None, display_no))
        row = c.execute("SELECT * FROM strategy_topics WHERE id=%s", (tid,)).fetchone()
    return _public(row)


def list_topics(uid, org):
    with get_conn() as c:
        rows = c.execute(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM strategy_branches b
                        WHERE b.user_id=t.user_id AND b.org_id=t.org_id AND b.topic_id=t.id) AS branch_count,
                      (SELECT COUNT(*) FROM strategy_trials r
                        WHERE r.user_id=t.user_id AND r.org_id=t.org_id AND r.topic_id=t.id) AS trial_count
               FROM strategy_topics t WHERE t.user_id=%s AND t.org_id=%s ORDER BY t.created_at DESC""",
            (uid, org)).fetchall()
    return [_public(r) for r in rows]


def create_branch(uid, org, topic_id, payload, allowed_sources=("manual",)):
    with get_conn() as c:
        topic = c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",
                          (topic_id, uid, org)).fetchone()
        if not topic:
            raise KeyError(topic_id)
        if topic["view_id"] != published_view()["view_id"]:
            raise ValueError("课题锁定视图与当前发布视图不一致；请新建计划版本/课题，不能用新视图结果接旧台账")
        source = str(payload.get("source") or "manual")
        if source not in allowed_sources:
            raise ValueError("该入口不允许创建此来源的分支")
        parent_id = payload.get("parent_id") or None
        if parent_id:
            parent = c.execute(
                "SELECT id FROM strategy_branches WHERE id=%s AND user_id=%s AND org_id=%s AND topic_id=%s",
                (parent_id, uid, org, topic_id)).fetchone()
            if not parent:
                raise KeyError(parent_id)
        rc = recipe(payload)
        hypothesis = str(payload.get("hypothesis") or "").strip()
        if not hypothesis:
            raise ValueError("分支必须写研究假设")
        bid = str(uuid.uuid4())
        version = int(c.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS v FROM strategy_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s",
            (uid, org, topic_id)).fetchone()["v"])
        c.execute(
            """INSERT INTO strategy_branches
               (id,user_id,org_id,topic_id,parent_id,source,owner_id,hypothesis,recipe,implementation_hash,version)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
            (bid, uid, org, topic_id, parent_id, source, uid,
             hypothesis, json.dumps(rc, ensure_ascii=False), _recipe_hash(rc), version))
        row = c.execute("SELECT * FROM strategy_branches WHERE id=%s", (bid,)).fetchone()
    return _public(row)


def _branch_labels(branches):
    by_parent = {}
    for b in sorted(branches, key=lambda x: (str(x.get("created_at") or ""), str(x["id"]))):
        by_parent.setdefault(b.get("parent_id"), []).append(b)
    labels = {}
    revision = [1]
    letters = "abcdefghijklmnopqrstuvwxyz"

    def visit(parent, parent_label):
        parallel = 0
        for child in by_parent.get(parent["id"] if parent else None, []):
            if parent is None:
                label = "V1" if parallel == 0 else "V1" + letters[min(parallel, 25)]
                parallel += 1
            elif child.get("source") == "manual":
                label = parent_label + letters[min(parallel, 25)]
                parallel += 1
            else:
                revision[0] += 1
                label = "V" + str(revision[0])
            labels[child["id"]] = label
            visit(child, label)

    visit(None, "")
    return labels


def ledger(uid, org, topic_id):
    with get_conn() as c:
        topic = c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",
                          (topic_id, uid, org)).fetchone()
        if not topic:
            raise KeyError(topic_id)
        branches = [dict(r) for r in c.execute(
            "SELECT * FROM strategy_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at",
            (uid, org, topic_id)).fetchall()]
        trials = [dict(r) for r in c.execute(
            "SELECT * FROM strategy_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY trial_no",
            (uid, org, topic_id)).fetchall()]
        diag_rows = [dict(r) for r in c.execute(
            "SELECT kind,payload,branch_id FROM strategy_diagnostics WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC",
            (uid, org, topic_id)).fetchall()]
        sealed_rows = [dict(r) for r in c.execute(
            """SELECT branch_id,status,result,gate,report_id,created_at FROM strategy_sealed_validations
               WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at DESC""",
            (uid, org, topic_id)).fetchall()]
    def counts(t):
        if t["outcome"] in ("passed", "failed"):
            return True
        return t["outcome"] in ("error", "timeout") and bool(t.get("metrics"))
    k = sum(1 for t in trials if counts(t))
    from . import strategy_gates
    from .strategy_diagnostics import merged_gate
    diag = {}
    for row in diag_rows:
        diag.setdefault(row["branch_id"], {}).setdefault(row["kind"], row)
    sealed = {}
    for row in sealed_rows:
        sealed.setdefault(row["branch_id"], row)
    public_trials = []
    for t in trials:
        item = _public(t)
        item["effective_gate"] = merged_gate(item, diag.get(t["branch_id"], {}))
        public_trials.append(item)
    labels = _branch_labels(branches)
    public_branches = []
    for b in branches:
        item = _public(b)
        item["display_label"] = labels.get(b["id"], "V?")
        item["sealed"] = _public(sealed[b["id"]]) if b["id"] in sealed else None
        public_branches.append(item)
    return {"topic": _public(topic), "branches": public_branches,
            "trials": public_trials, "k": k,
            "ir_threshold": strategy_gates.need_ir(k),
            "policy": {"version": strategy_gates.POLICY_VERSION, **strategy_gates.POLICY},
            "policy_note": "测试阈值（原型默认值）；机构可发布新的策略政策版本"}


def trial_report(uid, org, trial_id):
    """One trial with its real gate, robustness diagnostics and sealed result."""
    with get_conn() as c:
        trial = c.execute("SELECT * FROM strategy_trials WHERE id=%s AND user_id=%s AND org_id=%s",
                          (trial_id, uid, org)).fetchone()
        if not trial:
            raise KeyError(trial_id)
        branch = c.execute("SELECT * FROM strategy_branches WHERE id=%s AND user_id=%s AND org_id=%s",
                           (trial["branch_id"], uid, org)).fetchone()
        topic = c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",
                          (trial["topic_id"], uid, org)).fetchone()
        diag = [dict(r) for r in c.execute(
            """SELECT kind,payload,created_at FROM strategy_diagnostics
               WHERE user_id=%s AND org_id=%s AND branch_id=%s ORDER BY created_at DESC""",
            (uid, org, trial["branch_id"])).fetchall()]
        sealed = c.execute(
            """SELECT id,status,result,gate,report_id,created_at FROM strategy_sealed_validations
               WHERE user_id=%s AND org_id=%s AND branch_id=%s ORDER BY created_at DESC LIMIT 1""",
            (uid, org, trial["branch_id"])).fetchone()
    from . import strategy_gates
    from .strategy_diagnostics import merged_gate
    latest = {}
    for row in diag:
        latest.setdefault(row["kind"], row)
    trial_public = _public(trial)
    trial_public["effective_gate"] = merged_gate(trial_public, latest)
    return {"trial": trial_public, "branch": _public(branch), "topic": _public(topic),
            "diagnostics": latest, "sealed": _public(sealed) if sealed else None,
            "policy": {"version": strategy_gates.POLICY_VERSION, **strategy_gates.POLICY}}


def importable(uid, org):
    """SVQuant strategy projects owned by this member, not yet imported into V5."""
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT p.id,p.name,p.description,p.run_count,p.updated_at,
                      (i.id IS NOT NULL) AS imported
               FROM strategy_projects p
               LEFT JOIN strategy_imported_assets i
                 ON i.user_id=%s AND i.org_id=%s AND i.source_project_id=p.id
               WHERE p.user_id=%s ORDER BY p.updated_at DESC""", (uid, org, uid)).fetchall()]
    return [_public(r) for r in rows]


def import_asset(uid, org, project_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM strategy_projects WHERE id=%s AND user_id=%s",
                        (project_id, uid)).fetchone()
        if not row:
            raise KeyError(project_id)
        cfg = row["config"] or {}
        h = hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        aid = str(uuid.uuid4())
        c.execute(
            """INSERT INTO strategy_imported_assets
               (id,user_id,org_id,source_project_id,name,config,implementation_hash,status)
               VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,'imported')
               ON CONFLICT (user_id,org_id,source_project_id)
               DO UPDATE SET name=EXCLUDED.name,config=EXCLUDED.config,
                             implementation_hash=EXCLUDED.implementation_hash,imported_at=NOW()""",
            (aid, uid, org, project_id, row["name"], json.dumps(cfg, ensure_ascii=False), h))
        out = c.execute("SELECT * FROM strategy_imported_assets WHERE user_id=%s AND org_id=%s AND source_project_id=%s",
                        (uid, org, project_id)).fetchone()
    return _public(out)


def imported_assets(uid, org):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM strategy_imported_assets WHERE user_id=%s AND org_id=%s AND status='imported' ORDER BY imported_at DESC",
            (uid, org)).fetchall()]
    return [_public(r) for r in rows]


def library(uid, org):
    """Approved strategy versions available as research baselines."""
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT b.id,b.topic_id,b.hypothesis,b.recipe,b.version,b.implementation_hash,
                      b.reviewer_id,b.reviewed_at,b.review_note,
                      t.name AS topic_name,t.universe,t.benchmark,t.development_start,t.development_end,
                      (SELECT COUNT(*) FROM strategy_trials r
                        WHERE r.user_id=b.user_id AND r.org_id=b.org_id AND r.branch_id=b.id AND r.rerun_of IS NULL) AS trial_count,
                      (SELECT v.result FROM strategy_sealed_validations v
                        WHERE v.user_id=b.user_id AND v.org_id=b.org_id AND v.branch_id=b.id
                        ORDER BY v.created_at DESC LIMIT 1) AS sealed_result,
                      (SELECT v.gate FROM strategy_sealed_validations v
                        WHERE v.user_id=b.user_id AND v.org_id=b.org_id AND v.branch_id=b.id
                        ORDER BY v.created_at DESC LIMIT 1) AS sealed_gate,
                      (SELECT r.gate FROM strategy_trials r
                        WHERE r.user_id=b.user_id AND r.org_id=b.org_id AND r.branch_id=b.id
                        ORDER BY r.trial_no DESC LIMIT 1) AS latest_gate,
                      (SELECT r.metrics FROM strategy_trials r
                        WHERE r.user_id=b.user_id AND r.org_id=b.org_id AND r.branch_id=b.id
                        ORDER BY r.trial_no DESC LIMIT 1) AS latest_metrics
               FROM strategy_branches b JOIN strategy_topics t
                 ON t.user_id=b.user_id AND t.org_id=b.org_id AND t.id=b.topic_id
               WHERE b.user_id=%s AND b.org_id=%s AND b.status='approved'
               ORDER BY b.reviewed_at DESC NULLS LAST""", (uid, org)).fetchall()]
    return [_public(r) for r in rows]


__all__ = ["create_branch", "create_topic", "import_asset", "importable", "imported_assets", "ledger", "library", "list_topics", "recipe", "trial_report"]
