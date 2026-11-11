# -*- coding: utf-8 -*-
"""机构端组合与投后：持仓、监控、论点、退出复核、流水线与结果页。

从 inst_service 拆出，函数名与签名不变；调用方仍从 inst_service 导入。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from psycopg.types.json import Jsonb

from ai.runtime import agent_store
from ai.runtime.agent_store import (
    get_cached_output,
    get_effective_prompt,
    get_latest_output,
    input_hash as agent_input_hash,
    save_output,
)
from services.core.db import get_conn
from services.core.tenant import OrgScope
from services.institution.prompts import (
    CHAIRMAN_MEMO_PROMPT,
    PARTNER_MEMO_PROMPT,
    CHAT_PROMPT,
    INDUSTRY_PROMPT,
    DEBATE_PROMPT,
    DIMENSION_PROMPTS as _DIMENSION_PROMPTS,
    RESEARCH_MEMO_PROMPT,
    RISK_REVIEW_PROMPT,
    ROLE_PROMPTS as _ROLE_PROMPTS,
)
from services.institution import data_platform, inst_ai_store
from services.institution.report import render_research_report, report_filename
from services.marketdata import store as md

from . import repo
from .common import _clip_brief, _evidence_grade, _hash, _iso, _j, _pc, _row_dict, _yi
from .guards import POLICY_VERSION, _audit, _member, _require_role, _uid
from .stages import _record_gate, _record_transition, _set_case_stage, _stage_def, _stage_payload
from .company_service import (
    DEFAULT_NAV,
    MAX_SINGLE_WEIGHT,
    MIN_CASH_RATIO,
    _mapped_industry,
    list_companies,
)
from .execution_service import authorization_for_proposal
from .stages import STAGE_DEFS
from .research_service import (
    _derive_case_stage,
    _idea_questions,
    _opportunity_source,
    get_case,
    get_company,
    ideas_push,
)
from .research_service import *   # noqa: F401,F403
from .debate_service import *    # noqa: F401,F403
from .exit_service import *      # noqa: F401,F403


def portfolio(org_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        pf, positions = repo.portfolio(OrgScope(org_id), conn=conn)
        if not pf:
            return {"portfolio": None, "positions": [], "cash": 0, "nav": 0}
        # 按最新未复权收盘价做一次盯市；没有行情则保留成交时市值。
        for p in positions:
            bar = md.latest_bar(str(p.get("symbol") or ""), adjust="none")
            if bar and bar.get("close") is not None and p.get("qty") is not None:
                p["last_close"] = bar["close"]
                p["market_value"] = float(p["qty"]) * float(bar["close"])
            p["idea"] = _idea_questions(p, "holdings")
    invested = sum(float(p.get("market_value") or 0) for p in positions)
    cash = float(pf["cash"] or 0)
    nav = cash + invested
    for p in positions:
        p["weight"] = (float(p.get("market_value") or 0) / nav) if nav else 0
    industry: dict[str, float] = {}
    for p in positions:
        key = p.get("industry") or "未分类"
        industry[key] = industry.get(key, 0.0) + float(p.get("market_value") or 0)
    out = _row_dict(pf) or {}
    out["nav"] = nav
    out["cash"] = cash
    out["invested"] = invested
    return {
        "portfolio": out,
        "positions": positions,
        "cash": cash,
        "nav": nav,
        "invested": invested,
        "invested_ratio": invested / nav if nav else 0,
        "industry_exposure": {k: v / nav for k, v in industry.items()} if nav else {},
    }


def monitor(org_id: int) -> dict[str, Any]:
    return {"portfolio": portfolio(org_id), **repo.monitor(OrgScope(org_id))}


def exit_advice(org_id: int, symbol: str) -> dict[str, Any]:
    """组合经理 + 风控两个 Agent 的持仓建议，只给一个动作。"""
    data = monitor(org_id)
    positions = (data.get("portfolio") or {}).get("positions") or []
    pos = next((p for p in positions if str(p.get("symbol")) == symbol), None)
    if not pos:
        return {"symbol": symbol, "stance": "hold", "label": "继续持有", "pm": "当前无持仓记录。", "risk": "无敞口，退出不触发硬约束。"}
    company_id = pos.get("company_id")
    with get_conn() as conn:
        if not company_id:
            row = conn.execute(
                "SELECT id FROM inst_company WHERE org_id=%s AND symbol=%s LIMIT 1", (org_id, symbol)
            ).fetchone()
            company_id = int(row["id"]) if row else None
    weight = float(pos.get("weight") or 0) * 100
    cost = float(pos.get("cost") or 0)
    last = float(pos.get("last_close") or pos.get("market_value") or 0)
    pnl = ((last - cost) / cost * 100) if cost > 0 and last > 0 else 0.0
    thesis = next(
        (t for t in (data.get("theses") or []) if int(t.get("company_id") or 0) == int(company_id or 0)),
        None,
    )
    events = [
        e for e in (data.get("events") or [])
        if int(e.get("company_id") or 0) == int(company_id or 0)
    ][:3]
    exits = [
        x for x in (data.get("exits") or [])
        if int(x.get("company_id") or 0) == int(company_id or 0) and str(x.get("status") or "") not in {"closed", "rejected", "cancelled"}
    ]
    exposure = float(((data.get("portfolio") or {}).get("industry_exposure") or {}).get(pos.get("industry") or "", 0)) * 100
    severe = any(str(e.get("severity") or "") in {"high", "critical"} for e in events)
    review_due = str((thesis or {}).get("review_due") or "")[:10]
    overdue = bool(review_due and review_due < date.today().isoformat())
    if exits or severe or overdue or str((thesis or {}).get("status") or "") in {"invalid", "closed"}:
        stance, label = "exit", "平仓"
    elif weight > 10 or pnl < -10:
        stance, label = "trim", "减仓持有"
    else:
        stance, label = "hold", "继续持有"
    raw_event = events[0].get("detail") if events else ""
    event_text = json.dumps(raw_event, ensure_ascii=False) if isinstance(raw_event, (dict, list)) else str(raw_event or "")
    pm = f"仓位 {weight:.1f}%，现价较成本 {pnl:+.1f}%"
    if exits:
        pm += "；已有退出研究案在途"
    elif overdue:
        pm += f"；论点复核已逾期（{review_due}）"
    elif event_text:
        pm += f"；最近事件：{event_text[:36]}"
    elif str((thesis or {}).get("status") or "") in {"invalid", "closed"}:
        pm += "；买入论点已失效"
    if stance == "exit":
        pm += "，建议平仓。"
    elif stance == "trim":
        pm += "，建议减仓持有。"
    else:
        pm += "，建议继续持有。"
    risk = f"单票 {weight:.1f}%"
    risk += "，接近/超过 15% 上限，退出需分批。" if weight > 13 else "，低于 15% 单票上限"
    if exposure:
        risk += f"；行业敞口 {exposure:.1f}%。"
    else:
        risk += "。"
    if stance == "exit":
        risk += "硬约束不阻断平仓，可执行。"
    elif stance == "trim":
        risk += "减仓不触发硬约束。"
    else:
        risk += "当前退出可行性正常。"
    return {
        "symbol": symbol,
        "stance": stance,
        "label": label,
        "pm": pm,
        "risk": risk,
    }


def scan_holdings(org_id: int, *, actor_member_id: int | None = None) -> dict[str, Any]:
    """自动监控：复核到期与持仓价格异常，登记监控事件；7 天内同类不重复。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "risk", "partner")
        rows = conn.execute(
            """
            SELECT * FROM (
              SELECT DISTINCT ON (ps.symbol)
                     ps.symbol, ps.qty, ps.cost, co.id AS company_id, co.name AS company_name
                FROM inst_position_snapshot ps
                JOIN inst_portfolio p ON p.id=ps.portfolio_id
                LEFT JOIN inst_company co ON co.symbol=ps.symbol AND co.org_id=p.org_id
               WHERE p.org_id=%s
               ORDER BY ps.symbol, ps.as_of DESC, ps.id DESC
            ) latest
             WHERE latest.qty > 0
            """,
            (org_id,),
        ).fetchall()
        created: list[dict[str, Any]] = []
        for pos in rows:
            company_id = pos["company_id"]
            if not company_id:
                continue
            ledger = conn.execute(
                "SELECT * FROM inst_thesis_ledger WHERE org_id=%s AND company_id=%s "
                "ORDER BY updated_at DESC LIMIT 1",
                (org_id, int(company_id)),
            ).fetchone()
            due = ledger.get("review_due") if ledger else None
            if due and due < date.today():
                exists = conn.execute(
                    "SELECT 1 FROM inst_monitor_event WHERE org_id=%s AND company_id=%s "
                    "AND type='thesis' AND created_at > NOW() - INTERVAL '7 days' LIMIT 1",
                    (org_id, int(company_id)),
                ).fetchone()
                if not exists:
                    event = conn.execute(
                        "INSERT INTO inst_monitor_event (org_id, company_id, type, severity, detail) "
                        "VALUES (%s,%s,'thesis','warning',%s) RETURNING *",
                        (
                            org_id,
                            int(company_id),
                            _j({"text": f"买入论点复核到期（约定 {due.isoformat()}）"}),
                        ),
                    ).fetchone()
                    created.append(_row_dict(event) or {})
            bar = (
                conn.execute(
                    "SELECT close FROM md_daily_bar WHERE symbol=%s AND adjust='none' "
                    "ORDER BY trade_date DESC LIMIT 1",
                    (str(pos["symbol"]),),
                ).fetchone()
                if pos["symbol"]
                else None
            )
            cost = float(pos.get("cost") or 0)
            close = float(bar["close"]) if bar and bar.get("close") is not None else 0.0
            if cost > 0 and close > 0 and close < cost * 0.9:
                exists = conn.execute(
                    "SELECT 1 FROM inst_monitor_event WHERE org_id=%s AND company_id=%s "
                    "AND type='price' AND created_at > NOW() - INTERVAL '7 days' LIMIT 1",
                    (org_id, int(company_id)),
                ).fetchone()
                if not exists:
                    event = conn.execute(
                        "INSERT INTO inst_monitor_event (org_id, company_id, type, severity, detail) "
                        "VALUES (%s,%s,'price','warning',%s) RETURNING *",
                        (
                            org_id,
                            int(company_id),
                            _j(
                                {
                                    "text": (
                                        f"现价 {close:g} 较成本 {cost:g} 下跌 "
                                        f"{(1 - close / cost) * 100:.1f}%，需复核论点是否仍成立"
                                    )
                                }
                            ),
                        ),
                    ).fetchone()
                    created.append(_row_dict(event) or {})
        if created:
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="monitor.scan",
                object_type="inst_monitor_event",
                object_id=None,
                after={"created": len(created)},
            )
    return {"created": len(created), "events": created}


def refresh_thesis(org_id: int, company_id: int, *, actor_member_id: int | None = None) -> dict[str, Any]:
    """从最近一笔买入议案/研究版本重新生成论点台账；旧台账保留，不自动覆盖。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        company = conn.execute(
            "SELECT id, symbol, name FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        proposal = conn.execute(
            """
            SELECT p.*, v.snapshot
              FROM inst_proposal p
              JOIN LATERAL (
                SELECT snapshot FROM inst_proposal_version
                 WHERE proposal_id=p.id ORDER BY version_no DESC LIMIT 1
              ) v ON TRUE
             WHERE p.org_id=%s AND p.company_id=%s
             ORDER BY p.updated_at DESC LIMIT 1
            """,
            (org_id, company_id),
        ).fetchone()
        if not proposal:
            raise PermissionError("该公司还没有可生成台账的买入议案")
        snapshot = dict(proposal.get("snapshot") or {})
        research = {}
        if snapshot.get("research_version_id"):
            row = conn.execute(
                "SELECT * FROM inst_research_version WHERE id=%s",
                (snapshot["research_version_id"],),
            ).fetchone()
            research = dict(row) if row else {}
        opinion = str(snapshot.get("investment_opinion") or "").strip()
        conclusion = str(research.get("conclusion") or "").strip()
        status_words = {"好", "ok", "OK", "有条件通过", "待补充", "推进审议"}
        if opinion and opinion not in status_words and len(opinion) >= 6:
            thesis = opinion
        elif conclusion and conclusion not in status_words:
            thesis = conclusion
        else:
            first_dim = next(
                (str(d.get("summary") or "").strip() for d in research.get("six_dim") or [] if isinstance(d, dict) and str(d.get("summary") or "").strip()),
                "",
            )
            thesis = first_dim or f"{company['name']} 买入论点待补充"
        # 台账卡只显示一句买入假设：取第一句，最长 60 字；审批状态/短评不上台账。
        thesis = _clip_brief(re.split(r"[；;。]", thesis)[0] or thesis)[:60]
        assumptions: list[str] = []
        for dim in research.get("six_dim") or []:
            if isinstance(dim, dict):
                text = str(dim.get("summary") or dim.get("conclusion") or "").strip()
            else:
                text = str(dim).strip()
            if text:
                assumptions.append(text[:200])
        monitoring = [str(x).strip() for x in (snapshot.get("monitoring") or []) if str(x).strip()]
        kpis = []
        for line in monitoring[:4]:
            name = re.split(r"[<>=≤≥（(→]", line)[0].strip()[:12] or "KPI"
            kpis.append({"name": name, "target": line[:60]})
        falsifiers = monitoring[:2]
        row = conn.execute(
            """
            INSERT INTO inst_thesis_ledger
              (org_id, company_id, proposal_id, symbol, thesis, key_assumptions, kpis, falsifiers,
               review_due, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                org_id,
                company_id,
                int(proposal["id"]),
                company["symbol"],
                thesis[:2000],
                _j(assumptions[:2]),
                _j(kpis),
                _j(falsifiers),
                date.today() + timedelta(days=30),
                actor_member_id,
            ),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.thesis.refresh",
            object_type="inst_thesis_ledger",
            object_id=int(row["id"]),
            after={"company_id": company_id, "proposal_id": int(proposal["id"])},
        )
        out = _row_dict(row) or {}
        out["company_name"] = company["name"]
        out["review_count"] = 0
    return out


def _validated_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是数组")
    return value


def create_thesis(
    org_id: int,
    *,
    company_id: int,
    thesis: str,
    proposal_id: int | None = None,
    key_assumptions: Any = None,
    kpis: Any = None,
    falsifiers: Any = None,
    review_due: str | None = None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """建立买入论点台账：论点、关键假设、KPI、复核时间、推翻条件。"""
    text = str(thesis or "").strip()
    if not text:
        raise ValueError("买入论点不能为空")
    assumptions = _validated_list(key_assumptions, "关键假设")
    kpi_list = _validated_list(kpis, "KPI")
    falsifier_list = _validated_list(falsifiers, "推翻条件")
    for idx, item in enumerate(kpi_list, start=1):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise ValueError(f"第 {idx} 个 KPI 缺少 name")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        company = conn.execute(
            "SELECT id, symbol, name FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        row = conn.execute(
            """
            INSERT INTO inst_thesis_ledger
              (org_id, company_id, proposal_id, symbol, thesis, key_assumptions, kpis, falsifiers,
               review_due, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                org_id,
                company_id,
                proposal_id,
                company["symbol"],
                text,
                _j(assumptions),
                _j(kpi_list),
                _j(falsifier_list),
                review_due or None,
                actor_member_id,
            ),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.thesis.create",
            object_type="inst_thesis_ledger",
            object_id=int(row["id"]),
            after={"company_id": company_id, "proposal_id": proposal_id, "review_due": review_due},
        )
    return _row_dict(row) or {}


def _thesis_row(conn, org_id: int, ledger_id: int) -> dict[str, Any] | None:
    return repo.thesis_row(conn, OrgScope(org_id), ledger_id)


def list_theses(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    return repo.theses(OrgScope(org_id), status=status)


def review_thesis(
    org_id: int,
    ledger_id: int,
    *,
    kpi_status: str,
    conclusion: str,
    note: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if kpi_status not in {"on_track", "at_risk", "broken"}:
        raise ValueError("kpi_status 必须是 on_track/at_risk/broken")
    if conclusion not in {"hold", "reduce", "exit", "invalidate"}:
        raise ValueError("conclusion 必须是 hold/reduce/exit/invalidate")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        ledger, new_status, out = repo.review_thesis(
            conn, OrgScope(org_id), ledger_id,
            kpi_status=kpi_status, conclusion=conclusion, note=note,
            actor_member_id=actor_member_id,
        )
        if not ledger:
            raise LookupError("论点台账不存在")
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.thesis.review",
            object_type="inst_thesis_ledger",
            object_id=ledger_id,
            before={"status": ledger["status"]},
            after={"status": new_status, "kpi_status": kpi_status, "conclusion": conclusion},
        )
    return out or {}


def create_monitor_event(
    org_id: int,
    company_id: int,
    *,
    event_type: str,
    severity: str,
    detail: str,
    actor_member_id: int | None,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "risk", "partner")
        company = conn.execute(
            "SELECT id FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        row = repo.create_monitor_event(
            conn, OrgScope(org_id), company_id, event_type, severity, detail
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.event.create",
            object_type="inst_monitor_event",
            object_id=int(row["id"]),
            after={"company_id": company_id, "type": event_type, "severity": severity},
        )
    return _row_dict(row) or {}


def _position_for_symbol(org_id: int, symbol: str) -> dict[str, Any] | None:
    pf = portfolio(org_id)
    for pos in pf.get("positions") or []:
        if str(pos.get("symbol")) == str(symbol):
            return pos
    return None


def holding_detail(org_id: int, symbol: str) -> dict[str, Any]:
    """v3 单票盘中：持仓 + 论点台账 + 监控事件 + 在途退出。"""
    pf = portfolio(org_id)
    position = next((p for p in pf.get("positions") or [] if str(p.get("symbol")) == symbol), None)
    if not position:
        raise LookupError("持仓不存在")
    company_id = position.get("company_id")
    mon = monitor(org_id)
    events = [e for e in mon.get("events") or [] if str(e.get("symbol")) == symbol]
    theses = [t for t in mon.get("theses") or [] if int(t.get("company_id") or 0) == int(company_id or 0)]
    exits = [
        e for e in mon.get("exits") or []
        if int(e.get("company_id") or 0) == int(company_id or 0)
        and str(e.get("status") or "") not in {"closed", "rejected", "cancelled"}
    ]
    version_no = None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT pv.version_no
              FROM inst_proposal p
              JOIN LATERAL (
                SELECT version_no FROM inst_proposal_version
                 WHERE proposal_id=p.id ORDER BY version_no DESC LIMIT 1
              ) pv ON TRUE
             WHERE p.org_id=%s AND p.company_id=%s
             ORDER BY p.updated_at DESC LIMIT 1
            """,
            (org_id, company_id),
        ).fetchone()
        if row:
            version_no = int(row["version_no"])
    return {
        "symbol": symbol,
        "company_id": company_id,
        "version_no": version_no,
        "position": position,
        "events": events,
        "theses": theses,
        "exits": exits,
        "portfolio": pf.get("portfolio"),
    }


def pipeline(org_id: int) -> dict[str, Any]:
    """v3 六阶段看板：stage 0 为候选线索，1–5 为研究案/议案/执行/持仓。

    生产默认不截断，返回该环节全部项目。仅演示环境可显式设置
    INST_PIPELINE_PER_STAGE=3 限制每环节展示数（0 或负数表示不限制）。
    """
    try:
        configured = int(os.getenv("INST_PIPELINE_PER_STAGE", "0") or "0")
    except ValueError:
        configured = 0
    per_stage = None if configured <= 0 else max(1, min(configured, 200))

    def _take(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return items if per_stage is None else items[:per_stage]
    cases = [_row_dict(r) or {} for r in repo.cases(OrgScope(org_id))]
    with get_conn() as conn:
        # 辩论/议案/授权/持仓是各自独立的事实；流水线按“实际走到的最远阶段”展示，
        # 不再只看 case.stage_no，也避免重复案把下游项目遮住。
        debate_cases = {
            int(r["case_id"])
            for r in conn.execute(
                """
                SELECT DISTINCT d.case_id
                  FROM inst_debate_session d
                  JOIN inst_research_case c ON c.id=d.case_id AND c.org_id=%s
                  JOIN LATERAL (
                    SELECT id FROM inst_research_version
                     WHERE case_id=d.case_id ORDER BY version_no DESC LIMIT 1
                  ) v ON v.id=d.research_version_id
                 WHERE d.status='completed'
                """,
                (org_id,),
            ).fetchall()
        }
        proposal_cases = {
            int(r["case_id"])
            for r in conn.execute(
                """
                SELECT DISTINCT case_id FROM inst_proposal
                 WHERE org_id=%s AND stale_at IS NULL
                   AND status IN ('partner_review','risk_precheck','chairman_review','authorized')
                """,
                (org_id,),
            ).fetchall()
        }
        auth_cases = {
            int(r["case_id"])
            for r in conn.execute(
                """
                SELECT DISTINCT p.case_id
                  FROM inst_authorization a
                  JOIN inst_proposal_version pv ON pv.id=a.proposal_version_id
                  JOIN inst_proposal p ON p.id=pv.proposal_id
                 WHERE p.org_id=%s AND a.status='qualified'
                """,
                (org_id,),
            ).fetchall()
        }
        # 退出研究案属于投后/退出流程，不能回到价值分析列。
        exit_cases = {
            int(r["case_id"])
            for r in conn.execute(
                "SELECT DISTINCT case_id FROM inst_exit_case "
                " WHERE org_id=%s AND status NOT IN ('closed','rejected','cancelled')",
                (org_id,),
            ).fetchall()
        }
        position_symbols = {
            str(r["symbol"])
            for r in conn.execute(
                """
                SELECT ps.symbol FROM inst_position_snapshot ps
                  JOIN inst_portfolio po ON po.id=ps.portfolio_id
                 WHERE po.org_id=%s AND ps.qty > 0
                   AND ps.as_of=(
                     SELECT MAX(p2.as_of) FROM inst_position_snapshot p2
                      WHERE p2.portfolio_id=ps.portfolio_id
                   )
                """,
                (org_id,),
            ).fetchall()
        }
        # 持仓卡直接来自组合持仓；即使买入案已关闭，只要未真正退出，
        # 投资管理阶段仍要显示这只持仓（退出案另在其当前流程阶段显示）。
        holding_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT DISTINCT ON (co.symbol)
                       co.id AS company_id, co.symbol, co.name AS company_name,
                       co.market, co.industry, ps.qty, ps.as_of
                  FROM inst_position_snapshot ps
                  JOIN inst_portfolio po ON po.id=ps.portfolio_id
                  JOIN inst_company co ON co.symbol=ps.symbol AND co.org_id=po.org_id
                 WHERE po.org_id=%s AND ps.qty > 0
                   AND ps.as_of=(
                     SELECT MAX(p2.as_of) FROM inst_position_snapshot p2
                      WHERE p2.portfolio_id=ps.portfolio_id
                   )
                 ORDER BY co.symbol, ps.as_of DESC, ps.id DESC
                """,
                (org_id,),
            ).fetchall()
        ]
    by_stage: dict[int, list[dict[str, Any]]] = {i: [] for i in range(6)}
    selected: dict[int, tuple[tuple[int, str, int], dict[str, Any]]] = {}
    case_company_ids: set[int] = set()
    for case in cases:
        card = _pipeline_card(case)
        case_id = int(case.get("id") or 0)
        company_id = int(card.get("company_id") or 0)
        symbol = str(card.get("symbol") or "")
        stage = int(card.get("stage_no") or 0)
        if case_id in debate_cases:
            stage = max(stage, 2)
        if case_id in proposal_cases:
            stage = max(stage, 3)
        if case_id in auth_cases:
            stage = max(stage, 4)
        card["is_exit"] = case_id in exit_cases
        # 持仓只覆盖已进入执行/管理阶段的案；同一标的的新研究案仍留在研究阶段。
        if symbol and symbol in position_symbols and stage >= 4:
            stage = 5
        stage_def = _stage_def(stage)
        card.update(
            {
                "stage_no": stage,
                "stage_key": stage_def["key"],
                "stage_name": stage_def["name"],
                "gate": stage_def["gate"],
            }
        )
        rank = (stage, str(card.get("updated_at") or ""), case_id)
        if company_id and (company_id not in selected or rank > selected[company_id][0]):
            selected[company_id] = (rank, card)
        if company_id:
            case_company_ids.add(company_id)
    for _, card in selected.values():
        by_stage[int(card["stage_no"])].append(card)
    # 持仓中的标的始终保留一张 05 投资管理卡；退出案同时保留在其当前流程阶段。
    managed_company_ids = {
        int(card["company_id"])
        for card in by_stage[5]
        if card.get("company_id")
    }
    for row in holding_rows:
        company_id = int(row.get("company_id") or 0)
        if not company_id or company_id in managed_company_ids:
            continue
        stage_def = _stage_def(5)
        by_stage[5].append(
            {
                "key": f"holding:{row.get('symbol')}",
                "case_id": None,
                "company_id": company_id,
                "symbol": row.get("symbol"),
                "company_name": row.get("company_name"),
                "industry": row.get("industry"),
                "stage_no": 5,
                "stage_key": stage_def["key"],
                "stage_name": stage_def["name"],
                "gate": stage_def["gate"],
                "version_no": None,
                "version_status": None,
                "conclusion": None,
                "proposal_status": None,
                "owner_member_id": None,
                "updated_at": _iso(row.get("as_of")),
                "stale": False,
                "is_exit": False,
                "is_holding": True,
            }
        )
        managed_company_ids.add(company_id)
        case_company_ids.add(company_id)
    # stage 0：量化推送 + 观察池，排除已建研究案的公司。
    push = ideas_push(org_id, limit=12).get("items") or []
    watch = list_companies(org_id, pool_status="watch", limit=20).get("items") or []
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()
    for source, items in (("push", push), ("watch", watch)):
        for item in items:
            company_id = int(item.get("id") or 0)
            if not company_id or company_id in seen or company_id in case_company_ids:
                continue
            seen.add(company_id)
            candidates.append({
                "key": f"company:{company_id}",
                "company_id": company_id,
                "symbol": item.get("symbol"),
                "company_name": item.get("name"),
                "industry": item.get("industry"),
                "stage_no": 0,
                "stage_key": "find",
                "stage_name": "机会发现",
                "gate": "机会来源",
                "source": source,
                "idea": item.get("idea"),
                "opportunity": _opportunity_source(
                    dict(item), source, item.get("idea")
                ),
                "ref_price": item.get("ref_price") or item.get("last_close"),
                "updated_at": None,
            })
    by_stage[0] = _take(candidates)
    stages = []
    for no in range(6):
        stage = _stage_def(no)
        all_items = by_stage[no]
        items = _take(all_items)
        stages.append({
            "stage_no": no,
            "stage_key": stage["key"],
            "stage_name": stage["name"],
            "gate": stage["gate"],
            "owner": stage["owner"],
            "count": len(items),
            "total_count": len(all_items),
            "truncated": len(items) < len(all_items),
            "items": items,
        })
    return {
        "stages": stages,
        "total": sum(x["count"] for x in stages),
        "total_count": sum(x["total_count"] for x in stages),
    }


def project_result(org_id: int, key: str, *, digest: bool = False) -> dict[str, Any]:
    """v3 结果页聚合：company:<id> 为 01 线索，case:<id> 为 02–06 结果。

    digest=True 时只返回结论与状态摘要，不返回六维全文、证据与辩论明细。
    """
    kind, _, raw_id = str(key).partition(":")
    try:
        entity_id = int(raw_id)
    except ValueError:
        raise LookupError("项目不存在") from None
    if kind == "company":
        company = get_company(org_id, entity_id)
        if not company:
            raise LookupError("公司不存在")
        idea = _idea_questions(company, "watch")
        with get_conn() as conn:
            decision = conn.execute(
                "SELECT * FROM inst_idea_decision WHERE org_id=%s AND company_id=%s ORDER BY id DESC LIMIT 1",
                (org_id, entity_id),
            ).fetchone()
        decision_row = _row_dict(decision) or {}
        source = str(
            decision_row.get("source")
            or ("push" if company.get("research_points") else "watch")
        )
        opportunity = _opportunity_source(
            company, source, decision_row.get("reason")
        )
        return {
            "key": key,
            "stage_no": 0,
            "stage_key": "find",
            "stage_name": "机会发现",
            "company": {k: company.get(k) for k in ("id", "symbol", "name", "market", "industry", "ref_price", "data_status", "pool_status")},
            "idea": idea,
            "opportunity": opportunity,
            "latest_decision": decision_row,
        }
    if kind != "case":
        raise LookupError("项目不存在")
    case = get_case(org_id, entity_id)
    if not case:
        raise LookupError("研究案不存在")
    latest_version = (case.get("versions") or [{}])[0]
    latest_debate = (case.get("debates") or [{}])[0]
    latest_proposal = (case.get("proposals") or [{}])[0]
    authorization = None
    if latest_proposal.get("id"):
        authorization = authorization_for_proposal(org_id, int(latest_proposal["id"]))
    position = _position_for_symbol(org_id, str(case.get("symbol") or ""))
    if digest:
        case = {
            k: case.get(k)
            for k in (
                "id", "company_id", "symbol", "company_name", "market", "industry",
                "ref_price", "stage_no", "stage_key", "stage_name", "stage_state",
                "stage_gate", "updated_at",
            )
        }
        latest_version = {
            k: (latest_version or {}).get(k)
            for k in ("id", "version_no", "status", "conclusion", "locked_at", "superseded_at")
        }
        latest_debate = {
            k: (latest_debate or {}).get(k)
            for k in ("id", "status", "conclusion", "started_at", "ended_at")
        }
        latest_proposal = {
            k: (latest_proposal or {}).get(k)
            for k in (
                "id", "direction", "target_weight", "status", "current_version_no",
                "price_low", "price_high", "stale_at", "updated_at",
            )
        }
        authorization = {
            k: (authorization or {}).get(k)
            for k in ("id", "status", "issued_at", "version_no")
        } if authorization else None
    return {
        "key": key,
        "digest": digest,
        "case": case,
        "stage_no": case.get("stage_no"),
        "stage_key": case.get("stage_key"),
        "stage_name": case.get("stage_name"),
        "stage_state": case.get("stage_state"),
        "stage_gate": case.get("stage_gate"),
        "locks": case.get("locks"),
        "latest_version": latest_version,
        "latest_debate": latest_debate,
        "latest_proposal": latest_proposal,
        "authorization": authorization,
        "position": position,
    }


def playbook() -> dict[str, Any]:
    """v3 流程与权限静态配置；前端不再硬编码阶段/门禁。"""
    return {
        "stages": [
            {
                "stage_no": x["no"],
                "stage_key": x["key"],
                "stage_name": x["name"],
                "gate": x["gate"],
                "owner": x["owner"],
                "steps": {
                    "research": ["行业分析", "六维结论", "一页纸", "研究定稿"],
                    "debate": ["多空立论", "交叉质询", "估值复核", "议案"],
                    "approve": ["议案提交", "合伙人", "风控", "Chairman", "授权"],
                    "execute": ["授权核对", "下单成交", "对账", "持仓更新"],
                    "manage": ["组合总览", "单票盘中", "预警与退出"],
                }.get(x["key"], []),
            }
            for x in STAGE_DEFS
        ],
        "gates": [
            {"key": "partner", "name": "合伙人", "rule": "研究质量与上会判断", "actions": ["复核通过", "退回", "附条件"]},
            {"key": "risk", "name": "风控", "rule": "六项硬约束 · 一票否决", "actions": ["放行", "否决", "有条件放行"]},
            {"key": "chairman", "name": "Chairman", "rule": "资本配置 · 最终拍板", "actions": ["批准", "附条件", "拒绝", "退回"]},
        ],
        "hard_constraints": [
            "单票 ≤ 15%；同行业 / 同一发行人聚合 ≤ 15%",
            "交易后现金 ≥ 10%",
            "研究定稿 / 议案 / 证据校验码一致",
            "授权在有效期内，价格在批准带内",
            "停牌 / 涨跌停 / ST / 限售 / 资金股数",
            "两份议案抢同一笔钱 = 拦",
        ],
        "evidence_grades": [
            {"grade": "A", "source": "公告 / 年报 / 审计报告 / 问询回复 / 交易所披露", "rule": "重大结论至少 1 条 A 级"},
            {"grade": "B", "source": "交易所、监管、行业协会、统计局、央行、海关", "rule": "或 2 条独立 B 级"},
            {"grade": "C", "source": "第三方研究、券商研报、权威财经媒体", "rule": "辅助，不单独支撑重大结论"},
            {"grade": "D", "source": "一般媒体、网络信息、推断、无来源", "rule": "不得支撑买入"},
        ],
        "rules": [
            "提案人不能批自己的案子；同一角色多人时各看各的、按人留痕。",
            "风控否决 = 终局，Chairman 不能越过。",
            "下游只读引用，不复制、不改写；上游变更 → 下游版本作废重跑。",
        ],
    }


def overview(org_id: int, role: str) -> dict[str, Any]:
    data = repo.overview(OrgScope(org_id), role)
    pf = data.get("portfolio") or {}
    nav = float(pf.get("nav") or DEFAULT_NAV)
    cash = float(pf.get("cash") or nav)
    return {
        "org_id": org_id,
        "role": role,
        "companies": data["companies"],
        "active_cases": data["active_cases"],
        "pending_approvals": data["pending_approvals"],
        "my_pending": data["my_pending"],
        "risk_blocks": data["risk_blocks"],
        "monitor_alerts": data["monitor_alerts"],
        "portfolio": {**pf, "invested_ratio": (1 - cash / nav) if nav else 0},
        "data_date": _iso(data["data_date"]) if data.get("data_date") else None,
        "policy": {
            "max_single_weight": MAX_SINGLE_WEIGHT,
            "min_cash_ratio": MIN_CASH_RATIO,
            "nav": nav,
            "policy_version": POLICY_VERSION,
        },
    }


def _pipeline_card(case: dict[str, Any]) -> dict[str, Any]:
    stage_no = case.get("stage_no")
    if stage_no is None:
        stage_no = _derive_case_stage(case)
    stage = _stage_def(stage_no)
    proposals = case.get("proposals") or []
    latest_proposal = proposals[0] if proposals else None
    return {
        "key": f"case:{int(case['id'])}",
        "case_id": int(case["id"]),
        "company_id": int(case["company_id"]),
        "symbol": case.get("symbol"),
        "company_name": case.get("company_name"),
        "industry": case.get("industry"),
        "stage_no": int(stage_no),
        "stage_key": stage["key"],
        "stage_name": stage["name"],
        "gate": stage["gate"],
        "version_no": case.get("version_no"),
        "version_status": case.get("version_status"),
        "conclusion": case.get("conclusion"),
        "proposal_status": (latest_proposal or {}).get("status"),
        "owner_member_id": case.get("created_by"),
        "updated_at": _iso(case.get("updated_at")),
        "stale": bool(latest_proposal and latest_proposal.get("stale_at")),
    }


