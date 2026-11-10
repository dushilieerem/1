# -*- coding: utf-8 -*-
"""公司池：种子、全市场同步、列表/更新、全局搜索、行业展示。

从 inst_service 拆出，保持函数名与签名不变；调用方仍从 inst_service 导入。
"""
from __future__ import annotations

import re
from typing import Any

from services.core.db import get_conn
from services.core.tenant import OrgScope
from services.marketdata import store as md

from . import repo
from .common import _row_dict
from .guards import _audit, _member, _require_role
from .stages import _stage_def

MAX_SINGLE_WEIGHT = 0.15
MAX_INDUSTRY_WEIGHT = 0.30
MIN_CASH_RATIO = 0.10
DEFAULT_NAV = 10_000_000.0

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


def list_companies(
    org_id: int,
    *,
    market: str | None = None,
    q: str | None = None,
    pool_status: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    rows, total = repo.companies(
        OrgScope(org_id), market=market, q=q, pool_status=pool_status, limit=limit, offset=offset
    )
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    out = []
    for r in rows:
        item = _row_dict(r) or {}
        item["ref_price"] = item.get("last_close") or item.get("ref_price")
        if item.get("industry_name"):
            item["industry"] = item["industry_name"]
        elif re.match(r"^\d{6}\.", str(item.get("industry") or "")):
            item["industry"] = None
        item["idea"] = _idea_questions(item, "watch")
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
        before = repo.set_company_pool(
            conn, OrgScope(org_id), company_id, pool_status,
            reason if pool_status == "dropped" else None,
        )
        if not before:
            raise LookupError("公司不存在")
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


def search_companies(org_id: int, q: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """全局股票搜索：按代码/名称/行业检索，并返回该公司当前研究案状态。"""
    query = str(q or "").strip()
    if not query:
        return []
    rows, _ = repo.companies(OrgScope(org_id), q=query, limit=max(1, min(int(limit), 20)))
    out: list[dict[str, Any]] = []
    with get_conn() as conn:
        for row in rows:
            item = _row_dict(row) or {}
            case = conn.execute(
                """
                SELECT c.id, c.stage_no, c.stage_key, c.stage_state,
                       (SELECT version_no FROM inst_research_version v
                         WHERE v.case_id=c.id ORDER BY version_no DESC LIMIT 1) AS version_no
                  FROM inst_research_case c
                 WHERE c.org_id=%s AND c.company_id=%s
                 ORDER BY c.updated_at DESC, c.id DESC LIMIT 1
                """,
                (org_id, int(item["id"])),
            ).fetchone()
            stage_no = int(case["stage_no"] or 0) if case else None
            stage = _stage_def(stage_no) if stage_no is not None else None
            out.append({
                "company_id": int(item["id"]),
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "market": item.get("market"),
                "industry": item.get("industry_name") or item.get("industry"),
                "data_status": item.get("data_status"),
                "pool_status": item.get("pool_status"),
                "ref_price": item.get("last_close") or item.get("ref_price"),
                "case_id": int(case["id"]) if case else None,
                "stage_no": stage_no,
                "stage_key": stage["key"] if stage else None,
                "stage_name": stage["name"] if stage else None,
                "version_no": int(case["version_no"]) if case and case.get("version_no") is not None else None,
            })
    return out


