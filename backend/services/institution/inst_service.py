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
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from psycopg.types.json import Jsonb

from services.core.db import get_conn
from services.institution.report import render_research_report, report_filename
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
    ("business_model", "公司商业模式", "收入结构、客户价值、单位经济性与资本强度"),
    ("moat", "护城河", "品牌、成本、网络、转换成本与可持续性"),
    ("financial", "财务质量", "收入、利润、现金流、ROE 与三表勾稽"),
    ("governance", "CEO 与治理", "资本配置、承诺兑现、关联交易与治理结构"),
    ("valuation", "估值与价格", "PE/PB 分位、DCF 参数、安全边际"),
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
        # 全市场研究范围：首次把 ref_security 的 A 股/美股全部纳入公司池。
        if int(existing["n"] or 0) < 1000:
            _sync_company_universe(conn, org_id)
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
             WHERE c.ref_price IS NULL
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


def _sync_company_universe(conn, org_id: int) -> None:
    """把 ref_security 的 A 股/美股补进公司池；保留已有人工字段。"""
    conn.execute(
        """
        INSERT INTO inst_company
          (org_id, symbol, name, market, industry, ref_price, data_status, pool_status)
        SELECT %s, s.symbol, s.name, s.market,
               i.industry_code,
               b.close,
               CASE
                 WHEN s.market='CN' AND EXISTS (
                   SELECT 1 FROM fin_income_statement f
                    WHERE f.symbol=s.symbol AND f.notice_date IS NOT NULL AND f.notice_date <= CURRENT_DATE
                 ) THEN 'real'
                 WHEN b.close IS NOT NULL THEN 'partial'
                 ELSE 'missing'
               END,
               'research'
          FROM ref_security s
          LEFT JOIN LATERAL (
            SELECT industry_code FROM ref_security_industry x
             WHERE x.symbol=s.symbol AND x.level=1
             ORDER BY effective_from DESC LIMIT 1
          ) i ON TRUE
          LEFT JOIN LATERAL (
            SELECT close FROM md_daily_bar b
             WHERE b.symbol=s.symbol AND b.adjust='none'
             ORDER BY trade_date DESC LIMIT 1
          ) b ON TRUE
         WHERE s.market IN ('CN','US') AND s.status='listed'
        ON CONFLICT (org_id, market, symbol) DO UPDATE
          SET name=EXCLUDED.name,
              industry=COALESCE(inst_company.industry, EXCLUDED.industry),
              ref_price=COALESCE(inst_company.ref_price, EXCLUDED.ref_price),
              data_status=CASE
                WHEN inst_company.data_status='real' THEN 'real'
                ELSE EXCLUDED.data_status
              END,
              updated_at=NOW()
        """,
        (org_id,),
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inst_company_market_name ON inst_company (org_id, market, name)"
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
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["c.org_id=%s"]
    params: list[Any] = [org_id]
    if market:
        where.append("c.market=%s")
        params.append(market)
    if pool_status:
        where.append("c.pool_status=%s")
        params.append(pool_status)
    if q:
        where.append("(c.symbol ILIKE %s OR c.name ILIKE %s OR c.industry ILIKE %s)")
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    clause = " AND ".join(where)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    sql = f"""
        SELECT c.*,
               v.pe_ttm, v.pb_mrq, v.float_mv,
               b.close AS last_close, b.trade_date AS last_trade_date,
               ind.name AS industry_name
          FROM inst_company c
          LEFT JOIN LATERAL (
            SELECT pe_ttm, pb_mrq, float_mv FROM md_valuation_daily
             WHERE symbol=c.symbol ORDER BY trade_date DESC LIMIT 1
          ) v ON TRUE
          LEFT JOIN LATERAL (
            SELECT close, trade_date FROM md_daily_bar
             WHERE symbol=c.symbol AND adjust='none' ORDER BY trade_date DESC LIMIT 1
          ) b ON TRUE
          LEFT JOIN LATERAL (
            SELECT ri.name
              FROM ref_security_industry rsi
              JOIN ref_industry ri
                ON ri.industry_code = rsi.industry_code AND ri.level = 1
             WHERE rsi.symbol = c.symbol AND rsi.level = 1
             ORDER BY rsi.effective_from DESC
             LIMIT 1
          ) ind ON TRUE
         WHERE {clause}
         ORDER BY c.market, c.symbol
         LIMIT %s OFFSET %s
    """
    with get_conn() as conn:
        total = int(
            conn.execute(f"SELECT COUNT(*) AS n FROM inst_company c WHERE {clause}", tuple(params)).fetchone()["n"]
            or 0
        )
        rows = conn.execute(sql, tuple(params + [limit, offset])).fetchall()
    out = []
    for r in rows:
        item = _row_dict(r) or {}
        item["ref_price"] = item.get("last_close") or item.get("ref_price")
        if item.get("industry_name"):
            item["industry"] = item["industry_name"]
        elif re.match(r"^\d{6}\.", str(item.get("industry") or "")):
            item["industry"] = None
        out.append(item)
    return {"items": out, "total": total, "limit": limit, "offset": offset}


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


def ideas_push(org_id: int, *, limit: int = 12) -> dict[str, Any]:
    """量化策略推送：A 股 20 日动量 + 估值初筛，收盘后计算。

    不是实时信号，也不构成投资建议。候选池取机构公司池中未放弃的 A 股，
    按 20 个交易日动量排序，只推正动量；PE/PB 仅作为估值上下文展示。
    """
    cap = max(1, min(int(limit), 30))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.symbol, c.name, c.market, c.industry, c.ref_price,
                   c.data_status, c.pool_status, c.tags, c.research_points,
                   v.pe_ttm, v.pb_mrq, v.trade_date AS valuation_date,
                   ind.name AS industry_name
              FROM inst_company c
              LEFT JOIN LATERAL (
                SELECT pe_ttm, pb_mrq, trade_date
                  FROM md_valuation_daily
                 WHERE symbol=c.symbol
                 ORDER BY trade_date DESC LIMIT 1
              ) v ON TRUE
              LEFT JOIN LATERAL (
                SELECT ri.name
                  FROM ref_security_industry rsi
                  JOIN ref_industry ri
                    ON ri.industry_code = rsi.industry_code AND ri.level = 1
                 WHERE rsi.symbol = c.symbol AND rsi.level = 1
                 ORDER BY rsi.effective_from DESC
                 LIMIT 1
              ) ind ON TRUE
             WHERE c.org_id=%s AND c.market='CN' AND c.pool_status <> 'dropped'
             ORDER BY (c.data_status='real') DESC, (v.pe_ttm IS NOT NULL) DESC, c.id
             LIMIT 500
            """,
            (org_id,),
        ).fetchall()
        symbols = [str(r["symbol"]) for r in rows]
        bars: list[Any] = []
        if symbols:
            bars = conn.execute(
                """
                SELECT symbol, close, trade_date,
                       ROW_NUMBER() OVER (
                         PARTITION BY symbol ORDER BY trade_date DESC
                       ) AS rn
                  FROM md_daily_bar
                 WHERE symbol = ANY(%s) AND adjust='none'
                   AND trade_date >= CURRENT_DATE - INTERVAL '60 days'
                """,
                (symbols,),
            ).fetchall()
    closes: dict[str, dict[int, float]] = {}
    latest_date = None
    for b in bars:
        if b["close"] is None:
            continue
        closes.setdefault(str(b["symbol"]), {})[int(b["rn"])] = float(b["close"])
        if latest_date is None or b["trade_date"] > latest_date:
            latest_date = b["trade_date"]

    items: list[dict[str, Any]] = []
    for r in rows:
        series = closes.get(str(r["symbol"]), {})
        if 1 not in series or len(series) < 3:
            continue
        # 测试库可能只有最近几天数据；窗口自动缩短到可用长度，生产环境最多 20 日。
        window = min(20, max(series) - 1)
        base = series.get(window + 1)
        if window < 2 or not base:
            continue
        momentum = series[1] / base - 1
        if momentum <= 0:
            continue
        pe = r["pe_ttm"]
        pb = r["pb_mrq"]
        # 估值初筛：有 PE/PB 时必须为正，PE 超过 100 视为不具备估值吸引力。
        if pe is not None and not (0 < float(pe) <= 100):
            continue
        if pb is not None and float(pb) <= 0:
            continue
        reasons = [f"近 {window} 日动量 {momentum * 100:.1f}%"]
        if pe is not None:
            reasons.append(f"PE TTM {float(pe):.2f}")
        if pb is not None:
            reasons.append(f"PB MRQ {float(pb):.2f}")
        industry = r["industry_name"] or r["industry"]
        if industry and re.match(r"^\d{6}\.", str(industry)):
            # 801120.SI 这类申万代码对用户不可读；交给前端显示「行业待补充」。
            industry = None
        items.append(
            {
                "id": int(r["id"]),
                "symbol": r["symbol"],
                "name": r["name"],
                "market": r["market"],
                "industry": industry,
                "ref_price": r["ref_price"],
                "data_status": r["data_status"],
                "pool_status": r["pool_status"],
                "tags": r["tags"] or [],
                "research_points": r["research_points"] or [],
                "pe_ttm": pe,
                "pb_mrq": pb,
                "last_close": series[1],
                "momentum": momentum,
                "momentum_window": window,
                "reason": "；".join(reasons),
            }
        )
    items.sort(key=lambda x: x["momentum"], reverse=True)
    return {
        "strategy": {
            "key": "momentum_valuation",
            "name": "动量 + 估值初筛",
            "note": "动量窗口取最近 2-20 个交易日（数据不足时自动缩短）；PE TTM 限 0-100、PB 限正值；收盘后计算，非实时推送；不构成投资建议。",
        },
        "as_of": str(latest_date) if latest_date else None,
        "scanned": len(rows),
        "qualified": len(items),
        "items": items[:cap],
    }


def _mapped_industry(conn, symbol: str, raw: Any) -> str | None:
    """行业展示：优先申万中文名；行业代码（801120.SI）不裸展示。"""
    text = str(raw or "").strip()
    if text and not re.match(r"^\d{6}\.", text):
        return text
    row = conn.execute(
        """
        SELECT ri.name
          FROM ref_security_industry rsi
          JOIN ref_industry ri
            ON ri.industry_code = rsi.industry_code AND ri.level = 1
         WHERE rsi.symbol=%s AND rsi.level=1
         ORDER BY rsi.effective_from DESC
         LIMIT 1
        """,
        (symbol,),
    ).fetchone()
    return str(row["name"]) if row and row["name"] else None


def get_company(org_id: int, company_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s", (company_id, org_id)
        ).fetchone()
        if not row:
            return None
        company = _row_dict(row) or {}
        company["industry"] = _mapped_industry(
            conn, str(company.get("symbol") or ""), company.get("industry")
        )
    symbol = company["symbol"]
    company["market_data"] = {
        "bar": md.latest_bar(symbol, adjust="none"),
        "valuation": md.valuation_latest(symbol),
        "percentile": md.valuation_percentile(symbol, years=3),
        "status": md.status_latest(symbol),
        "risk": md.risk_stats(symbol, index_code=None if company.get("market") == "US" else "000300.SH"),
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
        case = dict(case)
        case["industry"] = _mapped_industry(
            conn, str(case.get("symbol") or ""), case.get("industry")
        )
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
        exit_case = conn.execute(
            "SELECT * FROM inst_exit_case WHERE case_id=%s AND org_id=%s ORDER BY id DESC LIMIT 1",
            (case_id, org_id),
        ).fetchone()
    out = _row_dict(case) or {}
    out["tasks"] = [_row_dict(r) for r in tasks]
    out["versions"] = [_row_dict(r) for r in versions]
    out["evidence"] = [_row_dict(r) for r in evidence]
    out["debates"] = [_row_dict(r) for r in sessions]
    out["proposals"] = [_row_dict(r) for r in proposals]
    out["exit_case"] = _row_dict(exit_case)
    return out


def _dim_status(has_data: bool) -> str:
    return "done" if has_data else "partial"


def _build_research(company: dict[str, Any], mode: str = "full") -> dict[str, Any]:
    symbol = company["symbol"]
    bar = md.latest_bar(symbol, adjust="none")
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    risk = md.risk_stats(symbol, index_code=None if company.get("market") == "US" else "000300.SH") or {}
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
    if "business_model" in want:
        dim(
            "business_model",
            "公司商业模式",
            "公司靠什么赚钱？客户价值、收入结构与资本强度是否可持续？",
            "done" if has_fin else "partial",
            f"收入 {_yi(latest_fin.get('revenue'))}，净利 {_yi(latest_fin.get('net_profit'))}，毛利率 {_pc(gross_margin)}，净利率 {_pc(latest_fin.get('net_margin'))}；分部/客户/渠道数据待补充。",
            [
                f"营收同比：{_pc(latest_fin.get('revenue_yoy'))}",
                f"净利同比：{_pc(latest_fin.get('profit_yoy'))}",
                f"毛利率：{_pc(gross_margin)}",
                f"自由现金流：{_yi(latest_fin.get('free_cash_flow'))}",
            ],
            ["财务结果不等于商业模式；需分部收入、客户集中度、渠道与定价机制"],
            [ev_fin, ev_gm],
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
        "facts": {
            "company": {
                "symbol": symbol,
                "name": company.get("name"),
                "market": company.get("market"),
                "industry": company.get("industry"),
                "data_status": company.get("data_status"),
                "ref_price": company.get("ref_price"),
            },
            "as_of": (bar or {}).get("trade_date") or latest_fin.get("notice_date"),
            "price": price,
            "valuation": val,
            "percentile": pct,
            "risk": risk,
            "industry": ind,
            "financials": fin[:8],
            "data_gaps": [] if has_fin else ["财务三表未接入或未公告"],
        },
    }


DIMENSION_TASK_IDS: dict[str, str] = {
    "industry": "inst.dim.industry",
    "business_model": "inst.dim.business_model",
    "moat": "inst.dim.moat",
    "financial": "inst.dim.financial",
    "governance": "inst.dim.governance",
    "valuation": "inst.dim.valuation",
}

_DIM_OUTPUT = (
    '只输出 JSON，不要 markdown：{"summary":"...","checks":["..."],"counter":["..."],'
    '"evidence":[{"title":"...","quote":"...","source":"..."}],"open_questions":["..."],'
    '"confidence":0.6,"data_gaps":["..."]}。'
    "数据不足写待补充并放入 data_gaps；禁止编造数字、人名或事实；"
    "summary≤120字，checks≤4条，counter≤3条，evidence≤4条，open_questions≤3条，data_gaps≤4条，"
    "总输出不超过1200字；不给买卖点、目标价、涨跌预测或收益承诺；不改变业务状态。"
)

_DIMENSION_PROMPTS: dict[str, str] = {
    "industry": (
        "你是旸谷资本机构研究部的产业研究 Agent，服务巴菲特式价值投资。"
        "只依据输入的公司、行情、行业与财务数据，分析行业规模、竞争结构、供需与周期、产业链位置与行业吸引力。"
        "没有行业规模/份额数据时必须列入 data_gaps，不得编造。" + _DIM_OUTPUT
    ),
    "business_model": (
        "你是旸谷资本机构研究部的商业模式 Agent，服务巴菲特式价值投资。"
        "只依据输入数据分析：公司靠什么赚钱、客户价值、收入结构、单位经济性、资本强度与可复制性。"
        "没有分部收入、客户集中度、渠道数据时只能做财务结构推断，并在 data_gaps 明确标注。" + _DIM_OUTPUT
    ),
    "moat": (
        "你是旸谷资本机构研究部的护城河 Agent，服务巴菲特式价值投资。"
        "只依据输入数据分析品牌、成本优势、网络效应、转换成本、规模与可持续性；"
        "毛利率、ROE、增速只是线索，不等于护城河；必须给出可检验的护城河证据、侵蚀路径与反证条件。" + _DIM_OUTPUT
    ),
    "financial": (
        "你是旸谷资本机构研究部的财务质量 Agent，服务巴菲特式价值投资。"
        "只依据输入财务数据分析三表勾稽、ROE/ROIC、自由现金流、应收存货、资本化与会计风险；"
        "指出利润与现金流是否互相印证，以及需要回原始公告核验的项目。" + _DIM_OUTPUT
    ),
    "governance": (
        "你是旸谷资本机构研究部的 CEO 与治理 Agent，服务巴菲特式价值投资。"
        "只依据输入数据分析资本配置、承诺兑现、关联交易、分红回购与治理结构；"
        "输入若没有公告、管理层履历或治理数据，必须把缺口写入 data_gaps，禁止编造人名、履历或违规事实。" + _DIM_OUTPUT
    ),
    "valuation": (
        "你是旸谷资本机构研究部的估值与价格 Agent，服务巴菲特式价值投资。"
        "只依据输入数据分析 PE/PB 分位、DCF 假设与局限、安全边际与估值风险；"
        "不给目标价或买卖点，必须说明估值口径、数据缺口与哪些假设会推翻结论。" + _DIM_OUTPUT
    ),
}


def _agent_payload(facts: dict[str, Any], key: str) -> dict[str, Any]:
    val = facts.get("valuation") or {}
    pct = facts.get("percentile") or {}
    risk = facts.get("risk") or {}
    payload: dict[str, Any] = {
        "company": facts.get("company"),
        "as_of": facts.get("as_of"),
        "market_data": {
            "price": facts.get("price"),
            "pe_ttm": val.get("pe_ttm"),
            "pb_mrq": val.get("pb_mrq"),
            "pe_percentile": pct.get("pe_percentile"),
            "pb_percentile": pct.get("pb_percentile"),
            "max_drawdown": risk.get("max_drawdown"),
            "annual_vol": risk.get("annual_vol"),
            "total_mv": val.get("total_mv"),
            "float_mv": val.get("float_mv"),
            "total_shares": val.get("total_shares"),
        },
        "industry": facts.get("industry"),
        "financials": facts.get("financials") or [],
        "data_gaps": facts.get("data_gaps") or [],
    }
    if key == "governance":
        payload["governance_note"] = "输入不含公告正文、管理层履历或关联交易明细，必须据此列 data_gaps。"
    if key == "business_model":
        payload["business_model_note"] = "输入没有分部收入、客户集中度和渠道数据，只能从财务结构推断并标注缺口。"
    return payload


def _run_dimension_agent(key: str, facts: dict[str, Any]) -> dict[str, Any]:
    from ai.router import available_task, run_task

    task_id = DIMENSION_TASK_IDS[key]
    if not available_task(task_id):
        return {"error": "AI 未配置"}
    payload = _agent_payload(facts, key)
    out = run_task(
        task_id,
        messages=[
            {"role": "system", "content": _DIMENSION_PROMPTS[key]},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ],
    )
    data = out.get("data")
    if not isinstance(data, dict):
        content = str(out.get("content") or "")
        data = json.loads(content) if content.strip().startswith("{") else {}
    if not isinstance(data, dict) or not str(data.get("summary") or "").strip():
        return {"error": "Agent 返回缺少 summary"}
    return {"data": data}


def _update_task_progress(
    case_id: int,
    key: str,
    status: str,
    payload: Any = None,
) -> None:
    """把单个 Agent 的开始/完成写入任务表，供前端轮询展示。"""
    title = next((title for k, title, _ in SIX_DIM_DEFS if k == key), key)
    task_status = {"done": "done", "partial": "needs_review", "failed": "failed", "running": "running", "pending": "pending"}.get(
        status, "running"
    )
    progress = 15 if task_status == "running" else (100 if task_status in {"done", "needs_review", "failed"} else 0)
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO inst_research_task (case_id, task_key, title, agent, status, progress, result)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (case_id, task_key) DO UPDATE
                  SET status=EXCLUDED.status, progress=EXCLUDED.progress, result=EXCLUDED.result, updated_at=NOW()
                """,
                (case_id, key, title, f"AI-{key}", task_status, progress, _j(payload) if payload is not None else None),
            )
    except Exception:
        # 进度展示失败不能阻断研究生成
        pass


def _run_dimension_agents(
    facts: dict[str, Any],
    keys: list[str],
    on_event: Callable[[str, str, Any], None] | None = None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not keys:
        return results

    def one(key: str) -> dict[str, Any]:
        if on_event:
            on_event(key, "running", None)
        last: dict[str, Any] = {}
        for attempt in range(3):
            try:
                result = _run_dimension_agent(key, facts)
                if result.get("data"):
                    data = result["data"]
                    if on_event:
                        on_event(key, "partial" if data.get("data_gaps") else "done", data)
                    return result
                last = result
            except Exception as exc:  # noqa: BLE001 - 单个 Agent 失败不能阻断其他 Agent
                last = {"error": str(exc)}
            if attempt < 2:
                time.sleep(1.2 * (attempt + 1))
        if on_event:
            on_event(key, "failed", {"error": last.get("error") or "Agent 未返回有效结果"})
        return last

    try:
        workers = max(1, min(6, int(os.getenv("INST_AGENT_CONCURRENCY", "6"))))
    except ValueError:
        workers = 6
    with ThreadPoolExecutor(max_workers=min(workers, len(keys))) as pool:
        futures = {pool.submit(one, key): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[key] = {"error": str(exc)}
                if on_event:
                    on_event(key, "failed", {"error": str(exc)})
    return results


def _merge_agent_results(
    built: dict[str, Any],
    results: dict[str, dict[str, Any]],
    keys: list[str],
) -> dict[str, Any]:
    built_dims = {d["key"]: d for d in built.get("dims") or []}
    evidence = list(built.get("evidence") or [])
    as_of = (built.get("facts") or {}).get("as_of")
    gaps = list(built.get("data_gaps") or [])
    dims: list[dict[str, Any]] = []
    states: dict[str, str] = {}
    key_set = set(keys)

    for key, title, question in SIX_DIM_DEFS:
        if key not in key_set:
            continue
        fallback = built_dims.get(key) or {"key": key, "title": title, "question": question}
        item = results.get(key) or {}
        data = item.get("data") or {}
        err = str(item.get("error") or "")
        if data and str(data.get("summary") or "").strip():
            ev_idx: list[int] = []
            for ev in data.get("evidence") or []:
                ev_title = str(ev.get("title") or "").strip()
                ev_quote = str(ev.get("quote") or "").strip()
                if not ev_title or not ev_quote:
                    continue
                idx = len(evidence)
                evidence.append(
                    {
                        "title": ev_title[:200],
                        "quote": ev_quote[:500],
                        "source": str(ev.get("source") or "agent")[:80],
                        "evidence_type": "research",
                        "as_of": as_of,
                        "hash": _hash([ev_title, ev_quote]),
                        "_idx": idx,
                    }
                )
                ev_idx.append(idx)
            for gap in data.get("data_gaps") or []:
                gap_text = str(gap).strip()
                if gap_text and gap_text not in gaps:
                    gaps.append(gap_text)
            status = "partial" if data.get("data_gaps") else "done"
            dims.append(
                {
                    "key": key,
                    "title": title,
                    "question": question,
                    "status": status,
                    "summary": str(data.get("summary")),
                    "checks": data.get("checks") or [],
                    "counter": data.get("counter") or [],
                    "open_questions": data.get("open_questions") or [],
                    "data_gaps": data.get("data_gaps") or [],
                    "confidence": data.get("confidence", 0.5),
                    "engine": "agent",
                    "agent": f"AI-{key}",
                    "evidence_idx": ev_idx,
                    "evidence_ids": [],
                }
            )
            states[key] = status
        else:
            fallback = dict(fallback)
            fallback["engine"] = "rule"
            fallback["agent"] = f"AI-{key}"
            fallback["agent_error"] = err or "Agent 未返回有效结果"
            fallback["evidence_ids"] = []
            dims.append(fallback)
            states[key] = "failed"

    built = dict(built)
    built["dims"] = dims
    built["evidence"] = evidence
    built["data_gaps"] = gaps
    built["agent_states"] = states
    return built


def generate_research(
    org_id: int,
    case_id: int,
    *,
    mode: str = "full",
    actor_member_id: int | None,
) -> dict[str, Any]:
    # 1) 先校验权限并取公司，关闭连接后再跑 6 个模型 Agent，避免长时间占用 DB 连接
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
    keys = [d[0] for d in SIX_DIM_DEFS] if mode == "full" else [mode]
    with get_conn() as conn:
        for key, title, _ in SIX_DIM_DEFS:
            if key not in keys:
                continue
            conn.execute(
                """
                INSERT INTO inst_research_task (case_id, task_key, title, agent, status, progress, result)
                VALUES (%s,%s,%s,%s,'pending',0,NULL)
                ON CONFLICT (case_id, task_key) DO UPDATE
                  SET status='pending', progress=0, result=NULL, updated_at=NOW()
                """,
                (case_id, key, title, f"AI-{key}"),
            )
    results = _run_dimension_agents(
        built["facts"],
        keys,
        on_event=lambda key, status, payload: _update_task_progress(case_id, key, status, payload),
    )
    built = _merge_agent_results(built, results, keys)

    # 2) 持久化：任务、证据、版本
    with get_conn() as conn:
        if mode == "full":
            conn.execute(
                "DELETE FROM inst_research_task WHERE case_id=%s AND NOT (task_key = ANY(%s))",
                (case_id, keys),
            )
        for key, title, _ in SIX_DIM_DEFS:
            if key not in keys:
                continue
            dim = next((d for d in built["dims"] if d["key"] == key), {})
            status = built["agent_states"].get(key, "done")
            task_status = {"done": "done", "partial": "needs_review", "failed": "failed"}.get(status, status)
            conn.execute(
                """
                INSERT INTO inst_research_task (case_id, task_key, title, agent, status, progress, result)
                VALUES (%s,%s,%s,%s,%s,100,%s)
                ON CONFLICT (case_id, task_key) DO UPDATE
                  SET status=EXCLUDED.status, progress=100, result=EXCLUDED.result, updated_at=NOW()
                """,
                (case_id, key, title, f"AI-{key}", task_status, _j(dim)),
            )

        ev_ids: list[int] = []
        idx_to_id: dict[int, int] = {}
        seen_hash: dict[str, int] = {}
        for ev in built["evidence"]:
            digest = str(ev.get("hash") or "")
            eid = seen_hash.get(digest)
            if eid is None:
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
                if digest:
                    seen_hash[digest] = eid
            idx_to_id[int(ev["_idx"])] = eid
            if eid not in ev_ids:
                ev_ids.append(eid)

        for dim in built["dims"]:
            dim["evidence_ids"] = [idx_to_id.get(i) for i in dim.pop("evidence_idx", []) if i in idx_to_id]

        # 单维重新分析：合并到最近一版，保留其余五维，而不是用只含一维的版本覆盖。
        existing = None
        if mode != "full":
            existing = conn.execute(
                "SELECT * FROM inst_research_version WHERE case_id=%s "
                "ORDER BY version_no DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        if existing:
            new_dim = next((d for d in built["dims"] if d.get("key") == mode), None)
            old_dims = [d for d in (existing["six_dim"] or []) if isinstance(d, dict)]
            if new_dim and any(d.get("key") == mode for d in old_dims):
                merged = [dict(new_dim) if d.get("key") == mode else d for d in old_dims]
            elif new_dim:
                merged = [*old_dims, dict(new_dim)]
            else:
                merged = old_dims
            order = {k: i for i, (k, _, _) in enumerate(SIX_DIM_DEFS)}
            merged.sort(key=lambda d: order.get(str(d.get("key")), 99))
            built["dims"] = merged
            seen_ids = [int(x) for x in (existing["evidence_ids"] or [])]
            for eid in ev_ids:
                if eid not in seen_ids:
                    seen_ids.append(eid)
            ev_ids = seen_ids
            built["data_gaps"] = list(
                dict.fromkeys([*(existing["open_questions"] or []), *built["data_gaps"]])
            )
            if existing["valuation"]:
                built["valuation"] = existing["valuation"]

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
            after={
                "case_id": case_id,
                "version_no": version_no,
                "mode": mode,
                "agents": built["agent_states"],
                "merged_from_version_no": int(existing["version_no"]) if existing else None,
            },
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


def review_research_dimension(
    org_id: int,
    version_id: int,
    key: str,
    *,
    decision: str,
    comment: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """逐维审核：记录单维通过/不通过，不改版本整体状态。

    整体「审核通过」仍走 review_research；前端要求六维全部通过后才允许提交。
    """
    if decision not in {"approve", "reject"}:
        raise ValueError("decision 必须是 approve/reject")
    dim_keys = {d[0] for d in SIX_DIM_DEFS}
    if key not in dim_keys:
        raise ValueError("未知研究维度")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        row = conn.execute(
            """
            SELECT v.*, c.id AS case_id
              FROM inst_research_version v
              JOIN inst_research_case c ON c.id=v.case_id
             WHERE v.id=%s AND c.org_id=%s
            """,
            (version_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("研究版本不存在")
        if str(row["status"]) != "pending_review":
            raise PermissionError("当前研究版本不在待审核状态")
        dims = row["six_dim"] or []
        if not any(isinstance(d, dict) and d.get("key") == key for d in dims):
            raise LookupError("该维度尚未生成")
        before = dict(row["dim_reviews"] or {})
        reviews = dict(before)
        reviews[key] = {
            "decision": decision,
            "comment": (comment or "").strip() or None,
            "reviewer_member_id": actor_member_id,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        conn.execute(
            "UPDATE inst_research_version SET dim_reviews=%s WHERE id=%s",
            (_j(reviews), version_id),
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"research.review.dimension.{decision}",
            object_type="inst_research_version",
            object_id=version_id,
            before={"dim_reviews": before},
            after={"key": key, "decision": decision, "comment": comment},
        )
    return get_case(org_id, int(row["case_id"]))  # type: ignore[return-value]


def export_research(
    org_id: int,
    case_id: int,
    *,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """导出研究简报（Markdown，带演示标识）；导出动作写审计。"""
    data = get_case(org_id, case_id)
    if not data:
        raise LookupError("研究案不存在")
    versions = data.get("versions") or []
    version = versions[0] if versions else None
    generated_at = datetime.now().astimezone()
    content = render_research_report(
        case=data,
        version=version,
        evidence=data.get("evidence") or [],
        generated_at=generated_at,
    )
    filename = report_filename(data, version)
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.export",
            object_type="inst_research_case",
            object_id=case_id,
            after={
                "format": "markdown",
                "version_id": int(version["id"]) if version and version.get("id") is not None else None,
                "version_no": version.get("version_no") if version else None,
            },
        )
    return {
        "filename": filename,
        "content": content,
        "content_type": "text/markdown; charset=utf-8",
    }


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


# ---------------------------------------------------------------- 退出案状态机


_EXIT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"approved", "rejected", "closed"},
    "approved": {"rejected", "closed"},
    "rejected": set(),
    "closed": set(),
}


def _exit_case_for_case(conn, org_id: int, case_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_exit_case WHERE case_id=%s AND org_id=%s ORDER BY id DESC LIMIT 1",
        (case_id, org_id),
    ).fetchone()
    return _row_dict(row)


def _exit_case_for_proposal(conn, org_id: int, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM inst_exit_case WHERE proposal_id=%s AND org_id=%s ORDER BY id DESC LIMIT 1",
        (proposal_id, org_id),
    ).fetchone()
    return _row_dict(row)


def _transition_exit_case(
    conn,
    org_id: int,
    exit_case: dict[str, Any],
    new_status: str,
    *,
    actor_member_id: int | None,
    action: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    """按状态机迁移退出案；非法迁移直接拒绝，成功迁移写审计。"""
    old_status = str(exit_case.get("status") or "draft")
    if new_status == old_status:
        return False
    if new_status not in _EXIT_TRANSITIONS.get(old_status, set()):
        raise PermissionError(f"退出案状态不能从 {old_status} 迁移到 {new_status}")
    row = conn.execute(
        "UPDATE inst_exit_case SET status=%s WHERE id=%s AND org_id=%s AND status=%s RETURNING id",
        (new_status, int(exit_case["id"]), org_id, old_status),
    ).fetchone()
    if not row:
        raise PermissionError("退出案状态已变化，请刷新后重试")
    _audit(
        conn,
        org_id=org_id,
        actor_member_id=actor_member_id,
        action=action,
        object_type="inst_exit_case",
        object_id=int(exit_case["id"]),
        before={"status": old_status},
        after={"status": new_status, **(extra or {})},
    )
    return True


def _advance_exit_case(
    conn,
    org_id: int,
    exit_case: dict[str, Any],
    new_status: str,
    *,
    actor_member_id: int | None,
    action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """兼容旧数据：仍为 draft 的退出案先补 submitted，再前进到目标状态。"""
    if new_status in {"approved", "rejected", "closed"} and str(
        exit_case.get("status") or "draft"
    ) == "draft":
        _transition_exit_case(
            conn,
            org_id,
            exit_case,
            "submitted",
            actor_member_id=actor_member_id,
            action="monitor.exit.submit",
            extra={"auto": True},
        )
        exit_case = {**exit_case, "status": "submitted"}
    _transition_exit_case(
        conn,
        org_id,
        exit_case,
        new_status,
        actor_member_id=actor_member_id,
        action=action,
        extra=extra,
    )
    return {**exit_case, "status": new_status}


def create_proposal(
    org_id: int,
    case_id: int,
    *,
    actor_member_id: int | None,
    direction: str | None = None,
    target_weight: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        exit_case = _exit_case_for_case(conn, org_id, case_id)
        if exit_case and exit_case.get("proposal_id"):
            raise PermissionError("该退出研究案已关联议案，不能重复创建")
        resolved_direction = str(direction or ("exit" if exit_case else "buy")).strip()
        if resolved_direction not in {"buy", "sell", "exit"}:
            raise ValueError("direction 必须是 buy/sell/exit")
        # 退出案只能清仓/减持，不允许借退出研究案创建买入议案。
        if exit_case and resolved_direction not in {"sell", "exit"}:
            raise ValueError("退出研究案只能创建 sell/exit 方向的退出议案")
        if target_weight is None:
            resolved_target = 0.0 if exit_case else 0.05
        else:
            resolved_target = float(target_weight)
        if not (0 <= resolved_target <= 1):
            raise ValueError("target_weight 必须在 0-1")
        snapshot = {
            "research_version_id": int(version["id"]),
            "research_version_no": int(version["version_no"]),
            "debate_session_id": int(debate["id"]) if debate else None,
            "direction": resolved_direction,
            "target_weight": resolved_target,
            "exit_case_id": int(exit_case["id"]) if exit_case else None,
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
            (org_id, case_id, case["company_id"], resolved_direction, resolved_target, actor_member_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_proposal_version (proposal_id, version_no, snapshot, status, created_by) "
            "VALUES (%s,1,%s,'draft',%s)",
            (row["id"], _j(snapshot), actor_member_id),
        )
        if exit_case:
            conn.execute(
                "UPDATE inst_exit_case SET proposal_id=%s WHERE id=%s AND org_id=%s",
                (row["id"], int(exit_case["id"]), org_id),
            )
            _transition_exit_case(
                conn,
                org_id,
                exit_case,
                "submitted",
                actor_member_id=actor_member_id,
                action="monitor.exit.submit",
                extra={"proposal_id": int(row["id"]), "direction": resolved_direction},
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.create",
            object_type="inst_proposal",
            object_id=int(row["id"]),
            after={
                "case_id": case_id,
                "direction": resolved_direction,
                "target_weight": resolved_target,
                "exit_case_id": int(exit_case["id"]) if exit_case else None,
            },
        )
    return get_proposal(org_id, int(row["id"]))  # type: ignore[return-value]


def list_proposals(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT p.*, co.symbol, co.name AS company_name, co.market,
               v.version_no, v.snapshot, v.status AS version_status,
               a.id AS authorization_id, a.status AS authorization_status,
               x.id AS exit_case_id, x.status AS exit_status, x.reason_type AS exit_reason_type
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
          LEFT JOIN LATERAL (
            SELECT id, status, reason_type FROM inst_exit_case
             WHERE proposal_id=p.id ORDER BY id DESC LIMIT 1
          ) x ON TRUE
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
        exit_case = conn.execute(
            "SELECT * FROM inst_exit_case WHERE proposal_id=%s AND org_id=%s ORDER BY id DESC LIMIT 1",
            (proposal_id, org_id),
        ).fetchone()
    proposal["versions"] = [_row_dict(r) for r in versions]
    proposal["current_version"] = version
    proposal["approvals"] = [_row_dict(r) for r in approvals]
    proposal["authorizations"] = [_row_dict(r) for r in auths]
    proposal["exit_case"] = _row_dict(exit_case)
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
        exit_case = _exit_case_for_proposal(conn, org_id, proposal_id)
        if exit_case and decision in {"approve", "conditional"}:
            _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "approved",
                actor_member_id=actor_member_id,
                action="monitor.exit.approve",
                extra={"proposal_id": proposal_id, "decision": decision},
            )
        elif exit_case and decision == "reject":
            _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "rejected",
                actor_member_id=actor_member_id,
                action="monitor.exit.reject",
                extra={"proposal_id": proposal_id, "decision": decision},
            )
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
            exit_case = _exit_case_for_proposal(conn, org_id, proposal_id)
            if exit_case:
                _advance_exit_case(
                    conn,
                    org_id,
                    exit_case,
                    "rejected",
                    actor_member_id=actor_member_id,
                    action="monitor.exit.risk_block",
                    extra={"proposal_id": proposal_id, "risk_decision": decision},
                )
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
        exit_case = _exit_case_for_proposal(conn, org_id, proposal_id)
        if exit_case:
            # 退出案状态没有独立「已授权」态：授权不改状态，只写审计，下一步执行后关闭。
            exit_case = _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "approved",
                actor_member_id=actor_member_id,
                action="monitor.exit.approve",
                extra={"proposal_id": proposal_id, "authorization_id": int(row["id"])},
            )
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="monitor.exit.authorize",
                object_type="inst_exit_case",
                object_id=int(exit_case["id"]),
                before={"status": exit_case["status"]},
                after={
                    "status": exit_case["status"],
                    "proposal_id": proposal_id,
                    "authorization_id": int(row["id"]),
                },
            )
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
        # 幂等优先：同一授权重复执行返回原订单，而不是报“状态不可执行”。
        existing = conn.execute(
            "SELECT * FROM inst_order WHERE authorization_id=%s", (authorization_id,)
        ).fetchone()
        if existing:
            exit_case = _exit_case_for_proposal(conn, org_id, int(auth["proposal_id"]))
            if exit_case:
                _advance_exit_case(
                    conn,
                    org_id,
                    exit_case,
                    "closed",
                    actor_member_id=actor_member_id,
                    action="monitor.exit.close",
                    extra={"order_id": int(existing["id"]), "authorization_id": authorization_id},
                )
            return {"ok": True, "idempotent": True, "order": _row_dict(existing)}
        if auth["status"] != "qualified":
            raise PermissionError(f"授权状态为 {auth['status']}，不可执行")
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
        status = md.status_latest(auth["symbol"]) or {}
        if status.get("is_suspended") or status.get("is_st"):
            reason = "停牌" if status.get("is_suspended") else "ST"
            _record_blocked_execution(
                org_id,
                authorization_id,
                type_="suspended_or_st",
                detail=f"{auth['symbol']} 当前状态：{reason}",
                actor_member_id=actor_member_id,
            )
            raise PermissionError(f"标的当前{reason}，不能执行")
        if px <= 0:
            _record_blocked_execution(
                org_id,
                authorization_id,
                type_="price_invalid",
                detail=f"{auth['symbol']} 无可用成交价",
                actor_member_id=actor_member_id,
            )
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
        exit_case = _exit_case_for_proposal(conn, org_id, int(auth["proposal_id"]))
        if exit_case:
            _advance_exit_case(
                conn,
                org_id,
                exit_case,
                "closed",
                actor_member_id=actor_member_id,
                action="monitor.exit.close",
                extra={"order_id": int(order["id"]), "authorization_id": authorization_id},
            )
        conn.execute(
            "UPDATE inst_execution_exception SET status='resolved', resolution='执行成功自动关闭', "
            "resolved_by=%s, resolved_at=NOW() "
            "WHERE org_id=%s AND authorization_id=%s AND status='open'",
            (actor_member_id, org_id, authorization_id),
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


# ---------------------------------------------------------------- 执行前校验 / 对账 / 异常


def _execution_context(conn, org_id: int, authorization_id: int):
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
    portfolio = conn.execute(
        "SELECT * FROM inst_portfolio WHERE org_id=%s ORDER BY id LIMIT 1", (org_id,)
    ).fetchone()
    existing = conn.execute(
        "SELECT * FROM inst_order WHERE authorization_id=%s", (authorization_id,)
    ).fetchone()
    pos = conn.execute(
        "SELECT qty FROM inst_position_snapshot WHERE portfolio_id=%s AND symbol=%s "
        "ORDER BY as_of DESC LIMIT 1",
        (portfolio["id"] if portfolio else 0, auth["symbol"]),
    ).fetchone()
    return auth, (auth.get("snapshot") or {}), portfolio, existing, float(pos["qty"]) if pos else 0.0


def precheck_execution(org_id: int, authorization_id: int) -> dict[str, Any]:
    """执行前校验：授权、有效期、价格区间、现金/持仓、停牌与 ST。"""
    from services.institution.execution_guard import evaluate

    with get_conn() as conn:
        auth, snapshot, portfolio, existing, pos_qty = _execution_context(
            conn, org_id, authorization_id
        )
    bar = md.latest_bar(str(auth["symbol"]), adjust="none") or {}
    status = md.status_latest(str(auth["symbol"])) or {}
    price = float(bar.get("close") or 0)
    nav = float((portfolio or {}).get("nav") or DEFAULT_NAV)
    cash = float((portfolio or {}).get("cash") or 0)
    target = float(snapshot.get("target_weight") or 0)
    direction = str(auth["direction"])
    if direction in {"sell", "exit"}:
        lot = math.floor(target * nav / price / 100) * 100 if price > 0 and target > 0 else pos_qty
        qty = int(min(pos_qty, lot))
        cost = 0.0
    else:
        qty = math.floor(target * nav / price / 100) * 100 if price > 0 else 0
        cost = qty * price * 1.0003
    out = evaluate(
        auth_status=str(auth["status"]),
        valid_until=(snapshot.get("valid_until") if isinstance(snapshot, dict) else None),
        direction=direction,
        price=price,
        price_low=snapshot.get("price_low"),
        price_high=snapshot.get("price_high"),
        cash=cash,
        cost=cost,
        qty=qty,
        position_qty=pos_qty,
        suspended=bool(status.get("is_suspended") or False),
        is_st=bool(status.get("is_st") or False),
        duplicate_order=existing is not None,
    )
    return {
        **out,
        "authorization_id": authorization_id,
        "symbol": auth["symbol"],
        "price": price,
        "qty": qty,
        "cash": cash,
        "position_qty": pos_qty,
    }


def _record_execution_exception(
    conn, org_id: int, authorization_id: int, *, type_: str, detail: str
) -> None:
    exists = conn.execute(
        "SELECT 1 FROM inst_execution_exception WHERE org_id=%s AND authorization_id=%s "
        "AND type=%s AND status='open'",
        (org_id, authorization_id, type_),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO inst_execution_exception (org_id, authorization_id, type, detail) "
        "VALUES (%s,%s,%s,%s)",
        (org_id, authorization_id, type_, detail),
    )


def _record_blocked_execution(
    org_id: int,
    authorization_id: int,
    *,
    type_: str,
    detail: str,
    actor_member_id: int | None,
) -> None:
    """失败请求会回滚，异常记录用独立事务落库。"""
    try:
        with get_conn() as conn:
            _record_execution_exception(conn, org_id, authorization_id, type_=type_, detail=detail)
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="authorization.execute.blocked",
                object_type="inst_authorization",
                object_id=authorization_id,
                after={"type": type_, "detail": detail},
            )
    except Exception:
        pass


def list_execution_exceptions(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        sql = (
            "SELECT e.*, co.symbol, co.name AS company_name FROM inst_execution_exception e "
            "LEFT JOIN inst_authorization a ON a.id=e.authorization_id "
            "LEFT JOIN inst_proposal_version v ON v.id=a.proposal_version_id "
            "LEFT JOIN inst_proposal p ON p.id=v.proposal_id "
            "LEFT JOIN inst_company co ON co.id=p.company_id "
            "WHERE e.org_id=%s"
        )
        params: list[Any] = [org_id]
        if status:
            sql += " AND e.status=%s"
            params.append(status)
        sql += " ORDER BY e.created_at DESC LIMIT 200"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) for r in rows]


def resolve_execution_exception(
    org_id: int,
    exception_id: int,
    *,
    status: str,
    resolution: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if status not in {"resolved", "ignored"}:
        raise ValueError("status 必须是 resolved/ignored")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner", "execution")
        row = conn.execute(
            "SELECT * FROM inst_execution_exception WHERE id=%s AND org_id=%s",
            (exception_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("异常记录不存在")
        updated = conn.execute(
            "UPDATE inst_execution_exception SET status=%s, resolution=%s, resolved_by=%s, "
            "resolved_at=NOW() WHERE id=%s RETURNING *",
            (status, resolution, actor_member_id, exception_id),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"execution.exception.{status}",
            object_type="inst_execution_exception",
            object_id=exception_id,
            before={"status": row["status"]},
            after={"status": status, "resolution": resolution},
        )
    return _row_dict(updated) or {}


def reconcile_authorization(
    org_id: int, authorization_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """成交对账：订单、成交、持仓快照与组合现金的一致性检查。"""
    with get_conn() as conn:
        auth, _snapshot, portfolio, order, pos_qty = _execution_context(
            conn, org_id, authorization_id
        )
        fill = (
            conn.execute("SELECT * FROM inst_fill WHERE order_id=%s", (order["id"],)).fetchone()
            if order
            else None
        )
        differences: list[str] = []
        if order is None:
            differences.append("授权没有成交订单")
        else:
            if fill is None:
                differences.append("订单没有成交记录")
            else:
                if int(fill["qty"]) != int(order["qty"]):
                    differences.append(f"成交数量 {fill['qty']} ≠ 订单数量 {order['qty']}")
                if abs(float(fill["price"]) - float(order["price"])) > 1e-6:
                    differences.append(f"成交价 {fill['price']} ≠ 订单价 {order['price']}")
            if str(order["side"]) == "buy" and pos_qty < float(order["qty"]):
                differences.append(f"持仓 {pos_qty} 少于买入数量 {order['qty']}")
            expected = float((portfolio or {}).get("cash") or 0)
            if expected < 0:
                differences.append("组合现金为负")
        matched = not differences
        if order is not None and not matched:
            exists = conn.execute(
                "SELECT 1 FROM inst_execution_exception WHERE org_id=%s AND authorization_id=%s "
                "AND type='reconcile_mismatch' AND status='open'",
                (org_id, authorization_id),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO inst_execution_exception "
                    "  (org_id, authorization_id, order_id, type, detail, status) "
                    "VALUES (%s,%s,%s,'reconcile_mismatch',%s,'open')",
                    (org_id, authorization_id, order["id"], "；".join(differences)[:500]),
                )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="authorization.reconcile",
            object_type="inst_authorization",
            object_id=authorization_id,
            after={"matched": matched, "differences": differences},
        )
    return {
        "authorization_id": authorization_id,
        "matched": matched,
        "differences": differences,
        "order": _row_dict(order) if order else None,
        "fill": _row_dict(fill) if fill else None,
    }


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
            """
            SELECT x.*, co.symbol, co.name AS company_name, c.case_no,
                   p.status AS proposal_status, p.direction AS proposal_direction,
                   a.status AS authorization_status
              FROM inst_exit_case x
              JOIN inst_company co ON co.id=x.company_id
              LEFT JOIN inst_research_case c ON c.id=x.case_id
              LEFT JOIN inst_proposal p ON p.id=x.proposal_id
              LEFT JOIN LATERAL (
                SELECT au.status FROM inst_authorization au
                  JOIN inst_proposal_version v ON v.id=au.proposal_version_id
                 WHERE v.proposal_id=x.proposal_id
                 ORDER BY au.id DESC LIMIT 1
              ) a ON TRUE
             WHERE x.org_id=%s ORDER BY x.created_at DESC LIMIT 50
            """,
            (org_id,),
        ).fetchall()
        theses = conn.execute(
            """
            SELECT t.*, co.name AS company_name,
                   (SELECT COUNT(*) FROM inst_thesis_review r WHERE r.ledger_id=t.id) AS review_count
              FROM inst_thesis_ledger t
              JOIN inst_company co ON co.id=t.company_id
             WHERE t.org_id=%s
             ORDER BY t.updated_at DESC LIMIT 100
            """,
            (org_id,),
        ).fetchall()
        exit_reviews = conn.execute(
            """
            SELECT r.* FROM inst_exit_review r
              JOIN inst_exit_case x ON x.id=r.exit_case_id
             WHERE x.org_id=%s ORDER BY r.created_at DESC LIMIT 50
            """,
            (org_id,),
        ).fetchall()
    return {
        "portfolio": portfolio(org_id),
        "events": [_row_dict(r) for r in events],
        "exits": [_row_dict(r) for r in exits],
        "theses": [_row_dict(r) for r in theses],
        "exit_reviews": [_row_dict(r) for r in exit_reviews],
    }


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
        _require_role(member, "manager", "partner", "monitoring")
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
    row = conn.execute(
        """
        SELECT t.*, co.name AS company_name, co.market
          FROM inst_thesis_ledger t
          JOIN inst_company co ON co.id=t.company_id
         WHERE t.id=%s AND t.org_id=%s
        """,
        (ledger_id, org_id),
    ).fetchone()
    if not row:
        return None
    out = _row_dict(row) or {}
    reviews = conn.execute(
        "SELECT * FROM inst_thesis_review WHERE ledger_id=%s ORDER BY created_at DESC",
        (ledger_id,),
    ).fetchall()
    out["reviews"] = [_row_dict(r) for r in reviews]
    return out


def list_theses(org_id: int, *, status: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        sql = (
            "SELECT t.*, co.name AS company_name, co.market, "
            "  (SELECT COUNT(*) FROM inst_thesis_review r WHERE r.ledger_id=t.id) AS review_count "
            "  FROM inst_thesis_ledger t JOIN inst_company co ON co.id=t.company_id "
            " WHERE t.org_id=%s"
        )
        params: list[Any] = [org_id]
        if status:
            sql += " AND t.status=%s"
            params.append(status)
        sql += " ORDER BY t.updated_at DESC LIMIT 100"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_dict(r) for r in rows]


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
        _require_role(member, "manager", "partner", "monitoring")
        ledger = conn.execute(
            "SELECT * FROM inst_thesis_ledger WHERE id=%s AND org_id=%s",
            (ledger_id, org_id),
        ).fetchone()
        if not ledger:
            raise LookupError("论点台账不存在")
        conn.execute(
            """
            INSERT INTO inst_thesis_review
              (ledger_id, reviewer_member_id, kpi_status, conclusion, note)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (ledger_id, actor_member_id, kpi_status, conclusion, note),
        )
        new_status = "reviewed" if conclusion in {"hold", "reduce"} else "invalidated"
        conn.execute(
            "UPDATE inst_thesis_ledger SET status=%s, updated_at=NOW() WHERE id=%s",
            (new_status, ledger_id),
        )
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
        out = _thesis_row(conn, org_id, ledger_id)
    return out or {}


def review_exit(
    org_id: int,
    exit_case_id: int,
    *,
    thesis_verdict: str,
    realized_return: float | None = None,
    holding_days: int | None = None,
    lessons: str | None = None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """退出复盘：结果、持有天数、论点对错与教训。"""
    if thesis_verdict not in {"right", "wrong", "mixed"}:
        raise ValueError("thesis_verdict 必须是 right/wrong/mixed")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner", "monitoring")
        exit_case = conn.execute(
            "SELECT * FROM inst_exit_case WHERE id=%s AND org_id=%s",
            (exit_case_id, org_id),
        ).fetchone()
        if not exit_case:
            raise LookupError("退出案不存在")
        row = conn.execute(
            """
            INSERT INTO inst_exit_review
              (exit_case_id, realized_return, holding_days, thesis_verdict, lessons, reviewer_member_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (exit_case_id) DO UPDATE
              SET realized_return=EXCLUDED.realized_return,
                  holding_days=EXCLUDED.holding_days,
                  thesis_verdict=EXCLUDED.thesis_verdict,
                  lessons=EXCLUDED.lessons,
                  reviewer_member_id=EXCLUDED.reviewer_member_id,
                  created_at=NOW()
            RETURNING *
            """,
            (exit_case_id, realized_return, holding_days, thesis_verdict, lessons, actor_member_id),
        ).fetchone()
        current_status = str(exit_case["status"] or "draft")
        if current_status in {"approved", "submitted"}:
            _transition_exit_case(
                conn,
                org_id,
                _row_dict(exit_case) or {},
                "closed",
                actor_member_id=actor_member_id,
                action="monitor.exit.close",
                extra={"review_id": int(row["id"]), "source": "post_mortem"},
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.exit.review",
            object_type="inst_exit_case",
            object_id=exit_case_id,
            after={"thesis_verdict": thesis_verdict, "realized_return": realized_return},
        )
    return _row_dict(row) or {}


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


def _memo_metrics(case: dict[str, Any]) -> list[dict[str, Any]]:
    """一页纸顶部指标：只展示已有数据，缺失不编造。"""
    symbol = str(case.get("symbol") or "")
    fin = md.financials(symbol, limit=2) or []
    latest = fin[0] if fin else {}
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    out: list[dict[str, Any]] = []
    if latest.get("revenue") is not None:
        out.append(
            {
                "label": "营业收入",
                "value": _yi(latest.get("revenue")),
                "note": f"同比 {_pc(latest.get('revenue_yoy'))}"
                if latest.get("revenue_yoy") is not None
                else "最近报告期",
            }
        )
    if latest.get("net_profit") is not None:
        out.append(
            {
                "label": "净利润",
                "value": _yi(latest.get("net_profit")),
                "note": f"同比 {_pc(latest.get('profit_yoy'))}"
                if latest.get("profit_yoy") is not None
                else "最近报告期",
            }
        )
    if latest.get("roe") is not None:
        out.append({"label": "ROE", "value": _pc(latest.get("roe")), "note": "最近报告期"})
    if val.get("pe_ttm") is not None:
        out.append(
            {
                "label": "PE TTM",
                "value": f"{float(val['pe_ttm']):.2f}",
                "note": f"历史分位 {_pc(pct.get('pe_percentile'))}",
            }
        )
    elif val.get("pb_mrq") is not None:
        out.append(
            {
                "label": "PB MRQ",
                "value": f"{float(val['pb_mrq']):.2f}",
                "note": f"历史分位 {_pc(pct.get('pb_percentile'))}",
            }
        )
    return out


def _rule_memo(version: dict[str, Any]) -> dict[str, Any]:
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    risks = [str(c) for d in dims for c in (d.get("counter") or [])][:5]
    questions = [
        str(q) for d in dims for q in (d.get("open_questions") or d.get("data_gaps") or [])
    ][:8]
    return {
        "summary": version.get("conclusion")
        or "六维分析已完成；AI 摘要暂不可用，以下为规则摘要，请以各维证据为准。",
        "evidence": [],
        "risks": risks,
        "open_questions": questions,
        "engine": "rule",
    }


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
    try:
        data = _ai_task(
            "inst.research_memo",
            payload,
            "你是机构研究一页纸助手。只使用输入中的公司、六维与证据；结论必须可回源；"
            "数据不足写待补充；不给买卖建议、目标价或收益承诺。只输出 JSON："
            '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。',
        )
        data.setdefault("engine", "agent")
    except AiUnavailable:
        # AI 未配置时仍给出一页纸骨架，内容全部来自六维规则结果。
        data = _rule_memo(version)
    data["metrics"] = _memo_metrics(case)
    return {"memo": data, "task": "inst.research_memo", "version_no": version.get("version_no")}


def ai_dimension_chat(
    org_id: int,
    case_id: int,
    key: str,
    *,
    question: str,
    history: list[dict[str, Any]] | None = None,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """单维追问：只带该维结论、证据与最近对话，不改业务状态。"""
    q = str(question or "").strip()
    if not q:
        raise ValueError("问题不能为空")
    dim_keys = {d[0] for d in SIX_DIM_DEFS}
    if key not in dim_keys:
        raise ValueError("未知研究维度")
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    version = (case.get("versions") or [{}])[0]
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    dim = next((d for d in dims if d.get("key") == key), None)
    if not dim:
        raise LookupError("该维度尚未生成")
    ev_ids = {int(x) for x in (dim.get("evidence_ids") or []) if str(x).isdigit()}
    evidence = [e for e in (case.get("evidence") or []) if int(e.get("id") or 0) in ev_ids]
    history_in: list[dict[str, str]] = []
    for item in (history or [])[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            history_in.append({"role": role, "content": content[:2000]})
    payload = {
        "company": {k: case.get(k) for k in ("symbol", "company_name", "market", "industry", "ref_price")},
        "dimension": {
            k: dim.get(k)
            for k in (
                "key",
                "title",
                "question",
                "summary",
                "checks",
                "counter",
                "open_questions",
                "data_gaps",
                "confidence",
                "engine",
            )
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source")}
            for e in evidence
        ],
        "history": history_in,
        "question": q[:2000],
    }
    data = _ai_task(
        "inst.dim.chat",
        payload,
        "你是机构研究单维对话助手。只依据输入的该维结论、检查项、反证与证据回答；"
        "不扩展到其他维度、不编造数据、不给买卖建议/目标价/收益承诺；数据不足直接说待补充。"
        "用简洁中文回答，可引用证据标题，不要输出 JSON 以外的格式要求。",
    )
    answer = str(data.get("answer") or data.get("summary") or "").strip()
    if not answer:
        raise AiUnavailable("AI 未返回内容")
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.dimension.chat",
            object_type="inst_research_version",
            object_id=int(version.get("id") or 0),
            after={"case_id": case_id, "key": key, "question": q[:200], "answer": answer[:300]},
        )
    return {
        "answer": answer,
        "dimension": key,
        "task": "inst.dim.chat",
        "engine": str(data.get("engine") or "agent"),
    }


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


# ---------------------------------------------------------------- AI Chairman 模式


def _ai_available(task_id: str = "inst.chairman_memo") -> bool:
    try:
        from ai.router import available_task

        return bool(available_task(task_id))
    except Exception:
        return False


def _chairman_context(
    org_id: int, proposal_id: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    with get_conn() as conn:
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        approvals = {
            str(r["step"]): dict(r)
            for r in conn.execute(
                "SELECT * FROM inst_approval WHERE proposal_version_id=%s", (current["id"],)
            ).fetchall()
        }
        snapshot = current.get("snapshot") or {}
        risk_checks = _risk_checks(conn, org_id, proposal, current)
        evidence_count = 0
        research_version_id = snapshot.get("research_version_id")
        if research_version_id:
            row = conn.execute(
                "SELECT evidence_ids FROM inst_research_version WHERE id=%s",
                (research_version_id,),
            ).fetchone()
            if row:
                evidence_count = len(row.get("evidence_ids") or [])
    return proposal, current, snapshot, approvals, risk_checks, evidence_count


def ai_chairman_precheck(
    org_id: int, proposal_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """预检查：只读，不改状态。"""
    from services.institution.chairman_mode import evaluate

    proposal, current, snapshot, approvals, risk_checks, evidence_count = _chairman_context(
        org_id, proposal_id
    )
    result = evaluate(
        proposal_status=str(proposal.get("status") or ""),
        snapshot=snapshot,
        approvals=approvals,
        risk_checks=risk_checks,
        evidence_count=evidence_count,
        ai_available=_ai_available(),
        proposer_is_reviewer=int(proposal.get("created_by") or 0) == int(actor_member_id or 0),
    )
    result.update(
        {
            "proposal_id": proposal_id,
            "version_no": current.get("version_no"),
            "status": proposal.get("status"),
        }
    )
    return result


def ai_chairman_simulate(
    org_id: int, proposal_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """模拟批准：只记录建议与审计，不写审批、不改状态。"""
    pre = ai_chairman_precheck(org_id, proposal_id, actor_member_id=actor_member_id)
    memo = None
    if _ai_available():
        try:
            memo = ai_chairman_memo(org_id, proposal_id).get("memo")
        except AiUnavailable:
            memo = None
    recommendation = pre["recommendation"]
    decision = {
        "approve_candidate": "approve",
        "conditional_candidate": "conditional",
    }.get(recommendation, "handover")
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.chairman.ai_simulate",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={
                "simulated_decision": decision,
                "blocking": pre["blocking"],
                "warnings": pre["warnings"],
                "binding": False,
            },
        )
    return {
        **pre,
        "mode": "ai_simulated",
        "simulated_decision": decision,
        "memo": memo,
        "note": "AI 模拟结果不构成批准；需真人 Chairman 表决",
    }


def ai_chairman_handover(
    org_id: int,
    proposal_id: int,
    *,
    actor_member_id: int | None,
    note: str | None = None,
) -> dict[str, Any]:
    """人工移交：Chairman 放弃 AI 模拟，转真人流程；只写审计。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.chairman.ai_handover",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={"note": note or "已移交真人 Chairman", "status": proposal.get("status")},
        )
    return {
        "ok": True,
        "handover": True,
        "proposal_id": proposal_id,
        "status": proposal.get("status"),
        "note": note or "已移交真人 Chairman",
    }


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
        company = conn.execute(
            "SELECT id, symbol, name FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        pos = conn.execute(
            """
            SELECT ps.id, ps.portfolio_id, ps.symbol, ps.qty
              FROM inst_position_snapshot ps
              JOIN inst_portfolio p ON p.id=ps.portfolio_id
             WHERE p.org_id=%s AND ps.symbol=%s AND ps.qty > 0
             ORDER BY ps.as_of DESC LIMIT 1
            """,
            (org_id, company["symbol"]),
        ).fetchone()
        if not pos:
            raise PermissionError("该标的不在持仓中，不能发起退出研究")
        # 退出研究使旧授权失效：只撤销仍有效的授权，保留历史。
        conn.execute(
            """
            UPDATE inst_authorization a
               SET status='revoked', revoked_at=NOW(),
                   revoke_reason='exit research: ' || %s
             WHERE a.status='qualified'
               AND a.id IN (
                 SELECT a2.id FROM inst_authorization a2
                   JOIN inst_proposal_version v ON v.id=a2.proposal_version_id
                   JOIN inst_proposal p ON p.id=v.proposal_id
                  WHERE p.org_id=%s AND p.company_id=%s
               )
            """,
            (memo[:120] or reason_type, org_id, company_id),
        )
        case_no = f"EX-{date.today():%Y%m%d}-{str(company['symbol']).split('.')[0]}-{_uid()[:4]}"
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, created_by) "
            "VALUES (%s,%s,%s,'draft',%s) RETURNING id",
            (org_id, company_id, case_no, actor_member_id),
        ).fetchone()
        row = conn.execute(
            "INSERT INTO inst_exit_case (org_id, company_id, position_id, case_id, reason_type, memo, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'draft') RETURNING *",
            (org_id, company_id, pos["id"], int(case["id"]), reason_type, memo),
        ).fetchone()
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="monitor.exit.create",
            object_type="inst_exit_case",
            object_id=int(row["id"]),
            after={"company_id": company_id, "reason_type": reason_type, "case_id": int(case["id"])},
        )
    out = _row_dict(row) or {}
    out["case_id"] = int(case["id"])
    out["case_no"] = case_no
    return out


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
    "ideas_push",
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


# ---------------------------------------------------------------- AI 岗位（I01–I06）

AI_ROLE_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("research", "研究统筹 / 产业 / 护城河", "inst.research_memo"),
    ("financial", "财务与取证", "inst.role.financial"),
    ("governance", "治理 / 估值 / 反证", "inst.role.governance"),
    ("debate", "看多 / 看空 / 主持", "inst.debate"),
    ("risk", "风控 / 合规 / 交易", "inst.risk_review"),
    ("post_investment", "投后 / 退出 / 复盘", "inst.role.post_investment"),
)

_ROLE_PROMPTS = {
    "financial": (
        "你是机构端财务与取证岗位。只依据输入的财务、证据与估值数据；"
        "检查三表勾稽、ROIC/FCF、应收存货与会计风险；不给买卖建议或目标价。只输出 JSON："
        '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。'
    ),
    "governance": (
        "你是机构端治理、估值与反证岗位。只依据输入数据；"
        "评估资本配置、治理结构、DCF 假设与可检验的反证条件；不编造事实。只输出 JSON："
        '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。'
    ),
    "post_investment": (
        "你是机构端投后、退出与复盘岗位。只依据输入的持仓、论点台账、监控事件与退出案；"
        "给出复核要点、预警与复盘问题；不直接给卖出指令。只输出 JSON："
        '{"summary":"...","evidence":["..."],"risks":["..."],"open_questions":["..."]}。'
    ),
}


def ai_role_catalog() -> list[dict[str, Any]]:
    out = []
    for key, label, task in AI_ROLE_CATALOG:
        out.append(
            {
                "key": key,
                "label": label,
                "task": task,
                "available": _ai_available(task),
            }
        )
    return out


def _role_case_payload(org_id: int, case_id: int) -> dict[str, Any]:
    data = get_case(org_id, case_id)
    if not data:
        raise LookupError("研究案不存在")
    version = (data.get("versions") or [None])[0] or {}
    return {
        "company": {
            "symbol": data.get("symbol"),
            "name": data.get("company_name"),
            "market": data.get("market"),
            "industry": data.get("industry"),
            "data_status": data.get("data_status"),
        },
        "research": {
            "version_no": version.get("version_no"),
            "status": version.get("status"),
            "conclusion": version.get("conclusion"),
            "six_dim": [
                {
                    "key": d.get("key"),
                    "title": d.get("title"),
                    "summary": d.get("summary"),
                    "counter": d.get("counter"),
                }
                for d in (version.get("six_dim") or [])
            ],
            "valuation": version.get("valuation"),
            "counter_evidence": version.get("counter_evidence"),
            "open_questions": version.get("open_questions"),
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "source": e.get("source"), "quote": e.get("quote")}
            for e in (data.get("evidence") or [])[:30]
        ],
    }


def ai_role_run(
    org_id: int,
    role_key: str,
    *,
    case_id: int | None = None,
    proposal_id: int | None = None,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """执行一个 AI 岗位：只输出建议，不改业务状态。"""
    role = str(role_key or "").strip().lower()
    task = {key: task_id for key, _label, task_id in AI_ROLE_CATALOG}.get(role)
    if not task:
        raise ValueError("未知 AI 岗位")
    if role == "debate":
        if not case_id:
            raise ValueError("缺少 case_id")
        return {"role": role, "task": task, "result": start_debate(org_id, case_id, actor_member_id=actor_member_id, use_ai=True)}
    if role == "risk":
        if not proposal_id:
            raise ValueError("缺少 proposal_id")
        return {"role": role, "task": task, "result": ai_risk_review(org_id, proposal_id)}
    if role == "research":
        if not case_id:
            raise ValueError("缺少 case_id")
        return {"role": role, "task": task, "result": ai_research_memo(org_id, case_id)}
    if not case_id:
        raise ValueError("缺少 case_id")
    payload = _role_case_payload(org_id, case_id)
    data = _ai_task(task, payload, _ROLE_PROMPTS[role])
    return {"role": role, "task": task, "memo": data}
