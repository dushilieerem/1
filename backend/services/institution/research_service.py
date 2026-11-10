# -*- coding: utf-8 -*-
"""机构端研究域：立项、研究生成、六维分析、定稿门禁、版本锁定。

从 inst_service 拆出，保持函数名与签名不变；调用方仍从 inst_service 导入。
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
    CHAT_PROMPT,
    INDUSTRY_PROMPT,
    DIMENSION_PROMPTS as _DIMENSION_PROMPTS,
    RESEARCH_MEMO_PROMPT,
)
from services.institution import data_platform, inst_ai_store
from services.institution.report import render_research_report, report_filename
from services.marketdata import store as md

from . import repo
from .common import _clip_brief, _evidence_grade, _hash, _iso, _j, _pc, _row_dict, _yi
from .company_service import _mapped_industry
from .guards import POLICY_VERSION, _audit, _member, _require_role, _uid
from .stages import _record_gate, _record_transition, _set_case_stage, _stage_def, _stage_payload


SIX_DIM_DEFS: tuple[tuple[str, str, str], ...] = (
    ("industry", "商业与产业", "行业规模、竞争结构、供需与周期"),
    ("business_model", "公司商业模式", "收入结构、客户价值、单位经济性与资本强度"),
    ("moat", "护城河", "品牌、成本、网络、转换成本与可持续性"),
    ("financial", "财务质量", "收入、利润、现金流、ROE 与三表勾稽"),
    ("governance", "CEO 与治理", "资本配置、承诺兑现、关联交易与治理结构"),
    ("valuation", "估值与价格", "PE/PB 分位、DCF 参数、安全边际"),
)
DIMENSION_TASK_IDS: dict[str, str] = {
    "industry": "inst.dim.industry",
    "business_model": "inst.dim.business_model",
    "moat": "inst.dim.moat",
    "financial": "inst.dim.financial",
    "governance": "inst.dim.governance",
    "valuation": "inst.dim.valuation",
}
_VAGUE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("双轮驱动", "两项业务共同驱动"),
    ("双轮", "两项业务"),
    ("闭环", "完整链路"),
    ("赋能", "支持"),
    ("生态化反", "业务协同"),
)
_TERM_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("TAM/SAM/SOM", "TAM/SAM/SOM（总市场/可服务市场/可获得市场）"),
    ("PS/EV-EBITDA", "PS/EV-EBITDA（市销率/企业价值倍数）"),
    ("EV/EBITDA", "EV/EBITDA（企业价值/息税折旧摊销前利润）"),
    ("CR3/CR5", "CR3/CR5（前三/前五企业市占率）"),
    ("driver-based", "按业务驱动因素拆分"),
    ("KAM", "KAM（关键审计事项）"),
    ("DCF", "DCF（现金流折现）"),
    ("ROE", "ROE（净资产收益率）"),
    ("PE/PB", "PE/PB（市盈率/市净率）"),
    ("CEO", "CEO（首席执行官）"),
)


def _ensure_version_hash(conn, version: Any) -> dict[str, Any]:
    """为旧版本补内容 hash；新版本在生成时已写入。"""
    row = dict(version)
    if row.get("content_hash"):
        return row
    ev_ids = [int(x) for x in (row.get("evidence_ids") or []) if str(x).isdigit()]
    evidence_rows = []
    if ev_ids:
        evidence_rows = conn.execute(
            "SELECT hash, available_time, as_of FROM inst_evidence WHERE id = ANY(%s) ORDER BY id",
            (ev_ids,),
        ).fetchall()
    cutoff = max(
        (
            str(e.get("available_time") or e.get("as_of"))
            for e in evidence_rows
            if e.get("available_time") or e.get("as_of")
        ),
        default=date.today().isoformat(),
    )
    digest = _hash(
        {
            "case_id": row.get("case_id"),
            "six_dim": row.get("six_dim") or [],
            "industry_analysis": row.get("industry_analysis"),
            "valuation": row.get("valuation"),
            "conclusion": row.get("conclusion"),
            "assumptions": row.get("assumptions") or [],
            "counter_evidence": row.get("counter_evidence") or [],
            "open_questions": row.get("open_questions") or [],
            "evidence_ids": ev_ids,
            "evidence_hashes": sorted(str(e.get("hash") or "") for e in evidence_rows),
            "cutoff": cutoff,
        }
    )
    conn.execute(
        "UPDATE inst_research_version SET content_hash=%s, cutoff=COALESCE(cutoff,%s) WHERE id=%s",
        (digest, cutoff, row["id"]),
    )
    row["content_hash"] = digest
    row["cutoff"] = row.get("cutoff") or cutoff
    return row


def list_cases(org_id: int, *, company_id: int | None = None) -> list[dict[str, Any]]:
    rows = repo.cases(OrgScope(org_id), company_id=company_id)
    return [_row_dict(r) or {} for r in rows]


def start_research(org_id: int, company_id: int, actor_member_id: int | None) -> dict[str, Any]:
    """搜索/自选进入研究：同公司已有案则返回当前案，否则新建；保证一股一流程。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        company = conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s", (company_id, org_id)
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        _lock_company_case(conn, org_id, company_id)
        case_id = _existing_case_id(conn, org_id, company_id)
        created = False
        if case_id is None:
            case_no = f"RC-{date.today():%Y%m%d}-{company['symbol'].split('.')[0]}-{_uid()[:4]}"
            row = conn.execute(
                "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, stage_no, stage_key, stage_gate, created_by) "
                "VALUES (%s,%s,%s,'draft',1,'research','{\"stage_no\":1,\"gate\":\"研究定稿\"}'::jsonb,%s) RETURNING id",
                (org_id, company_id, case_no, actor_member_id),
            ).fetchone()
            case_id = int(row["id"])
            created = True
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="research.case.start",
                object_type="inst_research_case",
                object_id=case_id,
                after={"company_id": company_id, "case_no": case_no, "source": "search"},
            )
        if str(company.get("pool_status")) != "research":
            conn.execute(
                "UPDATE inst_company SET pool_status='research', drop_reason=NULL, updated_at=NOW() "
                "WHERE id=%s AND org_id=%s",
                (company_id, org_id),
            )
    data = get_case(org_id, case_id) or {}
    data["created"] = created
    return data


def _lock_company_case(conn, org_id: int, company_id: int) -> None:
    """同一公司串行化立案，避免并发双击生成重复研究案。"""
    del org_id  # company_id 全局唯一，无需再拼 org
    conn.execute("SELECT pg_advisory_xact_lock(7301, %s::int)", (int(company_id),))


def _existing_case_id(conn, org_id: int, company_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM inst_research_case
         WHERE org_id=%s AND company_id=%s
         ORDER BY updated_at DESC, id DESC LIMIT 1
        """,
        (org_id, company_id),
    ).fetchone()
    return int(row["id"]) if row else None


def create_case(org_id: int, company_id: int, actor_member_id: int | None) -> dict[str, Any]:
    """立案：同一公司只保留一个研究案；已存在时返回当前案（created=false）。"""
    created = False
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        company = conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s", (company_id, org_id)
        ).fetchone()
        if not company:
            raise LookupError("公司不存在")
        _lock_company_case(conn, org_id, company_id)
        case_id = _existing_case_id(conn, org_id, company_id)
        if case_id is None:
            case_no = f"RC-{date.today():%Y%m%d}-{company['symbol'].split('.')[0]}-{_uid()[:4]}"
            row = conn.execute(
                "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, stage_no, stage_key, stage_gate, created_by) "
                "VALUES (%s,%s,%s,'draft',1,'research','{\"stage_no\":1,\"gate\":\"研究定稿\"}'::jsonb,%s) RETURNING id",
                (org_id, company_id, case_no, actor_member_id),
            ).fetchone()
            case_id = int(row["id"])
            created = True
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="research.case.create",
                object_type="inst_research_case",
                object_id=case_id,
                after={"company_id": company_id, "case_no": case_no},
            )
    data = get_case(org_id, case_id) or {}
    data["created"] = created
    return data


def get_case(org_id: int, case_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        case = repo.case(OrgScope(org_id), case_id, conn=conn)
        if not case:
            return None
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
    symbol = str(out.get("symbol") or "")
    if symbol:
        bar = md.latest_bar(symbol, adjust="none")
        if bar and bar.get("close") is not None:
            out["ref_price"] = bar["close"]
            out["last_close"] = bar["close"]
            out["price_as_of"] = bar.get("trade_date")
    out["tasks"] = [_row_dict(r) for r in tasks]
    out["versions"] = [_row_dict(r) for r in versions]
    out["overall_score"] = _overall_score(
        (out["versions"][0] or {}).get("six_dim") if out["versions"] else None
    )
    out["evidence"] = [_row_dict(r) for r in evidence]
    out["debates"] = [_row_dict(r) for r in sessions]
    out["proposals"] = [_row_dict(r) for r in proposals]
    out["exit_case"] = _row_dict(exit_case)
    stage_no = out.get("stage_no")
    if stage_no is None:
        stage_no = _derive_case_stage(out)
    out.update(_stage_payload(stage_no))
    out["stage_state"] = out.get("stage_state") or "in_progress"
    out["stage_gate"] = out.get("stage_gate") or {"stage_no": int(stage_no), "gate": _stage_def(stage_no)["gate"]}
    out["locks"] = {
        "research": next(
            (
                {"version_id": int(v["id"]), "version_no": int(v["version_no"]), "locked_at": _iso(v.get("locked_at"))}
                for v in out["versions"]
                if str(v.get("status")) == "approved" and v.get("locked_at")
            ),
            None,
        ),
        "proposal": next(
            (
                {"proposal_id": int(p["id"]), "version_no": int(p.get("current_version_no") or 0), "locked_at": _iso(p.get("locked_at"))}
                for p in out["proposals"]
                if p.get("locked_at") and str(p.get("status")) not in {"draft", "rejected", "frozen"}
            ),
            None,
        ),
    }
    return out


def _derive_case_stage(case: dict[str, Any]) -> int:
    """旧数据兜底：没有 stage_no 时按版本/议案粗略推导。"""
    proposals = case.get("proposals") or []
    if any(str(p.get("status")) in {"executed"} for p in proposals):
        return 5
    if any(str(p.get("status")) in {"authorized"} for p in proposals):
        return 4
    if any(str(p.get("status")) in {"partner_review", "risk_precheck", "chairman_review", "frozen", "rejected"} for p in proposals):
        return 3
    versions = case.get("versions") or []
    if any(str(v.get("status")) == "approved" for v in versions):
        return 2
    return 1


def _dim_status(has_data: bool) -> str:
    return "done" if has_data else "partial"


def _median(values: list[Any]) -> float | None:
    nums = sorted(float(v) for v in values if v is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    return nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2


def _peer_summary(peers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(peers),
        "with_financials": sum(1 for p in peers if p.get("revenue_yoy") is not None or p.get("gross_margin") is not None),
        "with_valuation": sum(1 for p in peers if p.get("pe_ttm") is not None or p.get("pb_mrq") is not None),
        "revenue_yoy_median": _median([p.get("revenue_yoy") for p in peers]),
        "gross_margin_median": _median([p.get("gross_margin") for p in peers]),
        "net_margin_median": _median([p.get("net_margin") for p in peers]),
        "roe_median": _median([p.get("roe") for p in peers]),
        "pe_median": _median([p.get("pe_ttm") for p in peers if p.get("pe_ttm") is not None and float(p["pe_ttm"]) > 0]),
        "pb_median": _median([p.get("pb_mrq") for p in peers if p.get("pb_mrq") is not None and float(p["pb_mrq"]) > 0]),
        "sample_symbols": [p.get("symbol") for p in peers[:10]],
        "note": "同业中位数仅作对照，不代表公司自身数据；样本为同申万一级行业、按市值靠前的公司。",
    }


def _history_summary(fin: list[dict[str, Any]]) -> dict[str, Any]:
    annual = [f for f in fin if str(f.get("report_date") or "")[5:7] == "12"]
    series = annual or fin
    ordered = list(reversed(series))
    gross = [f.get("gross_margin") for f in series]
    roe = [f.get("roe") for f in series]
    ocf_ratio = [
        (float(f["operating_cf"]) / float(f["net_profit"]))
        for f in series
        if f.get("operating_cf") is not None and f.get("net_profit") not in (None, 0)
    ]
    fcf_positive = [
        1 if f.get("free_cash_flow") is not None and float(f["free_cash_flow"]) > 0 else 0
        for f in series
    ]
    revenue_cagr = None
    if len(ordered) >= 2:
        start, end = ordered[0].get("revenue"), ordered[-1].get("revenue")
        if start and end and float(start) > 0 and float(end) > 0:
            years = max(1, len(ordered) - 1)
            revenue_cagr = (float(end) / float(start)) ** (1 / years) - 1
    return {
        "annual_points": len(annual),
        "periods": len(series),
        "start_report": ordered[0].get("report_date") if ordered else None,
        "end_report": ordered[-1].get("report_date") if ordered else None,
        "revenue_cagr": revenue_cagr,
        "gross_margin_median": _median(gross),
        "roe_median": _median(roe),
        "ocf_to_profit_median": _median(ocf_ratio),
        "fcf_positive_ratio": (sum(fcf_positive) / len(fcf_positive)) if fcf_positive else None,
        "note": "按年报（12-31）计算；不足 10 年时用现有年报；季度序列用于最新趋势。",
    }


def _net_debt_proxy(latest_fin: dict[str, Any]) -> dict[str, Any] | None:
    liabilities = latest_fin.get("total_liabilities")
    cash = latest_fin.get("cash")
    if liabilities is None or cash is None:
        return None
    value = float(liabilities) - float(cash)
    return {
        "value": value,
        "label": "总负债 − 现金（近似净债务，未拆分有息负债/受限资金/少数股东）",
    }


def _data_completeness(
    *,
    ind: dict[str, Any],
    peers: list[dict[str, Any]],
    history: dict[str, Any],
    fin: list[dict[str, Any]],
    val: dict[str, Any],
    holders: dict[str, Any] | None = None,
    segments: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    debt: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    peer_note = f"同业公司 {len(peers)} 家" if peers else "同业公司未取到"
    business_have = ["10 年合并财务（营收/毛利/现金流）", peer_note]
    business_missing = [
        "分产品/分地区收入与毛利",
        "前五大客户占比",
        "量价拆分（销量/单价）",
        "成本结构",
        "合同负债/预收款",
        "经常性收入占比",
        "CAC/LTV/回收期",
    ]
    if segments:
        business_have.append(f"分部收入/毛利（{segments.get('report_date')}，产品/地区/行业）")
        business_missing.remove("分产品/分地区收入与毛利")
    if debt and (debt.get("advance_receipts") or 0) > 0:
        business_have.append("预收款项（非合同负债，合同负债源未单列）")
        if "合同负债/预收款" in business_missing:
            business_missing.remove("合同负债/预收款")
            business_missing.append("合同负债（源数据为空，B 组补）")
    financial_have = ["10 年合并三表", "存货/应收/现金/负债总额"]
    financial_missing = [
        "附注明细（应收账龄/存货构成/在建/商誉/有息负债/受限资金）",
        "审计意见与 KAM",
        "问询函与回复",
        "母公司报表",
        "非经常性损益/政府补助明细",
    ]
    financial: dict[str, Any] = {
        "level": "partial" if fin else "missing",
        "have": financial_have,
        "missing": financial_missing,
    }
    if audit:
        financial_have.append(
            f"审计意见类型（{audit.get('opinion_type') or '待补'}，{audit.get('report_date')}）"
        )
        financial_missing.remove("审计意见与 KAM")
        financial_missing.append("审计机构/KAM/问询函（B 组）")
        financial["level"] = "partial" if fin else "missing"
        if audit.get("red_flag"):
            financial["gate_cap"] = "fail"
            financial["red_flag"] = f"审计意见为非标准：{audit.get('opinion_type')}"
    if debt:
        if debt.get("is_financial"):
            financial_have.append("有息负债/净债务不适用（金融企业）")
        elif debt.get("net_debt") is not None:
            financial_have.append("有息负债/净债务（数据业务口径：不含租赁负债，未扣受限资金）")
        if (debt.get("advance_receipts") or 0) > 0:
            financial_have.append("预收款项（>0，有余额证据）")
        financial_missing.append("受限资金/租赁负债/合同负债（源数据为空，B 组补）")
    governance_have: list[str] = []
    governance_missing = [
        "实控人/董事长履历",
        "一致行动人认定（前十大只有报告期合计）",
        "质押冻结",
        "关联交易与资金占用",
        "对外担保",
        "承诺兑现记录",
        "分红/回购/融资历史",
        "高管变动/处罚诉讼",
        "董事会结构",
    ]
    governance: dict[str, Any] = {
        "level": "missing",
        "have": governance_have,
        "missing": governance_missing,
        "gate_cap": "fail",
        "gate_note": "治理核心字段未齐，按不可买入处理；前十大股东比例不代表控制权。",
    }
    if holders:
        governance["level"] = "partial"
        governance_have.append(
            f"前十大股东（{holders.get('report_date')}，合计 {holders.get('top10_ratio_pct')}%，未认定一致行动人）"
        )
    return {
        "industry": {
            "level": "partial" if ind else "missing",
            "have": ["申万行业分类/名称", peer_note],
            "missing": ["行业规模 TAM/SAM/SOM", "CR3/CR5 与主要玩家份额", "行业价格/产量/库存/产能", "政策与标准文件", "海外对标"],
        },
        "business_model": {
            "level": "partial" if fin else "missing",
            "have": business_have,
            "missing": business_missing,
        },
        "moat": {
            "level": "partial" if fin and peers else "missing",
            "have": ["10 年财务摘要", "ROE/毛利率序列", peer_note],
            "missing": ["份额序列", "价格序列/价格战历史", "客户留存/续约率", "专利/牌照清单"],
        },
        "financial": financial,
        "governance": governance,
        "valuation": {
            "level": "partial" if val else "missing",
            "have": [
                "PE/PB 与 3 年分位",
                "股息率",
                "净债务（有息负债合计−现金；不含租赁负债、未扣受限资金）"
                if debt and debt.get("net_debt_applicable")
                else "净债务近似（总负债−现金）",
                peer_note,
            ],
            "missing": [
                "PS/EV-EBITDA 序列与分位",
                "一致预期（营收/净利/目标价）",
                "driver-based 财务预测",
                "期权/受限资金/租赁负债（B 组）",
                "无风险利率/β/ERP",
            ],
        },
    }


def _build_research(company: dict[str, Any], mode: str = "full", targets: list[str] | None = None) -> dict[str, Any]:
    symbol = company["symbol"]
    bar = md.latest_bar(symbol, adjust="none")
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    risk = md.risk_stats(symbol, index_code=None if company.get("market") == "US" else "000300.SH") or {}
    ind = md.industry_latest(symbol) or {}
    fin = md.financials(symbol, limit=40)
    latest_fin = fin[0] if fin else {}
    peers = md.industry_peers(symbol, ind.get("industry_code")) if ind else []
    peer_summary = _peer_summary(peers)
    history_summary = _history_summary(fin)
    share_capital = md.share_capital_history(symbol)
    dividends = md.dividend_history(symbol)
    data_as_of = (bar or {}).get("trade_date") or latest_fin.get("notice_date") or date.today().isoformat()
    with get_conn() as conn:
        holder_summary = data_platform.holder_summary(conn, symbol, data_as_of)
        float_holder_summary = data_platform.holder_summary(conn, symbol, data_as_of, float_only=True)
        segment_summary = data_platform.segment_summary(conn, symbol, data_as_of)
        audit_summary = data_platform.audit_summary(conn, symbol, data_as_of)
        debt_summary = data_platform.interest_debt_summary(conn, symbol, data_as_of)
    net_debt = _net_debt_proxy(latest_fin)
    if debt_summary:
        if debt_summary.get("is_financial"):
            net_debt = {
                "value": None,
                "applicable": False,
                "label": "金融企业：有息负债合计与净债务均为 NULL（不适用），不能作为净债务桥。",
                "source": debt_summary.get("source"),
            }
        elif debt_summary.get("net_debt") is not None:
            net_debt = {
                "value": float(debt_summary["net_debt"]),
                "applicable": True,
                "label": "有息负债合计 − 现金（数据业务口径；合计不含租赁负债，现金未扣受限资金）",
                "source": debt_summary.get("source"),
            }
    valuation_extra = {
        "dividend_yield_ttm": val.get("dividend_yield_ttm"),
        "net_debt_proxy": net_debt,
        "interest_debt": debt_summary,
        "share_capital": share_capital,
        "dividends": dividends,
    }
    # 分部对账必须用同一报告期的合并营收，不能用最新半年报。
    if segment_summary:
        seg_date = str(segment_summary.get("report_date") or "")[:10]
        annual = next(
            (f for f in fin if str(f.get("report_date") or "")[:10] == seg_date), None
        )
        annual_revenue = float(annual.get("revenue") or 0) if annual else 0.0
        if annual_revenue > 0:
            for block in (segment_summary.get("types") or {}).values():
                block["revenue_vs_consolidated_pct"] = round(
                    (float(block.get("revenue_total") or 0) - annual_revenue)
                    / annual_revenue
                    * 100,
                    4,
                )
    data_completeness = _data_completeness(
        ind=ind,
        peers=peers,
        history=history_summary,
        fin=fin,
        val=val,
        holders=holder_summary,
        segments=segment_summary,
        audit=audit_summary,
        debt=debt_summary,
    )
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
        source = "ifind:parquet" if kind in {"market", "financial"} else "eastmoney"
        as_of = (bar or {}).get("trade_date") or latest_fin.get("notice_date") or date.today().isoformat()
        grade = _evidence_grade(source, kind)
        evidence.append(
            {
                "title": title,
                "quote": quote,
                "source": source,
                "evidence_type": kind,
                "grade": grade,
                "as_of": as_of,
                "event_time": as_of,
                "available_time": as_of,
                "cutoff": as_of,
                "document_id": None,
                "page_ref": None,
                "source_uri": None,
                "hash": _hash([title, quote, source, grade, as_of]),
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
                "summary": _clip_brief(summary),
                "checks": [_clip_brief(x) for x in checks],
                "counter": [_clip_brief(x) for x in counter],
                "evidence_idx": [x for x in evs if x is not None],
            }
        )

    dim_keys = {d[0] for d in SIX_DIM_DEFS}
    if targets is not None:
        want = {t for t in targets if t in dim_keys}
        if not want and "industry" not in targets:
            raise ValueError("退回目标至少包含一个行业/维度")
    else:
        if mode != "full" and mode not in dim_keys:
            raise ValueError("mode 必须是 full 或六个维度之一")
        want = dim_keys if mode == "full" else {mode}
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
    is_financial = bool(debt_summary and debt_summary.get("is_financial"))
    if has_fin and latest_fin.get("net_profit") and price and not is_financial:
        # 简易模型：以最新自由现金流/净利为起点，给出测算区间，不构成目标价
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
            enterprise_value = fcf * (1 + growth) / max(0.01, discount - terminal)
            net_debt_value = float((net_debt or {}).get("value") or 0.0)
            equity_value = enterprise_value - net_debt_value
            if equity_value > 0:
                per_share = equity_value / float(shares)
                valuation = {
                    "method": "owner_earnings_proxy_net_debt",
                    "is_demo": True,
                    "assumptions": {
                        "revenue_growth": growth,
                        "cash_flow_margin": None,
                        "discount_rate": discount,
                        "terminal_growth": terminal,
                    },
                    "enterprise_value": enterprise_value,
                    "equity_value": equity_value,
                    "net_debt_proxy": net_debt,
                    "per_share": per_share,
                    "low": per_share * 0.75,
                    "base": per_share,
                    "high": per_share * 1.25,
                    "shares_source": shares_source,
                    "note": (
                        "简易测算口径，不构成目标价；股权价值 = 企业价值 − 净债务（见 net_debt_proxy.label），"
                        "未计税费、营运资本、汇率与治理折价；股本为估算值。"
                    ),
                }
            else:
                valuation = {
                    "method": "owner_earnings_proxy_net_debt",
                    "is_demo": True,
                    "error": "净债务近似后股权价值为负，无法给出估值区间。",
                    "enterprise_value": enterprise_value,
                    "equity_value": equity_value,
                    "net_debt_proxy": net_debt,
                    "note": "简易测算口径，不构成目标价；净债务口径见 net_debt_proxy.label。",
                }
    if is_financial and has_fin:
        valuation = {
            "method": "relative_only",
            "is_demo": True,
            "error": "金融企业不适用净债务桥（有息负债/净债务为 NULL），简易模型仅保留相对估值。",
            "net_debt_proxy": net_debt,
            "note": "银行/保险/证券不计算企业价值与净债务桥；请使用 PB/ROE 等相对估值。",
        }
    industry_analysis = {
        "key": "industry",
        "title": "行业分析",
        "question": "行业空间、景气周期、产业链与竞争格局处于什么位置？",
        "status": _dim_status(bool(ind)),
        "summary": _clip_brief(
            f"行业：{ind_label}；行业规模、增速与竞争格局需补充数据后判断。"
        ),
        "checks": [
            _clip_brief(f"行业归属：{ind.get('industry_code') or '待补充'} / {ind_label}"),
            _clip_brief(f"参考价：{price or '待补充'}"),
        ],
        "counter": [_clip_brief("行业分类为当前快照，历史归属需另行核验")],
        "open_questions": [],
        "data_gaps": [] if ind else ["行业规模/份额/景气数据未接入"],
        "evidence_idx": [ev_ind] if ev_ind is not None else [],
        "engine": "rule",
    }
    gate_for_level = {"missing": "fail", "partial": "watch", "sufficient": "pass"}
    for dim_item in dims:
        completeness = data_completeness.get(dim_item["key"]) or {}
        dim_item["data_completeness"] = completeness
        dim_item.setdefault(
            "gate",
            completeness.get("gate_cap")
            or gate_for_level.get(completeness.get("level"), "watch"),
        )
    industry_completeness = data_completeness.get("industry") or {}
    industry_analysis["data_completeness"] = industry_completeness
    industry_analysis["gate"] = (
        industry_completeness.get("gate_cap")
        or gate_for_level.get(industry_completeness.get("level"), "watch")
    )

    return {
        "dims": dims,
        "evidence": evidence,
        "industry_analysis": industry_analysis,
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
            "as_of": (bar or {}).get("trade_date") or latest_fin.get("notice_date") or date.today().isoformat(),
            "price": price,
            "valuation": val,
            "percentile": pct,
            "risk": risk,
            "industry": ind,
            "industry_name": company.get("industry"),
            "financials": fin,
            "peer_summary": peer_summary,
            "history_summary": history_summary,
            "valuation_extra": valuation_extra,
            "holder_summary": holder_summary,
            "float_holder_summary": float_holder_summary,
            "segment_summary": segment_summary,
            "audit_summary": audit_summary,
            "interest_debt_summary": debt_summary,
            "data_completeness": data_completeness,
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
        "industry_name": facts.get("industry_name"),
        "financials": facts.get("financials") or [],
        "peer_summary": facts.get("peer_summary"),
        "history_summary": facts.get("history_summary"),
        "valuation_extra": facts.get("valuation_extra"),
        "holder_summary": facts.get("holder_summary"),
        "float_holder_summary": facts.get("float_holder_summary"),
        "segment_summary": facts.get("segment_summary"),
        "audit_summary": facts.get("audit_summary"),
        "interest_debt_summary": facts.get("interest_debt_summary"),
        "data_completeness": facts.get("data_completeness"),
        "platform_rules": {
            "level_gate": {"missing": "fail", "partial": "watch", "sufficient": "pass"},
            "note": (
                "本维 data_completeness.level=partial 时 gate 最高 watch；level=missing 时 gate 必须 fail。"
                "缺失项只能写入 data_gaps，不得用财务结果反推行业规模/份额、分部/客户、治理事实或审计结论。"
                "peer_summary 只作同业对照，不得当作公司自身数据。"
            ),
        },
        "data_gaps": facts.get("data_gaps") or [],
    }
    if key == "governance":
        payload["governance_note"] = (
            "输入不含股东名册、质押冻结、关联交易、对外担保、高管履历或审计意见；"
            "治理数据缺失时 gate 必须为 fail（不可买入），不得用“待补充”替代。"
        )
    if key == "business_model":
        payload["business_model_note"] = (
            "输入含 10 年合并财务和（如已接入）分部收入/毛利；仍没有前五大客户、量价拆分、成本结构、"
            "合同负债或渠道数据。不得声称增长来自量/价/结构，只能从分部/财务结构推断并标注缺口。"
        )
    return payload


def _run_dimension_agent(key: str, facts: dict[str, Any]) -> dict[str, Any]:
    from ai.router import available_task, run_task

    task_id = DIMENSION_TASK_IDS[key]
    if not available_task(task_id):
        return {"error": "AI 未配置"}
    payload = _agent_payload(facts, key)
    system, _ = get_effective_prompt(task_id, _DIMENSION_PROMPTS[key])
    out = run_task(
        task_id,
        messages=[
            {"role": "system", "content": system},
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


def _run_industry_agent(facts: dict[str, Any]) -> dict[str, Any]:
    from ai.router import available_task, run_task

    if not available_task("inst.industry"):
        return {"error": "AI 未配置"}
    payload = _agent_payload(facts, "industry")
    system, _ = get_effective_prompt("inst.industry", INDUSTRY_PROMPT)
    try:
        out = run_task(
            "inst.industry",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
        )
    except Exception as exc:  # AI 上游失败/空内容不应让整个研究 500
        return {"error": f"行业 Agent 暂不可用：{str(exc)[:240]}"}
    data = out.get("data")
    if not isinstance(data, dict):
        content = str(out.get("content") or "")
        data = json.loads(content) if content.strip().startswith("{") else {}
    if not isinstance(data, dict) or not str(data.get("summary") or "").strip():
        return {"error": "行业 Agent 返回缺少 summary"}
    return {"data": data}


def _apply_data_gate(data: dict[str, Any], completeness: dict[str, Any] | None) -> dict[str, Any]:
    level = str((completeness or {}).get("level") or "")
    cap = str((completeness or {}).get("gate_cap") or "")
    if cap not in {"pass", "watch", "fail"}:
        cap = {"missing": "fail", "partial": "watch", "sufficient": "pass"}.get(level) or ""
    if not cap:
        return data
    gate = str(data.get("gate") or "").lower()
    if gate not in {"pass", "watch", "fail"}:
        gate = "watch"
    order = {"fail": 0, "watch": 1, "pass": 2}
    if order[gate] > order[cap]:
        data["gate_original"] = gate
        data["gate"] = cap
        data["gate_note"] = f"数据完备性为 {level}，gate 由 {gate} 降为 {cap}。"
    data["data_completeness"] = completeness
    return data


_VAGUE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("双轮驱动", "两项业务共同驱动"),
    ("双轮", "两项业务"),
    ("闭环", "完整链路"),
    ("赋能", "支持"),
    ("生态化反", "业务协同"),
)

_TERM_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("TAM/SAM/SOM", "TAM/SAM/SOM（总市场/可服务市场/可获得市场）"),
    ("PS/EV-EBITDA", "PS/EV-EBITDA（市销率/企业价值倍数）"),
    ("EV/EBITDA", "EV/EBITDA（企业价值/息税折旧摊销前利润）"),
    ("CR3/CR5", "CR3/CR5（前三/前五企业市占率）"),
    ("driver-based", "按业务驱动因素拆分"),
    ("KAM", "KAM（关键审计事项）"),
    ("DCF", "DCF（现金流折现）"),
    ("ROE", "ROE（净资产收益率）"),
    ("PE/PB", "PE/PB（市盈率/市净率）"),
    ("CEO", "CEO（首席执行官）"),
)


def _clean_agent_text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    for bad, good in _VAGUE_REPLACEMENTS:
        text = text.replace(bad, good)
    for term, explained in _TERM_GLOSSARY:
        if term in text and explained not in text:
            text = text.replace(term, explained)
    # 术语解释后清理中文之间的多余空格，避免“CEO（首席执行官） 与治理”。
    return re.sub(r"(?<=[一-鿿）)])\s+(?=[一-鿿（(])", "", text)


def _first_sentence(text: str) -> str:
    for sep in ("。", "；", "\n"):
        if sep in text:
            return text.split(sep, 1)[0].strip(" ，,;；。")
    return text.strip(" ，,;；。")


def _four_line_output(
    data: dict[str, Any],
    *,
    title: str,
    gate: str | None,
    gaps: list[Any] | None,
    as_of: str,
) -> dict[str, Any]:
    """把 Agent 输出压成四行：判断 / 依据 / 影响 / 动作，并校验评分基准。"""
    judgment = _clean_agent_text(data.get("judgment") or data.get("one_line"))
    placeholders = ("待补充", "暂无", "—")
    if not judgment:
        summary_text = _clean_agent_text(data.get("summary"))
        if summary_text and not any(x in summary_text for x in placeholders):
            judgment = _first_sentence(summary_text)
    incomplete = not judgment or any(x in judgment for x in placeholders)
    if not judgment or incomplete:
        judgment = _clean_agent_text(
            f"{title}的关键数据尚未取得，当前不能形成可执行判断。"
        )
        incomplete = True

    checks = [_clean_agent_text(x) for x in (data.get("checks") or []) if _clean_agent_text(x)]
    raw_refs = data.get("evidence_ids") or []
    if isinstance(raw_refs, str):
        raw_refs = [x.strip().strip('"\'') for x in raw_refs.strip("[]").split(",")]
    refs = [str(x).strip() for x in raw_refs if str(x).strip()]
    ref_text = "、".join(refs[:6])
    basis = _clean_agent_text(data.get("basis"))
    if not basis:
        basis = "；".join(checks[:2])
    if ref_text:
        basis = f"{basis}；证据 {ref_text}；截至 {as_of}" if basis else f"证据 {ref_text}；截至 {as_of}"
    else:
        basis = f"截至 {as_of}，输入未提供可引用的证据 ID 与数据"

    missing: list[str] = []
    for gap in gaps or []:
        text = (
            _clean_agent_text(gap.get("missing") or gap.get("path"))
            if isinstance(gap, dict)
            else _clean_agent_text(gap)
        )
        if text and text not in missing:
            missing.append(text)
    completeness = data.get("data_completeness") or {}
    for item in completeness.get("missing") or []:
        text = _clean_agent_text(item)
        if text and text not in missing:
            missing.append(text)

    impact = _clean_agent_text(data.get("impact") or data.get("implication_for_company"))
    if not impact:
        if incomplete or str(gate) == "fail":
            impact = "关键数据缺失，估值与仓位不调整，维持观察。"
        elif str(gate) == "watch":
            impact = "仅支持观察，估值与仓位不高于同业基准。"
        else:
            impact = "支持纳入估值与仓位，幅度按同业中位或历史分位复核。"

    action = _clean_agent_text(data.get("action"))
    if action in {"缺", "缺数据", "待补充", "缺失", "暂无"}:
        action = ""
    if not action:
        if missing:
            action = f"补数据：{'；'.join(missing[:3])}；补齐前不进入定稿。"
        elif incomplete:
            action = f"补数据：补充{title}关键数据及证据 ID 与日期；补齐前不进入定稿。"
        else:
            action = "继续：按当前证据推进，下一复核点见反证条件。"
    elif not refs and not action.startswith(("补数据", "放弃")):
        action = f"补数据：补充{title}的证据 ID、数据与日期；补齐前不进入定稿。"

    rating = data.get("rating")
    score = data.get("score_10")
    benchmark = _clean_agent_text(data.get("rating_benchmark"))
    rating_note = _clean_agent_text(data.get("rating_note"))
    if score is not None:
        score = round(float(score), 1)
    if rating is None and score is not None:
        rating = round(score / 2, 1)
    if score is None and rating is not None:
        score = round(float(rating) * 2, 1)
    if (rating is not None or score is not None) and not benchmark:
        rating = None
        score = None
        rating_note = "评分缺少基准（同业中位或历史分位），未采用。"

    return {
        "judgment": judgment,
        "basis": basis,
        "impact": impact,
        "action": action,
        "rating_benchmark": benchmark or None,
        "rating_note": rating_note or None,
        "rating": rating,
        "score_10": score,
    }


def _overall_score(dims: list[Any] | None) -> float | None:
    scores: list[float] = []
    for dim in dims or []:
        if not isinstance(dim, dict):
            continue
        score = dim.get("score_10")
        if score is None and dim.get("rating") is not None:
            score = round(float(dim["rating"]) * 2, 1)
        if score is not None:
            scores.append(float(score))
    return round(sum(scores) / len(scores), 1) if scores else None


def _merge_industry(
    built: dict[str, Any],
    result: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    data = (result or {}).get("data") or {}
    if data:
        complete = (built.get("facts") or {}).get("data_completeness") or {}
        data = _apply_data_gate(data, complete.get("industry"))
    if not data:
        block = dict(fallback or {})
        block["engine"] = "rule"
        block["agent_error"] = str((result or {}).get("error") or "")
        block.update(_four_line_output(
            block,
            title="行业",
            gate=block.get("gate"),
            gaps=block.get("data_gaps"),
            as_of=(built.get("facts") or {}).get("as_of") or date.today().isoformat(),
        ))
        return block
    four = _four_line_output(
        data,
        title="行业",
        gate=data.get("gate"),
        gaps=data.get("data_gaps"),
        as_of=(built.get("facts") or {}).get("as_of") or date.today().isoformat(),
    )
    evidence = list(built.get("evidence") or [])
    ev_idx: list[int] = []
    for ev in data.get("evidence") or []:
        title = str(ev.get("title") or "").strip()
        quote = str(ev.get("quote") or "").strip()
        if not title or not quote:
            continue
        idx = len(evidence)
        evidence.append(
            {
                "title": title[:200],
                "quote": quote[:500],
                "source": str(ev.get("source") or "agent")[:80],
                "evidence_type": "research",
                "as_of": (built.get("facts") or {}).get("as_of") or date.today().isoformat(),
                "hash": _hash([title, quote, "agent"]),
                "_idx": idx,
            }
        )
        ev_idx.append(idx)
    built["evidence"] = evidence
    return {
        "key": "industry",
        "title": "行业分析",
        "question": str(data.get("question") or "行业空间、景气周期、产业链与竞争格局处于什么位置？"),
        "status": "partial" if data.get("data_gaps") else "done",
        "summary": _clip_brief(data.get("summary")),
        "checks": [_clip_brief(x) for x in (data.get("checks") or [])][:5],
        "counter": [_clip_brief(x) for x in (data.get("counter") or [])][:3],
        "open_questions": [_clip_brief(x) for x in (data.get("open_questions") or [])][:3],
        "data_gaps": [_clip_brief(x) for x in (data.get("data_gaps") or [])][:5],
        "evidence_idx": ev_idx,
        "direct_evidence_ids": [
            int(x) for x in (data.get("evidence_ids") or []) if str(x).isdigit()
        ],
        "confidence": data.get("confidence"),
        "confidence_label": data.get("confidence_label"),
        "analysis_md": str(data.get("analysis_md") or ""),
        "attractiveness": data.get("attractiveness"),
        "gate": data.get("gate"),
        "one_line": data.get("one_line"),
        "headline": data.get("headline"),
        "kpis": data.get("kpis") or [],
        "market_size": data.get("market_size"),
        "competition": data.get("competition"),
        "key_variables": data.get("key_variables") or [],
        "falsifiers": data.get("falsifiers") or [],
        "implication_for_company": data.get("implication_for_company"),
        "judgment": four["judgment"],
        "basis": four["basis"],
        "impact": four["impact"],
        "action": four["action"],
        "rating_benchmark": four["rating_benchmark"],
        "rating_note": four["rating_note"],
        "gate": data.get("gate"),
        "gate_note": data.get("gate_note"),
        "data_completeness": data.get("data_completeness"),
        "engine": "agent",
    }


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
    as_of = (built.get("facts") or {}).get("as_of") or date.today().isoformat()
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
            complete = (built.get("facts") or {}).get("data_completeness") or {}
            data = _apply_data_gate(data, complete.get(key))
            four = _four_line_output(
                data,
                title=title,
                gate=data.get("gate"),
                gaps=data.get("data_gaps"),
                as_of=as_of,
            )
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
                    "confidence_label": data.get("confidence_label"),
                    "rating": four["rating"],
                    "score_10": four["score_10"],
                    "rating_benchmark": four["rating_benchmark"],
                    "rating_note": four["rating_note"],
                    "judgment": four["judgment"],
                    "basis": four["basis"],
                    "impact": four["impact"],
                    "action": four["action"],
                    "gate": data.get("gate"),
                    "headline": data.get("headline"),
                    "kpis": data.get("kpis") or [],
                    "analysis_md": str(data.get("analysis_md") or ""),
                    "key_numbers": data.get("key_numbers") or [],
                    "falsifiers": data.get("falsifiers") or [],
                    "thesis_links": data.get("thesis_links") or [],
                    "gate": data.get("gate"),
                    "gate_note": data.get("gate_note"),
                    "data_completeness": data.get("data_completeness"),
                    "engine": "agent",
                    "agent": f"AI-{key}",
                    "evidence_idx": ev_idx,
                    "evidence_ids": [],
                    "direct_evidence_ids": [
                        int(x) for x in (data.get("evidence_ids") or []) if str(x).isdigit()
                    ],
                }
            )
            states[key] = status
        else:
            fallback = dict(fallback)
            fallback["engine"] = "rule"
            fallback["agent"] = f"AI-{key}"
            fallback["agent_error"] = err or "Agent 未返回有效结果"
            fallback["evidence_ids"] = []
            fallback.update(_four_line_output(
                fallback,
                title=str(fallback.get("title") or title),
                gate=fallback.get("gate"),
                gaps=fallback.get("data_gaps"),
                as_of=as_of,
            ))
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
    targets: list[str] | None = None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    # 1) 先校验权限并取公司，关闭连接后再跑 6 个模型 Agent，避免长时间占用 DB 连接
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        case = conn.execute(
            "SELECT c.*, co.symbol, co.name, co.market, co.industry, co.data_status, co.ref_price "
            "FROM inst_research_case c JOIN inst_company co ON co.id=c.company_id "
            "WHERE c.id=%s AND c.org_id=%s",
            (case_id, org_id),
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        if int(case["stage_no"] or 1) > 1:
            raise PermissionError("研究已锁定或已进入后续阶段，请先重开研究")
        company = dict(case)

    dim_keys = {d[0] for d in SIX_DIM_DEFS}
    if targets is not None:
        allowed = dim_keys | {"industry"}
        targets = list(dict.fromkeys(str(t) for t in targets))
        if not targets or any(t not in allowed for t in targets):
            raise ValueError("退回目标必须是行业或六个维度")
        keys = [d[0] for d in SIX_DIM_DEFS if d[0] in targets]
        rework = True
        mode_label = "rework"
    else:
        if mode != "full" and mode not in dim_keys:
            raise ValueError("mode 必须是 full 或六个维度之一")
        keys = [d[0] for d in SIX_DIM_DEFS] if mode == "full" else [mode]
        rework = mode != "full"
        mode_label = mode
    built = _build_research(company, mode=mode, targets=targets)
    run_industry = mode == "full" or (targets is not None and "industry" in targets)
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
    if keys:
        results = _run_dimension_agents(
            built["facts"],
            keys,
            on_event=lambda key, status, payload: _update_task_progress(case_id, key, status, payload),
        )
        built = _merge_agent_results(built, results, keys)
    if run_industry:
        industry_result = _run_industry_agent(built["facts"])
        built["industry_analysis"] = _merge_industry(
            built, industry_result, built.get("industry_analysis") or {}
        )

    # 2) 持久化：任务、证据、版本
    with get_conn() as conn:
        if mode == "full" and targets is None:
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
                      (org_id, case_id, evidence_type, grade, title, quote, source, as_of,
                       event_time, available_time, document_id, page_ref, source_uri, cutoff, hash, added_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (
                        org_id,
                        case_id,
                        ev.get("evidence_type") or "fact",
                        ev.get("grade") or _evidence_grade(str(ev.get("source") or ""), str(ev.get("evidence_type") or "fact")),
                        ev["title"],
                        ev.get("quote"),
                        ev["source"],
                        ev.get("as_of"),
                        ev.get("event_time") or ev.get("as_of"),
                        ev.get("available_time") or ev.get("as_of"),
                        ev.get("document_id"),
                        ev.get("page_ref"),
                        ev.get("source_uri"),
                        ev.get("cutoff") or ev.get("available_time") or ev.get("as_of"),
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

        def _scoped_evidence_ids(values: list[Any]) -> list[int]:
            ids = [int(x) for x in values if str(x).isdigit() and int(x) > 0]
            if not ids:
                return []
            rows = conn.execute(
                "SELECT id FROM inst_evidence WHERE id = ANY(%s) AND org_id=%s AND case_id=%s",
                (ids, org_id, case_id),
            ).fetchall()
            allowed = {int(r["id"]) for r in rows}
            return [x for x in ids if x in allowed]

        for dim in built["dims"]:
            mapped = [idx_to_id.get(i) for i in dim.pop("evidence_idx", []) if i in idx_to_id]
            direct = _scoped_evidence_ids(dim.pop("direct_evidence_ids", []))
            dim["evidence_ids"] = list(dict.fromkeys([*mapped, *direct]))
            for eid in direct:
                if eid not in ev_ids:
                    ev_ids.append(eid)
        industry_block = dict(built.get("industry_analysis") or {})
        mapped = [idx_to_id.get(i) for i in industry_block.pop("evidence_idx", []) if i in idx_to_id]
        direct = _scoped_evidence_ids(industry_block.pop("direct_evidence_ids", []))
        industry_block["evidence_ids"] = list(dict.fromkeys([*mapped, *direct]))
        for eid in direct:
            if eid not in ev_ids:
                ev_ids.append(eid)
        built["industry_analysis"] = industry_block

        # 单维重新分析：合并到最近一版，保留其余五维，而不是用只含一维的版本覆盖。
        existing = None
        if rework:
            existing = conn.execute(
                "SELECT * FROM inst_research_version WHERE case_id=%s "
                "ORDER BY version_no DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        if existing:
            selected = set(keys)
            new_dims = {d["key"]: d for d in built["dims"] if d.get("key") in selected}
            old_dims = [d for d in (existing["six_dim"] or []) if isinstance(d, dict)]
            merged = [new_dims.get(str(d.get("key")), d) for d in old_dims]
            for key in selected:
                if key not in {str(d.get("key")) for d in old_dims} and key in new_dims:
                    merged.append(new_dims[key])
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
            if not run_industry and existing.get("industry_analysis"):
                built["industry_analysis"] = existing["industry_analysis"]
            if "valuation" not in selected and existing["valuation"]:
                built["valuation"] = existing["valuation"]

        conn.execute("SELECT pg_advisory_xact_lock(7304, %s::int)", (case_id,))
        version_no = conn.execute(
            "SELECT COALESCE(MAX(version_no),0)+1 AS n FROM inst_research_version WHERE case_id=%s",
            (case_id,),
        ).fetchone()["n"]
        conclusion = "有条件通过" if built["data_gaps"] == [] else "待补充"
        assumptions = (
            [built["valuation"]["assumptions"]]
            if built.get("valuation") and built["valuation"].get("assumptions")
            else []
        )
        counter_evidence = [c for d in built["dims"] for c in d.get("counter", [])]
        open_questions = built["data_gaps"]
        version_evidence = conn.execute(
            "SELECT hash, available_time, as_of FROM inst_evidence "
            "WHERE id = ANY(%s) ORDER BY id",
            (ev_ids,),
        ).fetchall()
        cutoff = max(
            (
                str(ev.get("available_time") or ev.get("as_of"))
                for ev in version_evidence
                if ev.get("available_time") or ev.get("as_of")
            ),
            default=date.today().isoformat(),
        )
        content_hash = _hash(
            {
                "case_id": case_id,
                "six_dim": built["dims"],
                "industry_analysis": built.get("industry_analysis"),
                "valuation": built["valuation"],
                "conclusion": conclusion,
                "assumptions": assumptions,
                "counter_evidence": counter_evidence,
                "open_questions": open_questions,
                "evidence_ids": ev_ids,
                "evidence_hashes": sorted(str(ev.get("hash") or "") for ev in version_evidence),
                "cutoff": cutoff,
            }
        )
        row = conn.execute(
            """
            INSERT INTO inst_research_version
              (case_id, version_no, status, six_dim, industry_analysis, valuation, conclusion, assumptions,
               counter_evidence, open_questions, evidence_ids, content_hash, cutoff, created_by)
            VALUES (%s,%s,'pending_review',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,
            (
                case_id,
                version_no,
                _j(built["dims"]),
                _j(built.get("industry_analysis")),
                _j(built["valuation"]),
                conclusion,
                _j(assumptions),
                _j(counter_evidence),
                _j(open_questions),
                _j(ev_ids),
                content_hash,
                cutoff,
                actor_member_id,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE inst_evidence SET version_id=%s WHERE id = ANY(%s) AND org_id=%s AND case_id=%s",
            (int(row["id"]), ev_ids, org_id, case_id),
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
                "mode": mode_label,
                "targets": targets,
                "agents": built["agent_states"],
                "merged_from_version_no": int(existing["version_no"]) if existing else None,
                "content_hash": content_hash,
                "cutoff": cutoff,
            },
        )
    return get_case(org_id, case_id)  # type: ignore[return-value]

def review_research(
    org_id: int,
    version_id: int,
    *,
    decision: str,
    comment: str | None,
    targets: list[str] | None = None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    if decision not in {"approve", "return"}:
        raise ValueError("decision 必须是 approve/return")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
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
            row = _ensure_version_hash(conn, row)
            gate = evaluate_research_gate(_row_dict(row) or {})
            if gate["status"] == "block":
                raise PermissionError("研究门禁未通过：" + "；".join(
                    x["detail"] for x in gate["checks"] if x["status"] == "block"
                ))
            conn.execute(
                "UPDATE inst_research_version SET status='approved', frozen_at=NOW(), locked_at=COALESCE(locked_at,NOW()), approved_by=%s, approved_at=NOW() WHERE id=%s",
                (actor_member_id, version_id),
            )
            _set_case_stage(
                conn,
                org_id=org_id,
                case_id=int(row["case_id"]),
                to_stage=2,
                trigger="research.lock",
                actor_member_id=actor_member_id,
                gate_status=gate["status"],
                gate_checks=gate["checks"],
                object_type="inst_research_version",
                object_id=version_id,
                detail={"version_no": int(row.get("version_no") or 0), "content_hash": row.get("content_hash")},
            )
        else:
            if targets and not str(comment or "").strip():
                raise ValueError("退回时必须填写退回原因")
            conn.execute(
                "UPDATE inst_research_version SET status='changed' WHERE id=%s", (version_id,)
            )
            _set_case_stage(
                conn,
                org_id=org_id,
                case_id=int(row["case_id"]),
                to_stage=1,
                trigger="research.return",
                actor_member_id=actor_member_id,
                to_state="returned",
                object_type="inst_research_version",
                object_id=version_id,
                detail={"comment": comment, "targets": targets},
            )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action=f"research.review.{decision}",
            object_type="inst_research_version",
            object_id=version_id,
            before={"status": row["status"]},
            after={"decision": decision, "comment": comment, "targets": targets},
        )
    if decision == "return" and targets:
        return generate_research(
            org_id,
            int(row["case_id"]),
            targets=targets,
            actor_member_id=actor_member_id,
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
        _require_role(member, "manager")
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


def _six_dim_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = []
    return [x for x in (value or []) if isinstance(x, dict)]


def evaluate_research_gate(version: dict[str, Any]) -> dict[str, Any]:
    """v3 研究定稿门禁：六维完整、低置信处理、数据门禁、证据与 hash。"""
    dims = _six_dim_list(version.get("six_dim"))
    by_key = {str(d.get("key")): d for d in dims if d.get("key")}
    checks: list[dict[str, Any]] = []
    blocking = False

    required = [x[0] for x in SIX_DIM_DEFS]
    missing = [k for k in required if k not in by_key]
    checks.append({
        "key": "six_dim_complete",
        "label": "六维 6/6",
        "status": "block" if missing else "pass",
        "detail": f"缺失：{', '.join(missing)}" if missing else "六维齐全",
    })
    blocking = blocking or bool(missing)

    low: list[str] = []
    for key in required:
        d = by_key.get(key) or {}
        rating = d.get("rating")
        confidence = d.get("confidence")
        resolved = ((version.get("dim_reviews") or {}).get(key) or {}).get("decision") == "approve"
        is_low = (rating is not None and float(rating) < 3.3) or (
            confidence is not None and float(confidence) < 0.66
        )
        if is_low and not resolved:
            low.append(str(d.get("title") or key))
    checks.append({
        "key": "low_confidence",
        "label": "低置信项已处理",
        "status": "block" if low else "pass",
        "detail": f"未处理：{'、'.join(low)}" if low else "无低置信项",
    })
    blocking = blocking or bool(low)

    data_fail: list[str] = []
    for key in required:
        d = by_key.get(key) or {}
        gate = str(d.get("gate") or "")
        completeness = d.get("data_completeness") or {}
        if gate == "fail" or str(completeness.get("gate_cap") or "") == "fail":
            data_fail.append(str(d.get("title") or key))
    checks.append({
        "key": "data_gate",
        "label": "数据门禁",
        "status": "block" if data_fail else "pass",
        "detail": f"gate=fail：{'、'.join(data_fail)}" if data_fail else "无 fail 维度",
    })
    blocking = blocking or bool(data_fail)

    failed_agents = [
        str(d.get("title") or d.get("key") or "")
        for d in dims
        if str(d.get("agent_error") or "").strip()
    ]
    checks.append({
        "key": "agent_health",
        "label": "Agent 执行完整",
        "status": "block" if failed_agents else "pass",
        "detail": f"失败维度：{'、'.join(failed_agents)}" if failed_agents else "六维 Agent 均返回有效结果",
    })
    blocking = blocking or bool(failed_agents)

    evidence_ids = [x for x in (version.get("evidence_ids") or []) if str(x).strip()]
    checks.append({
        "key": "evidence",
        "label": "证据包",
        "status": "pass" if evidence_ids else "block",
        "detail": f"{len(evidence_ids)} 条证据" if evidence_ids else "无证据 ID，需补充证据或显式带缺口锁定",
    })
    blocking = blocking or not evidence_ids
    status = "block" if blocking else ("warn" if any(x["status"] == "warn" for x in checks) else "pass")
    return {"status": status, "checks": checks}


def research_gate(org_id: int, version_id: int) -> dict[str, Any]:
    """只读预览 R3 门禁；锁定前页面据此显示缺口与需处理的低置信项。"""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT v.*
              FROM inst_research_version v
              JOIN inst_research_case c ON c.id=v.case_id
             WHERE v.id=%s AND c.org_id=%s
            """,
            (version_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("研究版本不存在")
        version = _row_dict(_ensure_version_hash(conn, row)) or {}
    return evaluate_research_gate(version)


def lock_research(
    org_id: int,
    version_id: int,
    *,
    actor_member_id: int | None,
    allow_gaps: bool = False,
    comment: str | None = None,
) -> dict[str, Any]:
    """v3 研究定稿：门禁通过后锁定 R3，阶段 1→2。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        row = conn.execute(
            """
            SELECT v.*, c.id AS case_id, c.stage_no
              FROM inst_research_version v
              JOIN inst_research_case c ON c.id=v.case_id
             WHERE v.id=%s AND c.org_id=%s
            """,
            (version_id, org_id),
        ).fetchone()
        if not row:
            raise LookupError("研究版本不存在")
        if row.get("locked_at"):
            return get_case(org_id, int(row["case_id"]))  # type: ignore[return-value]
        version = _row_dict(_ensure_version_hash(conn, row)) or {}
        gate = evaluate_research_gate(version)
        if gate["status"] == "block" and not allow_gaps:
            raise PermissionError("研究门禁未通过：" + "；".join(
                x["detail"] for x in gate["checks"] if x["status"] == "block"
            ))
        status = "warn" if gate["status"] == "block" and allow_gaps else gate["status"]
        conn.execute(
            """
            UPDATE inst_research_version
               SET status='approved', frozen_at=COALESCE(frozen_at,NOW()),
                   locked_at=COALESCE(locked_at,NOW()), approved_by=%s, approved_at=NOW()
             WHERE id=%s
            """,
            (actor_member_id, version_id),
        )
        _set_case_stage(
            conn,
            org_id=org_id,
            case_id=int(row["case_id"]),
            to_stage=2,
            trigger="research.lock",
            actor_member_id=actor_member_id,
            gate_status=status,
            gate_checks=gate["checks"],
            object_type="inst_research_version",
            object_id=version_id,
            detail={"version_no": int(row.get("version_no") or 0), "allow_gaps": allow_gaps, "comment": comment},
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.lock",
            object_type="inst_research_version",
            object_id=version_id,
            after={"case_id": int(row["case_id"]), "gate": gate, "allow_gaps": allow_gaps},
        )
    return get_case(org_id, int(row["case_id"]))  # type: ignore[return-value]


def reopen_research(
    org_id: int, case_id: int, *, reason: str, actor_member_id: int | None
) -> dict[str, Any]:
    """研究重开：锁定的下游议案作废、授权撤销，阶段回到 1。"""
    if not str(reason or "").strip():
        raise ValueError("重开研究必须填写原因")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager", "partner")
        case = conn.execute(
            "SELECT * FROM inst_research_case WHERE id=%s AND org_id=%s", (case_id, org_id)
        ).fetchone()
        if not case:
            raise LookupError("研究案不存在")
        conn.execute(
            "UPDATE inst_research_version SET superseded_at=NOW(), status='changed' "
            "WHERE case_id=%s AND status='approved' AND superseded_at IS NULL",
            (case_id,),
        )
        conn.execute(
            "UPDATE inst_proposal SET stale_at=NOW(), stale_reason=%s WHERE case_id=%s AND stale_at IS NULL",
            (reason[:500], case_id),
        )
        conn.execute(
            "UPDATE inst_proposal SET status='rejected', updated_at=NOW() "
            "WHERE case_id=%s AND status IN ('partner_review','risk_precheck','chairman_review','authorized')",
            (case_id,),
        )
        conn.execute(
            """
            UPDATE inst_authorization a
               SET status='revoked', revoked_at=NOW(), revoke_reason=%s
              FROM inst_proposal_version pv
              JOIN inst_proposal p ON p.id=pv.proposal_id
             WHERE a.proposal_version_id=pv.id AND p.case_id=%s AND a.status='qualified'
            """,
            (reason[:500], case_id),
        )
        _set_case_stage(
            conn,
            org_id=org_id,
            case_id=case_id,
            to_stage=1,
            trigger="research.reopen",
            actor_member_id=actor_member_id,
            to_state="returned",
            object_type="inst_research_case",
            object_id=case_id,
            detail={"reason": reason},
        )
        conn.execute("UPDATE inst_research_case SET reopened_at=NOW() WHERE id=%s", (case_id,))
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.reopen",
            object_type="inst_research_case",
            object_id=case_id,
            after={"reason": reason},
        )
    return get_case(org_id, case_id)  # type: ignore[return-value]


def get_company(org_id: int, company_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = repo.company(OrgScope(org_id), company_id, conn=conn)
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


def company_bars(
    org_id: int, company_id: int, *, limit: int = 120, period: str = "day"
) -> dict[str, Any]:
    """行情 K 线。日/周/月由日线聚合；分钟线依赖行情源，未接入时明确返回不可用。"""
    if period not in {"min", "1min", "5min", "15min", "60min", "day", "week", "month"}:
        raise ValueError("period 必须是 min/1min/5min/15min/60min/day/week/month")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT symbol, name, market FROM inst_company WHERE id=%s AND org_id=%s",
            (company_id, org_id),
        ).fetchone()
    if not row:
        raise LookupError("公司不存在")
    symbol = str(row["symbol"])
    limit = max(20, min(int(limit), 300))
    if period.endswith("min"):
        return {
            "symbol": symbol,
            "name": row["name"],
            "market": row["market"],
            "adjust": "none",
            "period": period,
            "available": False,
            "note": "当前行情源仅提供日线，分钟线尚未接入；日/周/月可正常查看。",
            "items": [],
        }
    fetch_limit = 5000 if period in {"week", "month"} else limit
    items = md.bar_history(symbol, adjust="none", limit=fetch_limit)
    if period in {"week", "month"}:
        items = _resample_bars(items, period)[-limit:]
    return {
        "symbol": symbol,
        "name": row["name"],
        "market": row["market"],
        "adjust": "none",
        "period": period,
        "available": True,
        "items": items,
    }


def _resample_bars(items: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    """把日线聚合成周线/月线：开=首日开，高=最高，低=最低，收=末日收，量=合计。"""
    grouped: list[dict[str, Any]] = []
    key: Any = None
    for bar in items:
        day = date.fromisoformat(str(bar["trade_date"])[:10])
        bucket = day.isocalendar()[:2] if period == "week" else (day.year, day.month)
        if bucket != key:
            key = bucket
            grouped.append(
                {
                    "trade_date": str(bar["trade_date"])[:10],
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "volume": float(bar.get("volume") or 0),
                    "amount": float(bar.get("amount") or 0),
                }
            )
        else:
            cur = grouped[-1]
            cur["trade_date"] = str(bar["trade_date"])[:10]
            cur["high"] = max(cur["high"], float(bar["high"]))
            cur["low"] = min(cur["low"], float(bar["low"]))
            cur["close"] = float(bar["close"])
            cur["volume"] += float(bar.get("volume") or 0)
            cur["amount"] += float(bar.get("amount") or 0)
    return grouped


def _idea_data_sufficiency(company: dict[str, Any]) -> str:
    """立项三问的资料判断：美股/港股当前只有行情，按 missing 处理。"""
    market = str(company.get("market") or "CN").upper()
    if market in {"US", "HK"}:
        return "missing"
    status = str(company.get("data_status") or "missing")
    if status == "real":
        return "sufficient"
    if status in {"partial", "demo"}:
        return "partial"
    return "missing"


def _idea_questions(
    company: dict[str, Any],
    source: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """规则版立项三问。

    只使用已有行情/资料状态，不冒充 AI 判断；能力圈始终标为 unknown，
    由投资经理在立项弹窗中确认。后续接入 `inst.idea` 时可替换本函数。
    """
    sufficiency = _idea_data_sufficiency(company)
    if source == "holdings":
        why_now = "当前持仓；需要复核原投资论点是否仍成立，以及是否继续持有。"
    elif source == "watch":
        points = company.get("research_points") or []
        why_now = str(points[0]) if points else "已在观察池，等待新的价格或基本面变化。"
    else:
        why_now = str(reason or "").strip() or "量化初筛通过，需要说明为什么是现在。"

    gaps: list[str] = []
    if str(company.get("market") or "CN").upper() in {"US", "HK"}:
        gaps.append("美股/港股暂无财务、公告、行业与指数数据源，只有行情")
    elif sufficiency == "partial":
        gaps.append("财务/公告数据不完整，关键结论需回源核对")
    elif sufficiency == "missing":
        gaps.append("核心财务/公告数据缺失，暂不能形成可靠判断")
    if not str(company.get("industry") or "").strip():
        gaps.append("行业分类待补充")

    suggestion = "initiate" if sufficiency == "sufficient" else "watch"
    reason_text = {
        "sufficient": "资料齐备，可进入研究；能力圈需投资经理确认。",
        "partial": "资料部分缺失，建议先观察并补齐关键数据。",
        "missing": "核心资料缺失，建议观察或放弃，不直接立项。",
    }[sufficiency]
    return {
        "source": source,
        "why_now": why_now,
        "circle_of_competence": "unknown",
        "circle_note": "需投资经理确认：能否用三句话说清它怎么赚钱？",
        "data_sufficiency": "insufficient" if sufficiency == "missing" else sufficiency,
        "suggestion": suggestion,
        "gate": "pass" if sufficiency == "sufficient" else "watch",
        "reason": reason_text,
        "data_gaps": gaps,
    }


def record_idea_decision(
    org_id: int,
    company_id: int,
    *,
    source: str,
    action: str,
    reason: str | None,
    circle_confirmed: bool,
    actor_member_id: int | None,
) -> dict[str, Any]:
    """记录投资经理的立项/观察/放弃决策。

    立项必须同时满足：资料充分 + 能力圈已确认；观察/放弃必须写理由。
    决策写入 inst_idea_decision，公司池状态同步更新，并写审计。
    """
    if source not in {"push", "watch", "holdings"}:
        raise ValueError("source 必须是 push/watch/holdings")
    if action not in {"initiate", "watch", "reject"}:
        raise ValueError("action 必须是 initiate/watch/reject")
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("请填写决策理由")

    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        row = conn.execute(
            "SELECT * FROM inst_company WHERE id=%s AND org_id=%s", (company_id, org_id)
        ).fetchone()
        if not row:
            raise LookupError("公司不存在")
        company = dict(row)
        idea = _idea_questions(company, source, reason)
        if action == "initiate":
            if idea["data_sufficiency"] in {"missing", "insufficient"}:
                raise ValueError("核心资料缺失，建议先观察，不能立项")
            if not circle_confirmed:
                raise ValueError("立项前需确认能力圈：能否用三句话说清它怎么赚钱")

        case_id: int | None = None
        case_no: str | None = None
        if action == "initiate":
            case_no = f"RC-{date.today():%Y%m%d}-{str(company['symbol']).split('.')[0]}-{_uid()[:4]}"
            case_row = conn.execute(
                "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, stage_no, stage_key, stage_gate, created_by) "
                "VALUES (%s,%s,%s,'draft',1,'research','{\"stage_no\":1,\"gate\":\"研究定稿\"}'::jsonb,%s) RETURNING id",
                (org_id, company_id, case_no, actor_member_id),
            ).fetchone()
            case_id = int(case_row["id"])

        pool_status = {"initiate": "research", "watch": "watch", "reject": "dropped"}[action]
        before = {"pool_status": company.get("pool_status"), "drop_reason": company.get("drop_reason")}
        conn.execute(
            "UPDATE inst_company SET pool_status=%s, drop_reason=%s, updated_at=NOW() "
            "WHERE id=%s AND org_id=%s",
            (pool_status, reason if action == "reject" else None, company_id, org_id),
        )
        decision = conn.execute(
            """
            INSERT INTO inst_idea_decision
              (org_id, company_id, source, action, reason, circle_confirmed, data_sufficiency, actor_member_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                org_id,
                company_id,
                source,
                action,
                reason,
                bool(circle_confirmed),
                idea["data_sufficiency"],
                actor_member_id,
            ),
        ).fetchone()
        decision_id = int(decision["id"])
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="idea.decision",
            object_type="inst_idea_decision",
            object_id=decision_id,
            before=before,
            after={
                "company_id": company_id,
                "source": source,
                "action": action,
                "reason": reason,
                "circle_confirmed": bool(circle_confirmed),
                "data_sufficiency": idea["data_sufficiency"],
                "case_id": case_id,
            },
        )
        if case_id:
            _audit(
                conn,
                org_id=org_id,
                actor_member_id=actor_member_id,
                action="research.case.create",
                object_type="inst_research_case",
                object_id=case_id,
                after={"company_id": company_id, "case_no": case_no, "from_idea_decision": decision_id},
            )
    return {
        "ok": True,
        "id": decision_id,
        "action": action,
        "pool_status": pool_status,
        "case_id": case_id,
        "idea": idea,
    }


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
        item = {
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
        item["idea"] = _idea_questions(item, "push", item["reason"])
        items.append(item)
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

__all__ = [
    "_agent_payload",
    "_apply_data_gate",
    "_build_research",
    "_clean_agent_text",
    "_data_completeness",
    "_derive_case_stage",
    "_dim_status",
    "_ensure_version_hash",
    "_existing_case_id",
    "_first_sentence",
    "_four_line_output",
    "_history_summary",
    "_idea_data_sufficiency",
    "_idea_questions",
    "_lock_company_case",
    "_median",
    "_merge_agent_results",
    "_merge_industry",
    "_net_debt_proxy",
    "_overall_score",
    "_peer_summary",
    "_resample_bars",
    "_run_dimension_agent",
    "_run_dimension_agents",
    "_run_industry_agent",
    "_six_dim_list",
    "_update_task_progress",
    "company_bars",
    "create_case",
    "evaluate_research_gate",
    "export_research",
    "generate_research",
    "get_case",
    "get_company",
    "ideas_push",
    "list_cases",
    "lock_research",
    "record_idea_decision",
    "reopen_research",
    "research_gate",
    "review_research",
    "review_research_dimension",
    "start_research",
]
