"""M3 simulated portfolios: versioned plans, deterministic checks and approval."""
from __future__ import annotations

import json
import uuid
from datetime import date

from services.core.db import get_conn


def _public(row):
    return {k: v for k, v in dict(row).items() if k not in ("user_id", "org_id")}


def _date(value, name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是 YYYY-MM-DD") from None


def _plan(uid, org, plan_id, lock=False):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM portfolio_plans WHERE id=%s AND user_id=%s AND org_id=%s" + (" FOR UPDATE" if lock else ""),
            (plan_id, uid, org)).fetchone()
    if not row:
        raise KeyError(plan_id)
    return dict(row)


def _approved_strategies(uid, org, ids):
    with get_conn() as c:
        rows = c.execute(
            "SELECT id,hypothesis,recipe FROM strategy_branches WHERE user_id=%s AND org_id=%s AND status='approved' AND id = ANY(%s)",
            (uid, org, list(ids))).fetchall()
    return {r["id"]: dict(r) for r in rows}


def _weights(payload):
    items = payload.get("weights")
    if not isinstance(items, list) or not 1 <= len(items) <= 2:
        raise ValueError("组合需选择 1—2 个已入库策略")
    out = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("权重项格式不正确")
        sid = str(item.get("strategy_branch_id") or "").strip()
        if not sid or sid in seen:
            raise ValueError("策略不能为空或重复")
        seen.add(sid)
        try:
            w = float(item.get("weight"))
        except (TypeError, ValueError):
            raise ValueError("权重必须是数值") from None
        if not 0 < w <= 100:
            raise ValueError("每个策略权重必须在 0—100% 之间")
        out.append({"strategy_branch_id": sid, "weight": w})
    return out


def create(uid, org, payload):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("组合名称不能为空")
    weights = _weights(payload)
    approved = _approved_strategies(uid, org, [w["strategy_branch_id"] for w in weights])
    missing = [w["strategy_branch_id"] for w in weights if w["strategy_branch_id"] not in approved]
    if missing:
        raise ValueError("只能选择已入库策略；未入库：" + "、".join(x[:8] for x in missing))
    try:
        capital = float(payload.get("capital"))
    except (TypeError, ValueError):
        raise ValueError("模拟资金必须是数值") from None
    if capital <= 0:
        raise ValueError("模拟资金必须大于 0")
    single = float(payload.get("single_limit", 0.1))
    industry = float(payload.get("industry_limit", 0.3))
    if not 0 < single <= 1 or not 0 < industry <= 1:
        raise ValueError("集中度上限必须在 0—1 之间")
    pid, family = str(uuid.uuid4()), str(uuid.uuid4())
    with get_conn() as c:
        c.execute(
            """INSERT INTO portfolio_plans
               (id,user_id,org_id,family_id,version,name,status,environment,capital,weights,
                single_limit,industry_limit,valid_from,valid_to,note)
               VALUES (%s,%s,%s,%s,1,%s,'draft','simulated',%s,%s::jsonb,%s,%s,%s,%s,%s)""",
            (pid, uid, org, family, name, capital, json.dumps(weights, ensure_ascii=False),
             single, industry,
             _date(payload["valid_from"], "valid_from") if payload.get("valid_from") else None,
             _date(payload["valid_to"], "valid_to") if payload.get("valid_to") else None,
             str(payload.get("note") or "")[:2000]))
        row = c.execute("SELECT * FROM portfolio_plans WHERE id=%s", (pid,)).fetchone()
    return _public(row)


def revise(uid, org, plan_id, payload):
    old = _plan(uid, org, plan_id)
    weights = _weights(payload) if payload.get("weights") else old["weights"]
    approved = _approved_strategies(uid, org, [w["strategy_branch_id"] for w in weights])
    if len(approved) != len(weights):
        raise ValueError("只能选择已入库策略")
    with get_conn() as c:
        version = c.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS v FROM portfolio_plans WHERE user_id=%s AND org_id=%s AND family_id=%s",
            (uid, org, old["family_id"])).fetchone()["v"]
        pid = str(uuid.uuid4())
        c.execute(
            """INSERT INTO portfolio_plans
               (id,user_id,org_id,family_id,version,name,status,environment,capital,weights,
                single_limit,industry_limit,valid_from,valid_to,note)
               VALUES (%s,%s,%s,%s,%s,%s,'draft','simulated',%s,%s::jsonb,%s,%s,%s,%s,%s)""",
            (pid, uid, org, old["family_id"], version, str(payload.get("name") or old["name"]),
             float(payload.get("capital") or old["capital"]), json.dumps(weights, ensure_ascii=False),
             float(payload.get("single_limit") or old["single_limit"]),
             float(payload.get("industry_limit") or old["industry_limit"]),
             _date(payload["valid_from"], "valid_from") if payload.get("valid_from") else old["valid_from"],
             _date(payload["valid_to"], "valid_to") if payload.get("valid_to") else old["valid_to"],
             str(payload.get("note") or "")[:2000]))
        row = c.execute("SELECT * FROM portfolio_plans WHERE id=%s", (pid,)).fetchone()
    return _public(row)


def risk(uid, org, plan_id):
    plan = _plan(uid, org, plan_id)
    weights = plan["weights"] or []
    total = sum(float(w.get("weight") or 0) for w in weights)
    approved = _approved_strategies(uid, org, [w["strategy_branch_id"] for w in weights])
    checks = [
        {"name": "权重和为 100%", "actual": total, "threshold": 100, "passed": abs(total - 100) < 1e-6},
        {"name": "策略均已入库", "actual": len(approved), "threshold": len(weights), "passed": len(approved) == len(weights)},
        {"name": "策略数量 1—2", "actual": len(weights), "threshold": 2, "passed": 1 <= len(weights) <= 2},
        {"name": "单票集中度", "actual": None, "threshold": plan["single_limit"], "passed": None,
         "reason": "目标持仓生成后检查；当前尚无模拟成交"},
        {"name": "行业集中度", "actual": None, "threshold": plan["industry_limit"], "passed": None,
         "reason": "目标持仓生成后检查；当前尚无模拟成交"},
    ]
    hard = [c for c in checks[:3]]
    return {"plan": _public(plan), "checks": checks,
            "passed": all(c["passed"] for c in hard), "complete": False,
            "limitation": "单票/行业集中度需目标持仓；未生成持仓前不冒充通过。"}


def submit(uid, org, plan_id):
    result = risk(uid, org, plan_id)
    if not result["passed"]:
        raise ValueError("风险检查未通过，不能提交审批")
    with get_conn() as c:
        c.execute(
            "UPDATE portfolio_plans SET status='submitted',submitted_by=%s,submitted_at=NOW(),updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status='draft'",
            (uid, plan_id, uid, org))
        row = c.execute("SELECT * FROM portfolio_plans WHERE id=%s", (plan_id,)).fetchone()
    return _public(row)


def approve(uid, org, plan_id):
    plan = _plan(uid, org, plan_id, lock=True)
    if plan["submitted_by"] == uid:
        raise ValueError("提交人不能审批自己的组合")
    if plan["status"] != "submitted":
        raise ValueError("只有待审批版本可以审批")
    result = risk(uid, org, plan_id)
    if not result["passed"]:
        raise ValueError("风险检查未通过，不能审批")
    with get_conn() as c:
        c.execute(
            """UPDATE portfolio_plans SET status='approved',approved_by=%s,approved_at=NOW(),updated_at=NOW()
               WHERE id=%s AND user_id=%s AND org_id=%s""",
            (uid, plan_id, uid, org))
        row = c.execute("SELECT * FROM portfolio_plans WHERE id=%s", (plan_id,)).fetchone()
    return _public(row)


def stop(uid, org, plan_id):
    plan = _plan(uid, org, plan_id)
    if plan["status"] not in ("approved", "submitted"):
        raise ValueError("只有已提交/已批准组合可以停止")
    with get_conn() as c:
        c.execute("UPDATE portfolio_plans SET status='stopped',updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s",
                  (plan_id, uid, org))
        row = c.execute("SELECT * FROM portfolio_plans WHERE id=%s", (plan_id,)).fetchone()
    return _public(row)


def list_plans(uid, org):
    with get_conn() as c:
        rows = c.execute(
            """SELECT p.*, (SELECT COUNT(*) FROM portfolio_nav n WHERE n.plan_id=p.id) AS nav_days
               FROM portfolio_plans p WHERE p.user_id=%s AND p.org_id=%s ORDER BY p.created_at DESC""",
            (uid, org)).fetchall()
    return [_public(r) for r in rows]


def read(uid, org, plan_id):
    plan = _plan(uid, org, plan_id)
    with get_conn() as c:
        nav = [dict(r) for r in c.execute(
            "SELECT trade_date,nav,cash,positions_value,daily_return,drawdown FROM portfolio_nav WHERE plan_id=%s ORDER BY trade_date",
            (plan_id,)).fetchall()]
        orders = [dict(r) for r in c.execute(
            "SELECT trade_date,symbol,side,target_weight,price,quantity,status,reason FROM portfolio_orders WHERE plan_id=%s ORDER BY created_at DESC LIMIT 100",
            (plan_id,)).fetchall()]
    return {"plan": _public(plan), "risk": risk(uid, org, plan_id), "nav": nav, "orders": orders}


def simulate(uid, org, plan_id, trade_date=None):
    """Daily simulation entry. Requires target holdings from approved strategies."""
    plan = _plan(uid, org, plan_id)
    if plan["status"] != "approved":
        raise ValueError("只有已批准组合可以生成模拟调仓")
    raise ValueError("尚无可用目标持仓：当前策略库没有已入库策略/RE 日度持仓接口；不生成假订单")


__all__ = ["approve", "create", "list_plans", "read", "revise", "risk", "simulate", "stop", "submit"]
