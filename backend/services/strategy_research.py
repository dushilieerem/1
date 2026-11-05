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
        c.execute(
            """INSERT INTO strategy_topics
               (id,user_id,org_id,name,objective,universe,benchmark,development_start,development_end,
                validation_start,validation_end,cost_bps,policy_version,max_trials,view_id,
                release_ids,view_manifest_sha256,contract_revision,as_of)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (tid, uid, org, name, str(payload.get("objective") or ""), universe, benchmark,
             dev_start, dev_end, val_start, val_end, cost,
             str(payload.get("policy_version") or "strategy-v5-p0"),
             _int(payload.get("max_trials"), "max_trials", 1, 1000),
             view["view_id"], json.dumps({k: v.get("release") for k, v in view["datasets"].items()
                                          if v.get("release")}, ensure_ascii=False),
             view.get("manifest_sha256") or "", view.get("contract_revision") or "",
             max(dates) if dates else None))
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
    def counts(t):
        if t["outcome"] in ("passed", "failed"):
            return True
        return t["outcome"] in ("error", "timeout") and bool(t.get("metrics"))
    k = sum(1 for t in trials if counts(t))
    return {"topic": _public(topic), "branches": [_public(b) for b in branches],
            "trials": [_public(t) for t in trials], "k": k,
            "ir_threshold": None, "ir_threshold_status": "pending_product_confirmation"}


__all__ = ["create_branch", "create_topic", "ledger", "list_topics", "recipe"]
