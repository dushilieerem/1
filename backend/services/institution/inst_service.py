# -*- coding: utf-8 -*-
"""主观机构端业务服务：公司池、研究、辩论、议案、审批、授权、模拟执行、投后。

边界：
- 这里是业务事实与状态机；AI 只产生建议，不直接改状态（`ai/inst_agents.py` 负责生成）。
- 硬约束在服务端校验：单股 ≤15%、交易后现金 ≥10%、版本一致、无有效批准不得授权。
- 授权是不可变快照；撤销写新行，不 UPDATE 旧行。
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from services.core.db import get_conn
from services.marketdata import store as md

POLICY_VERSION = "demo-v1"
MAX_SINGLE_WEIGHT = 0.15
MIN_CASH_RATIO = 0.10
DEFAULT_NAV = 10_000_000.0


class AiUnavailable(RuntimeError):
    """AI 未配置/不可用；由路由层映射为 503。"""

# 24 个演示研究对象：A 股 8 + 美股 8 + 港股 8（与需求 FR-DIS-01 一致）
DEMO_COMPANIES: tuple[dict[str, Any], ...] = (
    {"symbol": "600519.SH", "name": "贵州茅台", "market": "CN", "industry": "白酒", "tags": ["品牌", "高毛利"], "points": "品牌护城河、提价能力、渠道结构"},
    {"symbol": "000858.SZ", "name": "五粮液", "market": "CN", "industry": "白酒", "tags": ["品牌", "渠道"], "points": "浓香龙头、渠道改革、量价关系"},
    {"symbol": "300750.SZ", "name": "宁德时代", "market": "CN", "industry": "电池", "tags": ["成长", "制造"], "points": "动力电池份额、储能、海外扩张"},
    {"symbol": "600036.SH", "name": "招商银行", "market": "CN", "industry": "银行", "tags": ["零售", "质量"], "points": "零售银行、息差、资产质量"},
    {"symbol": "000333.SZ", "name": "美的集团", "market": "CN", "industry": "家电", "tags": ["制造", "全球化"], "points": "家电龙头、B 端业务、海外"},
    {"symbol": "601318.SH", "name": "中国平安", "market": "CN", "industry": "保险", "tags": ["金融", "寿险"], "points": "寿险改革、代理人、投资端"},
    {"symbol": "000651.SZ", "name": "格力电器", "market": "CN", "industry": "家电", "tags": ["高分红", "制造"], "points": "空调龙头、渠道、治理"},
    {"symbol": "002415.SZ", "name": "海康威视", "market": "CN", "industry": "电子", "tags": ["安防", "AI"], "points": "安防需求、创新业务、海外"},
    {"symbol": "AAPL.O", "name": "Apple", "market": "US", "industry": "消费电子", "tags": ["品牌", "生态"], "points": "服务收入、生态、资本回报"},
    {"symbol": "MSFT.O", "name": "Microsoft", "market": "US", "industry": "软件", "tags": ["云", "AI"], "points": "Azure、Copilot、订阅"},
    {"symbol": "NVDA.O", "name": "NVIDIA", "market": "US", "industry": "半导体", "tags": ["AI", "算力"], "points": "GPU、数据中心、软件生态"},
    {"symbol": "GOOGL.O", "name": "Alphabet", "market": "US", "industry": "互联网", "tags": ["搜索", "广告"], "points": "搜索、云、AI 投入"},
    {"symbol": "AMZN.O", "name": "Amazon", "market": "US", "industry": "电商", "tags": ["云", "零售"], "points": "AWS、履约、广告"},
    {"symbol": "META.O", "name": "Meta", "market": "US", "industry": "互联网", "tags": ["社交", "广告"], "points": "广告效率、Reels、AI"},
    {"symbol": "BRK.B", "name": "Berkshire Hathaway", "market": "US", "industry": "综合", "tags": ["价值", "保险"], "points": "浮存金、资本配置、回购"},
    {"symbol": "JPM.N", "name": "JPMorgan", "market": "US", "industry": "银行", "tags": ["金融", "质量"], "points": "净息差、投行、资本回报"},
    {"symbol": "00700.HK", "name": "腾讯控股", "market": "HK", "industry": "互联网", "tags": ["社交", "游戏"], "points": "微信生态、游戏、广告"},
    {"symbol": "09988.HK", "name": "阿里巴巴", "market": "HK", "industry": "电商", "tags": ["电商", "云"], "points": "电商、云、组织变革"},
    {"symbol": "03690.HK", "name": "美团", "market": "HK", "industry": "本地生活", "tags": ["平台", "履约"], "points": "外卖、到店、竞争"},
    {"symbol": "00941.HK", "name": "中国移动", "market": "HK", "industry": "电信", "tags": ["高分红", "现金流"], "points": "ARPU、资本开支、分红"},
    {"symbol": "02318.HK", "name": "中国平安", "market": "HK", "industry": "保险", "tags": ["金融", "寿险"], "points": "寿险、投资、A/H 价差"},
    {"symbol": "01299.HK", "name": "友邦保险", "market": "HK", "industry": "保险", "tags": ["寿险", "亚洲"], "points": "新业务价值、代理人、区域"},
    {"symbol": "00388.HK", "name": "香港交易所", "market": "HK", "industry": "交易所", "tags": ["平台", "垄断"], "points": "成交额、IPO、互联互通"},
    {"symbol": "00005.HK", "name": "汇丰控股", "market": "HK", "industry": "银行", "tags": ["金融", "高分红"], "points": "净息差、回购、亚洲业务"},
)

SIX_DIM_DEFS: tuple[tuple[str, str, str], ...] = (
    ("industry", "商业与产业", "行业规模、竞争结构、供需与周期"),
    ("moat", "护城河", "品牌、成本、网络、转换成本与可持续性"),
    ("financial", "财务质量", "收入、利润、现金流、ROE 与三表勾稽"),
    ("governance", "CEO 与治理", "资本配置、承诺兑现、关联交易与治理结构"),
    ("valuation", "估值与价格", "PE/PB 分位、DCF 参数、安全边际"),
    ("evidence", "证据与反证", "关键证据、反证条件、待核验事项"),
)


# ---------------------------------------------------------------- 基础工具


def _j(value: Any) -> Jsonb:
    return Jsonb(value)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _row_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, (date, datetime)):
            out[k] = _iso(v)
    return out


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _yi(value: Any) -> str:
    if value is None:
        return "待补充"
    try:
        return f"{float(value) / 1e8:.2f} 亿元"
    except (TypeError, ValueError):
        return "待补充"


def _pc(value: Any) -> str:
    if value is None:
        return "待补充"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "待补充"


def _audit(
    conn,
    *,
    org_id: int,
    actor_member_id: int | None,
    action: str,
    object_type: str,
    object_id: int | None,
    before: Any = None,
    after: Any = None,
    ip: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO inst_audit_event
          (org_id, actor_member_id, action, object_type, object_id, before, after, policy_version, ip)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            org_id,
            actor_member_id,
            action,
            object_type,
            object_id,
            _j(before) if before is not None else None,
            _j(after) if after is not None else None,
            POLICY_VERSION,
            ip,
        ),
    )


def _member(conn, org_id: int, member_id: int | None) -> dict[str, Any] | None:
    if not member_id:
        return None
    row = conn.execute(
        "SELECT id, org_id, role, status, title_cn FROM inst_members WHERE id=%s AND org_id=%s AND status='active'",
        (member_id, org_id),
    ).fetchone()
    return dict(row) if row else None


def _require_role(member: dict[str, Any] | None, *roles: str) -> None:
    if not member or member.get("role") not in roles:
        raise PermissionError("当前角色无权执行该操作")


def _uid() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- 种子


def ensure_and_seed(org_id: int | None = None) -> dict[str, Any]:
    from services.institution.inst_schema import ensure_inst_business_schema

    ensure_inst_business_schema()
    with get_conn() as conn:
        if org_id is None:
            row = conn.execute("SELECT id FROM inst_orgs WHERE code='sunvalley'").fetchone()
            if not row:
                return {"ok": False, "reason": "org_missing"}
            org_id = int(row["id"])
        existing = conn.execute("SELECT COUNT(*) AS n FROM inst_company WHERE org_id=%s", (org_id,)).fetchone()
        if int(existing["n"] or 0) == 0:
            _seed_companies(conn, org_id)
        # 财务/行情晚于公司池种子到达时，刷新数据状态与参考价（不覆盖人工字段）。
        conn.execute(
            """
            UPDATE inst_company c
               SET data_status = 'real'
             WHERE c.market='CN'
               AND EXISTS (
                 SELECT 1 FROM fin_income_statement f
                  WHERE f.symbol=c.symbol AND f.notice_date IS NOT NULL AND f.notice_date <= CURRENT_DATE
               )
            """
        )
        conn.execute(
            """
            UPDATE inst_company c
               SET ref_price = (
                 SELECT b.close FROM md_daily_bar b
                  WHERE b.symbol=c.symbol AND b.adjust='none'
                  ORDER BY b.trade_date DESC LIMIT 1
               )
             WHERE c.market='CN' AND c.ref_price IS NULL
            """
        )
        existing_pf = conn.execute("SELECT COUNT(*) AS n FROM inst_portfolio WHERE org_id=%s", (org_id,)).fetchone()
        if int(existing_pf["n"] or 0) == 0:
            conn.execute(
                "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
                "VALUES (%s,'MAIN','主观价值组合','CNY',%s,%s)",
                (org_id, DEFAULT_NAV, DEFAULT_NAV),
            )
        return {"ok": True, "org_id": org_id}


def _seed_companies(conn, org_id: int) -> None:
    for item in DEMO_COMPANIES:
        symbol = item["symbol"]
        data_status = "missing"
        ref_price = None
        if item["market"] == "CN":
            fin = md.financials(symbol, limit=1)
            data_status = "real" if fin else "partial"
            bar = md.latest_bar(symbol, adjust="none")
            ref_price = bar.get("close") if bar else None
        elif item["market"] == "US":
            # 美股有 parquet 行情，但没有基本面
            data_status = "partial"
        conn.execute(
            """
            INSERT INTO inst_company
              (org_id, symbol, name, market, industry, ref_price, research_points, tags,
               pending_items, data_status, pool_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'research')
            ON CONFLICT (org_id, market, symbol) DO NOTHING
            """,
            (
                org_id,
                symbol,
                item["name"],
                item["market"],
                item["industry"],
                ref_price,
                _j([item["points"]]),
                _j(item["tags"]),
                _j(["待补充：完整财务三表与公告证据"] if data_status != "real" else []),
                data_status,
            ),
        )


# ---------------------------------------------------------------- 驾驶舱 / 公司池


def overview(org_id: int, role: str) -> dict[str, Any]:
    with get_conn() as conn:
        def one(sql: str, params: tuple = ()) -> int:
            row = conn.execute(sql, params).fetchone()
            return int(row["n"] or 0) if row else 0

        companies = one("SELECT COUNT(*) AS n FROM inst_company WHERE org_id=%s", (org_id,))
        cases = one("SELECT COUNT(*) AS n FROM inst_research_case WHERE org_id=%s", (org_id,))
        pending = one(
            "SELECT COUNT(*) AS n FROM inst_proposal WHERE org_id=%s AND status IN "
            "('partner_review','chairman_review','risk_precheck','authorized')",
            (org_id,),
        )
        role_status = {
            "manager": ("draft", "partner_review"),
            "partner": ("partner_review",),
            "chairman": ("chairman_review",),
            "risk": ("risk_precheck",),
            "execution": ("authorized",),
            "monitoring": (),
        }.get(role, ())
        my_pending = one(
            "SELECT COUNT(*) AS n FROM inst_proposal WHERE org_id=%s AND status = ANY(%s)",
            (org_id, list(role_status)),
        ) if role_status else 0
        blocked = one(
            "SELECT COUNT(*) AS n FROM inst_proposal WHERE org_id=%s AND status='frozen'",
            (org_id,),
        )
        alerts = one("SELECT COUNT(*) AS n FROM inst_monitor_event WHERE org_id=%s AND status='open'", (org_id,))
        portfolio = conn.execute(
            "SELECT id, code, name, base_currency, nav, cash FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1",
            (org_id,),
        ).fetchone()
        latest = conn.execute("SELECT MAX(trade_date) AS d FROM md_daily_bar").fetchone()
    pf = _row_dict(portfolio) or {}
    nav = float(pf.get("nav") or DEFAULT_NAV)
    cash = float(pf.get("cash") or nav)
    return {
        "org_id": org_id,
        "role": role,
        "companies": companies,
        "active_cases": cases,
        "pending_approvals": pending,
        "my_pending": my_pending,
        "risk_blocks": blocked,
        "monitor_alerts": alerts,
        "portfolio": {**pf, "invested_ratio": (1 - cash / nav) if nav else 0},
        "data_date": _iso(latest["d"]) if latest else None,
        "policy": {
            "max_single_weight": MAX_SINGLE_WEIGHT,
            "min_cash_ratio": MIN_CASH_RATIO,
            "nav": nav,
            "policy_version": POLICY_VERSION,
        },
    }


def list_companies(
    org_id: int,
    *,
    market: str | None = None,
    q: str | None = None,
    pool_status: str | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT c.*,
               v.pe_ttm, v.pb_mrq, v.float_mv,
               b.close AS last_close, b.trade_date AS last_trade_date
          FROM inst_company c
          LEFT JOIN LATERAL (
            SELECT pe_ttm, pb_mrq, float_mv FROM md_valuation_daily
             WHERE symbol=c.symbol ORDER BY trade_date DESC LIMIT 1
          ) v ON TRUE
          LEFT JOIN LATERAL (
            SELECT close, trade_date FROM md_daily_bar
             WHERE symbol=c.symbol AND adjust='none' ORDER BY trade_date DESC LIMIT 1
          ) b ON TRUE
         WHERE c.org_id=%s
    """
    params: list[Any] = [org_id]
    if market:
        sql += " AND c.market=%s"
        params.append(market)
    if pool_status:
        sql += " AND c.pool_status=%s"
        params.append(pool_status)
    if q:
        sql += " AND (c.symbol ILIKE %s OR c.name ILIKE %s OR c.industry ILIKE %s)"
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    sql += " ORDER BY c.market, c.id"
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    out = []
    for r in rows:
        item = _row_dict(r) or {}
        item["ref_price"] = item.get("last_close") or item.get("ref_price")
        out.append(item)
    return out


def update_company_pool(
    org_id: int,
    company_id: int,
    *,
    pool_status: str,
    reason: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if pool_status not in {"research", "watch", "dropped"}:
        raise ValueError("pool_status 必须是 research/watch/dropped")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        before = conn.execute(
            "SELECT pool_status, drop_reason FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not before:
            raise LookupError("公司不存在")
        conn.execute(
            "UPDATE inst_company SET pool_status=%s, drop_reason=%s, updated_at=NOW() WHERE id=%s AND org_id=%s",
            (pool_status, reason if pool_status == "dropped" else None, company_id, org_id),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="company.pool_status",
            object_type="inst_company",
            object_id=company_id,
            before=dict(before),
            after={"pool_status": pool_status, "drop_reason": reason},
        )
    return {"ok": True, "id": company_id, "pool_status": pool_status}


def get_company(org_id: int, company_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s", (company_id, org_id)
        ).fetchone()
    if not row:
        return None
    company = _row_dict(row) or {}
    symbol = company["symbol"]
    company["market_data"] = {
        "bar": md.latest_bar(symbol, adjust="none"),
        "valuation": md.valuation_latest(symbol),
        "percentile": md.valuation_percentile(symbol, years=3),
        "status": md.status_latest(symbol),
        "risk": md.risk_stats(symbol),
        "industry": md.industry_latest(symbol),
    }
    company["financials"] = md.financials(symbol, limit=8)
    company["cases"] = list_cases(org_id, company_id=company_id)
    return company


# ---------------------------------------------------------------- 研究


def list_cases(org_id: int, *, company_id: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT c.*, co.symbol, co.name AS company_name, co.market, co.industry,
               v.version_no, v.status AS version_status, v.conclusion
          FROM inst_research_case c
          JOIN inst_company co ON co.id=c.company_id
          LEFT JOIN LATERAL (
            SELECT version_no, status, conclusion FROM inst_research_version
             WHERE case_id=c.id ORDER BY version_no DESC LIMIT 1
          ) v ON TRUE
         WHERE c.org_id=%s
    """
    params: list[Any] = [org_id]
    if company_id:
        sql += " AND c.company_id=%s"
        params.append(company_id)
    sql += " ORDER BY c.updated_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) or {} for r in rows]


def create_case(org_id: int, company_id: int, actor_member_id: int | None) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        company = conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s", (company_id, org_id)
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        case_no = f"RC-{date.today():%Y%m%d}-{company['symbol'].split('.')[0]}-{_uid()[:4]}"
        row = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, created_by) "
            "VALUES (%s,%s,%s,'draft',%s) RETURNING *",
            (org_id, company_id, case_no, actor_member_id),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.case.create",
            object_type="inst_research_case",
            object_id=int(row["id"]),
            after={"company_id": company_id, "case_no": case_no},
        )
    return get_case(org_id, int(row["id"]))  # type: ignore[return-value]


def get_case(org_id: int, case_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        case = conn.execute(
            """
            SELECT c.*, co.symbol, co.name AS company_name, co.market, co.industry,
                   co.data_status, co.ref_price
              FROM inst_research_case c
              JOIN inst_company co ON co.id=c.company_id
             WHERE c.id=%s AND c.org_id=%s
            """,
            (case_id, org_id),
        ).fetchone()
        if not case:
            return None
        tasks = conn.execute(
            "SELECT * FROM inst_research_task WHERE case_id=%s ORDER BY id", (case_id,)
        ).fetchall()
        versions = conn.execute(
            "SELECT * FROM inst_research_version WHERE case_id=%s ORDER BY version_no DESC",
            (case_id,),
        ).fetchall()
        latest_version_id = int(versions[0]["id"]) if versions else None
        if latest_version_id:
            evidence = conn.execute(
                "SELECT * FROM inst_evidence WHERE case_id=%s AND version_id=%s ORDER BY id DESC LIMIT 200",
                (case_id, latest_version_id),
            ).fetchall()
        else:
            evidence = conn.execute(
                "SELECT * FROM inst_evidence WHERE case_id=%s ORDER BY id DESC LIMIT 200", (case_id,)
            ).fetchall()
        sessions = conn.execute(
            "SELECT * FROM inst_debate_session WHERE case_id=%s ORDER BY id DESC", (case_id,)
        ).fetchall()
        proposals = conn.execute(
            "SELECT * FROM inst_proposal WHERE case_id=%s ORDER BY id DESC", (case_id,)
        ).fetchall()
    out = _row_dict(case) or {}
    out["tasks"] = [_row_dict(r) for r in tasks]
    out["versions"] = [_row_dict(r) for r in versions]
    out["evidence"] = [_row_dict(r) for r in evidence]
    out["debates"] = [_row_dict(r) for r in sessions]
    out["proposals"] = [_row_dict(r) for r in proposals]
    return out


def _dim_status(has_data: bool) -> str:
    return "done" if has_data else "partial"


def _build_research(company: dict[str, Any], mode: str = "full") -> dict[str, Any]:
    symbol = company["symbol"]
    bar = md.latest_bar(symbol, adjust="none")
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    risk = md.risk_stats(symbol) or {}
    ind = md.industry_latest(symbol) or {}
    fin = md.financials(symbol, limit=8)
    latest_fin = fin[0] if fin else {}
    gross_margin = latest_fin.get("gross_margin")
    if gross_margin is None and latest_fin.get("revenue") and latest_fin.get("gross_profit"):
        gross_margin = latest_fin["gross_profit"] / latest_fin["revenue"]
    has_fin = bool(fin)
    price = (bar or {}).get("close") or company.get("ref_price")
    dims: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def add_ev(title: str, quote: str, kind: str = "fact") -> int:
        # 先占位，写入时再拿真实 ID；用负数占位，_persist_research 替换
        idx = len(evidence)
        evidence.append(
            {
                "title": title,
                "quote": quote,
                "source": "ifind:parquet" if kind in {"market", "financial"} else "eastmoney",
                "evidence_type": kind,
                "as_of": (bar or {}).get("trade_date") or latest_fin.get("notice_date"),
                "hash": _hash([title, quote]),
                "_idx": idx,
            }
        )
        return idx

    ev_price = add_ev(f"{symbol} 最新收盘价", f"{price}", "market") if price else None
    ev_pe = add_ev(
        "PE_TTM 与近 3 年分位",
        f"PE={val.get('pe_ttm'):.2f}，分位={_pc(pct.get('pe_percentile'))}" if val.get("pe_ttm") is not None else "PE 待补充",
        "market",
    ) if val else None
    ev_pb = add_ev(
        "PB_MRQ 与近 3 年分位",
        f"PB={val.get('pb_mrq'):.2f}，分位={_pc(pct.get('pb_percentile'))}" if val.get("pb_mrq") is not None else "PB 待补充",
        "market",
    ) if val else None
    ev_risk = add_ev(
        "近一年波动与最大回撤",
        f"年化波动={_pc(risk.get('annual_vol'))}，最大回撤={_pc(risk.get('max_drawdown'))}",
        "market",
    ) if risk else None
    ev_fin = add_ev(
        "最近报告期财务",
        f"营收={_yi(latest_fin.get('revenue'))}，净利={_yi(latest_fin.get('net_profit'))}，ROE={_pc(latest_fin.get('roe'))}",
        "financial",
    ) if has_fin else None
    ev_gm = add_ev("毛利率", _pc(gross_margin), "financial") if gross_margin is not None else None
    ind_label = company.get("industry") or "待补充"
    ev_ind = add_ev("申万一级行业", f"{ind.get('industry_code') or '待补充'} / {ind_label}", "fact") if ind else None

    def dim(key: str, title: str, question: str, status: str, summary: str, checks: list[str], counter: list[str], evs: list[int | None]) -> None:
        dims.append(
            {
                "key": key,
                "title": title,
                "question": question,
                "status": status,
                "summary": summary,
                "checks": checks,
                "counter": counter,
                "evidence_idx": [x for x in evs if x is not None],
            }
        )

    if mode != "full" and mode not in {d[0] for d in SIX_DIM_DEFS}:
        raise ValueError("mode 必须是 full 或六个维度之一")

    want = {d[0] for d in SIX_DIM_DEFS} if mode == "full" else {mode}
    if "industry" in want:
        dim(
            "industry",
            "商业与产业",
            "行业规模、竞争结构、供需与周期处于什么位置？",
            _dim_status(bool(ind)),
            f"申万一级行业 {ind.get('industry_code') or '待补充'}（{ind_label}）；参考价 {price or '待补充'}。",
            [f"行业归属：{ind.get('industry_code') or '待补充'} / {ind_label}"],
            ["行业分类为当前快照，历史归属需另行核验"],
            [ev_ind],
        )
    if "moat" in want:
        dim(
            "moat",
            "护城河",
            "竞争优势是否真实、可验证、可持续？",
            _dim_status(gross_margin is not None),
            f"毛利率 {round(gross_margin * 100, 2) if gross_margin is not None else '待补充'}%；需结合品牌、成本、网络与转换成本判断。",
            [f"毛利率：{gross_margin if gross_margin is not None else '待补充'}"],
            ["高毛利不等于护城河；需验证定价权与客户留存"],
            [ev_gm],
        )
    if "financial" in want:
        dim(
            "financial",
            "财务质量",
            "收入、利润、现金流与 ROE 是否相互印证？",
            "done" if has_fin else "partial",
            f"最近报告期：营收 {_yi(latest_fin.get('revenue'))}，净利 {_yi(latest_fin.get('net_profit'))}，经营现金流 {_yi(latest_fin.get('operating_cf'))}。",
            [
                f"ROE：{_pc(latest_fin.get('roe'))}",
                f"净利率：{_pc(latest_fin.get('net_margin'))}",
                f"自由现金流：{_yi(latest_fin.get('free_cash_flow'))}",
            ],
            ["财务数据来自公开接口，需与公告原文交叉核验", "应收、存货与资本化需逐项检查"],
            [ev_fin, ev_gm],
        )
    if "governance" in want:
        dim(
            "governance",
            "CEO 与治理",
            "资本配置、承诺兑现与治理结构是否可信？",
            "partial",
            "仅展示治理核验框架，不编造个人履历或违规事实；待核验公告清单另行补充。",
            ["治理结构：待补充", "关联交易：待补充", "分红/回购：待补充"],
            ["未核验前不得把治理判断写成事实"],
            [],
        )
    if "valuation" in want:
        dim(
            "valuation",
            "估值与价格",
            "当前价格隐含了什么预期？安全边际在哪里？",
            "done" if val else "partial",
            f"PE_TTM {val.get('pe_ttm'):.2f}，近 3 年分位 {_pc(pct.get('pe_percentile'))}；PB {val.get('pb_mrq'):.2f}，分位 {_pc(pct.get('pb_percentile'))}。"
            if val.get("pe_ttm") is not None and val.get("pb_mrq") is not None
            else "估值数据待补充。",
            [f"参考价：{price or '待补充'}", f"近一年最大回撤：{risk.get('max_drawdown', '待补充')}"],
            ["分位低不等于便宜；需结合盈利周期与资产质量"],
            [ev_price, ev_pe, ev_pb],
        )
    if "evidence" in want:
        dim(
            "evidence",
            "证据与反证",
            "哪些证据支持论点？哪些事实可能推翻它？",
            "done" if evidence else "partial",
            f"当前收集 {len([e for e in evidence if e])} 条结构化证据；反证条件与待核验事项需人工确认。",
            ["证据必须带来源与时间", "重大结论无证据 ID 不得进入审批包"],
            ["数据缺口本身也是反证：不得补造缺失数据"],
            [ev_risk, ev_fin],
        )

    valuation = None
    if has_fin and latest_fin.get("net_profit") and price:
        # 仅作演示口径：以最新净利为起点，不做目标价
        growth = 0.06
        discount = 0.10
        terminal = 0.03
        fcf = float(latest_fin.get("free_cash_flow") or latest_fin.get("net_profit") or 0)
        shares = (val or {}).get("total_shares")
        shares_source = "total_shares"
        if not shares and price and (val or {}).get("float_mv"):
            # 演示代理：用流通市值/未复权价估算股本；不是总股本口径，页面必须标注。
            shares = float(val["float_mv"]) / float(price)
            shares_source = "float_mv/price_proxy"
        if fcf > 0 and shares:
            value = fcf * (1 + growth) / max(0.01, discount - terminal)
            per_share = value / float(shares)
            valuation = {
                "method": "owner_earnings_proxy",
                "is_demo": True,
                "assumptions": {
                    "revenue_growth": growth,
                    "cash_flow_margin": None,
                    "discount_rate": discount,
                    "terminal_growth": terminal,
                },
                "per_share": per_share,
                "low": per_share * 0.75,
                "base": per_share,
                "high": per_share * 1.25,
                "shares_source": shares_source,
                "note": "演示口径，不是目标价；未计税费、营运资本、汇率与治理折价；股本为估算值。",
            }
    return {
        "dims": dims,
        "evidence": evidence,
        "valuation": valuation,
        "data_gaps": [] if has_fin else ["财务三表未接入或未公告"],
    }


def generate_research(
    org_id: int,
    case_id: int,
    *,
    mode: str = "full",
    actor_member_id: int | None,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        case = conn.execute(
            "SELECT c.*, co.symbol, co.name, co.market, co.industry, co.data_status, co.ref_price "
            "FROM inst_research_case c JOIN inst_company co ON co.id=c.company_id "
            "WHERE c.id=%s AND c.org_id=%s",
            (case_id, org_id),
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        company = dict(case)
        built = _build_research(company, mode=mode)
        # 任务
        tasks = SIX_DIM_DEFS if mode == "full" else tuple(d for d in SIX_DIM_DEFS if d[0] == mode)
        for key, title, _ in tasks:
            conn.execute(
                """
                INSERT INTO inst_research_task (case_id, task_key, title, agent, status, progress, result)
                VALUES (%s,%s,%s,%s,'done',100,%s)
                ON CONFLICT (case_id, task_key) DO UPDATE
                  SET status='done', progress=100, result=EXCLUDED.result, updated_at=NOW()
                """,
                (case_id, key, title, f"AI-{key}", _j(next((d for d in built["dims"] if d["key"] == key), {}))),
            )
        # 证据先落库拿 ID
        ev_ids: list[int] = []
        idx_to_id: dict[int, int] = {}
        for ev in built["evidence"]:
            row = conn.execute(
                """
                INSERT INTO inst_evidence
                  (org_id, case_id, evidence_type, title, quote, source, as_of, hash, added_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    org_id,
                    case_id,
                    ev.get("evidence_type") or "fact",
                    ev["title"],
                    ev.get("quote"),
                    ev["source"],
                    ev.get("as_of"),
                    ev["hash"],
                    actor_member_id,
                ),
            ).fetchone()
            eid = int(row["id"])
            ev_ids.append(eid)
            idx_to_id[int(ev["_idx"])] = eid
        for dim in built["dims"]:
            dim["evidence_ids"] = [idx_to_id.get(i) for i in dim.pop("evidence_idx", []) if i in idx_to_id]
        version_no = conn.execute(
            "SELECT COALESCE(MAX(version_no),0)+1 AS n FROM inst_research_version WHERE case_id=%s",
            (case_id,),
        ).fetchone()["n"]
        conclusion = "有条件通过" if built["data_gaps"] == [] else "待补充"
        row = conn.execute(
            """
            INSERT INTO inst_research_version
              (case_id, version_no, status, six_dim, valuation, conclusion, assumptions,
               counter_evidence, open_questions, evidence_ids, created_by)
            VALUES (%s,%s,'pending_review',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                case_id,
                version_no,
                _j(built["dims"]),
                _j(built["valuation"]),
                conclusion,
                _j([built["valuation"]["assumptions"]] if built["valuation"] else []),
                _j([c for d in built["dims"] for c in d.get("counter", [])]),
                _j(built["data_gaps"]),
                _j(ev_ids),
                actor_member_id,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE inst_evidence SET version_id=%s WHERE id = ANY(%s)",
            (int(row["id"]), ev_ids),
        )
        conn.execute(
            "UPDATE inst_research_case SET stage='pending_review', updated_at=NOW() WHERE id=%s",
            (case_id,),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.generate",
            object_type="inst_research_version",
            object_id=int(row["id"]),
            after={"case_id": case_id, "version_no": version_no, "mode": mode},
        )
    return get_case(org_id, case_id)  # type: ignore[return-value]


def review_research(
    org_id: int,
    version_id: int,
    *,
    decision: str,
    comment: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if decision not in {"approve", "return"}:
        raise ValueError("decision 必须是 approve/return")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        row = conn.execute(
            """
            SELECT v.*, c.id AS case_id, c.created_by AS case_created_by
              FROM inst_research_version v
              JOIN inst_research_case c ON c.id=v.case_id
             WHERE v.id=%s AND c.org_id=%s
            """,
            (version_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("研究版本不存在")
        if decision == "approve":
            conn.execute(
                "UPDATE inst_research_version SET status='approved', frozen_at=NOW(), approved_by=%s, approved_at=NOW() WHERE id=%s",
                (actor_member_id, version_id),
            )
            conn.execute(
                "UPDATE inst_research_case SET stage='approved', updated_at=NOW() WHERE id=%s",
                (row["case_id"],),
            )
        else:
            conn.execute(
                "UPDATE inst_research_version SET status='changed' WHERE id=%s", (version_id,)
            )
            conn.execute(
                "UPDATE inst_research_case SET stage='researching', updated_at=NOW() WHERE id=%s",
                (row["case_id"],),
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"research.review.{decision}",
            object_type="inst_research_version",
            object_id=version_id,
            before={"status": row["status"]},
            after={"decision": decision, "comment": comment},
        )
    return get_case(org_id, int(row["case_id"]))  # type: ignore[return-value]


# ---------------------------------------------------------------- 辩论


def _evidence_payload(conn, evidence_ids: list[int]) -> list[dict[str, Any]]:
    if not evidence_ids:
        return []
    rows = conn.execute(
        "SELECT id, title, quote, source, as_of FROM inst_evidence WHERE id = ANY(%s)", (evidence_ids,)
    ).fetchall()
    return [_row_dict(r) or {} for r in rows]


def _debate_fallback(company: dict[str, Any], evidence: list[dict[str, Any]], valuation: dict[str, Any] | None) -> dict[str, Any]:
    ev_ids = [e["id"] for e in evidence]
    price_note = next((e["quote"] for e in evidence if "收盘价" in e["title"]), "参考价待补充")
    pe_note = next((e["quote"] for e in evidence if "PE" in e["title"]), "估值待补充")
    fin_note = next((e["quote"] for e in evidence if "财务" in e["title"]), "财务待补充")
    bull = [
        {
            "side": "bull",
            "round": 1,
            "claim": f"{company['name']} 的长期竞争力与现金流质量值得持续研究；{fin_note}。",
            "evidence_ids": ev_ids[:4],
            "confidence": 0.62,
            "falsifier": "若收入增速连续两个季度低于行业且现金流恶化，看多假设失效。",
        },
        {
            "side": "bull",
            "round": 2,
            "claim": f"当前估值分位提供了观察窗口：{pe_note}；但这不是买入建议。",
            "evidence_ids": ev_ids[:3],
            "confidence": 0.55,
            "falsifier": "若估值分位上升主要由盈利下修而非价格上涨造成，估值判断失效。",
        },
    ]
    bear = [
        {
            "side": "bear",
            "round": 1,
            "claim": f"证据链仍不完整：{price_note}；财务与公告尚未完成交叉核验，不能把演示口径当成事实。",
            "evidence_ids": ev_ids[:4],
            "confidence": 0.58,
            "falsifier": "若完整财报、公告与行业数据补齐且相互印证，该反方论点减弱。",
        },
        {
            "side": "bear",
            "round": 2,
            "claim": "估值分位低可能反映盈利周期或治理折价，而非安全边际；需用反证条件检验。",
            "evidence_ids": ev_ids[:3],
            "confidence": 0.6,
            "falsifier": "若盈利质量、资本配置与治理记录均通过核验，价值陷阱假设减弱。",
        },
    ]
    chair = {
        "side": "chair",
        "round": 2,
        "claim": "双方均承认证据链尚需补强；结论为「补充研究」，补齐财务与公告后再进入议案。",
        "evidence_ids": ev_ids[:2],
        "confidence": 0.7,
        "falsifier": "若补齐证据后双方仍无法收敛，提交人工裁决。",
    }
    return {"bull": bull, "bear": bear, "chair": [chair]}


def start_debate(
    org_id: int,
    case_id: int,
    *,
    actor_member_id: int | None,
    use_ai: bool = True,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        case = conn.execute(
            """
            SELECT c.*, co.symbol, co.name, co.market, co.industry, co.ref_price
              FROM inst_research_case c JOIN inst_company co ON co.id=c.company_id
             WHERE c.id=%s AND c.org_id=%s
            """,
            (case_id, org_id),
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        version = conn.execute(
            "SELECT * FROM inst_research_version WHERE case_id=%s AND status='approved' ORDER BY version_no DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if not version:
            raise PermissionError("研究未审核通过，不能进入辩论")
        ev_ids = list(version.get("evidence_ids") or [])
        evidence = _evidence_payload(conn, [int(x) for x in ev_ids])
        factpack = {
            "company": _row_dict(case),
            "research_version": _row_dict(version),
            "evidence": evidence,
        }
        session = conn.execute(
            """
            INSERT INTO inst_debate_session
              (case_id, research_version_id, status, agenda_step, factpack, factpack_hash, started_at)
            VALUES (%s,%s,'running',0,%s,%s,NOW()) RETURNING *
            """,
            (case_id, version["id"], _j(factpack), _hash(factpack)),
        ).fetchone()
        args = _debate_fallback(dict(case), evidence, version.get("valuation"))
        if use_ai:
            ai_args = _ai_debate(dict(case), evidence, version.get("valuation"), ev_ids)
            if ai_args:
                args = ai_args
        for side in ("bull", "bear", "chair"):
            for item in args.get(side, []):
                conn.execute(
                    """
                    INSERT INTO inst_debate_argument
                      (session_id, side, round, claim, evidence_ids, confidence, falsifier, valid)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        int(session["id"]),
                        side,
                        int(item.get("round") or 1),
                        str(item.get("claim") or ""),
                        _j(item.get("evidence_ids") or []),
                        float(item.get("confidence") or 0),
                        item.get("falsifier"),
                        True,
                    ),
                )
        conclusion = "补充研究" if not evidence else "推进审议"
        conn.execute(
            "UPDATE inst_debate_session SET status='completed', agenda_step=9, conclusion=%s, ended_at=NOW() WHERE id=%s",
            (conclusion, session["id"]),
        )
        conn.execute(
            "UPDATE inst_research_case SET stage='proposal', updated_at=NOW() WHERE id=%s", (case_id,)
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="debate.complete",
            object_type="inst_debate_session",
            object_id=int(session["id"]),
            after={"conclusion": conclusion, "use_ai": use_ai},
        )
    return get_debate(org_id, int(session["id"]))  # type: ignore[return-value]


def _ai_debate(company, evidence, valuation, ev_ids) -> dict[str, Any] | None:
    try:
        from ai.router import available_task, run_task

        if not available_task("inst.debate"):
            return None
        prompt = {
            "company": {"symbol": company.get("symbol"), "name": company.get("name"), "market": company.get("market")},
            "evidence": [{"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source")} for e in evidence],
            "valuation": valuation,
        }
        out = run_task(
            "inst.debate",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是投资辩论助手。只输出 JSON，结构："
                        '{"bull":[{"claim":"...","evidence_ids":[1],"confidence":0.6,"falsifier":"...","round":1}],'
                        '"bear":[...],"chair":[...]}。'
                        "每条必须引用输入中存在的 evidence id；不给买卖建议、目标价或收益承诺。"
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            variables={"evidence_ids": [int(x) for x in ev_ids]},
        )
        data = json.loads(str(out.get("content") or "{}"))
        if not isinstance(data, dict):
            return None
        valid_ids = {int(x) for x in ev_ids}
        for side in ("bull", "bear", "chair"):
            items = data.get(side)
            if not isinstance(items, list):
                return None
            for item in items:
                ids = [int(x) for x in item.get("evidence_ids") or [] if str(x).isdigit()]
                item["evidence_ids"] = [x for x in ids if x in valid_ids]
                if not item.get("claim"):
                    return None
        # 需求要求至少两轮；模型常全部标 1，这里按顺序补齐第二轮。
        for side in ("bull", "bear"):
            items = data.get(side) or []
            if len(items) >= 2 and all(int(x.get("round") or 1) == 1 for x in items):
                for idx, item in enumerate(items):
                    item["round"] = 2 if idx >= len(items) // 2 else 1
        return data
    except Exception:
        return None


def get_debate(org_id: int, session_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.*, c.id AS case_id, co.symbol, co.name AS company_name, co.market
              FROM inst_debate_session s
              JOIN inst_research_case c ON c.id=s.case_id
              JOIN inst_company co ON co.id=c.company_id
             WHERE s.id=%s AND c.org_id=%s
            """,
            (session_id, org_id),
        ).fetchone()
        if not row:
            return None
        args = conn.execute(
            "SELECT * FROM inst_debate_argument WHERE session_id=%s ORDER BY round, side, id",
            (session_id,),
        ).fetchall()
    out = _row_dict(row) or {}
    out["arguments"] = [_row_dict(r) for r in args]
    return out


# ---------------------------------------------------------------- 议案 / 审批 / 授权


def _current_version(conn, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_proposal_version WHERE proposal_id=%s ORDER BY version_no DESC LIMIT 1",
        (proposal_id,),
    ).fetchone()
    return _row_dict(row)


def _proposal_row(conn, org_id: int, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT p.*, co.symbol, co.name AS company_name, co.market, co.industry, c.case_no
          FROM inst_proposal p
          JOIN inst_company co ON co.id=p.company_id
          JOIN inst_research_case c ON c.id=p.case_id
         WHERE p.id=%s AND p.org_id=%s
        """,
        (proposal_id, org_id),
    ).fetchone()
    return _row_dict(row)


def create_proposal(
    org_id: int,
    case_id: int,
    *,
    actor_member_id: int | None,
    direction: str = "buy",
    target_weight: float = 0.05,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if direction not in {"buy", "sell", "exit"}:
        raise ValueError("direction 必须是 buy/sell/exit")
    if not (0 <= target_weight <= 1):
        raise ValueError("target_weight 必须在 0-1")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        case = conn.execute(
            "SELECT * FROM inst_research_case WHERE id=%s AND org_id=%s", (case_id, org_id)
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        if case["stage"] not in {"proposal", "approved"}:
            raise PermissionError("研究与辩论未完成，不能创建议案")
        version = conn.execute(
            "SELECT * FROM inst_research_version WHERE case_id=%s AND status='approved' ORDER BY version_no DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if not version:
            raise PermissionError("没有已审核通过的研究版本")
        debate = conn.execute(
            "SELECT * FROM inst_debate_session WHERE case_id=%s AND status='completed' ORDER BY id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        snapshot = {
            "research_version_id": int(version["id"]),
            "research_version_no": int(version["version_no"]),
            "debate_session_id": int(debate["id"]) if debate else None,
            "direction": direction,
            "target_weight": target_weight,
            "price_low": None,
            "price_high": None,
            "account": "SIM-001",
            "funding_source": "自有资金",
            "currency": "CNY",
            "fx_rate": 1.0,
            "valid_until": (date.today() + timedelta(days=30)).isoformat(),
            "monitoring": ["季度财报后复核论点", "单股仓位超过 15% 触发复核"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            **(config or {}),
        }
        row = conn.execute(
            """
            INSERT INTO inst_proposal (org_id, case_id, company_id, direction, target_weight, current_version_no, status, created_by)
            VALUES (%s,%s,%s,%s,%s,1,'draft',%s) RETURNING *
            """,
            (org_id, case_id, case["company_id"], direction, target_weight, actor_member_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_proposal_version (proposal_id, version_no, snapshot, status, created_by) "
            "VALUES (%s,1,%s,'draft',%s)",
            (row["id"], _j(snapshot), actor_member_id),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.create",
            object_type="inst_proposal",
            object_id=int(row["id"]),
            after={"case_id": case_id, "target_weight": target_weight},
        )
    return get_proposal(org_id, int(row["id"]))  # type: ignore[return-value]


def list_proposals(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT p.*, co.symbol, co.name AS company_name, co.market,
               v.version_no, v.snapshot, v.status AS version_status,
               a.id AS authorization_id, a.status AS authorization_status
          FROM inst_proposal p
          JOIN inst_company co ON co.id=p.company_id
          LEFT JOIN LATERAL (
            SELECT version_no, snapshot, status, id FROM inst_proposal_version
             WHERE proposal_id=p.id ORDER BY version_no DESC LIMIT 1
          ) v ON TRUE
          LEFT JOIN LATERAL (
            SELECT id, status FROM inst_authorization
             WHERE proposal_version_id=v.id AND status='qualified' ORDER BY id DESC LIMIT 1
          ) a ON TRUE
         WHERE p.org_id=%s
    """
    params: list[Any] = [org_id]
    if status:
        sql += " AND p.status=%s"
        params.append(status)
    sql += " ORDER BY p.updated_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) or {} for r in rows]


def get_proposal(org_id: int, proposal_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            return None
        versions = conn.execute(
            "SELECT * FROM inst_proposal_version WHERE proposal_id=%s ORDER BY version_no DESC",
            (proposal_id,),
        ).fetchall()
        version = _row_dict(versions[0]) if versions else None
        approvals = []
        auths = []
        if version:
            approvals = conn.execute(
                "SELECT * FROM inst_approval WHERE proposal_version_id=%s ORDER BY decided_at",
                (version["id"],),
            ).fetchall()
            auths = conn.execute(
                "SELECT * FROM inst_authorization WHERE proposal_version_id=%s ORDER BY id DESC",
                (version["id"],),
            ).fetchall()
    proposal["versions"] = [_row_dict(r) for r in versions]
    proposal["current_version"] = version
    proposal["approvals"] = [_row_dict(r) for r in approvals]
    proposal["authorizations"] = [_row_dict(r) for r in auths]
    return proposal


def partner_review(
    org_id: int,
    proposal_id: int,
    *,
    decision: str,
    comment: str | None,
    updates: dict[str, Any] | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if decision not in {"approve", "return"}:
        raise ValueError("decision 必须是 approve/return")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "partner")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        snapshot = dict(current.get("snapshot") or {})
        version_id = int(current["id"])
        version_no = int(current["version_no"])
        if updates:
            snapshot.update(updates)
            version_no += 1
            row = conn.execute(
                "INSERT INTO inst_proposal_version (proposal_id, version_no, snapshot, status, created_by) "
                "VALUES (%s,%s,%s,'partner_submitted',%s) RETURNING id",
                (proposal_id, version_no, _j(snapshot), actor_member_id),
            ).fetchone()
            version_id = int(row["id"])
        conn.execute(
            """
            INSERT INTO inst_approval (proposal_version_id, step, approver_member_id, decision, comment, policy_version)
            VALUES (%s,'partner',%s,%s,%s,%s)
            ON CONFLICT (proposal_version_id, step) DO UPDATE
              SET approver_member_id=EXCLUDED.approver_member_id, decision=EXCLUDED.decision,
                  comment=EXCLUDED.comment, decided_at=NOW()
            """,
            (version_id, actor_member_id, "approve" if decision == "approve" else "return", comment, POLICY_VERSION),
        )
        new_status = "chairman_review" if decision == "approve" else "partner_review"
        conn.execute(
            "UPDATE inst_proposal SET status=%s, current_version_no=%s, updated_at=NOW() WHERE id=%s",
            (new_status, version_no, proposal_id),
        )
        conn.execute(
            "UPDATE inst_proposal_version SET status=%s WHERE id=%s",
            ("partner_submitted" if decision == "approve" else "draft", version_id),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"proposal.partner.{decision}",
            object_type="inst_proposal",
            object_id=proposal_id,
            before={"status": proposal["status"], "version_no": current["version_no"]},
            after={"status": new_status, "version_no": version_no, "comment": comment},
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def chairman_review(
    org_id: int,
    proposal_id: int,
    *,
    decision: str,
    comment: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if decision not in {"approve", "conditional", "return", "reject"}:
        raise ValueError("decision 必须是 approve/conditional/return/reject")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        if int(proposal.get("created_by") or 0) == int(actor_member_id or 0):
            raise PermissionError("提案人不得审批自己的议案")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        partner = conn.execute(
            "SELECT * FROM inst_approval WHERE proposal_version_id=%s AND step='partner'",
            (current["id"],),
        ).fetchone()
        if not partner or partner["decision"] not in {"approve"}:
            raise PermissionError("合伙人复核未通过，不能提交 Chairman")
        blocked = conn.execute(
            "SELECT 1 FROM inst_approval WHERE proposal_version_id=%s AND step='risk_precheck' AND decision IN ('block','veto')",
            (current["id"],),
        ).fetchone()
        if blocked:
            raise PermissionError("独立风控已阻断，Chairman 不能批准")
        conn.execute(
            """
            INSERT INTO inst_approval (proposal_version_id, step, approver_member_id, decision, comment, policy_version)
            VALUES (%s,'chairman',%s,%s,%s,%s)
            ON CONFLICT (proposal_version_id, step) DO UPDATE
              SET approver_member_id=EXCLUDED.approver_member_id, decision=EXCLUDED.decision,
                  comment=EXCLUDED.comment, decided_at=NOW()
            """,
            (current["id"], actor_member_id, "approve" if decision in {"approve", "conditional"} else decision, comment, POLICY_VERSION),
        )
        status = "risk_precheck" if decision in {"approve", "conditional"} else ("rejected" if decision == "reject" else "partner_review")
        conn.execute("UPDATE inst_proposal SET status=%s, updated_at=NOW() WHERE id=%s", (status, proposal_id))
        if decision in {"approve", "conditional"}:
            conn.execute("UPDATE inst_proposal_version SET status='chairman_approved' WHERE id=%s", (current["id"],))
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"proposal.chairman.{decision}",
            object_type="inst_proposal",
            object_id=proposal_id,
            before={"status": proposal["status"]},
            after={"status": status, "comment": comment},
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def _risk_checks(conn, org_id: int, proposal: dict[str, Any], version: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = version.get("snapshot") or {}
    target = float(snapshot.get("target_weight") or proposal.get("target_weight") or 0)
    portfolio = conn.execute(
        "SELECT nav, cash FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
    ).fetchone()
    nav = float(portfolio["nav"] or DEFAULT_NAV) if portfolio else DEFAULT_NAV
    cash = float(portfolio["cash"] or nav) if portfolio else nav
    amount = target * nav
    cash_after = (cash - amount) / nav if nav else 0
    valid_until = snapshot.get("valid_until")
    expired = bool(valid_until and str(valid_until)[:10] < date.today().isoformat())
    checks = [
        {
            "key": "single_weight",
            "label": "单股目标仓位 ≤ 15%",
            "threshold": MAX_SINGLE_WEIGHT,
            "value": target,
            "status": "pass" if target <= MAX_SINGLE_WEIGHT else "block",
        },
        {
            "key": "cash_after",
            "label": "交易后现金 ≥ 10%",
            "threshold": MIN_CASH_RATIO,
            "value": cash_after,
            "status": "pass" if cash_after >= MIN_CASH_RATIO else "block",
        },
        {
            "key": "version",
            "label": "研究/议案版本一致",
            "threshold": None,
            "value": f"research={snapshot.get('research_version_id')} proposal={version.get('version_no')}",
            "status": "pass" if snapshot.get("research_version_id") else "block",
        },
        {
            "key": "validity",
            "label": "审批有效期",
            "threshold": valid_until,
            "value": date.today().isoformat(),
            "status": "block" if expired else "pass",
        },
        {
            "key": "price_range",
            "label": "价格区间合法",
            "threshold": None,
            "value": f"{snapshot.get('price_low')} - {snapshot.get('price_high')}",
            "status": (
                "pass"
                if not (
                    snapshot.get("price_low") is not None
                    and snapshot.get("price_high") is not None
                    and float(snapshot["price_low"]) > float(snapshot["price_high"])
                )
                else "block"
            ),
        },
    ]
    return checks


def risk_check(
    org_id: int,
    proposal_id: int,
    *,
    actor_member_id: int | None,
    comment: str | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "risk")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        checks = _risk_checks(conn, org_id, proposal, current)
        blocked = any(c["status"] == "block" for c in checks)
        decision = "block" if blocked else "pass"
        conn.execute(
            """
            INSERT INTO inst_approval (proposal_version_id, step, approver_member_id, decision, comment, policy_version)
            VALUES (%s,'risk_precheck',%s,%s,%s,%s)
            ON CONFLICT (proposal_version_id, step) DO UPDATE
              SET approver_member_id=EXCLUDED.approver_member_id, decision=EXCLUDED.decision,
                  comment=EXCLUDED.comment, decided_at=NOW()
            """,
            (current["id"], actor_member_id, decision, comment, POLICY_VERSION),
        )
        if blocked:
            conn.execute(
                "UPDATE inst_proposal SET status='frozen', updated_at=NOW() WHERE id=%s", (proposal_id,)
            )
            conn.execute("UPDATE inst_proposal_version SET status='revoked' WHERE id=%s", (current["id"],))
        else:
            conn.execute(
                "UPDATE inst_proposal SET status='risk_precheck', updated_at=NOW() WHERE id=%s", (proposal_id,)
            )
            conn.execute("UPDATE inst_proposal_version SET status='risk_passed' WHERE id=%s", (current["id"],))
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"proposal.risk.{decision}",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={"checks": checks, "comment": comment},
        )
    out = get_proposal(org_id, proposal_id) or {}
    out["risk_checks"] = checks
    return out


def authorize(org_id: int, proposal_id: int, *, actor_member_id: int | None) -> dict[str, Any]:
    with get_conn() as conn:
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        approvals = {
            r["step"]: dict(r)
            for r in conn.execute(
                "SELECT * FROM inst_approval WHERE proposal_version_id=%s", (current["id"],)
            ).fetchall()
        }
        if approvals.get("partner", {}).get("decision") != "approve":
            raise PermissionError("缺少合伙人批准")
        if approvals.get("chairman", {}).get("decision") not in {"approve", "conditional"}:
            raise PermissionError("缺少 Chairman 批准")
        risk = approvals.get("risk_precheck", {})
        if risk.get("decision") != "pass":
            raise PermissionError("执行前风控复核未通过")
        if proposal["status"] == "frozen":
            raise PermissionError("风控冻结期间不能生成授权")
        snapshot = {
            "authorization_id": None,
            "proposal_id": proposal_id,
            "proposal_version_id": int(current["id"]),
            "proposal_version_no": int(current["version_no"]),
            "research_version_id": (current.get("snapshot") or {}).get("research_version_id"),
            "direction": proposal["direction"],
            "target_weight": (current.get("snapshot") or {}).get("target_weight", proposal["target_weight"]),
            "price_low": (current.get("snapshot") or {}).get("price_low"),
            "price_high": (current.get("snapshot") or {}).get("price_high"),
            "account": (current.get("snapshot") or {}).get("account"),
            "funding_source": (current.get("snapshot") or {}).get("funding_source"),
            "currency": (current.get("snapshot") or {}).get("currency"),
            "fx_rate": (current.get("snapshot") or {}).get("fx_rate"),
            "valid_until": (current.get("snapshot") or {}).get("valid_until"),
            "conditions": (current.get("snapshot") or {}).get("monitoring") or [],
            "policy_version": POLICY_VERSION,
            "issued_at": datetime.now().isoformat(timespec="seconds"),
        }
        row = conn.execute(
            "INSERT INTO inst_authorization (proposal_version_id, approval_id, snapshot, status) VALUES (%s,%s,%s,'qualified') RETURNING *",
            (current["id"], risk.get("id"), _j(snapshot)),
        ).fetchone()
        snapshot["authorization_id"] = int(row["id"])
        conn.execute(
            "UPDATE inst_authorization SET snapshot=%s WHERE id=%s", (_j(snapshot), row["id"])
        )
        conn.execute(
            "UPDATE inst_proposal SET status='authorized', updated_at=NOW() WHERE id=%s", (proposal_id,)
        )
        conn.execute("UPDATE inst_proposal_version SET status='authorized' WHERE id=%s", (current["id"],))
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.authorize",
            object_type="inst_authorization",
            object_id=int(row["id"]),
            after=snapshot,
        )
    return get_proposal(org_id, proposal_id)  # type: ignore[return-value]


def list_authorizations(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT a.*, p.id AS proposal_id, p.company_id, co.symbol, co.name AS company_name,
               v.version_no, v.snapshot AS version_snapshot
          FROM inst_authorization a
          JOIN inst_proposal_version v ON v.id=a.proposal_version_id
          JOIN inst_proposal p ON p.id=v.proposal_id
          JOIN inst_company co ON co.id=p.company_id
         WHERE p.org_id=%s
    """
    params: list[Any] = [org_id]
    if status:
        sql += " AND a.status=%s"
        params.append(status)
    sql += " ORDER BY a.issued_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) or {} for r in rows]


# ---------------------------------------------------------------- 模拟执行 / 组合


def execute_authorization(
    org_id: int,
    authorization_id: int,
    *,
    actor_member_id: int | None,
    price: float | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "execution")
        row = conn.execute(
            """
            SELECT a.*, v.snapshot AS version_snapshot, p.id AS proposal_id, p.company_id, p.direction,
                   co.symbol, co.name AS company_name
              FROM inst_authorization a
              JOIN inst_proposal_version v ON v.id=a.proposal_version_id
              JOIN inst_proposal p ON p.id=v.proposal_id
              JOIN inst_company co ON co.id=p.company_id
             WHERE a.id=%s AND p.org_id=%s
            """,
            (authorization_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("授权不存在")
        auth = dict(row)
        if auth["status"] != "qualified":
            raise PermissionError(f"授权状态为 {auth['status']}，不可执行")
        existing = conn.execute(
            "SELECT * FROM inst_order WHERE authorization_id=%s", (authorization_id,)
        ).fetchone()
        if existing:
            return {"ok": True, "idempotent": True, "order": _row_dict(existing)}
        snapshot = auth.get("snapshot") or {}
        valid_until = snapshot.get("valid_until")
        if valid_until and str(valid_until)[:10] < date.today().isoformat():
            raise PermissionError("授权已过期")
        portfolio = conn.execute(
            "SELECT * FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
        ).fetchone()
        if not portfolio:
            raise LookupError("组合不存在")
        bar = md.latest_bar(auth["symbol"], adjust="none")
        px = float(price or (bar or {}).get("close") or 0)
        if px <= 0:
            raise ValueError("没有可用的成交价")
        low = snapshot.get("price_low")
        high = snapshot.get("price_high")
        if low is not None and px < float(low):
            raise PermissionError(f"成交价 {px} 低于授权下限 {low}")
        if high is not None and px > float(high):
            raise PermissionError(f"成交价 {px} 高于授权上限 {high}")
        nav = float(portfolio["nav"] or DEFAULT_NAV)
        cash = float(portfolio["cash"] or nav)
        target = float(snapshot.get("target_weight") or 0)
        direction = auth["direction"]
        pos = None
        if direction in {"sell", "exit"}:
            pos = conn.execute(
                "SELECT qty, cost FROM inst_position_snapshot WHERE portfolio_id=%s AND symbol=%s ORDER BY as_of DESC LIMIT 1",
                (portfolio["id"], auth["symbol"]),
            ).fetchone()
            if not pos or float(pos["qty"]) <= 0:
                raise PermissionError("没有可卖持仓")
            pos_qty = float(pos["qty"])
            # target=0 表示清仓；否则按目标权重减持，但不允许超过现有持仓。
            qty = pos_qty if target <= 0 else min(pos_qty, math.floor(target * nav / px / 100) * 100)
        else:
            qty = math.floor(target * nav / px / 100) * 100
        if qty <= 0:
            raise ValueError("目标仓位不足以形成一手")
        if direction in {"buy"}:
            cost = qty * px
            fee = cost * 0.0003
            if cost + fee > cash:
                raise PermissionError("现金不足，无法执行")
            new_cash = cash - cost - fee
            side = "buy"
        else:
            proceeds = qty * px
            fee = proceeds * 0.0003
            new_cash = cash + proceeds - fee
            side = "sell"
        order = conn.execute(
            """
            INSERT INTO inst_order (authorization_id, portfolio_id, symbol, side, qty, price, status, idempotency_key, filled_at)
            VALUES (%s,%s,%s,%s,%s,%s,'filled',%s,NOW()) RETURNING *
            """,
            (authorization_id, portfolio["id"], auth["symbol"], side, qty, px, f"auth-{authorization_id}"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_fill (order_id, qty, price, fee) VALUES (%s,%s,%s,%s)",
            (order["id"], qty, px, fee),
        )
        conn.execute(
            "UPDATE inst_portfolio SET cash=%s, updated_at=NOW() WHERE id=%s", (new_cash, portfolio["id"])
        )
        # 更新持仓快照（按最新交易日）
        today = date.today()
        prev = conn.execute(
            "SELECT qty, cost FROM inst_position_snapshot WHERE portfolio_id=%s AND symbol=%s ORDER BY as_of DESC LIMIT 1",
            (portfolio["id"], auth["symbol"]),
        ).fetchone()
        prev_qty = float(prev["qty"]) if prev else 0.0
        prev_cost = float(prev["cost"]) if prev else 0.0
        if side == "buy":
            new_qty = prev_qty + qty
            new_cost = (prev_qty * prev_cost + qty * px) / new_qty if new_qty else 0
        else:
            new_qty = prev_qty - qty
            new_cost = prev_cost
        mv = new_qty * px
        weight = mv / nav if nav else 0
        conn.execute(
            """
            INSERT INTO inst_position_snapshot (portfolio_id, symbol, qty, cost, market_value, weight, as_of)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (portfolio_id, symbol, as_of) DO UPDATE
              SET qty=EXCLUDED.qty, cost=EXCLUDED.cost, market_value=EXCLUDED.market_value, weight=EXCLUDED.weight
            """,
            (portfolio["id"], auth["symbol"], new_qty, new_cost, mv, weight, today),
        )
        conn.execute("UPDATE inst_authorization SET status='filled' WHERE id=%s", (authorization_id,))
        conn.execute(
            "UPDATE inst_proposal SET status='executed', updated_at=NOW() WHERE id=%s", (auth["proposal_id"],)
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="authorization.execute",
            object_type="inst_order",
            object_id=int(order["id"]),
            after={"symbol": auth["symbol"], "side": side, "qty": qty, "price": px, "fee": fee},
        )
    return {"ok": True, "idempotent": False, "order": _row_dict(order), "cash": new_cash}


def portfolio(org_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        pf = conn.execute(
            "SELECT * FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
        ).fetchone()
        if not pf:
            return {"portfolio": None, "positions": [], "cash": 0, "nav": 0}
        latest = conn.execute(
            "SELECT MAX(as_of) AS d FROM inst_position_snapshot WHERE portfolio_id=%s", (pf["id"],)
        ).fetchone()
        positions = []
        if latest and latest["d"]:
            rows = conn.execute(
                """
                SELECT ps.*, co.id AS company_id, co.name, co.industry, co.market
                  FROM inst_position_snapshot ps
                  LEFT JOIN inst_company co ON co.symbol=ps.symbol AND co.org_id=%s
                 WHERE ps.portfolio_id=%s AND ps.as_of=%s AND ps.qty > 0
                 ORDER BY ps.market_value DESC
                """,
                (org_id, pf["id"], latest["d"]),
            ).fetchall()
            positions = [_row_dict(r) or {} for r in rows]
            # 按最新未复权收盘价做一次盯市；没有行情则保留成交时市值。
            for p in positions:
                bar = md.latest_bar(str(p.get("symbol") or ""), adjust="none")
                if bar and bar.get("close") is not None and p.get("qty") is not None:
                    p["last_close"] = bar["close"]
                    p["market_value"] = float(p["qty"]) * float(bar["close"])
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
    with get_conn() as conn:
        events = conn.execute(
            "SELECT e.*, co.symbol, co.name AS company_name FROM inst_monitor_event e "
            "LEFT JOIN inst_company co ON co.id=e.company_id WHERE e.org_id=%s ORDER BY e.created_at DESC LIMIT 50",
            (org_id,),
        ).fetchall()
        exits = conn.execute(
            "SELECT x.*, co.symbol, co.name AS company_name FROM inst_exit_case x "
            "JOIN inst_company co ON co.id=x.company_id WHERE x.org_id=%s ORDER BY x.created_at DESC LIMIT 50",
            (org_id,),
        ).fetchall()
    return {
        "portfolio": portfolio(org_id),
        "events": [_row_dict(r) for r in events],
        "exits": [_row_dict(r) for r in exits],
    }


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
        _require_role(member, "manager", "risk", "monitoring", "partner")
        row = conn.execute(
            "INSERT INTO inst_monitor_event (org_id, company_id, type, severity, detail) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (org_id, company_id, event_type, severity, _j({"text": detail})),
        ).fetchone()
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


# ---------------------------------------------------------------- AI 只读辅助


def _ai_task(task_id: str, payload: dict[str, Any], system: str) -> dict[str, Any]:
    try:
        from ai.router import available_task, run_task
    except Exception as exc:  # pragma: no cover - 依赖缺失
        raise AiUnavailable(f"AI 路由层不可用：{exc}") from exc
    if not available_task(task_id):
        raise AiUnavailable("AI 未配置（缺少 LLM 网关或 Key）")
    out = run_task(
        task_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    data = out.get("data")
    if isinstance(data, dict):
        return data
    return {"summary": str(out.get("content") or "")}


def ai_research_memo(org_id: int, case_id: int) -> dict[str, Any]:
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    version = (case.get("versions") or [{}])[0]
    payload = {
        "company": {k: case.get(k) for k in ("symbol", "company_name", "market", "industry", "ref_price")},
        "version": {k: version.get(k) for k in ("version_no", "status", "conclusion", "valuation", "six_dim")},
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source"), "as_of": e.get("as_of")}
            for e in (case.get("evidence") or [])
        ],
    }
    data = _ai_task(
        "inst.research_memo",
        payload,
        "你是机构研究一页纸助手。只使用输入中的公司、六维与证据；结论必须可回源；"
        "数据不足写待补充；不给买卖建议、目标价或收益承诺。只输出 JSON："
        '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。',
    )
    return {"memo": data, "task": "inst.research_memo", "version_no": version.get("version_no")}


def ai_risk_review(org_id: int, proposal_id: int) -> dict[str, Any]:
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    payload = {
        "proposal": {k: proposal.get(k) for k in ("id", "status", "direction", "target_weight", "symbol", "company_name")},
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "checks": None,
        "policy": {"max_single_weight": MAX_SINGLE_WEIGHT, "min_cash_ratio": MIN_CASH_RATIO, "policy_version": POLICY_VERSION},
    }
    # 用真实检查项；避免在 AI 侧重算。
    with get_conn() as conn:
        proposal_row = _proposal_row(conn, org_id, proposal_id)
        current = _current_version(conn, proposal_id)
        checks = _risk_checks(conn, org_id, proposal_row or proposal, current or version)
    payload["checks"] = checks
    data = _ai_task(
        "inst.risk_review",
        payload,
        "你是独立风控复核助手。只依据输入中的检查项与政策阈值；"
        "对通过/警告/阻断给出解释，但不得改变状态；不给买卖建议。只输出 JSON："
        '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。',
    )
    return {"memo": data, "task": "inst.risk_review", "checks": checks}


def ai_chairman_memo(org_id: int, proposal_id: int) -> dict[str, Any]:
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    payload = {
        "proposal": {k: proposal.get(k) for k in ("id", "status", "direction", "target_weight", "symbol", "company_name")},
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "approvals": proposal.get("approvals") or [],
        "authorizations": proposal.get("authorizations") or [],
        "policy": {"max_single_weight": MAX_SINGLE_WEIGHT, "min_cash_ratio": MIN_CASH_RATIO, "policy_version": POLICY_VERSION},
    }
    data = _ai_task(
        "inst.chairman_memo",
        payload,
        "你是 Chairman 审议辅助助手。只依据输入中的议案、审批与政策；"
        "不得修改仓位、不得解除风控阻断、不得生成订单；不给目标价或收益承诺。只输出 JSON："
        '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。',
    )
    return {"memo": data, "task": "inst.chairman_memo", "version_no": version.get("version_no")}


def create_exit_case(
    org_id: int,
    company_id: int,
    *,
    reason_type: str,
    memo: str,
    actor_member_id: int | None,
) -> dict[str, Any]:
    allowed = {"thesis_invalid", "valuation", "better_allocation", "portfolio_constraint", "other"}
    if reason_type not in allowed:
        raise ValueError("reason_type 不合法")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner", "monitoring")
        pos = conn.execute(
            """
            SELECT ps.id, ps.portfolio_id, ps.symbol, ps.qty
              FROM inst_position_snapshot ps
              JOIN inst_portfolio p ON p.id=ps.portfolio_id
             WHERE p.org_id=%s AND ps.symbol=(
               SELECT symbol FROM inst_company WHERE id=%s AND org_id=%s
             ) AND ps.qty > 0
             ORDER BY ps.as_of DESC LIMIT 1
            """,
            (org_id, company_id, org_id),
        ).fetchone()
        if not pos:
            raise PermissionError("该标的不在持仓中，不能发起退出研究")
        row = conn.execute(
            "INSERT INTO inst_exit_case (org_id, company_id, position_id, reason_type, memo, status) "
            "VALUES (%s,%s,%s,%s,%s,'draft') RETURNING *",
            (org_id, company_id, pos["id"], reason_type, memo),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.exit.create",
            object_type="inst_exit_case",
            object_id=int(row["id"]),
            after={"company_id": company_id, "reason_type": reason_type},
        )
    return _row_dict(row) or {}


def list_audit(org_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM inst_audit_event WHERE org_id=%s ORDER BY id DESC LIMIT %s",
            (org_id, max(1, min(limit, 500))),
        ).fetchall()
    return [_row_dict(r) or {} for r in rows]


__all__ = [
    "AiUnavailable",
    "DEMO_COMPANIES",
    "POLICY_VERSION",
    "ai_chairman_memo",
    "ai_research_memo",
    "ai_risk_review",
    "authorize",
    "chairman_review",
    "create_case",
    "create_exit_case",
    "create_monitor_event",
    "create_proposal",
    "ensure_and_seed",
    "execute_authorization",
    "generate_research",
    "get_case",
    "get_company",
    "get_debate",
    "get_proposal",
    "list_audit",
    "list_authorizations",
    "list_cases",
    "list_companies",
    "list_proposals",
    "monitor",
    "overview",
    "partner_review",
    "portfolio",
    "review_research",
    "risk_check",
    "start_debate",
    "update_company_pool",
]
